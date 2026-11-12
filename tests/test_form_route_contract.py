"""Guard rendered form field names against the route's ``request.form`` reads."""
from __future__ import annotations

import ast
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from netcup_api_filter.models import (
    BackendProvider,
    BackendService,
    ManagedDomainRoot,
    OwnerTypeEnum,
    VisibilityEnum,
)
from netcup_api_filter.password_reset import generate_reset_token
from tests.form_contract_helpers import ParsedForm, parse_forms
from tests.http_helpers import login_admin, login_portal


APP_ROOT = Path(__file__).resolve().parents[1] / "src" / "netcup_api_filter"
MODULE_PATHS = {
    "account": APP_ROOT / "api" / "account.py",
    "admin": APP_ROOT / "api" / "admin.py",
}

# Thin route aliases delegate to the function that owns the form reads. Keep
# these explicit so the AST scan cannot mistake an alias for a no-op handler.
HANDLER_ALIASES = {
    "account.request_realm": "request_realm_view",
}


# Handler reads that are genuinely optional or are compatibility aliases for
# this rendered form. These are explicit so a future dropped required field
# cannot hide behind a broad wildcard.
OPTIONAL_HANDLER_KEYS = {
    "account.create_new_token": {"record_types", "operations"},
    "admin.account_approve": set(),
    "admin.account_change_email": set(),
    "admin.account_disable": set(),
    "admin.account_regenerate_alias": set(),
    "admin.account_reset_password": set(),
    "admin.config_email": {
        "admin_email",
        "notify_new_account",
        "notify_realm_request",
        "notify_security",
        "reply_to",
        "test_only",
    },
    "admin.config_netcup": {"api_endpoint", "customer_number"},
    "admin.config_geoip": set(),
    "admin.token_revoke": {"reason"},
    "admin.update_security_settings": set(),
    "admin.change_password": {"email"},
}

# Visible controls whose purpose is enforced entirely client-side (or which
# are intentionally not persisted by the server). They are per-endpoint and
# documented here rather than silently waived by the comparison.
TEMPLATE_ONLY_FIELDS = {
    "account.login": {
        "remember": "HTML-only convenience control; portal sessions are server-managed",
    },
    "account.register": {
        "terms": "browser-required acknowledgement; no server-side acceptance field exists",
    },
    "account.disable_2fa": {
        "totp_code": "optional UI confirmation; the authoritative check is the account password",
    },
}


def _read_form_keys(module: str, endpoint: str) -> frozenset[str]:
    tree = ast.parse(MODULE_PATHS[module].read_text(encoding="utf-8"))
    handler_name = HANDLER_ALIASES.get(endpoint, endpoint.rsplit(".", 1)[-1])
    function = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == handler_name
        ),
        None,
    )
    assert function is not None, (
        f"handler {handler_name!r} for {endpoint!r} not found in {MODULE_PATHS[module]}"
    )

    keys: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr not in {"get", "getlist"}:
                continue
            receiver = node.func.value
            if not (
                isinstance(receiver, ast.Attribute)
                and receiver.attr == "form"
                and isinstance(receiver.value, ast.Name)
                and receiver.value.id == "request"
            ):
                continue
            if node.args and isinstance(node.args[0], ast.Constant):
                if isinstance(node.args[0].value, str):
                    keys.add(node.args[0].value)
        elif isinstance(node, ast.Subscript):
            receiver = node.value
            if not (
                isinstance(receiver, ast.Attribute)
                and receiver.attr == "form"
                and isinstance(receiver.value, ast.Name)
                and receiver.value.id == "request"
            ):
                continue
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(key.value)
    return frozenset(keys)


def _contract_diff(
    endpoint: str,
    form_fields: frozenset[str],
    handler_reads: frozenset[str],
) -> tuple[frozenset[str], frozenset[str]]:
    template_only = frozenset(TEMPLATE_ONLY_FIELDS.get(endpoint, {}))
    dropped = form_fields - handler_reads - template_only
    optional = frozenset(OPTIONAL_HANDLER_KEYS.get(endpoint, set()))
    required = handler_reads - optional
    missing = required - form_fields
    return dropped, missing


def _assert_form_matches(
    app,
    page_path: str,
    html: str,
    *,
    allow_actionless: bool = False,
) -> set[str]:
    covered: set[str] = set()
    bind = app.url_map.bind("localhost")
    for form in parse_forms(html):
        if form.method != "post":
            continue
        path = urlsplit(form.action).path if form.action else urlsplit(page_path).path
        try:
            endpoint, _values = bind.match(path, method="POST")
        except Exception:
            if allow_actionless and not form.action:
                continue
            raise AssertionError(
                f"POST form on {page_path} points at unmapped endpoint {path!r}"
            )

        module = endpoint.split(".", 1)[0]
        if module not in MODULE_PATHS:
            pytest.fail(
                f"{page_path} rendered a form for unsupported blueprint {endpoint!r}"
            )
        handler_reads = _read_form_keys(module, endpoint)
        dropped, missing = _contract_diff(endpoint, form.names, handler_reads)
        assert not dropped, (
            f"{endpoint}: template fields are not read by the handler: "
            f"{sorted(dropped)} (form={sorted(form.names)}, handler={sorted(handler_reads)})"
        )
        assert not missing, (
            f"{endpoint}: required handler fields are absent from the form: "
            f"{sorted(missing)} (form={sorted(form.names)}, handler={sorted(handler_reads)})"
        )
        covered.add(endpoint)
    return covered


def _get_page(client, path: str, *, status: int = 200) -> str:
    response = client.get(path)
    assert response.status_code == status, (
        f"GET {path} returned {response.status_code}, expected {status}"
    )
    return response.get_data(as_text=True)


def test_rendered_form_fields_match_route_handlers(
    app, db, make_account, make_realm, make_token
):
    owner = make_account(
        "forms-owner",
        password="OldPassword-2024:ABC#xyz",
        telegram_enabled=1,
        telegram_chat_id="12345",
    )
    main_realm = make_realm(
        owner,
        domain="example.com",
        realm_type="subdomain",
        realm_value="forms",
        operations=("read", "update", "create"),
    )
    second_realm = make_realm(
        owner,
        domain="example.org",
        realm_type="host",
        realm_value="second",
    )
    token, _plain = make_token(
        main_realm,
        name="forms-token",
        ip_ranges=["203.0.113.0/24"],
    )
    target = make_account("forms-target", password="OldPassword-2024:ABC#xyz")
    admin = make_account("forms-admin", is_admin=1)

    provider = BackendProvider.query.first()
    assert provider is not None, "test app did not seed backend providers"
    platform_owner = OwnerTypeEnum.query.filter_by(owner_code=OwnerTypeEnum.PLATFORM).one()
    public_visibility = VisibilityEnum.query.filter_by(
        visibility_code=VisibilityEnum.PUBLIC
    ).one()
    public_backend = BackendService(
        provider_id=provider.id,
        service_name="forms-public-backend",
        display_name="Forms public backend",
        owner_type_id=platform_owner.id,
        config="{}",
        is_active=True,
    )
    db.session.add(public_backend)
    db.session.flush()
    db.session.add(
        ManagedDomainRoot(
            backend_service_id=public_backend.id,
            root_domain="forms.example.net",
            dns_zone="forms.example.net",
            visibility_id=public_visibility.id,
            display_name="Forms public zone",
            is_active=True,
        )
    )
    db.session.commit()

    anonymous_client = app.test_client()
    reset_token, _expiry = generate_reset_token(
        owner, source_ip=None, token_type="reset"
    )
    invite_token, _expiry = generate_reset_token(
        target, source_ip=None, token_type="invite"
    )

    covered = set()
    for path, kwargs in [
        ("/account/login", {}),
        ("/account/forgot-password", {}),
        (f"/account/reset-password/{reset_token}", {}),
        (f"/account/invite/{invite_token}", {}),
        ("/account/register", {}),
    ]:
        covered |= _assert_form_matches(
            app,
            path,
            _get_page(anonymous_client, path),
            **kwargs,
        )

    portal_client = app.test_client()
    login_portal(portal_client, owner)
    for path, kwargs in [
        (f"/account/realms/{main_realm.id}/tokens/new", {}),
        (f"/account/realms/{main_realm.id}/dns/create", {}),
        ("/account/tokens/new", {}),
        ("/account/realms/request", {}),
        ("/account/change-password", {}),
        ("/account/settings/recovery-codes", {}),
        (f"/account/tokens/{token.id}/regenerate", {}),
        (f"/account/realms/{main_realm.id}", {"allow_actionless": True}),
        ("/account/security", {}),
        ("/account/settings/telegram/link", {}),
    ]:
        covered |= _assert_form_matches(
            app,
            path,
            _get_page(portal_client, path),
            **kwargs,
        )

    admin_client = app.test_client()
    login_admin(admin_client, admin)
    for path, kwargs in [
        ("/admin/settings", {}),
        ("/admin/config/netcup", {}),
        ("/admin/config/email", {}),
        ("/admin/change-password", {}),
        ("/admin/accounts", {}),
        (f"/admin/accounts/{target.id}", {}),
    ]:
        covered |= _assert_form_matches(
            app,
            path,
            _get_page(admin_client, path),
            **kwargs,
        )

    expected_core = {
        "account.accept_invite",
        "account.change_password_page",
        "account.create_new_token",
        "account.create_token_select",
        "account.ddns_update",
        "account.dns_record_create",
        "account.disable_2fa",
        "account.forgot_password",
        "account.generate_recovery_codes",
        "account.login",
        "account.register",
        "account.request_realm",
        "account.reset_password",
        "account.telegram_send_test_message",
        "account.unlink_telegram",
        "admin.account_change_email",
        "admin.account_regenerate_alias",
        "admin.account_reset_password",
        "admin.change_password",
        "admin.config_email",
        "admin.config_geoip",
        "admin.config_netcup",
        "admin.update_security_settings",
    }
    assert expected_core <= covered, (
        f"form guard missed core endpoints: {sorted(expected_core - covered)}"
    )


def test_contract_diff_rejects_the_old_b057_and_b058_shapes():
    """The comparison must go red if either shipped mismatch is reintroduced."""
    b057_old_fields = frozenset(
        {
            "realm_id",
            "token_name",
            "expires_in",
            "ip_whitelist",
            "rate_limit_per_minute",
            "notes",
        }
    )
    b057_old_reads = frozenset(
        {"token_name", "expires", "ip_ranges", "description", "record_types", "operations"}
    )
    dropped, missing = _contract_diff(
        "account.create_new_token", b057_old_fields, b057_old_reads
    )
    assert {
        "expires_in",
        "ip_whitelist",
        "rate_limit_per_minute",
        "notes",
    } <= dropped
    assert {"expires", "ip_ranges"} <= missing

    b058_old_fields = frozenset({"password", "confirm_password"})
    b058_old_reads = frozenset({"new_password", "confirm_password"})
    dropped, missing = _contract_diff(
        "account.reset_password", b058_old_fields, b058_old_reads
    )
    assert dropped == {"password"}
    assert missing == {"new_password"}

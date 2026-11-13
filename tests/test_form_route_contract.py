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
from tests.form_contract_helpers import parse_forms
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


# Handler reads the rendered form may legitimately omit. Every entry names the
# reason; a key whose field the template renders unconditionally must NOT be
# listed here, or a dropped field would silently reset the setting and the
# guard would stay green (the B057 class). Endpoints with nothing optional are
# simply absent.
OPTIONAL_HANDLER_KEYS = {
    # No UI renders operations/record-type restrictions; the route accepts them
    # for scripted clients and falls back to the realm's scope.
    "account.create_new_token": {"record_types", "operations"},
    # `test_only` is appended by the "Send test email" JS (config_email.html
    # ~361), never rendered as a field. Every other read is a rendered field.
    "admin.config_email": {"test_only"},
    # Legacy aliases read as fallbacks for the canonical customer_id/api_url
    # (admin.py config_netcup); the template renders only the canonical names.
    # (The "Test connection" JS appends `test_only`, which this handler does not
    # read at all, so it needs no entry.)
    "admin.config_netcup": {"api_endpoint", "customer_number"},
    # Has a handler default ("Revoked by admin"); no admin form renders it.
    "admin.token_revoke": {"reason"},
    # Rendered only while the admin still needs an email (needs_email_setup).
    "admin.change_password": {"email"},
}

# Visible controls the handler never reads. Each one is either a client-side
# control or a KNOWN DEFECT with a backlog id; a defect entry is removed when
# its item lands, so the guard then pins the fix.
TEMPLATE_ONLY_FIELDS = {
    "account.login": {
        "remember": "KNOWN DEFECT B077: the 'Remember me' checkbox is a UI no-op; "
        "the login handler never reads it. Waived until B077 lands",
    },
    "account.register": {
        "terms": "browser-required acknowledgement; no server-side acceptance field exists",
    },
    "account.disable_2fa": {
        "totp_code": "KNOWN DEFECT B073: the form requires a 2FA code the handler "
        "never verifies (it checks only the password); waived until B073 lands",
    },
}

# Required handler keys a specific page's form is known to omit, keyed by
# (page path, endpoint). Scoped to one page so the endpoint's own page stays
# fully guarded. The guard fails if a listed key is no longer missing, so an
# entry must be deleted when its defect is fixed.
PAGE_MISSING_WAIVERS = {
    # KNOWN DEFECT (found by this guard; B081): the SMTP
    # quick form on /admin/settings posts to admin.config_email without these
    # fields, and the handler overwrites them on every save, so saving that form
    # clears the reply-to and admin addresses and turns the notifications off.
    # /admin/config/email renders all of them and is guarded without a waiver.
    ("/admin/settings", "admin.config_email"): frozenset(
        {
            "admin_email",
            "notify_new_account",
            "notify_realm_request",
            "notify_security",
            "reply_to",
        }
    ),
}

# POST endpoints whose rendered forms the guard test below must reach and
# compare. Pinned so coverage cannot shrink silently.
GUARDED_ENDPOINTS = frozenset(
    {
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
        "account.regenerate_token",
        "account.register",
        "account.request_realm",
        "account.reset_password",
        "account.revoke_all_sessions",
        "account.telegram_send_test_message",
        "account.unlink_telegram",
        "admin.account_change_email",
        "admin.account_delete",
        "admin.account_disable",
        "admin.account_regenerate_alias",
        "admin.account_reset_password",
        "admin.change_password",
        "admin.config_email",
        "admin.config_geoip",
        "admin.config_netcup",
        "admin.update_security_settings",
    }
)

_MULTI_ACTION = (
    "multi-action handler dispatched by a hidden `action` field; the guard's "
    "union-of-reads model cannot express it"
)
_LOGIN_2FA = "needs a pending-2FA login session; not yet covered"
_NOT_YET = "not yet covered; cheap to add later"

# Every account/admin POST endpoint the guard does NOT pin, with the reason.
# test_every_post_endpoint_is_guarded_or_listed_uncovered keeps this table
# honest in both directions: a new POST route must be guarded or listed here,
# and an entry for a removed route fails.
UNCOVERED_ENDPOINTS = {
    # --- account blueprint ---
    "account.login_2fa": _LOGIN_2FA,
    "account.verify_2fa_code": _LOGIN_2FA + " (no template posts here; "
    "login_2fa.html posts to account.login_2fa)",
    "account.resend_2fa_code": _LOGIN_2FA,
    "account.verify_email": "needs a registration session (registration_id); " + _NOT_YET,
    "account.resend_code": "posted from verify_email.html, which needs a registration "
    "session; " + _NOT_YET,
    "account.register_realms": _MULTI_ACTION,
    "account.settings": "KNOWN DEFECT B074 and " + _MULTI_ACTION + "; the "
    "delete_account, disable_totp and unlink_telegram actions are rendered but "
    "not handled",
    "account.setup_totp": "POST needs a TOTP secret pending in the session; " + _NOT_YET,
    "account.setup_2fa": "alias that delegates to account.setup_totp; no template "
    "posts to it",
    "account.token_create": "alias that delegates to account.create_new_token "
    "(guarded); templates only link to it with GET",
    "account.request_realm_view": "same handler as account.request_realm (guarded); "
    "the request form posts to that alias",
    "account.dns_record_edit": "GET loads the record from the realm's DNS backend; "
    "needs a backend mock",
    "account.dns_record_delete": "form action is set by JS (dns_records.html), so "
    "it cannot be mapped statically",
    "account.revoke_user_token": "form action is set by JS (realm_detail.html, "
    "tokens.html), so it cannot be mapped statically",
    "account.revoke_session": "rendered only for non-current sessions; compared "
    "when present but not pinned",
    "account.link_telegram": "link form renders only for an unlinked account; the "
    "guard's owner is linked so unlink/test are covered",
    "account.backend_create": "provider config fields are read in "
    "_build_backend_config_from_form, which the per-handler AST scan does not follow",
    "account.backend_edit": "provider config fields are read in "
    "_build_backend_config_from_form, which the per-handler AST scan does not follow",
    "account.backend_test": "needs a user backend; " + _NOT_YET,
    "account.backend_delete": "needs a user backend; " + _NOT_YET,
    # --- admin blueprint ---
    "admin.login": "tests authenticate through login_admin(); " + _NOT_YET,
    "admin.login_2fa": _LOGIN_2FA,
    "admin.resend_2fa": _LOGIN_2FA,
    "admin.setup_totp": _MULTI_ACTION,
    "admin.generate_recovery_codes": _MULTI_ACTION,
    "admin.account_create": _NOT_YET,
    "admin.account_add_realm": _NOT_YET,
    "admin.account_approve": "rendered only for unapproved accounts; the guard's "
    "accounts are all active",
    "admin.account_reject": "form action is set by JS (accounts_pending.html), so "
    "it cannot be mapped statically",
    "admin.realm_approve": "rendered only for pending realms; " + _NOT_YET,
    "admin.realm_reject": "rendered for pending realms (realm_detail.html) and via "
    "JS (realms_pending.html); " + _NOT_YET,
    "admin.realm_revoke": "rendered on the admin realm detail page; " + _NOT_YET,
    "admin.token_revoke": "rendered only for accounts with active tokens; " + _NOT_YET,
    "admin.audit_trim": "no template posts to it; " + _NOT_YET,
    "admin.config_email_test": "legacy endpoint; no template posts to it",
    "admin.api_accounts_bulk": "JSON API called by fetch(), not a form post",
    "admin.api_realms_bulk": "JSON API called by fetch(), not a form post",
    "admin.backend_create": "domain-root/backend/grant family; " + _NOT_YET,
    "admin.backend_edit": "domain-root/backend/grant family; " + _NOT_YET,
    "admin.backend_test": "domain-root/backend/grant family; " + _NOT_YET,
    "admin.backend_enable": "domain-root/backend/grant family; " + _NOT_YET,
    "admin.backend_disable": "domain-root/backend/grant family; " + _NOT_YET,
    "admin.backend_delete": "domain-root/backend/grant family; " + _NOT_YET,
    "admin.domain_root_create": "domain-root/backend/grant family; " + _NOT_YET,
    "admin.domain_root_edit": "domain-root/backend/grant family; " + _NOT_YET,
    "admin.domain_root_enable": "domain-root/backend/grant family; " + _NOT_YET,
    "admin.domain_root_disable": "domain-root/backend/grant family; " + _NOT_YET,
    "admin.domain_root_delete": "domain-root/backend/grant family; " + _NOT_YET,
    "admin.domain_root_grant_add": "domain-root/backend/grant family; " + _NOT_YET,
    "admin.domain_root_grant_revoke": "domain-root/backend/grant family; " + _NOT_YET,
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
        waived = PAGE_MISSING_WAIVERS.get((urlsplit(page_path).path, endpoint))
        if waived is not None:
            assert waived <= missing, (
                f"{endpoint} on {page_path}: waived keys are no longer missing, "
                f"delete the PAGE_MISSING_WAIVERS entry: {sorted(waived - missing)}"
            )
            missing = missing - waived
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

    assert GUARDED_ENDPOINTS <= covered, (
        f"form guard missed pinned endpoints: {sorted(GUARDED_ENDPOINTS - covered)}"
    )


def _blueprint_post_endpoints(app) -> frozenset[str]:
    return frozenset(
        rule.endpoint
        for rule in app.url_map.iter_rules()
        if "POST" in (rule.methods or ())
        and rule.endpoint.split(".", 1)[0] in MODULE_PATHS
    )


def test_every_post_endpoint_is_guarded_or_listed_uncovered(app):
    """No account/admin POST route may go silently unguarded, and the table cannot rot."""
    post_endpoints = _blueprint_post_endpoints(app)
    uncovered = frozenset(UNCOVERED_ENDPOINTS)

    assert not GUARDED_ENDPOINTS & uncovered, (
        f"endpoints both guarded and listed uncovered: {sorted(GUARDED_ENDPOINTS & uncovered)}"
    )
    unaccounted = post_endpoints - GUARDED_ENDPOINTS - uncovered
    assert not unaccounted, (
        "POST endpoints neither guarded nor listed in UNCOVERED_ENDPOINTS "
        f"(cover them or add a reason): {sorted(unaccounted)}"
    )
    stale = (GUARDED_ENDPOINTS | uncovered) - post_endpoints
    assert not stale, (
        f"guard tables name endpoints that are no longer POST routes: {sorted(stale)}"
    )
    assert all(reason.strip() for reason in UNCOVERED_ENDPOINTS.values())


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

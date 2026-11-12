"""Dynamic cross-tenant and cross-role authorization sweeps for portal routes."""
from __future__ import annotations

import json
import secrets
from collections import Counter
from datetime import datetime, timedelta

from http_helpers import login_portal, mint_csrf
from netcup_api_filter.models import (
    AccountSession,
    BackendProvider,
    BackendService,
    DomainRootGrant,
    GrantTypeEnum,
    ManagedDomainRoot,
    OwnerTypeEnum,
    VisibilityEnum,
)
from sweep_helpers import build_rule_path, database_snapshot, rule_methods, sweep_form, sweep_ip


# Every id-bearing /account route is listed. A new endpoint, path variable, or
# method fails collection of the sweep until it is classified here.
ID_ROUTE_CASES = {
    "account.create_new_token": (frozenset({"realm_id"}), frozenset({"GET", "POST"}), 302, "/account/dashboard"),
    "account.revoke_user_token": (frozenset({"token_id"}), frozenset({"POST"}), 302, "/account/dashboard"),
    "account.token_activity": (frozenset({"token_id"}), frozenset({"GET"}), 302, "/account/dashboard"),
    "account.api_realm_tokens": (frozenset({"realm_id"}), frozenset({"GET"}), 403, None),
    "account.realm_detail": (frozenset({"realm_id"}), frozenset({"GET"}), 302, "/account/dashboard"),
    "account.ddns_update": (frozenset({"realm_id"}), frozenset({"POST"}), 302, "/account/dashboard"),
    "account.dns_records": (frozenset({"realm_id"}), frozenset({"GET"}), 302, "/account/dashboard"),
    "account.dns_record_create": (frozenset({"realm_id"}), frozenset({"GET", "POST"}), 302, "/account/dashboard"),
    "account.dns_record_edit": (frozenset({"realm_id", "record_id"}), frozenset({"GET", "POST"}), 302, "/account/dashboard"),
    "account.dns_record_delete": (frozenset({"realm_id", "record_id"}), frozenset({"POST"}), 302, "/account/dashboard"),
    "account.regenerate_token": (frozenset({"token_id"}), frozenset({"GET", "POST"}), 302, "/account/dashboard"),
    "account.revoke_session": (frozenset({"session_id"}), frozenset({"POST"}), 302, "/account/security"),
    "account.token_create": (frozenset({"realm_id"}), frozenset({"GET", "POST"}), 302, "/account/dashboard"),
    "account.backend_detail": (frozenset({"backend_id"}), frozenset({"GET"}), 302, "/account/backends"),
    "account.backend_edit": (frozenset({"backend_id"}), frozenset({"GET", "POST"}), 302, "/account/backends"),
    "account.backend_test": (frozenset({"backend_id"}), frozenset({"POST"}), 302, "/account/backends"),
    "account.backend_zones": (frozenset({"backend_id"}), frozenset({"GET"}), 302, "/account/backends"),
    "account.backend_delete": (frozenset({"backend_id"}), frozenset({"POST"}), 302, "/account/backends"),
}

# No id-bearing account route is exempt from the ownership check.
ID_ROUTE_EXCEPTIONS = {}

# These routes intentionally support unauthenticated login, registration,
# invitation, reset, and logout flows. Every other portal/admin route must
# redirect an anonymous client to its matching login page.
PUBLIC_ROUTE_ALLOWLIST = {
    "account.login": {"GET": (200, None), "POST": (200, None)},
    "account.forgot_password": {"GET": (200, None), "POST": (200, None)},
    "account.reset_password": {"GET": (302, "/account/forgot-password"), "POST": (302, "/account/forgot-password")},
    "account.accept_invite": {"GET": (302, "/account/login"), "POST": (302, "/account/login")},
    "account.register": {"GET": (200, None), "POST": (200, None)},
    "account.verify_email": {"GET": (302, "/account/register"), "POST": (302, "/account/register")},
    "account.verify_email_link": {"GET": (302, "/account/register")},
    "account.register_realms": {"GET": (302, "/account/register"), "POST": (302, "/account/register")},
    "account.resend_code": {"POST": (302, "/account/register")},
    "account.pending": {"GET": (200, None)},
    "account.login_2fa": {"GET": (302, "/account/login"), "POST": (302, "/account/login")},
    "account.account_logout": {"GET": (302, "/account/login")},
    "admin.login": {"GET": (200, None), "POST": (200, None)},
    "admin.login_2fa": {"GET": (302, "/admin/login"), "POST": (302, "/admin/login")},
    "admin.resend_2fa": {"POST": (302, "/admin/login")},
    "admin.logout": {"GET": (302, "/admin/login")},
}

# A portal identity cannot be required to refuse calls to the public admin
# credential form. Its POST is a login attempt and deliberately updates the
# admin-login failure counter for invalid credentials.
PORTAL_TO_ADMIN_PUBLIC_EXCEPTIONS = {
    ("admin.login", "GET"): (200, None),
    ("admin.login", "POST"): (200, None),
}


def _create_foreign_resources(make_account, make_realm, make_token, db):
    owner = make_account("sweep-owner-a", email="owner-a-sweep@example.invalid")
    realm = make_realm(
        owner,
        domain="foreign-sweep.example",
        realm_value="owner-a-host",
        operations=("read", "update", "create", "delete"),
    )
    token, _plain = make_token(realm, name="owner-a-token-marker")

    provider = BackendProvider.query.filter_by(provider_code="netcup").first()
    owner_type = OwnerTypeEnum.query.filter_by(owner_code=OwnerTypeEnum.USER).first()
    visibility = VisibilityEnum.query.filter_by(visibility_code=VisibilityEnum.PUBLIC).first()
    grant_type = GrantTypeEnum.query.filter_by(grant_code=GrantTypeEnum.STANDARD).first()
    assert provider is not None
    assert owner_type is not None
    assert visibility is not None
    assert grant_type is not None

    backend = BackendService(
        provider_id=provider.id,
        service_name="owner-a-sweep-backend",
        display_name="owner-a-backend-marker",
        owner_type_id=owner_type.id,
        owner_id=owner.id,
        config=json.dumps({"credential_marker": "owner-a-private-config-marker"}),
    )
    db.session.add(backend)
    db.session.commit()

    root = ManagedDomainRoot(
        backend_service_id=backend.id,
        root_domain="foreign-sweep.example",
        dns_zone="foreign-sweep.example",
        visibility_id=visibility.id,
        display_name="owner-a-root-marker",
    )
    db.session.add(root)
    db.session.commit()

    grant = DomainRootGrant(
        domain_root_id=root.id,
        account_id=owner.id,
        grant_type_id=grant_type.id,
        granted_by_id=owner.id,
    )
    db.session.add(grant)
    foreign_session = AccountSession(
        account_id=owner.id,
        session_token=secrets.token_urlsafe(32),
        ip_address="198.51.100.31",
        user_agent="authz-sweep",
    )
    db.session.add(foreign_session)
    db.session.commit()

    resources = {
        "account_id": owner.id,
        "realm_id": realm.id,
        "token_id": token.id,
        "record_id": 918273,
        "session_id": foreign_session.id,
        "backend_id": backend.id,
        "root_id": root.id,
        "grant_id": grant.id,
        "token": "not-a-valid-sweep-token",
        "domain": "foreign-sweep.example",
        "hostname": "owner-a.foreign-sweep.example",
        "ip_address": "203.0.113.31",
    }
    markers = (
        owner.username,
        owner.email,
        realm.domain,
        realm.realm_value,
        token.token_name,
        backend.service_name,
        backend.display_name,
        "owner-a-private-config-marker",
        root.display_name,
    )
    return owner, resources, markers


def _assert_no_foreign_markers(response, markers, endpoint):
    body = response.get_data(as_text=True)
    for marker in markers:
        assert marker not in body, f"{endpoint} disclosed foreign marker {marker!r}"


def test_every_id_bearing_account_route_refuses_foreign_owner(
    app, db, make_account, make_realm, make_token,
):
    """Exercise each of the 18 current id-bearing portal rules with valid CSRF."""
    owner, resources, markers = _create_foreign_resources(make_account, make_realm, make_token, db)
    other_user = make_account("sweep-owner-b", password="Portal-Sweep-Pass-9!", email="owner-b-sweep@example.invalid")

    client = app.test_client()
    login_portal(client, other_user)
    other_session = AccountSession.query.filter_by(account_id=other_user.id).one()
    other_session.last_active = datetime.utcnow() + timedelta(days=1)
    db.session.commit()
    csrf_token = mint_csrf(client, "/account/settings")

    discovered = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/account/") and "<int:" in rule.rule
    ]
    actual_endpoint_counts = Counter(rule.endpoint for rule in discovered)
    expected_endpoint_counts = Counter({
        endpoint: 1 for endpoint in set(ID_ROUTE_CASES) | set(ID_ROUTE_EXCEPTIONS)
    })
    assert actual_endpoint_counts == expected_endpoint_counts, (
        f"id-bearing /account rules need one classification per rule: "
        f"discovered={dict(actual_endpoint_counts)}, expected={dict(expected_endpoint_counts)}"
    )

    request_number = 0
    for rule in sorted(discovered, key=lambda item: (item.endpoint, item.rule)):
        endpoint = rule.endpoint
        arguments, expected_methods, expected_status, expected_location = ID_ROUTE_CASES.get(
            endpoint,
            ID_ROUTE_EXCEPTIONS.get(endpoint),
        )
        assert frozenset(rule.arguments) == arguments, f"path arguments changed for {endpoint}"
        assert frozenset(rule_methods(rule)) == expected_methods, f"methods changed for {endpoint}"
        path = build_rule_path(rule, resources)
        for method in rule_methods(rule):
            before = database_snapshot(db)
            response = client.open(
                path,
                method=method,
                data=sweep_form(csrf_token=csrf_token),
                environ_overrides={"REMOTE_ADDR": sweep_ip(request_number)},
            )
            request_number += 1
            assert response.status_code == expected_status, f"{method} {path} returned {response.status_code}"
            assert response.headers.get("Location") == expected_location, f"unexpected redirect from {method} {path}"
            _assert_no_foreign_markers(response, markers, endpoint)
            assert database_snapshot(db) == before, f"{method} {path} mutated the database for a foreign owner"


def test_portal_user_is_refused_by_every_admin_rule(app, db, make_account, make_realm, make_token):
    owner, resources, markers = _create_foreign_resources(make_account, make_realm, make_token, db)
    portal_user = make_account("sweep-portal-admin-probe", password="Portal-Sweep-Pass-9!")
    client = app.test_client()
    login_portal(client, portal_user)
    portal_session = AccountSession.query.filter_by(account_id=portal_user.id).one()
    portal_session.last_active = datetime.utcnow() + timedelta(days=1)
    db.session.commit()
    csrf_token = mint_csrf(client, "/account/settings")

    rules = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/admin/") or rule.rule == "/admin/"
    ]
    assert rules
    request_number = 1000
    for rule in sorted(rules, key=lambda item: (item.endpoint, item.rule)):
        path = build_rule_path(rule, resources)
        for method in rule_methods(rule):
            exception = PORTAL_TO_ADMIN_PUBLIC_EXCEPTIONS.get((rule.endpoint, method))
            before = None if exception is not None else database_snapshot(db)
            data = sweep_form(csrf_token=csrf_token)
            if (rule.endpoint, method) == ("admin.login", "POST"):
                data.update(username=portal_user.username, password="not-an-admin-password")
            response = client.open(
                path,
                method=method,
                data=data,
                environ_overrides={"REMOTE_ADDR": sweep_ip(request_number)},
            )
            request_number += 1

            if exception is not None:
                status, location = exception
            else:
                status, location = 302, "/admin/login"
            assert response.status_code == status, f"{method} {path} returned {response.status_code}"
            assert response.headers.get("Location") == location, f"unexpected admin redirect from {method} {path}"
            _assert_no_foreign_markers(response, markers, rule.endpoint)
            if before is not None:
                assert database_snapshot(db) == before, f"portal user changed admin data through {method} {path}"


def test_anonymous_account_and_admin_rules_redirect_or_match_public_allowlist(
    app, db, make_account, make_realm, make_token,
):
    _owner, resources, markers = _create_foreign_resources(make_account, make_realm, make_token, db)
    rules = [
        rule for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/account/") or rule.rule.startswith("/admin/") or rule.rule in {"/account", "/admin"}
    ]
    assert rules

    expected_public_methods = {
        (endpoint, method)
        for endpoint, methods in PUBLIC_ROUTE_ALLOWLIST.items()
        for method in methods
    }
    discovered_methods = {
        (rule.endpoint, method)
        for rule in rules
        for method in rule_methods(rule)
    }
    assert expected_public_methods <= discovered_methods, (
        f"public allowlist entries have no matching route method: {sorted(expected_public_methods - discovered_methods)}"
    )

    request_number = 2000
    for rule in sorted(rules, key=lambda item: (item.endpoint, item.rule)):
        path = build_rule_path(rule, resources)
        for method in rule_methods(rule):
            client = app.test_client()
            client.environ_base["REMOTE_ADDR"] = sweep_ip(request_number)
            blueprint = rule.endpoint.split(".", 1)[0]
            login_path = "/admin/login" if blueprint == "admin" else "/account/login"
            csrf_token = mint_csrf(client, login_path)
            public_expected = PUBLIC_ROUTE_ALLOWLIST.get(rule.endpoint, {}).get(method)
            data = sweep_form(csrf_token=csrf_token)
            if rule.endpoint == "account.forgot_password" and method == "POST":
                data["email"] = ""
            if rule.endpoint == "admin.login" and method == "POST":
                data["username"] = f"anonymous-admin-probe-{request_number}"
                data["password"] = "not-a-credential"

            before = None if public_expected is not None else database_snapshot(db)
            response = client.open(path, method=method, data=data, environ_overrides={"REMOTE_ADDR": sweep_ip(request_number)})
            request_number += 1

            if public_expected is not None:
                status, location = public_expected
            else:
                status = 302
                location = "/admin/login" if blueprint == "admin" else "/account/login"
            assert response.status_code == status, f"anonymous {method} {path} returned {response.status_code}"
            assert response.headers.get("Location") == location, f"unexpected anonymous redirect from {method} {path}"
            _assert_no_foreign_markers(response, markers, rule.endpoint)
            if before is not None:
                assert database_snapshot(db) == before, f"anonymous {method} {path} mutated protected data"

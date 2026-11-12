"""Dynamic missing/forged-token sweep for every cookie-auth mutation route."""
from __future__ import annotations

from datetime import datetime

from http_helpers import login_admin, login_portal, mint_csrf
from netcup_api_filter.models import Account, AccountSession
from sweep_helpers import build_rule_path, database_snapshot, rule_methods, sweep_form, sweep_ip


# app.py exempts these mutation routes because their credentials are not browser
# cookies: DNS/DDNS require Bearer tokens; Telegram requires its shared-secret header.
# Keep this method-level table exact so a newly-exempt route is reviewed explicitly.
CSRF_EXEMPT_MUTATIONS = {
    ("dns_api.create_record", "POST", "/api/dns/<domain>/records"): "@require_auth Bearer token",
    ("dns_api.update_record", "PUT", "/api/dns/<domain>/records/<int:record_id>"): "@require_auth Bearer token",
    ("dns_api.delete_record", "DELETE", "/api/dns/<domain>/records/<int:record_id>"): "@require_auth Bearer token",
    ("dns_api.ddns_update", "POST", "/api/ddns/<domain>/<hostname>"): "@require_auth Bearer token",
    ("dns_api.ddns_update", "PUT", "/api/ddns/<domain>/<hostname>"): "@require_auth Bearer token",
    ("ddns_protocols.dyndns2_update", "POST", "/api/ddns/dyndns2/update"): "@require_auth Bearer token",
    ("ddns_protocols.noip_update", "POST", "/api/ddns/noip/update"): "@require_auth Bearer token",
    ("telegram.telegram_link_callback", "POST", "/api/telegram/link"): "X-NAF-TELEGRAM-SECRET shared-secret header",
}

COOKIE_BLUEPRINTS = {"account", "admin"}


def _path_values():
    return {
        "account_id": 1,
        "realm_id": 1,
        "token_id": 1,
        "record_id": 1,
        "session_id": 1,
        "backend_id": 1,
        "root_id": 1,
        "grant_id": 1,
        "token": "csrf-sweep-invalid-token",
        "domain": "example.com",
        "hostname": "host.example.com",
        "ip_address": "203.0.113.10",
    }


def test_cookie_mutations_reject_missing_and_forged_csrf_without_mutation(app, db, make_account):
    # create_app enables Flask-WTF by default. Set the documented Flask-WTF config
    # explicitly for this module so an altered shared test config cannot disable it.
    app.config["WTF_CSRF_ENABLED"] = True
    assert app.config["WTF_CSRF_ENABLED"] is True

    mutating = [
        (rule, method)
        for rule in app.url_map.iter_rules()
        for method in rule_methods(rule)
        if method in {"POST", "PUT", "DELETE"}
    ]
    discovered = {(rule.endpoint, method, rule.rule) for rule, method in mutating}

    cookie_routes = {
        (endpoint, method, path)
        for endpoint, method, path in discovered
        if endpoint.split(".", 1)[0] in COOKIE_BLUEPRINTS
    }
    exempt_routes = {
        (endpoint, method, path)
        for endpoint, method, path in discovered
        if (endpoint, method, path) in CSRF_EXEMPT_MUTATIONS
    }
    unclassified = discovered - cookie_routes - exempt_routes
    assert unclassified == set(), f"unclassified mutating routes: {sorted(unclassified)}"
    assert exempt_routes == set(CSRF_EXEMPT_MUTATIONS), (
        f"CSRF exemption table drift: discovered={sorted(exempt_routes)}, "
        f"documented={sorted(CSRF_EXEMPT_MUTATIONS)}"
    )
    assert all(reason for reason in CSRF_EXEMPT_MUTATIONS.values())

    portal = make_account("csrf-portal-user")
    admin = Account.query.filter_by(is_admin=1).first()
    assert admin is not None

    clients = {}
    for role, account, login_func, csrf_path in (
        ("account", portal, login_portal, "/account/settings"),
        ("admin", admin, login_admin, "/admin/settings"),
    ):
        client = app.test_client()
        client.environ_base["REMOTE_ADDR"] = "127.0.0.1"
        login_func(client, account)
        if role == "account":
            account_session = AccountSession.query.filter_by(account_id=account.id).one()
            account_session.last_active = datetime(2100, 1, 1)
            db.session.commit()
        clients[role] = client
        mint_csrf(client, csrf_path)

    request_number = 4000
    for rule, method in sorted(mutating, key=lambda item: (item[0].endpoint, item[0].rule, item[1])):
        blueprint = rule.endpoint.split(".", 1)[0]
        if blueprint not in COOKIE_BLUEPRINTS:
            continue
        path = rule.rule
        path = build_rule_path(rule, _path_values())
        client = clients[blueprint]
        for token_kind in ("missing", "forged"):
            data = sweep_form()
            headers = {}
            if token_kind == "forged":
                if method == "POST":
                    data["csrf_token"] = "forged-csrf-token"
                else:
                    headers["X-CSRFToken"] = "forged-csrf-token"

            before = database_snapshot(db)
            response = client.open(
                path,
                method=method,
                data=data,
                headers=headers,
                environ_overrides={"REMOTE_ADDR": sweep_ip(request_number)},
            )
            request_number += 1
            assert response.status_code == 400, f"{token_kind} CSRF passed for {method} {path}"
            assert database_snapshot(db) == before, f"{token_kind} CSRF mutated data for {method} {path}"

    assert cookie_routes

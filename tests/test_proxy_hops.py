"""Hermetic coverage for proxy trust, canonical origins, and host-only cookies."""
from __future__ import annotations

import html
import importlib
from pathlib import Path
import re
import shutil

import pytest
from flask import jsonify, render_template_string, request, url_for
from werkzeug.datastructures import Headers

from netcup_api_filter import config_defaults
from netcup_api_filter.app import create_app
from netcup_api_filter.config_defaults import _parse_env_file
from netcup_api_filter.database import db

REPO = Path(__file__).resolve().parents[1]
APP_MODULE = importlib.import_module("netcup_api_filter.app")
PROXY_ADDR = "192.0.2.10"
FORGED_ADDR = "203.0.113.99"
RESOLVED_ADDR = "198.51.100.17"

XFF_EDGE_CASES = [
    # label, header value, N=1 remote_addr, N=2 remote_addr, N=1 parsed IP, N=2 parsed IP
    ("empty header", "", PROXY_ADDR, PROXY_ADDR, PROXY_ADDR, PROXY_ADDR),
    (
        "empty entries",
        ",, 198.51.100.16,, 198.51.100.17,,",
        "198.51.100.17",
        "198.51.100.16",
        "198.51.100.17",
        "198.51.100.16",
    ),
    (
        "duplicate entries",
        "198.51.100.17, 198.51.100.17",
        "198.51.100.17",
        "198.51.100.17",
        "198.51.100.17",
        "198.51.100.17",
    ),
    (
        "quoted entries",
        '"198.51.100.16", "198.51.100.17"',
        "198.51.100.17",
        "198.51.100.16",
        "198.51.100.17",
        "198.51.100.16",
    ),
    (
        "malformed selected entry",
        "198.51.100.16, not-an-ip, 198.51.100.18",
        "198.51.100.18",
        "not-an-ip",
        "198.51.100.18",
        None,
    ),
    (
        "malformed rightmost entry",
        "198.51.100.16, not-an-ip",
        "not-an-ip",
        "198.51.100.16",
        None,
        "198.51.100.16",
    ),
    (
        "IPv6 entries",
        "2001:db8::1, 2001:db8::2",
        "2001:db8::2",
        "2001:db8::1",
        "2001:db8::2",
        "2001:db8::1",
    ),
    (
        "port-suffixed IPv4",
        "198.51.100.17:443",
        "198.51.100.17:443",
        PROXY_ADDR,
        "198.51.100.17",
        PROXY_ADDR,
    ),
    (
        "comma spacing",
        " 198.51.100.16 \t,   198.51.100.17  ",
        "198.51.100.17",
        "198.51.100.16",
        "198.51.100.17",
        "198.51.100.16",
    ),
]


@pytest.fixture(autouse=True)
def _repository_defaults_only():
    """Keep proxy-hop defaults independent of untracked checkout overlays."""
    cached_load_defaults = config_defaults.load_defaults
    cached_load_defaults.cache_clear()
    catalog = _parse_env_file(REPO / ".env.defaults")
    config_defaults.load_defaults = lambda: catalog
    try:
        yield cached_load_defaults
    finally:
        config_defaults.load_defaults = cached_load_defaults
        cached_load_defaults.cache_clear()


@pytest.fixture
def app(request, monkeypatch, tmp_path):
    """Use the real factory with a per-test trusted-hop and origin configuration."""
    options = getattr(request, "param", {}) or {}
    monkeypatch.setenv("SECRET_KEY", "test_secret_key_for_testing_only")
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("NETCUP_FILTER_APP_ROOT", raising=False)
    monkeypatch.setenv("FLASK_ENV", options.get("flask_env", "local_test"))
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", str(options.get("trusted_proxy_hops", "0")))
    monkeypatch.setenv("PUBLIC_BASE_URL", options.get("public_base_url", ""))
    if "public_fqdn" in options:
        monkeypatch.setenv("PUBLIC_FQDN", options["public_fqdn"])
    else:
        monkeypatch.delenv("PUBLIC_FQDN", raising=False)
    if "cookie_domain" in options:
        monkeypatch.setenv("FLASK_SESSION_COOKIE_DOMAIN", options["cookie_domain"])
    else:
        monkeypatch.delenv("FLASK_SESSION_COOKIE_DOMAIN", raising=False)
    if "cookie_secure" in options:
        monkeypatch.setenv("FLASK_SESSION_COOKIE_SECURE", options["cookie_secure"])
    else:
        monkeypatch.delenv("FLASK_SESSION_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("TOKEN_IP_BINDING_ENABLED", "true")

    application = create_app()
    application.config["TESTING"] = True
    application.config["WTF_CSRF_ENABLED"] = False
    with application.app_context():
        yield application
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


def _probe_route(app):
    @app.get("/__proxy_probe")
    def proxy_probe():
        return jsonify(
            remote_addr=request.remote_addr,
            scheme=request.scheme,
            host=request.host,
            external_url=url_for("account.login", _external=True),
        )


def _headers(**extra):
    return {
        "Host": "origin.example.invalid",
        "X-Forwarded-For": f"{FORGED_ADDR}, {RESOLVED_ADDR}",
        "X-Forwarded-Proto": "http, https",
        "X-Forwarded-Host": "forged.example.invalid, forwarded.example.invalid",
        **extra,
    }


def _environ():
    return {"REMOTE_ADDR": PROXY_ADDR, "wsgi.url_scheme": "http"}


@pytest.mark.parametrize("app", [{"trusted_proxy_hops": "0"}], indirect=True)
def test_zero_hops_ignores_forged_forwarded_for_proto_and_host(caplog, app, client, monkeypatch):
    """Old unconditional ProxyFix fails all three resolved-environ assertions."""
    _probe_route(app)
    monkeypatch.setattr(APP_MODULE, "_forwarded_header_warning_logged", False)

    with caplog.at_level("WARNING", logger="netcup_api_filter.app"):
        first = client.get("/__proxy_probe", headers=_headers(), environ_overrides=_environ())
        second = client.get("/__proxy_probe", headers=_headers(), environ_overrides=_environ())

    assert first.status_code == second.status_code == 200
    data = first.get_json()
    assert data["remote_addr"] == PROXY_ADDR
    assert data["scheme"] == "http"
    assert data["host"] == "origin.example.invalid"
    assert data["external_url"] == "http://origin.example.invalid/account/login"
    ignored_warnings = [r for r in caplog.records if "TRUSTED_PROXY_HOPS" in r.getMessage()]
    assert len(ignored_warnings) == 1
    assert "ignored" in ignored_warnings[0].getMessage().lower()
    public_origin_warnings = [
        r for r in caplog.get_records("setup") if "PUBLIC_BASE_URL" in r.getMessage()
    ]
    assert len(public_origin_warnings) == 1
    assert "Host" in public_origin_warnings[0].getMessage()


@pytest.mark.parametrize("app", [{"trusted_proxy_hops": "1"}], indirect=True)
def test_one_hop_uses_rightmost_for_and_proto_but_never_forwarded_host(app, client):
    """Old code uses the XFH value; the amended policy always leaves Host alone."""
    _probe_route(app)
    response = client.get("/__proxy_probe", headers=_headers(), environ_overrides=_environ())

    assert response.status_code == 200
    data = response.get_json()
    assert data["remote_addr"] == RESOLVED_ADDR
    assert data["scheme"] == "https"
    assert data["host"] == "origin.example.invalid"
    assert data["external_url"] == "https://origin.example.invalid/account/login"


@pytest.mark.parametrize("app", [{"trusted_proxy_hops": "2"}], indirect=True)
def test_two_hops_selects_the_second_from_last_forwarded_for_entry(app, client):
    _probe_route(app)
    response = client.get(
        "/__proxy_probe",
        headers=_headers(**{"X-Forwarded-For": f"{FORGED_ADDR}, {RESOLVED_ADDR}, 192.0.2.22"}),
        environ_overrides=_environ(),
    )

    assert response.status_code == 200
    assert response.get_json()["remote_addr"] == RESOLVED_ADDR


@pytest.mark.parametrize(
    "app",
    [
        {"trusted_proxy_hops": "0"},
        {"trusted_proxy_hops": "1"},
        {"trusted_proxy_hops": "2"},
    ],
    indirect=True,
)
def test_xff_edge_matrix_resolves_rightmost_hops_and_fails_closed(app, client):
    from netcup_api_filter.utils import parse_client_address

    hops = app.config["TRUSTED_PROXY_HOPS"]

    @app.get("/__xff_edge_probe")
    def xff_edge_probe():
        parsed = parse_client_address(request.remote_addr)
        return jsonify(
            remote_addr=request.remote_addr,
            parsed_address=str(parsed) if parsed is not None else None,
            raw_xff=request.environ.get("HTTP_X_FORWARDED_FOR"),
        )

    for label, raw_xff, hop_one, hop_two, parsed_one, parsed_two in XFF_EDGE_CASES:
        if hops == 0:
            expected_remote = expected_parsed = PROXY_ADDR
        elif hops == 1:
            expected_remote, expected_parsed = hop_one, parsed_one
        else:
            expected_remote, expected_parsed = hop_two, parsed_two
        response = client.get(
            "/__xff_edge_probe",
            headers={"Host": "origin.example.invalid", "X-Forwarded-For": raw_xff},
            environ_overrides=_environ(),
        )

        assert response.status_code == 200, label
        data = response.get_json()
        assert data["remote_addr"] == expected_remote, label
        assert data["parsed_address"] == expected_parsed, label

    multi_line_headers = Headers([
        ("Host", "origin.example.invalid"),
        ("X-Forwarded-For", "198.51.100.16"),
        ("X-Forwarded-For", "198.51.100.17"),
    ])
    response = client.get(
        "/__xff_edge_probe",
        headers=multi_line_headers,
        environ_overrides=_environ(),
    )
    data = response.get_json()
    if hops == 0:
        expected_remote = PROXY_ADDR
    elif hops == 1:
        expected_remote = "198.51.100.17"
    else:
        expected_remote = "198.51.100.16"
    expected_parsed = expected_remote
    assert data["raw_xff"] == "198.51.100.16, 198.51.100.17"
    assert data["remote_addr"] == expected_remote
    assert data["parsed_address"] == expected_parsed


@pytest.mark.parametrize(
    "value,expected",
    [
        ("198.51.100.17:443", "198.51.100.17"),
        ("[2001:db8::17]:443", "2001:db8::17"),
        ("2001:db8::17", "2001:db8::17"),
        ("198.51.100.17:0", None),
        ("198.51.100.17:bad", None),
        ("198.51.100.17:443:extra", None),
        ("[2001:db8::17]:bad", None),
        ("not-an-ip", None),
    ],
)
def test_client_address_parser_normalizes_only_unambiguous_addresses(value, expected):
    from netcup_api_filter.utils import parse_client_address

    parsed = parse_client_address(value)
    actual = str(parsed) if parsed is not None else None
    assert actual == expected


@pytest.mark.parametrize("value", ["-1", "not-an-integer", ""])
def test_invalid_trusted_proxy_hops_fails_startup_with_setting_name(app, monkeypatch, tmp_path, value):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", value)
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "invalid-hops.db"))

    with pytest.raises(RuntimeError, match="TRUSTED_PROXY_HOPS"):
        create_app()


@pytest.mark.parametrize("value", [
    "ftp://public.example.invalid",
    "//public.example.invalid",
    "https://user:password@public.example.invalid",
    "https://public.example.invalid/path",
    "https://public.example.invalid?query=yes",
    "https://public.example.invalid#fragment",
    "https://public.example.invalid:70000",
    "https://public.example.invalid\n",
    "https://",
])
def test_invalid_public_base_url_fails_startup_with_setting_name(app, monkeypatch, tmp_path, value):
    monkeypatch.setenv("PUBLIC_BASE_URL", value)
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "invalid-public-url.db"))

    with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL"):
        create_app()


@pytest.mark.parametrize("app", [{
    "trusted_proxy_hops": "1",
    "public_base_url": "https://canonical.example.invalid:8443",
}], indirect=True)
def test_public_base_url_is_the_only_external_url_origin(app, client):
    from netcup_api_filter.api.admin import _redirect_back_or

    @app.get("/__external_probe")
    def external_probe():
        return jsonify(
            external_url=url_for("account.login", _external=True),
            template_origin=render_template_string("{{ public_base_url }}"),
        )

    @app.get("/__referrer_redirect")
    def referrer_redirect():
        return _redirect_back_or("account.login")

    response = client.get(
        "/__external_probe",
        headers=_headers(**{"Host": "attacker.example.invalid"}),
        environ_overrides=_environ(),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "external_url": "https://canonical.example.invalid:8443/account/login",
        "template_origin": "https://canonical.example.invalid:8443/",
    }
    referrer_response = client.get(
        "/__referrer_redirect",
        headers={"Referer": "https://attacker.example.invalid/admin/accounts?tab=pending"},
    )
    assert referrer_response.headers["Location"] == (
        "https://canonical.example.invalid:8443/admin/accounts?tab=pending"
    )

    with app.app_context():
        assert app.url_for("account.login", _external=True) == (
            "https://canonical.example.invalid:8443/account/login"
        )

        from netcup_api_filter.database import set_setting
        from netcup_api_filter.notification_service import _get_base_url

        set_setting("general", {"base_url": "https://legacy.example.invalid"})
        assert _get_base_url() == "https://canonical.example.invalid:8443"


@pytest.mark.parametrize("app", [{
    "public_base_url": "https://canonical.example.invalid",
}], indirect=True)
def test_password_reset_manual_url_fallback_uses_public_base_url(app):
    from netcup_api_filter.password_reset import _external_base_url_fallback

    assert _external_base_url_fallback() == "https://canonical.example.invalid"


def test_proxy_hops_repository_default_is_zero_and_public_origin_default_is_empty():
    defaults = _parse_env_file(REPO / ".env.defaults")
    assert defaults["TRUSTED_PROXY_HOPS"] == "0"
    assert defaults["PUBLIC_BASE_URL"] == ""


@pytest.mark.parametrize("app", [{
    "public_fqdn": "parent.example.invalid",
    "flask_env": "production",
}], indirect=True)
def test_default_session_cookie_domain_is_host_only_even_with_public_fqdn(app, client):
    @app.get("/__session_cookie")
    def issue_cookie():
        from flask import session
        session["cookie_probe"] = "set"
        return "ok"

    response = client.get(
        "/__session_cookie",
        headers={
            "Host": "origin.example.invalid",
            "X-Forwarded-Proto": "https",
        },
        environ_overrides={"wsgi.url_scheme": "http"},
    )

    assert app.config.get("SESSION_COOKIE_DOMAIN") is None
    set_cookie = response.headers["Set-Cookie"]
    assert "Domain=" not in set_cookie
    assert "; Secure" in set_cookie


def test_default_config_ignores_local_env_overlay(
    tmp_path, monkeypatch, _repository_defaults_only
):
    """Contrast poisoned real-loader behaviour with the isolated proxy path."""
    real_load_defaults = _repository_defaults_only
    isolated_load_defaults = config_defaults.load_defaults
    original_module_file = config_defaults.__file__
    poisoned_cwd = tmp_path / "cwd"
    poisoned_repo = tmp_path / "repo"
    loader_source = poisoned_repo / "src" / "netcup_api_filter" / "config_defaults.py"
    poisoned_env = (
        "FLASK_SESSION_COOKIE_DOMAIN=auto\n"
        "TRUSTED_PROXY_HOPS=7\n"
        "PUBLIC_BASE_URL=http://evil.example\n"
    )

    for root in (poisoned_cwd, poisoned_repo):
        root.mkdir(parents=True)
        shutil.copyfile(REPO / ".env.defaults", root / ".env.defaults")
        (root / ".env").write_text(poisoned_env, encoding="utf-8")
    loader_source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        REPO / "src" / "netcup_api_filter" / "config_defaults.py",
        loader_source,
    )

    monkeypatch.chdir(poisoned_cwd)
    monkeypatch.delenv("FLASK_SESSION_COOKIE_DOMAIN", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_FQDN", raising=False)
    monkeypatch.setenv("SECRET_KEY", "test_secret_key_for_testing_only")
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "overlay-defaults.db"))
    monkeypatch.delenv("NETCUP_FILTER_APP_ROOT", raising=False)

    # CONTROL: the real loader reads the poisoned cwd/repo overlays. Explicit
    # assignment avoids overlapping monkeypatch undo order with the isolation
    # fixture and makes the pair leak-free even when an assertion fails.
    real_load_defaults.cache_clear()
    config_defaults.load_defaults = real_load_defaults
    config_defaults.__file__ = str(loader_source)
    try:
        assert config_defaults.get_default("FLASK_SESSION_COOKIE_DOMAIN") == "auto"
        with pytest.raises(
            RuntimeError,
            match="FLASK_SESSION_COOKIE_DOMAIN must be empty for host-only cookies",
        ):
            create_app()
    finally:
        config_defaults.__file__ = original_module_file
        config_defaults.load_defaults = isolated_load_defaults
        real_load_defaults.cache_clear()

    # ISOLATED: the same poisoned cwd remains, but this path reads only the catalog.
    real_load_defaults.cache_clear()
    application = None
    try:
        application = create_app()
        assert application.config["TRUSTED_PROXY_HOPS"] == 0
        assert application.config["PUBLIC_BASE_URL"] == ""
        assert application.config.get("SESSION_COOKIE_DOMAIN") is None
    finally:
        real_load_defaults.cache_clear()
        if application is not None:
            with application.app_context():
                db.session.remove()
                db.drop_all()
                db.engine.dispose()


@pytest.mark.parametrize("app", [{"cookie_domain": ".example.invalid"}], indirect=True)
def test_explicit_session_cookie_domain_is_honored_and_validated(
    app, monkeypatch, tmp_path
):
    assert app.config["SESSION_COOKIE_DOMAIN"] == ".example.invalid"
    monkeypatch.setenv("FLASK_SESSION_COOKIE_DOMAIN", "auto")
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "invalid-explicit-domain.db"))
    with pytest.raises(RuntimeError, match="FLASK_SESSION_COOKIE_DOMAIN"):
        create_app()


@pytest.mark.parametrize("value", [
    "auto",
    "AUTO",
    "https://example.invalid",
    "example.invalid/path",
    ".example..invalid",
    " example.invalid",
    "example.invalid:443",
])
def test_invalid_explicit_session_cookie_domain_fails_startup(app, monkeypatch, tmp_path, value):
    monkeypatch.setenv("FLASK_SESSION_COOKIE_DOMAIN", value)
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "invalid-cookie-domain.db"))

    with pytest.raises(RuntimeError, match="FLASK_SESSION_COOKIE_DOMAIN"):
        create_app()


def _client_address_request(client, path, *, method="get", headers=None, **kwargs):
    call = getattr(client, method)
    return call(
        path,
        headers=_headers(**(headers or {})),
        environ_overrides=_environ(),
        **kwargs,
    )


def _authenticate(client, account, db):
    import secrets

    from netcup_api_filter.account_auth import SESSION_KEY_SESSION_TOKEN, SESSION_KEY_USER_ID
    from netcup_api_filter.models import AccountSession

    token = secrets.token_urlsafe(24)
    db.session.add(AccountSession(
        account_id=account.id,
        session_token=token,
        ip_address=PROXY_ADDR,
        user_agent="proxy-hop-test",
    ))
    db.session.commit()
    with client.session_transaction(base_url="http://origin.example.invalid") as session:
        session[SESSION_KEY_USER_ID] = account.id
        session[SESSION_KEY_SESSION_TOKEN] = token


def _preformatted_snippets(markup):
    blocks = re.findall(r"<pre\b[^>]*>(.*?)</pre\s*>", markup, re.IGNORECASE | re.DOTALL)
    return [html.unescape(re.sub(r"<[^>]+>", "", block)) for block in blocks]


@pytest.mark.parametrize("app", [{
    "trusted_proxy_hops": "0",
    "public_base_url": "https://canonical.example.invalid",
}], indirect=True)
def test_account_copyable_snippets_use_public_origin_not_request_host(
    app, db, make_account
):
    from flask import render_template

    account = make_account("proxy-copy-examples")
    request_host = "unrelated-request-host.example.invalid"
    origin = "https://canonical.example.invalid"
    snippets = []

    templates = (
        ("account/dashboard.html", {"account": account, "realm_data": []}),
        ("account/tokens.html", {"account": account, "tokens": []}),
        ("account/api_docs.html", {"account": account}),
    )
    for template, context in templates:
        with app.test_request_context(
            "/account/",
            base_url="http://origin.example.invalid",
            headers={"Host": request_host},
            environ_overrides=_environ(),
        ):
            assert request.host == request_host
            markup = render_template(template, **context)
        snippets.extend(_preformatted_snippets(markup))

    assert snippets
    assert any(f'{origin}/api/dns/records' in snippet for snippet in snippets)
    assert all(request_host not in snippet for snippet in snippets)
    assert all("example.com" not in snippet.lower() for snippet in snippets)


@pytest.mark.parametrize("app", [{"trusted_proxy_hops": "1"}], indirect=True)
def test_forgot_password_binds_reset_token_to_middleware_address(
    app, client, db, make_account
):
    from netcup_api_filter.models import ResetToken

    account = make_account("proxy-reset", email="proxy-reset@example.invalid")
    response = _client_address_request(
        client,
        "/account/forgot-password",
        method="post",
        data={"email": account.email},
    )

    assert response.status_code == 302
    row = ResetToken.query.filter_by(target_id=account.id, token_type="reset").one()
    assert row.source_ip == RESOLVED_ADDR
    assert row.source_ip != FORGED_ADDR


@pytest.mark.parametrize("app", [{"trusted_proxy_hops": "1"}], indirect=True)
def test_email_verification_link_accepts_the_ip_bound_to_middleware_address(
    app, client, db
):
    from datetime import datetime, timedelta

    from netcup_api_filter.models import RegistrationRequest
    from netcup_api_filter.password_reset import generate_reset_token

    registration = RegistrationRequest(
        username="proxy-verify",
        email="proxy-verify@example.invalid",
        password_hash="unused-test-hash",
        verification_code="123456",
        verification_expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    db.session.add(registration)
    db.session.commit()
    raw_token, _ = generate_reset_token(
        registration, source_ip=RESOLVED_ADDR, token_type="verify"
    )

    response = _client_address_request(
        client, f"/account/register/verify/{raw_token}"
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/account/register/realms")


@pytest.mark.parametrize("path,action", [
    ("/account/settings", "change_password"),
    ("/account/change-password", None),
])
@pytest.mark.parametrize("app", [{"trusted_proxy_hops": "1"}], indirect=True)
def test_password_change_routes_pass_middleware_address_to_notification(
    app, client, db, make_account, monkeypatch, path, action
):
    from netcup_api_filter.api import account as account_routes

    account = make_account("proxy-password", password="Known-Strong-Password-2024!abc")
    _authenticate(client, account, db)
    observed = []

    def capture_change_password(account_arg, current_password, new_password, source_ip=None):
        observed.append(source_ip)
        return False, "captured address"

    monkeypatch.setattr(account_routes, "change_password", capture_change_password)
    form = {
        "current_password": "Known-Strong-Password-2024!abc",
        "new_password": "Another-Strong-Password-2024!xyz",
        "confirm_password": "Another-Strong-Password-2024!xyz",
    }
    if action:
        form["action"] = action

    response = _client_address_request(client, path, method="post", data=form)

    assert response.status_code == 200
    assert observed == [RESOLVED_ADDR]
    assert FORGED_ADDR not in observed


@pytest.mark.parametrize("app", [{"trusted_proxy_hops": "1"}], indirect=True)
def test_realm_detail_shows_middleware_address_for_ddns(app, client, db, make_account, make_realm):
    account = make_account("proxy-realm-view")
    realm = make_realm(account, domain="example.invalid", realm_value="vpn")
    _authenticate(client, account, db)

    response = _client_address_request(client, f"/account/realms/{realm.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert f'id="currentIp">{RESOLVED_ADDR}</code>' in body
    assert FORGED_ADDR not in body


@pytest.mark.parametrize(
    "resolved_header,expected_ip",
    [
        (RESOLVED_ADDR, RESOLVED_ADDR),
        ("198.51.100.17:443", RESOLVED_ADDR),
        ("not-an-ip", None),
    ],
)
@pytest.mark.parametrize("app", [{"trusted_proxy_hops": "1"}], indirect=True)
def test_account_ddns_uses_validated_middleware_address(
    app, client, db, make_account, make_realm, monkeypatch, resolved_header, expected_ip
):
    from netcup_api_filter.database import set_setting
    from netcup_api_filter.models import ActivityLog
    from netcup_api_filter import netcup_client

    account = make_account("proxy-ddns-ui")
    realm = make_realm(account, domain="example.invalid", realm_value="vpn")
    _authenticate(client, account, db)
    set_setting("netcup_config", {
        "customer_id": "customer",
        "api_key": "key",
        "api_password": "password",
        "timeout": 5,
    })

    updated_records = []

    class FakeNetcupClient:
        def __init__(self, **kwargs):
            pass

        def info_dns_records(self, domain):
            return []

        def update_dns_records(self, domain, records):
            updated_records.extend(records)
            return {"status": "success"}

    monkeypatch.setattr(netcup_client, "NetcupClient", FakeNetcupClient)
    response = _client_address_request(
        client,
        f"/account/realms/{realm.id}/ddns",
        method="post",
        headers={"X-Forwarded-For": f"{FORGED_ADDR}, {resolved_header}"},
    )

    assert response.status_code == 302
    if expected_ip is None:
        assert ActivityLog.query.filter_by(account_id=account.id, action="ddns_ui").first() is None
        assert updated_records == []
        return

    row = ActivityLog.query.filter_by(account_id=account.id, action="ddns_ui").one()
    assert row.source_ip == expected_ip
    assert row.source_ip != FORGED_ADDR
    assert updated_records == [{
        "hostname": realm.realm_value,
        "type": "A",
        "destination": expected_ip,
    }]


@pytest.mark.parametrize("path,action", [
    ("/account/security/2fa/disable", "2fa_disabled"),
    ("/account/telegram/unlink", "telegram_unlinked"),
])
@pytest.mark.parametrize("app", [{"trusted_proxy_hops": "1"}], indirect=True)
def test_sensitive_account_activity_records_middleware_address(
    app, client, db, make_account, path, action
):
    from netcup_api_filter.models import ActivityLog

    account = make_account(
        "proxy-sensitive",
        password="Known-Strong-Password-2024!abc",
        telegram_enabled=1,
        telegram_chat_id="test-chat-id",
    )
    _authenticate(client, account, db)
    form = {"password": "Known-Strong-Password-2024!abc"} if action == "2fa_disabled" else {}

    response = _client_address_request(client, path, method="post", data=form)

    assert response.status_code == 302
    row = ActivityLog.query.filter_by(account_id=account.id, action=action).one()
    assert row.source_ip == RESOLVED_ADDR
    assert row.source_ip != FORGED_ADDR


@pytest.mark.parametrize(
    "resolved_header,expected_ip",
    [
        (RESOLVED_ADDR, RESOLVED_ADDR),
        ("198.51.100.17:443", RESOLVED_ADDR),
        ("not-an-ip", None),
    ],
)
@pytest.mark.parametrize("app", [{"trusted_proxy_hops": "1"}], indirect=True)
def test_filter_proxy_auto_ddns_uses_middleware_address(
    app, client, make_account, make_realm, make_token, monkeypatch, resolved_header, expected_ip
):
    from netcup_api_filter import filter_proxy
    from flask import g, request

    app.register_blueprint(filter_proxy.filter_proxy_bp, url_prefix="/__legacy")
    account = make_account("proxy-filter-ddns")
    realm = make_realm(
        account,
        domain="example.com",
        realm_type="host",
        realm_value="vpn",
        operations=("update",),
        record_types=("A",),
    )
    # The legacy filter_proxy route uses an attribute from its former realm model.
    realm.record_types_list = realm.get_allowed_record_types()
    _token_row, plain_token = make_token(
        realm, operations=("update",), record_types=("A",)
    )

    @app.before_request
    def provide_legacy_filter_proxy_context():
        # The legacy endpoint still expects aliases not populated by require_auth.
        # Supply them in this test so the real route reaches its client-IP use.
        if request.endpoint == "filter_proxy.ddns_update":
            g.token = _token_row
            g.realm = realm

    # This legacy endpoint passes (token, realm, operation) to the newer
    # check_permission(auth, operation, domain) helper. Stub that unrelated
    # pre-existing mismatch so the request exercises the address selection.
    monkeypatch.setattr(filter_proxy, "check_permission", lambda token, scope, operation: True)
    # Its legacy audit call also uses a keyword the current helper rejects; the
    # outbound DNS payload below is the observable client-address use.
    monkeypatch.setattr(filter_proxy, "log_activity", lambda *args, **kwargs: None)

    updates = []

    def fake_netcup(action, params):
        if action == "infoDnsRecords":
            return {"dnsrecords": []}
        if action == "updateDnsRecords":
            updates.append(params["dnsrecordset"]["dnsrecords"])
            return {"status": "success"}
        raise AssertionError(f"unexpected Netcup action: {action}")

    monkeypatch.setattr(filter_proxy, "call_netcup_api", fake_netcup)
    response = _client_address_request(
        client,
        "/__legacy/api/ddns/example.com/vpn?auto=true",
        headers={
            "Authorization": f"Bearer {plain_token}",
            "X-Forwarded-For": f"{FORGED_ADDR}, {resolved_header}",
        },
    )

    if expected_ip is None:
        assert response.status_code == 400
        assert updates == []
        return

    assert response.status_code == 200
    assert updates[0][0]["destination"] == expected_ip
    assert updates[0][0]["destination"] != FORGED_ADDR
    assert updates[0][0]["type"] == "A"


@pytest.mark.parametrize("app", [{"trusted_proxy_hops": "1"}], indirect=True)
def test_filter_proxy_myip_returns_middleware_address(app, client):
    from netcup_api_filter.filter_proxy import filter_proxy_bp

    app.register_blueprint(filter_proxy_bp, url_prefix="/__legacy")
    response = _client_address_request(client, "/__legacy/api/myip")

    assert response.status_code == 200
    assert response.get_json() == {"ip": RESOLVED_ADDR}

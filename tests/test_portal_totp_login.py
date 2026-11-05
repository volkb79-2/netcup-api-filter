"""Account-portal login with TOTP as the chosen 2FA method (real HTTP, real CSRF).

Regression: GET /account/login/2fa?method=totp never recorded the method in the session
(send_2fa_code was skipped for TOTP), so verify_2fa checked the TOTP code as an EMAIL code
and a portal TOTP login could never succeed.
"""
from __future__ import annotations

import secrets

import pyotp

from netcup_api_filter.account_auth import SESSION_KEY_2FA_METHOD
from tests.http_helpers import mint_csrf


def _account_with_totp(make_account):
    password = secrets.token_urlsafe(18) + "Aa1@"
    secret = pyotp.random_base32()
    account = make_account("totpportal1", password=password, email_2fa_enabled=1,
                           totp_enabled=1, totp_secret=secret)
    return account, password, secret


def _step1(client, account, password):
    csrf = mint_csrf(client, "/account/login")
    response = client.post("/account/login", data={
        "username": account.username, "password": password, "csrf_token": csrf})
    assert response.status_code == 302 and "/account/login/2fa" in response.headers["Location"]


def test_choosing_totp_records_the_method_and_a_valid_code_logs_in(client, make_account):
    account, password, secret = _account_with_totp(make_account)
    _step1(client, account, password)

    page = client.get("/account/login/2fa?method=totp")
    assert page.status_code == 200
    with client.session_transaction() as sess:
        assert sess[SESSION_KEY_2FA_METHOD] == "totp"

    csrf = mint_csrf(client, "/account/login/2fa?method=totp")
    response = client.post("/account/login/2fa", data={"code": pyotp.TOTP(secret).now(), "csrf_token": csrf})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/account/dashboard")


def test_wrong_totp_code_does_not_log_in(client, make_account):
    account, password, secret = _account_with_totp(make_account)
    _step1(client, account, password)
    correct = pyotp.TOTP(secret).now()
    wrong = "111111" if correct != "111111" else "222222"

    csrf = mint_csrf(client, "/account/login/2fa?method=totp")
    response = client.post("/account/login/2fa", data={"code": wrong, "csrf_token": csrf})
    assert response.status_code == 200  # re-rendered with an error, no redirect to the dashboard
    with client.session_transaction() as sess:
        assert sess[SESSION_KEY_2FA_METHOD] == "totp"


def test_unoffered_method_is_not_recorded(client, make_account):
    password = secrets.token_urlsafe(18) + "Aa1@"
    account = make_account("emailonly01", password=password, email_2fa_enabled=1, totp_enabled=0)
    _step1(client, account, password)
    client.get("/account/login/2fa?method=totp")
    with client.session_transaction() as sess:
        assert sess.get(SESSION_KEY_2FA_METHOD) != "totp"

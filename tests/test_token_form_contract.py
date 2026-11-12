"""Regression tests for the portal's visible create-token form contract."""
from __future__ import annotations

from datetime import datetime, timedelta
import re

import pytest

from netcup_api_filter.api.account import TOKEN_EXPIRY_DAYS
from netcup_api_filter.models import APIToken
from netcup_api_filter.token_auth import authenticate_token, check_permission
from tests.form_contract_helpers import csrf_field, field_by_id, parse_forms
from tests.http_helpers import login_portal


FIELD_IDS = ("token_name", "expires", "ip_ranges", "description")


def _token_form(client, realm_id):
    response = client.get(f"/account/realms/{realm_id}/tokens/new")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    forms = [form for form in parse_forms(html) if form.method == "post"]
    assert len(forms) == 1, f"expected one token POST form, got {forms!r}"
    form = forms[0]
    assert form.action and form.action.endswith("/tokens/new")
    assert form.names == frozenset(FIELD_IDS)
    assert "rate_limit_per_minute" not in html
    return form, csrf_field(html)


def _create_token(
    client,
    realm_id,
    *,
    name: str,
    ip_ranges: str = "",
    expires: str = "never",
    description: str = "",
):
    form, (csrf_name, csrf_value) = _token_form(client, realm_id)
    data = {
        csrf_name: csrf_value,
        field_by_id(form, "token_name").name: name,
        field_by_id(form, "ip_ranges").name: ip_ranges,
        field_by_id(form, "expires").name: expires,
        field_by_id(form, "description").name: description,
    }
    response = client.post(form.action, data=data)
    body = response.get_data(as_text=True)
    plaintext = None
    if "Token Generated" in body:
        match = re.search(
            r'id="tokenValue"[^>]*value="([^"]+)"',
            body,
        )
        assert match, "token success page did not expose #tokenValue"
        plaintext = match.group(1)
    return response, plaintext


@pytest.fixture
def token_owner(make_account):
    return make_account("token-form-owner", password="OldPassword-2024:ABC#xyz")


@pytest.fixture
def token_realm(token_owner, make_realm):
    return make_realm(
        token_owner,
        domain="example.com",
        realm_type="subdomain",
        realm_value="",
        operations=("read", "update"),
        record_types=("A", "AAAA"),
    )


def test_token_form_uses_visible_field_names_and_stores_comma_allow_list(
    app, client, db, token_owner, token_realm
):
    login_portal(client, token_owner)
    response, token_plain = _create_token(
        client,
        token_realm.id,
        name="comma-ranges",
        ip_ranges="192.0.2.10, 203.0.113.0/24",
        description="Comma-separated allow-list",
    )

    assert response.status_code == 200
    assert "Token Generated" in response.get_data(as_text=True)
    token = db.session.query(APIToken).filter_by(token_name="comma-ranges").one()
    assert token.get_allowed_ip_ranges() == ["192.0.2.10", "203.0.113.0/24"]
    assert token.token_description == "Comma-separated allow-list"
    assert token.expires_at is None

    assert token_plain is not None
    auth = authenticate_token(token_plain)
    assert auth.success is True
    denied = check_permission(
        auth, "read", "example.com", client_ip="198.51.100.7"
    )
    assert denied.granted is False
    assert denied.error_code == "ip_denied"
    # Positive oracle: an address inside the stored CIDR is admitted, so the
    # denial above is the allow-list at work and not a blanket refusal.
    allowed = check_permission(
        auth, "read", "example.com", client_ip="203.0.113.5"
    )
    assert allowed.granted is True


@pytest.mark.parametrize(
    ("raw_ranges", "expected"),
    [
        ("192.0.2.10\n198.51.100.4", ["192.0.2.10", "198.51.100.4"]),
        ("203.0.113.0/24", ["203.0.113.0/24"]),
        ("2001:db8::/32\n2001:db8:1::1", ["2001:db8::/32", "2001:db8:1::1"]),
    ],
)
def test_token_form_accepts_newlines_cidr_and_ipv6(
    app, client, db, token_owner, token_realm, raw_ranges, expected
):
    login_portal(client, token_owner)
    name = f"ranges-{len(raw_ranges)}-{expected[0]}"
    response, _token_plain = _create_token(
        client,
        token_realm.id,
        name=name,
        ip_ranges=raw_ranges,
    )
    assert response.status_code == 200
    assert "Token Generated" in response.get_data(as_text=True)
    token = db.session.query(APIToken).filter_by(token_name=name).one()
    assert token.get_allowed_ip_ranges() == expected


def test_token_form_rejects_entire_submission_for_any_invalid_entry(
    app, client, db, token_owner, token_realm
):
    login_portal(client, token_owner)
    response, _token_plain = _create_token(
        client,
        token_realm.id,
        name="invalid-mixed-range",
        ip_ranges="203.0.113.0/24, definitely-not-an-ip",
    )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Invalid IP address or CIDR: definitely-not-an-ip" in body
    assert "Token Generated" not in body
    assert (
        db.session.query(APIToken)
        .filter_by(token_name="invalid-mixed-range")
        .count()
        == 0
    )


EXPECTED_EXPIRY_OPTIONS = frozenset({"never", *TOKEN_EXPIRY_DAYS})


def _rendered_expiry_options(client, realm_id) -> tuple[str, ...]:
    form, _csrf = _token_form(client, realm_id)
    return field_by_id(form, "expires").options


def test_token_form_expiry_select_matches_route_constant(
    app, client, token_owner, token_realm
):
    """The rendered #expires values are exactly what the route accepts (B057)."""
    login_portal(client, token_owner)
    options = _rendered_expiry_options(client, token_realm.id)
    assert len(options) == len(set(options)), f"duplicate expiry options: {options!r}"
    assert frozenset(options) == EXPECTED_EXPIRY_OPTIONS


def test_token_form_expiry_options_match_route_contract(
    app, client, db, token_owner, token_realm
):
    """Every rendered expiry option creates a token with the mapped lifetime."""
    login_portal(client, token_owner)
    options = _rendered_expiry_options(client, token_realm.id)
    assert frozenset(options) == EXPECTED_EXPIRY_OPTIONS

    for expires in options:
        name = f"expiry-{expires}"
        before = datetime.utcnow()
        response, _token_plain = _create_token(
            client,
            token_realm.id,
            name=name,
            expires=expires,
        )
        after = datetime.utcnow()

        assert response.status_code == 200, expires
        assert "Token Generated" in response.get_data(as_text=True), expires
        token = db.session.query(APIToken).filter_by(token_name=name).one()
        # The IP field was left empty: the token must stay unrestricted.
        assert token.get_allowed_ip_ranges() == [], expires
        if expires == "never":
            assert token.expires_at is None
        else:
            expected_days = TOKEN_EXPIRY_DAYS[expires]
            assert before + timedelta(days=expected_days) <= token.expires_at, expires
            assert token.expires_at <= after + timedelta(days=expected_days), expires


def test_token_form_rejects_unknown_expiry_without_creating(
    app, client, db, token_owner, token_realm
):
    login_portal(client, token_owner)
    response, _token_plain = _create_token(
        client,
        token_realm.id,
        name="invalid-expiry",
        expires="30",
    )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Invalid expiration option" in body
    assert (
        db.session.query(APIToken)
        .filter_by(token_name="invalid-expiry")
        .count()
        == 0
    )

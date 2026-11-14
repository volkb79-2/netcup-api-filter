"""Render-driven tests for reset and invite password form contracts."""
from __future__ import annotations

from netcup_api_filter.password_reset import generate_reset_token
from tests.form_contract_helpers import csrf_field, parse_forms


STRONG_PASSWORD = "SecurePass-2024:XYZ#abc"
OLD_PASSWORD = "OldPassword-2024:ABC#xyz"


def _password_fields(html: str):
    forms = [form for form in parse_forms(html) if form.method == "post"]
    assert len(forms) == 1, f"expected one password POST form, got {forms!r}"
    password_fields = [
        field for field in forms[0].fields if field.field_type == "password"
    ]
    assert len(password_fields) == 2, (
        f"expected password and confirmation fields, got {password_fields!r}"
    )
    csrf_name, csrf_value = csrf_field(html)
    data = {
        csrf_name: csrf_value,
        password_fields[0].name: STRONG_PASSWORD,
        password_fields[1].name: STRONG_PASSWORD,
    }
    return forms[0], password_fields, data


def _assert_password_changed(db, account, old_hash):
    db.session.refresh(account)
    assert account.password_hash != old_hash
    assert account.verify_password(OLD_PASSWORD) is False
    assert account.verify_password(STRONG_PASSWORD) is True


def test_reset_password_post_uses_names_from_rendered_template(
    client, db, make_account
):
    account = make_account("reset-form-user", password=OLD_PASSWORD)
    old_hash = account.password_hash
    token, _expiry = generate_reset_token(
        account, source_ip=None, token_type="reset"
    )

    page = client.get(f"/account/reset-password/{token}")
    assert page.status_code == 200
    form, password_fields, data = _password_fields(page.get_data(as_text=True))
    assert form.action and form.action.endswith("/reset-password/" + token)
    assert [field.name for field in password_fields] == [
        "new_password",
        "confirm_password",
    ]

    response = client.post(form.action, data=data)
    assert response.status_code == 302
    assert response.location.endswith("/account/login")
    _assert_password_changed(db, account, old_hash)


def test_invite_password_post_uses_names_from_rendered_template(
    client, db, make_account
):
    account = make_account("invite-form-user", password=OLD_PASSWORD)
    old_hash = account.password_hash
    token, _expiry = generate_reset_token(
        account, source_ip=None, token_type="invite"
    )

    page = client.get(f"/account/invite/{token}")
    assert page.status_code == 200
    form, password_fields, data = _password_fields(page.get_data(as_text=True))
    assert form.action and form.action.endswith("/invite/" + token)
    assert [field.name for field in password_fields] == [
        "new_password",
        "confirm_password",
    ]

    response = client.post(form.action, data=data)
    assert response.status_code == 302
    assert response.location.endswith("/account/login")
    _assert_password_changed(db, account, old_hash)


def _assert_mismatch_rejected(client, db, account, old_hash, page_path):
    page = client.get(page_path)
    assert page.status_code == 200
    form, password_fields, data = _password_fields(page.get_data(as_text=True))
    assert password_fields[0].name == "new_password", (
        "the mismatch case must submit the handler's actual password field"
    )
    data[password_fields[1].name] = STRONG_PASSWORD + "-different"

    response = client.post(form.action, data=data)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'class="alert alert-danger' in body
    assert "Passwords do not match" in body
    db.session.refresh(account)
    assert account.password_hash == old_hash
    assert account.verify_password(OLD_PASSWORD) is True
    assert account.verify_password(STRONG_PASSWORD) is False


def test_reset_password_rejects_confirmation_mismatch(client, db, make_account):
    account = make_account("reset-mismatch-user", password=OLD_PASSWORD)
    old_hash = account.password_hash
    token, _expiry = generate_reset_token(
        account, source_ip=None, token_type="reset"
    )
    _assert_mismatch_rejected(
        client, db, account, old_hash, f"/account/reset-password/{token}"
    )


def test_invite_rejects_confirmation_mismatch(client, db, make_account):
    account = make_account("invite-mismatch-user", password=OLD_PASSWORD)
    old_hash = account.password_hash
    token, _expiry = generate_reset_token(
        account, source_ip=None, token_type="invite"
    )
    _assert_mismatch_rejected(
        client, db, account, old_hash, f"/account/invite/{token}"
    )

"""Small helpers for hermetic HTTP tests that drive the real (CSRF-enabled) Flask stack."""
from __future__ import annotations

import re
import secrets

from flask import g

from netcup_api_filter.account_auth import SESSION_KEY_SESSION_TOKEN, SESSION_KEY_USER_ID
from netcup_api_filter.api.admin import SESSION_KEY_ADMIN_ID, SESSION_KEY_ADMIN_USERNAME
from netcup_api_filter.database import db
from netcup_api_filter.models import AccountSession

_FIELD_RE = re.compile(r'name="csrf_token"[^>]*?value="([^"]+)"')
_META_RE = re.compile(r'<meta name="csrf-token" content="([^"]+)"')


def mint_csrf(client, path):
    """GET *path* with *client* and return the CSRF token rendered into the page.

    The ``app`` fixture keeps ONE app context open for the whole test, so ``flask.g``
    (where Flask-WTF caches the generated token) outlives requests. Drop the cache so
    every GET mints/reads the token for *this* client's session, as in production.
    """
    g.pop("csrf_token", None)
    html = client.get(path).get_data(as_text=True)
    match = _FIELD_RE.search(html) or _META_RE.search(html)
    assert match, f"no csrf token rendered on {path}"
    return match.group(1)


def login_portal(client, account):
    """Authenticate *client* as *account*, bypassing password + 2FA.

    Writes exactly what account_auth.create_session() leaves behind: a DB-backed
    AccountSession plus the two session keys require_account_auth checks.
    """
    token = secrets.token_urlsafe(32)
    db.session.add(AccountSession(
        account_id=account.id, session_token=token, ip_address="127.0.0.1", user_agent="pytest",
    ))
    db.session.commit()
    with client.session_transaction() as sess:
        sess[SESSION_KEY_USER_ID] = account.id
        sess[SESSION_KEY_SESSION_TOKEN] = token


def login_admin(client, admin):
    with client.session_transaction() as sess:
        sess[SESSION_KEY_ADMIN_ID] = admin.id
        sess[SESSION_KEY_ADMIN_USERNAME] = admin.username

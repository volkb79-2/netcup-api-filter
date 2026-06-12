"""Shared helpers for cross-role E2E round-trip test suites (T08–T11).

Import from here instead of duplicating in each test file. Every function is
small, dependency-free (only imports from ui_tests + stdlib), and stateless.

Pattern rules: read test_cross_role_account_lifecycle.py module docstring.
"""
from __future__ import annotations

import re
import secrets

from ui_tests import verification, workflows
from ui_tests.browser import Browser
from ui_tests.config import settings
from ui_tests.deployment_state import get_base_url, get_deployment_target
from ui_tests.mailpit_client import MailpitClient
from ui_tests.parallel_session_manager import ParallelSessionManager


# Password policy: >= 20 chars, special chars limited to @#$%
def make_password(tag: str) -> str:
    return f"Xq{tag}{secrets.token_hex(10)}@#$%"


def base_url() -> str:
    return get_base_url(get_deployment_target()).rstrip("/")


# --------------------------------------------------------------------------
# Mailpit helpers
# --------------------------------------------------------------------------

def mailpit_client() -> MailpitClient:
    return MailpitClient()


def wait_for_email(
    mailpit: MailpitClient,
    *,
    to_address: str,
    subject_substr: str,
    timeout: float = 20.0,
):
    msg = mailpit.wait_for_message(
        predicate=lambda m: (
            subject_substr.lower() in (m.subject or "").lower()
            and any(to_address.lower() == a.address.lower() for a in (m.to or []))
        ),
        timeout=timeout,
        poll_interval=0.5,
    )
    assert msg is not None, (
        f"Timed out waiting for email to {to_address!r} with subject ~ {subject_substr!r}"
    )
    return msg


def extract_link(msg, path_prefix: str) -> str:
    """Extract the first absolute URL whose path contains ``path_prefix``."""
    body = (msg.text or "") + "\n" + (msg.html or "")
    pattern = re.compile(r"https?://[^\s\"'<>]*" + re.escape(path_prefix) + r"[^\s\"'<>]+")
    m = pattern.search(body)
    assert m, f"No URL containing {path_prefix!r} in email body:\n{body[:600]}"
    return m.group(0)


def link_to_local_url(absolute_url: str) -> str:
    """Rewrite the email's external host to the test base URL, keep path+query."""
    path = re.sub(r"^https?://[^/]+", "", absolute_url)
    return base_url() + path


# --------------------------------------------------------------------------
# Browser / session helpers
# --------------------------------------------------------------------------

async def browser_for(manager: ParallelSessionManager, role: str, session_id: str) -> Browser:
    handle = await manager.create_session(role=role, session_id=session_id)
    browser = Browser(handle.page)
    await browser.reset()
    return browser


async def admin_browser(manager: ParallelSessionManager, session_id: str = "admin_xrole") -> Browser:
    handle = await manager.create_session(role="admin", session_id=session_id)
    browser = Browser(handle.page)
    await browser.reset()
    await workflows.ensure_admin_dashboard(browser)
    return browser


async def account_login(browser: Browser, username: str, password: str) -> None:
    """Log a throwaway account in (username/password + email 2FA via Mailpit)."""
    await browser.goto(settings.url("/account/login"))
    await browser.fill("#username", username)
    await browser.fill("#password", password)
    await browser.click("button[type='submit']")
    try:
        await browser._page.wait_for_url(
            re.compile(r".*/account/(?:login/2fa|login|dashboard)(?:\?.*)?$"),
            timeout=10_000,
        )
    except Exception:
        pass
    await workflows.handle_2fa_if_present(browser, timeout=20.0)
    await browser.goto(settings.url("/account/dashboard"), wait_until="domcontentloaded")
    assert "/account/login" not in browser._page.url, (
        f"Account login did not establish a session for {username!r}; "
        f"at {browser._page.url}"
    )


async def admin_delete_account(admin: Browser, account_id: int, username: str) -> None:
    """Best-effort cleanup: delete a throwaway account via the admin UI."""
    try:
        await admin.goto(settings.url(f"/admin/accounts/{account_id}"))
        await admin.evaluate(
            """
            () => {
                const f = document.querySelector("form[action$='/delete']");
                if (f) f.submit();
            }
            """
        )
        verification.wait_for(
            lambda: verification.get_account(username) is None,
            timeout=10.0,
        )
    except Exception:
        pass


async def dns_get(token: str, domain: str) -> int:
    """GET the DNS records endpoint with a Bearer token; return HTTP status."""
    import httpx

    url = base_url() + f"/api/dns/{domain}/records"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url, headers={"Authorization": f"Bearer {token}"}, timeout=15.0
        )
    return resp.status_code


async def complete_invite(
    manager: ParallelSessionManager,
    invite_url: str,
    password: str,
) -> None:
    """Accept an account invite via a fresh anonymous browser context."""
    invite_browser = await browser_for(
        manager, "anonymous", f"invite_{secrets.token_hex(3)}"
    )
    try:
        await invite_browser.goto(invite_url, wait_until="domcontentloaded")
        await invite_browser.fill("#new_password", password)
        await invite_browser.fill("#confirm_password", password)
        await invite_browser.submit("#invite-form")
        await invite_browser._page.wait_for_url(
            re.compile(r".*/account/login(?:\?.*)?$"), timeout=10_000
        )
    finally:
        await invite_browser._page.context.close()

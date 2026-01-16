"""Account security session management tests.

Covers:
- /account/security (GET)
- /account/security/session/<id>/revoke (POST)
- /account/security/sessions/revoke-all (POST)

These are functional/journey tests: they may call ensure_user_dashboard(),
which only logs in if needed (session reuse is allowed).
"""

import pytest

from ui_tests.browser import Browser
from ui_tests.config import settings
from ui_tests import workflows


pytestmark = pytest.mark.asyncio


class TestAccountSessionRevocation:
    async def _new_account_browser(self, session_manager, session_id: str) -> Browser:
        handle = await session_manager.create_session(role="account", session_id=session_id)
        browser = Browser(handle.page)
        await browser.reset()
        await workflows.ensure_user_dashboard(browser)
        return browser

    async def test_revoke_specific_session_forces_other_session_to_login(self, session_manager, active_profile):
        security_path = "/account/security"
        revoke_action_prefix = "/account/security/session/"

        browser_a = await self._new_account_browser(session_manager, "acct_a")
        browser_b = await self._new_account_browser(session_manager, "acct_b")

        await browser_b.goto(settings.url(security_path))
        await browser_b.wait_for_text("h1.h3", "Security Settings", timeout=10.0)

        # Should show at least one revoke button when there is another active session.
        await browser_b.click(f"form[action^='{revoke_action_prefix}'] button[type='submit']")
        await browser_b.wait_for_text(".alert", "Session revoked", timeout=10.0)

        # The revoked session should be forced back to login on next navigation.
        await browser_a.goto(settings.url("/account/dashboard"))
        assert "/account/login" in browser_a._page.url

    async def test_revoke_all_other_sessions_forces_other_session_to_login(self, session_manager, active_profile):
        security_path = "/account/security"
        revoke_all_path = "/account/security/sessions/revoke-all"

        browser_a = await self._new_account_browser(session_manager, "acct_a2")
        browser_b = await self._new_account_browser(session_manager, "acct_b2")

        await browser_b.goto(settings.url(security_path))
        await browser_b.wait_for_text("h1.h3", "Security Settings", timeout=10.0)

        await browser_b.click(f"form[action='{revoke_all_path}'] button[type='submit']")
        await browser_b.wait_for_text(".alert", "Signed out", timeout=10.0)

        await browser_a.goto(settings.url("/account/dashboard"))
        assert "/account/login" in browser_a._page.url

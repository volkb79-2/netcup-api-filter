"""Coverage tests for remaining account routes flagged by the route audit.

Target routes (from coverage audit):
- /account/register/resend
- /account/register/verify/<token>
- /account/activity/export
- /account/api/realms
- /account/api/realms/<int:realm_id>/tokens
- /account/realms/new
- /account/telegram/unlink

These tests aim to be stable and policy-compliant:
- They reuse sessions (no forced login resets) unless explicitly required.
- They avoid assuming optional dependencies or external services.
"""

import json
import os

import pytest

from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests.env_defaults import get_env_default
from ui_tests.workflows import ensure_user_dashboard


pytestmark = pytest.mark.asyncio


async def _clear_browser_auth_state(browser) -> None:
    # The test suite reuses Playwright storage state by default.
    # Registration route-guard tests must ensure an unauthenticated context.
    await browser._page.context.clear_cookies()
    # localStorage/sessionStorage are origin-scoped and may not be accessible on
    # about:blank; ensure we're on an app origin first.
    await browser.goto(settings.url("/"), wait_until="domcontentloaded")
    try:
        await browser.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
    except Exception:
        await browser.goto(settings.url("/"), wait_until="domcontentloaded")
        await browser.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")


class TestAccountRegistrationRouteGuards:
    async def test_register_verify_link_invalid_token_redirects_to_register(self, active_profile):
        async with browser_session() as browser:
            await browser.reset()
            await _clear_browser_auth_state(browser)

            nav = await browser.goto(
                settings.url("/account/register/verify/invalid-token-for-coverage"),
                wait_until="domcontentloaded",
            )
            assert nav.get("status") == 200

            current_path = await browser.evaluate("() => window.location.pathname")
            # Invalid or expired token should land back on /account/register.
            assert current_path.startswith("/account/register")

    async def test_register_resend_without_registration_session_redirects_to_register(self, active_profile):
        async with browser_session() as browser:
            await browser.reset()
            await _clear_browser_auth_state(browser)

            # CSRF is typically enforced for POST requests; get a token from /account/register.
            await browser.goto(settings.url("/account/register"), wait_until="domcontentloaded")
            csrf_token = await browser.get_attribute('input[name="csrf_token"]', "value")
            assert csrf_token

            resp = await browser.request_post_form(
                settings.url("/account/register/resend"),
                data={"csrf_token": csrf_token},
            )
            assert resp["status"] in (200, 302)


class TestAccountAuthenticatedRemainingRoutes:
    async def _ensure_telegram_linked(self, browser) -> None:
        link_url = settings.url("/account/settings/telegram/link")
        nav = await browser.goto(link_url, wait_until="domcontentloaded")
        assert nav.get("status") == 200

        if await browser._page.locator("text=Telegram Linked").count():
            return

        if await browser._page.locator("text=Telegram linking is not configured").count():
            pytest.skip("Telegram linking not configured in this deployment")

        token = (await browser._page.text_content("#telegram-link-token") or "").strip()
        assert token

        callback_secret = (
            os.getenv("UI_TELEGRAM_LINK_CALLBACK_SECRET")
            or os.getenv("TELEGRAM_LINK_CALLBACK_SECRET")
            or get_env_default("TELEGRAM_LINK_CALLBACK_SECRET")
            or ""
        ).strip()
        if not callback_secret:
            pytest.skip("Telegram callback secret not configured")

        resp = await browser._page.request.post(
            settings.url("/api/telegram/link"),
            headers={
                "Content-Type": "application/json",
                "X-NAF-TELEGRAM-SECRET": callback_secret,
            },
            data=json.dumps({"token": token, "chat_id": "123"}),
        )
        assert resp.status == 200
        assert await resp.json() == {"status": "linked"}

        await browser.goto(link_url, wait_until="domcontentloaded")
        assert await browser._page.locator("text=Telegram Linked").is_visible()

    async def test_account_api_realms_returns_json(self, active_profile):
        async with browser_session() as browser:
            await ensure_user_dashboard(browser)

            resp = await browser.request_get_json(settings.url("/account/api/realms"))
            assert resp["status"] == 200
            assert isinstance(resp["json"], list)

    async def test_account_api_realm_tokens_route_exists(self, active_profile):
        async with browser_session() as browser:
            await ensure_user_dashboard(browser)

            # We don't assume a specific realm exists in all environments. This request is
            # still valuable for route coverage (should return 200/403/404, never 500).
            resp = await browser.request_get_bytes(settings.url("/account/api/realms/0/tokens"))
            assert resp["status"] in (200, 403, 404)

    async def test_account_realms_new_page_loads(self, active_profile):
        async with browser_session() as browser:
            await ensure_user_dashboard(browser)

            nav = await browser.goto(settings.url("/account/realms/new"), wait_until="domcontentloaded")
            assert nav.get("status") == 200

            current_path = await browser.evaluate("() => window.location.pathname")
            assert current_path.startswith("/account/realms")

    async def test_account_activity_export_returns_ods_zip(self, active_profile):
        async with browser_session() as browser:
            await ensure_user_dashboard(browser)

            resp = await browser.request_get_bytes(settings.url("/account/activity/export"))
            assert resp["status"] == 200
            body = resp["bytes"]
            assert isinstance(body, (bytes, bytearray))
            assert len(body) > 10
            # ODS is a zip file; first bytes should be 'PK'.
            assert body[:2] == b"PK"

    async def test_account_telegram_unlink_post_works_with_csrf(self, active_profile):
        async with browser_session() as browser:
            await ensure_user_dashboard(browser)

            # Obtain a CSRF token from the Telegram settings page.
            await browser.goto(settings.url("/account/settings/telegram/link"), wait_until="domcontentloaded")
            csrf_token = await browser.get_attribute('input[name="csrf_token"]', "value")

            if not csrf_token:
                # Fallback: settings page generally includes CSRF tokens in forms.
                await browser.goto(settings.url("/account/settings"), wait_until="domcontentloaded")
                csrf_token = await browser.get_attribute('input[name="csrf_token"]', "value")

            assert csrf_token

            resp = await browser.request_post_form(
                settings.url("/account/telegram/unlink"),
                data={"csrf_token": csrf_token},
            )
            assert resp["status"] in (200, 302)

    async def test_account_telegram_linking_flow_completes_when_configured(self, active_profile):
        async with browser_session() as browser:
            await ensure_user_dashboard(browser)

            await self._ensure_telegram_linked(browser)

            status = await browser.request_get_json(settings.url("/account/settings/telegram/status"))
            assert status["status"] == 200
            assert status["json"]["linked"] is True

    async def test_account_telegram_send_test_message_shows_feedback(self, active_profile):
        async with browser_session() as browser:
            await ensure_user_dashboard(browser)
            await self._ensure_telegram_linked(browser)

            # Click the Send Test button on the Telegram linking page.
            await browser._page.click("form[action$='/account/settings/telegram/test'] button")
            await browser._page.wait_for_load_state("domcontentloaded")

            body = (await browser.text("body")) or ""
            lowered = body.lower()
            # Deterministic in default local config: Telegram sending disabled -> error flash.
            # But allow success if a developer configured Telegram for real.
            assert (
                "test message sent to telegram" in lowered
                or "failed to send telegram test message" in lowered
            )

    async def test_account_telegram_notification_toggle_persists_and_resets_on_unlink(self, active_profile):
        async with browser_session() as browser:
            await ensure_user_dashboard(browser)
            await self._ensure_telegram_linked(browser)

            # Enable notify_via_telegram in Account Settings.
            await browser.goto(settings.url("/account/settings"), wait_until="domcontentloaded")
            checkbox = browser._page.locator("#notify_via_telegram")
            assert await checkbox.count() == 1
            await checkbox.check()
            await browser._page.click("button[type='submit']")
            await browser._page.wait_for_load_state("domcontentloaded")
            assert "settings updated" in ((await browser.text("body")) or "").lower()

            # Verify persisted.
            await browser.goto(settings.url("/account/settings"), wait_until="domcontentloaded")
            assert await browser._page.locator("#notify_via_telegram").is_checked()

            # Unlink Telegram via direct POST with CSRF.
            await browser.goto(settings.url("/account/settings/telegram/link"), wait_until="domcontentloaded")
            csrf_token = await browser.get_attribute('input[name="csrf_token"]', "value")
            assert csrf_token

            resp = await browser.request_post_form(
                settings.url("/account/telegram/unlink"),
                data={"csrf_token": csrf_token},
            )
            assert resp["status"] in (200, 302)

            # After unlink, the checkbox should disappear and the helper text should show.
            await browser.goto(settings.url("/account/settings"), wait_until="domcontentloaded")
            assert await browser._page.locator("#notify_via_telegram").count() == 0
            assert "telegram notifications are available after linking" in ((await browser.text("body")) or "").lower()

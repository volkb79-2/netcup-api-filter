"""The ONE test of the shipped admin's forced first-login password change.

It runs on its own fresh instance (a private copy of the golden DB, no personas), so it
always starts from exactly what a fresh tarball install looks like — independent of test
order, of earlier or interrupted runs, and of every other test. The new password lives in
a local variable only; nothing is persisted anywhere.
"""
from __future__ import annotations

import sqlite3
from dataclasses import replace

import bcrypt
import pytest

from netcup_api_filter.config_defaults import require_default
from ui_tests.browser import Browser
from ui_tests.config import settings
from ui_tests.e2e_env import app_instance
from ui_tests.personas import new_password
from ui_tests.playwright_client import PlaywrightClient

pytestmark = [pytest.mark.asyncio, pytest.mark.installation, pytest.mark.smoke]


def _admin_row(db_path, username: str) -> tuple[int, str]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT must_change_password, password_hash FROM accounts WHERE username = ?", (username,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, f"shipped admin {username} missing from the fresh instance"
    return int(row[0]), row[1]


async def _submit_login(browser: Browser, username: str, password: str) -> None:
    await browser.goto(settings.url("/admin/login"), wait_until="domcontentloaded")
    await browser.fill("#username", username)
    await browser.fill("#password", password)
    await browser.click("form[action*='/admin/login'] button[type='submit']")
    await browser._page.wait_for_load_state("domcontentloaded")


async def test_first_login_forces_password_change_on_a_fresh_install():
    username = require_default("DEFAULT_ADMIN_USERNAME")
    shipped_password = require_default("DEFAULT_ADMIN_PASSWORD")
    chosen = new_password()

    with app_instance(keep_shipped_admin=True) as (instance, _):
        assert _admin_row(instance.db_path, username)[0] == 1, "a fresh install must force the change"
        fresh = replace(settings.profile("primary"), base_url=instance.base_url)
        with settings.use_profile(fresh):
            async with PlaywrightClient(headless=settings.playwright_headless) as client:
                browser = Browser(client.page)

                # 1. The documented default logs in, but only as far as the forced change.
                await _submit_login(browser, username, shipped_password)
                await browser._page.wait_for_url(lambda url: "/admin/change-password" in url, timeout=10_000)
                await browser.goto(settings.url("/admin/"), wait_until="domcontentloaded")
                assert "/admin/change-password" in browser._page.url, "dashboard reachable before the change"

                # The fresh admin has the placeholder email, so the form offers 2FA-email setup,
                # but it is optional (SMTP is typically not configured yet on a fresh install).
                email_field = await browser.query_selector("#email")
                assert email_field is not None, "fresh install must offer the 2FA email setup"
                assert await email_field.get_attribute("required") is None, "email must stay optional"

                # 2. A mismatched confirmation is rejected and changes nothing.
                await browser.fill("#new_password", chosen)
                await browser.fill("#confirm_password", new_password())
                await browser.submit("#changePasswordForm")
                await browser.wait_for_text("body", "New passwords do not match", timeout=10.0)
                assert _admin_row(instance.db_path, username)[0] == 1

                # 3. The real change clears the flag and stores the new hash.
                await browser.fill("#new_password", chosen)
                await browser.fill("#confirm_password", chosen)
                await browser.submit("#changePasswordForm")
                await browser.wait_for_text("h1", "Dashboard", timeout=10.0)
                must_change, password_hash = _admin_row(instance.db_path, username)
                assert must_change == 0
                assert bcrypt.checkpw(chosen.encode(), password_hash.encode())
                assert not bcrypt.checkpw(shipped_password.encode(), password_hash.encode())

                # 4. After logout the default is dead and the chosen password works.
                await browser.goto(settings.url("/admin/logout"), wait_until="domcontentloaded")
                await _submit_login(browser, username, shipped_password)
                assert "/admin/login" in browser._page.url
                assert "Invalid credentials" in await browser.text("body")
                await _submit_login(browser, username, chosen)
                await browser.wait_for_text("h1", "Dashboard", timeout=10.0)

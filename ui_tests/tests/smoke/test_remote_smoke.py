"""Read-only smoke against a DEPLOYED instance (``NAF_E2E_TARGET=remote``).

Selected with ``-m remote_smoke``; see docs/WEBHOSTING_TESTING_GUIDE.md. Every test here only
issues GET navigations plus the admin login form of the operator account from the environment
(``ui_tests/config.py bind_remote``). Nothing is created, changed or deleted, and no password
is rotated. Locally (default target) the same tests run against the throwaway instance, so the
subset itself stays verified by the normal browser lane.
"""
from __future__ import annotations

import pytest

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import TARGET_REMOTE, selected_target, settings

pytestmark = [pytest.mark.asyncio, pytest.mark.remote_smoke]

_BAD_BODY = ("Traceback", "Internal Server Error", "UndefinedError", "jinja2.")
PUBLIC_PAGES = ["/admin/login", "/account/login"]
ADMIN_PAGES = ["/admin/", "/admin/accounts", "/admin/audit", "/admin/settings", "/admin/system"]


async def _assert_page_ok(browser, path: str) -> None:
    result = await browser.goto(settings.url(path), wait_until="domcontentloaded")
    status = result["status"]
    assert status is not None and status < 400, f"{path} returned HTTP {status}"
    body = await browser.text("body")
    for fragment in _BAD_BODY:
        assert fragment not in body, f"error fragment {fragment!r} on {path}"


@pytest.mark.skipif(
    selected_target() != TARGET_REMOTE,
    reason="the local throwaway instance allows writes by design; the guard applies to the remote profile",
)
async def test_remote_profile_is_read_only():
    """The smoke profile never permits writes; load-bearing guard for the whole subset."""
    assert settings.allow_writes is False


@pytest.mark.parametrize("path", PUBLIC_PAGES)
async def test_public_pages_render(path):
    async with browser_session("anonymous") as browser:
        await _assert_page_ok(browser, path)
        assert await browser.query_selector("input[type='password']") is not None, (
            f"{path} has no password field"
        )


async def test_admin_login_reaches_dashboard():
    async with browser_session("admin") as browser:
        await workflows.ensure_admin_dashboard(browser)
        assert "/admin/" in browser._page.url


@pytest.mark.parametrize("path", ADMIN_PAGES)
async def test_admin_pages_render(path):
    async with browser_session("admin") as browser:
        await workflows.ensure_admin_dashboard(browser)
        await _assert_page_ok(browser, path)

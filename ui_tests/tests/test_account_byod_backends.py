"""Account portal BYOD backend lifecycle.

Covers:
- GET/POST /account/backends/new
- GET/POST /account/backends/<id>/edit
- POST /account/backends/<id>/delete

This is intentionally offline-safe: it does not call the backend test endpoint.
"""

from __future__ import annotations

import re
import secrets

import pytest

from ui_tests import workflows
from ui_tests.browser import Browser
from ui_tests.config import settings


pytestmark = pytest.mark.asyncio


def _extract_backend_id(url: str) -> int:
    match = re.search(r"/account/backends/(\d+)(?:/|$)", url)
    if not match:
        raise AssertionError(f"Could not extract backend_id from url={url!r}")
    return int(match.group(1))


async def _pick_provider_id(browser: Browser, provider_code: str) -> str:
    return await browser.evaluate(
        """
        (providerCode) => {
            const select = document.querySelector('#provider_id');
            if (!select) return '';
            const options = Array.from(select.options || []);
            const opt = options.find(o => (o.dataset.providerCode || '') === providerCode && (o.value || '') !== '' && !o.disabled);
            return opt ? opt.value : '';
        }
        """,
        provider_code,
    )


async def test_account_byod_backend_create_edit_delete(active_profile, session_manager):
    if not active_profile.allow_writes:
        pytest.skip("profile is read-only")

    handle = await session_manager.create_session(role="account", session_id="acct_byod")
    browser = Browser(handle.page)
    await browser.reset()
    await workflows.ensure_user_dashboard(browser)

    token = secrets.token_hex(4)
    display_name = f"BYOD PowerDNS {token}"
    display_name2 = f"BYOD PowerDNS {token} (edited)"
    service_name = f"byod-powerdns-{token}"  # lowercase letters/numbers/hyphens

    await browser.goto(settings.url("/account/backends/new"), wait_until="domcontentloaded")
    await browser.wait_for_text("h1", "Add DNS Backend", timeout=10.0)

    provider_id = await _pick_provider_id(browser, "powerdns")
    if not provider_id:
        pytest.skip("No enabled PowerDNS provider available")

    await browser.select("#provider_id", provider_id)
    # Ensure dynamic config section becomes visible before filling config.
    await browser._page.wait_for_selector("#config-powerdns:not(.d-none)")

    await browser.fill("#service_name", service_name)
    await browser.fill("#display_name", display_name)
    await browser.fill("#config_api_url", "http://powerdns:8081")
    await browser.fill("#config_pdns_api_key", f"dummy-pdns-key-{token}")

    await browser.submit("#backend-form")
    await browser.wait_for_text("h1", display_name, timeout=10.0)

    backend_id = _extract_backend_id(browser._page.url)

    # Edit (non-destructive)
    await browser.goto(settings.url(f"/account/backends/{backend_id}/edit"), wait_until="domcontentloaded")
    await browser.wait_for_text("h1", "Edit Backend", timeout=10.0)
    await browser.fill("#display_name", display_name2)
    await browser.submit("#backend-form")
    await browser.wait_for_text("h1", display_name2, timeout=10.0)

    # Delete
    delete_action_raw = await browser.get_attribute("form[action*='/delete']", "action")
    delete_csrf = await browser.get_attribute("form[action*='/delete'] input[name='csrf_token']", "value")
    assert delete_action_raw and delete_csrf

    delete_action = delete_action_raw if delete_action_raw.startswith("http") else settings.url(delete_action_raw)
    resp = await browser.request_post_form(delete_action, {"csrf_token": delete_csrf})
    assert resp["status"] in {200, 302}

    await browser.goto(settings.url("/account/backends"), wait_until="domcontentloaded")
    body = await browser.text("body")
    assert service_name not in (body or "")
    assert display_name2 not in (body or "")

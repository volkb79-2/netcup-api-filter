"""Admin Domain Roots lifecycle journey.

Covers the core admin lifecycle for Domain Roots:
- Create
- Grants page loads
- Enable/disable toggles
- Delete

This test is intentionally self-cleaning and uses session reuse.
"""

from __future__ import annotations

import re
import secrets

import pytest

from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests import workflows


pytestmark = pytest.mark.asyncio


def _extract_root_id(url: str) -> int:
    match = re.search(r"/admin/domain-roots/(\d+)(?:/|$)", url)
    if not match:
        raise AssertionError(f"Could not extract root_id from url={url!r}")
    return int(match.group(1))


async def _pick_backend_service_id(browser) -> str:
    backend_id = await browser.evaluate(
        """
        () => {
            const sel = document.querySelector('#backend_service_id');
            if (!sel) return null;
            const options = Array.from(sel.options || []);
            const chosen = options.find(opt => opt.value && opt.value !== '');
            return chosen ? chosen.value : null;
        }
        """
    )
    return backend_id or ""


async def test_admin_domain_roots_lifecycle_journey(active_profile):
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)

        suffix = secrets.token_hex(4)
        root_domain = f"dr-{suffix}.example.test"
        dns_zone = root_domain

        # Create
        await browser.goto(settings.url("/admin/domain-roots/new"))
        await browser.wait_for_text("main h1", "Create")

        backend_id = await _pick_backend_service_id(browser)
        if not backend_id:
            pytest.skip("No backend services available to create a domain root")

        await browser.fill("#root_domain", root_domain)
        await browser.fill("#dns_zone", dns_zone)
        await browser.select("#backend_service_id", backend_id)
        await browser.select("#visibility", "public")

        await browser.submit("#domainRootForm")

        # We should land on the detail page for the new root.
        await browser.wait_for_text("h1", root_domain)
        root_id = _extract_root_id(browser._page.url)

        # Grants page loads
        grants_nav = await browser.goto(
            settings.url(f"/admin/domain-roots/{root_id}/grants"),
            wait_until="domcontentloaded",
        )
        assert grants_nav.get("status") == 200, (
            f"Expected 200 for grants page, got {grants_nav.get('status')} (url={browser._page.url!r})"
        )
        await browser.wait_for_text("body", "User Grants")
        body_text = await browser.text("body")
        # Page should render even with zero grants.
        assert "Add Grant" in body_text
        assert "No grants configured for this domain root" in body_text

        # Disable
        await browser.goto(settings.url(f"/admin/domain-roots/{root_id}"))
        disable_csrf = await browser.get_attribute(
            "form[action*='/disable'] input[name='csrf_token']",
            "value",
        )
        disable_action_raw = await browser.get_attribute("form[action*='/disable']", "action")
        assert disable_csrf and disable_action_raw

        disable_action = (
            disable_action_raw
            if disable_action_raw.startswith("http")
            else settings.url(disable_action_raw)
        )

        resp = await browser.request_post_form(disable_action, {"csrf_token": disable_csrf})
        assert resp["status"] in {200, 302}

        await browser.goto(settings.url(f"/admin/domain-roots/{root_id}"))
        await browser.wait_for_text("h1", root_domain)
        await browser.wait_for_text("body", "Inactive")

        # Enable
        enable_csrf = await browser.get_attribute(
            "form[action*='/enable'] input[name='csrf_token']",
            "value",
        )
        enable_action_raw = await browser.get_attribute("form[action*='/enable']", "action")
        assert enable_csrf and enable_action_raw

        enable_action = (
            enable_action_raw
            if enable_action_raw.startswith("http")
            else settings.url(enable_action_raw)
        )

        resp = await browser.request_post_form(enable_action, {"csrf_token": enable_csrf})
        assert resp["status"] in {200, 302}

        await browser.goto(settings.url(f"/admin/domain-roots/{root_id}"))
        await browser.wait_for_text("h1", root_domain)
        await browser.wait_for_text("body", "Active")

        # Delete
        delete_csrf = await browser.get_attribute(
            "form[action*='/delete'] input[name='csrf_token']",
            "value",
        )
        delete_action_raw = await browser.get_attribute("form[action*='/delete']", "action")
        assert delete_csrf and delete_action_raw

        delete_action = (
            delete_action_raw
            if delete_action_raw.startswith("http")
            else settings.url(delete_action_raw)
        )

        resp = await browser.request_post_form(delete_action, {"csrf_token": delete_csrf})
        assert resp["status"] in {200, 302}

        await browser.goto(settings.url("/admin/domain-roots"))
        await browser.wait_for_text("h1", "Domain Roots")
        body_text = await browser.text("body")
        assert root_domain not in body_text

"""Admin Domain Root grants tests.

Covers:
- /admin/domain-roots/<id>/grants (GET)
- /admin/domain-roots/<id>/grants/add (POST)
- /admin/domain-roots/<id>/grants/<grant_id>/revoke (POST)

Also verifies grants actually influence account portal eligibility:
- /account/realms/request shows/hides private roots based on grant state.

These are functional/journey tests:
- They reuse existing sessions when possible.
- They only create isolated sessions when we need two actors (admin + account).
"""

from __future__ import annotations

import re
import secrets

import pytest

from ui_tests import workflows
from ui_tests.browser import Browser, browser_session
from ui_tests.config import settings


pytestmark = pytest.mark.asyncio


def _extract_root_id(url: str) -> int:
    match = re.search(r"/admin/domain-roots/(\d+)(?:/|$)", url)
    if not match:
        raise AssertionError(f"Could not extract root_id from url={url!r}")
    return int(match.group(1))


async def _pick_backend_service_id(browser: Browser) -> str:
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


async def _add_grant_for_demo_user(browser: Browser, root_id: int) -> None:
    await browser.goto(settings.url(f"/admin/domain-roots/{root_id}/grants"), wait_until="domcontentloaded")
    await browser.wait_for_text("body", "User Grants")

    # Identify the demo user option.
    demo_username = await browser.evaluate(
        """
        () => {
            const sel = document.querySelector("select[name='account_id']");
            if (!sel) return null;
            const opts = Array.from(sel.options || []);
            const desired = opts.find(o => (o.value || '') !== '' && (o.textContent || '').includes('demo-user'));
            return desired ? desired.value : null;
        }
        """
    )

    if not demo_username:
        pytest.skip("demo-user not available in eligible_accounts for grants")

    add_csrf = await browser.get_attribute(
        "form[action*='/grants/add'] input[name='csrf_token']",
        "value",
    )
    add_action_raw = await browser.get_attribute("form[action*='/grants/add']", "action")
    assert add_csrf and add_action_raw

    add_action = add_action_raw if add_action_raw.startswith("http") else settings.url(add_action_raw)

    resp = await browser.request_post_form(
        add_action,
        {
            "csrf_token": add_csrf,
            "account_id": str(demo_username),
            "max_realms": "5",
        },
    )
    assert resp["status"] in {200, 302}


async def _revoke_grant_for_demo_user(browser: Browser, root_id: int) -> None:
    await browser.goto(settings.url(f"/admin/domain-roots/{root_id}/grants"), wait_until="domcontentloaded")
    await browser.wait_for_text("body", "User Grants")

    revoke_form_selector = "tr:has-text('demo-user') form[action*='/revoke']"
    revoke_action_raw = await browser.get_attribute(revoke_form_selector, "action")
    revoke_csrf = await browser.get_attribute(f"{revoke_form_selector} input[name='csrf_token']", "value")

    if not revoke_action_raw:
        # No active grant to revoke.
        return

    assert revoke_csrf

    revoke_action = revoke_action_raw if revoke_action_raw.startswith("http") else settings.url(revoke_action_raw)

    resp = await browser.request_post_form(revoke_action, {"csrf_token": revoke_csrf})
    assert resp["status"] in {200, 302}


async def _delete_domain_root(browser: Browser, root_id: int) -> None:
    await browser.goto(settings.url(f"/admin/domain-roots/{root_id}"), wait_until="domcontentloaded")

    delete_csrf = await browser.get_attribute(
        "form[action*='/delete'] input[name='csrf_token']",
        "value",
    )
    delete_action_raw = await browser.get_attribute("form[action*='/delete']", "action")

    if not delete_csrf or not delete_action_raw:
        return

    delete_action = delete_action_raw if delete_action_raw.startswith("http") else settings.url(delete_action_raw)

    resp = await browser.request_post_form(delete_action, {"csrf_token": delete_csrf})
    assert resp["status"] in {200, 302}


async def test_admin_domain_root_grants_add_and_revoke(active_profile):
    if not active_profile.allow_writes:
        pytest.skip("profile is read-only")

    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)

        suffix = secrets.token_hex(4)
        root_domain = f"grants-{suffix}.example.test"

        # Create a private root so grants are meaningful.
        await browser.goto(settings.url("/admin/domain-roots/new"))
        await browser.wait_for_text("main h1", "Create")

        backend_id = await _pick_backend_service_id(browser)
        if not backend_id:
            pytest.skip("No backend services available to create a domain root")

        await browser.fill("#root_domain", root_domain)
        await browser.fill("#dns_zone", root_domain)
        await browser.select("#backend_service_id", backend_id)
        await browser.select("#visibility", "private")
        await browser.submit("#domainRootForm")

        await browser.wait_for_text("h1", root_domain)
        root_id = _extract_root_id(browser._page.url)

        try:
            # Add grant.
            await _add_grant_for_demo_user(browser, root_id)

            await browser.goto(settings.url(f"/admin/domain-roots/{root_id}/grants"))
            body = await browser.text("body")
            assert "demo-user" in body
            assert "Active" in body

            # Revoke grant.
            await _revoke_grant_for_demo_user(browser, root_id)

            await browser.goto(settings.url(f"/admin/domain-roots/{root_id}/grants"))
            body = await browser.text("body")
            assert "demo-user" in body
            assert "Revoked" in body or "Inactive" in body
        finally:
            await _delete_domain_root(browser, root_id)


class _AccountBrowserFactory:
    @staticmethod
    async def new(session_manager, session_id: str) -> Browser:
        handle = await session_manager.create_session(role="account", session_id=session_id)
        browser = Browser(handle.page)
        await browser.reset()
        await workflows.ensure_user_dashboard(browser)
        return browser


async def test_domain_root_grant_controls_account_realm_request(session_manager, active_profile):
    if not active_profile.allow_writes:
        pytest.skip("profile is read-only")

    admin_handle = await session_manager.admin_session()
    admin = Browser(admin_handle.page)
    await admin.reset()

    user = await _AccountBrowserFactory.new(session_manager, "acct_grants")

    suffix = secrets.token_hex(4)
    root_domain = f"grants-elig-{suffix}.example.test"

    # Create private domain root as admin.
    await admin.goto(settings.url("/admin/domain-roots/new"))
    await admin.wait_for_text("main h1", "Create")

    backend_id = await _pick_backend_service_id(admin)
    if not backend_id:
        pytest.skip("No backend services available to create a domain root")

    await admin.fill("#root_domain", root_domain)
    await admin.fill("#dns_zone", root_domain)
    await admin.select("#backend_service_id", backend_id)
    await admin.select("#visibility", "private")
    await admin.submit("#domainRootForm")

    await admin.wait_for_text("h1", root_domain)
    root_id = _extract_root_id(admin._page.url)

    try:
        # Without a grant, user should not see the private root as an option.
        await user.goto(settings.url("/account/realms/request"), wait_until="domcontentloaded")
        body_before = await user.text("body")
        assert root_domain not in body_before

        # Add grant.
        await _add_grant_for_demo_user(admin, root_id)

        # User should now see the root.
        await user.goto(settings.url("/account/realms/request"), wait_until="domcontentloaded")
        body_after = await user.text("body")
        assert root_domain in body_after

        # Revoke grant.
        await _revoke_grant_for_demo_user(admin, root_id)

        await user.goto(settings.url("/account/realms/request"), wait_until="domcontentloaded")
        body_revoked = await user.text("body")
        assert root_domain not in body_revoked

        # Also verify POST is rejected.
        csrf = await user.get_attribute("form input[name='csrf_token']", "value")
        assert csrf
        resp = await user.request_post_form(
            settings.url("/account/realms/request"),
            {
                "csrf_token": csrf,
                "domain_root_id": str(root_id),
                "subdomain": "",
                "realm_type": "host",
                "record_types": "A",
                "operations": "read",
            },
        )
        assert resp["status"] == 200
        post_body = resp.get("text") or ""
        assert "you do not have access to this dns zone" in post_body.lower()
    finally:
        await _delete_domain_root(admin, root_id)

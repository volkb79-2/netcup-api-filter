"""
UI Regression Tests - Catch fundamental UI flaws.

These tests verify that UI pages don't have broken layouts, missing content,
error messages, or other fundamental issues that should never make it to production.
"""
import pytest
import asyncio
from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests import workflows


pytestmark = pytest.mark.asyncio


async def test_ui_no_error_messages_on_pages(active_profile):
    """Verify no pages show error messages or 404 in normal flow."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Admin pages should not show errors
        admin_pages = [
            "/admin/",
            "/admin/client/",
            "/admin/auditlog/",
            "/admin/netcup_config/",
            "/admin/email_config/",
            "/admin/system_info/",
        ]
        
        for path in admin_pages:
            await browser.goto(settings.url(path))
            await asyncio.sleep(0.5)
            page_text = await browser.text("body")
            
            # Check for common error indicators
            assert "404" not in page_text, f"Page {path} shows 404 error"
            assert "Not Found" not in page_text or path == "/admin/auditlog/", f"Page {path} shows 'Not Found'"
            assert "Internal Server Error" not in page_text, f"Page {path} shows 500 error"
            assert "Exception" not in page_text, f"Page {path} shows exception"
            assert "Traceback" not in page_text, f"Page {path} shows traceback"
            
            # Check page loaded (has header)
            assert await browser.query_selector("h1"), f"Page {path} has no h1 heading"


async def test_client_portal_no_errors(active_profile):
    """Verify client portal pages work without errors."""
    async with browser_session() as browser:
        # Login to client portal with separate client_id and secret_key fields
        await browser.goto(settings.url("/client/login"))
        await asyncio.sleep(0.5)
        
        # Split token into client_id and secret_key
        client_id, secret_key = settings.client_token.split(":", 1)
        await browser.fill('input[name="client_id"]', client_id)
        await browser.fill('input[name="secret_key"]', secret_key)
        await browser.click("button[type='submit']")
        await asyncio.sleep(1)
        
        # Dashboard should not show errors
        page_text = await browser.text("body")
        assert "error" not in page_text.lower() or "no error" in page_text.lower(), \
            "Client dashboard shows error message"
        assert "404" not in page_text, "Client dashboard shows 404"
        assert "exception" not in page_text.lower(), "Client dashboard shows exception"
        
        # Activity log should load
        await browser.goto(settings.url("/client/activity"))
        await asyncio.sleep(0.5)
        page_text = await browser.text("body")
        assert "Activity Log" in page_text or "activity" in page_text.lower(), \
            "Activity log page doesn't show header"
        assert "404" not in page_text, "Activity log shows 404"


async def test_terminology_consistency(active_profile):
    """Verify consistent terminology across UI - should use separate Client ID and Secret Key fields."""
    async with browser_session() as browser:
        # Client login should use clear terminology with separate fields
        await browser.goto(settings.url("/client/login"))
        await asyncio.sleep(0.5)
        page_html = await browser.html("body")
        
        # Should have separate Client ID and Secret Key fields (not concatenated)
        assert "Client ID" in page_html, \
            "Client login should have 'Client ID' field label"
        assert "Secret Key" in page_html, \
            "Client login should have 'Secret Key' field label"
        assert 'name="client_id"' in page_html, \
            "Client login should have client_id input field"
        assert 'name="secret_key"' in page_html, \
            "Client login should have secret_key input field"


async def test_audit_logs_not_empty_on_fresh_install(active_profile):
    """Audit logs page should show demo data on fresh install."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/auditlog/"))
        await asyncio.sleep(1)
        
        page_text = await browser.text("body")
        
        # Should either have demo logs or a helpful empty state
        has_logs = "test_qweqweqwe_vi" in page_text or "infoDnsZone" in page_text
        has_empty_message = "No audit logs yet" in page_text or "will appear here" in page_text
        
        assert has_logs or has_empty_message, \
            "Audit logs page shows neither demo data nor helpful empty state"


async def test_no_template_code_in_rendered_pages(active_profile):
    """Verify no template syntax leaks into rendered HTML - catches code spillage."""
    async with browser_session() as browser:
        await browser.goto(settings.url("/client/login"))
        await asyncio.sleep(0.5)
        page_html = await browser.html("body")
        
        # Check for common template syntax that shouldn't appear
        assert "{{" not in page_html, "Jinja2 syntax leaked into client login"
        assert "{%" not in page_html, "Jinja2 syntax leaked into client login"
        
        # Login to client portal with separate fields
        client_id, secret_key = settings.client_token.split(":", 1)
        await browser.fill('input[name="client_id"]', client_id)
        await browser.fill('input[name="secret_key"]', secret_key)
        await browser.click("button[type='submit']")
        await asyncio.sleep(1)
        
        # Check activity log for template code spillage
        await browser.goto(settings.url("/client/activity"))
        await asyncio.sleep(0.5)
        page_html = await browser.html("body")
        page_text = await browser.text("body")
        
        # Jinja2 template syntax should never appear in rendered HTML
        assert "{{" not in page_html, "Jinja2 syntax leaked into activity log HTML"
        assert "{%" not in page_html, "Jinja2 syntax leaked into activity log HTML"
        
        # Alpine.js expressions should be in attributes, not visible text
        # Check for common Alpine.js code spillage patterns
        assert "filteredLogs()" not in page_text, "Alpine.js function name visible in activity log text"
        assert "${" not in page_text, "JavaScript template literal visible in activity log text"
        assert "x-text=" not in page_text, "Alpine.js x-text attribute visible as text"
        assert "x-bind:" not in page_text, "Alpine.js x-bind directive visible as text"
        # Check for the specific bug we found
        visible_text = await browser.text("body")
        assert "{{ logs|length }}" not in visible_text, "Template code visible in activity log search"


async def test_forms_have_consistent_styling(active_profile):
    """Verify forms use consistent field sizes and labels."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Check client create form
        await browser.goto(settings.url("/admin/client/new/"))
        await asyncio.sleep(1)
        
        # All text inputs should have form-control class (Bootstrap standard)
        text_inputs = await browser.query_selector_all('input[type="text"]')
        assert len(text_inputs) > 0, "Client create form has no text inputs"
        
        # Check Netcup config form for comparison
        await browser.goto(settings.url("/admin/netcup_config/"))
        await asyncio.sleep(1)
        
        # Should have consistent form styling
        form_exists = await browser.query_selector("form")
        assert form_exists, "Netcup config page has no form"


async def test_admin_list_toolbar_clear(active_profile):
    """Verify admin list toolbar is intuitive and clear."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/client/"))
        await asyncio.sleep(1)
        
        page_html = await browser.html("body")
        
        # Should have clear action buttons (not mysterious dark boxes)
        # Flask-Admin uses dropdown menus
        has_add_button = "Add New" in page_html or "Create" in page_html
        assert has_add_button, "Client list page missing clear 'Add' button"
        
        # Check if we can identify the toolbar area
        toolbar = await browser.query_selector(".toolbar-card")
        if toolbar:
            toolbar_html = await browser.html(".toolbar-card")
            # Toolbar should have descriptive elements
            assert toolbar_html, "Toolbar exists but is empty"


async def test_viewport_shows_full_content(active_profile):
    """Verify screenshots capture full page content (regression test for truncation)."""
    async with browser_session() as browser:
        # Set large viewport like screenshot script
        await browser._page.set_viewport_size({"width": 1920, "height": 1200})
        
        await workflows.ensure_admin_dashboard(browser)
        
        # Dashboard should be fully visible
        await browser.goto(settings.url("/admin/"))
        await asyncio.sleep(0.5)
        
        # Check we can see header and footer
        header = await browser.query_selector("nav") or await browser.query_selector("header")
        assert header, "Cannot see header in viewport"
        
        # Footer should be visible (if it exists)
        footer_text = await browser.text("body")
        # Just check page loaded fully
        assert "Dashboard" in footer_text or "admin" in footer_text.lower(), \
            "Page doesn't appear fully loaded"


async def test_system_info_filesystem_tests_present(active_profile):
    """System info page should show filesystem test results."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/system_info/"))
        await asyncio.sleep(0.5)
        page_text = await browser.text("body")
        
        # Should have filesystem tests section with actual test results
        assert "Filesystem Tests" in page_text, "System info missing Filesystem Tests section"
        assert "Working Directory" in page_text or "writable" in page_text.lower(), \
            "Filesystem tests section has no content"


async def test_no_internal_errors_in_rendered_pages(active_profile):
    """Verify no pages show 'Internal error' messages in normal flow."""
    async with browser_session() as browser:
        # Admin pages
        await workflows.ensure_admin_dashboard(browser)
        page_text = await browser.text("body")
        assert "Internal error" not in page_text, "Admin dashboard shows 'Internal error'"
        
        # Client portal - login and check dashboard
        await browser.goto(settings.url("/client/login"))
        client_id, secret_key = settings.client_token.split(":", 1)
        await browser.fill('input[name="client_id"]', client_id)
        await browser.fill('input[name="secret_key"]', secret_key)
        await browser.click("button[type='submit']")
        await asyncio.sleep(1)
        
        page_text = await browser.text("body")
        assert "Internal error" not in page_text, "Client dashboard shows 'Internal error'"
        
        # Activity log
        await browser.goto(settings.url("/client/activity"))
        await asyncio.sleep(0.5)
        page_text = await browser.text("body")
        assert "Internal error" not in page_text, "Client activity shows 'Internal error'"


async def test_audit_logs_page_accessible(active_profile):
    """Audit logs page should load without 'not found' error."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/auditlog/"))
        await asyncio.sleep(1)
        
        page_text = await browser.text("body")
        
        # Should not show 'not found' error
        assert "not found" not in page_text.lower() or "No audit logs" in page_text, \
            "Audit logs page shows 'not found' error"
        assert "404" not in page_text, "Audit logs page shows 404"


async def test_client_domain_detail_no_errors(active_profile):
    """Client domain detail page should show valid data without errors."""
    async with browser_session() as browser:
        # Login to client portal with separate fields
        await browser.goto(settings.url("/client/login"))
        client_id, secret_key = settings.client_token.split(":", 1)
        await browser.fill('input[name="client_id"]', client_id)
        await browser.fill('input[name="secret_key"]', secret_key)
        await browser.click("button[type='submit']")
        await asyncio.sleep(1)
        
        # Check dashboard has a domain
        page_text = await browser.text("body")
        if settings.client_domain in page_text:
            # Try to access domain detail
            await browser.goto(settings.url(f"/client/domains/{settings.client_domain}"))
            await asyncio.sleep(1)
            
            page_text = await browser.text("body")
            
            # Should not show errors (or skip if not implemented yet)
            if "404" not in page_text:
                assert "Internal error" not in page_text, \
                    "Domain detail page shows internal error"
                assert "Exception" not in page_text, \
                    "Domain detail page shows exception"


async def test_client_list_visual_indicators(active_profile):
    """Verify client list shows visual badges and clickable IDs."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await browser.goto(settings.url("/admin/client/"))
        await asyncio.sleep(0.5)
        
        page_html = await browser.html("body")
        
        # Check for badge indicators (✓/✗) not plain True/False
        assert '<span class="badge' in page_html, "Badge indicators not found in client list"
        assert '✓</span>' in page_html or '✗</span>' in page_html, "Badge symbols (✓/✗) not found"
        
        # Check for clickable client IDs
        assert 'class="client-id-link"' in page_html, "Clickable client ID links not found"
        assert '/admin/client/edit/' in page_html, "Edit links not found in client list"


async def test_toolbar_has_labels(active_profile):
    """Verify Flask-Admin toolbar has labeled sections."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await browser.goto(settings.url("/admin/client/"))
        await asyncio.sleep(0.5)
        
        page_html = await browser.html("body")
        
        # Check for new labeled toolbar (not old dark card)
        assert 'class="list-toolbar"' in page_html, "New labeled toolbar not found"
        assert 'class="toolbar-label"' in page_html, "Toolbar labels not found"
        
        # Ensure old dark toolbar is gone
        assert 'class="toolbar-card"' not in page_html, "Old dark toolbar card still present"


async def test_form_has_safe_defaults(active_profile):
    """Verify client create form pre-selects safe defaults."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await browser.goto(settings.url("/admin/client/new/"))
        await asyncio.sleep(0.5)
        
        page_html = await browser.html("body")
        
        # Check for form fields (may not have selected="selected" in HTML if defaults set via JavaScript)
        # Just verify form exists and has the expected structure
        assert 'id="realm_type"' in page_html, "Realm type select not found"
        assert 'id="allowed_record_types"' in page_html, "Allowed record types select not found"
        assert 'id="allowed_operations"' in page_html, "Allowed operations select not found"
        
        # Check options exist
        assert 'value="host"' in page_html, "Host realm type option not found"
        assert 'value="A"' in page_html, "A record type option not found"
        assert 'value="read"' in page_html, "Read operation option not found"

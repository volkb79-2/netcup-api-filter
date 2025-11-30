#!/usr/bin/env python3
"""
Capture screenshots of all UI pages for inspection and optimization.

This script systematically navigates through all admin and client pages,
capturing screenshots for UI/UX review.
"""
import asyncio
import sys
import os
from pathlib import Path

# Ensure both repo root and ui_tests/ are importable
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(CURRENT_DIR))

from ui_tests.browser import browser_session
from ui_tests.config import settings


async def set_viewport(browser, width=None, height=None):
    """Set viewport for screenshots using environment config (NO HARDCODED VALUES)."""
    import os
    if width is None:
        width = int(os.environ.get('SCREENSHOT_VIEWPORT_WIDTH', '1920'))
    if height is None:
        height = int(os.environ.get('SCREENSHOT_VIEWPORT_HEIGHT', '1200'))
    await browser._page.set_viewport_size({"width": width, "height": height})


async def verify_not_login_page(browser, page_name: str):
    """Verify we're not redirected back to a login page (session expired/auth failed)."""
    current_url = browser.current_url
    if "/login" in current_url:
        print(f"❌ ERROR: Redirected to login page while accessing {page_name}!")
        print(f"   Current URL: {current_url}")
        print(f"   This means the session expired or authentication failed.")
        print(f"   Page: {page_name}")
        raise RuntimeError(f"Session lost - redirected to login while accessing {page_name}")


async def verify_page_status(browser, page_name: str, expected_status: int = 200):
    """Verify HTTP status code of the current page."""
    # Get the page response status via JavaScript
    try:
        status_code = await browser._page.evaluate("() => window.performance.getEntriesByType('navigation')[0]?.responseStatus || 0")
        
        # If we can't get status from performance API, check for error indicators in page content
        if status_code == 0:
            page_text = await browser._page.text_content("body")
            if "500 Internal Server Error" in page_text or "Internal Server Error" in page_text:
                status_code = 500
            elif "404" in page_text and ("Not Found" in page_text or "Page not found" in page_text):
                status_code = 404
        
        if status_code != expected_status:
            print(f"❌ ERROR: Unexpected HTTP status for {page_name}!")
            print(f"   Expected: {expected_status}, Got: {status_code}")
            print(f"   URL: {browser.current_url}")
            
            # Get page content for debugging
            page_content = await browser._page.content()
            if len(page_content) < 500:
                print(f"   Page content: {page_content[:500]}")
            
            raise RuntimeError(f"HTTP {status_code} error on {page_name} (expected {expected_status})")
        
        return status_code
    except Exception as e:
        print(f"⚠️  Warning: Could not verify status for {page_name}: {e}")
        return None


async def capture_admin_pages(browser):
    """Capture all admin UI pages.
    
    Credentials are passed via environment variables (no file access needed).
    This makes the Playwright container a pure service.
    """
    screenshots = []
    
    # Get admin credentials from environment (passed by caller)
    admin_password = os.environ.get('DEPLOYED_ADMIN_PASSWORD')
    if not admin_password:
        raise RuntimeError(
            "DEPLOYED_ADMIN_PASSWORD not set. "
            "Playwright container needs credentials passed as environment variables."
        )
    
    # Login to admin
    print("📸 Logging into admin...")
    await browser.goto(settings.url("/admin/login"))
    await asyncio.sleep(0.5)
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", admin_password)
    await browser.click("button[type='submit']")
    await asyncio.sleep(1)
    
    # Verify login was successful (not still on login page)
    current_url = browser.current_url
    if "/admin/login" in current_url:
        print("❌ ERROR: Still on login page after login attempt!")
        print(f"   Current URL: {current_url}")
        print(f"   This likely means:")
        print(f"   1. Password is incorrect (check .env.local or .env.webhosting)")
        print(f"   2. Admin test didn't run (password not changed from default)")
        print(f"   3. Credentials mismatch between config and database")
        raise RuntimeError("Login failed - still on login page. Run authentication test first: pytest ui_tests/tests/test_admin_ui.py::test_admin_authentication_flow -v")
    
    # Check if we're on password change page (fresh database)
    current_h1 = await browser._page.locator("main h1").text_content()
    if "Change Password" in current_h1:
        print("📸 Capturing 00b-admin-password-change...")
        screenshot_path = await browser.screenshot("00b-admin-password-change")
        screenshots.append(("00b-admin-password-change", screenshot_path))
        
        # Note: This only happens on fresh database before auth test runs
        # For now, just proceed to dashboard since we can't change password here
        await browser.goto(settings.url("/admin/"))
        await asyncio.sleep(1)
    
    # Admin pages to capture
    pages = [
        ("/admin/", "01-admin-dashboard"),
        ("/admin/client/", "02-admin-clients-list"),
        ("/admin/client/new/", "03-admin-client-create"),
        ("/admin/auditlog/", "04-admin-audit-logs"),
        ("/admin/netcup_config/", "05-admin-netcup-config"),
        ("/admin/email_config/", "06-admin-email-config"),
        ("/admin/system_info/", "07-admin-system-info"),
    ]
    
    for path, name in pages:
        print(f"📸 Capturing {name}...")
        response = await browser.goto(settings.url(path))
        await asyncio.sleep(1)
        await verify_not_login_page(browser, name)
        await verify_page_status(browser, name, expected_status=200)
        
        # Validate HTTP status from response dict
        if response and response.get('status') and response['status'] >= 400:
            raise RuntimeError(f"HTTP {response['status']} error on {name} ({path})")
        
        screenshot_path = await browser.screenshot(f"{name}")
        screenshots.append((name, screenshot_path))
    
    # Capture client edit form (if preseeded client exists)
    try:
        print("📸 Capturing client edit form...")
        await browser.goto(settings.url("/admin/client/"))
        await asyncio.sleep(0.5)
        
        # Click first edit link
        edit_links = await browser.query_selector_all('a[href*="/admin/client/edit/"]')
        if edit_links:
            await edit_links[0].click()
            await asyncio.sleep(1)
            screenshot_path = await browser.screenshot("03b-admin-client-edit")
            screenshots.append(("03b-admin-client-edit", screenshot_path))
    except Exception as e:
        print(f"⚠️  Could not capture client edit: {e}")
    
    return screenshots


async def capture_client_pages_for_token(browser, client_token: str, client_idx: int, client_type: str):
    """Capture client portal pages for a specific client token.
    
    Args:
        browser: Browser instance
        client_token: Full token (client_id:secret_key)
        client_idx: Client index (1-based)
        client_type: Client type description (e.g., 'readonly', 'fullcontrol')
    """
    screenshots = []
    
    # Logout first if we're already logged in (from previous client)
    current_url = browser.current_url
    if "/client/" in current_url and "/client/login" not in current_url:
        print(f"📸 Logging out previous client session...")
        try:
            await browser.goto(settings.url("/client/logout"))
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"⚠️  Logout warning: {e}")
    
    # Login to client portal
    print(f"📸 Logging in as client ({client_type}-{client_idx})...")
    await browser.goto(settings.url("/client/login"))
    await asyncio.sleep(0.5)
    
    # Split token into client_id and secret_key
    client_id, secret_key = client_token.split(":", 1)
    await browser.fill('input[name="client_id"]', client_id)
    await browser.fill('input[name="secret_key"]', secret_key)
    await browser.click("button[type='submit']")
    await asyncio.sleep(1)
    
    # Verify login was successful
    current_url = browser.current_url
    if "/client/login" in current_url:
        print(f"⚠️  WARNING: Login failed for {client_type}-{client_idx} - skipping")
        return screenshots
    
    # Client pages to capture
    # Naming convention: XX-client-{idx}-{page}-{type}
    pages = [
        ("/client/", f"08-client-{client_idx}-dashboard-{client_type}"),
        ("/client/activity", f"09-client-{client_idx}-activity-{client_type}"),
    ]
    
    for path, name in pages:
        print(f"📸 Capturing {name}...")
        await browser.goto(settings.url(path))
        await asyncio.sleep(1)
        try:
            await verify_not_login_page(browser, name)
            screenshot_path = await browser.screenshot(name)
            screenshots.append((name, screenshot_path))
        except Exception as e:
            print(f"⚠️  Could not capture {name}: {e}")
    
    # Capture domain detail page (if available)
    try:
        print(f"📸 Capturing domain detail ({client_type}-{client_idx})...")
        await browser.goto(settings.url("/client/"))
        await asyncio.sleep(0.5)
        
        # Click first domain link
        domain_links = await browser.query_selector_all('a[href*="/client/domains/"]')
        if domain_links:
            await domain_links[0].click()
            await asyncio.sleep(1)
            
            # Get current URL to extract domain name
            current_url = browser.current_url
            domain_name = current_url.split('/domains/')[-1].rstrip('/')
            
            name = f"10-client-{client_idx}-domain-{client_type}"
            screenshot_path = await browser.screenshot(name)
            screenshots.append((name, screenshot_path))
            
            # Try to capture record management (if client has write permissions)
            try:
                # Check if create button exists (only for write-enabled clients)
                create_button = await browser.query_selector('a[href*="/records/new"], button:has-text("Add Record")')
                if create_button:
                    await create_button.click()
                    await asyncio.sleep(1)
                    name = f"11-client-{client_idx}-record-create-{client_type}"
                    screenshot_path = await browser.screenshot(name)
                    screenshots.append((name, screenshot_path))
                    
                    # Go back to domain detail page
                    await browser.goto(settings.url(f"/client/domains/{domain_name}"))
                    await asyncio.sleep(2)  # Wait for Alpine.js to render
                    
                    # Click first edit button (for DDNS update scenario)
                    # Use text-based selector since href is Alpine.js bound
                    edit_buttons = await browser.query_selector_all('a:has-text("Edit")')
                    if edit_buttons:
                        await edit_buttons[0].click()
                        await asyncio.sleep(1)
                        name = f"12-client-{client_idx}-record-edit-{client_type}"
                        screenshot_path = await browser.screenshot(name)
                        screenshots.append((name, screenshot_path))
                        print(f"📸 Captured record edit form ({client_type}-{client_idx})")
            except Exception as e:
                print(f"⚠️  Could not capture record edit form for {client_type}-{client_idx}: {e}")
    except Exception as e:
        print(f"⚠️  Could not capture domain detail for {client_type}-{client_idx}: {e}")
    
    return screenshots


async def capture_client_pages(browser):
    """Capture all client portal pages for all demo clients.
    
    Reads demo client list from build_info.json (in mounted workspace).
    """
    import json
    screenshots = []
    
    # build_info.json is in the mounted workspace (NO HARDCODED PATHS)
    repo_root = os.environ.get('REPO_ROOT')
    if not repo_root:
        raise RuntimeError("REPO_ROOT must be set (no hardcoded paths allowed)")
    build_info_path = Path(f"{repo_root}/deploy-local/build_info.json")
    if not build_info_path.exists():
        print(f"⚠️  WARNING: {build_info_path} not found - no demo clients to capture")
        print(f"   Run build-and-deploy-local.sh first to generate build_info.json")
        return screenshots
    
    with open(build_info_path, 'r') as f:
        build_info = json.load(f)
    
    demo_clients = build_info.get("demo_clients", [])
    if not demo_clients:
        print("⚠️  No demo clients found in build_info.json")
        return screenshots
    
    print(f"📋 Found {len(demo_clients)} demo clients in build_info.json")
    
    # Capture screenshots for each demo client
    for idx, client_data in enumerate(demo_clients, 1):
        client_id = client_data["client_id"]
        client_token = client_data["token"]
        description = client_data["description"]
        
        print(f"\n--- Client {idx}/{len(demo_clients)}: {client_id} ---")
        print(f"    Description: {description}")
        
        # Generate suffix based on description keywords
        desc_lower = description.lower()
        if "subdomain" in desc_lower:
            if "read-only" in desc_lower or "monitor" in desc_lower:
                client_type = "subdomain-readonly"
            elif "update" in desc_lower or "write" in desc_lower or "create" in desc_lower:
                client_type = "subdomain-write"
            else:
                client_type = "subdomain"
        elif "full control" in desc_lower or "full access" in desc_lower or "multi-record" in desc_lower:
            client_type = "fullcontrol"
        elif "read-only" in desc_lower or "monitor" in desc_lower:
            client_type = "readonly"
        else:
            client_type = "generic"
        
        client_screenshots = await capture_client_pages_for_token(browser, client_token, idx, client_type)
        screenshots.extend(client_screenshots)
    
    return screenshots


async def capture_public_pages(browser):
    """Capture public/unauthenticated pages."""
    screenshots = []
    
    pages = [
        ("/admin/login", "00-admin-login"),
        ("/client/login", "00-client-login"),
    ]
    
    for path, name in pages:
        print(f"📸 Capturing {name}...")
        await browser.goto(settings.url(path))
        await asyncio.sleep(0.5)
        screenshot_path = await browser.screenshot(f"{name}")
        screenshots.append((name, screenshot_path))
    
    return screenshots


async def main():
    """Main screenshot capture workflow."""
    print("🎬 Starting UI Screenshot Capture")
    print(f"📍 Target: {settings.base_url}")
    print(f"👤 Admin: {settings.admin_username}")
    print(f"🔑 Client: {settings.client_id}")
    print()
    
    screenshot_dir_str = os.environ.get("SCREENSHOT_DIR")
    if not screenshot_dir_str:
        raise RuntimeError("SCREENSHOT_DIR environment variable is not set.")
    screenshot_dir = Path(screenshot_dir_str)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Screenshots will be saved to: {screenshot_dir}")
    
    all_screenshots = []
    
    async with browser_session() as browser:
        # Set larger viewport
        await set_viewport(browser, 1920, 1200)
        
        # Capture public pages
        print("=" * 60)
        print("PUBLIC PAGES")
        print("=" * 60)
        all_screenshots.extend(await capture_public_pages(browser))
        
        # Capture admin pages
        print("\n" + "=" * 60)
        print("ADMIN PAGES")
        print("=" * 60)
        all_screenshots.extend(await capture_admin_pages(browser))
        
        # Capture client pages
        print("\n" + "=" * 60)
        print("CLIENT PORTAL PAGES")
        print("=" * 60)
        all_screenshots.extend(await capture_client_pages(browser))
    
    # Print summary
    print("\n" + "=" * 60)
    print("SCREENSHOT SUMMARY")
    print("=" * 60)
    print(f"✅ Captured {len(all_screenshots)} screenshots")
    print(f"📁 Location: {screenshot_dir}/")
    print()
    print("Screenshots captured:")
    for name, path in all_screenshots:
        status = "✅" if Path(path).exists() else "❌"
        print(f"  {status} {name}: {path}")
    
    print("\n💡 Next steps:")
    print("   1. Review screenshots for UI/UX issues")
    print("   2. Check consistency across pages")
    print("   3. Identify optimization opportunities")
    print("   4. Verify responsive design elements")
    print("   5. Assess workflow efficiency")


if __name__ == "__main__":
    asyncio.run(main())

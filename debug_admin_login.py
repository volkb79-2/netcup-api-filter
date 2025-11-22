#!/usr/bin/env python3
"""Debug script to check what happens after admin login and password change"""

import asyncio
import os
import sys
sys.path.insert(0, '/workspaces/netcup-api-filter')

from ui_tests.browser import browser_session
from ui_tests.config import settings

async def debug_admin_login():
    # Set up settings for live testing
    os.environ['UI_BASE_URL'] = 'https://naf.vxxu.de'
    os.environ['UI_MCP_URL'] = 'http://172.17.0.1:8765/mcp'
    os.environ['UI_ADMIN_USERNAME'] = 'admin'
    os.environ['UI_ADMIN_PASSWORD'] = 'admin'
    os.environ['UI_ADMIN_NEW_PASSWORD'] = 'Admin123!'
    os.environ['PLAYWRIGHT_HEADLESS'] = 'true'

    # Reload settings after setting env vars
    from ui_tests.config import UiTestConfig
    global settings
    settings = UiTestConfig()

    async with browser_session() as browser:
        print("1. Going to admin login page...")
        await browser.goto(settings.url("/admin/login"))

        print("2. Filling login form...")
        await browser.fill("#username", settings.admin_username)
        await browser.fill("#password", settings.admin_password)

        print("3. Submitting login form...")
        response = await browser.click("button[type='submit']")
        destination = response.get("url", "")
        print(f"   Redirected to: {destination}")

        print("4. Checking page content after login...")
        current_url = browser.current_url
        print(f"   Current URL: {current_url}")

        main_h1 = ""
        try:
            main_h1 = await browser.text("main h1")
            print(f"   Main H1: '{main_h1}'")
        except:
            print("   No main h1 found")

        try:
            page_title = await browser.text("title")
            print(f"   Page title: '{page_title}'")
        except:
            print("   No title found")

        # Check for flash messages or errors
        try:
            flash_messages = await browser.text(".flash-messages")
            print(f"   Flash messages: '{flash_messages}'")
        except:
            print("   No flash messages found")

        # Check if login was successful by looking for navigation or dashboard elements
        try:
            nav_links = await browser.text("nav a")
            print(f"   Navigation links: '{nav_links[:200]}...'")
        except:
            print("   No navigation links found")

        # Check if we're still on login page
        if current_url and "login" in current_url.lower() or "Admin Login" in main_h1:
            print("   Still on login page - login may have failed")
            # Try to see what's in the form or if there are errors
            try:
                form_errors = await browser.text(".invalid-feedback")
                print(f"   Form errors: '{form_errors}'")
            except:
                print("   No form errors found")
        else:
            print("   Appears to have logged in successfully")

        # Check if we need to change password
        try:
            current_main_h1 = await browser.text("main h1")
        except:
            current_main_h1 = ""

        if "change-password" in destination or "Change Password" in current_main_h1:
            print("5. Password change required, filling form...")
            await browser.fill("#current_password", settings.admin_password)
            if settings.admin_new_password:
                await browser.fill("#new_password", settings.admin_new_password)
                await browser.fill("#confirm_password", settings.admin_new_password)

            print("6. Submitting password change...")
            await browser.click("button[type='submit']")

            print("7. Checking page content after password change...")
            await asyncio.sleep(2)  # Wait a bit for redirect

            current_url = browser.current_url
            print(f"   Current URL after password change: {current_url}")

            try:
                main_h1 = await browser.text("main h1")
                print(f"   Main H1 after password change: '{main_h1}'")
            except:
                print("   No main h1 after password change")

            try:
                page_title = await browser.text("title")
                print(f"   Page title after password change: '{page_title}'")
            except:
                print("   No title after password change")

            # Get all h1 elements
            try:
                all_h1 = await browser.text("h1")
                print(f"   All H1 elements: '{all_h1}'")
            except:
                print("   No h1 elements found")

            # Get body text
            try:
                body_text = await browser.text("body")
                print(f"   Body contains 'Dashboard': {'Dashboard' in body_text}")
            except:
                print("   No body text found")

            # Check for specific elements
            try:
                dashboard_text = await browser.text("h1.mb-4")
                print(f"   Dashboard H1 with class: '{dashboard_text}'")
            except:
                print("   No H1 with class mb-4 found")

        print("8. Done debugging")

if __name__ == "__main__":
    asyncio.run(debug_admin_login())
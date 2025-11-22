#!/usr/bin/env python3
"""Debug script to check admin dashboard content after login."""

import asyncio
import sys
import os

# Add the project root to the path
sys.path.insert(0, '/workspaces/netcup-api-filter')

from ui_tests.browser import browser_session
from ui_tests.config import settings

async def debug_admin_dashboard():
    """Debug the admin dashboard content."""
    async with browser_session() as browser:
        try:
            # Go to login page
            print("Going to admin login page...")
            await browser.goto(settings.url("/admin/login"))
            
            # Check initial page content
            print("Current URL:", browser.current_url)
            print("Current title:", browser.current_title)
            
            login_form = await browser.html("body")
            print("Login form present:", "username" in login_form and "password" in login_form)
            
            # Login
            print("Logging in...")
            await browser.fill("#username", settings.admin_username)
            await browser.fill("#password", settings.admin_password)
            response = await browser.click("button[type='submit']")
            destination = response.get("url", "")
            print("Login response URL:", destination)
            
            # Wait a moment and check again
            await asyncio.sleep(1)
            current_url_after_click = browser.current_url
            print("Current URL after click:", current_url_after_click)
            
            # Check for flash messages
            try:
                flash_messages = await browser.text(".flash-messages")
                print("Flash messages:", repr(flash_messages))
            except Exception as e:
                print("No flash messages found:", e)
            
            # Check if password change is required
            h1_after_login = await browser.text("main h1")
            print("H1 after login:", repr(h1_after_login))
            
            if "change-password" in destination or (current_url_after_click and "change-password" in current_url_after_click):
                print("Password change required - redirect detected")
            elif "Change Password" in h1_after_login:
                print("Password change required - on change password page")
            else:
                print("No password change required")
            
            # Wait a bit more for redirect
            await asyncio.sleep(2)
            
            # Check current URL and content
            print("Current URL after login:", browser.current_url)
            print("Page title after login:", browser.current_title)
            
            # Get all h1 text by trying different selectors
            try:
                h1_text = await browser.text("h1")
                print("H1 text:", repr(h1_text))
            except Exception as e:
                print("Error getting h1 text:", e)
            
            # Check main element
            try:
                main_content = await browser.html("main")
                print("Main element content length:", len(main_content))
                main_h1 = await browser.text("main h1")
                print("Main h1 text:", repr(main_h1))
            except Exception as e:
                print("Error getting main content:", e)
            
            # Get full body text
            body_text = await browser.text("body")
            print("Body contains 'Dashboard':", "Dashboard" in body_text)
            print("Body contains 'Login':", "Login" in body_text)
            
            # Check for error messages
            if "error" in body_text.lower():
                print("ERROR found in body text!")
                # Print first 500 chars of body
                print("Body preview:", body_text[:500])
            
        except Exception as e:
            print(f"Error during debug: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_admin_dashboard())
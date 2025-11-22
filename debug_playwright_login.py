#!/usr/bin/env python3
"""Debug script to test Playwright login independently"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # Run headless in container
        context = await browser.new_context()
        page = await context.new_page()
        
        print("1. Navigating to login page...")
        await page.goto("https://naf.vxxu.de/admin/login")
        await page.wait_for_load_state("networkidle")
        
        print("2. Filling credentials...")
        await page.fill("#username", "admin")
        await page.fill("#password", "admin")
        
        print("3. Enabling request logging...")
        def log_request(request):
            print(f"   → {request.method} {request.url}")
            if request.method == "POST" and "/login" in request.url:
                print(f"      Headers: {request.headers}")
                print(f"      POST data: {request.post_data}")
        page.on("request", log_request)
        page.on("response", lambda response: print(f"   ← {response.status} {response.url}"))
        
        print("4. Submitting form...")
        await page.click("button[type='submit']")
        
        print("5. Waiting for navigation...")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        
        print(f"5. Current URL: {page.url}")
        h1 = await page.locator("main h1").inner_text()
        print(f"6. Current h1: {h1}")
        
        # Check for flash messages
        alerts = await page.locator(".alert").all()
        if alerts:
            print(f"7. Flash messages:")
            for alert in alerts:
                text = await alert.inner_text()
                print(f"   - {text.strip()}")
        
        print("\n7. Cookies:")
        cookies = await context.cookies()
        for cookie in cookies:
            print(f"   {cookie['name']}: {cookie['value'][:20]}...")
        
        print("\n8. Taking screenshot...")
        await page.screenshot(path="/tmp/playwright_debug.png")
        print("   Saved to /tmp/playwright_debug.png")
        
        input("\nPress Enter to close browser...")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Quick screenshot capture after handling password change"""
import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path("tmp/screenshots/ui-inspection")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1200})
        
        # Login and handle password change
        await page.goto("http://localhost:5100/admin/login")
        await page.fill("#username", "admin")
        await page.fill("#password", "admin")
        await page.click("button[type='submit']")
        await asyncio.sleep(1)
        
        h1 = await page.locator("h1").text_content()
        if "Change Password" in h1:
            print("📸 Capturing password change page...")
            await page.screenshot(path=str(OUTPUT_DIR / "00b-admin-password-change.png"))
            
            await page.fill("#current_password", "admin")
            await page.fill("#new_password", "TestPassword123!")
            await page.fill("#confirm_password", "TestPassword123!")
            await page.click("button[type='submit']")
            await asyncio.sleep(2)
        
        # Capture pages
        pages = [
            ("/admin/client/", "02-admin-clients-list"),
            ("/admin/client/new/", "03-admin-client-create"),
            ("/admin/auditlogview/", "04-admin-audit-logs"),
        ]
        
        for url, name in pages:
            print(f"📸 Capturing {name}...")
            await page.goto(f"http://localhost:5100{url}")
            await asyncio.sleep(1)
            await page.screenshot(path=str(OUTPUT_DIR / f"{name}.png"))
        
        print(f"\n✅ Captured {len(pages) + 1} screenshots in {OUTPUT_DIR}")
        await browser.close()

asyncio.run(capture())

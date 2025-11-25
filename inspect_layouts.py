#!/usr/bin/env python3
"""Inspect page layouts to identify styling issues"""
import asyncio
from playwright.async_api import async_playwright

async def inspect_pages():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1200})
        
        # Login
        await page.goto("http://localhost:5100/admin/login")
        await page.fill("#username", "admin")
        await page.fill("#password", "admin")
        await page.click("button[type='submit']")
        await asyncio.sleep(1)
        
        # Handle password change
        h1 = await page.locator("h1").text_content()
        if "Change Password" in h1:
            await page.fill("#current_password", "admin")
            await page.fill("#new_password", "TestPass123!")
            await page.fill("#confirm_password", "TestPass123!")
            await page.click("button[type='submit']")
            await asyncio.sleep(2)
        
        # Inspect Netcup Config (reference for good styling)
        print("=== NETCUP CONFIG (Reference) ===")
        await page.goto("http://localhost:5100/admin/netcup_config/")
        await asyncio.sleep(1)
        
        grid = await page.locator(".grid").count()
        sidebar = await page.locator(".grid > div").nth(1).inner_html()
        has_info_box = 'Security Note' in sidebar or 'Information' in sidebar
        
        print(f"Grid layout: {grid == 1}")
        print(f"Has info sidebar: {has_info_box}")
        
        # Inspect Email Config
        print("\n=== EMAIL CONFIG ===")
        await page.goto("http://localhost:5100/admin/email_config/")
        await asyncio.sleep(1)
        
        html = await page.content()
        test_email_location = "Test Email Settings" in html
        grid_email = await page.locator(".grid").count()
        
        print(f"Has grid layout: {grid_email == 1}")
        print(f"Has Test Email section: {test_email_location}")
        
        # Inspect Client Create
        print("\n=== CLIENT CREATE ===")
        await page.goto("http://localhost:5100/admin/client/new/")
        await asyncio.sleep(1)
        
        form_panel = await page.locator(".form-panel").count()
        has_sidebar = await page.locator(".grid").count()
        
        print(f"Has form-panel: {form_panel == 1}")
        print(f"Has grid/sidebar: {has_sidebar == 1}")
        
        # Inspect Client List
        print("\n=== CLIENT LIST ===")
        await page.goto("http://localhost:5100/admin/client/")
        await asyncio.sleep(1)
        
        toolbar_html = await page.locator(".list-toolbar").inner_html()
        print("Toolbar structure:")
        print(f"  Has search: {'search' in toolbar_html.lower()}")
        print(f"  Has filters: {'Add Filter' in toolbar_html}")
        print(f"  Has actions: {'Actions:' in toolbar_html}")
        
        await browser.close()

asyncio.run(inspect_pages())

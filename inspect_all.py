#!/usr/bin/env python3
"""Comprehensive page inspection"""
import asyncio
from playwright.async_api import async_playwright

async def inspect_all():
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
            print("✓ Password change page detected")
            icon_spacing = await page.locator(".alert-warning .flex-shrink-0.me-3").count()
            print(f"  Icon spacing (me-3): {icon_spacing == 1}")
            
            await page.fill("#current_password", "admin")
            await page.fill("#new_password", "Test123!")
            await page.fill("#confirm_password", "Test123!")
            await page.click("button[type='submit']")
            await asyncio.sleep(2)
        
        # Check Clients List
        print("\n✓ Clients List Page:")
        await page.goto("http://localhost:5100/admin/client/")
        await asyncio.sleep(1)
        
        eyebrow = await page.locator(".eyebrow").count()
        page_header = await page.locator(".page-header-with-actions").count()
        toolbar = await page.locator(".list-toolbar").count()
        search_in_toolbar = await page.locator(".list-toolbar input[name='search']").count()
        filter_panel = await page.locator(".filter-panel").count()
        edit_buttons = await page.locator(".list-buttons-column a").count()
        
        print(f"  Eyebrow 'Management': {eyebrow == 1}")
        print(f"  Custom page header: {page_header == 1}")
        print(f"  List toolbar: {toolbar == 1}")
        print(f"  Search in toolbar: {search_in_toolbar == 1}")
        print(f"  No empty filter-panel: {filter_panel == 0}")
        print(f"  Edit/Delete buttons: {edit_buttons > 0}")
        
        # Check Audit Logs  
        print("\n✓ Audit Logs Page:")
        await page.goto("http://localhost:5100/admin/auditlogview/")
        await asyncio.sleep(1)
        
        eyebrow = await page.locator(".eyebrow").count()
        toolbar = await page.locator(".list-toolbar").count()
        search_in_toolbar = await page.locator(".list-toolbar input[name='search']").count()
        filter_panel = await page.locator(".filter-panel").count()
        
        print(f"  Eyebrow 'Logs': {eyebrow == 1}")
        print(f"  List toolbar: {toolbar == 1}")
        print(f"  Search in toolbar: {search_in_toolbar == 1}")
        print(f"  No empty filter-panel: {filter_panel == 0}")
        
        # Check Client Create
        print("\n✓ Client Create Page:")
        await page.goto("http://localhost:5100/admin/client/new/")
        await asyncio.sleep(1)
        
        form_panel = await page.locator(".form-panel").count()
        centered = await page.locator(".d-flex.justify-content-center").count()
        
        print(f"  Form panel exists: {form_panel == 1}")
        print(f"  Centered layout: {centered == 1}")
        
        print("\n✅ All checks complete!")
        await browser.close()

asyncio.run(inspect_all())

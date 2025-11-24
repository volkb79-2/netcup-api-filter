#!/usr/bin/env python3
"""Quick script to fetch and display system info page"""
import asyncio
import sys
import os

sys.path.insert(0, '/workspace')
os.environ['UI_BASE_URL'] = 'https://naf.vxxu.de'
os.environ['PLAYWRIGHT_HEADLESS'] = 'true'

from ui_tests.browser import Browser
from ui_tests.playwright_client import PlaywrightClient
from ui_tests.config import settings
from ui_tests import workflows


async def main():
    async with PlaywrightClient(headless=True) as client:
        page = await client.new_page()
        browser = Browser(page)
        await browser.reset()
        
        # Login
        await workflows.ensure_admin_dashboard(browser)
        
        # Navigate to system info
        await browser.goto(settings.url("/admin/system_info/"))
        
        # Get the page content
        content = await browser.html("body")
        
        # Extract filesystem test results
        if "Filesystem Tests" in content:
            print("=" * 80)
            print("FILESYSTEM TEST RESULTS")
            print("=" * 80)
            
            # Try to extract the test results table/section
            import re
            # Look for pre-formatted or code blocks
            pre_blocks = re.findall(r'<pre[^>]*>(.*?)</pre>', content, re.DOTALL)
            for block in pre_blocks:
                # Remove HTML tags
                clean = re.sub(r'<[^>]+>', '', block)
                print(clean)
            
            # Look for dl/dt/dd definition lists
            dl_matches = re.findall(r'<dl[^>]*>(.*?)</dl>', content, re.DOTALL)
            for dl in dl_matches:
                clean = re.sub(r'<dt[^>]*>', '\n• ', dl)
                clean = re.sub(r'</dt>', ':', clean)
                clean = re.sub(r'<dd[^>]*>', ' ', clean)
                clean = re.sub(r'</dd>', '', clean)
                clean = re.sub(r'<[^>]+>', '', clean)
                print(clean)
        else:
            print("No filesystem test results found in page")
            print("Page title:", await browser.text("h1"))


if __name__ == "__main__":
    asyncio.run(main())

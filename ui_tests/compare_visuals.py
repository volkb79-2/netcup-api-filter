import asyncio
import os
from playwright.async_api import async_playwright

async def capture(name, base_url, username, password, output_dir):
    print(f"[{name}] Starting capture for {base_url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1200})
        
        print(f"[{name}] Navigating to {base_url}/admin/login")
        try:
            await page.goto(f"{base_url}/admin/login", timeout=30000)
        except Exception as e:
            print(f"[{name}] Failed to load login page: {e}")
            await browser.close()
            return

        print(f"[{name}] Logging in...")
        try:
            await page.fill("#username", username)
            await page.fill("#password", password)
            await page.click("button[type='submit']")
            await page.wait_for_load_state("networkidle")
        except Exception as e:
            print(f"[{name}] Login interaction failed: {e}")
            await browser.close()
            return
        
        # Check if login failed
        if "/login" in page.url:
            print(f"[{name}] Login failed! URL: {page.url}")
            # Take screenshot of failure
            await page.screenshot(path=f"{output_dir}/{name}_login_failed.png")
            await browser.close()
            return

        print(f"[{name}] Capturing Dashboard...")
        await page.screenshot(path=f"{output_dir}/{name}_dashboard.png", full_page=True)
        
        print(f"[{name}] Navigating to Client List...")
        await page.goto(f"{base_url}/admin/client/")
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path=f"{output_dir}/{name}_client_list.png", full_page=True)
        
        print(f"[{name}] Navigating to Create Client...")
        await page.goto(f"{base_url}/admin/client/new/")
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path=f"{output_dir}/{name}_client_create.png", full_page=True)

        await browser.close()
        print(f"[{name}] Capture complete")

async def main():
    # Correct path inside container
    output_dir = "/workspaces/netcup-api-filter/deploy-local/visual-comparison"
    
    # Read local password from .env.local
    local_password = "admin" # Default
    try:
        with open("/workspaces/netcup-api-filter/.env.local", "r") as f:
            for line in f:
                if line.startswith("DEPLOYED_ADMIN_PASSWORD="):
                    local_password = line.split("=", 1)[1].strip()
                    break
    except Exception as e:
        print(f"Warning: Could not read .env.local: {e}")

    # Local
    print(f"--- Capturing Local (Password: {local_password[:3]}...) ---")
    local_url = "http://netcup-api-filter-devcontainer-vb:5100"
    
    await capture(
        "local", 
        local_url, 
        "admin", 
        local_password, 
        output_dir
    )
    
    # Production
    print("\n--- Capturing Production ---")
    # Read prod password from .env.webhosting
    prod_password = "gu2HLkcv5Ditp9KzMpvfXfTScVZaHfUM" 
    
    await capture(
        "prod", 
        "https://naf.vxxu.de", 
        "admin", 
        prod_password, 
        output_dir
    )

if __name__ == "__main__":
    asyncio.run(main())

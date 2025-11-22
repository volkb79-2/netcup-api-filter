#!/usr/bin/env python3
"""
Validate WebSocket Playwright implementation solves form submission issues.

This script tests the exact scenario that failed in 10 MCP iterations:
- Admin login form submission
- Navigation to dashboard
- Form POST triggering correctly

If this succeeds, it proves dual-mode architecture solves the core problem.
"""
import asyncio
import sys
from pathlib import Path

# Add ui_tests to path
sys.path.insert(0, str(Path(__file__).parent.parent / "ui_tests"))

from playwright_client import PlaywrightClient, playwright_session


class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    MAGENTA = '\033[0;35m'
    CYAN = '\033[0;36m'
    NC = '\033[0m'  # No Color


def log_info(msg: str):
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {msg}")


def log_success(msg: str):
    print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {msg}")


def log_error(msg: str):
    print(f"{Colors.RED}[ERROR]{Colors.NC} {msg}", file=sys.stderr)


def log_test(msg: str):
    print(f"{Colors.CYAN}[TEST]{Colors.NC} {msg}")


def log_result(passed: bool, msg: str):
    if passed:
        print(f"{Colors.GREEN}[PASS]{Colors.NC} {msg}")
    else:
        print(f"{Colors.RED}[FAIL]{Colors.NC} {msg}")


async def test_connection():
    """Test 1: Basic WebSocket connection."""
    log_test("Test 1: WebSocket connection")
    
    try:
        async with PlaywrightClient(ws_url="ws://localhost:3000") as client:
            log_success("WebSocket connection established")
            return True
    except Exception as e:
        log_error(f"Connection failed: {e}")
        return False


async def test_navigation():
    """Test 2: Basic page navigation."""
    log_test("Test 2: Page navigation")
    
    try:
        async with playwright_session(base_url="https://naf.vxxu.de") as page:
            await page.goto("/admin/login")
            url = page.url
            log_info(f"Current URL: {url}")
            
            if "/admin/login" in url:
                log_success("Navigation successful")
                return True
            else:
                log_error(f"Wrong URL: {url}")
                return False
    except Exception as e:
        log_error(f"Navigation failed: {e}")
        return False


async def test_form_elements():
    """Test 3: Form element interaction."""
    log_test("Test 3: Form element interaction")
    
    try:
        async with playwright_session(base_url="https://naf.vxxu.de") as page:
            await page.goto("/admin/login")
            
            # Check form exists
            form = await page.query_selector("form")
            if not form:
                log_error("Login form not found")
                return False
            log_info("Form found")
            
            # Fill username
            await page.fill("#username", "admin")
            username_value = await page.input_value("#username")
            log_info(f"Username field: {username_value}")
            
            # Fill password
            await page.fill("#password", "admin123")
            password_value = await page.input_value("#password")
            log_info(f"Password field: {'*' * len(password_value)}")
            
            # Check submit button
            submit_btn = await page.query_selector("button[type='submit']")
            if not submit_btn:
                log_error("Submit button not found")
                return False
            log_info("Submit button found")
            
            log_success("Form elements working")
            return True
            
    except Exception as e:
        log_error(f"Form elements test failed: {e}")
        return False


async def test_form_submission():
    """
    Test 4: CRITICAL - Form submission (failed in all 10 MCP iterations).
    
    This is the core validation. If this works, dual-mode architecture succeeds.
    """
    log_test("Test 4: Form submission (THE CRITICAL TEST)")
    log_info("This test failed 10 times with MCP. Testing with WebSocket...")
    
    try:
        async with playwright_session(base_url="https://naf.vxxu.de") as page:
            # Navigate to login
            await page.goto("/admin/login")
            initial_url = page.url
            log_info(f"Initial URL: {initial_url}")
            
            # Get initial heading
            initial_heading = await page.text_content("h1")
            log_info(f"Initial heading: {initial_heading}")
            
            # Fill form
            await page.fill("#username", "admin")
            await page.fill("#password", "Admin123!")
            log_info("Credentials filled")
            
            # Submit form (THE MOMENT OF TRUTH)
            log_info("Clicking submit button...")
            await page.click("button[type='submit']")
            
            # Wait for navigation
            log_info("Waiting for navigation...")
            await page.wait_for_load_state("networkidle", timeout=10000)
            
            # Check results
            final_url = page.url
            final_heading = await page.text_content("h1")
            
            log_info(f"Final URL: {final_url}")
            log_info(f"Final heading: {final_heading}")
            
            # Validate success
            success = (
                "/admin/" in final_url and 
                "login" not in final_url.lower() and
                final_heading != initial_heading
            )
            
            if success:
                log_success("🎉 FORM SUBMISSION WORKS!")
                log_success(f"✅ URL changed: {initial_url} → {final_url}")
                log_success(f"✅ Heading changed: {initial_heading} → {final_heading}")
                log_success("✅ This proves WebSocket solves the MCP limitation!")
                return True
            else:
                log_error("❌ Form submission failed")
                log_error(f"URL: {initial_url} → {final_url}")
                log_error(f"Heading: {initial_heading} → {final_heading}")
                return False
                
    except Exception as e:
        log_error(f"Form submission test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_screenshot():
    """Test 5: Screenshot capability."""
    log_test("Test 5: Screenshot")
    
    try:
        async with playwright_session(base_url="https://naf.vxxu.de") as page:
            await page.goto("/admin/login")
            screenshot_path = Path("/tmp/playwright_validation.png")
            await page.screenshot(path=str(screenshot_path))
            
            if screenshot_path.exists():
                size = screenshot_path.stat().st_size
                log_success(f"Screenshot saved: {screenshot_path} ({size} bytes)")
                return True
            else:
                log_error("Screenshot file not created")
                return False
                
    except Exception as e:
        log_error(f"Screenshot test failed: {e}")
        return False


async def test_multiple_contexts():
    """Test 6: Multiple browser contexts (sessions)."""
    log_test("Test 6: Multiple contexts")
    
    try:
        async with PlaywrightClient() as client:
            # Create two independent contexts
            page1 = await client.new_page()
            page2 = await client.new_page()
            
            # Navigate independently
            await page1.goto("https://naf.vxxu.de/admin/login")
            await page2.goto("https://naf.vxxu.de/client/login")
            
            url1 = page1.url
            url2 = page2.url
            
            log_info(f"Context 1: {url1}")
            log_info(f"Context 2: {url2}")
            
            if "admin" in url1 and "client" in url2:
                log_success("Multiple contexts working")
                return True
            else:
                log_error("Context isolation failed")
                return False
                
    except Exception as e:
        log_error(f"Multiple contexts test failed: {e}")
        return False


async def main():
    """Run all validation tests."""
    print(f"\n{Colors.MAGENTA}{'='*70}{Colors.NC}")
    print(f"{Colors.MAGENTA}Playwright WebSocket Validation Suite{Colors.NC}")
    print(f"{Colors.MAGENTA}Testing solution for 10 failed MCP iterations{Colors.NC}")
    print(f"{Colors.MAGENTA}{'='*70}{Colors.NC}\n")
    
    tests = [
        ("Connection", test_connection),
        ("Navigation", test_navigation),
        ("Form Elements", test_form_elements),
        ("Form Submission", test_form_submission),  # CRITICAL TEST
        ("Screenshot", test_screenshot),
        ("Multiple Contexts", test_multiple_contexts),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            passed = await test_func()
            results.append((name, passed))
        except Exception as e:
            log_error(f"Test '{name}' crashed: {e}")
            results.append((name, False))
        print()  # Blank line between tests
    
    # Summary
    print(f"{Colors.MAGENTA}{'='*70}{Colors.NC}")
    print(f"{Colors.MAGENTA}Test Results Summary{Colors.NC}")
    print(f"{Colors.MAGENTA}{'='*70}{Colors.NC}\n")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for name, passed in results:
        log_result(passed, f"{name:<20}")
    
    print()
    print(f"Total: {passed_count}/{total_count} tests passed")
    
    # Critical test check
    form_submission_passed = any(
        name == "Form Submission" and passed 
        for name, passed in results
    )
    
    if form_submission_passed:
        print(f"\n{Colors.GREEN}{'='*70}{Colors.NC}")
        print(f"{Colors.GREEN}🎉 SUCCESS! Form submission works with WebSocket!{Colors.NC}")
        print(f"{Colors.GREEN}This validates the dual-mode architecture solves the core problem.{Colors.NC}")
        print(f"{Colors.GREEN}{'='*70}{Colors.NC}\n")
        return 0
    else:
        print(f"\n{Colors.RED}{'='*70}{Colors.NC}")
        print(f"{Colors.RED}❌ CRITICAL: Form submission still failing{Colors.NC}")
        print(f"{Colors.RED}Check server logs and network connectivity{Colors.NC}")
        print(f"{Colors.RED}{'='*70}{Colors.NC}\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

"""
Journey Master: Orchestrated Sequential Test Execution

This is the main entry point for integrated journey testing.
Journeys execute in order, each building on the state from the previous.

Run with:
    pytest ui_tests/tests/test_journey_master.py -v --timeout=300

Or run specific journeys:
    pytest ui_tests/tests/test_journey_master.py::TestJourneyMaster::test_journey_1 -v
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio

from ui_tests.browser import Browser, browser_session
from ui_tests.config import settings
from ui_tests.tests.journeys import journey_state


# Reset journey state at module load
journey_state.reset()


class TestJourneyMaster:
    """Master test class that runs all journeys in sequence."""
    
    @pytest.fixture(scope="class")
    def mailpit_client(self):
        """Shared Mailpit client for email testing."""
        try:
            from ui_tests.mailpit_client import MailpitClient
            client = MailpitClient()
            client.clear()
            yield client
            client.close()
        except Exception as e:
            pytest.skip(f"Mailpit not available: {e}")
    
    # =========================================================================
    # Journey 1: Fresh Deployment
    # =========================================================================
    
    async def test_journey_1_fresh_deployment(self):
        """Journey 1: Validate fresh deployment state."""
        print("\n" + "=" * 60)
        print("JOURNEY 1: Fresh Deployment")
        print("=" * 60)
        
        from ui_tests.tests.journeys.j1_fresh_deployment import TestJourney1FreshDeployment
        
        journey = TestJourney1FreshDeployment()
        
        # Execute journey steps in order using function-scope browser
        async with browser_session() as browser:
            await journey.test_J1_01_login_page_accessible(browser)
            await journey.test_J1_02_default_credentials_work(browser)
            await journey.test_J1_03_forced_password_change(browser)
            await journey.test_J1_04_dashboard_state(browser)
            await journey.test_J1_05_admin_pages_accessible(browser)
            await journey.test_J1_06_summary(browser)
        
        # Verify journey state
        assert journey_state.admin_logged_in, "Admin should be logged in after Journey 1"
        assert journey_state.admin_password is not None, "Admin password should be set"
        
        print(f"\n✓ Journey 1 complete: {len(journey_state.screenshots)} screenshots")
    
    # =========================================================================
    # Journey 2: Account Lifecycle
    # =========================================================================
    
    async def test_journey_2_account_lifecycle(self, mailpit_client):
        """Journey 2: Account registration, verification, and approval."""
        print("\n" + "=" * 60)
        print("JOURNEY 2: Account Lifecycle")
        print("=" * 60)
        
        from ui_tests.tests.journeys.j2_account_lifecycle import TestJourney2AccountLifecycle
        
        journey = TestJourney2AccountLifecycle()
        
        # Execute journey steps in order using function-scope browser
        async with browser_session() as browser:
            await journey.test_J2_01_registration_page(browser)
            await journey.test_J2_02_submit_registration(browser, mailpit_client)
            await journey.test_J2_03_check_verification_email(browser, mailpit_client)
            await journey.test_J2_04_complete_verification(browser)
            await journey.test_J2_05_admin_sees_pending_account(browser)
            await journey.test_J2_06_approve_account(browser, mailpit_client)
            await journey.test_J2_07_user_can_login(browser)
            await journey.test_J2_08_summary(browser)
        
        print(f"\n✓ Journey 2 complete: {len(journey_state.screenshots)} screenshots total")
    
    # =========================================================================
    # Journey 3: Comprehensive State Population
    # =========================================================================
    
    async def test_journey_3_comprehensive_states(self):
        """Journey 3: Create ALL account/realm/token states from matrix."""
        print("\n" + "=" * 60)
        print("JOURNEY 3: Comprehensive State Population")
        print("=" * 60)
        
        from ui_tests.tests.journeys.j3_comprehensive_states import TestJourney3ComprehensiveStates
        
        journey = TestJourney3ComprehensiveStates()
        
        # Execute journey steps in order using function-scope browser
        async with browser_session() as browser:
            await journey.test_J3_01_create_accounts(browser)
            await journey.test_J3_02_create_realms(browser)
            await journey.test_J3_03_create_tokens(browser)
            await journey.test_J3_04_api_tests(browser)
            await journey.test_J3_05_ui_validation(browser)
            await journey.test_J3_06_summary(browser)
        
        print(f"\n✓ Journey 3 complete: {len(journey_state.screenshots)} screenshots total")
    
    # =========================================================================
    # Journey Summary
    # =========================================================================
    
    async def test_journey_final_summary(self):
        """Generate final summary and save state."""
        print("\n" + "=" * 60)
        print("ALL JOURNEYS COMPLETE")
        print("=" * 60)
        
        # Print state summary
        state = journey_state.to_dict()
        print(f"\nFinal State:")
        for key, value in state.items():
            print(f"  {key}: {value}")
        
        # Print screenshot manifest
        print(f"\nScreenshots Captured ({len(journey_state.screenshots)}):")
        for name, path in journey_state.screenshots:
            exists = "✓" if Path(path).exists() else "✗"
            print(f"  {exists} {name}")
        
        # Save journey report
        await _save_journey_report()
        
        print("\n" + "=" * 60)
        print("Test run complete!")
        print("=" * 60)


async def _save_journey_report():
    """Save journey results to JSON report."""
    screenshot_dir = os.environ.get("SCREENSHOT_DIR")
    if not screenshot_dir:
        return
    
    report_path = Path(screenshot_dir) / "journey_report.json"
    
    # Get comprehensive state from journey 3
    account_creator = journey_state.get_extra("account_creator")
    realm_creator = journey_state.get_extra("realm_creator")
    token_creator = journey_state.get_extra("token_creator")
    
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state": journey_state.to_dict(),
        "screenshots": [
            {"name": name, "path": path, "exists": Path(path).exists()}
            for name, path in journey_state.screenshots
        ],
        "summary": {
            "total_screenshots": len(journey_state.screenshots),
            "admin_password_changed": journey_state.admin_password != "admin",
            "test_account_created": journey_state.test_account_username is not None,
            "test_account_approved": journey_state.test_account_approved,
            # Comprehensive state counts
            "accounts_created": len(account_creator.created_accounts) if account_creator else 0,
            "realms_created": len(realm_creator.created_realms) if realm_creator else 0,
            "tokens_created": len(token_creator.created_tokens) if token_creator else 0,
        }
    }
    
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Journey report saved to: {report_path}")


# ============================================================================
# Standalone execution support
# ============================================================================

if __name__ == "__main__":
    # Allow running with: python test_journey_master.py
    pytest.main([__file__, "-v", "--timeout=300"])

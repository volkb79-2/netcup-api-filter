"""
Journey Master: Orchestrated Sequential Test Execution

This is the main entry point for integrated journey testing.
Journeys execute in order, each building on the state from the previous.

Run with:
    pytest ui_tests/tests/test_journey_master.py -v --timeout=300

Or run specific journeys:
    pytest ui_tests/tests/test_journey_master.py::TestJourneyMaster::test_journey_1 -v
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ui_tests.browser import browser_session
from ui_tests.tests.journeys import journey_state

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.asyncio, pytest.mark.journey]

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
        except Exception as e:
            pytest.fail(
                f"Local e2e requires reachable Mailpit via MAILPIT_URL ({type(e).__name__})",
                pytrace=False,
            )
        try:
            yield client
        finally:
            client.close()
    
    # =========================================================================
    # Journey 1: Fresh Deployment
    # =========================================================================
    
    async def test_journey_1_fresh_deployment(self):
        """Journey 1: Validate fresh deployment state."""
        logger.info("\n" + "=" * 60)
        logger.info("JOURNEY 1: Fresh Deployment")
        logger.info("=" * 60)
        
        from ui_tests.tests.journeys.j1_fresh_deployment import TestJourney1FreshDeployment
        
        journey = TestJourney1FreshDeployment()
        
        # Execute journey steps in order using function-scope browser
        async with browser_session("anonymous") as browser:
            await journey.test_J1_01_login_page_accessible(browser)
            await journey.test_J1_02_admin_persona_authenticates(browser)
            await journey.test_J1_04_dashboard_state(browser)
            await journey.test_J1_05_admin_pages_accessible(browser)
            await journey.test_J1_06_summary(browser)
        
        # Verify journey state
        assert journey_state.admin_logged_in, "Admin should be logged in after Journey 1"
        assert journey_state.admin_password is not None, "Admin password should be set"
        
        logger.info(f"\n✓ Journey 1 complete: {len(journey_state.screenshots)} screenshots")
    
    # =========================================================================
    # Journey 2: Account Lifecycle
    # =========================================================================
    
    async def test_journey_2_account_lifecycle(self, mailpit_client):
        """Journey 2: Account registration, verification, and approval."""
        journey_state.set_extra("j2_user_login_verified", False)
        logger.info("\n" + "=" * 60)
        logger.info("JOURNEY 2: Account Lifecycle")
        logger.info("=" * 60)
        
        from ui_tests.tests.journeys.j2_account_lifecycle import TestJourney2AccountLifecycle
        
        journey = TestJourney2AccountLifecycle()
        skipped_steps = []

        async def run_step(name, step):
            try:
                await step
            except pytest.skip.Exception as exc:
                reason = str(exc)
                skipped_steps.append((name, reason))
                logger.info("Journey 2 step %s skipped: %s", name, reason)
        
        # Execute journey steps in order using function-scope browser
        async with browser_session("anonymous") as browser:
            await run_step("J2_01", journey.test_J2_01_registration_page(browser))
            await run_step("J2_02", journey.test_J2_02_submit_registration(browser, mailpit_client))
            await run_step("J2_03", journey.test_J2_03_check_verification_email(browser, mailpit_client))
            await run_step("J2_04", journey.test_J2_04_complete_verification(browser))
            await run_step("J2_05", journey.test_J2_05_admin_sees_pending_account(browser))
            await run_step("J2_06", journey.test_J2_06_approve_account(browser, mailpit_client))
            await run_step("J2_07", journey.test_J2_07_user_can_login(browser, mailpit_client))
            await run_step("J2_08", journey.test_J2_08_summary(browser))
        
        logger.info(f"\n✓ Journey 2 complete: {len(journey_state.screenshots)} screenshots total")
        if skipped_steps:
            pytest.skip(
                "Journey 2 completed with documented skipped steps: "
                + "; ".join(f"{name}: {reason}" for name, reason in skipped_steps)
            )
    
    # =========================================================================
    # Journey 3: Comprehensive State Population
    # =========================================================================
    
    async def test_journey_3_comprehensive_states(self):
        """Journey 3: Create ALL account/realm/token states from matrix."""
        from ui_tests.config import settings

        if (
            journey_state.get_extra("invite_based_account")
            and settings.deployment_target != "webhosting"
            and not journey_state.get_extra("j2_user_login_verified")
        ):
            pytest.fail(
                "The local J2 admin-invite path did not reach and verify J2_07 user login",
                pytrace=False,
            )

        logger.info("\n" + "=" * 60)
        logger.info("JOURNEY 3: Comprehensive State Population")
        logger.info("=" * 60)
        
        from ui_tests.tests.journeys.j3_comprehensive_states import TestJourney3ComprehensiveStates
        
        journey = TestJourney3ComprehensiveStates()
        
        # Execute journey steps in order using function-scope browser
        async with browser_session("admin") as browser:
            await journey.test_J3_01_create_accounts(browser)
            await journey.test_J3_02_create_realms(browser)
            await journey.test_J3_03_create_tokens(browser)
            await journey.test_J3_04_api_tests(browser)
            await journey.test_J3_05_ui_validation(browser)
            await journey.test_J3_06_summary(browser)
        
        logger.info(f"\n✓ Journey 3 complete: {len(journey_state.screenshots)} screenshots total")
    
    # =========================================================================
    # Journey Summary
    # =========================================================================
    
    async def test_journey_final_summary(self):
        """Generate final summary and save state."""
        logger.info("\n" + "=" * 60)
        logger.info("ALL JOURNEYS COMPLETE")
        logger.info("=" * 60)
        
        # Print state summary
        state = journey_state.to_dict()
        logger.info("\nFinal State:")
        for key, value in state.items():
            logger.info(f"  {key}: {value}")
        
        # Print screenshot manifest
        logger.info(f"\nScreenshots Captured ({len(journey_state.screenshots)}):")
        for name, path in journey_state.screenshots:
            exists = "✓" if Path(path).exists() else "✗"
            logger.info(f"  {exists} {name}")
        
        # Save journey report
        await _save_journey_report()
        
        logger.info("\n" + "=" * 60)
        logger.info("Test run complete!")
        logger.info("=" * 60)


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
    
    logger.info(f"\n📄 Journey report saved to: {report_path}")


# ============================================================================
# Standalone execution support
# ============================================================================

if __name__ == "__main__":
    # Allow running with: python test_journey_master.py
    pytest.main([__file__, "-v", "--timeout=300"])

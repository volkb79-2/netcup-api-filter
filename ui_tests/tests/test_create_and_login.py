import pytest

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings

pytestmark = pytest.mark.asyncio


async def test_admin_creates_client_then_client_logs_in(active_profile):
    """
    A test that creates a client as admin, logs out, and then logs in as the
    new client in a separate, clean browser session. This isolates the sessions
    to prevent race conditions.
    """
    if not active_profile.allow_writes:
        pytest.skip("profile is read-only; skipping create/delete flow")

    client_data = workflows.generate_client_data()
    generated_token = ""

    # 1. Admin Session: Create the client
    print("\n--- Starting Admin Session (Create) ---")
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_client_create(browser)

        generated_token = await workflows.submit_client_form(browser, client_data)
        assert len(generated_token) >= 10
        
        await workflows.ensure_client_visible(browser, client_data.client_id)
        print("--- Finished Admin Session (Create) ---")

    # 2. Client Session: Log in as the new client
    print("\n--- Starting Client Session ---")
    assert generated_token, "Generated token should not be empty"
    async with browser_session() as browser:
        await workflows.test_client_login_with_token(
            browser, generated_token, should_succeed=True, expected_client_id=client_data.client_id
        )
        print("--- Finished Client Session ---")


    # 3. Admin Cleanup Session: Delete the client
    print("\n--- Starting Admin Session (Cleanup) ---")
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.delete_admin_client(browser, client_data.client_id)
        await workflows.ensure_client_absent(browser, client_data.client_id)
        print("--- Finished Admin Session (Cleanup) ---")

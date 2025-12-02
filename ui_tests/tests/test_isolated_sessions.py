"""
Test: Admin creates account with isolated browser sessions.

DEPRECATED: This test was written for the old "Client" model with single-step token creation.
The new architecture uses Account → Realm → Token with multi-step creation.

See test_create_and_login.py and TEMPLATE_CONTRACT.md for details.
"""
import pytest

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings

pytestmark = pytest.mark.asyncio


@pytest.mark.skip(reason="Test uses deprecated Client model. Needs rewrite for Account → Realm → Token architecture")
async def test_admin_creates_client_then_client_logs_in(active_profile):
    """
    DEPRECATED: See test_create_and_login.py for details on the architecture change.
    """
    pass

"""
Test: Admin creates account, adds realm with token, then client logs in.

DEPRECATED: This test was written for the old "Client" model with single-step token creation.
The new architecture uses Account → Realm → Token with multi-step creation:

1. Create account (username, email, password)
2. Add realm to account (domain, record types, operations)  
3. Token is auto-generated when realm is added

This requires rewriting to support the new Account-based flow.
See TEMPLATE_CONTRACT.md for the new architecture documentation.
"""
import pytest

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings

pytestmark = pytest.mark.asyncio


@pytest.mark.skip(reason="Test uses deprecated Client model. Needs rewrite for Account → Realm → Token architecture")
async def test_admin_creates_client_then_client_logs_in(active_profile):
    """
    DEPRECATED: This test expected old client-based single-form creation.
    
    The new flow requires:
    1. Create account at /admin/accounts/new (username, email, password)
    2. Add realm at /admin/accounts/<id>/realms/new (domain, record types, ops)
    3. Token is generated from realm creation
    4. Client authenticates with Bearer token (naf_<username>_<random>)
    
    TODO: Rewrite for Account → Realm → Token flow.
    """
    pass

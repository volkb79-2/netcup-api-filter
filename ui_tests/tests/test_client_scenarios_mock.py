"""Tests for client scenarios - DEPRECATED.

This test file was written for the old single-table client model.
The new architecture uses Account → AccountRealm → APIToken.

TODO: Rewrite tests for the new architecture when client portal is implemented.
"""
import pytest


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skip(reason="Test written for deprecated client model - needs rewrite for Account/Realm/Token architecture")
]


async def test_client_scenarios_placeholder():
    """Placeholder for future client scenario tests."""
    pytest.skip("Client scenario tests need rewrite for new architecture")

"""Tests for client portal UI - DEPRECATED.

This test file was written for the old client portal with client_id:secret_key auth.
The new architecture uses Account login with session auth.

TODO: Rewrite tests when client portal is updated for new auth model.
"""
import pytest


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skip(reason="Client portal tests need rewrite for Account-based auth (not client_id:secret_key)")
]


async def test_client_portal_placeholder():
    """Placeholder for future client portal tests."""
    pytest.skip("Client portal tests need rewrite")

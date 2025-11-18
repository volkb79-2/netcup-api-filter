import sys
from pathlib import Path

import pytest
import pytest_asyncio
import mcp
from mcp.client.streamable_http import streamablehttp_client

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui_tests.browser import Browser
from ui_tests.config import UiTargetProfile, settings


@pytest_asyncio.fixture()
async def mcp_session():
    async with streamablehttp_client(settings.mcp_url) as (read, write, _):
        async with mcp.ClientSession(read, write) as session:
            await session.initialize()
            yield session


@pytest_asyncio.fixture()
async def browser(mcp_session):
    browser = Browser(mcp_session)
    await browser.reset()
    return browser


def _profile_id(profile: UiTargetProfile) -> str:
    return profile.name


@pytest.fixture(params=settings.profiles(), ids=_profile_id)
def active_profile(request):
    """Activate each configured UI target profile for the test run."""
    profile: UiTargetProfile = request.param
    with settings.use_profile(profile):
        yield profile

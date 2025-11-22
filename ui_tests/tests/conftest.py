import sys
from pathlib import Path

import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui_tests.browser import Browser
from ui_tests.config import UiTargetProfile, settings
from ui_tests.playwright_client import PlaywrightClient


@pytest_asyncio.fixture()
async def playwright_client():
    """Create a Playwright client instance."""
    async with PlaywrightClient(headless=settings.playwright_headless) as client:
        yield client


@pytest_asyncio.fixture()
async def browser(playwright_client):
    """Create a Browser instance with the Playwright page."""
    browser = Browser(playwright_client.page)
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

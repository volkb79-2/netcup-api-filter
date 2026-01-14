import os
import sys
from pathlib import Path
import time
import cProfile
import pstats
import io
import json

import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui_tests.browser import Browser
from ui_tests.config import UiTargetProfile, settings
from ui_tests.deployment_state import (
    clear_playwright_storage_state,
    get_playwright_storage_state_path,
)
from ui_tests.playwright_client import PlaywrightClient


@pytest.fixture(autouse=True)
def refresh_credentials_before_test():
    """Auto-refresh credentials from deployment_state.json before each test.
    
    This ensures tests always have the latest credentials, even if a previous
    test changed the admin password or client tokens.
    """
    settings.refresh_credentials()
    yield


@pytest_asyncio.fixture()
async def playwright_client():
    """Create a Playwright client instance."""
    storage_state_path = os.environ.get("UI_PLAYWRIGHT_STORAGE_STATE_PATH")
    if not storage_state_path:
        storage_state_path = str(get_playwright_storage_state_path())

    async with PlaywrightClient(
        headless=settings.playwright_headless,
        storage_state_path=storage_state_path,
    ) as client:
        yield client


@pytest.fixture(scope="session", autouse=True)
def _clear_playwright_storage_state_on_exit():
    """Optionally clear persisted Playwright auth state after the test run.

    This is useful when you explicitly want the next run to re-test the full
    2FA/login flow.

    Controlled via env:
      - UI_CLEAR_AUTH_STATE_ON_EXIT=1
    """
    yield
    if os.environ.get("UI_CLEAR_AUTH_STATE_ON_EXIT") != "1":
        return
    deleted = clear_playwright_storage_state()
    path = get_playwright_storage_state_path()
    if deleted:
        print(f"[CONFIG] Cleared Playwright auth state on exit: {path}")
    else:
        print(f"[CONFIG] No Playwright auth state to clear on exit: {path}")


@pytest_asyncio.fixture()
async def browser(playwright_client):
    """Create a Browser instance with the Playwright page."""
    trace_threshold_s = os.environ.get("UI_TRACE_ON_SLOW_SECONDS")
    trace_dir = os.environ.get("UI_TRACE_DIR")
    trace_enabled = False
    started_at = time.perf_counter()

    if trace_threshold_s:
        if not trace_dir:
            raise RuntimeError(
                "UI_TRACE_ON_SLOW_SECONDS is set but UI_TRACE_DIR is not set. "
                "Set UI_TRACE_DIR to a writable directory to store trace zips."
            )
        os.makedirs(trace_dir, exist_ok=True)
        try:
            threshold_val = float(trace_threshold_s)
        except ValueError as exc:
            raise ValueError(
                f"Invalid UI_TRACE_ON_SLOW_SECONDS={trace_threshold_s!r} (expected float)"
            ) from exc
        if threshold_val > 0:
            await playwright_client.context.tracing.start(screenshots=True, snapshots=True, sources=True)
            trace_enabled = True

    browser = Browser(playwright_client.page)
    await browser.reset()
    try:
        yield browser
    finally:
        if trace_enabled:
            duration_s = time.perf_counter() - started_at
            threshold_val = float(trace_threshold_s)
            if duration_s >= threshold_val:
                test_id = os.environ.get("PYTEST_CURRENT_TEST", "unknown_test").split(" ", 1)[0]
                safe_name = "".join(ch if (ch.isalnum() or ch in "_.-") else "_" for ch in test_id).strip("_.-")
                safe_name = safe_name or "trace"
                trace_path = os.path.join(trace_dir, safe_name + ".zip")
                await playwright_client.context.tracing.stop(path=trace_path)
            else:
                await playwright_client.context.tracing.stop()


# ============================================================================
# Parallel Session Manager fixtures
# ============================================================================

@pytest_asyncio.fixture()
async def session_manager(playwright_client):
    """Create a parallel session manager for multi-user tests.
    
    Provides isolated browser contexts for concurrent session testing.
    All sessions are automatically cleaned up after the test.
    
    Usage:
        async def test_multi_user(session_manager):
            admin = await session_manager.admin_session()
            user = await session_manager.account_session('testuser')
            # Both sessions operate independently
    """
    from ui_tests.parallel_session_manager import ParallelSessionManager
    
    async with ParallelSessionManager(
        browser=playwright_client.browser,
        base_url=settings.url(''),
    ) as manager:
        yield manager


@pytest_asyncio.fixture()
async def admin_session(session_manager):
    """Get the admin session handle from parallel session manager.
    
    Returns a logged-in admin session. Handles forced password change
    scenarios automatically.
    """
    return await session_manager.admin_session()


def _profile_id(profile: UiTargetProfile) -> str:
    return profile.name


@pytest.fixture(params=settings.profiles(), ids=_profile_id)
def active_profile(request):
    """Activate each configured UI target profile for the test run."""
    profile: UiTargetProfile = request.param
    with settings.use_profile(profile):
        yield profile


# ============================================================================
# Mock Netcup API fixtures
# ============================================================================

@pytest.fixture(scope='function')
def mock_netcup_api_server():
    """Fixture that provides a running mock Netcup API server."""
    import threading
    import time
    from werkzeug.serving import make_server
    from ui_tests.mock_netcup_api import create_mock_api_app, reset_mock_state
    
    class MockServer:
        def __init__(self, host='127.0.0.1', port=5555):
            self.host = host
            self.port = port
            self.app = create_mock_api_app()
            self.server = None
            self.thread = None
        
        def start(self):
            self.server = make_server(self.host, self.port, self.app, threaded=True)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            time.sleep(0.5)  # Give server time to start
        
        def stop(self):
            if self.server:
                self.server.shutdown()
                if self.thread:
                    self.thread.join(timeout=5)
        
        @property
        def url(self):
            return f"http://{self.host}:{self.port}/run/webservice/servers/endpoint.php"
    
    reset_mock_state()
    server = MockServer()
    server.start()
    
    yield server
    
    server.stop()
    reset_mock_state()


@pytest.fixture(scope='function')
def mock_netcup_credentials():
    """Fixture that provides mock Netcup API credentials."""
    from ui_tests.mock_netcup_api import MOCK_CUSTOMER_ID, MOCK_API_KEY, MOCK_API_PASSWORD
    return {
        'customer_id': MOCK_CUSTOMER_ID,
        'api_key': MOCK_API_KEY,
        'api_password': MOCK_API_PASSWORD
    }


@pytest.fixture(scope='function')
async def browser_session():
    """Fixture that provides a browser session (same as browser fixture but with better name)."""
    async with PlaywrightClient(headless=settings.playwright_headless) as client:
        browser = Browser(client.page)
        await browser.reset()
        yield browser


# ============================================================================
# Mock SMTP server fixtures
# ============================================================================

@pytest_asyncio.fixture(scope='function')
async def mock_smtp_server():
    """Fixture that provides a running mock SMTP server.
    
    Captures all emails sent during the test for inspection.
    
    Usage:
        async def test_email(mock_smtp_server):
            # Configure app to use mock SMTP
            smtp_host, smtp_port = "127.0.0.1", 1025
            
            # ... trigger email sending ...
            
            # Check captured emails
            assert len(mock_smtp_server.captured_emails) == 1
            email = mock_smtp_server.captured_emails[0]
            assert email.subject == "Test Subject"
    """
    from ui_tests.mock_smtp_server import MockSMTPServer
    
    server = MockSMTPServer(host='127.0.0.1', port=1025)
    await server.start()
    
    yield server
    
    await server.stop()


@pytest.fixture(scope='function')
def mailpit():
    """Fixture that provides a Mailpit client for SMTP testing.
    
    Requires Mailpit container to be running:
        cd tooling/mailpit && docker compose up -d
    
    Usage:
        def test_email(mailpit):
            # Clear mailbox before test
            mailpit.clear()
            
            # ... trigger email sending to mailpit:1025 ...
            
            # Wait for and check email
            msg = mailpit.wait_for_message(
                predicate=lambda m: "verification" in m.subject.lower(),
                timeout=10.0
            )
            assert msg is not None
            assert "Click here" in msg.text
    
    See ui_tests/mailpit_client.py for full API documentation.
    """
    from ui_tests.mailpit_client import MailpitClient
    
    client = MailpitClient()
    # Clear mailbox before test for isolation
    try:
        client.clear()
    except Exception:
        pytest.skip("Mailpit not available - start with: cd tooling/mailpit && docker compose up -d")
    
    yield client
    
    # Clear mailbox after test
    try:
        client.clear()
    except Exception:
        pass  # Ignore cleanup errors
    
    client.close()


# ============================================================================
# UI Page Fixtures
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def admin_page(browser_session):
    """
    Logs in as an admin user and returns an authenticated Page object.
    """
    from ui_tests.workflows import ensure_admin_dashboard
    
    await ensure_admin_dashboard(browser_session)
    return browser_session._page

@pytest_asyncio.fixture(scope="function")
async def client_page_readonly(browser_session, admin_page):
    """
    Creates a read-only client, logs in, and returns an authenticated Page object.
    """
    from ui_tests.workflows import generate_client_data, admin_create_client_and_extract_token, test_client_login_with_token

    # 1. Create a read-only client
    client_data = generate_client_data("readonly-client")
    client_data.operations = ["read"]
    token = await admin_create_client_and_extract_token(browser_session, client_data)

    # 2. Log in with the new client's token
    await test_client_login_with_token(browser_session, token, should_succeed=True, expected_client_id=client_data.client_id)
    return browser_session._page

@pytest_asyncio.fixture(scope="function")
async def client_page_fullcontrol(browser_session, admin_page):
    """
    Creates a full-control client, logs in, and returns an authenticated Page object.
    """
    from ui_tests.workflows import generate_client_data, admin_create_client_and_extract_token, test_client_login_with_token

    # 1. Create a full-control client
    client_data = generate_client_data("fullcontrol-client")
    client_data.operations = ["read", "update", "create", "delete"]
    token = await admin_create_client_and_extract_token(browser_session, client_data)

    # 2. Log in with the new client's token
    await test_client_login_with_token(browser_session, token, should_succeed=True, expected_client_id=client_data.client_id)
    return browser_session._page


@pytest.fixture(scope="session")
def base_url():
    """Provide base URL for tests."""
    return os.getenv("UI_BASE_URL", settings.base_url)


# =========================================================================
# Optional per-test profiling (cProfile)
# =========================================================================


def _env_flag(name: str) -> bool:
    val = (os.environ.get(name) or "").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _safe_profile_name(nodeid: str) -> str:
    safe = "".join(ch if (ch.isalnum() or ch in "_.-") else "_" for ch in nodeid)
    safe = safe.strip("_.-")
    return safe or "profile"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    enabled = _env_flag("PYTEST_PROFILE_ENABLED")
    if not enabled:
        yield
        return

    prof = cProfile.Profile()
    started_at = time.perf_counter()
    prof.enable()
    outcome = yield
    prof.disable()
    duration_s = time.perf_counter() - started_at

    # Only report/save for slow tests (config-driven)
    try:
        min_seconds = float((os.environ.get("PYTEST_PROFILE_MIN_SECONDS") or "0").strip())
    except ValueError:
        min_seconds = 0.0

    if duration_s < min_seconds:
        return

    profile_dir = (os.environ.get("PYTEST_PROFILE_DIR") or "").strip() or None
    sort_key = (os.environ.get("PYTEST_PROFILE_SORT") or "tottime").strip() or "tottime"
    try:
        top_n = int((os.environ.get("PYTEST_PROFILE_TOP") or "30").strip())
    except ValueError:
        top_n = 30

    # Capture a short, readable summary into the test report
    stream = io.StringIO()
    stats = pstats.Stats(prof, stream=stream)
    try:
        stats.sort_stats(sort_key)
    except Exception:
        stats.sort_stats("tottime")
    stats.print_stats(top_n)
    summary = stream.getvalue()

    item.user_properties.append(("cprofile_duration_s", duration_s))
    item.user_properties.append(("cprofile_top", summary))

    if profile_dir:
        os.makedirs(profile_dir, exist_ok=True)
        prof_path = os.path.join(profile_dir, _safe_profile_name(item.nodeid) + ".prof")
        prof.dump_stats(prof_path)
        item.user_properties.append(("cprofile_file", prof_path))

        meta_path = os.path.splitext(prof_path)[0] + ".json"
        meta = {
            "nodeid": item.nodeid,
            "duration_s": duration_s,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, sort_keys=True)
                f.write("\n")
        except OSError:
            # Best-effort: profiling should not fail tests due to filesystem issues.
            pass

    return outcome


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    enabled = _env_flag("PYTEST_PROFILE_ENABLED")
    if not enabled:
        return

    terminalreporter.write_sep("=", "Per-test cProfile (call phase)")

    # Print summaries for failed/slow tests only (already filtered by min_seconds)
    for report in terminalreporter.getreports("passed") + terminalreporter.getreports("failed"):
        duration_s = None
        profile_text = None
        profile_file = None
        for k, v in getattr(report, "user_properties", []):
            if k == "cprofile_duration_s":
                duration_s = v
            elif k == "cprofile_top":
                profile_text = v
            elif k == "cprofile_file":
                profile_file = v

        if profile_text is None or duration_s is None:
            continue

        terminalreporter.write_line(f"\n{report.nodeid}  (call: {duration_s:.3f}s)")
        if profile_file:
            terminalreporter.write_line(f"  profile: {profile_file}")
        for line in profile_text.rstrip().splitlines():
            terminalreporter.write_line("  " + line)
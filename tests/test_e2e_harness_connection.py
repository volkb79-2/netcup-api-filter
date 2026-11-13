"""Unit contracts for the session-scoped browser harness.

These tests exercise the harness without Playwright, browsers, pytest fixtures
from the e2e lane, or network access.  Their fakes deliberately expose the old
per-test connection and shared-storage behaviour as failures.
"""

from __future__ import annotations

import asyncio
import ast
import json
import signal
import urllib.error
from pathlib import Path

import pytest

from ui_tests.browser import Browser, ToolError, browser_session
from ui_tests.config import UiTestConfig, settings
from ui_tests.parallel_session_manager import ParallelSessionManager
from ui_tests.playwright_client import PlaywrightClient
from ui_tests.pwmcp_connection import (
    ConnectionOptions,
    GatewaySlotsBusyTimeout,
    PwmcpConnectionClosed,
    PwmcpContractError,
    SharedPwmcpSession,
    connect_with_bounded_retry,
    contract_url_from_ws,
    context_storage_state,
    fetch_contract,
    installed_playwright_protocol,
    is_gateway_slots_busy,
    lease_headers,
    load_connection_options,
    pwmcp_session_label,
    install_signal_cleanup,
    safe_connection_error,
    validate_contract,
)

# The message Playwright 1.64 raises when the pwmcp gateway rejects the upgrade (review L6).
REAL_PLAYWRIGHT_503 = (
    "WebSocket error: ws://pwmcp:3000/ 503 Service Unavailable\nall 2 browser slots are in use"
)


def _contract(protocol: str = "1.64", max_lease_seconds: int = 7200) -> dict:
    return {
        "schema_version": 1,
        "playwright": {"python": f"{protocol}.1", "protocol": protocol},
        "run_server": {"limits": {"max_lease_seconds": max_lease_seconds}},
    }


def _options(
    *,
    remote: bool = True,
    renew_margin: float = 60,
    recycle_interval: float = 540,
    max_reconnects: int = 3,
) -> ConnectionOptions:
    return ConnectionOptions(
        ws_url="ws://pwmcp:3000/" if remote else "",
        connect_timeout_seconds=30,
        retry_total_seconds=120,
        retry_initial_seconds=1,
        retry_max_seconds=8,
        contract_timeout_seconds=10,
        recycle_interval_seconds=recycle_interval,
        lease_renew_margin_seconds=renew_margin,
        max_reconnects=max_reconnects,
    )


_LEASE_ENV = {"E2E_PWMCP_LANE_NAME": "unit"}


class _FakePage:
    url = "about:blank"

    async def set_viewport_size(self, _viewport):
        return None

    async def close(self):
        return None


class _FakeContext:
    def __init__(self, *, page_error: BaseException | None = None) -> None:
        self.page = _FakePage()
        self.page_error = page_error
        self.close_calls = 0

    async def new_page(self):
        if self.page_error is not None:
            raise self.page_error
        return self.page

    def set_default_timeout(self, _timeout):
        return None

    async def close(self):
        self.close_calls += 1


class _FakeBrowser:
    def __init__(self, *, connected: bool = True) -> None:
        self._connected = connected
        self.close_calls = 0
        self.contexts: list[_FakeContext] = []
        self.context_kwargs: list[dict] = []

    def is_connected(self) -> bool:
        return self._connected

    async def new_context(self, **kwargs) -> _FakeContext:
        self.context_kwargs.append(kwargs)
        context = _FakeContext()
        self.contexts.append(context)
        return context

    async def close(self) -> None:
        self.close_calls += 1
        self._connected = False


class _FakeBrowserType:
    def __init__(self, browsers: list[_FakeBrowser]) -> None:
        self._browsers = browsers
        self.connect_calls = 0
        self.connect_kwargs: list[dict] = []
        self.errors: list[BaseException] = []

    async def connect(self, _url: str, **kwargs) -> _FakeBrowser:
        self.connect_calls += 1
        self.connect_kwargs.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)
        return self._browsers[min(self.connect_calls - 1, len(self._browsers) - 1)]


class _FakePlaywright:
    def __init__(self, browsers: list[_FakeBrowser]) -> None:
        self.chromium = _FakeBrowserType(browsers)
        self.stop_calls = 0

    async def stop(self) -> None:
        self.stop_calls += 1


class _FakePlaywrightStarter:
    def __init__(self, playwright: _FakePlaywright) -> None:
        self._playwright = playwright

    async def start(self) -> _FakePlaywright:
        return self._playwright


async def test_gateway_503_retries_with_exponential_backoff():
    now = 0.0
    delays: list[float] = []
    attempts = 0

    async def connect_once(timeout_seconds: float):
        nonlocal attempts
        attempts += 1
        assert timeout_seconds > 0
        if attempts < 3:
            raise RuntimeError("HTTP 503: all 2 browser slots are in use")
        return "browser"

    async def fake_sleep(delay: float) -> None:
        nonlocal now
        delays.append(delay)
        now += delay

    result = await connect_with_bounded_retry(
        connect_once,
        total_timeout_seconds=20,
        initial_backoff_seconds=1,
        max_backoff_seconds=4,
        clock=lambda: now,
        sleep=fake_sleep,
    )

    assert result == "browser"
    assert attempts == 3
    assert delays == [1, 2]


async def test_gateway_503_retry_is_total_bounded_and_names_the_cause():
    now = 0.0
    attempts = 0

    delays: list[float] = []

    async def always_busy(_timeout_seconds: float):
        nonlocal attempts
        attempts += 1
        raise RuntimeError(
            "WebSocket error: ws://pwmcp:3000/?token=connectionS3cret "
            "503 Service Unavailable; all 2 browser slots are in use"
        )

    async def fake_sleep(delay: float) -> None:
        nonlocal now
        delays.append(delay)
        now += delay

    with pytest.raises(GatewaySlotsBusyTimeout) as caught:
        await connect_with_bounded_retry(
            always_busy,
            total_timeout_seconds=3,
            initial_backoff_seconds=1,
            max_backoff_seconds=2,
            session_label="naf-e2e:e2e:gw0",
            clock=lambda: now,
            sleep=fake_sleep,
        )

    # total 3 s, backoff 1 then 2: attempt at t=0, sleep 1, attempt at t=1, sleep 2, deadline.
    assert attempts == 2
    assert delays == [1, 2]
    assert now == 3
    assert "all browser slots are in use" in str(caught.value)
    assert "naf-e2e:e2e:gw0" in str(caught.value)
    assert "connectionS3cret" not in str(caught.value)
    assert "connectionS3cret" not in repr(caught.value)


def test_contract_protocol_mismatch_is_a_clear_fail_fast_error():
    with pytest.raises(PwmcpContractError, match="protocol mismatch"):
        validate_contract(_contract("1.65"), installed_version="1.64.1")

    assert validate_contract(_contract("1.64"), installed_version="1.64.1") == "1.64"


async def test_dead_shared_browser_is_reconnected_once_then_reused():
    first = _FakeBrowser()
    replacement = _FakeBrowser()
    playwright = _FakePlaywright([first, replacement])
    session = SharedPwmcpSession(
        _options(),
        contract=_contract(),
        env=_LEASE_ENV,
        playwright_factory=lambda: _FakePlaywrightStarter(playwright),
    )

    await session.start()
    first._connected = False
    assert await session.ensure_connected() is replacement
    assert playwright.chromium.connect_calls == 2
    assert session.connects == 2
    assert session.reconnects == 1
    assert session.summary() == "pwmcp connects=2 reconnects=1 recycles=0 contexts=0"
    assert session.reconnect_causes == ["browser-disconnected"]

    assert await session.ensure_connected() is replacement
    assert playwright.chromium.connect_calls == 2

    await session.stop()


async def test_connection_recycles_at_file_boundary_and_elapsed_window_with_fake_clock():
    now = 0.0
    first, second, third = _FakeBrowser(), _FakeBrowser(), _FakeBrowser()
    playwright = _FakePlaywright([first, second, third])
    session = SharedPwmcpSession(
        _options(renew_margin=300, recycle_interval=1500),
        contract=_contract(max_lease_seconds=7200),
        env=_LEASE_ENV,
        playwright_factory=lambda: _FakePlaywrightStarter(playwright),
        clock=lambda: now,
    )

    await session.start()
    assert await session.prepare_for_test("features/test_one.py") is first
    now = 100.0
    assert await session.prepare_for_test("features/test_one.py") is first
    assert playwright.chromium.connect_calls == 1

    now = 200.0
    assert await session.prepare_for_test("features/test_two.py") is second
    assert first.close_calls == 1
    assert session.recycles == 1
    assert session.reconnect_causes == ["test-file-boundary"]

    now = 1700.0
    assert await session.prepare_for_test("features/test_two.py") is third
    assert second.close_calls == 1
    assert session.connects == 3
    assert session.reconnects == 2
    assert session.recycles == 2
    assert session.summary() == "pwmcp connects=3 reconnects=2 recycles=2 contexts=0"
    assert session.reconnect_causes == ["test-file-boundary", "recycle-window-expired"]

    await session.stop()


def test_role_storage_paths_are_isolated_and_anonymous_has_none(tmp_path):
    config = UiTestConfig()
    config.workdir = tmp_path

    admin_path = config.storage_state_path("admin")
    user_path = config.storage_state_path("user")
    anonymous_path = config.storage_state_path("anonymous")

    assert admin_path == tmp_path / "admin_auth_state.json"
    assert user_path == tmp_path / "user_auth_state.json"
    assert admin_path != user_path
    assert anonymous_path is None
    assert context_storage_state("admin", config.storage_state_path) == str(admin_path)
    assert context_storage_state("user", config.storage_state_path) == str(user_path)
    assert context_storage_state("anonymous", config.storage_state_path) is None


def test_connection_defaults_match_short_recycle_window_and_bounded_retry_policy():
    defaults = {
        "E2E_PWMCP_CONNECT_RETRY_TOTAL_SECONDS": "60",
        "E2E_PWMCP_CONNECT_RETRY_INITIAL_SECONDS": "15",
        "E2E_PWMCP_CONNECT_RETRY_MAX_SECONDS": "30",
        "E2E_PWMCP_CONNECT_TIMEOUT_SECONDS": "30",
        "E2E_PWMCP_CONTRACT_TIMEOUT_SECONDS": "10",
        "E2E_PWMCP_RECYCLE_INTERVAL_SECONDS": "1500",
        "E2E_PWMCP_LEASE_RENEW_MARGIN_SECONDS": "300",
        "E2E_PWMCP_MAX_RECONNECTS": "3",
    }
    options = load_connection_options(
        {"PLAYWRIGHT_SERVER_WS": "ws://pwmcp:3000/"},
        default_lookup=defaults.__getitem__,
    )

    assert options.retry_total_seconds == 60
    assert options.retry_initial_seconds == 15
    assert options.retry_max_seconds == 30
    assert options.recycle_interval_seconds == 1500
    assert options.lease_renew_margin_seconds == 300


def test_connection_error_redacts_endpoint_credentials_and_secret_query_values():
    error = RuntimeError(
        "WebSocket error: ws://user:pass@pwmcp:3000/path?token=connectionS3cret 403 Forbidden"
    )
    safe = safe_connection_error(error)

    assert "403 Forbidden" in safe
    assert "ws://pwmcp:3000/" in safe
    assert "user:pass" not in safe
    assert "connectionS3cret" not in safe


async def test_anonymous_browser_session_creates_context_without_storage_state(monkeypatch):
    calls: list[dict] = []

    class FakePage:
        url = "about:blank"

        async def set_viewport_size(self, _viewport):
            return None

        async def close(self):
            return None

    class FakeContext:
        def __init__(self):
            self.page = FakePage()

        async def new_page(self):
            return self.page

        def set_default_timeout(self, _timeout):
            return None

        async def close(self):
            return None

    class FakeSharedSession:
        async def ensure_connected(self):
            return object()

        async def new_context(self, **kwargs):
            calls.append(kwargs)
            return FakeContext()

    fake = FakeSharedSession()
    monkeypatch.setattr("ui_tests.pwmcp_connection._current_session", fake)
    monkeypatch.delenv("UI_TRACE_ON_SLOW_SECONDS", raising=False)

    async with browser_session("anonymous") as browser:
        assert browser._page.url == "about:blank"

    assert len(calls) == 1
    assert "storage_state" not in calls[0]


async def test_missing_role_storage_state_is_not_loaded(tmp_path):
    calls: list[dict] = []

    class FakeBrowser:
        def is_connected(self):
            return True

        async def new_context(self, **kwargs):
            calls.append(kwargs)
            return object()

    session = SharedPwmcpSession(
        _options(),
        contract=_contract(),
        env={},
    )
    session.browser = FakeBrowser()
    missing = tmp_path / "user_auth_state.json"

    await session.new_context(storage_state_path=str(missing))

    assert len(calls) == 1
    assert "storage_state" not in calls[0]


async def test_fill_error_redacts_typed_value_but_keeps_length():
    value = "S3cret-XYZ"

    class FailingPage:
        async def fill(self, selector: str, typed_value: str):
            raise RuntimeError(f"failed filling {selector}")

    with pytest.raises(ToolError) as caught:
        await Browser(FailingPage()).fill("#password", value)

    exc = caught.value
    assert value not in str(exc)
    assert value not in repr(exc)
    assert exc.payload == {"selector": "#password", "value_length": len(value)}


async def test_tool_errors_do_not_chain_the_unredacted_playwright_error():
    """pytest prints ``__context__``; the raw Playwright error (call log with the typed value or
    the full URL) must not ride along behind the redacted ToolError."""
    import traceback

    from playwright.async_api import TimeoutError as PlaywrightTimeout

    value = "S3cret-XYZ"
    token = "inviteS3cretTok"

    class Page:
        url = "about:blank"

        async def fill(self, selector: str, typed_value: str):
            raise RuntimeError(f'Call log:\n  - fill("{typed_value}")')

        async def goto(self, target, wait_until, timeout):
            raise PlaywrightTimeout(f'Timeout {timeout}ms exceeded.\nnavigating to "{target}"')

    with pytest.raises(ToolError) as fill_error:
        await Browser(Page()).fill("#password", value)
    with pytest.raises(ToolError) as goto_error:
        await Browser(Page()).goto(f"http://app:8000/account/invite/{token}", wait_until="domcontentloaded")

    for caught, secret in ((fill_error, value), (goto_error, token)):
        rendered = "".join(traceback.format_exception(caught.value))
        assert secret not in rendered
        assert caught.value.__suppress_context__


_LOG_LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log"}
_LOG_OWNERS = {"logger", "logging", "log", "_logger", "LOGGER", "LOG"}
_SECRET_WORDS = {"code", "password", "token", "secret", "totp"}
_NON_SECRET_METADATA = (
    "_id",
    "_name",
    "_length",
    "_len",
    "_present",
    "_count",
    "_prefix",
    "_hash",
    "_url",
    "_path",
    "_type",
)
_NON_SECRET_CODES = ("status_code", "error_code", "http_code", "response_code", "exit_code", "returncode")
# Only the length/truthiness/type of a secret may be printed or logged.
_SAFE_WRAPPERS = {"len", "bool", "type"}


def _is_secret_name(name: str) -> bool:
    name = name.lower()
    return name in _SECRET_WORDS or (
        name.split("_")[-1] in _SECRET_WORDS
        and not name.endswith(_NON_SECRET_METADATA)
        and name not in _NON_SECRET_CODES
    )


def _secret_names_in(node: ast.AST) -> set[str]:
    """Secret-looking variable and attribute names (``code``, ``settings.admin_password``)."""
    found: set[str] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if (
            isinstance(current, ast.Call)
            and isinstance(current.func, ast.Name)
            and current.func.id in _SAFE_WRAPPERS
        ):
            continue
        if isinstance(current, ast.Name) and _is_secret_name(current.id):
            found.add(current.id)
        elif isinstance(current, ast.Attribute) and _is_secret_name(current.attr):
            found.add(current.attr)
        stack.extend(ast.iter_child_nodes(current))
    return found


def _output_call_kind(node: ast.AST) -> str | None:
    """``print`` or ``<logger|logging>.<level>`` calls; anything else is not an output channel."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name) and func.id == "print":
        return "print"
    if (
        isinstance(func, ast.Attribute)
        and func.attr in _LOG_LEVELS
        and isinstance(func.value, ast.Name)
        and func.value.id in _LOG_OWNERS
    ):
        return f"{func.value.id}.{func.attr}"
    return None


def _secret_output_calls(source: str, filename: str = "<src>") -> list[tuple[int, str, list[str]]]:
    calls = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        kind = _output_call_kind(node)
        if kind is None:
            continue
        names: set[str] = set()
        for arg in [*node.args, *(keyword.value for keyword in node.keywords)]:
            names |= _secret_names_in(arg)
        calls.append((node.lineno, kind, sorted(names)))
    return calls


def test_secret_guard_covers_logging_calls_and_attribute_names():
    flagged = _secret_output_calls(
        "logger.info('admin %s', settings.admin_password)\n"
        "logging.warning('persona %s', persona.password)\n"
        "logger.debug('code=%s', code)\n"
        "log.error(f'token {api_token}')\n"
        "print(user.totp_secret)\n"
    )
    assert [names for _line, _kind, names in flagged] == [
        ["admin_password"],
        ["password"],
        ["code"],
        ["api_token"],
        ["totp_secret"],
    ]
    clean = _secret_output_calls(
        "logger.info('code length %d', len(code))\n"
        "logger.debug('status %s', response.status_code)\n"
        "logger.info('token %s', token_name)\n"
        "other.info(password)\n"
    )
    assert [names for _line, _kind, names in clean] == [[], [], []]


def test_ui_tests_do_not_print_and_never_print_or_log_secret_named_values():
    root = Path(__file__).resolve().parents[1]
    targets = sorted((root / "ui_tests").rglob("*.py"))
    workflows = root / "ui_tests" / "workflows.py"
    test_tree = root / "ui_tests" / "tests"
    offenders: list[str] = []

    for path in targets:
        in_no_print_scope = path == workflows or path.is_relative_to(test_tree)
        for lineno, kind, names in _secret_output_calls(path.read_text(encoding="utf-8"), str(path)):
            if names or (kind == "print" and in_no_print_scope):
                offenders.append(f"{path.relative_to(root)}:{lineno}: {kind}({names})")

    assert offenders == [], "debug print or secret-bearing print/log calls in ui_tests:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# M1: a failed reconnect is latched; reconnects are counted and capped
# ---------------------------------------------------------------------------


def _session(playwright: "_FakePlaywright", **option_overrides) -> SharedPwmcpSession:
    return SharedPwmcpSession(
        _options(**option_overrides),
        contract=_contract(),
        env=_LEASE_ENV,
        playwright_factory=lambda: _FakePlaywrightStarter(playwright),
    )


async def test_dead_replacement_browser_latches_and_never_reconnects_again():
    first = _FakeBrowser()
    dead_replacement = _FakeBrowser(connected=False)
    playwright = _FakePlaywright([first, dead_replacement])
    session = _session(playwright)

    await session.start()
    first._connected = False

    with pytest.raises(PwmcpConnectionClosed, match="remained disconnected"):
        await session.ensure_connected()
    assert playwright.chromium.connect_calls == 2

    with pytest.raises(PwmcpConnectionClosed, match="remained disconnected"):
        await session.ensure_connected()
    with pytest.raises(PwmcpConnectionClosed):
        await session.new_context()
    assert playwright.chromium.connect_calls == 2
    assert session.reconnects == 0
    assert any("latched" in line for line in session.summary_details())

    await session.stop()


async def test_failed_reconnect_attempt_is_latched_with_its_reason():
    first = _FakeBrowser()
    playwright = _FakePlaywright([first])
    session = _session(playwright)

    await session.start()
    first._connected = False
    playwright.chromium.errors.append(
        RuntimeError("WebSocket error: ws://user:pass@pwmcp:3000/?token=connectionS3cret 403 Forbidden")
    )

    with pytest.raises(PwmcpConnectionClosed, match="403 Forbidden") as caught:
        await session.ensure_connected()
    assert "connectionS3cret" not in str(caught.value)
    assert "user:pass" not in str(caught.value)
    with pytest.raises(PwmcpConnectionClosed, match="403 Forbidden"):
        await session.ensure_connected()
    assert playwright.chromium.connect_calls == 2

    await session.stop()


async def test_initial_connect_error_redacts_endpoint_credentials_and_query_values():
    playwright = _FakePlaywright([_FakeBrowser()])
    playwright.chromium.errors.append(
        RuntimeError(
            "WebSocket error: ws://user:pass@pwmcp:3000/path?token=initialS3cret 403 Forbidden"
        )
    )
    session = _session(playwright)

    with pytest.raises(RuntimeError, match="403 Forbidden") as caught:
        await session.start()

    assert "user:pass" not in str(caught.value)
    assert "initialS3cret" not in str(caught.value)
    assert "ws://pwmcp:3000/" in str(caught.value)
    assert caught.value.__cause__ is None
    await session.stop()


async def test_browser_deaths_beyond_the_reconnect_cap_latch_without_connecting():
    browsers = [_FakeBrowser(), _FakeBrowser(), _FakeBrowser()]
    playwright = _FakePlaywright(browsers)
    session = _session(playwright, max_reconnects=1)

    await session.start()
    browsers[0]._connected = False
    assert await session.ensure_connected() is browsers[1]
    browsers[1]._connected = False

    with pytest.raises(PwmcpConnectionClosed, match="E2E_PWMCP_MAX_RECONNECTS=1"):
        await session.ensure_connected()
    assert playwright.chromium.connect_calls == 2
    assert session.summary() == "pwmcp connects=2 reconnects=1 recycles=0 contexts=0"

    await session.stop()


async def test_session_stop_is_idempotent_and_closes_browser_and_driver():
    browser = _FakeBrowser()
    playwright = _FakePlaywright([browser])
    session = _session(playwright)
    await session.start()

    await session.stop()
    await session.stop()

    assert browser.close_calls == 1
    assert playwright.stop_calls == 1
    assert session.browser is None
    assert session._playwright is None


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
async def test_process_signal_closes_browser_before_forwarding_signal(signum):
    browser = _FakeBrowser()
    playwright = _FakePlaywright([browser])
    session = _session(playwright)
    await session.start()

    class FakeSignalApi:
        SIGTERM = signal.SIGTERM
        SIGINT = signal.SIGINT

        def __init__(self):
            self.old = {self.SIGTERM: object(), self.SIGINT: object()}
            self.restored = {}

        def getsignal(self, number):
            return self.old[number]

        def signal(self, number, handler):
            self.restored[number] = handler

    class FakeProcessApi:
        def __init__(self):
            self.kills = []

        def getpid(self):
            return 4242

        def kill(self, pid, number):
            self.kills.append((pid, number))

    class RecordingLoop:
        def __init__(self, actual_loop):
            self.actual_loop = actual_loop
            self.handlers = {}
            self.tasks = []

        def add_signal_handler(self, number, callback, *args):
            self.handlers[number] = (callback, args)

        def remove_signal_handler(self, number):
            self.handlers.pop(number, None)
            return True

        def create_task(self, coroutine):
            task = self.actual_loop.create_task(coroutine)
            self.tasks.append(task)
            return task

    signal_api = FakeSignalApi()
    process_api = FakeProcessApi()
    loop = RecordingLoop(asyncio.get_running_loop())
    restore = install_signal_cleanup(
        session,
        loop,
        signal_api=signal_api,
        process_api=process_api,
    )

    callback, args = loop.handlers[signum]
    callback(*args)
    await loop.tasks[0]

    assert browser.close_calls == 1
    assert playwright.stop_calls == 1
    assert process_api.kills == [(4242, signum)]
    assert signal_api.restored == signal_api.old
    restore()
    await session.stop()
    assert browser.close_calls == 1


# ---------------------------------------------------------------------------
# M2: the session lease is renewed between tests before the gateway ends it
# ---------------------------------------------------------------------------


async def test_lease_is_renewed_between_tests_when_under_the_margin():
    now = 0.0
    first = _FakeBrowser()
    second = _FakeBrowser()
    playwright = _FakePlaywright([first, second])
    session = SharedPwmcpSession(
        _options(renew_margin=300, recycle_interval=1500),
        contract=_contract(max_lease_seconds=7200),
        env=_LEASE_ENV,
        playwright_factory=lambda: _FakePlaywrightStarter(playwright),
        clock=lambda: now,
    )

    await session.start()
    assert session.lease_remaining_seconds() == 1800

    now = 1499.0
    assert await session.ensure_connected() is first
    assert playwright.chromium.connect_calls == 1

    # Under the margin, but a test still holds a context: never renew mid-test.
    now = 1501.0
    first.contexts.append(_FakeContext())
    assert await session.ensure_connected() is first
    assert playwright.chromium.connect_calls == 1

    # Between tests (no open context): close the old lease first, then reconnect.
    first.contexts.clear()
    assert await session.ensure_connected() is second
    assert first.close_calls == 1
    assert playwright.chromium.connect_calls == 2
    assert session.reconnects == 1
    assert session.reconnect_causes[0].startswith("lease-renewal")
    assert session.lease_remaining_seconds() == 1800

    await session.stop()


async def test_renew_margin_not_below_the_granted_lease_fails_fast():
    playwright = _FakePlaywright([_FakeBrowser()])
    session = SharedPwmcpSession(
        _options(renew_margin=600, recycle_interval=100),
        contract=_contract(max_lease_seconds=500),
        env=_LEASE_ENV,
        playwright_factory=lambda: _FakePlaywrightStarter(playwright),
    )

    with pytest.raises(RuntimeError, match="E2E_PWMCP_LEASE_RENEW_MARGIN_SECONDS"):
        await session.start()
    assert playwright.chromium.connect_calls == 0


# ---------------------------------------------------------------------------
# H1: ParallelSessionManager never hands Playwright a missing storage-state file
# ---------------------------------------------------------------------------


def _recording_factory(calls: list[dict]):
    async def factory(**kwargs):
        calls.append(kwargs)
        return _FakeContext()

    return factory


async def test_psm_missing_role_storage_state_is_not_passed_to_playwright(tmp_path):
    calls: list[dict] = []
    manager = ParallelSessionManager(browser=object(), context_factory=_recording_factory(calls))
    missing = tmp_path / "user_auth_state.json"

    await manager.create_session("account", storage_state_path=str(missing))

    assert len(calls) == 1
    assert "storage_state" not in calls[0]


async def test_psm_admin_session_loads_the_role_file_once_it_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workdir", tmp_path)
    calls: list[dict] = []

    first = ParallelSessionManager(browser=object(), context_factory=_recording_factory(calls))
    await first.admin_session(login=False)
    assert "storage_state" not in calls[-1]

    admin_file = tmp_path / "admin_auth_state.json"
    admin_file.write_text(json.dumps({"cookies": [], "origins": []}), encoding="utf-8")
    second = ParallelSessionManager(browser=object(), context_factory=_recording_factory(calls))
    await second.admin_session(login=False)
    assert calls[-1]["storage_state"] == str(admin_file)


# ---------------------------------------------------------------------------
# L2: navigation/request failures never carry one-time tokens
# ---------------------------------------------------------------------------


async def test_goto_failure_redacts_one_time_path_tokens_and_secret_query_values():
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    secret = "inviteS3cretTok"
    url = f"http://app:8000/account/invite/{secret}?next=/x&token={secret}Q"

    class Page:
        url = "about:blank"

        async def goto(self, target, wait_until, timeout):
            raise PlaywrightTimeout(f'Timeout {timeout}ms exceeded.\nnavigating to "{target}"')

    with pytest.raises(ToolError) as caught:
        await Browser(Page()).goto(url, wait_until="domcontentloaded")

    exc = caught.value
    assert secret not in str(exc)
    assert secret not in repr(exc)
    assert exc.payload["url"] == "http://app:8000/account/invite/<redacted>?next=/x&token=<redacted>"


@pytest.mark.parametrize("path", ["/account/register/verify/", "/account/reset-password/"])
async def test_request_failure_redacts_tokens_in_url_params_and_message(path):
    secret = "oneTimeS3cret"
    url = f"http://app:8000{path}{secret}"

    class Request:
        async def get(self, target, params=None, timeout=None):
            raise RuntimeError(f"APIRequestContext.get: socket hang up {target}?token={params['token']}")

    class Page:
        request = Request()

    with pytest.raises(ToolError) as caught:
        await Browser(Page()).request_get_json(url, params={"token": secret, "page": 1})

    exc = caught.value
    assert secret not in str(exc)
    assert secret not in repr(exc)
    assert exc.payload["params"] == {"token": "<redacted>", "page": 1}


# ---------------------------------------------------------------------------
# L3 / L4: PlaywrightClient attaches to the shared session and never leaks a context
# ---------------------------------------------------------------------------


class _RecordingSharedSession:
    def __init__(self, context: _FakeContext) -> None:
        self.context = context
        self.ensure_calls = 0
        self.context_kwargs: list[dict] = []

    async def ensure_connected(self):
        self.ensure_calls += 1
        return object()

    async def new_context(self, **kwargs):
        self.context_kwargs.append(kwargs)
        return self.context


def _forbid_driver_start():
    raise AssertionError("async_playwright() must not start a driver while a shared session is installed")


async def test_playwright_client_uses_the_installed_shared_session_only(monkeypatch):
    shared = _RecordingSharedSession(_FakeContext())
    monkeypatch.setattr("ui_tests.pwmcp_connection._current_session", shared)
    monkeypatch.setattr("ui_tests.playwright_client.async_playwright", _forbid_driver_start)

    client = PlaywrightClient(headless=True, storage_state_path="/nonexistent/admin_auth_state.json")
    await client.connect()
    assert shared.ensure_calls == 1
    assert shared.context_kwargs == [{"storage_state_path": "/nonexistent/admin_auth_state.json"}]

    await client.close()
    assert shared.context.close_calls == 1


async def test_playwright_client_closes_its_context_when_page_creation_fails(monkeypatch):
    shared = _RecordingSharedSession(_FakeContext(page_error=RuntimeError("Target closed")))
    monkeypatch.setattr("ui_tests.pwmcp_connection._current_session", shared)
    monkeypatch.setattr("ui_tests.playwright_client.async_playwright", _forbid_driver_start)

    with pytest.raises(RuntimeError, match="Target closed"):
        await PlaywrightClient(headless=True).connect()
    assert shared.context.close_calls == 1


async def test_browser_session_closes_the_context_when_tracing_stop_fails(monkeypatch, tmp_path):
    class FailingTracing:
        async def start(self, **_kwargs):
            return None

        async def stop(self, **_kwargs):
            raise RuntimeError("tracing stop failed")

    context = _FakeContext()
    context.tracing = FailingTracing()
    shared = _RecordingSharedSession(context)
    monkeypatch.setattr("ui_tests.pwmcp_connection._current_session", shared)
    monkeypatch.setenv("UI_TRACE_ON_SLOW_SECONDS", "0.000001")
    monkeypatch.setenv("UI_TRACE_DIR", str(tmp_path))

    with pytest.raises(RuntimeError, match="tracing stop failed"):
        async with browser_session("anonymous"):
            pass
    assert context.close_calls == 1


async def test_standalone_remote_client_uses_contract_lease_and_configured_timeout(monkeypatch):
    browser = _FakeBrowser()
    playwright = _FakePlaywright([browser])
    contract_calls: list[tuple[str, float]] = []

    def fake_fetch_contract(ws_url, *, timeout_seconds):
        contract_calls.append((ws_url, timeout_seconds))
        return _contract(max_lease_seconds=900)

    monkeypatch.setattr("ui_tests.pwmcp_connection._current_session", None)
    monkeypatch.setattr("ui_tests.playwright_client.fetch_contract", fake_fetch_contract)
    monkeypatch.setattr(
        "ui_tests.playwright_client.async_playwright", lambda: _FakePlaywrightStarter(playwright)
    )
    for key, value in {
        "PLAYWRIGHT_SERVER_WS": "ws://pwmcp:3000/",
        "E2E_PWMCP_LANE_NAME": "e2e",
        "E2E_PWMCP_CONTRACT_TIMEOUT_SECONDS": "4",
        "E2E_PWMCP_CONNECT_TIMEOUT_SECONDS": "7",
        "E2E_PWMCP_CONNECT_RETRY_TOTAL_SECONDS": "20",
        "E2E_PWMCP_CONNECT_RETRY_INITIAL_SECONDS": "1",
        "E2E_PWMCP_CONNECT_RETRY_MAX_SECONDS": "2",
        "E2E_PWMCP_RECYCLE_INTERVAL_SECONDS": "1500",
        "E2E_PWMCP_LEASE_RENEW_MARGIN_SECONDS": "60",
        "E2E_PWMCP_MAX_RECONNECTS": "0",
    }.items():
        monkeypatch.setenv(key, value)

    client = PlaywrightClient(headless=True)
    await client.connect()

    assert contract_calls == [("ws://pwmcp:3000/", 4.0)]
    assert playwright.chromium.connect_calls == 1
    kwargs = playwright.chromium.connect_kwargs[0]
    assert kwargs["timeout"] == 7000
    assert kwargs["headers"] == {
        "X-PWMCP-Lease-Seconds": "900",
        "X-PWMCP-Session-Label": pwmcp_session_label({"E2E_PWMCP_LANE_NAME": "e2e"}),
    }

    await client.close()
    assert browser.contexts[0].close_calls == 1
    assert browser.close_calls == 1
    assert playwright.stop_calls == 1


# ---------------------------------------------------------------------------
# L6: the real 503 text, the lease cap and the contract's fail-closed paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        REAL_PLAYWRIGHT_503,
        "BrowserType.connect: WebSocket error: ws://pwmcp:3000/ 503 Service Unavailable\n"
        "pwmcp: all 2 browser slots are in use; retry later",
    ],
)
async def test_real_playwright_503_text_is_retried(message):
    now = 0.0
    attempts = 0

    async def busy_then_free(_timeout_seconds: float):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError(message)
        return "browser"

    async def fake_sleep(delay: float) -> None:
        nonlocal now
        now += delay

    assert is_gateway_slots_busy(RuntimeError(message))
    result = await connect_with_bounded_retry(
        busy_then_free,
        total_timeout_seconds=10,
        initial_backoff_seconds=1,
        max_backoff_seconds=2,
        clock=lambda: now,
        sleep=fake_sleep,
    )
    assert result == "browser"
    assert attempts == 2


async def test_non_503_connect_errors_are_not_retried():
    attempts = 0

    async def forbidden(_timeout_seconds: float):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("WebSocket error: ws://pwmcp:3000/ 403 Forbidden\nHost not allowed")

    async def no_sleep(_delay: float) -> None:
        raise AssertionError("a non-503 error must not be retried")

    with pytest.raises(RuntimeError, match="403 Forbidden"):
        await connect_with_bounded_retry(
            forbidden,
            total_timeout_seconds=10,
            initial_backoff_seconds=1,
            max_backoff_seconds=2,
            clock=lambda: 0.0,
            sleep=no_sleep,
        )
    assert attempts == 1


def test_lease_headers_are_capped_by_the_contract_and_validated():
    contract = _contract(max_lease_seconds=7200)
    assert lease_headers({"E2E_PWMCP_LANE_NAME": "e2e"}, contract, 9000) == {
        "X-PWMCP-Lease-Seconds": "7200",
        "X-PWMCP-Session-Label": pwmcp_session_label({"E2E_PWMCP_LANE_NAME": "e2e"}),
    }
    assert lease_headers({"E2E_PWMCP_LANE_NAME": "e2e"}, contract, 600)[
        "X-PWMCP-Lease-Seconds"
    ] == "600"
    long_lane_env = {"E2E_PWMCP_LANE_NAME": "e" * 200, "PYTEST_XDIST_WORKER": "gw2"}
    assert lease_headers(long_lane_env, contract, 600)["X-PWMCP-Session-Label"] == (
        f"naf-e2e:{'e' * (128 - len('naf-e2e:') - len(':gw2'))}:gw2"
    )
    assert pwmcp_session_label({"E2E_PWMCP_LANE_NAME": "e2e"}, process_id=7) == "naf-e2e:e2e:7"
    assert pwmcp_session_label(
        {"E2E_PWMCP_LANE_NAME": "e2e", "PYTEST_XDIST_WORKER": "gw3"}, process_id=7
    ) == "naf-e2e:e2e:gw3"
    with pytest.raises(RuntimeError, match="positive integer"):
        lease_headers({"E2E_PWMCP_LANE_NAME": "e2e"}, contract, 0)
    with pytest.raises(RuntimeError, match="positive integer"):
        lease_headers({"E2E_PWMCP_LANE_NAME": "e2e"}, contract, 1.5)


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self) -> bytes:
        return self._body


def _opener_returning(body: bytes):
    def opener(url, *, timeout):
        assert url == "http://pwmcp:3000/contract"
        assert timeout == 5
        return _Response(body)

    return opener


def _opener_raising(exc: BaseException):
    def opener(_url, *, timeout):
        raise exc

    return opener


def _contract_bytes(**overrides) -> bytes:
    contract = _contract(installed_playwright_protocol())
    contract.update(overrides)
    return json.dumps(contract).encode()


@pytest.mark.parametrize(
    ("opener", "message"),
    [
        (_opener_raising(OSError("connection refused")), "contract unavailable"),
        (_opener_raising(urllib.error.URLError("name resolution")), "contract unavailable"),
        (_opener_returning(b"<html>not json</html>"), "not valid JSON"),
        (_opener_returning(b"[]"), "must be a JSON object"),
        (_opener_returning(_contract_bytes(schema_version=2)), "schema_version"),
        (_opener_returning(_contract_bytes(playwright=None)), "playwright object"),
        (_opener_returning(_contract_bytes(run_server={"limits": {}})), "max_lease_seconds"),
    ],
)
def test_fetch_contract_fails_closed(opener, message):
    with pytest.raises(PwmcpContractError, match=message):
        fetch_contract("ws://pwmcp:3000/", timeout_seconds=5, opener=opener)


def test_contract_transport_error_does_not_echo_url_credentials_or_query_secrets():
    with pytest.raises(PwmcpContractError) as caught:
        fetch_contract(
            "ws://user:pass@pwmcp:3000/?token=connectionS3cret",
            timeout_seconds=5,
            opener=_opener_raising(OSError("connection refused")),
        )

    assert "http://pwmcp:3000/contract" in str(caught.value)
    assert "user:pass" not in str(caught.value)
    assert "connectionS3cret" not in str(caught.value)


def test_fetch_contract_accepts_a_matching_contract_and_rejects_non_ws_urls():
    contract = fetch_contract("ws://pwmcp:3000/", timeout_seconds=5, opener=_opener_returning(_contract_bytes()))
    assert contract["playwright"]["protocol"] == installed_playwright_protocol()
    assert contract_url_from_ws("wss://pwmcp.example:443/x") == "https://pwmcp.example:443/contract"
    with pytest.raises(PwmcpContractError, match="ws\\(s\\) URL"):
        contract_url_from_ws("http://pwmcp:3000/")
    with pytest.raises(PwmcpContractError, match="invalid port"):
        contract_url_from_ws("ws://pwmcp:not-a-port/")

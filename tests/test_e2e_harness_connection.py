"""Unit contracts for the session-scoped browser harness.

These tests exercise the harness without Playwright, browsers, pytest fixtures
from the e2e lane, or network access.  Their fakes deliberately expose the old
per-test connection and shared-storage behaviour as failures.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ui_tests.browser import Browser, ToolError, browser_session
from ui_tests.config import UiTestConfig
from ui_tests.pwmcp_connection import (
    ConnectionOptions,
    GatewaySlotsBusyTimeout,
    PwmcpContractError,
    SharedPwmcpSession,
    connect_with_bounded_retry,
    context_storage_state,
    validate_contract,
)


def _contract(protocol: str = "1.64", max_lease_seconds: int = 7200) -> dict:
    return {
        "schema_version": 1,
        "playwright": {"python": f"{protocol}.1", "protocol": protocol},
        "run_server": {"limits": {"max_lease_seconds": max_lease_seconds}},
    }


def _options(*, remote: bool = True) -> ConnectionOptions:
    return ConnectionOptions(
        ws_url="ws://pwmcp:3000/" if remote else "",
        connect_timeout_seconds=30,
        retry_total_seconds=120,
        retry_initial_seconds=1,
        retry_max_seconds=8,
        contract_timeout_seconds=10,
    )


class _FakeBrowser:
    def __init__(self, *, connected: bool = True) -> None:
        self._connected = connected
        self.close_calls = 0

    def is_connected(self) -> bool:
        return self._connected

    async def close(self) -> None:
        self.close_calls += 1
        self._connected = False


class _FakeBrowserType:
    def __init__(self, browsers: list[_FakeBrowser]) -> None:
        self._browsers = browsers
        self.connect_calls = 0

    async def connect(self, _url: str, **_kwargs) -> _FakeBrowser:
        self.connect_calls += 1
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

    async def always_busy(_timeout_seconds: float):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("Unexpected server response: 503")

    async def fake_sleep(delay: float) -> None:
        nonlocal now
        now += delay

    with pytest.raises(GatewaySlotsBusyTimeout, match="all browser slots are in use"):
        await connect_with_bounded_retry(
            always_busy,
            total_timeout_seconds=3,
            initial_backoff_seconds=1,
            max_backoff_seconds=2,
            clock=lambda: now,
            sleep=fake_sleep,
        )

    assert 1 <= attempts <= 4
    assert now <= 3


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
        env={"PWMCP_LEASE_SECONDS": "600", "PWMCP_SESSION_LABEL": "unit-harness"},
        playwright_factory=lambda: _FakePlaywrightStarter(playwright),
    )

    await session.start()
    first._connected = False
    assert await session.ensure_connected() is replacement
    assert playwright.chromium.connect_calls == 2
    assert session.connects == 2

    assert await session.ensure_connected() is replacement
    assert playwright.chromium.connect_calls == 2

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


def test_ui_tests_do_not_print_and_never_print_secret_named_values():
    root = Path(__file__).resolve().parents[1]
    targets = sorted((root / "ui_tests").rglob("*.py"))
    no_print_roots = (root / "ui_tests" / "workflows.py", root / "ui_tests" / "tests")
    offenders: list[str] = []
    secret_words = {"code", "password", "token"}
    non_secret_metadata = (
        "_id",
        "_name",
        "_length",
        "_present",
        "_count",
        "_prefix",
        "_hash",
    )
    non_secret_codes = ("status_code", "error_code", "http_code", "response_code")

    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                continue
            secret_names = set()
            for child in ast.walk(node):
                if not isinstance(child, ast.Name):
                    continue
                name = child.id.lower()
                parts = name.split("_")
                if (
                    name in secret_words
                    or (
                        parts[-1] in secret_words
                        and not name.endswith(non_secret_metadata)
                        and name not in non_secret_codes
                    )
                ):
                    secret_names.add(child.id)
            in_no_print_scope = path == no_print_roots[0] or path.is_relative_to(no_print_roots[1])
            if in_no_print_scope or secret_names:
                offenders.append(f"{path.relative_to(root)}:{node.lineno}: print({sorted(secret_names)})")

    assert offenders == [], "debug/secret-bearing print calls in ui_tests:\n" + "\n".join(offenders)

"""Session-scoped Playwright connection lifecycle for the e2e suite.

The module-level connection is installed by ``ui_tests/conftest.py``. Concrete
Playwright imports stay lazy so the unit lane can exercise the retry, contract,
and storage-selection rules without a browser.
"""
from __future__ import annotations

import importlib.metadata
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)


class PwmcpContractError(RuntimeError):
    """The gateway contract is unavailable or incompatible with this client."""


class GatewaySlotsBusyTimeout(RuntimeError):
    """The gateway kept rejecting a connection because all browser slots were busy."""


class PwmcpConnectionClosed(RuntimeError):
    """The shared browser connection is unusable and could not be replaced."""


@dataclass(frozen=True)
class ConnectionOptions:
    ws_url: str
    connect_timeout_seconds: float
    retry_total_seconds: float
    retry_initial_seconds: float
    retry_max_seconds: float
    contract_timeout_seconds: float
    lease_renew_margin_seconds: float
    max_reconnects: int
    browser_type: str = "chromium"


def _settable_env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def _config_value(
    key: str,
    env: Mapping[str, str] | None,
    default_lookup: Callable[[str], str] | None,
) -> str:
    value = _settable_env(env).get(key, "").strip()
    if value:
        return value
    if default_lookup is None:
        from netcup_api_filter.config_defaults import require_default

        default_lookup = require_default
    return str(default_lookup(key)).strip()


def _positive_float(
    key: str,
    env: Mapping[str, str] | None,
    default_lookup: Callable[[str], str] | None,
) -> float:
    raw = _config_value(key, env, default_lookup)
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{key} must be a positive number, got {raw!r}") from exc
    if value <= 0:
        raise RuntimeError(f"{key} must be a positive number, got {raw!r}")
    return value


def _non_negative_int(
    key: str,
    env: Mapping[str, str] | None,
    default_lookup: Callable[[str], str] | None,
) -> int:
    raw = _config_value(key, env, default_lookup)
    if not re.fullmatch(r"[0-9]+", raw):
        raise RuntimeError(f"{key} must be a non-negative integer, got {raw!r}")
    return int(raw)


def load_connection_options(
    env: Mapping[str, str] | None = None,
    *,
    default_lookup: Callable[[str], str] | None = None,
) -> ConnectionOptions:
    """Read all timeout/backoff bounds from env or ``.env.defaults``."""
    env = _settable_env(env)
    retry_total = _positive_float("E2E_PWMCP_CONNECT_RETRY_TOTAL_SECONDS", env, default_lookup)
    initial = _positive_float("E2E_PWMCP_CONNECT_RETRY_INITIAL_SECONDS", env, default_lookup)
    maximum = _positive_float("E2E_PWMCP_CONNECT_RETRY_MAX_SECONDS", env, default_lookup)
    connect_timeout = _positive_float("E2E_PWMCP_CONNECT_TIMEOUT_SECONDS", env, default_lookup)
    contract_timeout = _positive_float("E2E_PWMCP_CONTRACT_TIMEOUT_SECONDS", env, default_lookup)
    renew_margin = _positive_float("E2E_PWMCP_LEASE_RENEW_MARGIN_SECONDS", env, default_lookup)
    max_reconnects = _non_negative_int("E2E_PWMCP_MAX_RECONNECTS", env, default_lookup)
    if initial > maximum:
        raise RuntimeError("E2E_PWMCP_CONNECT_RETRY_INITIAL_SECONDS exceeds the maximum backoff")
    return ConnectionOptions(
        ws_url=env.get("PLAYWRIGHT_SERVER_WS", "").strip(),
        connect_timeout_seconds=connect_timeout,
        retry_total_seconds=retry_total,
        retry_initial_seconds=initial,
        retry_max_seconds=maximum,
        contract_timeout_seconds=contract_timeout,
        lease_renew_margin_seconds=renew_margin,
        max_reconnects=max_reconnects,
    )


def contract_url_from_ws(ws_url: str) -> str:
    """Map ``ws[s]://host/`` to the matching gateway ``/contract`` URL."""
    parts = urlsplit(ws_url)
    if parts.scheme not in {"ws", "wss"} or not parts.netloc:
        raise PwmcpContractError(f"PLAYWRIGHT_SERVER_WS must be an absolute ws(s) URL, got {ws_url!r}")
    scheme = "https" if parts.scheme == "wss" else "http"
    return urlunsplit((scheme, parts.netloc, "/contract", "", ""))


def installed_playwright_protocol(version: str | None = None) -> str:
    """Return the installed Playwright package's major.minor wire protocol."""
    value = version or importlib.metadata.version("playwright")
    match = re.match(r"^(\d+)\.(\d+)", value.strip())
    if not match:
        raise PwmcpContractError(f"cannot determine Playwright's protocol from installed version {value!r}")
    return f"{match.group(1)}.{match.group(2)}"


def validate_contract(
    contract: Mapping[str, Any],
    *,
    installed_version: str | None = None,
) -> str:
    """Fail closed unless the gateway and installed Playwright share major.minor."""
    if contract.get("schema_version") != 1:
        raise PwmcpContractError(
            f"unsupported pwmcp contract schema_version={contract.get('schema_version')!r}; expected 1"
        )
    playwright = contract.get("playwright")
    if not isinstance(playwright, Mapping):
        raise PwmcpContractError("pwmcp contract is missing its playwright object")
    gateway_protocol = str(playwright.get("protocol") or "").strip()
    gateway_python = str(playwright.get("python") or "").strip()
    if not gateway_protocol:
        raise PwmcpContractError("pwmcp contract is missing playwright.protocol")
    installed_protocol = installed_playwright_protocol(installed_version)
    if installed_protocol != gateway_protocol:
        install_hint = f"playwright=={gateway_python}" if gateway_python else f"playwright {gateway_protocol}.x"
        raise PwmcpContractError(
            "pwmcp/Playwright protocol mismatch: "
            f"installed playwright uses {installed_protocol}, gateway uses {gateway_protocol}; "
            f"install {install_hint} or roll the gateway back"
        )
    limits = contract.get("run_server", {}).get("limits", {})
    if not isinstance(limits, Mapping) or not limits.get("max_lease_seconds"):
        raise PwmcpContractError("pwmcp contract is missing run_server.limits.max_lease_seconds")
    return gateway_protocol


def fetch_contract(
    ws_url: str,
    *,
    timeout_seconds: float,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Fetch and validate the gateway contract once at session start."""
    url = contract_url_from_ws(ws_url)
    try:
        with opener(url, timeout=timeout_seconds) as response:
            body = response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise PwmcpContractError(f"pwmcp contract unavailable at {url}: {exc}") from exc
    try:
        contract = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise PwmcpContractError(f"pwmcp contract at {url} is not valid JSON: {exc}") from exc
    if not isinstance(contract, dict):
        raise PwmcpContractError(f"pwmcp contract at {url} must be a JSON object")
    validate_contract(contract)
    return contract


def is_gateway_slots_busy(exc: BaseException) -> bool:
    """Recognise the gateway's HTTP 503 upgrade rejection."""
    message = str(exc).lower()
    return (
        "http 503" in message
        or "status 503" in message
        or "unexpected server response: 503" in message
        or "browser slots are in use" in message
        or "service unavailable" in message
    )


async def connect_with_bounded_retry(
    connect_once: Callable[[float], Awaitable[Any]],
    *,
    total_timeout_seconds: float,
    initial_backoff_seconds: float,
    max_backoff_seconds: float,
    is_retryable: Callable[[BaseException], bool] = is_gateway_slots_busy,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> Any:
    """Retry only gateway-busy failures, with one total deadline.

    ``connect_once`` receives the per-attempt timeout in seconds. The deadline,
    backoff values, clock, and sleep function are inputs so the behaviour is
    deterministic in the unit lane.
    """
    if sleep is None:
        import asyncio

        sleep = asyncio.sleep
    started = clock()
    deadline = started + total_timeout_seconds
    backoff = initial_backoff_seconds
    last_error: BaseException | None = None
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            break
        try:
            return await connect_once(remaining)
        except Exception as exc:
            if not is_retryable(exc):
                raise
            last_error = exc
        remaining = deadline - clock()
        if remaining <= 0:
            break
        delay = min(backoff, max_backoff_seconds, remaining)
        await sleep(delay)
        backoff = min(backoff * 2, max_backoff_seconds)
    detail = f"last error: {last_error}" if last_error else "deadline expired before the first attempt"
    raise GatewaySlotsBusyTimeout(
        "pwmcp connect gave up: the gateway kept returning HTTP 503 "
        f"(all browser slots are in use) for {total_timeout_seconds:g}s; another e2e session "
        f"or worktree holds a gateway lease ({detail})"
    ) from last_error


def lease_headers(env: Mapping[str, str], contract: Mapping[str, Any]) -> dict[str, str]:
    """Build the lease headers carried by the single session connection."""
    lease_raw = env.get("PWMCP_LEASE_SECONDS", "").strip()
    label = env.get("PWMCP_SESSION_LABEL", "").strip()
    if not lease_raw or not label:
        raise RuntimeError(
            "PLAYWRIGHT_SERVER_WS is set but PWMCP_LEASE_SECONDS / PWMCP_SESSION_LABEL are not: "
            "the runner must supply both lease values configured for the pwmcp gateway"
        )
    if not re.fullmatch(r"[1-9][0-9]*", lease_raw):
        raise RuntimeError(f"PWMCP_LEASE_SECONDS must be a positive integer, got {lease_raw!r}")
    max_lease = int(contract["run_server"]["limits"]["max_lease_seconds"])
    lease = min(int(lease_raw), max_lease)
    return {"X-PWMCP-Lease-Seconds": str(lease), "X-PWMCP-Session-Label": label[:128]}


def existing_storage_state(path: str | os.PathLike[str] | None) -> str | None:
    """Return ``path`` only when the file exists, so Playwright never reads a missing file.

    Role files are written after the first successful login of the session. Until then a
    context for that role starts empty and the login helpers (``ensure_*_dashboard``) log in
    and write the file.
    """
    if not path:
        return None
    if Path(path).is_file():
        return str(path)
    logger.warning(
        "role storage state does not exist yet; starting this context without cached auth: %s",
        path,
    )
    return None


def context_storage_state(
    role: str,
    path_for_role: Callable[[str], Path | None],
) -> str | None:
    """Return a storage-state path for named roles; anonymous always starts empty."""
    role = role.strip().lower()
    if not role:
        raise ValueError("browser role must not be empty")
    if role == "anonymous":
        return None
    path = path_for_role(role)
    return str(path) if path is not None else None


class SharedPwmcpSession:
    """Own one Playwright driver and one gateway browser for the pytest session."""

    def __init__(
        self,
        options: ConnectionOptions,
        *,
        contract: Mapping[str, Any] | None,
        env: Mapping[str, str] | None = None,
        playwright_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.options = options
        self.contract = contract
        self.env = _settable_env(env)
        self._playwright_factory = playwright_factory
        self._clock = clock
        self._sleep = sleep
        self._playwright: Any = None
        self.browser: Any = None
        self.connects = 0
        self.reconnects = 0
        self.contexts = 0
        self.reconnect_causes: list[str] = []
        self._recoveries = 0
        self._fatal_reason: str | None = None
        self._lease_seconds: int | None = None
        self._lease_started_at: float | None = None

    @property
    def remote(self) -> bool:
        return bool(self.options.ws_url)

    async def start(self) -> None:
        if self._playwright is None:
            if self._playwright_factory is None:
                from playwright.async_api import async_playwright

                self._playwright_factory = async_playwright
            self._playwright = await self._playwright_factory().start()
        await self._connect_browser()
        if not self.connected():
            raise PwmcpConnectionClosed("the shared browser was disconnected immediately after connect")

    async def _connect_browser(self) -> None:
        if not self.remote:
            self.browser = await self._launch_local()
            return
        if self.contract is None:
            raise PwmcpContractError("remote pwmcp mode has no validated gateway contract")
        headers = lease_headers(self.env, self.contract)
        lease = int(headers["X-PWMCP-Lease-Seconds"])
        if self.options.lease_renew_margin_seconds >= lease:
            raise RuntimeError(
                "E2E_PWMCP_LEASE_RENEW_MARGIN_SECONDS "
                f"({self.options.lease_renew_margin_seconds:g}) must be smaller than the granted "
                f"pwmcp lease ({lease}s); otherwise every test would reconnect"
            )
        browser_type = getattr(self._playwright, self.options.browser_type, self._playwright.chromium)
        attempt_started: list[float] = []

        async def connect_once(remaining_seconds: float) -> Any:
            timeout_ms = max(1, int(min(self.options.connect_timeout_seconds, remaining_seconds) * 1000))
            # The gateway starts the lease when it accepts the upgrade; the attempt start is
            # the conservative (earlier) bound for it.
            attempt_started.append(self._clock())
            return await browser_type.connect(
                self.options.ws_url,
                headers=headers,
                timeout=timeout_ms,
            )

        self.browser = await connect_with_bounded_retry(
            connect_once,
            total_timeout_seconds=self.options.retry_total_seconds,
            initial_backoff_seconds=self.options.retry_initial_seconds,
            max_backoff_seconds=self.options.retry_max_seconds,
            clock=self._clock,
            sleep=self._sleep,
        )
        self._lease_seconds = lease
        self._lease_started_at = attempt_started[-1] if attempt_started else self._clock()
        self.connects += 1

    async def _launch_local(self) -> Any:
        browser_type = getattr(self._playwright, self.options.browser_type, self._playwright.chromium)
        headless = self.env.get("PLAYWRIGHT_HEADLESS", "true").lower() in {"true", "1"}
        browser = await browser_type.launch(headless=headless)
        self.connects += 1
        return browser

    def connected(self) -> bool:
        if self.browser is None:
            return False
        try:
            return bool(self.browser.is_connected())
        except Exception:
            return False

    def lease_remaining_seconds(self) -> float | None:
        """Seconds left on the granted gateway lease (None in local-launch mode)."""
        if not self.remote or self._lease_seconds is None or self._lease_started_at is None:
            return None
        return self._lease_seconds - (self._clock() - self._lease_started_at)

    def _open_context_count(self) -> int:
        try:
            return len(self.browser.contexts)
        except Exception:
            return 0

    def _lease_renewal_due(self) -> bool:
        remaining = self.lease_remaining_seconds()
        if remaining is None or remaining >= self.options.lease_renew_margin_seconds:
            return False
        # Renew only between tests: a test that holds several contexts (ParallelSessionManager)
        # must not lose the earlier ones when it opens the next.
        return self._open_context_count() == 0

    def _latch(self, reason: str) -> PwmcpConnectionClosed:
        self._fatal_reason = reason
        logger.error("pwmcp session connection is unusable for the rest of the session: %s", reason)
        return PwmcpConnectionClosed(reason)

    async def ensure_connected(self) -> Any:
        """Return the shared browser, replacing it between tests when needed.

        * A failed replacement is latched: every later call re-raises the same reason at once
          and never connects again, so a dead gateway fails the rest of the session fast
          instead of costing a full connect/retry budget per test.
        * A browser found dead is replaced at most ``max_reconnects`` times per session.
        * A live browser whose lease has less than ``lease_renew_margin_seconds`` left is
          replaced proactively when no context is open (between tests).
        """
        if self._fatal_reason is not None:
            raise PwmcpConnectionClosed(self._fatal_reason)
        if self.connected():
            if not self._lease_renewal_due():
                return self.browser
            cause = f"lease-renewal ({self.lease_remaining_seconds():.0f}s of {self._lease_seconds}s left)"
        else:
            if self._recoveries >= self.options.max_reconnects:
                raise self._latch(
                    "the shared pwmcp browser died again after "
                    f"{self._recoveries} reconnect(s); E2E_PWMCP_MAX_RECONNECTS="
                    f"{self.options.max_reconnects} is exhausted (unstable gateway?)"
                )
            self._recoveries += 1
            cause = "browser-disconnected"
        old_browser = self.browser
        self.browser = None
        if old_browser is not None:
            try:
                await old_browser.close()
            except Exception:
                pass
        try:
            await self._connect_browser()
        except Exception as exc:
            raise self._latch(f"shared pwmcp browser reconnect after {cause} failed: {exc}") from exc
        if not self.connected():
            raise self._latch(f"shared pwmcp browser remained disconnected after the {cause} reconnect")
        self.reconnects += 1
        self.reconnect_causes.append(cause)
        logger.warning("pwmcp reconnected: %s (reconnects=%d)", cause, self.reconnects)
        return self.browser

    async def new_context(self, *, storage_state_path: str | None = None, **kwargs: Any) -> Any:
        browser = await self.ensure_connected()
        context_kwargs = dict(kwargs)
        existing = existing_storage_state(storage_state_path)
        if existing:
            context_kwargs["storage_state"] = existing
        context = await browser.new_context(**context_kwargs)
        self.contexts += 1
        return context

    async def stop(self) -> None:
        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception as exc:
                logger.debug("shared browser close failed during teardown: %s", exc)
            finally:
                self.browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.debug("Playwright driver stop failed during teardown: %s", exc)
            finally:
                self._playwright = None

    def summary(self) -> str:
        return f"pwmcp connects={self.connects} reconnects={self.reconnects} contexts={self.contexts}"

    def summary_details(self) -> list[str]:
        """Extra terminal-summary lines: why the session reconnected or gave up."""
        lines = []
        if self.reconnect_causes:
            lines.append("pwmcp reconnect causes: " + "; ".join(self.reconnect_causes))
        if self._fatal_reason is not None:
            lines.append(f"pwmcp connection latched as failed: {self._fatal_reason}")
        return lines


_current_session: SharedPwmcpSession | None = None
_last_summary = "pwmcp connects=0 reconnects=0 contexts=0"
_last_details: list[str] = []


def install_shared_session(session: SharedPwmcpSession) -> None:
    global _current_session
    _current_session = session


def current_shared_session() -> SharedPwmcpSession | None:
    return _current_session


def uninstall_shared_session(session: SharedPwmcpSession) -> None:
    global _current_session, _last_summary, _last_details
    if _current_session is session:
        _current_session = None
    _last_summary = session.summary()
    _last_details = session.summary_details()


def last_session_summary() -> str:
    return _last_summary


def last_session_summary_details() -> list[str]:
    return list(_last_details)

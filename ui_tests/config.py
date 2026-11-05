"""Shared configuration for the e2e (Playwright) suite.

Nothing here is read from a state file. ``ui_tests/conftest.py`` starts a throwaway app
instance per session (ui_tests/e2e_env.py), provisions personas into its private DB
(ui_tests/personas.py) and then *binds* this module's ``settings`` to them. Reading any
target value before that binding is a programming error and raises immediately.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Mapping
from urllib.parse import urljoin, urlsplit

PRIMARY_PROFILE = "primary"

# ---- target selection (local throwaway instance vs. remote read-only smoke) --------------
ENV_TARGET = "NAF_E2E_TARGET"
TARGET_LOCAL = "local"
TARGET_REMOTE = "remote"

ENV_REMOTE_BASE_URL = "NAF_REMOTE_BASE_URL"
ENV_REMOTE_ADMIN_USERNAME = "NAF_REMOTE_ADMIN_USERNAME"
ENV_REMOTE_ADMIN_PASSWORD = "NAF_REMOTE_ADMIN_PASSWORD"
ENV_REMOTE_ADMIN_PASSWORD_FILE = "NAF_REMOTE_ADMIN_PASSWORD_FILE"
ENV_REMOTE_ADMIN_TOTP_SECRET = "NAF_REMOTE_ADMIN_TOTP_SECRET"
ENV_REMOTE_ADMIN_TOTP_SECRET_FILE = "NAF_REMOTE_ADMIN_TOTP_SECRET_FILE"

# Profile fields a remote target cannot provide (no personas, no tokens, no private DB).
REMOTE_UNAVAILABLE = frozenset(
    {"mail_admin", "user", "client", "readonly_client", "db_path"}
)


class RemoteConfigError(RuntimeError):
    """The remote smoke target is selected but its configuration is wrong or incomplete."""


class TargetUnavailableError(RuntimeError):
    """A test asked the bound target for something it cannot provide (e.g. a user persona remotely)."""


def selected_target(env: Mapping[str, str] | None = None) -> str:
    """``local`` (default: throwaway instance) or ``remote`` (``NAF_E2E_TARGET=remote``).

    Any other value is an error: a typo must never silently select the local mode.
    """
    env = os.environ if env is None else env
    value = env.get(ENV_TARGET, "").strip().lower()
    if value in ("", TARGET_LOCAL):
        return TARGET_LOCAL
    if value == TARGET_REMOTE:
        return TARGET_REMOTE
    raise RemoteConfigError(f"{ENV_TARGET}={value!r} is not valid (use '{TARGET_LOCAL}' or '{TARGET_REMOTE}')")


def _value_or_file(env: Mapping[str, str], value_name: str, file_name: str, *, required: bool) -> str | None:
    """A secret from ``<value_name>`` XOR ``<file_name>`` (file preferred; both set is an error)."""
    value = env.get(value_name, "")
    file_path = env.get(file_name, "").strip()
    if value and file_path:
        raise RemoteConfigError(f"set only one of {value_name} and {file_name}")
    if file_path:
        path = Path(file_path)
        if not path.is_file():
            raise RemoteConfigError(f"{file_name} points to a missing file: {file_path}")
        value = path.read_text(encoding="utf-8").rstrip("\r\n")
        if not value:
            raise RemoteConfigError(f"{file_name} points to an empty file: {file_path}")
    if not value:
        if required:
            raise RemoteConfigError(f"set {file_name} (preferred) or {value_name}")
        return None
    return value


@dataclass
class UiTargetProfile:
    """Concrete host + credentials of one UI test target."""

    name: str
    base_url: str
    admin_username: str
    admin_password: str
    admin_totp_secret: str | None
    mail_admin_username: str
    mail_admin_password: str
    user_username: str
    user_password: str
    user_totp_secret: str | None
    client_id: str
    client_secret_key: str
    client_domain: str
    allow_writes: bool = True
    deployment_target: str = "local"
    readonly_client_id: str = ""
    readonly_client_secret_key: str = ""
    # Field groups the target cannot provide; reading one through ``settings`` raises.
    unavailable: frozenset = frozenset()

    @property
    def client_token(self) -> str:
        """Full Bearer token value (``naf_<user_alias>_<random>``)."""
        return self.client_secret_key

    @property
    def readonly_client_token(self) -> str:
        return self.readonly_client_secret_key

    def __repr__(self) -> str:  # never print credentials
        return f"UiTargetProfile({self.name!r}, {self.base_url!r})"


class UiTestConfig:
    """Session-bound UI target configuration."""

    def __init__(self) -> None:
        self.playwright_headless: bool = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() in {"true", "1"}
        self.screenshot_prefix: str = os.getenv("UI_SCREENSHOT_PREFIX", "test")
        self._profiles: dict[str, UiTargetProfile] = {}
        self._active: UiTargetProfile | None = None
        self._db_path: Path | None = None
        self.workdir: Path | None = None

    # ---- binding ------------------------------------------------------------------
    def bind_local(self, instance, personas) -> None:
        """Bind to a per-session e2e instance (e2e_env.AppInstance) and its personas."""
        profile = UiTargetProfile(
            name=PRIMARY_PROFILE,
            base_url=instance.base_url,
            admin_username=personas.admin.username,
            admin_password=personas.admin.password,
            admin_totp_secret=personas.admin.totp_secret,
            mail_admin_username=personas.mail_admin.username,
            mail_admin_password=personas.mail_admin.password,
            user_username=personas.user.username,
            user_password=personas.user.password,
            user_totp_secret=personas.user.totp_secret,
            client_id=personas.user.username,
            client_secret_key=personas.user_token,
            client_domain=personas.client_domain,
            allow_writes=True,
            deployment_target="local",
            readonly_client_id=personas.readonly.username,
            readonly_client_secret_key=personas.readonly_token,
        )
        self._profiles = {PRIMARY_PROFILE: profile}
        self._active = profile
        self._db_path = instance.db_path
        self.workdir = instance.workdir

    def bind_remote(self, env: Mapping[str, str] | None = None, *, workdir: Path | None = None) -> UiTargetProfile:
        """Bind to a REMOTE (webhosting) deployment for the read-only smoke; nothing is started.

        Everything comes from explicit environment variables (secrets preferably as ``*_FILE``).
        The profile is ``deployment_target="webhosting"`` and ``allow_writes=False``. User
        persona, tokens and the DB path do not exist remotely: reading them raises
        ``TargetUnavailableError`` instead of returning a placeholder.
        """
        env = os.environ if env is None else env
        base_url = env.get(ENV_REMOTE_BASE_URL, "").strip()
        if not base_url:
            raise RemoteConfigError(f"set {ENV_REMOTE_BASE_URL} (e.g. https://<your-host>)")
        parts = urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise RemoteConfigError(f"{ENV_REMOTE_BASE_URL} must be an absolute http(s) URL")
        username = env.get(ENV_REMOTE_ADMIN_USERNAME, "").strip()
        if not username:
            raise RemoteConfigError(f"set {ENV_REMOTE_ADMIN_USERNAME}")
        password = _value_or_file(
            env, ENV_REMOTE_ADMIN_PASSWORD, ENV_REMOTE_ADMIN_PASSWORD_FILE, required=True
        )
        totp = _value_or_file(
            env, ENV_REMOTE_ADMIN_TOTP_SECRET, ENV_REMOTE_ADMIN_TOTP_SECRET_FILE, required=False
        )
        profile = UiTargetProfile(
            name=PRIMARY_PROFILE,
            base_url=base_url,
            admin_username=username,
            admin_password=password,
            admin_totp_secret=totp,
            mail_admin_username="",
            mail_admin_password="",
            user_username="",
            user_password="",
            user_totp_secret=None,
            client_id="",
            client_secret_key="",
            client_domain="",
            allow_writes=False,
            deployment_target="webhosting",
            unavailable=REMOTE_UNAVAILABLE,
        )
        self._profiles = {PRIMARY_PROFILE: profile}
        self._active = profile
        self._db_path = None
        self.workdir = workdir
        return profile

    def unbind(self) -> None:
        self._profiles = {}
        self._active = None
        self._db_path = None
        self.workdir = None

    def _need(self, group: str) -> UiTargetProfile:
        profile = self.active
        if group in profile.unavailable:
            raise TargetUnavailableError(
                f"{group!r} is not available on the {profile.deployment_target!r} target "
                "(remote smoke is read-only and has only the operator admin)"
            )
        return profile

    @property
    def db_path(self) -> Path | None:
        """The session instance's private DB; raises on a remote target (no direct DB access)."""
        self._need("db_path")
        return self._db_path

    @property
    def active(self) -> UiTargetProfile:
        if self._active is None:
            raise RuntimeError(
                "ui_tests.config.settings is not bound: the e2e session fixture "
                "(ui_tests/conftest.py e2e_environment) binds it before any test runs"
            )
        return self._active

    # ---- active profile helpers ------------------------------------------------------
    @property
    def deployment_target(self) -> str:
        return self.active.deployment_target

    @property
    def base_url(self) -> str:
        return self.active.base_url

    @property
    def admin_username(self) -> str:
        return self.active.admin_username

    @property
    def admin_password(self) -> str:
        return self.active.admin_password

    @property
    def admin_totp_secret(self) -> str | None:
        return self.active.admin_totp_secret

    @property
    def mail_admin_username(self) -> str:
        """Admin persona with EMAIL 2FA only (2FA failure/lockout tests may lock it)."""
        return self._need("mail_admin").mail_admin_username

    @property
    def mail_admin_password(self) -> str:
        return self._need("mail_admin").mail_admin_password

    @property
    def user_username(self) -> str:
        return self._need("user").user_username

    @property
    def user_password(self) -> str:
        return self._need("user").user_password

    @property
    def user_totp_secret(self) -> str | None:
        return self._need("user").user_totp_secret

    @property
    def client_id(self) -> str:
        return self._need("client").client_id

    @property
    def client_token(self) -> str:
        return self._need("client").client_token

    @property
    def readonly_client_token(self) -> str:
        return self._need("readonly_client").readonly_client_token

    @property
    def client_domain(self) -> str:
        return self._need("client").client_domain

    @property
    def allow_writes(self) -> bool:
        return self.active.allow_writes

    # ---- profile orchestration ----------------------------------------------------------
    @staticmethod
    def profile_names() -> List[str]:
        """Static at collection time (the binding happens later, in the session fixture)."""
        return [PRIMARY_PROFILE]

    def profile(self, name: str) -> UiTargetProfile:
        self.active  # raise if unbound
        return self._profiles[name]

    def profiles(self) -> List[UiTargetProfile]:
        self.active
        return list(self._profiles.values())

    @contextmanager
    def use_profile(self, profile: UiTargetProfile) -> Iterator[UiTargetProfile]:
        """Temporarily switch the active profile (a COPY, so mutations never leak)."""
        previous = self.active
        self._active = deepcopy(profile)
        try:
            yield self._active
        finally:
            self._active = previous

    # ---- utility helpers ---------------------------------------------------------------
    def url(self, path: str) -> str:
        return urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))

    def storage_state_path(self, name: str = "admin") -> Path:
        """Per-session Playwright cookie cache (inside the instance work dir; dies with it)."""
        if self.workdir is None:
            raise RuntimeError("settings is not bound to an e2e instance")
        return self.workdir / f"{name}_auth_state.json"


settings = UiTestConfig()


def require_readonly_token() -> str:
    """The read-only persona's token (always provisioned for a local session)."""
    token = (settings.readonly_client_token or "").strip()
    if not token:
        raise AssertionError("read-only persona token missing from the bound e2e configuration")
    return token

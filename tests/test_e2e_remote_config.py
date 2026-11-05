"""Hermetic checks of the remote (webhosting) smoke binding in ui_tests/config.py.

No browser, no network: environments are plain dicts and secrets live in tmp files.
"""
from __future__ import annotations

import pytest

from ui_tests.config import (
    RemoteConfigError,
    TargetUnavailableError,
    UiTestConfig,
    selected_target,
)

URL = "https://naf.example.test"


def _env(tmp_path, **extra):
    pw = tmp_path / "pw"
    pw.write_text("s3cret-pass\n", encoding="utf-8")
    env = {
        "NAF_REMOTE_BASE_URL": URL,
        "NAF_REMOTE_ADMIN_USERNAME": "operator",
        "NAF_REMOTE_ADMIN_PASSWORD_FILE": str(pw),
    }
    env.update(extra)
    return {k: v for k, v in env.items() if v is not None}


def test_local_is_the_default_target():
    assert selected_target({}) == "local"
    assert selected_target({"NAF_E2E_TARGET": ""}) == "local"
    assert selected_target({"NAF_E2E_TARGET": "local"}) == "local"


def test_remote_target_is_explicit_and_typos_fail():
    assert selected_target({"NAF_E2E_TARGET": " Remote "}) == "remote"
    with pytest.raises(RemoteConfigError):
        selected_target({"NAF_E2E_TARGET": "remtoe"})


def test_bind_remote_reads_env_and_is_read_only(tmp_path):
    cfg = UiTestConfig()
    cfg.bind_remote(_env(tmp_path))
    assert cfg.base_url == URL
    assert cfg.admin_username == "operator"
    assert cfg.admin_password == "s3cret-pass"  # trailing newline stripped
    assert cfg.admin_totp_secret is None
    assert cfg.allow_writes is False
    assert cfg.deployment_target == "webhosting"
    assert cfg.url("/admin/login") == URL + "/admin/login"


def test_totp_secret_from_file_and_from_value(tmp_path):
    seed = tmp_path / "seed"
    seed.write_text("JBSWY3DPEHPK3PXP\n", encoding="utf-8")
    cfg = UiTestConfig()
    cfg.bind_remote(_env(tmp_path, NAF_REMOTE_ADMIN_TOTP_SECRET_FILE=str(seed)))
    assert cfg.admin_totp_secret == "JBSWY3DPEHPK3PXP"
    cfg.bind_remote(_env(tmp_path, NAF_REMOTE_ADMIN_TOTP_SECRET="ABCDEFGH"))
    assert cfg.admin_totp_secret == "ABCDEFGH"


def test_value_and_file_together_is_an_error(tmp_path):
    with pytest.raises(RemoteConfigError, match="only one of"):
        UiTestConfig().bind_remote(_env(tmp_path, NAF_REMOTE_ADMIN_PASSWORD="x"))
    seed = tmp_path / "seed"
    seed.write_text("AAAA", encoding="utf-8")
    with pytest.raises(RemoteConfigError, match="only one of"):
        UiTestConfig().bind_remote(
            _env(tmp_path, NAF_REMOTE_ADMIN_TOTP_SECRET="B", NAF_REMOTE_ADMIN_TOTP_SECRET_FILE=str(seed))
        )


@pytest.mark.parametrize("missing", ["NAF_REMOTE_BASE_URL", "NAF_REMOTE_ADMIN_USERNAME", "NAF_REMOTE_ADMIN_PASSWORD_FILE"])
def test_missing_required_values_fail(tmp_path, missing):
    env = _env(tmp_path)
    del env[missing]
    with pytest.raises(RemoteConfigError, match=missing.split("_FILE")[0]):
        UiTestConfig().bind_remote(env)


def test_missing_or_empty_secret_file_fails(tmp_path):
    env = _env(tmp_path, NAF_REMOTE_ADMIN_PASSWORD_FILE=str(tmp_path / "nope"))
    with pytest.raises(RemoteConfigError, match="missing file"):
        UiTestConfig().bind_remote(env)
    empty = tmp_path / "empty"
    empty.write_text("\n", encoding="utf-8")
    env = _env(tmp_path, NAF_REMOTE_ADMIN_PASSWORD_FILE=str(empty))
    with pytest.raises(RemoteConfigError, match="empty"):
        UiTestConfig().bind_remote(env)


@pytest.mark.parametrize("bad", ["naf.example.test", "ftp://x.example", "https://"])
def test_base_url_must_be_absolute_http(tmp_path, bad):
    with pytest.raises(RemoteConfigError, match="absolute http"):
        UiTestConfig().bind_remote(_env(tmp_path, NAF_REMOTE_BASE_URL=bad))


@pytest.mark.parametrize(
    "attr",
    ["user_username", "user_password", "user_totp_secret", "client_id", "client_token",
     "readonly_client_token", "client_domain", "mail_admin_username", "mail_admin_password", "db_path"],
)
def test_unavailable_fields_raise_instead_of_returning_placeholders(tmp_path, attr):
    cfg = UiTestConfig()
    cfg.bind_remote(_env(tmp_path))
    with pytest.raises(TargetUnavailableError):
        getattr(cfg, attr)


def test_unbound_settings_still_raise_and_unbind_resets(tmp_path):
    cfg = UiTestConfig()
    with pytest.raises(RuntimeError, match="not bound"):
        cfg.base_url
    cfg.bind_remote(_env(tmp_path))
    cfg.unbind()
    with pytest.raises(RuntimeError, match="not bound"):
        cfg.admin_password


def test_profile_repr_does_not_leak_credentials(tmp_path):
    cfg = UiTestConfig()
    profile = cfg.bind_remote(_env(tmp_path))
    assert "s3cret-pass" not in repr(profile)

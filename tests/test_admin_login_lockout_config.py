"""Admin login lockout is config-driven (ADMIN_LOGIN_LOCKOUT_THRESHOLD / _MINUTES)."""
import pytest

from netcup_api_filter.api import admin as admin_mod
from netcup_api_filter.config_defaults import require_default

KEYS = ("ADMIN_LOGIN_LOCKOUT_THRESHOLD", "ADMIN_LOGIN_LOCKOUT_MINUTES")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults_come_from_env_defaults():
    assert admin_mod.get_login_lockout_threshold() == int(require_default(KEYS[0])) == 5
    assert admin_mod.get_login_lockout_minutes() == int(require_default(KEYS[1])) == 15


def test_env_override(monkeypatch):
    monkeypatch.setenv(KEYS[0], "2")
    monkeypatch.setenv(KEYS[1], "7")
    assert admin_mod.get_login_lockout_threshold() == 2
    assert admin_mod.get_login_lockout_minutes() == 7


@pytest.mark.parametrize("bad", ["0", "-3", "abc", "1.5"])
@pytest.mark.parametrize("fn,key", [
    ("get_login_lockout_threshold", KEYS[0]),
    ("get_login_lockout_minutes", KEYS[1]),
])
def test_invalid_value_raises(monkeypatch, fn, key, bad):
    monkeypatch.setenv(key, bad)
    with pytest.raises(ValueError, match=key):
        getattr(admin_mod, fn)()


def test_threshold_drives_actual_lockout(app, monkeypatch):
    monkeypatch.setenv(KEYS[0], "2")
    with app.app_context():
        locked1, _ = admin_mod._track_failed_login("lockout-probe", "203.0.113.9")
        locked2, count = admin_mod._track_failed_login("lockout-probe", "203.0.113.9")
    assert (locked1, locked2, count) == (False, True, 2)

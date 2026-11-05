"""Tests for naf-P04: settings double-encoding and the SMTP config key split.

Two bugs, one root cause (settings readers/writers disagreeing on encoding
or on which key holds SMTP config):

  O1 — After a TOML import writes `netcup_config` (and friends), reading it
       back via `get_setting()` must return a dict, not a JSON string.
       `set_setting()` already JSON-encodes its argument (see
       `database.Settings.set_value`); a caller that pre-encodes with
       `json.dumps()` before calling `set_setting()` causes a double encode,
       so `get_setting()` hands back a string and the first `.get(...)` a
       downstream reader (dns_api.py, ddns_protocols.py) performs raises
       AttributeError.

  O2 — The same round-trip parity holds for every TOML-importer-written key,
       not just the one that crashes loudest — asserted together for
       netcup_config, smtp_config, and geoip_config.

  O3 — `send_account_invite_email` and `send_registration_verification_email`
       must succeed when SMTP is configured under the `smtp_config` key
       (what the admin UI and the TOML importer actually write), not only
       under `email_config` (what the local Mailpit seeder writes) — matching
       the already-correct `send_password_reset_email` path.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from netcup_api_filter import email_notifier as email_notifier_module
from netcup_api_filter import password_reset
from netcup_api_filter.database import get_setting, set_setting
from netcup_api_filter.models import RegistrationRequest


REPO_SRC = (Path(__file__).resolve().parent.parent / "src").resolve()
PASSENGER_WSGI_SRC = REPO_SRC / "netcup_api_filter" / "passenger_wsgi.py"


# ---------------------------------------------------------------------------
# O1 / O2 — real TOML import path via passenger_wsgi.py
#
# passenger_wsgi.py is module-level bootstrap code (no function to call
# directly), so this drives the *actual* file exactly as Passenger would:
# copy it to a scratch app_root next to an app-config.toml, exec it as a
# module in a subprocess (isolating its os.environ / logging-handler side
# effects from the test process), then read back the settings it wrote.
# ---------------------------------------------------------------------------

APP_CONFIG_TOML = """
[netcup]
customer_id = "12345"
api_key = "test-api-key"
api_password = "test-api-password"

[smtp]
smtp_host = "mail.example.com"
smtp_port = 465
from_email = "noreply@example.com"

[geoip]
account_id = "1"
license_key = "test-license-key"
"""

# Runs *inside* the subprocess: exec's the passenger_wsgi.py copy (so its
# module-level TOML-import code runs for real), then reads back the settings
# it wrote and dumps type + value as JSON for the parent process to assert on.
_DRIVER = """
import importlib.util
import json
import sys

passenger_wsgi_path, out_path = sys.argv[1], sys.argv[2]

spec = importlib.util.spec_from_file_location("passenger_wsgi_under_test", passenger_wsgi_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

from netcup_api_filter.database import get_setting

with mod.app.app_context():
    result = {
        key: {"type": type(get_setting(key)).__name__, "value": get_setting(key)}
        for key in ("netcup_config", "smtp_config", "geoip_config")
    }

with open(out_path, "w") as f:
    json.dump(result, f)
"""


def _run_real_toml_import(tmp_path: Path) -> dict:
    """Drive passenger_wsgi.py's real app-config.toml import in a subprocess
    against a scratch app_root. Fails the test (with subprocess stdout/stderr
    attached) if the bootstrap script itself errors."""
    app_root = tmp_path / "app_root"
    app_root.mkdir()
    shutil.copy(PASSENGER_WSGI_SRC, app_root / "passenger_wsgi.py")
    (app_root / "app-config.toml").write_text(APP_CONFIG_TOML)

    driver_path = tmp_path / "driver.py"
    driver_path.write_text(_DRIVER)
    out_path = tmp_path / "result.json"

    env = dict(os.environ)
    # Let passenger_wsgi.py's os.environ.setdefault(...) pick these based on
    # the scratch app_root, instead of inheriting anything from the outer
    # test-runner environment.
    env.pop("NETCUP_FILTER_APP_ROOT", None)
    env.pop("NETCUP_FILTER_DB_PATH", None)
    env["SECRET_KEY"] = "test-secret-key-for-passenger-wsgi-subprocess-import"
    env["NETCUP_FILTER_DB_PATH"] = str(app_root / "netcup_filter.db")
    # netcup_api_filter itself isn't pip-installed in this repo (see
    # tests/conftest.py); make it importable the same way pytest.ini does
    # (pythonpath = . src) for this subprocess.
    env["PYTHONPATH"] = str(REPO_SRC)

    proc = subprocess.run(
        [sys.executable, str(driver_path), str(app_root / "passenger_wsgi.py"), str(out_path)],
        cwd=str(app_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if proc.returncode != 0 or not out_path.exists():
        pytest.fail(
            "passenger_wsgi.py real app-config.toml import failed "
            f"(rc={proc.returncode}):\n--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}"
        )

    return json.loads(out_path.read_text())


def test_toml_import_settings_are_dicts_not_strings(tmp_path):
    """O1/O2: after the real app-config.toml import runs, get_setting()
    returns a dict (not a str) for netcup_config, smtp_config, and
    geoip_config, and a downstream `.get(...)` on each does not raise.
    """
    result = _run_real_toml_import(tmp_path)

    for key in ("netcup_config", "smtp_config", "geoip_config"):
        entry = result[key]
        assert entry["type"] == "dict", (
            f"{key} round-tripped through the real TOML import as "
            f"{entry['type']!r}, not dict — a downstream reader's "
            f"`.get(...)` would raise AttributeError. Value: {entry['value']!r}"
        )
        # This is exactly what dns_api.py / ddns_protocols.py do with the
        # config; it must not raise.
        entry["value"].get("anything")

    assert result["netcup_config"]["value"]["customer_id"] == "12345"
    assert result["netcup_config"]["value"]["api_key"] == "test-api-key"
    assert result["smtp_config"]["value"]["smtp_host"] == "mail.example.com"
    assert result["smtp_config"]["value"]["from_email"] == "noreply@example.com"
    assert result["geoip_config"]["value"]["account_id"] == "1"


# ---------------------------------------------------------------------------
# O2 (direct) — set_setting/get_setting round-trip contract
#
# Cheaper, additional pin on the underlying contract passenger_wsgi.py's
# callers must honor: set_setting() already JSON-encodes, so callers must
# hand it a Python object, not a pre-encoded JSON string.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "key,value",
    [
        ("netcup_config", {"customer_id": "123", "api_key": "k", "api_password": "p"}),
        ("smtp_config", {"smtp_host": "mail.example.com", "smtp_port": 465, "from_email": "a@b.com"}),
        ("geoip_config", {"account_id": "1", "license_key": "x"}),
    ],
)
def test_set_setting_get_setting_roundtrip_preserves_dict_type(app, db, key, value):
    set_setting(key, value)
    result = get_setting(key)
    assert isinstance(result, dict), f"{key} round-tripped as {type(result).__name__}, not dict"
    assert result == value
    result.get("anything")  # would raise AttributeError if result were a str


def test_pre_encoded_json_string_demonstrates_the_double_encode_bug(app, db):
    """Negative control: this is exactly the bug the passenger_wsgi.py fix
    removes. A caller that (wrongly) pre-encodes with json.dumps() before
    calling set_setting() gets a str back from get_setting(), and `.get(...)`
    on it raises — the AttributeError that used to 500 every DNS/DDNS
    request until an admin re-saved the config.
    """
    set_setting("some_config", json.dumps({"a": 1}))
    result = get_setting("some_config")
    assert isinstance(result, str)
    with pytest.raises(AttributeError):
        result.get("a")


# ---------------------------------------------------------------------------
# O3 — send_*_email must resolve SMTP config from `smtp_config`
# (what the admin UI / TOML importer write), not only `email_config`
# (what the local Mailpit seeder writes).
# ---------------------------------------------------------------------------

SMTP_CONFIG = {
    "smtp_host": "mail.example.com",
    "smtp_port": 465,
    "smtp_username": "",
    "smtp_password": "",
    "from_email": "noreply@example.com",
    "use_ssl": True,
}


@pytest.fixture
def make_registration(db):
    def _make(username="pendinguser", email="pending@example.com"):
        reg = RegistrationRequest(
            username=username,
            email=email,
            password_hash="dummy_hash",
            verification_code="123456",
            verification_expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.session.add(reg)
        db.session.commit()
        return reg
    return _make


def test_send_account_invite_email_uses_smtp_config_key(app, db, make_account):
    """O3: the invite path (previously email_config-only) must send when
    SMTP is configured under smtp_config."""
    set_setting("smtp_config", SMTP_CONFIG)
    account = make_account("invitee", email="invitee@example.com")

    with patch.object(email_notifier_module.EmailNotifier, "_send_email_sync") as mock_send:
        result = password_reset.send_account_invite_email(account)

    assert result is True
    mock_send.assert_called_once()


def test_send_registration_verification_email_uses_smtp_config_key(app, db, make_registration):
    """O3: the registration-verification path (previously email_config-only)
    must send when SMTP is configured under smtp_config."""
    set_setting("smtp_config", SMTP_CONFIG)
    reg = make_registration()

    with patch.object(email_notifier_module.EmailNotifier, "_send_email_sync") as mock_send:
        result = password_reset.send_registration_verification_email(reg)

    assert result is True
    mock_send.assert_called_once()


def test_send_password_reset_email_still_uses_smtp_config_key(app, db, make_account):
    """Control: the already-correct reset path keeps working via the shared
    helper (no regression from the refactor)."""
    set_setting("smtp_config", SMTP_CONFIG)
    account = make_account("resetter", email="resetter@example.com")

    with patch.object(email_notifier_module.EmailNotifier, "_send_email_sync") as mock_send:
        result = password_reset.send_password_reset_email(account)

    assert result is True
    mock_send.assert_called_once()


def test_send_account_invite_email_still_works_with_legacy_email_config_key(app, db, make_account):
    """The local Mailpit seeder writes `email_config`; that fallback must
    keep working for existing local-dev setups."""
    set_setting("email_config", SMTP_CONFIG)
    account = make_account("invitee2", email="invitee2@example.com")

    with patch.object(email_notifier_module.EmailNotifier, "_send_email_sync") as mock_send:
        result = password_reset.send_account_invite_email(account)

    assert result is True
    mock_send.assert_called_once()


def test_send_account_invite_email_prefers_smtp_config_over_email_config(app, db, make_account):
    """When both keys are present, smtp_config (the production-shaped key)
    wins — matching send_password_reset_email's existing precedence."""
    set_setting("smtp_config", SMTP_CONFIG)
    set_setting("email_config", {**SMTP_CONFIG, "from_email": "legacy@example.com"})
    account = make_account("invitee3", email="invitee3@example.com")

    real_factory = email_notifier_module.get_email_notifier_from_config
    with patch.object(
        email_notifier_module, "get_email_notifier_from_config", wraps=real_factory
    ) as mock_factory, patch.object(email_notifier_module.EmailNotifier, "_send_email_sync"):
        result = password_reset.send_account_invite_email(account)

    assert result is True
    used_config = mock_factory.call_args[0][0]
    assert used_config["from_email"] == "noreply@example.com"


def test_send_account_invite_email_fails_gracefully_with_no_smtp_config(app, db, make_account):
    """No config under either key: fails cleanly (returns False), doesn't
    raise."""
    account = make_account("noconfig", email="noconfig@example.com")
    result = password_reset.send_account_invite_email(account)
    assert result is False

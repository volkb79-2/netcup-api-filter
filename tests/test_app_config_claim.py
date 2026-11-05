"""Review finding #9: app-config.toml handling for containers.

* A bind-mounted FILE (EBUSY) or a read-only directory cannot be claimed (os.replace) for the
  one-shot import: the start must fail with an actionable message, not crash into a generic
  error page or silently skip the import.
* The ``docker exec``-ed bootstrap CLI resolves the app root exactly as passenger_wsgi does,
  so it reads the same app-config.toml.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from netcup_api_filter.bootstrap.__main__ import app_root_of_module, resolve_app_root

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"

_WRAPPER = r"""
import errno, os, runpy, sys
real_replace = os.replace
def busy(src, dst):
    if str(src).endswith("app-config.toml"):
        raise OSError(errno.EBUSY, "Device or resource busy", src)
    return real_replace(src, dst)
os.replace = busy
runpy.run_path(sys.argv[1], run_name="passenger_wsgi")
"""


def test_unclaimable_app_config_fails_the_start_with_guidance(tmp_path):
    app_root = tmp_path / "app"
    app_root.mkdir()
    shutil.copy(SRC / "netcup_api_filter" / "passenger_wsgi.py", app_root / "passenger_wsgi.py")
    (app_root / "app-config.toml").write_text('[rate_limits]\nadmin = "50 per minute"\n')
    env = {k: v for k, v in os.environ.items() if not k.startswith("NAF_BOOTSTRAP_ADMIN_")}
    env.pop("SECRET_KEY_FILE", None)
    env.update(
        PYTHONPATH=str(SRC), NETCUP_FILTER_APP_ROOT=str(app_root),
        NETCUP_FILTER_DB_PATH=str(tmp_path / "x.db"), NETCUP_FILTER_LOG_FILE=str(tmp_path / "app.log"),
        SECRET_KEY="k" * 32, FLASK_ENV="testing",
        NAF_BOOTSTRAP_ADMIN_USERNAME="claim-admin", NAF_BOOTSTRAP_ADMIN_EMAIL="claim-admin@example.com",
        NAF_BOOTSTRAP_ADMIN_PASSWORD="Claim-Test-" + "y" * 14 + "9!",
    )
    result = subprocess.run([sys.executable, "-c", _WRAPPER, str(app_root / "passenger_wsgi.py")],
                            env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode != 0
    assert "Mount the DIRECTORY" in result.stderr
    assert (app_root / "app-config.toml").is_file()  # untouched


def _fake_tree(tmp_path, *, deploy_tree: bool) -> Path:
    module = tmp_path / "app" / "src" / "netcup_api_filter" / "bootstrap" / "__main__.py"
    module.parent.mkdir(parents=True)
    module.write_text("")
    if deploy_tree:
        (tmp_path / "app" / "passenger_wsgi.py").write_text("")
    return module


def test_cli_app_root_is_the_deploy_tree_holding_the_package(tmp_path):
    assert app_root_of_module(_fake_tree(tmp_path, deploy_tree=True)) == str((tmp_path / "app").resolve())


def test_a_source_checkout_is_no_app_root(tmp_path):
    assert app_root_of_module(_fake_tree(tmp_path, deploy_tree=False)) is None


def test_explicit_app_root_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("NETCUP_FILTER_APP_ROOT", str(tmp_path))
    assert resolve_app_root() == str(tmp_path)

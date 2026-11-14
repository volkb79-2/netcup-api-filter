"""Documentation contracts for startup configuration that points operators here."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from netcup_api_filter.bootstrap.admin import CONFIG_HINT
from netcup_api_filter.bootstrap import __main__ as bootstrap_cli
from netcup_api_filter.bootstrap.init_lock import TIMEOUT_KEY


GUIDE = Path(__file__).resolve().parents[1] / "docs/CONFIGURATION_GUIDE.md"
BUILD_DEPLOYMENT = Path(__file__).resolve().parents[1] / "build_deployment.py"


def test_bootstrap_startup_error_keys_are_documented():
    guide = GUIDE.read_text(encoding="utf-8")
    keys = set(re.findall(r"NAF_BOOTSTRAP_ADMIN_[A-Z_]+", CONFIG_HINT))

    assert keys == {
        "NAF_BOOTSTRAP_ADMIN_USERNAME",
        "NAF_BOOTSTRAP_ADMIN_EMAIL",
        "NAF_BOOTSTRAP_ADMIN_PASSWORD",
        "NAF_BOOTSTRAP_ADMIN_PASSWORD_FILE",
    }
    for key in keys:
        assert f"`{key}`" in guide
    assert "`app-config.toml`" in guide


def _build_local_config_names() -> tuple[set[str], set[str]]:
    tree = ast.parse(BUILD_DEPLOYMENT.read_text(encoding="utf-8"))
    local_defaults: set[str] = set()
    service_vars: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if not isinstance(node.func, ast.Name) or not isinstance(node.args[0], ast.Constant):
            continue
        name = node.args[0].value
        if not isinstance(name, str):
            continue
        if node.func.id == "require_default" and name.startswith("LOCAL_"):
            local_defaults.add(name)
        elif node.func.id == "_local_service_var":
            service_vars.add(name)
    return local_defaults, service_vars


def test_startup_guide_pins_init_lock_and_cli_inputs():
    guide = GUIDE.read_text(encoding="utf-8")
    assert f"`{TIMEOUT_KEY}`" in guide

    parser = bootstrap_cli._build_parser()
    init_parser = parser._subparsers._group_actions[0].choices["init"]
    assert any(
        "--enforce-admin" in action.option_strings for action in init_parser._actions
    ), "the real bootstrap CLI parser must expose --enforce-admin"
    assert re.search(r"`[^`]*--enforce-admin[^`]*`", guide), (
        "the guide must show --enforce-admin in the explicit bootstrap command"
    )


def test_local_build_mailpit_and_mock_inputs_match_the_build_reader():
    guide = GUIDE.read_text(encoding="utf-8")
    local_defaults, service_vars = _build_local_config_names()

    assert local_defaults
    assert service_vars
    for key in sorted(local_defaults | service_vars):
        assert f"`{key}`" in guide
    assert "SERVICE_MAILPIT" not in guide
    assert "`[app_local.mail]`" in guide
    assert "`tooling/app-local/ciu.defaults.toml.j2`" in guide

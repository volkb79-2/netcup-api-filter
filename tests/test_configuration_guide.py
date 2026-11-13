"""Documentation contracts for startup configuration that points operators here."""
from __future__ import annotations

import re
from pathlib import Path

from netcup_api_filter.bootstrap.admin import CONFIG_HINT


GUIDE = Path(__file__).resolve().parents[1] / "docs/CONFIGURATION_GUIDE.md"


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

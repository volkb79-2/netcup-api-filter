"""Mailpit's rendered HTTP settings come from the committed stack defaults."""

from __future__ import annotations

import importlib.util
import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO / "tooling" / "mailpit" / "ciu.defaults.toml.j2"
COMPOSE_PATH = REPO / "tooling" / "mailpit" / "ciu.compose.yml.j2"
RESOLVER_PATH = REPO / "tooling" / "ciu_resolve_env.py"


def _load_resolver():
    spec = importlib.util.spec_from_file_location("naf_ciu_resolve_env", RESOLVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mailpit_compose_uses_committed_defaults_without_shell_inputs():
    """Reject the base 17d38c8 template's required/empty MAILPIT_* shell reads."""
    defaults = tomllib.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))["mailpit"]
    compose = COMPOSE_PATH.read_text(encoding="utf-8")

    assert defaults["web_root"] == "/mailpit"
    assert defaults["max_message_size"] == 10485760
    assert not re.findall(
        r"\$\{MAILPIT_(?:WEBROOT|MAX_MESSAGE_SIZE)\b[^}]*\}", compose
    )
    assert 'MP_WEBROOT: "{{ mailpit.web_root }}"' in compose
    assert 'MP_MAX_MESSAGE_SIZE: "{{ mailpit.max_message_size }}"' in compose


def test_mailpit_healthcheck_path_matches_the_rendered_webroot():
    """Reject 17d38c8's hardcoded healthcheck path beside an empty MP_WEBROOT."""
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    webroot = re.search(r'^\s*MP_WEBROOT:\s*"([^"]+)"\s*$', compose, re.MULTILINE)
    healthcheck = re.search(
        r"http://localhost:\{\{ mailpit\.web_port \}\}([^\s\"]+)", compose
    )

    assert webroot is not None
    assert healthcheck is not None
    assert webroot.group(1) == "{{ mailpit.web_root }}"
    assert healthcheck.group(1) == webroot.group(1) + "/"


def test_mailpit_resolver_uses_the_configured_webroot(tmp_path, monkeypatch):
    """Reject 17d38c8's literal resolver path when stack config selects another root."""
    resolver = _load_resolver()
    defaults_path = tmp_path / "ciu.defaults.toml.j2"
    defaults_path.write_text(
        '[mailpit]\nweb_port = 8765\nweb_root = "/configured-root"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(resolver, "MAILPIT_DEFAULTS_PATH", defaults_path, raising=False)

    document = {
        "resolved": {
            "identities": {
                "tooling/mailpit": {
                    "mailpit": {"container_name": "naf-test-mailpit"}
                }
            }
        }
    }
    values, _missing = resolver.build_assignments(document, tmp_path / "ciu.global.toml")

    assert values["MAILPIT_URL"] == "http://naf-test-mailpit:8765/configured-root"
    assert values["MAILPIT_API_URL"] == (
        "http://naf-test-mailpit:8765/configured-root/api/v1"
    )

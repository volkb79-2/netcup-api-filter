"""Cheap structural guards for the tracked environment-file examples and layout."""
from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_EXAMPLES = {
    ".env.operator.example",
    ".env.webhoster.example",
    ".env.live.example",
    ".env.guard.example",
}
PRIVATE_ENV_FILES = {
    ".env",
    ".env.workspace",
    ".env.operator",
    ".env.webhoster",
    ".env.live",
    ".env.guard",
    "ciu.env",
}
TRACKED_ENV_SOURCES = {".env.defaults", ".env.services"}

LIVE_ENV_KEY_REGISTRY = frozenset(
    {
        "DEPLOYMENT_MODE",
        "DNS_TEST_DOMAIN",
        "DNS_TEST_SUBDOMAIN_PREFIX",
        "DNS_PROPAGATION_TIMEOUT",
        "DNS_PROPAGATION_POLL_INTERVAL",
        "DNS_CHECK_SERVERS",
        "IMAP_HOST",
        "IMAP_PORT",
        "IMAP_USER",
        "IMAP_PASSWORD",
        "IMAP_USE_TLS",
        "IMAP_MAILBOX",
        "IMAP_MAILBOXES",
        "IMAP_TIMEOUT",
        "IMAP_MESSAGE_LOOKBACK",
        "NETCUP_CUSTOMER_ID",
        "NETCUP_API_KEY",
        "NETCUP_API_PASSWORD",
        "MAXMIND_ACCOUNT_ID",
        "MAXMIND_LICENSE_KEY",
        "MAXMIND_API_URL",
    }
)

# A placeholder is one or more bare lowercase tokens in angle brackets (comma separated); nothing
# host-, address- or account-shaped can hide inside it.
PLACEHOLDER = re.compile(r"<[a-z0-9-]+>(?:,<[a-z0-9-]+>)*")
ASSIGNMENT = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
SECRET_NAME = re.compile(r"PASSWORD|SECRET|TOKEN|KEY|HTPASSWD", re.IGNORECASE)
IDENTITY_OR_ENDPOINT_NAME = re.compile(
    r"(?:HOST|URL|DOMAIN|ZONE|SERVERS?|_IP|USER|USERNAME|ACCOUNT|CUSTOMER_ID)$",
    re.IGNORECASE,
)
EMAIL_VALUE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
IPV4_VALUE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
IPV6_VALUE = re.compile(
    r"(?<![\w:])(?:[0-9a-f]{0,4}:){2,}[0-9a-f:.]{2,}(?![\w:])",
    re.IGNORECASE,
)
HOSTNAME_VALUE = re.compile(
    r"(?<![\w.-])(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}(?![\w.-])",
    re.IGNORECASE,
)


def parse_env_text(text: str, *, source: str = "env text") -> dict[str, str]:
    """Parse the assignment-only subset used by these sourceable examples."""
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = ASSIGNMENT.fullmatch(line)
        if match is None:
            raise ValueError(f"{source}:{line_number}: expected KEY=value")
        key, value = match.groups()
        if key in values:
            raise ValueError(f"{source}:{line_number}: duplicate key {key}")
        value = value.strip()
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        values[key] = value
    return values


def secret_value_keys(values: dict[str, str]) -> set[str]:
    return {key for key, value in values.items() if SECRET_NAME.search(key) and value}


def non_placeholder_value_keys(values: dict[str, str]) -> set[str]:
    return {
        key
        for key, value in values.items()
        if value and PLACEHOLDER.fullmatch(value) is None
    }


def unsafe_value_keys(values: dict[str, str]) -> set[str]:
    unsafe: set[str] = set()
    for key, value in values.items():
        if not value or PLACEHOLDER.fullmatch(value):
            continue
        if IDENTITY_OR_ENDPOINT_NAME.search(key) or any(
            pattern.search(value)
            for pattern in (EMAIL_VALUE, IPV4_VALUE, IPV6_VALUE, HOSTNAME_VALUE)
        ):
            unsafe.add(key)
    return unsafe


def is_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", "--", path],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode in (0, 1), result.stderr
    return result.returncode == 0


def test_env_parser_rejects_malformed_and_duplicate_assignments():
    with pytest.raises(ValueError, match="expected KEY=value"):
        parse_env_text("MISSING_SEPARATOR", source="broken example")
    with pytest.raises(ValueError, match="duplicate key TOKEN"):
        parse_env_text("TOKEN=\nTOKEN=\n", source="broken example")


def test_example_value_guards_reject_secrets_and_real_endpoints():
    assert secret_value_keys({"IMAP_PASSWORD": "sample"}) == {"IMAP_PASSWORD"}
    assert non_placeholder_value_keys({"DEPLOYMENT_MODE": "live"}) == {"DEPLOYMENT_MODE"}
    assert non_placeholder_value_keys(
        {"IMAP_HOST": "<mail.real-host.de>", "IMAP_USER": "<me@real-host.de>", "DNS_CHECK_SERVERS": "<ip-1>,<ip-2>"}
    ) == {"IMAP_HOST", "IMAP_USER"}
    assert unsafe_value_keys(
        {
            "IMAP_HOST": "mail.example.invalid",
            "IMAP_USER": "reader@example.invalid",
            "DNS_TEST_DOMAIN": "192.0.2.1",
            "DNS_CHECK_SERVERS": "2001:db8::1",
        }
    ) == {
        "IMAP_HOST",
        "IMAP_USER",
        "DNS_TEST_DOMAIN",
        "DNS_CHECK_SERVERS",
    }


def test_all_env_examples_parse_and_have_unique_keys():
    paths = sorted(ROOT.glob(".env*.example"))
    assert {path.name for path in paths} == EXPECTED_EXAMPLES

    parsed = {
        path.name: parse_env_text(path.read_text(encoding="utf-8"), source=path.name)
        for path in paths
    }
    all_keys = [key for values in parsed.values() for key in values]
    assert len(all_keys) == len(set(all_keys)), "example keys must be unique across files"


def test_example_secret_values_are_empty():
    for path in sorted(ROOT.glob(".env*.example")):
        values = parse_env_text(path.read_text(encoding="utf-8"), source=path.name)
        assert not secret_value_keys(values), f"non-empty secret-looking values in {path.name}"


def test_example_values_are_empty_or_obvious_placeholders():
    for path in sorted(ROOT.glob(".env*.example")):
        values = parse_env_text(path.read_text(encoding="utf-8"), source=path.name)
        assert not non_placeholder_value_keys(values), f"non-placeholder values in {path.name}"


def test_examples_have_no_real_host_ip_email_or_account_values():
    for path in sorted(ROOT.glob(".env*.example")):
        values = parse_env_text(path.read_text(encoding="utf-8"), source=path.name)
        assert not unsafe_value_keys(values), f"non-placeholder host/account values in {path.name}"


def test_gitignore_covers_private_files_but_not_sources_or_examples():
    for path in sorted(PRIVATE_ENV_FILES):
        assert is_ignored(path), f"{path} must be ignored"
    for path in sorted(TRACKED_ENV_SOURCES | EXPECTED_EXAMPLES):
        assert not is_ignored(path), f"{path} must remain trackable"


def test_documented_live_overrides_exist_in_defaults_catalog():
    guide = (ROOT / "docs/CONFIGURATION_GUIDE.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```env-default-overrides\n(.*?)\n```", guide, re.DOTALL)
    assert len(blocks) == 1, "the guide must have one live-default override registry"
    documented = {line.strip() for line in blocks[0].splitlines() if line.strip()}
    defaults = parse_env_text(
        (ROOT / ".env.defaults").read_text(encoding="utf-8"), source=".env.defaults"
    )
    missing = documented - defaults.keys()
    assert documented <= defaults.keys(), f"documented default keys missing from catalog: {missing}"


def test_live_example_keys_are_registered():
    live = parse_env_text(
        (ROOT / ".env.live.example").read_text(encoding="utf-8"),
        source=".env.live.example",
    )
    unregistered = live.keys() - LIVE_ENV_KEY_REGISTRY
    assert live.keys() <= LIVE_ENV_KEY_REGISTRY, f"unregistered live keys: {unregistered}"


def test_private_env_files_are_excluded_from_the_ciu_push_bundle():
    """`ciu up --host webhoster --thin` pushes the checkout minus `bundle_excludes`.

    CIU always excludes `.git`, `.ciu` and `ciu.env`; every other private env file must be
    named in the inventory or it is copied to the shared webhoster.
    """
    inventory = tomllib.loads((ROOT / ".ciu.hosts.toml").read_text(encoding="utf-8"))
    excluded = set(inventory["deploy"]["hosts"]["webhoster"]["bundle_excludes"])
    missing = (PRIVATE_ENV_FILES - {"ciu.env"}) - excluded
    assert not missing, f"private env files not excluded from the webhoster push: {sorted(missing)}"

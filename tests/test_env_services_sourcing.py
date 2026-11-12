"""`.env.services` derives URLs from ciu-resolved identities.

The file must source cleanly under `set -u`, use the exact container identities
in a genuine `ciu resolve --json` document, and leave the public PowerDNS URL
empty when no rendered global topology supplies a FQDN.
"""
import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_SERVICES = REPO_ROOT / ".env.services"


def _resolve_doc() -> str:
    identities = {
        "tooling/mailpit": {"mailpit": {"container_name": "sample-instance-mailpit"}},
        "tooling/netcup-api-mock": {
            "mock-netcup-api": {"container_name": "sample-instance-mock-netcup-api"}
        },
        "tooling/geoip-mock": {
            "mock-geoip": {"container_name": "sample-instance-mock-geoip"}
        },
        "tooling/backend-powerdns": {
            "powerdns": {"container_name": "sample-instance-powerdns"}
        },
    }
    return json.dumps({"resolved": {"identities": identities}, "schema_version": 1})


def _source(env: dict, global_config: Path) -> subprocess.CompletedProcess:
    """Source .env.services under strict mode with a ciu resolve fixture."""
    script = f'set -euo pipefail; cd {REPO_ROOT!s}; source .env.services; ' \
             f'printf "MAILPIT_HOST=[%s]\\n" "${{MAILPIT_HOST-<UNBOUND>}}"; ' \
             f'printf "POWERDNS_API_URL=[%s]\\n" "${{POWERDNS_API_URL-<UNBOUND>}}"'
    return subprocess.run(
        ["bash", "-c", script],
        env={
            **env,
            "NAF_CIU_RESOLVE_JSON": _resolve_doc(),
            "NAF_CIU_GLOBAL_CONFIG": str(global_config),
        },
        capture_output=True,
        text=True,
    )


def test_env_services_exists():
    assert ENV_SERVICES.is_file(), f"{ENV_SERVICES} missing"


def test_sources_cleanly_without_rendered_public_topology(tmp_path):
    proc = _source({"PATH": os.environ["PATH"]}, tmp_path / "missing-ciu-global.toml")
    assert proc.returncode == 0, (
        f"sourcing .env.services aborted (rc={proc.returncode}); stderr:\n{proc.stderr}"
    )
    assert "MAILPIT_HOST=[sample-instance-mailpit]" in proc.stdout, proc.stdout
    assert "POWERDNS_API_URL=[]" in proc.stdout, proc.stdout
    assert "<UNBOUND>" not in proc.stdout, proc.stdout


def test_derives_public_url_from_rendered_instance_topology(tmp_path):
    global_config = tmp_path / "ciu.global.toml"
    global_config.write_text(
        '[topology.external]\npublic_fqdn = "example.test"\n'
        '[topology.dns]\npdns_subdomain = "naf-pdns-instance42"\n',
        encoding="utf-8",
    )
    proc = _source({"PATH": os.environ["PATH"]}, global_config)
    assert proc.returncode == 0, proc.stderr
    assert (
        "POWERDNS_API_URL=[https://naf-pdns-instance42.example.test]"
        in proc.stdout
    ), proc.stdout


def test_missing_resolved_identity_fails_instead_of_exporting_empty_urls(tmp_path):
    proc = subprocess.run(
        ["bash", "-c", f"set -u; cd {REPO_ROOT!s}; source .env.services"],
        env={
            "PATH": os.environ["PATH"],
            "NAF_CIU_RESOLVE_JSON": "{}",
            "NAF_CIU_GLOBAL_CONFIG": str(tmp_path / "missing-ciu-global.toml"),
        },
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "could not derive service identities" in proc.stderr


def test_partial_document_exports_what_resolves_and_unsets_the_rest(tmp_path):
    """A narrow resolve (review M5) warns, exports the rest, and clears stale values."""
    document = json.loads(_resolve_doc())
    del document["resolved"]["identities"]["tooling/backend-powerdns"]
    script = (
        f"set -euo pipefail; cd {REPO_ROOT!s}; "
        "export POWERDNS_API_URL_INTERNAL=stale-from-an-earlier-shell; "
        "source .env.services; "
        'printf "MAILPIT_HOST=[%s]\\n" "${MAILPIT_HOST-<UNBOUND>}"; '
        'printf "POWERDNS_API_URL_INTERNAL=[%s]\\n" "${POWERDNS_API_URL_INTERNAL-<UNBOUND>}"'
    )
    proc = subprocess.run(
        ["bash", "-c", script],
        env={
            "PATH": os.environ["PATH"],
            "NAF_CIU_RESOLVE_JSON": json.dumps(document),
            "NAF_CIU_GLOBAL_CONFIG": str(tmp_path / "missing-ciu-global.toml"),
        },
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "MAILPIT_HOST=[sample-instance-mailpit]" in proc.stdout, proc.stdout
    assert "POWERDNS_API_URL_INTERNAL=[<UNBOUND>]" in proc.stdout, proc.stdout
    assert "no ciu identity for tooling/backend-powerdns:powerdns" in proc.stderr


def test_env_services_resolves_against_the_full_profile():
    text = ENV_SERVICES.read_text(encoding="utf-8")
    assert "ciu resolve --json --profile full" in text

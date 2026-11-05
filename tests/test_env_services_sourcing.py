"""`.env.services` must source cleanly under `set -u` (naf-P05 O1 / review §P0-8).

The file derives POWERDNS_API_URL from ${PUBLIC_FQDN}. PUBLIC_FQDN is a ciu config fact
(topology.external.public_fqdn, naf-I04) — not reverse-DNS detected (naf-P05 O2,
superseded) — and is only needed for the HTTPS PowerDNS-over-the-public-edge path
(reached through the host traefik at naf-pdns.<PUBLIC_FQDN>, naf-I04). But the
derivation used to be unconditional, so under `set -euo pipefail` (which every consumer
uses) sourcing aborted with "PUBLIC_FQDN: unbound variable" whenever it wasn't set.
That bricked deploy.sh / run-gate local-build on any devcontainer rebuild.

These tests shell out (the contract is a shell contract) and run in the unit gate.
"""
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_SERVICES = REPO_ROOT / ".env.services"


def _source(env: dict) -> subprocess.CompletedProcess:
    """Source .env.services under strict mode with the given (minimal) environment.

    Uses `${VAR-<unbound>}` (single dash) so a var SET to empty prints empty, while a
    truly UNBOUND var prints the marker — the distinction that matters here (the fix
    sets POWERDNS_API_URL to empty rather than leaving it unbound).
    """
    script = f'set -euo pipefail; cd {REPO_ROOT!s}; source .env.services; ' \
             f'printf "POWERDNS_API_URL=[%s]\\n" "${{POWERDNS_API_URL-<UNBOUND>}}"'
    return subprocess.run(
        ["bash", "-c", script],
        env=env, capture_output=True, text=True,
    )


def test_env_services_exists():
    assert ENV_SERVICES.is_file(), f"{ENV_SERVICES} missing"


def test_sources_cleanly_with_no_public_vars():
    """The bug: `set -u` + unset PUBLIC_FQDN → abort at source time. Must not happen."""
    # env -i equivalent: a minimal environment with NO PUBLIC_* set. PATH is needed for
    # bash to find coreutils.
    proc = _source({"PATH": "/usr/bin:/bin"})
    # THE contract: sourcing must not abort (the old unconditional ${PUBLIC_FQDN}
    # aborted here with "unbound variable" under set -u).
    assert proc.returncode == 0, (
        f"sourcing .env.services aborted (rc={proc.returncode}); stderr:\n{proc.stderr}"
    )
    # And POWERDNS_API_URL is set to EMPTY (not left unbound, and not a bogus
    # 'https://<UNBOUND>...' string).
    assert "POWERDNS_API_URL=[]" in proc.stdout, proc.stdout
    assert "<UNBOUND>" not in proc.stdout, proc.stdout


def test_derives_url_when_public_fqdn_present():
    """The HTTPS path still works: a set PUBLIC_FQDN yields the derived URL.

    Routed through the host traefik at the naf-pdns subdomain (naf-I04) - mirrors
    tooling/backend-powerdns/ciu.compose.yml.j2's traefik Host() label and
    ciu.global.defaults.toml.j2's [topology.dns] pdns_subdomain = "naf-pdns".
    """
    proc = _source({"PATH": "/usr/bin:/bin", "PUBLIC_FQDN": "example.test"})
    assert proc.returncode == 0, proc.stderr
    assert "POWERDNS_API_URL=[https://naf-pdns.example.test]" in proc.stdout, proc.stdout

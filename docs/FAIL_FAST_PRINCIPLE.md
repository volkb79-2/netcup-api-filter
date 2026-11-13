# Fail-Fast Configuration Principle

Missing or invalid required configuration must stop the operation with an actionable error.
Defaults are allowed when they express a policy choice that is correct without more information;
they must not silently replace an authoritative fact that exists elsewhere. Derive a value when
there is a derivation, read it from its source when one exists, and fail otherwise.

## Shell consumers

Use required-value expansion for inputs the operation cannot safely invent:

```bash
set -euo pipefail
: "${PORT:?PORT must be provided by the caller}"
: "${PHYSICAL_REPO_ROOT:?load the generated CIU host facts}"
```

Avoid fallback syntax for required facts:

```bash
PORT="${PORT:-8000}"
NETWORK="${NETWORK:-some-network}"
```

Those forms continue with values that may point at the wrong service or host. If a value is
optional, make the optional behavior explicit and test it.

## Error messages

A refusal should state what is missing and where the consumer expects it. Do not prescribe an
operator to type a value that the repository can derive or read from an authoritative source.

```bash
: "${PWMCP_NETWORK:?export the network_name reported by the estate pwmcp instance}"
```

Never print a secret while reporting a configuration error. Print the key name or a safe identifier
only.

## File ownership

The current environment-file roles, load order, writers and readers are listed in
[`CONFIGURATION_GUIDE.md`](CONFIGURATION_GUIDE.md#environment-file-layout). Source only the file
required by the workflow. `.env.defaults` is a tracked defaults catalog; `.env.workspace` and
`ciu.env` are generated facts; `.env.services` derives checkout service identities; and the
operator-owned `.env.*` files have separate scopes. Root `.env` is an optional local override for
`.env.defaults` during default loading and build-time database seeding. It is empty by default and
does not automatically export variables to a shell.

Do not duplicate derived `POWERDNS_API_URL` values in a defaults or deployment-route file:
`.env.services` derives them from CIU identities and the public topology. The app's `SECRET_KEY`
is runtime-injected or created once in the database; it has no tracked default.

## Compose consumers

Compose supports required-value checks at render time:

```yaml
services:
  app:
    environment:
      - RUN_UID=${RUN_UID:?source the generated CIU environment}
    volumes:
      - ${PHYSICAL_REPO_ROOT:?source the generated CIU environment}:/workspace
```

The remedy must name the source that actually owns the value. Do not hide a missing path, host
identity or service endpoint behind a guessed fallback.

## Python consumers

For required environment input, validate at the boundary and identify the key without echoing its
value:

```python
import os


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value
```

Use `config_defaults.get_default()` or `require_default()` for keys that intentionally use the
catalog/shipped-default loader. A direct `os.environ` read does not load `.env` files by itself.

## Review checklist

- Does absence fail loudly when the value is required?
- Is the value derived or read from its owner before asking a person to supply it?
- Does the error point to the real source and avoid exposing the value?
- Does a test show that a broken or missing value is rejected?
- Are file ownership and reader claims current in the configuration guide?

# T02 — Unit-test bootstrap: `tests/conftest.py`, factories, `test_database_init.py`

| Status | Model / effort | Depends on | Size |
|--------|----------------|------------|------|
| open | Sonnet 4.6 / high | T01 | M |

## Objective

Create the shared pytest foundation for the unit layer: an app/db fixture pair plus
account/realm/token factory fixtures, so T03–T06 don't each reinvent setup. Add a small
regression test pinning the in-memory engine-options guard and `get_db_path` precedence.

## Context — read first

- `tests/test_telegram_linking.py:25-44` — the proven app-fixture pattern to generalize
  (monkeypatch env + tmp_path file DB + `create_app()`).
- `src/netcup_api_filter/models.py` — `Account` (~300+), `AccountRealm` (~450+),
  `APIToken` (~600+). Verified helpers: `TOKEN_PREFIX` (line 36), `USER_ALIAS_LENGTH` (37),
  `calculate_entropy` (127), `validate_password` (164), `generate_user_alias` (196),
  `generate_token` (209), `hash_token` (242), `Account.set_password` (338),
  `AccountRealm.set_allowed_record_types/operations` (499/511),
  `APIToken.set_allowed_record_types/operations/ip_ranges` (624/637/650).
  **Read the actual model constructors before writing factories — confirm every kwarg.**
- `src/netcup_api_filter/database.py` — `get_db_path` (114), `init_db` (130) with the
  in-memory guard at 139–148, `seed_demo_accounts` (325) — mirror its token construction
  (prefix slice + `hash_token`) in `make_token`.

## Spec

### `tests/conftest.py` (new)

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest
from datetime import datetime
from netcup_api_filter.app import create_app
from netcup_api_filter.database import db as _db
from netcup_api_filter.models import (
    Account, AccountRealm, APIToken,
    generate_token, generate_user_alias, hash_token,
    TOKEN_PREFIX, USER_ALIAS_LENGTH,
)

@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "test_secret_key_for_testing_only")
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "test.db"))
    application = create_app()
    application.config["TESTING"] = True
    with application.app_context():
        yield application
        _db.session.remove()
        _db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def db(app):
    return _db
```

Plus factories (signatures below are the contract; adapt kwargs to the real models):

- `make_account(username="testuser", *, is_active=1, is_admin=0, email=None, password=None, **kw) -> Account`
  — sets `user_alias=generate_user_alias()`, `email_verified=1`, `approved_at=datetime.utcnow()`,
  a dummy `password_hash` unless `password` given (then `set_password`). Commit and return.
- `make_realm(account, *, domain="example.com", realm_type="host", realm_value="vpn",
  status="approved", record_types=("A","AAAA"), operations=("read","update"), **kw) -> AccountRealm`
  — uses `set_allowed_record_types` / `set_allowed_operations`. Commit and return.
- `make_token(realm, *, name="test-token", operations=None, record_types=None, ip_ranges=None,
  is_active=1, expires_at=None) -> tuple[APIToken, str]` — generate plaintext via
  `generate_token(realm.account.user_alias)`; `token_prefix` is the 8 chars starting at
  `len(TOKEN_PREFIX) + USER_ALIAS_LENGTH + 1`; store `hash_token(plain)`; apply scope setters
  only when args are not None. Return `(token, plain)`. **Cross-check the slice against
  `database.seed_demo_accounts` — that function is the authority on token construction.**

Important: if `create_app()` pulls in `app-config.toml` seeding or demo accounts via env, the
fixture must neutralize that (e.g. `monkeypatch.delenv` of the relevant vars) — read
`create_app()`/`config_defaults.py` enough to confirm the test app starts empty apart from
whatever `init_db` itself seeds. Document what `init_db` seeds (e.g. admin account) in a
comment, since factory tests must not collide with it.

### `tests/test_database_init.py` (new, ~3 cases)

1. `create_app()` with `NETCUP_FILTER_DB_PATH=":memory:"` succeeds and
   `app.config["SQLALCHEMY_ENGINE_OPTIONS"] == {}` (pins the guard at `database.py:139-148`).
2. With a file path, `SQLALCHEMY_ENGINE_OPTIONS` contains `pool_size`/`pool_pre_ping`.
3. `get_db_path()` precedence: env `NETCUP_FILTER_DB_PATH` wins over the default (read
   `get_db_path` at `database.py:114` first and assert its actual contract).

### Migrate, don't duplicate

Where `tests/test_telegram_2fa.py` / `tests/test_telegram_linking.py` build the same app setup
inline, leave them working as-is (no churn), but make the new conftest coexist (fixture name
collisions: their local `app` fixtures take precedence in their files — verify all 4 existing
files still pass).

## Acceptance criteria

- [ ] `python -m pytest tests/ -v` green: all pre-existing tests plus the new ones, no new skips.
- [ ] A throwaway test (include it as `tests/test_factories.py` if useful, or as cases inside
      `test_database_init.py`) proves: `make_account` + `make_realm` + `make_token` round-trip —
      the returned plaintext token re-hashes to the stored `token_hash` and the prefix matches.
- [ ] Factories never print or log the plaintext token.

## Verify

```bash
cd /workspaces/netcup-api-filter
python -m pytest tests/ -v
```

## Guardrails (non-negotiable)

- A test that can't fail is worse than no test: no `pytest.skip` to go green, no assertions
  inside `if found:` blocks, no `or`-chained tolerant assertions.
- Never hardcode credentials; never log secrets (token plaintext stays in test scope).
- Run pytest from the repo root. Don't edit `deploy/`, `deploy-local/`, `deploy-webhosting/`.
- Leave changes uncommitted for review unless your operator says otherwise.
- When done: tick T02 in `docs/plans/testing-overhaul/PLAN.md` + add a worklog line.

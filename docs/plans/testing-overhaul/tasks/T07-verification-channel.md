# T07 — Backend-truth channel: `ui_tests/verification.py`

| Status | Model / effort | Depends on | Size |
|--------|----------------|------------|------|
| open | Sonnet 4.6 / high — **diff review by Opus 4.8 required** | — (needs a local deployment to verify) | M |

## Objective

Give E2E tests an independent way to check backend truth, so "click button → flash message"
tests can become "click button → backend state actually changed". Three channels: read-only
sqlite on the deployed DB, authenticated JSON endpoints, and DNS state (REST API + mock netcup
backend). Everything in T08–T12 builds on this module.

## Context — read first

- **DB facts (verified):** the local deployment DB is `deploy-local/netcup_filter.db`
  (`NETCUP_FILTER_DB_PATH` is set in `deploy.sh:536`; `DEPLOY_DIR=${REPO_ROOT}/deploy-local`).
  The Playwright container mounts the repo at the **same absolute path**
  (`tooling/playwright/docker-compose.yml:130`), so the file is reachable from tests.
  Journal mode is DELETE (not WAL): concurrent reads are safe; a writer's commit briefly takes
  an exclusive lock → use `busy_timeout` + retry on `database is locked`. **Writes from tests
  are forbidden by construction** (`mode=ro` + `PRAGMA query_only=ON`).
- **Existing inline-sqlite call sites to migrate:** `ui_tests/tests/test_2fa_security.py:70`
  (lockout-clear helper), `ui_tests/tests/test_registration_negative.py:285` (read),
  `ui_tests/journeys/test_03_realm_management.py:86-137` (**write**-seeding — see below).
- **JSON endpoints (verified to exist):** `/admin/api/accounts`, `/admin/api/stats`,
  `/admin/api/security/stats|timeline|events` (`src/netcup_api_filter/api/admin.py`
  ~2534–2619), `/account/api/realms` (`api/account.py:821`),
  `/account/api/realms/<id>/tokens` (`api/account.py:838`). Call pattern:
  `ui_tests/tests/test_admin_security_api_contracts.py` via
  `browser.request_get_json` (`ui_tests/browser.py:124`, returns `{"status": int, "json": Any}`).
- **Mock netcup:** `ui_tests/mock_netcup_api.py` — constants `MOCK_CUSTOMER_ID="123456"`,
  `MOCK_API_KEY="test-api-key"`, `MOCK_API_PASSWORD="test-api-password"` (lines 26–28);
  state readable via CCP `login` + `infoDnsRecords`. The container
  (`tooling/netcup-api-mock/`) serves `ui_tests/` read-only — new routes land on container
  restart.
- `ui_tests/config.py` raises at import time if no deployment state file exists — therefore
  **import `ui_tests.config` lazily inside functions**, never at module top.

## Spec

### New module `ui_tests/verification.py`

```python
"""Independent backend-truth helpers for E2E tests.
Channel A (sqlite) is READ-ONLY by construction. Never import ui_tests.config at module level."""

DEFAULT_LOCAL_DB_PATH = "/workspaces/netcup-api-filter/deploy-local/netcup_filter.db"

# ---- Channel A: read-only sqlite ----
def db_path() -> str | None: ...          # NAF_VERIFY_DB_PATH env > DEFAULT_LOCAL_DB_PATH if it exists > None
def db_available() -> bool: ...
def require_db() -> str: ...               # returns path or pytest.skip("No direct DB access for this target")

@contextmanager
def ro_connection():                       # sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
    ...                                    # PRAGMA busy_timeout=5000; PRAGMA query_only=ON; row_factory=sqlite3.Row
                                           # retry 3x / 250ms backoff on "database is locked"

def get_account(username: str) -> dict | None: ...
def get_account_by_email(email: str) -> dict | None: ...
def get_realm(*, realm_id=None, account_username=None, domain=None, realm_value=None) -> dict | None: ...
def list_realms(account_username: str) -> list[dict]: ...
def get_token(*, token_id=None, token_name=None, token_prefix=None) -> dict | None: ...
    # row must include is_active, revoked_at(if column exists), expires_at, allowed_* JSON, last_used_at, use_count
def count_activity(*, action=None, status=None, account_username=None, since=None) -> int: ...
def latest_activity(*, action=None, account_username=None, limit=5) -> list[dict]: ...
def list_account_sessions(account_username: str, *, active_only=True) -> list[dict]: ...
def get_setting_value(key: str): ...       # settings.value, JSON-decoded when possible

def wait_for(predicate, *, timeout=5.0, interval=0.25, message="") -> None:
    # poll until predicate() truthy; AssertionError(message) on timeout.
    # E2E tests call this after a UI submit so they don't race the request's commit.

# ---- Channel B: authed JSON via page context (async, takes the logged-in Browser) ----
async def admin_api_accounts(browser) -> list[dict]: ...
async def admin_api_stats(browser) -> dict: ...
async def admin_security_events(browser, *, hours=24, limit=50) -> list[dict]: ...
async def account_api_realms(browser) -> list[dict]: ...
async def account_api_realm_tokens(browser, realm_id: int) -> list[dict]: ...
# each: resp = await browser.request_get_json(<url>); assert resp["status"] == 200; return resp["json"]

# ---- Channel C: DNS truth ----
async def dns_api_list_records(token: str, domain: str) -> tuple[int, list[dict]]: ...  # httpx GET /api/dns/<domain>/records, Bearer
def mock_netcup_available(base_url: str | None = None) -> bool: ...                      # GET {MOCK_NETCUP_API_URL}/health
def mock_netcup_records(domain: str, *, base_url: str | None = None) -> list[dict]: ...
    # try GET {base}/_test/records/<domain> first; fall back to CCP login/infoDnsRecords/logout
def find_record(records, *, hostname: str, rtype: str, destination: str | None = None) -> dict | None: ...
```

Adapt column/table names to the real schema (`src/netcup_api_filter/models.py` —
`accounts`, `account_realms`, `api_tokens`, `activity_log`, `account_sessions`, `settings`;
confirm actual `__tablename__`s). Getters return plain dicts (Row→dict), `None` when absent.

### Test-only inspection routes in `ui_tests/mock_netcup_api.py`

Append (cannot collide with the single CCP endpoint path):

```python
@app.route('/_test/records/<domain>', methods=['GET'])
def _test_records(domain):
    return jsonify({"domain": domain, "records": DNS_RECORDS.get(domain, [])}), 200

@app.route('/_test/reset', methods=['POST'])
def _test_reset():
    reset_mock_state()
    return jsonify({"status": "reset"}), 200
```

(Verify the actual state-dict and reset-helper names in the module first.)
`mock_netcup_records()` must work both before and after the container restart (fallback path).

### Migrate the three inline-sqlite call sites

- `ui_tests/tests/test_registration_negative.py:~285` — replace the raw read with
  `verification` getters.
- `ui_tests/tests/test_2fa_security.py:~57-85` — reads via `verification`; its lockout-clear
  **write** is the one sanctioned legacy write: keep it working but isolate it as a clearly
  named local helper with a comment (`# WRITE: legacy cleanup, see T07 — do not copy this pattern`),
  or convert to an HTTP path if one exists. Do not put any write helper into `verification.py`.
- `ui_tests/journeys/test_03_realm_management.py:86-137` — the DB write-seeding is replaced
  properly in T09 (UI-driven realm request). In this task only add the same `# WRITE: legacy`
  comment marker; don't refactor the journey.

## Acceptance criteria

- [ ] `verification.py` opens the DB strictly read-only (attempting a write through
      `ro_connection()` raises) — include a tiny self-test:
      `ui_tests/tests/test_verification_selftest.py` with 3–4 cases (db_available, get_account
      of the seeded admin, query_only enforcement, wait_for timeout raises).
- [ ] Migrated tests still pass against a running local deployment.
- [ ] `_test/records` route works after `docker compose restart` of the netcup mock, and the
      CCP fallback works without the restart.
- [ ] No module-level import of `ui_tests.config`.

## Verify

```bash
cd /workspaces/netcup-api-filter
# Requires a deployment: ./deploy.sh local   (or --tests-only if one exists)
./run-local-tests.sh --skip-build --with-mocks ui_tests/tests/test_verification_selftest.py
./run-local-tests.sh --skip-build --with-mocks ui_tests/tests/test_registration_negative.py
./run-local-tests.sh --skip-build --with-mocks ui_tests/tests/test_2fa_security.py
```

## Guardrails (non-negotiable)

- **Never write to the live deployment DB** from this module or any test using it.
- No `pytest.skip` to go green (the `require_db()` skip is legitimate ONLY for non-local
  targets), no `if found:` assertions, no `or`-chained assertions.
- Credentials come from `deployment_state_local.json` via the harness — never hardcoded.
- Run from repo root; don't edit `deploy/`, `deploy-local/`, `deploy-webhosting/`.
- Leave changes uncommitted for review (this task requires an Opus review before commit).
- When done: tick T07 in `docs/plans/testing-overhaul/PLAN.md` + add a worklog line.

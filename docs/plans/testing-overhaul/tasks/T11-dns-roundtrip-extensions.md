# T11 — Round-trips #10–12: DNS/DDNS backend truth + security-event contract upgrade

| Status | Model / effort | Depends on | Size |
|--------|----------------|------------|------|
| open | Sonnet 4.6 / high | T08 (pattern), T07 (Channel C2) | M |

## Objective

Extend three existing strong test files so DNS mutations are verified against the **mock
netcup backend's own state** (not just the proxy's response), the portal UI reflects
API-created records, DDNS updates mutate the backend and record token usage, and a tampered
token verifiably surfaces as a security event.

## Context — read first (mandatory)

- `ui_tests/tests/test_api_dns_crud_success_with_mock_backend.py` — the existing CRUD test;
  reuse its mock-reachability check and its netcup-config capture/restore helpers.
- `ui_tests/verification.py` — Channel C2 (`mock_netcup_records`, `find_record`),
  Channel A (`get_token`, `count_activity`), `wait_for`.
- `ui_tests/tests/test_ddns_quick_update.py` — file to extend; `docs/DDNS_PROTOCOLS.md` +
  `src/netcup_api_filter/api/ddns_protocols.py` (real endpoint paths + auth shape:
  Bearer per README; confirm `dyndns2_update` at line 549).
- `ui_tests/tests/test_admin_security_api_contracts.py` — file to upgrade;
  `/admin/api/security/events` shape.
- T08's pattern file for fixture/cleanup style. Note `ui_tests/mock_netcup_api.py` has
  `seed_test_domain`/state dicts — seeding the mock zone happens via its `/_test/` routes or
  CCP calls, never by importing it in-process during E2E.

## Spec

### Test 10 (extend `test_api_dns_crud_success_with_mock_backend.py`) —
`test_api_create_visible_in_portal_and_backend`

After an API CREATE of a distinctive record (unique hostname + TXT/A destination):
- Channel C2: `find_record(mock_netcup_records(domain), hostname=..., rtype=..., destination=...)` is present.
- Portal UI: the user's realm DNS page renders the record (exact hostname + destination text).
- Cleanup: delete via API; C2 confirms gone.

### Test 11 (same file) — `test_portal_dns_create_roundtrip_to_backend`

1. User creates a record via the portal DNS form (grep the real route in `api/account.py`).
2. C2: record present in the mock backend; C1: API list shows it.
3. Portal delete → C2: record gone.

### Test 12 (extend `test_ddns_quick_update.py`) — `test_ddns_update_mutates_backend_and_usage`

1. Setup: token on a DDNS-capable realm (host realm with A record; reuse cross-role helpers).
   Baseline: Channel A snapshot of the token's `use_count` / `last_used_at`.
2. Call the DynDNS2 endpoint with an explicit `myip` (httpx, Bearer auth).
3. Assert the protocol response body is exactly `good <ip>` (or `nochg <ip>` on repeat — do
   both calls and pin both behaviors).
4. C2: the A record's destination in the mock backend equals the pushed IP.
5. Channel A: `use_count` incremented / `last_used_at` advanced; an ActivityLog row for the
   DDNS update exists (`count_activity` delta with the real action name).

### Contract upgrade (in `test_admin_security_api_contracts.py`) —
`test_failed_token_auth_produces_security_event`

1. Take a valid token plaintext, tamper the secret part (keep `naf_<alias>_` + prefix so it
   attributes), call the DNS API → exact auth-failure status.
2. Channel B: `/admin/api/security/events` contains a new event for it (match on the token
   prefix / error code field per the actual event schema); Channel A: ActivityLog row exists.
   Use `wait_for` — event writing may be post-commit.

## Acceptance criteria

- [ ] All extended files pass twice consecutively against a fresh `./deploy.sh local` (mock mode).
- [ ] Every DNS assertion has a backend-truth (C2) component — none rely solely on the proxy response.
- [ ] Netcup admin config captured/restored exactly as the existing CRUD test does (no residue).
- [ ] Exact-assertion rules hold (no sleeps/skips/or-chains/if-found).

## Verify

```bash
cd /workspaces/netcup-api-filter
./run-local-tests.sh --skip-build --with-mocks ui_tests/tests/test_api_dns_crud_success_with_mock_backend.py
./run-local-tests.sh --skip-build --with-mocks ui_tests/tests/test_ddns_quick_update.py
./run-local-tests.sh --skip-build --with-mocks ui_tests/tests/test_admin_security_api_contracts.py
```

## Guardrails (non-negotiable)

- Never write the live DB from tests; mock-backend state is inspected via HTTP, mutated only
  through the product (API/UI/DDNS) or the mock's own `/_test/reset`.
- Credentials via the harness only; never log token plaintext.
- No `pytest.skip` to go green (mock-unreachable may skip ONLY via the existing reachability
  guard pattern), no `if found:` assertions, no `or`-chains, no sleeps.
- Run from repo root; don't edit `deploy/`, `deploy-local/`, `deploy-webhosting/`; deploy.sh suite list is T12's job.
- Leave changes uncommitted for review unless your operator says otherwise.
- When done: tick T11 in `docs/plans/testing-overhaul/PLAN.md` + add a worklog line.

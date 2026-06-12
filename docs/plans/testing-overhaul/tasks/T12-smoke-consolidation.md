# T12 — Smoke consolidation: route-smoke + widgets, delete 9 files, deploy.sh suite list

| Status | Model / effort | Depends on | Size |
|--------|----------------|------------|------|
| open | Sonnet 4.6 / high (bump to `max` if first attempt is sloppy) — **Opus review of the deploy.sh diff required** | T07 | L |

## Objective

Replace ~9 overlapping L0 smoke files (~2,900 lines of "page loads, heading present") with one
route-discovery-driven parametrized smoke suite plus one widgets file for genuine JS/CSS
behavior. New routes get smoke coverage automatically. Update the deploy.sh suite list.

## Context — read first

- `ui_tests/route_discovery.py` — currently unused but working: `discover_routes_from_app()`
  (line 95) returns a `RouteRegistry` with `admin_pages()` (82), `client_pages()` (86),
  `public_pages()` (90), `static_routes()` (78). It imports `create_app` with a scratch DB
  (self-isolating, ~lines 104–112) — works inside the Playwright container because the repo
  is mounted at the same absolute path.
- `ui_tests/tests/test_console_errors.py` — console-listener pattern to fold in (this file
  gets absorbed and deleted at the end).
- `ui_tests/conftest.py` — module/session-scoped context patterns; `ui_tests/browser.py` —
  `verify_status` (255).
- `ui_tests/verification.py` (T07) — to resolve real IDs for param-route smoke.
- `deploy.sh:1190-1226` — the suite list: `local test_suites=(` with entries of the form
  `"Display Name|ui_tests/tests/test_x.py [pytest-args]|mode"` where mode ∈ `all|mock|live`.
- `pytest.ini` — note `addopts = -x` (first failing route aborts the matrix in deploy runs;
  acceptable as a deploy gate — leave as is).
- The 9 source files (read each before harvesting):
  `test_ui_comprehensive.py`, `test_ui_regression.py`, `test_ui_ux_validation.py`,
  `test_ui_interactive.py`, `test_ui_functional.py`, `test_user_journeys.py`,
  `test_mobile_responsive.py`, `test_account_portal_complete.py`, `test_admin_portal_complete.py`.

## Spec

### 1. New `ui_tests/tests/test_route_smoke.py`

Build param lists at import via `discover_routes_from_app()`:

```python
EXCLUDE = {"/admin/logout", "/account/logout", "/admin/audit/export",
           "/account/activity/export", "/admin/login/2fa", "/account/login/2fa"}
# + extend with anything destructive/redirect-by-design you find in the route map
ADMIN_ROUTES  = sorted(r.rule for r in REGISTRY.admin_pages()  if r.rule not in EXCLUDE)
CLIENT_ROUTES = sorted(r.rule for r in REGISTRY.client_pages() if r.rule not in EXCLUDE)
PUBLIC_ROUTES = sorted(r.rule for r in REGISTRY.public_pages())
```

Module-scoped logged-in contexts (one admin, one account user, one anonymous — reuse the
conftest/session-manager machinery so login happens once per module, not per route).

Tests:

- `test_admin_route_smoke[rule]` / `test_account_route_smoke[rule]` /
  `test_public_route_smoke[rule]`: navigate; assert HTTP 200 (`browser.verify_status()`),
  body contains none of `{"Traceback", "Internal Server Error", "UndefinedError", "jinja2."}`,
  **zero** `pageerror` + severe console messages (listener attached per context; pattern from
  `test_console_errors.py`), navbar and footer present.
- `test_protected_route_redirects_anonymous[rule]`: anonymous context on admin+client routes
  → redirected to the respective login.
- `test_param_route_smoke[path]`: explicit small set of detail pages with IDs resolved via
  `verification.py` from the seeded deployment (first account/realm/token):
  `/admin/accounts/<id>`, `/admin/realms/<id>`, `/admin/tokens/<id>`, `/account/realms/<id>`,
  `/account/realms/<id>/dns` (confirm each route exists in the route map; skip-list any that
  don't — by editing the param list, not with pytest.skip).
- `test_unknown_route_404`.

### 2. New `ui_tests/tests/test_ui_widgets.py`

Harvest the genuinely behavioral tests (read the old files; keep the strongest version of
each, rewritten to exact assertions): CSS theme variables defined per theme; theme switcher
applies + persists across pages; density switcher; table theming; password visibility toggle;
password generate button; entropy meter updates; confirm-password mismatch warning;
copy-to-clipboard; dropdown/modal open. Plus a slim `TestResponsive` class (mobile viewport):
tap-target sizes, no horizontal overflow, navbar collapse — 3–5 tests, no sleeps.

### 3. Move unique survivors (before deleting)

- netcup config test-connection + email config field/validation tests
  (`test_ui_comprehensive.py`) → `ui_tests/tests/test_config_pages.py`.
- audit table columns/sorting/pagination + "audit not empty on fresh install"
  (`test_ui_comprehensive.py`, `test_ui_regression.py`) → `ui_tests/tests/test_audit_logs.py`.
- create-account form field check (`test_ui_ux_validation.py`) → `ui_tests/tests/test_admin_ui.py`.
- login↔register/forgot-password link checks (`test_user_journeys.py`) → route smoke or
  `test_ui_widgets.py`.
- While moving, fix false-green patterns in the moved tests (no `if found:` / or-chains).

### 4. Delete the 9 files

Plus `ui_tests/tests/test_console_errors.py` (absorbed). Grep for references (deploy.sh,
docs, other tests) before each deletion.

### 5. `deploy.sh` suite list (lines ~1190–1226)

- Remove the entries pointing at deleted files (grep the suite array for each filename).
- Add: `"Route Smoke|ui_tests/tests/test_route_smoke.py|all"`,
  `"UI Widgets|ui_tests/tests/test_ui_widgets.py|all"`, and entries for the T08–T11 files if
  not yet present: `Cross-Role Accounts`, `Cross-Role Realms`, `Cross-Role Tokens`
  (`|all`; the DNS-CRUD/DDNS files are already listed — verify their modes).
- Touch nothing else in deploy.sh. **This diff requires Opus review.**

## Acceptance criteria

- [ ] `./run-local-tests.sh --skip-build --with-mocks ui_tests/tests/test_route_smoke.py` and
      `.../test_ui_widgets.py` pass against a fresh `./deploy.sh local`.
- [ ] A full `./deploy.sh local` run completes with the updated suite list (this is the
      end-to-end gate for the deploy.sh edit).
- [ ] Route count sanity: the smoke suite covers at least as many distinct GET routes as the 9
      deleted files did (report the numbers).
- [ ] No deleted file is referenced anywhere (grep clean); moved tests live in their new homes
      with exact assertions.

## Verify

```bash
cd /workspaces/netcup-api-filter
./run-local-tests.sh --skip-build --with-mocks ui_tests/tests/test_route_smoke.py
./run-local-tests.sh --skip-build --with-mocks ui_tests/tests/test_ui_widgets.py
./deploy.sh local   # full gate
grep -n "test_ui_comprehensive\|test_ui_regression\|test_ui_ux_validation\|test_ui_interactive\|test_ui_functional\|test_user_journeys\|test_mobile_responsive\|test_account_portal_complete\|test_admin_portal_complete" deploy.sh && echo "FAIL: stale suite entries" || echo OK
```

## Guardrails (non-negotiable)

- No `pytest.skip` to go green, no `if found:` assertions, no `or`-chains, no sleeps —
  including in tests you MOVE (fix them as you move them).
- Never write the live DB from tests. Credentials via the harness only.
- Run from repo root; don't edit `deploy/`, `deploy-local/`, `deploy-webhosting/`.
- deploy.sh: touch ONLY the `test_suites` array.
- Leave changes uncommitted for review (Opus review of the deploy.sh diff is mandatory).
- When done: tick T12 in `docs/plans/testing-overhaul/PLAN.md` + add a worklog line.

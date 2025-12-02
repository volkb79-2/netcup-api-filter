# UI Testing Suite

Automated UI coverage using a multi-layer testing strategy:

| Layer | File | Tool | Purpose |
|-------|------|------|---------|
| Static Audit | `admin_ux_audit.py` | httpx + BeautifulSoup | Element presence, form fields, 500 errors |
| Functional | `tests/test_ui_functional.py` | Playwright | JS behavior, CSS validation, navigation consistency |
| UX Validation | `tests/test_ui_ux_validation.py` | Playwright | Page structure, navigation links |
| Comprehensive | `tests/test_ui_comprehensive.py` | Playwright | Full admin workflows |

## Testing Layers Explained

### Layer 1: Static Audit (httpx - No JavaScript)

```bash
python ui_tests/admin_ux_audit.py --base-url http://localhost:5100
```

**What it tests:**
- All admin pages return 200 (no 500 errors)
- Required form fields exist
- Navigation links present
- Page structure matches UI_REQUIREMENTS.md

**Limitations:**
- ❌ No JavaScript execution
- ❌ Cannot test theme switching
- ❌ Cannot test form validation
- ❌ Cannot test dropdowns/modals

**Use for:** Quick sanity checks, CI/CD validation

### Layer 2: Playwright Functional Tests

```bash
docker exec playwright pytest /workspaces/netcup-api-filter/ui_tests/tests/test_ui_functional.py -v
```

**What it tests:**

1. **JavaScript Behavior:**
   - Password toggle reveals/hides text
   - Entropy calculation updates dynamically
   - Generate button creates strong passwords
   - Submit button enables when requirements met
   - Mismatch warning appears for different passwords

2. **CSS Variable Validation:**
   - Theme variables defined (`--color-bg-primary`, etc.)
   - Tables don't have white background on dark theme
   - Theme applies immediately (no reload needed)

3. **Navigation Consistency Matrix:**
   - Navbar on all pages
   - Same links across all pages
   - No stale breadcrumbs
   - No icons in H1 headings
   - Footer with build info
   - Logout accessible everywhere

**Use for:** After CSS/JS changes, theme modifications

## Prerequisites

1. Start the Playwright container:
   ```bash
   cd tooling/playwright
   docker compose up -d
   ```
2. Install the test dependencies (this intentionally lives in a standalone file
   so production dependencies are untouched):
   ```bash
   pip install -r ui_tests/requirements.txt
   ```
3. Export any environment overrides before running the suite. Defaults cover
   the current deployment documented in `AGENTS.md`.

## One-command local validation

When you need to spin up the seeded backend, TLS proxy, Playwright container,
and the pytest suite in one go, run `tooling/run-ui-validation.sh` from the
repository root. The script will:

- Render/stage the nginx config and cert bundle under `/tmp/netcup-local-proxy`.
- Start gunicorn on port `LOCAL_APP_PORT` (default 5100) with a seeded SQLite
   database inside `tmp/local-netcup.db`.
- Launch the nginx proxy + Playwright container via docker compose.
- Install `ui_tests/requirements.txt` (skip via `SKIP_UI_TEST_DEPS=1`).
- Export sensible defaults for `UI_BASE_URL` (`https://<host-gateway>:443`).
- Execute `pytest ui_tests/tests -vv` inside the Playwright container and tear everything down afterwards.

Override `UI_BASE_URL`, `PLAYWRIGHT_HEADLESS`, `UI_ADMIN_PASSWORD`, and similar
variables before running the helper if you need to target a different host or
credentials.

| Variable | Default | Purpose |
| --- | --- | --- |
| `UI_BASE_URL` | `https://naf.vxxu.de` | Target deployment root |
| `UI_ADMIN_USERNAME` | `admin` | Admin login |
| `UI_ADMIN_PASSWORD` | `admin` | Current admin password |
| `UI_ADMIN_NEW_PASSWORD` | _(unset)_ | Provide if the server still forces password rotation |
| `UI_CLIENT_ID` | `test_qweqweqwe_vi` | Expected client row in the admin UI |
| `UI_CLIENT_TOKEN` | `qweqweqwe-vi-readonly` | Token for the client portal |
| `UI_CLIENT_DOMAIN` | `qweqweqwe.vi` | Domain shown for the seeded token |
| `UI_SCREENSHOT_PREFIX` | `ui-regression` | Prefix when capturing screenshots |
| `UI_ALLOW_WRITES` | `1` | Set to `0` to skip destructive admin flows |
| `UI_SMOKE_BASE_URL` | _(unset)_ | Optional second target (e.g., production host) |
| `UI_SMOKE_ALLOW_WRITES` | `0` | Controls whether smoke profile may perform writes |
| `UI_SMOKE_ADMIN_*` etc. | inherit primary | Override credentials/domain for smoke profile |

When `UI_SMOKE_BASE_URL` is provided, each test parametrizes over both the
primary (usually local) environment and the smoke target, automatically
reusing credentials unless the `UI_SMOKE_*` overrides are supplied. Write-heavy
flows (client creation, Netcup config saves, etc.) automatically skip any
profile that sets `*_ALLOW_WRITES=0`, allowing safe read-only validation
against production.

## Running the suite

```bash
# All tests
docker exec playwright pytest /workspaces/netcup-api-filter/ui_tests/tests -q

# Specific test file
docker exec playwright pytest /workspaces/netcup-api-filter/ui_tests/tests/test_ui_functional.py -v

# Specific test class
docker exec playwright pytest /workspaces/netcup-api-filter/ui_tests/tests/test_ui_functional.py::TestThemeAndCSS -v
```

Screenshots stay inside the Playwright container under `/screenshots`; copy any
artifacts out with `docker cp playwright:/screenshots/<file> ./screenshots/`
if you need to attach them to an issue or PR.

## Test Organization

```
ui_tests/
├── admin_ux_audit.py          # Static audit (httpx, no browser)
├── browser.py                 # Playwright browser wrapper
├── config.py                  # Test configuration
├── conftest.py                # Pytest fixtures
├── workflows.py               # Common test workflows
├── tests/
│   ├── test_ui_functional.py  # JS/CSS/Navigation tests (NEW)
│   ├── test_ui_ux_validation.py  # Page structure tests
│   ├── test_ui_comprehensive.py  # Full workflow tests
│   ├── test_admin_ui.py       # Admin-specific tests
│   └── ...
└── baselines/                 # Visual regression baselines
```

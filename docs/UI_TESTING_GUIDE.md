# Holistic UI Testing and Screenshot Guide

This document describes the comprehensive approach to UI testing and screenshot capture for the Netcup API Filter project.

## Overview

The testing framework has three layers:

| Layer | Tool | Purpose | Speed |
|-------|------|---------|-------|
| **Capture** | `capture_ui_screenshots.py` | Screenshot all routes + inline UX validation | Fast (~30s) |
| **Validation** | `test_ux_theme_validation.py` | Automated theme/CSS compliance checking | Medium (~2m) |
| **Coverage** | `smoke/test_screenshot_capture_and_ux.py` | Data setup + interweaved screenshots + validation | Slow (~5m) |

## Quick Start

### 1. Run Screenshot Capture with UX Validation

```bash
# From Playwright container (after local deployment)
cd /workspaces/netcup-api-filter
SCREENSHOT_DIR=/tmp/screenshots \
DEPLOYED_ADMIN_PASSWORD=YourPassword \
python ui_tests/capture_ui_screenshots.py
```

This will:
- Capture screenshots of all public, admin, and account pages
- Capture BS5 demo with all 3 themes (Cobalt 2, Obsidian Noir, Gold Dust)
- Validate UX compliance inline (white backgrounds, theme colors)
- Generate `ux_issues.json` report

### 2. Run Automated Theme Validation

```bash
pytest ui_tests/tests/test_ux_theme_validation.py -v
```

This validates:
- CSS variables match BS5 reference
- Cards don't have white backgrounds
- Buttons use theme accent colors
- Navigation is consistent across pages
- Glow effects are present on cards

### 3. Run Full Holistic Coverage

```bash
pytest ui_tests/tests/smoke/test_screenshot_capture_and_ux.py -v
```

This performs complete coverage:
- Sets up test data (accounts, realms, tokens)
- Captures screenshots after each data change
- Validates UX on every page
- Simulates API activity for audit logs
- Captures error pages

## Route Coverage

See [ROUTE_COVERAGE.md](deprecated/ROUTE_COVERAGE.md) for the complete route matrix with test and screenshot coverage status.

### Route coverage status

As of the testing overhaul (T01–T14, completed 2026-06-12), the route smoke suite
(`test_route_smoke.py`, 86 tests) is generated from Flask's live URL map at import time.
Every route in every blueprint is automatically smoke-tested without manual upkeep.

Previously identified gaps (account portal, admin detail pages, 2FA pages) are now
covered by the smoke suite and by domain-specific E2E files:

- `/account/dashboard`, `/account/tokens`, `/account/settings` — `test_account_remaining_routes.py`
- `/admin/accounts/<id>`, `/admin/realms/<id>` — `test_admin_ui.py`
- `/account/settings/totp/setup`, `/account/settings/recovery-codes` — `security/test_recovery_codes.py`, `security/test_account_2fa_disable.py`

If a route still lacks a *round-trip* test (UI action → backend state via Channel A/B/C),
add one following the pattern in `roundtrip/test_cross_role_account_lifecycle.py`.

## UX Validation Reference

The BS5 component demo at `/component-demo-bs5` serves as the canonical reference for theme styling. All application pages should match its CSS variables.

### Theme Reference (Cobalt 2)

```css
--bs-primary: #3b7cf5
--bs-body-bg: #070a14
--bs-secondary-bg: #0c1020
--bs-card-bg: #141c30
--bs-card-border-color: rgba(100, 150, 255, 0.38)
--accent-glow: rgba(59, 124, 245, 0.4)
```

### Common Issues Detected

| Issue | Severity | Fix |
|-------|----------|-----|
| White card background | Error | Add `.bg-elevated` or check `.card` CSS |
| Default Bootstrap blue buttons | Warning | Ensure theme CSS loads after Bootstrap |
| Missing card glow | Warning | Check `box-shadow` on `.card` class |
| Table row white background | Error | Add `--bs-table-bg` variable |

## Files Added/Updated

| File | Purpose |
|------|---------|
| `ui_tests/capture_ui_screenshots.py` | Enhanced with UX validation and comprehensive coverage |
| `ui_tests/tests/smoke/test_screenshot_capture_and_ux.py` | Full data-driven coverage tests (renamed from `test_holistic_coverage.py`) |
| `docs/ROUTE_COVERAGE.md` | Complete route matrix |
| `docs/UI_TESTING_GUIDE.md` | This document |

## Integration with deploy.sh

The deployment script (`deploy.sh`) runs tests and screenshots in Phase 5 and 6:

```bash
# Phase 5: Run tests
pytest ui_tests/tests -v

# Phase 6: Capture screenshots
python ui_tests/capture_ui_screenshots.py
```

Both phases now include UX validation automatically.

## Debugging UX Issues

When issues are detected:

1. Check the `ux_issues.json` report for details
2. Compare failing page screenshot to BS5 demo screenshot
3. Use browser DevTools to inspect CSS variables
4. Verify theme CSS file is loading correctly
5. Check for CSS specificity conflicts

### Manual Inspection

For complex issues, use Playwright MCP for interactive debugging:

```bash
# Navigate to page
mcp_playwright_navigate --url "http://localhost:5100/admin/"

# Take screenshot
mcp_playwright_screenshot --path "debug.png"

# Evaluate CSS
mcp_playwright_evaluate --script "getComputedStyle(document.querySelector('.card')).backgroundColor"
```

---

## UI tech stack and testability

This project uses **Jinja2 server-rendered HTML + Alpine.js** (no SPA framework). That
stack is well-suited to automated testing — here is how it compares to the alternatives:

| Stack | Testability | Notes |
|---|---|---|
| **Server-rendered (Jinja2 + Alpine.js) — this project** | Excellent | Single render path; no hydration bugs; server state is directly queryable (Channel A/B); Playwright tests match real user experience exactly |
| React / Vue / Svelte SPA | Good, but harder | Client-side state is opaque to the server; E2E tests need full backend or mocked API; hydration mismatches add a second failure mode |
| Next.js / Nuxt (SSR + hydration) | Moderate | Two render paths (server + client hydration); hydration bugs surface only in E2E, not unit tests; harder to isolate state |
| React Native / Electron | Hard | Native layer requires simulators or physical devices; CI setup is significantly heavier |

**The tradeoff we pay**: every Playwright test needs the Flask app running. This is
mitigated by keeping 239 fast unit tests (no browser, no app) that run in CI in <60 s,
and reserving Playwright for behaviour that genuinely requires a real request cycle.

**Why server-rendering helps the verification channel pattern**: because the server is the
only source of state (no client-side store), Channel A (read-only SQLite) and Channel B
(authed JSON endpoints) give complete, authoritative coverage of what happened after any
UI action. In a SPA, client-side caches can show stale state that conflicts with the DB
— the server-rendered model eliminates that class of false-green.

# Holistic UI Testing and Screenshot Guide

This document describes the comprehensive approach to UI testing and screenshot capture for the Netcup API Filter project.

## Overview

The testing framework has three layers:

| Layer | Tool | Purpose | Speed |
|-------|------|---------|-------|
| **Capture** | `capture_ui_screenshots.py` | Screenshot all routes + inline UX validation | Fast (~30s) |
| **Validation** | `test_ux_theme_validation.py` | Automated theme/CSS compliance checking | Medium (~2m) |
| **Coverage** | `test_holistic_coverage.py` | Data setup + interweaved screenshots + validation | Slow (~5m) |

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
pytest ui_tests/tests/test_holistic_coverage.py -v
```

This performs complete coverage:
- Sets up test data (accounts, realms, tokens)
- Captures screenshots after each data change
- Validates UX on every page
- Simulates API activity for audit logs
- Captures error pages

## Route Coverage

See [ROUTE_COVERAGE.md](ROUTE_COVERAGE.md) for the complete route matrix with test and screenshot coverage status.

### Priority Gaps

Currently uncovered routes that need attention:

1. **Account Portal Authenticated Pages**
   - `/account/dashboard`
   - `/account/realms/<id>`
   - `/account/tokens`
   - `/account/settings`

2. **Admin Detail Pages**
   - `/admin/accounts/<id>`
   - `/admin/realms/<id>` 
   - `/admin/tokens/<id>`

3. **2FA/Security Pages**
   - `/account/settings/totp/setup`
   - `/account/settings/recovery-codes`

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
| `ui_tests/tests/test_ux_theme_validation.py` | Automated theme compliance tests |
| `ui_tests/tests/test_holistic_coverage.py` | Full data-driven coverage tests |
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

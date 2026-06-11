# Recent Changes Summary

## UI Improvements (Latest Session)

### Password Change Page
- **Fixed**: Removed duplicate heading ("Change Password" appeared twice)
- **Result**: Clean single h1 at top of page

### Admin Layout
- **Removed**: "Management" eyebrow text from admin pages
- **Result**: Cleaner navigation with just section names

### Hover Effects
- **Changed**: Removed vertical bounce (`transform: translateY(-1px)`) from all button hover states
- **Affected**: `.btn-primary:hover`, `.btn-important:hover`, `.btn-icon:hover`, `.btn-copy:hover`, `.btn-logs:hover`
- **Result**: Hover effects now only change colors, no movement

### Generate Client ID Button
- **Changed**: Button styling from `btn-outline-light` to `btn-important`
- **Result**: Yellow/gold styling matching other important actions

### Client List Improvements
- **Pen Button**: Changed from rectangular to round (border-radius: 50%)
- **Client ID Column**:
  - Monospace font for better readability
  - Copy button with ⌘ symbol (two overlapping circles)
  - Inline client ID (no longer a link)
  - JavaScript `copyToClipboard()` function with ✓ checkmark feedback
- **Logs Column**: New column with 📄 button for viewing client logs
- **Toggle Columns**: Removed formatters for `is_active` and `email_notifications_enabled` to allow inline editing
- **Result**: Professional client management interface with quick actions

## Playwright Container Architecture (Major Refactoring)

### Problem
- Playwright was running locally in devcontainer
- Cluttered devcontainer with browser dependencies
- Inconsistent emoji/font rendering between dev and production
- No separation of concerns

### Solution
Implemented dedicated Playwright container with comprehensive tooling:

### New Files Created
1. **`tooling/playwright/start-playwright.sh`**
   - One-command container setup
   - Auto-configures from `.env.workspace`
   - Generates docker-compose `.env` file
   - Starts container with correct network/volumes

2. **`tooling/playwright/playwright-exec.sh`**
   - Wrapper for executing commands in container
   - Passes all UI test environment variables
   - Sources `DEPLOYMENT_ENV_FILE` if provided

3. **`PLAYWRIGHT_CONTAINER.md`**
   - Comprehensive documentation
   - Architecture, setup, troubleshooting
   - Environment variables, volume mappings, network addressing

### Modified Files

#### `build_deployment_lib.sh`
- **Added**: `capture_screenshots()` function
- **Features**: Automatic container detection, devcontainer hostname addressing, fallback to local Playwright
- **Example**: `http://netcup-api-filter-devcontainer-vb:5100`

#### `tooling/playwright/docker-compose.yml`
- **Changed**: `/screenshots` volume from `vol-playwright-screenshots` to direct `deploy-local/screenshots` mapping
- **Changed**: `/workspaces/netcup-api-filter` volume from read-only to read-write for flexibility

#### `requirements-dev.txt`
- **Removed**: `playwright>=1.40.0` (now in container)
- **Removed**: `ipython>=8.0.0` (now in container)
- **Result**: Cleaner devcontainer with only essential dependencies

#### `tooling/playwright/requirements.root.txt`
- **Added** comprehensive tooling:
  - `pytest-xdist>=3.5.0` (parallel test execution)
  - `pytest-timeout>=2.2.0` (test timeouts)
  - `pytest-rerunfailures>=13.0` (retry flaky tests)
  - `pixelmatch>=0.3.0` (pixel-level image comparison)
  - `ruff>=0.2.0` (fast linter)
  - `black>=24.0.0` (code formatter)
  - `mypy>=1.8.0` (type checker)
  - `ipython>=8.0.0` (enhanced REPL)
  - `ipdb>=0.13.0` (debugger)
  - `rich>=13.0.0` (rich terminal output)
  - `httpx>=0.27.0` (async HTTP client)
  - `requests>=2.32.0` (sync HTTP client)

#### `.devcontainer/Dockerfile`
- **Added**: `fonts-noto-color-emoji` package
- **Result**: Emoji rendering parity between devcontainer and production

#### `tooling/playwright/Dockerfile`
- **Added**: `fonts-noto-color-emoji` package
- **Result**: Consistent emoji/symbol rendering in screenshots

### Network Architecture
- **Container Network**: Shares devcontainer network (e.g., `naf-dev-network`)
- **Addressing**: Container uses devcontainer hostname for Flask access
- **Dynamic**: Network name from `.env.workspace` (`DOCKER_NETWORK_INTERNAL`)
- **Port**: Flask listens on 5100 in devcontainer

### Integration with Build Scripts

#### `build-and-deploy-local.sh`
- Uses `capture_screenshots()` from `build_deployment_lib.sh`
- Automatically detects and uses Playwright container
- Falls back to local Playwright with helpful message

#### `build-and-deploy.sh`
- Same automatic detection and fallback behavior
- Consistent screenshot capture for both local and webhosting deployments

## Documentation Updates

### New Documentation
1. **`PLAYWRIGHT_CONTAINER.md`** (NEW)
   - Complete architecture guide
   - Quick start commands
   - Troubleshooting section
   - Environment variables reference

2. **`PYTHON_PACKAGES.md`** (UPDATED)
   - Added Playwright container requirements section
   - Updated devcontainer requirements (removed Playwright/ipython)
   - Clarified two-tier + container system
   - Updated testing workflow documentation

### Updated Documentation
1. **`AGENTS.md`**
   - Added "UI Testing with Playwright Container" section
   - Updated Docker network documentation (dynamic network name)
   - Added container capabilities list
   - Updated screenshot workflow

2. **`README.md`**
   - Added links to `PLAYWRIGHT_CONTAINER.md`, `PYTHON_PACKAGES.md`, `AGENTS.md`
   - Maintained focus on core guides

3. **`docs/README.md`**
   - Added "Project Documentation (Repository Root)" section
   - Links to root-level docs (Playwright, Python, Agents, Client Templates)

### Verified Documentation
- **`docs/OPERATIONS_GUIDE.md`**: Already correct (references Playwright container properly)
- **`docs/ROOT_INVENTORY.md`**: Already correct (mentions Playwright utilities)

## Configuration Changes

### `.env.defaults`
No changes in this session, but all configuration remains 100% config-driven per project policy.

### Environment Variables
All Playwright environment variables now passed via `playwright-exec.sh`:
- `UI_BASE_URL` (required)
- `PLAYWRIGHT_HEADLESS` (optional)
- `SCREENSHOT_DIR` (optional)
- `UI_ADMIN_USERNAME`, `UI_ADMIN_PASSWORD` (optional)
- `UI_CLIENT_ID`, `UI_CLIENT_TOKEN` (optional)
- All `DEPLOYED_*` variables

## Testing Workflow

### Before (Local Playwright)
```bash
# Cluttered devcontainer with browser deps
python3 ui_tests/capture_ui_screenshots.py
pytest ui_tests/tests -v
```

### After (Container-based)
```bash
# Clean separation with dedicated container
cd tooling/playwright && ./start-playwright.sh
./tooling/playwright/playwright-exec.sh python3 /workspaces/netcup-api-filter/ui_tests/capture_ui_screenshots.py
./tooling/playwright/playwright-exec.sh pytest /workspaces/netcup-api-filter/ui_tests/tests -v
docker stop playwright  # When done
```

### Automatic (Build Scripts)
```bash
# Automatic detection and container usage
./build-and-deploy-local.sh  # Uses container if available
./run-local-tests.sh         # Full test suite
```

## Key Benefits

### Cleaner Devcontainer
- Removed 2 packages from `requirements-dev.txt`
- No browser/Playwright clutter
- Faster devcontainer rebuild
- Clear separation of concerns

### Better Rendering
- Emoji fonts in both devcontainer and container
- Consistent rendering across all environments
- Screenshots match production appearance
- Copy/logs buttons (⌘, 📄) render correctly

### Comprehensive Tooling
- 12 additional packages in Playwright container
- Parallel test execution (pytest-xdist)
- Visual regression testing (pixelmatch)
- Code quality tools (ruff, black, mypy)
- Debugging tools (ipython, ipdb, rich)
- Mock servers (Flask, aiosmtpd)

### Flexible Architecture
- Container optional (automatic fallback)
- Reusable for multiple test runs
- Network-aware (dynamic hostname detection)
- Volume mappings for direct output

## Breaking Changes

**None** - All changes are backward compatible:
- Build scripts detect container availability and fall back automatically
- Existing workflows continue to work
- Local Playwright still available if container not running

## Migration Notes

### For Developers
1. Remove Playwright from local Python if desired: `pip uninstall playwright`
2. Start Playwright container: `cd tooling/playwright && ./start-playwright.sh`
3. Run tests as usual - scripts detect container automatically

### For CI/CD
No changes needed - scripts handle container detection and fallback automatically.

### For Documentation Readers
- Read `PLAYWRIGHT_CONTAINER.md` for container-specific workflows
- Check `AGENTS.md` for updated testing instructions
- Review `PYTHON_PACKAGES.md` for requirements changes

## Future Enhancements

### Potential Additions
- GitHub Actions workflow using Playwright container
- Pre-built container images (no local build needed)
- Multi-browser testing (Firefox, WebKit)
- Accessibility testing tools (axe-core)

### Not Planned
- Removing local Playwright fallback (useful for quick checks)
- Changing container base image (mcr.microsoft.com/playwright:latest is standard)
- Adding more fonts (Noto Color Emoji covers most cases)

## Rollback Plan

If the Playwright container causes issues:

1. **Temporary fix**: Scripts automatically fall back to local Playwright
2. **Permanent rollback**: Add `playwright>=1.40.0` back to `requirements-dev.txt`
3. **Container removal**: `docker stop playwright && docker rm playwright`

No code changes needed - fallback is built-in.

## See Also

- `PLAYWRIGHT_CONTAINER.md` - Complete container documentation
- `PYTHON_PACKAGES.md` - Requirements management
- `AGENTS.md` - Agent instructions (Section: "UI Testing with Playwright Container")
- `docs/OPERATIONS_GUIDE.md` - Full deployment and testing workflows
- `tooling/playwright/README.md` - Container-specific setup

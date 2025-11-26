# Python Package Management

## Overview

Python dependencies are managed through a **two-tier requirements system**:

1. **`requirements.webhosting.txt`** - Production runtime dependencies (Flask app only)
2. **`requirements-dev.txt`** - Development dependencies (includes production + testing + tooling)

## Structure

```
requirements.webhosting.txt (production)
├── Flask app core (flask, flask-limiter, flask-admin, etc.)
├── Database (sqlalchemy, flask-sqlalchemy)
├── Authentication (bcrypt, flask-login)
└── Configuration (pyyaml, python-dotenv)

requirements-dev.txt (development)
├── -r requirements.webhosting.txt (includes all production deps)
├── Testing (pytest, pytest-asyncio)
└── WSGI server (gunicorn - for local testing)

tooling/playwright/requirements.root.txt (Playwright container)
├── Browser automation (playwright, chromium)
├── Testing frameworks (pytest with xdist, timeout, rerunfailures)
├── Visual regression (Pillow, pixelmatch)
├── Code quality (ruff, black, mypy)
├── Debugging (ipython, ipdb, rich)
└── HTTP clients (httpx, requests)
```

## Usage

### Production Deployment (Webhosting)

**Automated via `build_deployment.py`:**
```bash
./build_deployment.py
# Downloads and vendors packages from requirements.webhosting.txt into deploy/vendor/
```

The deployment package (`deploy.zip`) contains:
- Vendored dependencies (no pip install needed on server)
- Application code
- Preseeded database
- Configuration defaults

### Local Development (Devcontainer)

**Automated via `.devcontainer/post-create.sh`:**
```bash
# Runs automatically when devcontainer is created
pip install --user -r requirements-dev.txt
```

**Manual installation (if needed):**
```bash
pip install --user -r requirements-dev.txt
```

### Testing and Tooling

**Test dependencies in `requirements-dev.txt` (devcontainer):**
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `gunicorn` - WSGI server for local testing

**UI testing in dedicated Playwright container:**
- **Browser automation**: playwright, chromium
- **Testing**: pytest with parallel execution (xdist), timeouts, retries (rerunfailures)
- **Visual regression**: Pillow (images), pixelmatch (comparison)
- **Code quality**: ruff (linter), black (formatter), mypy (types)
- **Debugging**: ipython (REPL), ipdb (debugger), rich (output)
- **HTTP clients**: httpx (async), requests (sync)

**UI validation workflow:**
```bash
# Start Playwright container (one-time setup)
cd tooling/playwright && ./start-playwright.sh

# Run UI tests in container
./tooling/playwright/playwright-exec.sh pytest /workspace/ui_tests/tests -v

# Or use automated validation script
./tooling/run-ui-validation.sh
# (Installs from requirements-dev.txt automatically unless SKIP_UI_TEST_DEPS=1)
```

See `tooling/playwright/README.md` for complete container documentation.

## Why Two Files?

**`requirements.webhosting.txt` (production):**
- Minimal dependencies
- Only runtime requirements
- No testing/development tools
- Smaller deployment package
- Faster installation on server

**`requirements-dev.txt` (development):**
- Includes all production dependencies (`-r requirements.webhosting.txt`)
- Plus testing frameworks (pytest, pytest-asyncio)
- Plus development tools (gunicorn)
- Used only in devcontainer and CI/CD
- **NOTE**: Playwright moved to dedicated container (keeps devcontainer clean)

**`tooling/playwright/requirements.root.txt` (Playwright container):**
- Browser automation and UI testing tools
- Isolated from devcontainer for cleaner separation
- Comprehensive tooling for testing, debugging, visual regression
- See "UI Testing with Playwright Container" section in AGENTS.md

## Adding Dependencies

### Production Dependency (needed by Flask app)

Add to `requirements.webhosting.txt`:
```bash
echo "new-package>=1.0.0" >> requirements.webhosting.txt
```

Then reinstall in devcontainer:
```bash
pip install --user -r requirements-dev.txt
```

### Development/Testing Dependency

Add to `requirements-dev.txt` (below the `-r requirements.webhosting.txt` line):
```bash
# Edit requirements-dev.txt and add:
new-dev-tool>=2.0.0
```

Then reinstall:
```bash
pip install --user -r requirements-dev.txt
```

## Version Pinning

**Use flexible version constraints:**
- `>=X.Y.Z,<X+1.0.0` - Major version pin (recommended for production)
- `>=X.Y.Z` - Minimum version (for development tools)

**Examples:**
```
flask>=2.3.0,<4.0.0     # Allow minor/patch updates, pin major version
pytest>=9.0              # Development tool, latest is fine
```

## Verification

**Check installed packages:**
```bash
pip list --user
```

**Verify critical imports:**
```bash
python -c "import flask, pytest, gunicorn; print('✓ All critical packages installed')"
# Note: playwright is in dedicated container, not devcontainer
```

## Migration from Old System

**Before (scattered, conflicting):**
- `.devcontainer/requirements.txt` - Devcontainer packages (DELETED)
- Hardcoded packages in `post-create.sh` (REMOVED)
- `requirements.webhosting.txt` - Production packages (KEPT)
- Multiple pip install commands scattered across scripts

**After (clean, centralized):**
- `requirements.webhosting.txt` - Production runtime only
- `requirements-dev.txt` - Development/testing (includes production)
- Single source of truth for each environment
- All scripts reference the same files

## Troubleshooting

**Package import fails after installation:**
```bash
# Check user site-packages location
python -m site --user-site

# Verify package is installed
pip show <package-name>

# Force reinstall
pip install --user --force-reinstall <package-name>
```

**Conflicting versions:**
```bash
# Uninstall all versions
pip uninstall -y <package-name>

# Reinstall from requirements
pip install --user -r requirements-dev.txt
```

**Devcontainer pip issues:**
```bash
# Upgrade pip first
pip install --user --upgrade pip setuptools wheel

# Then retry
pip install --user -r requirements-dev.txt
```

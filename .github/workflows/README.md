# GitHub Actions Workflows

This directory contains automated CI/CD workflows for the netcup-api-filter project.

## Workflows

### `tests.yml` - Automated Testing and Linting

**Triggers:**
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop` branches

**Jobs:**

#### 1. Test Job
- **Matrix:** Python 3.9, 3.10, 3.11
- **Steps:**
  1. Checkout code
  2. Set up Python environment
  3. Cache pip dependencies for faster runs
  4. Install project dependencies
  5. **Lint with flake8** - Check for Python syntax errors and code quality
  6. **Check formatting with black** - Verify code style (non-blocking)
  7. **Type check with mypy** - Static type analysis (non-blocking)
  8. **Run unit tests** - Execute pytest on root-level tests

#### 2. Security Job
- **Python:** 3.11
- **Steps:**
  1. Checkout code
  2. Set up Python environment
  3. Install pip-audit
  4. **Run security audit** - Check dependencies for known CVEs (non-blocking)

#### 3. Lint Markdown Job
- **Steps:**
  1. Checkout code
  2. **Lint Markdown files** - Check documentation formatting (non-blocking)

## Configuration Files

- **`.flake8`** - Flake8 linting configuration
  - Max line length: 127 characters
  - Excludes: vendor, deploy, .venv, etc.
  - Ignores: E203, W503 (black compatibility)

- **`pyproject.toml`** - Black, mypy, and pytest configuration
  - Black line length: 127
  - Target Python versions: 3.9-3.11
  - Pytest configuration for test discovery

## Local Testing

Run the same checks locally before pushing:

```bash
# Install development dependencies
pip install flake8 black mypy pytest pytest-asyncio

# Run flake8
flake8 .

# Check formatting
black --check .

# Format code
black .

# Type check
mypy .

# Run tests
pytest
```

## Non-Blocking Checks

Some checks are set to `continue-on-error: true` and won't fail the build:
- Black formatting check (informational only)
- Mypy type checking (gradually improving coverage)
- Security audit (alerts but doesn't block)
- Markdown linting (documentation quality)

This allows gradual improvement without blocking development.

## Future Enhancements

- [ ] Add E2E UI tests (requires Playwright setup)
- [ ] Add code coverage reporting (codecov.io)
- [ ] Add automated dependency updates (Dependabot)
- [ ] Add Docker image building
- [ ] Add deployment automation (for staging/production)

## Status Badge

Add to README.md:

```markdown
![Tests](https://github.com/volkb79-2/netcup-api-filter/workflows/Tests/badge.svg)
```

## Troubleshooting

**Flake8 failures:**
- Check `.flake8` configuration
- Run locally: `flake8 <file>`
- Fix automatically where possible: `autopep8 -i <file>`

**Black formatting failures:**
- Run locally: `black .`
- This will automatically reformat code

**MyPy errors:**
- Add type hints incrementally
- Use `# type: ignore` for complex cases
- Configure in `pyproject.toml` as needed

**Security audit failures:**
- Review pip-audit output
- Update vulnerable dependencies: `pip install --upgrade <package>`
- Check for patches or workarounds
- Document exceptions in SECURITY.md if needed

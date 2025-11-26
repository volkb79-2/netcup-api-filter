# Root Inventory

Catalog of top-level files/directories, their purpose, and the proposed action as we prepare to move application code under `/src`.

## Legend

- **Keep (root)** – File stays where it is (e.g., docs, tooling, tests, deploy scripts).
- **Move → /src** – Part of the runtime application and should relocate into the new source tree.
- **Archive/Cleanup** – Legacy artifact or generated output we should delete or regenerate elsewhere.
- **Generated** – Build output or runtime state; keep gitignored.

## Documentation & Metadata

| Path | Type | Purpose | Action |
| --- | --- | --- | --- |
| `README.md` | File | Top-level overview | Keep (root) |
| `AGENTS.md` | File | Automation instructions | Keep (root) |
| `DOCS.md` | Symlink | Points to `docs/README.md` | Keep (root) |

## Build & Deployment Tooling

| Path | Type | Purpose | Action |
| --- | --- | --- | --- |
| `build-and-deploy.sh` | Script | Primary deployment pipeline (webhosting) | Keep (root) |
| `build-and-deploy-local.sh` | Script | Local parity deployment | Keep (root) |
| `build_deployment.py` | Script | Produces `deploy.zip` | Keep (root) – update once `/src` exists |
| `build_deployment_lib.sh` | Script | Shared helpers for deploy scripts | Keep (root) |
| `requirements.webhosting.txt` | File | Dependency lock for vendor build | Keep (root) |
| `Dockerfile` | File | Devcontainer build | Keep (root) |
| `docker-compose.yml` | File | Local stack orchestration | Keep (root) |
| `global-config.active.toml` | File | Workspace config (generated) | Generated |
| `global-config.defaults.toml` | File | Template config | Keep (root) |

## Application Modules (`src/netcup_api_filter`)

| Path | Notes |
| --- | --- |
| `src/netcup_api_filter/filter_proxy.py` | Main Flask app entry point (Flask factory + limiter) |
| `src/netcup_api_filter/passenger_wsgi.py` | Primary WSGI entrypoint (build copies to deployment root) |
| `src/netcup_api_filter/diagnostics/passenger_wsgi_hello.py` | Diagnostic hello-world WSGI entrypoint |
| `src/netcup_api_filter/wsgi.py`, `src/netcup_api_filter/cgi_handler.py` | Alternate deployment adapters (Gunicorn/CGI - legacy) |
| `src/netcup_api_filter/{access_control,admin_ui,client_portal,audit_logger,email_notifier,database,utils}.py` | Core modules |
| `src/netcup_api_filter/{netcup_client,netcup_client_mock,example_client,generate_token,list_config,migrate_yaml_to_db}.py` | Client integrations + CLI helpers |
| `src/netcup_api_filter/bootstrap/` | Seeding logic used by build/deploy |
| `src/netcup_api_filter/{templates,static}/` | Jinja templates + assets |
| `.env.defaults` | Single source of truth for default config values (version-controlled) |
| `.env.local`, `.env.webhosting` | Runtime environment state (gitignored, per-deployment) |

> Configuration is now 100% database-driven. `.env.defaults` provides initial values; runtime config managed via admin UI (stored in SQLite).
> Legacy YAML-based config system (`config.yaml`, `config.example.yaml`) removed.

## Operational Scripts (evaluate usefulness)

| Path | Purpose | Action |
| --- | --- | --- |
| `capture_ui_screenshots.py`, `quick_capture.py`, `analyze_ui_screenshots.py` | Screenshot tooling | Moved to `ui_tests/` alongside Playwright utilities |
| `debug_admin_content.py`, `debug_admin_login.py`, `debug_playwright_login.py`, `debug_db_lockout.py`, `debug_curl_login.sh` | Debug helpers | Removed (stale scripts) |
| `cleanup_legacy_ui.sh`, `report_ui_modernization.sh`, `test_fail_fast.sh`, `test_modern_ui.sh` | One-off validation scripts | Removed (served their purpose) |
| `clear_lockouts.py`, `remote_clear_lockouts.py` | Maintenance utilities | Removed |
| `reset_test_database.py`, `upload_debug.sh` | Maintenance scripts | Removed |
| `inspect_all.py`, `inspect_layouts.py` | UI inspection helpers | Removed |
| `run-comprehensive-tests.sh`, `run-local-tests.sh` | Test runners | Keep (root) | 
| `test_access_control.py`, `test_client_portal.py`, `test_client_scenarios_smoke.py`, `test_fs_standalone.py`, `test_system_info.py` | Pytests | Moved to `ui_tests/legacy_pytests/` |

## Tooling & Test Suites

| Path | Type | Action |
| --- | --- | --- |
| `tooling/` | Dir | Keep (root) |
| `ui_tests/` | Dir | Keep (root) |
| `pytest.ini` | File | Keep (root) |

## Build Artifacts & Data

| Path | Type | Notes | Action |
| --- | --- | --- | --- |
| `deploy/`, `deploy-local/`, `deploy-webhosting/` | Dirs | Build outputs | Generated |
| `deploy.zip`, `deploy.zip.sha256` | Files | Build outputs | Generated |
| `tmp/` | Dir | Temp/log output | Generated |
| `netcup_filter.db`, `netcup_filter.log`, `netcup_filter_audit.log`, `netcup_filter_startup_error.log` | Files | Runtime artifacts | Removed from root (regenerated under deploy-local/webhosting per run) |
| `cookies.txt` | File | Playwright/session artifact | Removed from root (generated within tooling pipelines) |

## Miscellaneous / Cleanup Candidates

| Path | Purpose | Action |
| --- | --- | --- |
| `=10.0.0`, `=3.0.0` | Stray pip output files | Removed; no creator scripts found |
| `__pycache__/` | Python cache | Removed |
| `passenger_wsgi_hello.py` | Diagnostic entrypoint | Moved to `src/diagnostics/passenger_wsgi_hello.py` |

This catalog should be refined as we confirm which debug scripts remain useful. Files marked for review will stay put until we finish dependency analysis.

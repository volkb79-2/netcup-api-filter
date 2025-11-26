# Documentation Hub

This folder contains the living documentation for the Netcup API Filter.

## Core Guides

- `CONFIGURATION_GUIDE.md` – Configuration layers, env defaults, and fail-fast policy.
- `OPERATIONS_GUIDE.md` – Build/test/deploy runbook and troubleshooting.
- `ADMIN_GUIDE.md` – Admin UI walkthrough for platform operators.
- `CLIENT_USAGE.md` – Token-holder instructions with API examples.

## Specialized Guides

- `CLIENT_AUTH.md` – Authentication models, token scopes, and API expectations.
- `DOCKER_NETWORKS.md` – Required Docker networks and topology notes for the devcontainer + proxies.
- `ENV_WORKSPACE.md` – Managing `.env.workspace` and other env files for local work.
- `EXAMPLES.md` – Common workflows and API usage patterns.
- `MCP_FUSE_SETUP.md` – Instructions for enabling FUSE/sshfs access inside the devcontainer.
- `PLAYWRIGHT_MCP_SETUP.md` – Details for running the Playwright MCP container and integration points.
- `READY_TO_DEPLOY.md` – Final preflight checklist before pushing to production.
- `SECURITY.md` – Security posture, hardening expectations, and threat model notes.
- `SSH_AGENT_PERSISTENCE.md` – Guide to the persistent SSH agent in the devcontainer.
- `UI_GUIDE.md` – UI walkthrough for operator-facing pages.
- `WEBHOSTING_DEPLOYMENT.md` – Hosting-specific deployment steps for the Netcup environment.

## Project Documentation (Repository Root)

These files live at the repository root for quick access:

- `../PLAYWRIGHT_CONTAINER.md` – Dedicated Playwright container architecture, setup, and troubleshooting.
- `../PYTHON_PACKAGES.md` – Python dependencies, requirements files, and package management.
- `../AGENTS.md` – Agent instructions and project context (for AI assistants).
- `../CLIENT_TEMPLATES.md` – Pre-configured client templates for common use cases.

## Deprecated / Historical References

See `docs/deprecated/` for archived summaries. They remain available for context but should not be updated; fold any new information into the active guides above.

## Keeping Docs Canonical

- Treat the files in this folder as the single source of truth; do not recreate new Markdown files in the repo root.
- When a feature or workflow changes, update the relevant guide here (and link it from `README.md` if it is new).
- If you need to preserve historical context, move the old content into `docs/deprecated/` instead of leaving duplicates elsewhere.
- Reuse the existing symlinks in the repo root so legacy references keep working without reintroducing clutter.

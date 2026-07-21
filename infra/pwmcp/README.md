# infra/pwmcp — Playwright-as-a-Service for the e2e gate

The gate image installs **no browser engine** (cockpit doctrine — see
`tooling/test-runner/Dockerfile`). UI/e2e tests offload the browser to this container
and drive it remotely over `ws://pwmcp:3000/`.

## What it is

`ghcr.io/volkb79-2/pwmcp:latest` — the shared, prebuilt unified Playwright image
(Playwright `run-server` on `:3000` + `@playwright/mcp` on `:8931`, under supervisord).
naf uses **only** the `:3000` `connect()` path. Mirrors `dstdns/infra/pwmcp`, but joins
**naf-dev-network** with alias `pwmcp` (the shared `dstdns-shared-local-pwmcp` sits on dstdns's
network, unreachable from here — hence naf's own instance; decision D-006/B).

## Use

This stack is ciu-managed (`ciu.defaults.toml.j2` + `ciu.compose.yml.j2`, root key
`pwmcp`) — bring it up via the central ciu orchestrator (`source ciu.env`, then
`ciu up`), not a bare `docker compose` invocation. See the header comments in
`ciu.compose.yml.j2` for why: a bare `docker compose -f ... up` here once adopted
dstdns's shared `dstdns-shared-local-pwmcp` because both directories share the basename
`pwmcp` (hit live, see `nyxloom-trove/backlog.md` B-INFRA); ciu scopes the compose
project name explicitly instead of falling back to the directory basename.

```bash
# run the e2e gate (defaults PLAYWRIGHT_SERVER_WS=ws://pwmcp:3000/)
./tooling/test-runner/testing-exec.sh e2e
```

The gate image must carry the `playwright` client (pinned `==1.61.*` in
`requirements-dev.txt` to match the image's Playwright version); no `playwright install`
is needed — the server owns the engine.

## Scope

INFRA-2 stands up the browser-offload path and proves connectivity. The **full**
`ui_tests/tests` suite additionally needs a deployed app peer on naf-dev-network
(deploy-local) — that, plus retiring the can't-fail ui_tests, is **naf-P06 part 2**.

This stack is now expressed as a ciu consumer template (`ciu.compose.yml.j2` +
`ciu.defaults.toml.j2`, INFRA-1 follow-up) with cgroup/mem governance; registering
it in the central stack registry (`ciu.global.defaults.toml.j2` `[deploy.phases...]`)
is tracked separately.

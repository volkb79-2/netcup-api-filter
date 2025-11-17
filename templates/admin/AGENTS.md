# Build and deployment

You can use the script `./build-and-deploy.sh` to build and deploy to the server and directoy defined in the script.

# Accesss the deployed system

Use the Playwright MCP harness under `tooling/playwright-mcp/` whenever you
need to interact with the deployed UI (login, create clients, inspect logs,
etc.). The quick steps are:

1. `cd tooling/playwright-mcp`
2. `docker compose up -d`
3. Register `http://localhost:8765/mcp` in your MCP-enabled chat client

The detailed build (including `docker buildx`) and troubleshooting notes are in
`tooling/playwright-mcp/README.md`.


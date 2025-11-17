# Build and deployment


## to live server via webhosting

The database will be reset and on first login the admin password needs to be changed. 

**Default credentials**: 'admin' / 'admin' 

You can use the script `./build-and-deploy.sh` to build and deploy to the server and directoy defined in the script.

see defined variables `NETCUP_USER`, `NETCUP_SERVER`, `REMOTE_DIR`, `PUBLIC_FQDN` how to access it.

## to local docker container 

use the container address to access it 

# Use Playwright

Use the Playwright MCP harness under `tooling/playwright-mcp/` whenever you
need to interact with the deployed UI (login, create clients, inspect logs,
etc.). The quick steps are:

1. `cd tooling/playwright-mcp`
2. `docker compose up -d`
3. Register `http://localhost:8765/mcp` in your MCP-enabled chat client

The detailed build (including `docker buildx`) and troubleshooting notes are in
`tooling/playwright-mcp/README.md`.

# Webhosting constraints

- the python application resides not inside the web server's document root
- via webhoster's management UI passenger is configured to pick up `passenger_wsgi.py` as startup

## `.htaccess` 

`.htaccess` is not used by the hoster, no overrides possible

# Repository structure

- `deploy` is a generated temporary folder holding copies for creating the `deploy.zip` created by `build_deploy.py`
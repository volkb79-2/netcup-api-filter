# Playwright MCP server container built on vanilla Python to allow pip-based updates
FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY tooling/playwright-mcp/requirements.txt ./requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY tooling/playwright-mcp/playwright_mcp_server.py ./playwright_mcp_server.py

# Ensure screenshots directory exists and has proper permissions
RUN mkdir -p /screenshots && chmod 775 /screenshots

EXPOSE 8765
VOLUME ["/screenshots"]

ENTRYPOINT ["python", "/app/playwright_mcp_server.py"]

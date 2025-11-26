# Generic Playwright container with optional MCP server
FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.root.txt ./
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl fonts-noto-color-emoji && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.root.txt && \
    python -m playwright install --with-deps chromium

# Create directories with world-writable permissions (will be mounted anyway)
RUN mkdir -p /screenshots && chmod 777 /screenshots && \
    mkdir -p /workspace && chmod 777 /workspace

# Copy MCP server script
COPY mcp_server.py /app/mcp_server.py

# Default to running bash (for exec commands)
# If MCP_ENABLED=true, docker-compose will override to run MCP server
CMD ["/bin/bash"]

# Note: No EXPOSE needed - ports defined in docker-compose.yml
# MCP server runs on port 8765 (configurable via MCP_PORT)
VOLUME ["/screenshots", "/workspace"]

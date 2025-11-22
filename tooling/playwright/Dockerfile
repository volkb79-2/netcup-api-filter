# Generic Playwright container with optional MCP server
FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt ./
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    python -m playwright install --with-deps chromium

# Create directories with world-writable permissions (will be mounted anyway)
RUN mkdir -p /screenshots && chmod 777 /screenshots && \
    mkdir -p /workspace && chmod 777 /workspace

# Optional: Copy MCP server script if it exists
# (Will be created during setup if MCP mode is needed)
RUN touch /app/mcp_server.py

# Default to running bash (for exec commands)
# If MCP_ENABLED=true, docker-compose will override to run MCP server
CMD ["/bin/bash"]

EXPOSE 8765
VOLUME ["/screenshots", "/workspace"]

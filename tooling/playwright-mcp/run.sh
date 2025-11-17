#!/bin/bash
# Dynamic user ID script for MCP Playwright
# Sets UID and GID environment variables for proper file permissions

# Get current user and docker group IDs
CURRENT_UID=$(id -u)
DOCKER_GID=$(getent group docker | cut -d: -f3)

echo "Starting MCP Playwright with UID=$CURRENT_UID, GID=$DOCKER_GID (docker group)"

# Run docker compose with the dynamic user settings
env UID=$CURRENT_UID GID=$DOCKER_GID docker compose "$@"
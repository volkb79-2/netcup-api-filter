#!/bin/bash
# Stop mock services
# Usage: ./stop.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# Load environment from .env.workspace if available
if [[ -f "${SCRIPT_DIR}/../../.env.workspace" ]]; then
    # shellcheck disable=SC1091
    set -a && source "${SCRIPT_DIR}/../../.env.workspace" && set +a
fi

echo "[INFO] Stopping mock services..."
docker compose down

echo "[OK] Mock services stopped"

#!/usr/bin/env bash
# Playwright setup helper — installs browser binaries for in-process mode.
#
# For remote Playwright-as-a-Service mode (no local binaries needed), set:
#   export PLAYWRIGHT_SERVER_WS=ws://<service-name>:3000/
# and skip this script entirely.
#
# See tooling/PLAYWRIGHT-TESTING.md for the full guide.

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}[INFO]${NC} Installing Playwright dependencies (in-process mode)..."

pip install --user -r "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ui_tests/requirements.txt"
python -m playwright install --with-deps chromium

echo -e "${GREEN}[SUCCESS]${NC} Playwright ready. Run tests with:"
echo "  pytest ui_tests/tests -v"
echo ""
echo "To use a remote Playwright-as-a-Service container instead:"
echo "  export PLAYWRIGHT_SERVER_WS=ws://<service-name>:3000/"
echo "  pytest ui_tests/tests -v"

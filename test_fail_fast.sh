#!/bin/bash
# Test fail-fast behavior of scripts
# Verifies that scripts fail immediately when required variables are missing

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_PASSED=0
TESTS_FAILED=0

test_script_fails_fast() {
    local script="$1"
    local var="$2"
    local description="$3"
    
    echo "Testing: $description"
    
    # Unset the variable and try to run script
    if (unset "$var"; bash -c "source '$script' 2>&1") | grep -q "$var"; then
        echo -e "${GREEN}✓ PASS${NC}: $script fails fast on missing $var"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}: $script should fail on missing $var"
        ((TESTS_FAILED++))
    fi
}

test_docker_compose_fails_fast() {
    local compose_file="$1"
    local var="$2"
    local description="$3"
    
    echo "Testing: $description"
    
    # Try to validate compose file without variable
    if (unset "$var"; cd "$(dirname "$compose_file")" && docker compose config 2>&1) | grep -q "$var"; then
        echo -e "${GREEN}✓ PASS${NC}: $compose_file requires $var"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}: $compose_file should require $var"
        ((TESTS_FAILED++))
    fi
}

echo "============================================"
echo "FAIL-FAST POLICY COMPLIANCE TESTS"
echo "============================================"
echo ""

# Test scripts
echo "--- Testing Shell Scripts ---"
test_script_fails_fast ".vscode/ensure-mcp-connection.sh" "DOCKER_NETWORK_INTERNAL" "ensure-mcp-connection.sh requires DOCKER_NETWORK_INTERNAL"

# Test docker-compose files
echo ""
echo "--- Testing Docker Compose Files ---"
test_docker_compose_fails_fast "tooling/playwright/docker-compose.yml" "DOCKER_UID" "playwright docker-compose requires DOCKER_UID"
test_docker_compose_fails_fast "tooling/playwright/docker-compose.yml" "DOCKER_NETWORK_INTERNAL" "playwright docker-compose requires DOCKER_NETWORK_INTERNAL"
test_docker_compose_fails_fast "tooling/local_proxy/docker-compose.yml" "LOCAL_PROXY_NETWORK" "local_proxy docker-compose requires LOCAL_PROXY_NETWORK"

# Summary
echo ""
echo "============================================"
echo "TEST SUMMARY"
echo "============================================"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
echo ""

if [[ $TESTS_FAILED -gt 0 ]]; then
    echo "Some tests failed - fail-fast policy not fully enforced"
    exit 1
else
    echo "All tests passed - fail-fast policy is enforced"
    exit 0
fi

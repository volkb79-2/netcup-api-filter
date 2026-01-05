#!/bin/bash
set -euo pipefail

echo "========================================="
echo "Testing HTTPS Deployment with Fixed Nginx"
echo "========================================="

# Stop everything first
echo "→ Stopping all services..."
./deploy.sh --stop > /dev/null 2>&1 || true

# Deploy with HTTPS
echo "→ Starting deployment with HTTPS (default)..."
./deploy.sh local --skip-tests 2>&1 | grep -E "(Phase|✓|✗|⚠|ERROR)" || true

# Check if reverse proxy is running
echo ""
echo "→ Checking container status..."
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(NAMES|naf-dev)"

# Check if reverse proxy is healthy (not restarting)
PROXY_STATUS=$(docker ps --filter "name=naf-dev-reverse-proxy" --format "{{.Status}}")
if echo "$PROXY_STATUS" | grep -q "Restarting"; then
    echo "✗ FAILED: Reverse proxy is restarting (nginx config issue)"
    docker logs naf-dev-reverse-proxy 2>&1 | tail -20
    exit 1
elif echo "$PROXY_STATUS" | grep -q "Up"; then
    echo "✓ SUCCESS: Reverse proxy is running stable"
else
    echo "⚠ WARNING: Reverse proxy not running"
    exit 1
fi

# Test HTTPS endpoint
echo ""
echo "→ Testing HTTPS endpoint..."
if curl -sk https://gstammtisch.dchive.de/admin/login | grep -q "Admin Login"; then
    echo "✓ SUCCESS: HTTPS endpoint responding correctly"
else
    echo "✗ FAILED: HTTPS endpoint not responding"
    exit 1
fi

echo ""
echo "========================================="
echo "✓ All tests passed!"
echo "========================================="

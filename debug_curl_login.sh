#!/usr/bin/env bash
set -euo pipefail

URL="https://naf.vxxu.de"
COOKIE_JAR="/tmp/test_cookies.txt"

echo "=========================================="
echo "Testing login with curl (verbose)"
echo "=========================================="
echo ""

# Clean up old cookies
rm -f "$COOKIE_JAR"

echo "STEP 1: GET login page to establish session"
echo "--------------------------------------------"
curl -v -c "$COOKIE_JAR" "${URL}/admin/login" 2>&1 | grep -E "(^< |^> |Set-Cookie|Cookie:)" || true

echo ""
echo ""
echo "STEP 2: POST login credentials"
echo "--------------------------------------------"
curl -v -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
    -X POST \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -H "Referer: ${URL}/admin/login" \
    -d "username=admin&password=admin" \
    "${URL}/admin/login" 2>&1 | grep -E "(^< |^> |Set-Cookie|Cookie:|Location:)" || true

echo ""
echo ""
echo "STEP 3: Check cookies"
echo "--------------------------------------------"
if [ -f "$COOKIE_JAR" ]; then
    echo "Cookies saved:"
    cat "$COOKIE_JAR"
else
    echo "No cookies saved"
fi

echo ""
echo ""
echo "STEP 4: Follow redirect (if any)"
echo "--------------------------------------------"
FINAL_URL=$(curl -s -b "$COOKIE_JAR" -c "$COOKIE_JAR" -w '%{url_effective}' -o /tmp/final_page.html "${URL}/admin/dashboard" || echo "FAILED")
echo "Final URL: $FINAL_URL"
echo ""
echo "Page content (first 500 chars):"
head -c 500 /tmp/final_page.html
echo ""
echo "..."

echo ""
echo ""
echo "STEP 5: Check for h1 heading"
echo "--------------------------------------------"
if grep -o '<h1[^>]*>.*</h1>' /tmp/final_page.html; then
    echo "[FOUND] h1 heading above"
else
    echo "[NOT FOUND] No h1 heading"
fi

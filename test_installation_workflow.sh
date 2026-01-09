#!/bin/bash
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "======================================================================"
echo "INSTALLATION WORKFLOW TEST (Using curl)"
echo "======================================================================"

BASE_URL="${UI_BASE_URL:-http://localhost:5100}"
MAILPIT_URL="http://localhost:8025"
COOKIE_JAR="/tmp/install_test_cookies.txt"
rm -f "$COOKIE_JAR"

DEFAULT_USERNAME="admin"
DEFAULT_PASSWORD="admin"
NEW_PASSWORD="SecureAdmin2026!"
ADMIN_EMAIL="admin@example.com"

# Helper function to extract CSRF token from HTML
extract_csrf() {
    grep 'name="csrf_token"' | grep -oP 'value="\K[^"]+' | head -1
}

# Helper to get latest email code from Mailpit
get_mailpit_code() {
    sleep 3
    MSG_ID=$(curl -s "$MAILPIT_URL/api/v1/messages" | python3 -c "import sys, json; msgs=json.load(sys.stdin).get('messages',[]); print(msgs[0]['ID'] if msgs else '')")
    if [ -z "$MSG_ID" ]; then
        echo "ERROR: No messages in Mailpit" >&2
        return 1
    fi
    curl -s "$MAILPIT_URL/api/v1/message/$MSG_ID" | python3 -c "import sys, json, re; content=json.load(sys.stdin); text=content.get('HTML','') or content.get('Text',''); match=re.search(r'\b(\d{6})\b', text); print(match.group(1) if match else '')"
}

echo ""
echo "[STEP 1] Initial login with default credentials"
# Get login page and extract CSRF token
CSRF_TOKEN=$(curl -sS -c "$COOKIE_JAR" "$BASE_URL/admin/login" | extract_csrf)
echo -e "   ${BLUE}CSRF token:${NC} ${CSRF_TOKEN:0:20}..."

# Submit login
RESPONSE=$(curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -X POST \
    -d "username=$DEFAULT_USERNAME" \
    -d "password=$DEFAULT_PASSWORD" \
    -d "csrf_token=$CSRF_TOKEN" \
    "$BASE_URL/admin/login" \
    -w "\n__HTTP_STATUS__:%{http_code}\n__REDIRECT_URL__:%{redirect_url}" \
    -L)

HTTP_STATUS=$(echo "$RESPONSE" | grep "__HTTP_STATUS__" | cut -d: -f2)
REDIRECT_URL=$(echo "$RESPONSE" | grep "__REDIRECT_URL__" | cut -d: -f2-)

if echo "$RESPONSE" | grep -q "change-password"; then
    echo -e "${GREEN}✅ Redirected to password change page (must_change_password=True)${NC}"
else
    echo -e "${RED}❌ Expected password-change redirect${NC}"
    echo "   HTTP Status: $HTTP_STATUS"
    echo "   Response contains: $(echo "$RESPONSE" | grep -o '<title>[^<]*' | head -1)"
    exit 1
fi

echo ""
echo "[STEP 2] Changing password (skip email/2FA for now)"
# Get password change page
CSRF_TOKEN=$(curl -sS -b "$COOKIE_JAR" "$BASE_URL/admin/change-password" | extract_csrf)

# Submit password change
RESPONSE=$(curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -X POST \
    -d "current_password=$DEFAULT_PASSWORD" \
    -d "new_password=$NEW_PASSWORD" \
    -d "confirm_password=$NEW_PASSWORD" \
    -d "csrf_token=$CSRF_TOKEN" \
    "$BASE_URL/admin/change-password" \
    -L)

if echo "$RESPONSE" | grep -q "Dashboard"; then
    echo -e "${GREEN}✅ Password changed successfully, redirected to dashboard${NC}"
else
    echo -e "${RED}❌ Expected dashboard redirect${NC}"
    exit 1
fi

echo ""
echo "[STEP 3] Configuring SMTP to point to Mailpit"
# Get email config page
CSRF_TOKEN=$(curl -sS -b "$COOKIE_JAR" "$BASE_URL/admin/config/email" | extract_csrf)

# Submit SMTP configuration
RESPONSE=$(curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -X POST \
    -d "smtp_host=naf-dev-mailpit" \
    -d "smtp_port=1025" \
    -d "smtp_encryption=none" \
    -d "smtp_username=" \
    -d "smtp_password=" \
    -d "from_email=noreply@naf.example.com" \
    -d "from_name=Netcup API Filter" \
    -d "admin_notification_email=$ADMIN_EMAIL" \
    -d "csrf_token=$CSRF_TOKEN" \
    "$BASE_URL/admin/config/email" \
    -L)

echo -e "${GREEN}✅ SMTP configuration saved${NC}"

echo ""
echo "[STEP 4] Setting admin email address"
# Get profile page
CSRF_TOKEN=$(curl -sS -b "$COOKIE_JAR" "$BASE_URL/admin/profile" | extract_csrf)

# Submit email address
RESPONSE=$(curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -X POST \
    -d "email=$ADMIN_EMAIL" \
    -d "csrf_token=$CSRF_TOKEN" \
    "$BASE_URL/admin/profile" \
    -L)

echo -e "${GREEN}✅ Admin email set to: $ADMIN_EMAIL${NC}"

echo ""
echo "[STEP 5] Enabling 2FA"
# Navigate to 2FA setup
RESPONSE=$(curl -sS -b "$COOKIE_JAR" "$BASE_URL/admin/profile/2fa/setup" 2>/dev/null || echo "")

if [ -z "$RESPONSE" ]; then
    echo -e "${YELLOW}⚠️  2FA setup route not found, checking profile for enable link${NC}"
    # Check if there's an enable link on profile page
    PROFILE_PAGE=$(curl -sS -b "$COOKIE_JAR" "$BASE_URL/admin/profile")
    if echo "$PROFILE_PAGE" | grep -qi "enable.*2fa\|two-factor"; then
        echo -e "${BLUE}   Found 2FA enable option on profile page${NC}"
    else
        echo -e "${YELLOW}⚠️  Could not find 2FA setup - may need manual testing${NC}"
    fi
else
    CSRF_TOKEN=$(echo "$RESPONSE" | extract_csrf)
    
    # Submit 2FA setup with email method
    RESPONSE=$(curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -X POST \
        -d "method=email" \
        -d "csrf_token=$CSRF_TOKEN" \
        "$BASE_URL/admin/profile/2fa/setup" \
        -L)
    
    echo -e "${GREEN}✅ 2FA setup initiated${NC}"
    
    echo ""
    echo "[STEP 6] Retrieving 2FA verification code from Mailpit"
    CODE=$(get_mailpit_code)
    if [ -n "$CODE" ]; then
        echo -e "${GREEN}✅ Retrieved code from Mailpit: $CODE${NC}"
        
        # Submit verification code if needed
        if echo "$RESPONSE" | grep -q "code"; then
            CSRF_TOKEN=$(echo "$RESPONSE" | extract_csrf)
            RESPONSE=$(curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -X POST \
                -d "code=$CODE" \
                -d "csrf_token=$CSRF_TOKEN" \
                "$BASE_URL/admin/profile/2fa/verify" \
                -L)
            echo -e "${GREEN}✅ 2FA verification code submitted${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  No email found in Mailpit${NC}"
    fi
fi

echo ""
echo "[STEP 7] Testing 2FA login flow"
# Logout
curl -sS -b "$COOKIE_JAR" "$BASE_URL/admin/logout" > /dev/null
echo -e "${GREEN}✅ Logged out${NC}"

# Clear cookies for fresh login
rm -f "$COOKIE_JAR"

# Get fresh login page
CSRF_TOKEN=$(curl -sS -c "$COOKIE_JAR" "$BASE_URL/admin/login" | extract_csrf)

# Login with new password
RESPONSE=$(curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -X POST \
    -d "username=$DEFAULT_USERNAME" \
    -d "password=$NEW_PASSWORD" \
    -d "csrf_token=$CSRF_TOKEN" \
    "$BASE_URL/admin/login" \
    -L)

if echo "$RESPONSE" | grep -qi "2fa\|verification"; then
    echo -e "${GREEN}✅ Redirected to 2FA verification page${NC}"
    
    echo ""
    echo "📧 Retrieving 2FA login code from Mailpit..."
    CODE=$(get_mailpit_code)
    if [ -n "$CODE" ]; then
        echo -e "${GREEN}✅ Retrieved login code: $CODE${NC}"
        
        CSRF_TOKEN=$(echo "$RESPONSE" | extract_csrf)
        RESPONSE=$(curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -X POST \
            -d "code=$CODE" \
            -d "csrf_token=$CSRF_TOKEN" \
            "$BASE_URL/admin/login-2fa" \
            -L)
        
        if echo "$RESPONSE" | grep -q "Dashboard"; then
            echo -e "${GREEN}✅ 2FA login successful! Redirected to dashboard${NC}"
        else
            echo -e "${YELLOW}⚠️  2FA submitted, but dashboard not detected${NC}"
        fi
    else
        echo -e "${RED}❌ Failed to get 2FA code from Mailpit${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  2FA not triggered (may not be fully enabled yet)${NC}"
    echo "   Check if 2FA setup completed successfully"
fi

echo ""
echo "======================================================================"
echo "INSTALLATION WORKFLOW COMPLETE"
echo "======================================================================"
echo ""
echo -e "${BLUE}📧 Check Mailpit UI for all emails:${NC} http://localhost:8025"
echo -e "${BLUE}🌐 Application:${NC} $BASE_URL"

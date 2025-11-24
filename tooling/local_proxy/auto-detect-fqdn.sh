#!/usr/bin/env bash
#
# auto-detect-fqdn.sh - Automatically detect public FQDN and populate proxy environment
#
# This script:
# 1. Queries external IP detection endpoints (ipify.org, icanhazip.com)
# 2. Performs reverse DNS lookup on detected IP
# 3. Populates PUBLIC_FQDN and INFRASTRUCTURE_PUBLIC_FQDN environment variables
# 4. Auto-updates TLS cert paths: /etc/letsencrypt/live/<detected-fqdn>/
# 5. Generates proxy.env with auto-detected values
#
# Usage:
#   ./auto-detect-fqdn.sh [--dry-run] [--output proxy.env]
#
# Options:
#   --dry-run: Print detected values without writing files
#   --output FILE: Write to custom file (default: proxy.env)
#   --verify-certs: Check if Let's Encrypt certificates exist for detected domain
#
# Environment variables (optional overrides):
#   FORCE_PUBLIC_IP: Skip IP detection, use this IP
#   FORCE_FQDN: Skip reverse DNS, use this FQDN
#   LE_CERT_BASE: Base directory for Let's Encrypt (default: /etc/letsencrypt)
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

# Parse arguments
DRY_RUN=0
OUTPUT_FILE="proxy.env"
VERIFY_CERTS=0

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --verify-certs)
            VERIFY_CERTS=1
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Configuration
LE_CERT_BASE="${LE_CERT_BASE:-/etc/letsencrypt}"
IP_DETECTION_ENDPOINTS=(
    "https://api.ipify.org"
    "https://icanhazip.com"
    "https://ifconfig.me/ip"
    "https://checkip.amazonaws.com"
)

# Step 1: Detect public IP
log_info "Detecting public IP address..."
PUBLIC_IP="${FORCE_PUBLIC_IP:-}"

if [[ -z "$PUBLIC_IP" ]]; then
    for endpoint in "${IP_DETECTION_ENDPOINTS[@]}"; do
        log_info "Trying endpoint: $endpoint"
        if PUBLIC_IP=$(curl -s --max-time 5 "$endpoint" | tr -d '[:space:]'); then
            if [[ "$PUBLIC_IP" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
                log_success "Detected public IP: $PUBLIC_IP"
                break
            else
                log_warn "Invalid IP format from $endpoint: $PUBLIC_IP"
                PUBLIC_IP=""
            fi
        else
            log_warn "Failed to query $endpoint"
        fi
    done
    
    if [[ -z "$PUBLIC_IP" ]]; then
        log_error "Failed to detect public IP from any endpoint"
        exit 1
    fi
else
    log_info "Using forced public IP: $PUBLIC_IP"
fi

# Step 2: Perform reverse DNS lookup
log_info "Performing reverse DNS lookup for $PUBLIC_IP..."
PUBLIC_FQDN="${FORCE_FQDN:-}"

if [[ -z "$PUBLIC_FQDN" ]]; then
    # Try multiple methods for reverse DNS
    if command -v dig &> /dev/null; then
        log_info "Using dig for reverse DNS..."
        PUBLIC_FQDN=$(dig +short -x "$PUBLIC_IP" | head -n1 | sed 's/\.$//')
    elif command -v host &> /dev/null; then
        log_info "Using host for reverse DNS..."
        PUBLIC_FQDN=$(host "$PUBLIC_IP" | awk '/domain name pointer/ {print $NF}' | sed 's/\.$//' | head -n1)
    elif command -v nslookup &> /dev/null; then
        log_info "Using nslookup for reverse DNS..."
        PUBLIC_FQDN=$(nslookup "$PUBLIC_IP" | awk '/name =/ {print $NF}' | sed 's/\.$//' | head -n1)
    else
        log_error "No DNS lookup tool found (dig, host, or nslookup required)"
        exit 1
    fi
    
    if [[ -z "$PUBLIC_FQDN" ]]; then
        log_error "Reverse DNS lookup failed for $PUBLIC_IP"
        log_info "You can force a FQDN with: FORCE_FQDN=your.domain.com $0"
        exit 1
    fi
    
    log_success "Detected public FQDN: $PUBLIC_FQDN"
else
    log_info "Using forced FQDN: $PUBLIC_FQDN"
fi

# Step 3: Verify Let's Encrypt certificates exist
CERT_PATH="${LE_CERT_BASE}/live/${PUBLIC_FQDN}"
FULLCHAIN_PATH="${CERT_PATH}/fullchain.pem"
PRIVKEY_PATH="${CERT_PATH}/privkey.pem"

if [[ $VERIFY_CERTS -eq 1 ]]; then
    log_info "Verifying Let's Encrypt certificates..."
    
    if [[ ! -d "$CERT_PATH" ]]; then
        log_error "Certificate directory does not exist: $CERT_PATH"
        log_info "Available certificates:"
        if [[ -d "${LE_CERT_BASE}/live" ]]; then
            ls -1 "${LE_CERT_BASE}/live/" || log_warn "No certificates found"
        else
            log_warn "Let's Encrypt live directory not found: ${LE_CERT_BASE}/live"
        fi
        exit 1
    fi
    
    if [[ ! -L "$FULLCHAIN_PATH" ]]; then
        log_error "Certificate file does not exist: $FULLCHAIN_PATH"
        exit 1
    fi
    
    if [[ ! -L "$PRIVKEY_PATH" ]]; then
        log_error "Private key does not exist: $PRIVKEY_PATH"
        exit 1
    fi
    
    # Verify symlinks resolve correctly
    FULLCHAIN_TARGET=$(readlink -f "$FULLCHAIN_PATH")
    PRIVKEY_TARGET=$(readlink -f "$PRIVKEY_PATH")
    
    if [[ ! -f "$FULLCHAIN_TARGET" ]]; then
        log_error "Certificate symlink broken: $FULLCHAIN_PATH -> $FULLCHAIN_TARGET"
        exit 1
    fi
    
    if [[ ! -f "$PRIVKEY_TARGET" ]]; then
        log_error "Private key symlink broken: $PRIVKEY_PATH -> $PRIVKEY_TARGET"
        exit 1
    fi
    
    log_success "Certificates verified:"
    log_info "  Fullchain: $FULLCHAIN_PATH -> $FULLCHAIN_TARGET"
    log_info "  Private Key: $PRIVKEY_PATH -> $PRIVKEY_TARGET"
else
    log_info "Certificate paths (not verified):"
    log_info "  Fullchain: $FULLCHAIN_PATH"
    log_info "  Private Key: $PRIVKEY_PATH"
    log_warn "Use --verify-certs to check if certificates exist"
fi

# Step 4: Generate proxy.env content
log_info "Generating proxy environment configuration..."

ENV_CONTENT=$(cat <<EOF
# Auto-generated by auto-detect-fqdn.sh on $(date -u +"%Y-%m-%d %H:%M:%S UTC")
# Detected public IP: $PUBLIC_IP
# Detected public FQDN: $PUBLIC_FQDN

# Public hostname of this machine (reverse DNS of the public IP)
LOCAL_TLS_DOMAIN=$PUBLIC_FQDN

# Hostname/port where the Flask app is reachable from the proxy container.
# Typically this is the devcontainer name on the shared Docker network. Set to
# __auto__ if you rely on tooling/run-ui-validation.sh so it injects the current
# hostname at runtime.
LOCAL_APP_HOST=__auto__
LOCAL_APP_PORT=5100

# External port bindings for HTTPS and HTTP->HTTPS redirect.
LOCAL_TLS_BIND_HTTPS=443
LOCAL_TLS_BIND_HTTP=80

# Path to the parent LetsEncrypt directory on the host (contains live/ and archive/).
# When running inside a devcontainer, point this to a /tmp directory and run
# ./stage-proxy-inputs.sh so Docker can read the files.
LE_CERT_BASE=${LE_CERT_BASE}

# Name of the Docker network that both the devcontainer and proxy should join.
LOCAL_PROXY_NETWORK=naf-local

# Directory that holds the rendered nginx configuration files (mounted to /etc/nginx/conf.d).
# In devcontainer: Auto-detects PHYSICAL_REPO_ROOT for direct bind mounting
# Fallback: /tmp/netcup-local-proxy/conf.d (requires staging via stage-proxy-inputs.sh)
LOCAL_PROXY_CONFIG_PATH=\${PHYSICAL_REPO_ROOT:-/tmp/netcup-local-proxy}/tooling/local_proxy/conf.d

# Auto-detected certificate paths (for verification only, computed from LE_CERT_BASE + LOCAL_TLS_DOMAIN)
# PUBLIC_TLS_CRT_PEM=${LE_CERT_BASE}/live/${PUBLIC_FQDN}/fullchain.pem
# PUBLIC_TLS_KEY_PEM=${LE_CERT_BASE}/live/${PUBLIC_FQDN}/privkey.pem
EOF
)

# Step 5: Write output or display dry-run
if [[ $DRY_RUN -eq 1 ]]; then
    log_info "DRY RUN - Would write to: $OUTPUT_FILE"
    echo ""
    echo "$ENV_CONTENT"
    echo ""
    log_info "To apply this configuration, run without --dry-run"
else
    # Backup existing file if present
    if [[ -f "$OUTPUT_FILE" ]]; then
        BACKUP_FILE="${OUTPUT_FILE}.backup.$(date +%s)"
        log_warn "Backing up existing file: $OUTPUT_FILE -> $BACKUP_FILE"
        cp "$OUTPUT_FILE" "$BACKUP_FILE"
    fi
    
    echo "$ENV_CONTENT" > "$OUTPUT_FILE"
    log_success "Configuration written to: $OUTPUT_FILE"
    
    # Display next steps
    echo ""
    log_info "Next steps:"
    log_info "  1. Review generated configuration: cat $OUTPUT_FILE"
    log_info "  2. Render nginx config: ./render-nginx-conf.sh"
    log_info "  3. Stage proxy inputs: ./stage-proxy-inputs.sh"
    log_info "  4. Start Flask backend: gunicorn tooling.local_proxy.local_app:app -b 0.0.0.0:5100"
    log_info "  5. Start proxy: docker compose --env-file $OUTPUT_FILE up -d"
    log_info "  6. Update /etc/hosts: echo '172.17.0.1 $PUBLIC_FQDN' >> /etc/hosts"
fi

# Step 6: Export for immediate use in shell
log_info "To use these values in your current shell:"
echo ""
echo "export PUBLIC_FQDN='$PUBLIC_FQDN'"
echo "export PUBLIC_IP='$PUBLIC_IP'"
echo "export PUBLIC_TLS_CRT_PEM='${LE_CERT_BASE}/live/${PUBLIC_FQDN}/fullchain.pem'"
echo "export PUBLIC_TLS_KEY_PEM='${LE_CERT_BASE}/live/${PUBLIC_FQDN}/privkey.pem'"
echo ""

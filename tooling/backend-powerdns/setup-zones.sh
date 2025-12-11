#!/usr/bin/env bash
# ============================================================================
# PowerDNS Zone Setup Script
# ============================================================================
# Purpose: Initialize PowerDNS with test zones for development
# 
# Usage:
#   ./setup-zones.sh                    # Interactive mode
#   ./setup-zones.sh dyn.vxxu.de        # Create specific zone
#   ./setup-zones.sh --help             # Show usage
# ============================================================================

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

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Source environment
source "${REPO_ROOT}/.env.workspace"
source "${REPO_ROOT}/.env.services"
source "${REPO_ROOT}/.env.defaults"
source "${SCRIPT_DIR}/.env"

# PowerDNS API configuration (from .env.services)
POWERDNS_API_URL="${POWERDNS_API_URL:-http://naf-dev-powerdns:8081}"
POWERDNS_API_KEY="${POWERDNS_API_KEY:?POWERDNS_API_KEY must be set in .env.defaults}"

# Default values (NS from PUBLIC_FQDN)
DEFAULT_ZONE="dyn.vxxu.de"
DEFAULT_NS="${PUBLIC_FQDN:-ns1.vxxu.de}"
DEFAULT_HOSTMASTER="hostmaster.vxxu.de"
DEFAULT_TTL="${POWERDNS_DEFAULT_TTL:-60}"

# Parse arguments
show_help() {
    cat <<EOF
PowerDNS Zone Setup Script

Usage:
    $0 [options] [zone]

Options:
    -h, --help              Show this help message
    --api-url URL           PowerDNS API URL (default: http://localhost:80)
    --api-key KEY           PowerDNS API key
    --ns HOSTNAME           Nameserver hostname (default: ns1.vxxu.de)
    --hostmaster EMAIL      Hostmaster email (default: hostmaster.vxxu.de)
    --ttl SECONDS           Default TTL (default: 60)

Arguments:
    zone                    Zone name to create (default: dyn.vxxu.de)

Examples:
    # Interactive setup with defaults
    $0
    
    # Create specific zone
    $0 dyn.example.com
    
    # Create zone with custom nameserver
    $0 --ns ns1.example.com dyn.example.com
    
    # Multiple zones
    $0 dyn.vxxu.de && $0 test.vxxu.de

DNS Delegation Setup (at parent zone):
    After creating zone 'dyn.vxxu.de', add to parent (vxxu.de):
    
    dyn.vxxu.de.  IN  NS  ns1.vxxu.de.
    ns1.vxxu.de.  IN  A   <PowerDNS-server-IP>
    ns1.vxxu.de.  IN  AAAA <PowerDNS-server-IPv6>

EOF
}

ZONE="${DEFAULT_ZONE}"
NS="${DEFAULT_NS}"
HOSTMASTER="${DEFAULT_HOSTMASTER}"
TTL="${DEFAULT_TTL}"

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        --api-url)
            POWERDNS_API_URL="$2"
            shift 2
            ;;
        --api-key)
            POWERDNS_API_KEY="$2"
            shift 2
            ;;
        --ns)
            NS="$2"
            shift 2
            ;;
        --hostmaster)
            HOSTMASTER="$2"
            shift 2
            ;;
        --ttl)
            TTL="$2"
            shift 2
            ;;
        -*)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
        *)
            ZONE="$1"
            shift
            ;;
    esac
done

# Validate zone format
if [[ ! "$ZONE" =~ ^[a-z0-9.-]+$ ]]; then
    log_error "Invalid zone name: $ZONE"
    exit 1
fi

# Ensure zone ends with dot for API
ZONE_FQDN="${ZONE}."
if [[ "$ZONE" == *. ]]; then
    ZONE_FQDN="$ZONE"
    ZONE="${ZONE%.}"
fi

log_info "PowerDNS Zone Setup"
log_info "===================="
log_info "API URL: $POWERDNS_API_URL"
log_info "Zone: $ZONE_FQDN"
log_info "Nameserver: $NS"
log_info "Hostmaster: $HOSTMASTER"
log_info "Default TTL: $TTL"
echo

# Check PowerDNS is running
log_info "Checking PowerDNS availability..."
if ! curl -sf -H "X-API-Key: $POWERDNS_API_KEY" \
    "${POWERDNS_API_URL}/api/v1/servers/localhost" > /dev/null; then
    log_error "PowerDNS API not accessible at $POWERDNS_API_URL"
    log_error "Is the PowerDNS container running?"
    log_info "Start it with: cd tooling/backend-powerdns && docker compose up -d"
    exit 1
fi
log_success "PowerDNS API is reachable"

# Check if zone already exists
log_info "Checking if zone exists..."
if curl -sf -H "X-API-Key: $POWERDNS_API_KEY" \
    "${POWERDNS_API_URL}/api/v1/servers/localhost/zones/${ZONE_FQDN}" > /dev/null; then
    log_warn "Zone $ZONE_FQDN already exists"
    log_info "To recreate, delete first:"
    log_info "  curl -X DELETE -H \"X-API-Key: \$POWERDNS_API_KEY\" \\"
    log_info "    ${POWERDNS_API_URL}/api/v1/servers/localhost/zones/${ZONE_FQDN}"
    exit 0
fi

# Create zone
log_info "Creating zone $ZONE_FQDN..."

# SOA serial (current timestamp)
SERIAL=$(date +%Y%m%d%H)

# Zone data
ZONE_DATA=$(cat <<EOF
{
  "name": "${ZONE_FQDN}",
  "kind": "Native",
  "masters": [],
  "nameservers": ["${NS}."],
  "rrsets": [
    {
      "name": "${ZONE_FQDN}",
      "type": "SOA",
      "ttl": ${TTL},
      "records": [{
        "content": "${NS}. ${HOSTMASTER}. ${SERIAL} 10800 3600 604800 ${TTL}",
        "disabled": false
      }]
    }
  ]
}
EOF
)

RESPONSE=$(curl -s -X POST \
    -H "X-API-Key: $POWERDNS_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$ZONE_DATA" \
    "${POWERDNS_API_URL}/api/v1/servers/localhost/zones" \
    -w "\n%{http_code}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
RESPONSE=$(echo "$RESPONSE" | sed '$d')

if [[ "$HTTP_CODE" == "201" ]]; then
    log_success "Zone $ZONE_FQDN created successfully"
    echo
    log_info "Zone details:"
    echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
    echo
    log_info "Next steps:"
    log_info "1. Add delegation in parent zone (e.g., at Netcup DNS for vxxu.de):"
    log_info "   ${ZONE_FQDN}  IN  NS  ${NS}."
    log_info ""
    log_info "2. Ensure glue record exists (A/AAAA for nameserver):"
    log_info "   ${NS}.  IN  A   <PowerDNS-server-IP>"
    log_info ""
    log_info "3. Add test record via API:"
    log_info "   curl -X PATCH -H \"X-API-Key: \$POWERDNS_API_KEY\" \\"
    log_info "     -H \"Content-Type: application/json\" \\"
    log_info "     -d '{\"rrsets\": [{\"name\": \"test.${ZONE_FQDN}\", \"type\": \"A\", \"changetype\": \"REPLACE\", \"ttl\": ${TTL}, \"records\": [{\"content\": \"192.0.2.1\", \"disabled\": false}]}]}' \\"
    log_info "     ${POWERDNS_API_URL}/api/v1/servers/localhost/zones/${ZONE_FQDN}"
    log_info ""
    log_info "4. Verify DNS resolution:"
    log_info "   dig @localhost -p 53 test.${ZONE} A"
else
    log_error "Failed to create zone"
    exit 1
fi

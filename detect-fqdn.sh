#!/usr/bin/env bash
#
# detect-fqdn.sh - Detect public FQDN via reverse DNS and update .env.workspace
#
# This script provides a single source of truth for PUBLIC_FQDN detection.
# All scripts should source .env.workspace instead of detecting FQDN themselves.
#
# Usage:
#   ./detect-fqdn.sh [--update-workspace]
#
# Options:
#   --update-workspace: Update .env.workspace with detected values
#   --silent: Suppress output (exit code indicates success/failure)
#
# Output:
#   PUBLIC_FQDN, PUBLIC_IP, PUBLIC_TLS_CRT_PEM, PUBLIC_TLS_KEY_PEM
#
# Exit codes:
#   0: Success
#   1: Failed to detect IP
#   2: Failed to detect FQDN (fallback to localhost)

set -euo pipefail

# Parse arguments
UPDATE_WORKSPACE=0
SILENT=0

while [[ $# -gt 0 ]]; do
    case $1 in
        --update-workspace)
            UPDATE_WORKSPACE=1
            shift
            ;;
        --silent)
            SILENT=1
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

log() {
    if [[ $SILENT -eq 0 ]]; then
        echo "$@" >&2
    fi
}

# Detect public IP
log "[INFO] Detecting public IP..."
PUBLIC_IP="${FORCE_PUBLIC_IP:-}"

if [[ -z "$PUBLIC_IP" ]]; then
    IP_ENDPOINTS=(
        "https://api.ipify.org"
        "https://icanhazip.com"
        "https://ifconfig.me/ip"
    )
    
    for endpoint in "${IP_ENDPOINTS[@]}"; do
        if PUBLIC_IP=$(curl -s --max-time 3 "$endpoint" 2>/dev/null | tr -d '[:space:]'); then
            if [[ "$PUBLIC_IP" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
                log "[SUCCESS] Detected IP: $PUBLIC_IP"
                break
            fi
        fi
        PUBLIC_IP=""
    done
fi

if [[ -z "$PUBLIC_IP" ]]; then
    log "[ERROR] Failed to detect public IP"
    exit 1
fi

# Perform reverse DNS lookup
log "[INFO] Performing reverse DNS lookup..."
PUBLIC_FQDN="${FORCE_FQDN:-}"

if [[ -z "$PUBLIC_FQDN" ]]; then
    if command -v dig >/dev/null 2>&1; then
        PUBLIC_FQDN=$(dig +short -x "$PUBLIC_IP" 2>/dev/null | sed 's/\.$//' | head -1 || echo "")
    elif command -v host >/dev/null 2>&1; then
        PUBLIC_FQDN=$(host "$PUBLIC_IP" 2>/dev/null | awk '/domain name pointer/ {print $NF}' | sed 's/\.$//' || echo "")
    fi
fi

if [[ -z "$PUBLIC_FQDN" ]]; then
    log "[WARN] No reverse DNS record found, using localhost"
    PUBLIC_FQDN="localhost"
    EXIT_CODE=2
else
    log "[SUCCESS] Detected FQDN: $PUBLIC_FQDN"
    EXIT_CODE=0
fi

# Construct TLS cert paths
PUBLIC_TLS_CRT_PEM="/etc/letsencrypt/live/${PUBLIC_FQDN}/fullchain.pem"
PUBLIC_TLS_KEY_PEM="/etc/letsencrypt/live/${PUBLIC_FQDN}/privkey.pem"

# Output for sourcing
echo "export PUBLIC_IP=\"${PUBLIC_IP}\""
echo "export PUBLIC_FQDN=\"${PUBLIC_FQDN}\""
echo "export PUBLIC_TLS_CRT_PEM=\"${PUBLIC_TLS_CRT_PEM}\""
echo "export PUBLIC_TLS_KEY_PEM=\"${PUBLIC_TLS_KEY_PEM}\""

# Update .env.workspace if requested
if [[ $UPDATE_WORKSPACE -eq 1 ]]; then
    WORKSPACE_ENV="${REPO_ROOT:-.}/.env.workspace"
    
    if [[ ! -f "$WORKSPACE_ENV" ]]; then
        log "[ERROR] .env.workspace not found at: $WORKSPACE_ENV"
        exit 1
    fi
    
    log "[INFO] Updating $WORKSPACE_ENV..."
    
    # Use temporary file for atomic update
    TMP_FILE=$(mktemp)
    
    # Update PUBLIC_FQDN and PUBLIC_IP lines
    if grep -q "^export PUBLIC_FQDN=" "$WORKSPACE_ENV"; then
        sed "s|^export PUBLIC_FQDN=.*|export PUBLIC_FQDN=\"${PUBLIC_FQDN}\"|" "$WORKSPACE_ENV" > "$TMP_FILE"
        mv "$TMP_FILE" "$WORKSPACE_ENV"
    else
        echo "export PUBLIC_FQDN=\"${PUBLIC_FQDN}\"" >> "$WORKSPACE_ENV"
    fi
    
    TMP_FILE=$(mktemp)
    if grep -q "^export PUBLIC_IP=" "$WORKSPACE_ENV"; then
        sed "s|^export PUBLIC_IP=.*|export PUBLIC_IP=\"${PUBLIC_IP}\"|" "$WORKSPACE_ENV" > "$TMP_FILE"
        mv "$TMP_FILE" "$WORKSPACE_ENV"
    else
        echo "export PUBLIC_IP=\"${PUBLIC_IP}\"" >> "$WORKSPACE_ENV"
    fi
    
    log "[SUCCESS] Updated .env.workspace"
fi

exit $EXIT_CODE

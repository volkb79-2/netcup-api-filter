"""
DDNS Protocol Endpoints - DynDNS2 and No-IP compatibility.

Provides DDNS protocol-compliant endpoints for major client tools (ddclient, 
inadyn, routers) while maintaining strict security through bearer token auth.

Protocols:
- DynDNS2: /api/ddns/dyndns2/update
- No-IP:   /api/ddns/noip/update

Security:
- Bearer token authentication only (NO username/password fallback)
- All requests through @require_auth decorator
- Realm-based authorization via check_permission()
- IP whitelisting support
- Auto IP detection with X-Forwarded-For handling

Response Format:
- Protocol-compliant text responses (not JSON)
- DynDNS2: good/nochg/badauth/!yours/notfqdn/dnserr/911
- No-IP: good/nochg/nohost/abuse/dnserr/911
"""
import ipaddress
import logging
import os
from flask import Blueprint, g, request

from ..database import get_setting
from ..token_auth import (
    check_permission,
    extract_bearer_token,
    log_activity,
    require_auth,
)

logger = logging.getLogger(__name__)

ddns_protocols_bp = Blueprint('ddns_protocols', __name__, url_prefix='/api/ddns')


# =============================================================================
# Configuration
# =============================================================================

def get_auto_ip_keywords():
    """Get list of keywords that trigger auto IP detection."""
    keywords_str = os.environ.get('DDNS_AUTO_IP_KEYWORDS', 'auto,public,detect')
    return [k.strip().lower() for k in keywords_str.split(',') if k.strip()]


def is_ddns_enabled():
    """Check if DDNS protocol support is enabled."""
    enabled = os.environ.get('DDNS_PROTOCOLS_ENABLED', 'true')
    return enabled.lower() in ('true', '1', 'yes')


# =============================================================================
# IP Detection
# =============================================================================

def get_client_ip():
    """
    Extract client IP from request, respecting X-Forwarded-For header.
    
    Returns the first IP in X-Forwarded-For if present, otherwise remote_addr.
    """
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # X-Forwarded-For can be: "client, proxy1, proxy2"
        # First IP is the original client
        client_ip = forwarded_for.split(',')[0].strip()
        logger.debug(f"Client IP from X-Forwarded-For: {client_ip}")
        return client_ip
    
    client_ip = request.remote_addr or 'unknown'
    logger.debug(f"Client IP from remote_addr: {client_ip}")
    return client_ip


def should_auto_detect_ip(myip_value):
    """
    Check if IP should be auto-detected based on myip value.
    
    Auto-detect if:
    - myip is None (not provided)
    - myip is empty string
    - myip is one of the configured keywords (auto, public, detect)
    """
    if myip_value is None or myip_value == '':
        return True
    
    if myip_value.lower() in get_auto_ip_keywords():
        return True
    
    return False


def validate_ip_address(ip_str):
    """
    Validate IP address format.
    
    Returns:
        (is_valid, is_ipv6, normalized_ip)
    """
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        is_ipv6 = isinstance(ip_obj, ipaddress.IPv6Address)
        return True, is_ipv6, str(ip_obj)
    except ValueError:
        return False, False, None


# =============================================================================
# Hostname Parsing
# =============================================================================

def parse_hostname(hostname):
    """
    Parse FQDN to extract domain and record name.
    
    Examples:
        device.example.com → domain=example.com, record=device
        sub.device.example.com → domain=device.example.com, record=sub
        example.com → domain=example.com, record=@ (or empty)
    
    Returns:
        (domain, record_name) or (None, None) if invalid
    """
    if not hostname or not isinstance(hostname, str):
        return None, None
    
    # Basic FQDN validation
    hostname = hostname.strip().lower()
    if not hostname or '.' not in hostname:
        return None, None
    
    # Split into parts
    parts = hostname.split('.')
    if len(parts) < 2:
        return None, None
    
    # Assume last two parts are the domain (simple heuristic)
    # For TLDs like .co.uk this may need adjustment
    domain = '.'.join(parts[-2:])
    
    if len(parts) == 2:
        # Apex domain (example.com)
        record_name = '@'
    else:
        # Subdomain (device.example.com)
        record_name = '.'.join(parts[:-2])
    
    return domain, record_name


def validate_hostname_format(hostname):
    """
    Basic FQDN format validation.
    
    Checks for basic DNS hostname rules:
    - Contains at least one dot
    - No consecutive dots
    - Valid characters (alphanumeric, hyphen, dot)
    - Each label starts/ends with alphanumeric
    """
    if not hostname or not isinstance(hostname, str):
        return False
    
    hostname = hostname.strip()
    
    # Must contain at least one dot
    if '.' not in hostname:
        return False
    
    # No consecutive dots
    if '..' in hostname:
        return False
    
    # Check each label
    labels = hostname.split('.')
    for label in labels:
        if not label:  # Empty label
            return False
        if len(label) > 63:  # DNS label max length
            return False
        if not label[0].isalnum() or not label[-1].isalnum():  # Must start/end with alphanumeric
            return False
        if not all(c.isalnum() or c == '-' for c in label):  # Valid chars only
            return False
    
    return True


# =============================================================================
# Netcup Client Integration
# =============================================================================

def get_netcup_client():
    """Get configured Netcup client."""
    from ..netcup_client import NetcupClient
    
    config = get_setting('netcup_config')
    if not config:
        return None
    
    return NetcupClient(
        customer_id=config.get('customer_id'),
        api_key=config.get('api_key'),
        api_password=config.get('api_password'),
        api_url=config.get('api_url', 'https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON'),
        timeout=config.get('timeout', 30)
    )


def update_dns_record(domain, hostname, ip_address, record_type):
    """
    Update or create DNS record via Netcup API.
    
    Args:
        domain: Domain name (e.g., example.com)
        hostname: Record hostname (e.g., device or @ for apex)
        ip_address: IP to set (IPv4 or IPv6)
        record_type: A or AAAA
    
    Returns:
        (success, error_message, changed)
    """
    netcup = get_netcup_client()
    if not netcup:
        return False, 'Netcup API not configured', False
    
    try:
        # Fetch current records
        info_result = netcup.info_dns_records(domain)
        
        if info_result.get('status') != 'success':
            error_msg = info_result.get('message', 'Failed to fetch records')
            logger.error(f"Netcup API error fetching records: {error_msg}")
            return False, error_msg, False
        
        records = info_result.get('responsedata', {}).get('dnsrecords', [])
        
        # Find existing record
        existing = None
        for rec in records:
            if rec.get('hostname') == hostname and rec.get('type') == record_type:
                existing = rec
                break
        
        # Check if update needed
        if existing and existing.get('destination') == ip_address:
            logger.info(f"DNS record already up to date: {hostname}.{domain} {record_type} {ip_address}")
            return True, None, False  # No change needed
        
        # Build update record
        if existing:
            record = {
                'id': existing['id'],
                'hostname': hostname,
                'type': record_type,
                'destination': ip_address
            }
            logger.info(f"Updating DNS record: {hostname}.{domain} {record_type} {ip_address} (was {existing.get('destination')})")
        else:
            record = {
                'hostname': hostname,
                'type': record_type,
                'destination': ip_address
            }
            logger.info(f"Creating DNS record: {hostname}.{domain} {record_type} {ip_address}")
        
        # Execute update
        result = netcup.update_dns_records(domain, [record])
        
        if result.get('status') != 'success':
            error_msg = result.get('message', 'Failed to update record')
            logger.error(f"Netcup API error updating record: {error_msg}")
            return False, error_msg, False
        
        return True, None, True  # Success with change
    
    except Exception as e:
        logger.exception(f"Error updating DNS record for {domain}")
        return False, str(e), False


# =============================================================================
# Protocol Response Helpers
# =============================================================================

def dyndns2_response(code, ip=None):
    """
    Generate DynDNS2 protocol response.
    
    Response codes:
        good <ip>    - Update successful
        nochg <ip>   - No change needed (IP already set)
        badauth      - Authentication failed
        !yours       - Permission denied (domain not in scope)
        notfqdn      - Hostname format invalid
        dnserr       - DNS/backend error
        911          - Internal server error
    """
    responses = {
        'good': (200, f'good {ip}'),
        'nochg': (200, f'nochg {ip}'),
        'badauth': (401, 'badauth'),
        '!yours': (403, '!yours'),
        'notfqdn': (400, 'notfqdn'),
        'dnserr': (502, 'dnserr'),
        '911': (500, '911'),
    }
    
    status_code, text = responses.get(code, (500, '911'))
    return text, status_code, {'Content-Type': 'text/plain; charset=utf-8'}


def noip_response(code, ip=None):
    """
    Generate No-IP protocol response.
    
    Response codes:
        good <ip>    - Update successful
        nochg <ip>   - No change needed
        nohost       - Authentication failed OR invalid hostname
        abuse        - Permission denied (domain not in scope)
        dnserr       - DNS/backend error
        911          - Internal server error
    """
    responses = {
        'good': (200, f'good {ip}'),
        'nochg': (200, f'nochg {ip}'),
        'nohost': (401, 'nohost'),  # Used for both auth and hostname errors
        'abuse': (403, 'abuse'),
        'dnserr': (502, 'dnserr'),
        '911': (500, '911'),
    }
    
    status_code, text = responses.get(code, (500, '911'))
    return text, status_code, {'Content-Type': 'text/plain; charset=utf-8'}


# =============================================================================
# Core DDNS Update Logic
# =============================================================================

def process_ddns_update(protocol='dyndns2'):
    """
    Process DDNS update request for either protocol.
    
    Args:
        protocol: 'dyndns2' or 'noip'
    
    Returns:
        Flask response tuple (text, status_code, headers)
    """
    # Check if DDNS is enabled
    if not is_ddns_enabled():
        logger.warning(f"DDNS {protocol} request rejected: feature disabled")
        if protocol == 'dyndns2':
            return dyndns2_response('911')
        else:
            return noip_response('911')
    
    # Get response helper for protocol
    response_func = dyndns2_response if protocol == 'dyndns2' else noip_response
    auth_error = 'badauth' if protocol == 'dyndns2' else 'nohost'
    permission_error = '!yours' if protocol == 'dyndns2' else 'abuse'
    hostname_error = 'notfqdn' if protocol == 'dyndns2' else 'nohost'
    
    # Extract parameters (support both GET query and POST form data)
    hostname = request.args.get('hostname') or request.form.get('hostname')
    myip = request.args.get('myip') or request.form.get('myip')
    
    # Get client IP
    client_ip = get_client_ip()
    
    # Validate hostname parameter
    if not hostname:
        logger.warning(f"DDNS {protocol}: hostname parameter missing")
        log_activity(
            auth=g.auth,
            action='ddns_update',
            operation='update',
            source_ip=client_ip,
            status='denied',
            error_code='missing_parameter',
            status_reason='hostname parameter required',
            request_data={'protocol': protocol}
        )
        return response_func(hostname_error)
    
    # Validate hostname format
    if not validate_hostname_format(hostname):
        logger.warning(f"DDNS {protocol}: invalid hostname format: {hostname}")
        log_activity(
            auth=g.auth,
            action='ddns_update',
            operation='update',
            source_ip=client_ip,
            status='denied',
            error_code='invalid_hostname',
            status_reason=f'Invalid hostname format: {hostname}',
            request_data={'protocol': protocol, 'hostname': hostname}
        )
        return response_func(hostname_error)
    
    # Parse hostname to extract domain and record name
    domain, record_name = parse_hostname(hostname)
    if not domain:
        logger.warning(f"DDNS {protocol}: failed to parse hostname: {hostname}")
        log_activity(
            auth=g.auth,
            action='ddns_update',
            operation='update',
            source_ip=client_ip,
            status='denied',
            error_code='invalid_hostname',
            status_reason=f'Failed to parse hostname: {hostname}',
            request_data={'protocol': protocol, 'hostname': hostname}
        )
        return response_func(hostname_error)
    
    # Determine IP address
    if should_auto_detect_ip(myip):
        ip_address = client_ip
        logger.info(f"DDNS {protocol}: auto-detected IP: {ip_address} (from {myip or 'empty'})")
    else:
        ip_address = myip
        logger.info(f"DDNS {protocol}: explicit IP: {ip_address}")
    
    # Validate IP address
    is_valid_ip, is_ipv6, normalized_ip = validate_ip_address(ip_address)
    if not is_valid_ip:
        logger.warning(f"DDNS {protocol}: invalid IP address: {ip_address}")
        log_activity(
            auth=g.auth,
            action='ddns_update',
            operation='update',
            domain=domain,
            record_name=record_name,
            source_ip=client_ip,
            status='denied',
            error_code='invalid_ip',
            status_reason=f'Invalid IP address: {ip_address}',
            request_data={'protocol': protocol, 'hostname': hostname, 'myip': myip}
        )
        return response_func('dnserr')
    
    ip_address = normalized_ip  # Use normalized form
    record_type = 'AAAA' if is_ipv6 else 'A'
    
    # Check permission
    perm = check_permission(
        auth=g.auth,
        operation='update',
        domain=domain,
        record_type=record_type,
        record_name=record_name,
        client_ip=client_ip
    )
    
    if not perm.granted:
        logger.warning(
            f"DDNS {protocol}: permission denied for {hostname} "
            f"(domain={domain}, record={record_name}): {perm.reason}"
        )
        log_activity(
            auth=g.auth,
            action='ddns_update',
            operation='update',
            domain=domain,
            record_type=record_type,
            record_name=record_name,
            source_ip=client_ip,
            status='denied',
            error_code=perm.error_code,
            status_reason=perm.reason,
            request_data={
                'protocol': protocol,
                'hostname': hostname,
                'ip': ip_address,
                'detected_ip': client_ip
            }
        )
        return response_func(permission_error)
    
    # Update DNS record
    success, error_msg, changed = update_dns_record(domain, record_name, ip_address, record_type)
    
    if not success:
        logger.error(f"DDNS {protocol}: DNS update failed for {hostname}: {error_msg}")
        log_activity(
            auth=g.auth,
            action='ddns_update',
            operation='update',
            domain=domain,
            record_type=record_type,
            record_name=record_name,
            source_ip=client_ip,
            status='error',
            status_reason=f'DNS update failed: {error_msg}',
            request_data={
                'protocol': protocol,
                'hostname': hostname,
                'ip': ip_address,
                'detected_ip': client_ip
            }
        )
        return response_func('dnserr')
    
    # Success!
    result_code = 'good' if changed else 'nochg'
    logger.info(
        f"DDNS {protocol}: {result_code} - {hostname} {record_type} → {ip_address} "
        f"(token={g.auth.token.token_name if g.auth.token else 'unknown'})"
    )
    log_activity(
        auth=g.auth,
        action='ddns_update',
        operation='update',
        domain=domain,
        record_type=record_type,
        record_name=record_name,
        source_ip=client_ip,
        status='success',
        request_data={
            'protocol': protocol,
            'hostname': hostname,
            'ip': ip_address,
            'detected_ip': client_ip
        },
        response_summary={
            'result': result_code,
            'changed': changed,
            'record_type': record_type
        }
    )
    
    return response_func(result_code, ip_address)


# =============================================================================
# Protocol Endpoints
# =============================================================================

@ddns_protocols_bp.route('/dyndns2/update', methods=['GET', 'POST'])
@require_auth
def dyndns2_update():
    """
    DynDNS2-compatible update endpoint.
    
    Query/Form Parameters:
        hostname: FQDN to update (required)
        myip: IP address (optional, auto-detect if missing/empty/auto/public)
        username: Ignored (legacy compatibility)
        password: Ignored (legacy compatibility)
    
    Authentication:
        Bearer token in Authorization header (REQUIRED)
    
    Response Codes:
        good <ip>    - Update successful (200)
        nochg <ip>   - No change needed (200)
        badauth      - Authentication failed (401)
        !yours       - Permission denied (403)
        notfqdn      - Invalid hostname (400)
        dnserr       - DNS error (502)
        911          - Server error (500)
    """
    return process_ddns_update(protocol='dyndns2')


@ddns_protocols_bp.route('/noip/update', methods=['GET', 'POST'])
@require_auth
def noip_update():
    """
    No-IP compatible update endpoint.
    
    Query/Form Parameters:
        hostname: FQDN to update (required)
        myip: IP address (optional, auto-detect if missing/empty/auto/public)
        username: Ignored (legacy compatibility)
        password: Ignored (legacy compatibility)
    
    Authentication:
        Bearer token in Authorization header (REQUIRED)
    
    Response Codes:
        good <ip>    - Update successful (200)
        nochg <ip>   - No change needed (200)
        nohost       - Auth failed or invalid hostname (401/400)
        abuse        - Permission denied (403)
        dnserr       - DNS error (502)
        911          - Server error (500)
    """
    return process_ddns_update(protocol='noip')

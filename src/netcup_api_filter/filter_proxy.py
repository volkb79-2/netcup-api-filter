"""
Netcup DNS API Filter Proxy (v2 - Bearer Token Authentication).

Proxies DNS API requests to Netcup, applying realm and permission restrictions
based on Bearer token authentication.
"""
import logging
import os
from typing import Any

import httpx
from flask import Blueprint, jsonify, request, g

from .models import (
    APIToken, 
    AccountRealm, 
    parse_token,
    hash_token,
)
from .token_auth import (
    authenticate_token,
    check_permission,
    require_auth,
    log_activity,
)
from .database import db

logger = logging.getLogger(__name__)

# Netcup API configuration
NETCUP_API_URL = os.environ.get('NETCUP_API_URL', 'https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON')
NETCUP_CUSTOMER_ID = os.environ.get('NETCUP_CUSTOMER_ID', '')
NETCUP_API_KEY = os.environ.get('NETCUP_API_KEY', '')
NETCUP_API_PASSWORD = os.environ.get('NETCUP_API_PASSWORD', '')

# HTTP client timeout
REQUEST_TIMEOUT = int(os.environ.get('NETCUP_API_TIMEOUT', '30'))


class NetcupAPIError(Exception):
    """Raised when Netcup API returns an error."""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


def call_netcup_api(action: str, params: dict[str, Any]) -> dict[str, Any]:
    """
    Call the Netcup API with given action and parameters.
    
    Args:
        action: API action name
        params: Action-specific parameters
        
    Returns:
        API response data
        
    Raises:
        NetcupAPIError: On API error or timeout
    """
    if not NETCUP_CUSTOMER_ID or not NETCUP_API_KEY or not NETCUP_API_PASSWORD:
        raise NetcupAPIError("Netcup API credentials not configured", 500)
    
    payload = {
        "action": action,
        "param": {
            "customernumber": NETCUP_CUSTOMER_ID,
            "apikey": NETCUP_API_KEY,
            "apipassword": NETCUP_API_PASSWORD,
            **params
        }
    }
    
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.post(NETCUP_API_URL, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        logger.error("Netcup API timeout")
        raise NetcupAPIError("API request timed out", 504)
    except httpx.HTTPError as e:
        logger.error(f"Netcup API HTTP error: {e}")
        raise NetcupAPIError(f"API request failed: {e}", 502)
    except Exception as e:
        logger.error(f"Netcup API error: {e}")
        raise NetcupAPIError(f"API error: {e}", 500)
    
    if data.get("status") != "success":
        msg = data.get("longmessage") or data.get("shortmessage") or "Unknown error"
        logger.warning(f"Netcup API error: {msg}")
        raise NetcupAPIError(msg, 400)
    
    return data.get("responsedata", {})


def filter_records_by_realm(
    records: list[dict],
    realm: AccountRealm,
    domain: str
) -> list[dict]:
    """
    Filter DNS records based on realm restrictions.
    
    Args:
        records: List of DNS records from Netcup
        realm: Realm to apply filtering for
        domain: Domain name
        
    Returns:
        Filtered list of records
    """
    filtered = []
    realm_value = realm.realm_value
    allowed_types = realm.record_types_list
    
    for record in records:
        hostname = record.get("hostname", "@")
        record_type = record.get("type", "")
        
        # Check record type is allowed
        if allowed_types and record_type not in allowed_types:
            continue
        
        # Check hostname matches realm
        if realm.realm_type == "host":
            # Exact match only
            if hostname != realm_value:
                continue
        elif realm.realm_type == "subdomain":
            # Apex + all children
            if hostname != realm_value and not hostname.endswith(f".{realm_value}"):
                if realm_value != "@" and hostname != "@":
                    continue
        elif realm.realm_type == "subdomain_only":
            # Children only, not apex
            if not hostname.endswith(f".{realm_value}"):
                continue
        
        filtered.append(record)
    
    return filtered


def check_hostname_in_realm(hostname: str, realm: AccountRealm) -> bool:
    """
    Check if a hostname is within a realm's scope.
    
    Args:
        hostname: DNS record hostname
        realm: Realm to check against
        
    Returns:
        True if hostname is within realm
    """
    realm_value = realm.realm_value
    
    if realm.realm_type == "host":
        return hostname == realm_value
    elif realm.realm_type == "subdomain":
        return hostname == realm_value or hostname.endswith(f".{realm_value}")
    elif realm.realm_type == "subdomain_only":
        return hostname.endswith(f".{realm_value}")
    
    return False


# Blueprint for filter proxy
filter_proxy_bp = Blueprint('filter_proxy', __name__)


@filter_proxy_bp.route('/api/dns/<domain>/records', methods=['GET'])
@require_auth
def get_records(domain: str):
    """
    Get DNS records for a domain, filtered by realm.
    
    Token must have 'read' permission and realm matching the domain.
    """
    token: APIToken = g.token
    realm: AccountRealm = g.realm
    
    # Check read permission
    if not check_permission(token, realm, 'read'):
        log_activity(token, 'read_denied', domain=domain, success=False)
        return jsonify({
            'error': 'forbidden',
            'message': 'Token does not have read permission for this realm'
        }), 403
    
    try:
        data = call_netcup_api("infoDnsRecords", {"domainname": domain})
        records = data.get("dnsrecords", [])
        
        # Filter by realm
        filtered = filter_records_by_realm(records, realm, domain)
        
        log_activity(token, 'read', domain=domain, details=f"{len(filtered)} records", success=True)
        
        return jsonify({
            'domain': domain,
            'records': filtered,
            'count': len(filtered)
        })
        
    except NetcupAPIError as e:
        log_activity(token, 'read', domain=domain, success=False, details=str(e))
        return jsonify({'error': 'api_error', 'message': str(e)}), e.status_code


@filter_proxy_bp.route('/api/dns/<domain>/records', methods=['POST'])
@require_auth
def create_record(domain: str):
    """
    Create a DNS record.
    
    Token must have 'create' permission and record must be within realm.
    """
    token: APIToken = g.token
    realm: AccountRealm = g.realm
    
    # Check create permission
    if not check_permission(token, realm, 'create'):
        log_activity(token, 'create_denied', domain=domain, success=False)
        return jsonify({
            'error': 'forbidden',
            'message': 'Token does not have create permission'
        }), 403
    
    data = request.get_json() or {}
    hostname = data.get('hostname', '@')
    record_type = data.get('type', 'A')
    destination = data.get('destination', '')
    priority = data.get('priority')
    
    # Validate hostname within realm
    if not check_hostname_in_realm(hostname, realm):
        log_activity(token, 'create_denied', domain=domain, 
                    details=f"hostname {hostname} outside realm", success=False)
        return jsonify({
            'error': 'forbidden',
            'message': f'Hostname {hostname} is outside your realm'
        }), 403
    
    # Check record type is allowed
    allowed_types = realm.record_types_list
    if allowed_types and record_type not in allowed_types:
        log_activity(token, 'create_denied', domain=domain,
                    details=f"type {record_type} not allowed", success=False)
        return jsonify({
            'error': 'forbidden',
            'message': f'Record type {record_type} not allowed for this realm'
        }), 403
    
    # Build record
    record = {
        "hostname": hostname,
        "type": record_type,
        "destination": destination,
    }
    if priority is not None:
        record["priority"] = priority
    
    try:
        # Get existing records first
        existing_data = call_netcup_api("infoDnsRecords", {"domainname": domain})
        existing_records = existing_data.get("dnsrecords", [])
        
        # Add new record
        existing_records.append(record)
        
        # Update all records
        call_netcup_api("updateDnsRecords", {
            "domainname": domain,
            "dnsrecordset": {"dnsrecords": existing_records}
        })
        
        log_activity(token, 'create', domain=domain,
                    details=f"{record_type} {hostname} -> {destination}", success=True)
        
        return jsonify({
            'message': 'Record created',
            'record': record
        }), 201
        
    except NetcupAPIError as e:
        log_activity(token, 'create', domain=domain, success=False, details=str(e))
        return jsonify({'error': 'api_error', 'message': str(e)}), e.status_code


@filter_proxy_bp.route('/api/dns/<domain>/records/<int:record_id>', methods=['PUT'])
@require_auth
def update_record(domain: str, record_id: int):
    """
    Update a DNS record.
    
    Token must have 'update' permission and record must be within realm.
    """
    token: APIToken = g.token
    realm: AccountRealm = g.realm
    
    # Check update permission
    if not check_permission(token, realm, 'update'):
        log_activity(token, 'update_denied', domain=domain, success=False)
        return jsonify({
            'error': 'forbidden',
            'message': 'Token does not have update permission'
        }), 403
    
    data = request.get_json() or {}
    
    try:
        # Get existing records
        existing_data = call_netcup_api("infoDnsRecords", {"domainname": domain})
        existing_records = existing_data.get("dnsrecords", [])
        
        # Find record by id
        target_record = None
        for rec in existing_records:
            if rec.get("id") == str(record_id) or rec.get("id") == record_id:
                target_record = rec
                break
        
        if not target_record:
            return jsonify({'error': 'not_found', 'message': 'Record not found'}), 404
        
        # Check hostname within realm
        hostname = target_record.get("hostname", "@")
        if not check_hostname_in_realm(hostname, realm):
            log_activity(token, 'update_denied', domain=domain,
                        details=f"hostname {hostname} outside realm", success=False)
            return jsonify({
                'error': 'forbidden',
                'message': f'Hostname {hostname} is outside your realm'
            }), 403
        
        # Check record type is allowed
        record_type = target_record.get("type", "")
        allowed_types = realm.record_types_list
        if allowed_types and record_type not in allowed_types:
            log_activity(token, 'update_denied', domain=domain,
                        details=f"type {record_type} not allowed", success=False)
            return jsonify({
                'error': 'forbidden',
                'message': f'Record type {record_type} not allowed'
            }), 403
        
        # Apply updates
        if 'destination' in data:
            target_record['destination'] = data['destination']
        if 'priority' in data:
            target_record['priority'] = data['priority']
        
        # Update all records
        call_netcup_api("updateDnsRecords", {
            "domainname": domain,
            "dnsrecordset": {"dnsrecords": existing_records}
        })
        
        log_activity(token, 'update', domain=domain,
                    details=f"record {record_id}", success=True)
        
        return jsonify({
            'message': 'Record updated',
            'record': target_record
        })
        
    except NetcupAPIError as e:
        log_activity(token, 'update', domain=domain, success=False, details=str(e))
        return jsonify({'error': 'api_error', 'message': str(e)}), e.status_code


@filter_proxy_bp.route('/api/dns/<domain>/records/<int:record_id>', methods=['DELETE'])
@require_auth
def delete_record(domain: str, record_id: int):
    """
    Delete a DNS record.
    
    Token must have 'delete' permission and record must be within realm.
    """
    token: APIToken = g.token
    realm: AccountRealm = g.realm
    
    # Check delete permission
    if not check_permission(token, realm, 'delete'):
        log_activity(token, 'delete_denied', domain=domain, success=False)
        return jsonify({
            'error': 'forbidden',
            'message': 'Token does not have delete permission'
        }), 403
    
    try:
        # Get existing records
        existing_data = call_netcup_api("infoDnsRecords", {"domainname": domain})
        existing_records = existing_data.get("dnsrecords", [])
        
        # Find record by id
        target_record = None
        target_index = None
        for i, rec in enumerate(existing_records):
            if rec.get("id") == str(record_id) or rec.get("id") == record_id:
                target_record = rec
                target_index = i
                break
        
        if not target_record:
            return jsonify({'error': 'not_found', 'message': 'Record not found'}), 404
        
        # Check hostname within realm
        hostname = target_record.get("hostname", "@")
        if not check_hostname_in_realm(hostname, realm):
            log_activity(token, 'delete_denied', domain=domain,
                        details=f"hostname {hostname} outside realm", success=False)
            return jsonify({
                'error': 'forbidden',
                'message': f'Hostname {hostname} is outside your realm'
            }), 403
        
        # Check record type is allowed
        record_type = target_record.get("type", "")
        allowed_types = realm.record_types_list
        if allowed_types and record_type not in allowed_types:
            log_activity(token, 'delete_denied', domain=domain,
                        details=f"type {record_type} not allowed", success=False)
            return jsonify({
                'error': 'forbidden',
                'message': f'Record type {record_type} not allowed'
            }), 403
        
        # Remove record
        del existing_records[target_index]
        
        # Update all records (Netcup requires sending all records)
        # For delete, we need to mark the record with deleterecord flag
        # Actually, Netcup API uses deleterecord flag
        target_record['deleterecord'] = True
        existing_records.append(target_record)
        
        call_netcup_api("updateDnsRecords", {
            "domainname": domain,
            "dnsrecordset": {"dnsrecords": existing_records}
        })
        
        log_activity(token, 'delete', domain=domain,
                    details=f"record {record_id}", success=True)
        
        return jsonify({'message': 'Record deleted'})
        
    except NetcupAPIError as e:
        log_activity(token, 'delete', domain=domain, success=False, details=str(e))
        return jsonify({'error': 'api_error', 'message': str(e)}), e.status_code


@filter_proxy_bp.route('/api/ddns/<domain>/<hostname>', methods=['GET', 'POST'])
@require_auth
def ddns_update(domain: str, hostname: str):
    """
    DDNS convenience endpoint for updating A/AAAA records.
    
    Query parameters:
    - ip: IPv4 address (uses client IP if not specified)
    - ipv6: IPv6 address
    - auto: If 'true', auto-detect IP from request
    
    Token must have 'update' permission.
    """
    token: APIToken = g.token
    realm: AccountRealm = g.realm
    
    # Check update permission
    if not check_permission(token, realm, 'update'):
        log_activity(token, 'ddns_denied', domain=domain, success=False)
        return jsonify({
            'error': 'forbidden',
            'message': 'Token does not have update permission'
        }), 403
    
    # Check hostname within realm
    if not check_hostname_in_realm(hostname, realm):
        log_activity(token, 'ddns_denied', domain=domain,
                    details=f"hostname {hostname} outside realm", success=False)
        return jsonify({
            'error': 'forbidden',
            'message': f'Hostname {hostname} is outside your realm'
        }), 403
    
    # Check record types are allowed
    allowed_types = realm.record_types_list
    if allowed_types:
        if 'A' not in allowed_types and 'AAAA' not in allowed_types:
            log_activity(token, 'ddns_denied', domain=domain,
                        details="A/AAAA not allowed", success=False)
            return jsonify({
                'error': 'forbidden',
                'message': 'A/AAAA record types not allowed for this realm'
            }), 403
    
    # Get IP addresses
    ipv4 = request.args.get('ip') or request.args.get('ipv4')
    ipv6 = request.args.get('ipv6')
    auto = request.args.get('auto', '').lower() in ('true', '1', 'yes')
    
    if auto or (not ipv4 and not ipv6):
        # Auto-detect from request
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if client_ip:
            client_ip = client_ip.split(',')[0].strip()
        
        if ':' in client_ip:
            ipv6 = ipv6 or client_ip
        else:
            ipv4 = ipv4 or client_ip
    
    if not ipv4 and not ipv6:
        return jsonify({
            'error': 'bad_request',
            'message': 'No IP address specified or detected'
        }), 400
    
    try:
        # Get existing records
        existing_data = call_netcup_api("infoDnsRecords", {"domainname": domain})
        existing_records = existing_data.get("dnsrecords", [])
        
        updated = []
        
        # Update A record
        if ipv4 and (not allowed_types or 'A' in allowed_types):
            a_record = None
            for rec in existing_records:
                if rec.get("hostname") == hostname and rec.get("type") == "A":
                    a_record = rec
                    break
            
            if a_record:
                a_record['destination'] = ipv4
            else:
                existing_records.append({
                    "hostname": hostname,
                    "type": "A",
                    "destination": ipv4
                })
            updated.append(f"A -> {ipv4}")
        
        # Update AAAA record
        if ipv6 and (not allowed_types or 'AAAA' in allowed_types):
            aaaa_record = None
            for rec in existing_records:
                if rec.get("hostname") == hostname and rec.get("type") == "AAAA":
                    aaaa_record = rec
                    break
            
            if aaaa_record:
                aaaa_record['destination'] = ipv6
            else:
                existing_records.append({
                    "hostname": hostname,
                    "type": "AAAA",
                    "destination": ipv6
                })
            updated.append(f"AAAA -> {ipv6}")
        
        if not updated:
            return jsonify({
                'error': 'bad_request',
                'message': 'No records to update'
            }), 400
        
        # Update records
        call_netcup_api("updateDnsRecords", {
            "domainname": domain,
            "dnsrecordset": {"dnsrecords": existing_records}
        })
        
        log_activity(token, 'ddns', domain=domain,
                    details=f"{hostname}: {', '.join(updated)}", success=True)
        
        return jsonify({
            'message': 'DDNS update successful',
            'hostname': hostname,
            'domain': domain,
            'updated': updated
        })
        
    except NetcupAPIError as e:
        log_activity(token, 'ddns', domain=domain, success=False, details=str(e))
        return jsonify({'error': 'api_error', 'message': str(e)}), e.status_code


@filter_proxy_bp.route('/api/myip', methods=['GET'])
def my_ip():
    """
    Return the client's IP address.
    
    This endpoint does not require authentication.
    """
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip:
        client_ip = client_ip.split(',')[0].strip()
    
    return jsonify({'ip': client_ip})

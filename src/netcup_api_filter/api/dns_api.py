"""
DNS API Blueprint - Bearer Token Authentication.

Provides DNS record operations with the new token auth system.

Routes:
- GET  /api/dns/<domain>/records - List records
- POST /api/dns/<domain>/records - Create record
- PUT  /api/dns/<domain>/records/<id> - Update record
- DELETE /api/dns/<domain>/records/<id> - Delete record
- GET  /api/myip - Get caller's public IP
"""
import logging
from flask import Blueprint, g, jsonify, request

from ..models import db
from ..token_auth import (
    authenticate_token,
    check_permission,
    extract_bearer_token,
    filter_dns_records,
    log_activity,
    require_auth,
    validate_dns_records_update,
)
from ..database import get_setting

logger = logging.getLogger(__name__)

dns_api_bp = Blueprint('dns_api', __name__, url_prefix='/api')


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


# ============================================================================
# Public Endpoints
# ============================================================================

@dns_api_bp.route('/myip')
def my_ip():
    """Return caller's public IP address."""
    return jsonify({
        'ip': request.remote_addr,
        'headers': {
            'x-forwarded-for': request.headers.get('X-Forwarded-For'),
            'x-real-ip': request.headers.get('X-Real-IP'),
        }
    })


@dns_api_bp.route('/geoip/<ip>')
def geoip_lookup(ip):
    """Look up geolocation for an IP address.
    
    Returns:
        JSON with location data including country, city, coordinates
    """
    try:
        from ..geoip_service import lookup
        
        result = lookup(ip)
        
        if result.error:
            return jsonify({
                'ip': ip,
                'error': result.error
            }), 200  # Still 200 - valid response, just no location data
        
        return jsonify(result.to_dict())
    
    except ImportError:
        logger.warning("geoip_service module not available")
        return jsonify({
            'ip': ip,
            'error': 'GeoIP service not available'
        }), 503
    except Exception as e:
        logger.exception(f"Error in GeoIP lookup for {ip}")
        return jsonify({
            'ip': ip,
            'error': str(e)
        }), 500


# ============================================================================
# DNS Record Operations (Bearer Token Auth)
# ============================================================================

@dns_api_bp.route('/dns/<domain>/records', methods=['GET'])
@require_auth
def list_records(domain):
    """List DNS records for a domain."""
    auth = g.auth
    client_ip = request.remote_addr
    
    # Check permission for read operation
    perm = check_permission(auth, 'read', domain, client_ip=client_ip)
    if not perm.granted:
        log_activity(
            auth=auth,
            action='api_call',
            operation='read',
            domain=domain,
            source_ip=client_ip,
            status='denied',
            status_reason=perm.reason
        )
        return jsonify({'error': 'forbidden', 'message': perm.reason}), 403
    
    # Get Netcup client
    netcup = get_netcup_client()
    if not netcup:
        return jsonify({'error': 'configuration', 'message': 'Netcup API not configured'}), 500
    
    try:
        # Fetch records from Netcup
        result = netcup.info_dns_records(domain)

        # NetcupClient.info_dns_records returns a list of records.
        # Some mocks/legacy clients may return a Netcup-style envelope.
        if isinstance(result, list):
            records = result
        elif isinstance(result, dict):
            status = result.get('status')
            if status and status != 'success':
                log_activity(
                    auth=auth,
                    action='api_call',
                    operation='read',
                    domain=domain,
                    source_ip=client_ip,
                    status='error',
                    status_reason=result.get('message', 'API error'),
                    response_summary={'status': status}
                )
                return jsonify({
                    'error': 'api_error',
                    'message': result.get('message', 'Failed to fetch records')
                }), 502
            records = result.get('responsedata', {}).get('dnsrecords', [])
        else:
            raise TypeError(f"Unexpected Netcup response type: {type(result)}")
        
        # Filter records by allowed types
        filtered = filter_dns_records(auth, domain, records)
        
        log_activity(
            auth=auth,
            action='api_call',
            operation='read',
            domain=domain,
            source_ip=client_ip,
            status='success',
            response_summary={'record_count': len(filtered)}
        )
        
        return jsonify({
            'domain': domain,
            'records': filtered,
            'total': len(filtered)
        })
    
    except Exception as e:
        logger.exception(f"Error fetching DNS records for {domain}")
        log_activity(
            auth=auth,
            action='api_call',
            operation='read',
            domain=domain,
            source_ip=client_ip,
            status='error',
            status_reason=str(e)
        )
        return jsonify({'error': 'internal', 'message': 'Internal server error'}), 500


@dns_api_bp.route('/dns/<domain>/records', methods=['POST'])
@require_auth
def create_record(domain):
    """Create a new DNS record."""
    auth = g.auth
    client_ip = request.remote_addr
    data = request.get_json() or {}
    
    record_type = data.get('type', '').upper()
    hostname = data.get('hostname', '')
    destination = data.get('destination', '')
    priority = data.get('priority')
    
    if not all([record_type, hostname, destination]):
        return jsonify({
            'error': 'validation',
            'message': 'Required fields: type, hostname, destination'
        }), 400
    
    # Check permission
    perm = check_permission(
        auth, 'create', domain,
        record_type=record_type,
        record_name=hostname,
        client_ip=client_ip
    )
    
    if not perm.granted:
        log_activity(
            auth=auth,
            action='api_call',
            operation='create',
            domain=domain,
            record_type=record_type,
            record_name=hostname,
            source_ip=client_ip,
            status='denied',
            status_reason=perm.reason,
            request_data=data
        )
        return jsonify({'error': 'forbidden', 'message': perm.reason}), 403
    
    # Get Netcup client
    netcup = get_netcup_client()
    if not netcup:
        return jsonify({'error': 'configuration', 'message': 'Netcup API not configured'}), 500
    
    try:
        # Build record
        record = {
            'hostname': hostname,
            'type': record_type,
            'destination': destination,
        }
        if priority is not None:
            record['priority'] = priority
        
        # Update DNS records (creates new record)
        result = netcup.update_dns_records(domain, [record])

        status = result.get('status') if isinstance(result, dict) else None
        if status and status != 'success':
            log_activity(
                auth=auth,
                action='api_call',
                operation='create',
                domain=domain,
                record_type=record_type,
                record_name=hostname,
                source_ip=client_ip,
                status='error',
                status_reason=result.get('message', 'API error'),
                request_data=data
            )
            return jsonify({
                'error': 'api_error',
                'message': result.get('message', 'Failed to create record')
            }), 502
        
        log_activity(
            auth=auth,
            action='api_call',
            operation='create',
            domain=domain,
            record_type=record_type,
            record_name=hostname,
            source_ip=client_ip,
            status='success',
            request_data=data,
            response_summary={'status': 'created'}
        )
        
        return jsonify({
            'status': 'created',
            'record': record
        }), 201
    
    except Exception as e:
        logger.exception(f"Error creating DNS record for {domain}")
        log_activity(
            auth=auth,
            action='api_call',
            operation='create',
            domain=domain,
            record_type=record_type,
            record_name=hostname,
            source_ip=client_ip,
            status='error',
            status_reason=str(e),
            request_data=data
        )
        return jsonify({'error': 'internal', 'message': 'Internal server error'}), 500


@dns_api_bp.route('/dns/<domain>/records/<int:record_id>', methods=['PUT'])
@require_auth
def update_record(domain, record_id):
    """Update an existing DNS record."""
    auth = g.auth
    client_ip = request.remote_addr
    data = request.get_json() or {}
    
    record_type = data.get('type', '').upper()
    hostname = data.get('hostname', '')
    destination = data.get('destination', '')
    
    if not all([record_type, hostname, destination]):
        return jsonify({
            'error': 'validation',
            'message': 'Required fields: type, hostname, destination'
        }), 400
    
    # Check permission
    perm = check_permission(
        auth, 'update', domain,
        record_type=record_type,
        record_name=hostname,
        client_ip=client_ip
    )
    
    if not perm.granted:
        log_activity(
            auth=auth,
            action='api_call',
            operation='update',
            domain=domain,
            record_type=record_type,
            record_name=hostname,
            source_ip=client_ip,
            status='denied',
            status_reason=perm.reason,
            request_data=data
        )
        return jsonify({'error': 'forbidden', 'message': perm.reason}), 403
    
    # Get Netcup client
    netcup = get_netcup_client()
    if not netcup:
        return jsonify({'error': 'configuration', 'message': 'Netcup API not configured'}), 500
    
    try:
        # Build record with ID for update
        record = {
            'id': record_id,
            'hostname': hostname,
            'type': record_type,
            'destination': destination,
        }
        if 'priority' in data:
            record['priority'] = data['priority']
        
        result = netcup.update_dns_records(domain, [record])

        status = result.get('status') if isinstance(result, dict) else None
        if status and status != 'success':
            log_activity(
                auth=auth,
                action='api_call',
                operation='update',
                domain=domain,
                record_type=record_type,
                record_name=hostname,
                source_ip=client_ip,
                status='error',
                status_reason=result.get('message', 'API error'),
                request_data=data
            )
            return jsonify({
                'error': 'api_error',
                'message': result.get('message', 'Failed to update record')
            }), 502
        
        log_activity(
            auth=auth,
            action='api_call',
            operation='update',
            domain=domain,
            record_type=record_type,
            record_name=hostname,
            source_ip=client_ip,
            status='success',
            request_data=data,
            response_summary={'status': 'updated', 'record_id': record_id}
        )
        
        return jsonify({
            'status': 'updated',
            'record': record
        })
    
    except Exception as e:
        logger.exception(f"Error updating DNS record for {domain}")
        log_activity(
            auth=auth,
            action='api_call',
            operation='update',
            domain=domain,
            record_type=record_type,
            record_name=hostname,
            source_ip=client_ip,
            status='error',
            status_reason=str(e),
            request_data=data
        )
        return jsonify({'error': 'internal', 'message': 'Internal server error'}), 500


@dns_api_bp.route('/dns/<domain>/records/<int:record_id>', methods=['DELETE'])
@require_auth
def delete_record(domain, record_id):
    """Delete a DNS record."""
    auth = g.auth
    client_ip = request.remote_addr
    
    # We need to fetch the record first to get its type for permission check
    # For now, we'll use a generic check
    perm = check_permission(auth, 'delete', domain, client_ip=client_ip)
    
    if not perm.granted:
        log_activity(
            auth=auth,
            action='api_call',
            operation='delete',
            domain=domain,
            source_ip=client_ip,
            status='denied',
            status_reason=perm.reason
        )
        return jsonify({'error': 'forbidden', 'message': perm.reason}), 403
    
    # Get Netcup client
    netcup = get_netcup_client()
    if not netcup:
        return jsonify({'error': 'configuration', 'message': 'Netcup API not configured'}), 500
    
    try:
        # Delete record by marking deleterecord=True
        record = {
            'id': record_id,
            'deleterecord': True
        }
        
        result = netcup.update_dns_records(domain, [record])

        status = result.get('status') if isinstance(result, dict) else None
        if status and status != 'success':
            log_activity(
                auth=auth,
                action='api_call',
                operation='delete',
                domain=domain,
                source_ip=client_ip,
                status='error',
                status_reason=result.get('message', 'API error')
            )
            return jsonify({
                'error': 'api_error',
                'message': result.get('message', 'Failed to delete record')
            }), 502
        
        log_activity(
            auth=auth,
            action='api_call',
            operation='delete',
            domain=domain,
            source_ip=client_ip,
            status='success',
            response_summary={'status': 'deleted', 'record_id': record_id}
        )
        
        return jsonify({
            'status': 'deleted',
            'record_id': record_id
        })
    
    except Exception as e:
        logger.exception(f"Error deleting DNS record for {domain}")
        log_activity(
            auth=auth,
            action='api_call',
            operation='delete',
            domain=domain,
            source_ip=client_ip,
            status='error',
            status_reason=str(e)
        )
        return jsonify({'error': 'internal', 'message': 'Internal server error'}), 500


# ============================================================================
# DDNS Convenience Endpoint
# ============================================================================

@dns_api_bp.route('/ddns/<domain>/<hostname>', methods=['POST', 'PUT'])
@require_auth
def ddns_update(domain, hostname):
    """
    DDNS-style update endpoint.
    
    Automatically detects caller IP and updates A/AAAA record.
    
    Query params:
    - ip: Optional explicit IP (defaults to caller IP)
    - type: A or AAAA (defaults to A)
    """
    auth = g.auth
    client_ip = request.remote_addr
    
    # Get IP from query or use caller IP
    ip = request.args.get('ip', client_ip)
    record_type = request.args.get('type', 'A').upper()
    
    if record_type not in ('A', 'AAAA'):
        return jsonify({
            'error': 'validation',
            'message': 'Type must be A or AAAA'
        }), 400
    
    # Check permission
    perm = check_permission(
        auth, 'update', domain,
        record_type=record_type,
        record_name=hostname,
        client_ip=client_ip
    )
    
    if not perm.granted:
        log_activity(
            auth=auth,
            action='api_call',
            operation='update',
            domain=domain,
            record_type=record_type,
            record_name=hostname,
            source_ip=client_ip,
            status='denied',
            status_reason=perm.reason
        )
        return jsonify({'error': 'forbidden', 'message': perm.reason}), 403
    
    # Get Netcup client
    netcup = get_netcup_client()
    if not netcup:
        return jsonify({'error': 'configuration', 'message': 'Netcup API not configured'}), 500
    
    try:
        # First, try to find existing record
        info_result = netcup.info_dns_records(domain)

        if isinstance(info_result, list):
            records = info_result
        elif isinstance(info_result, dict):
            status = info_result.get('status')
            if status and status != 'success':
                return jsonify({
                    'error': 'api_error',
                    'message': 'Failed to fetch current records'
                }), 502
            records = info_result.get('responsedata', {}).get('dnsrecords', [])
        else:
            raise TypeError(f"Unexpected Netcup response type: {type(info_result)}")
        
        # Find matching record
        existing = None
        for rec in records:
            if rec.get('hostname') == hostname and rec.get('type') == record_type:
                existing = rec
                break
        
        # Build update record
        if existing:
            record = {
                'id': existing['id'],
                'hostname': hostname,
                'type': record_type,
                'destination': ip
            }
        else:
            # Create new record
            record = {
                'hostname': hostname,
                'type': record_type,
                'destination': ip
            }
        
        result = netcup.update_dns_records(domain, [record])

        status = result.get('status') if isinstance(result, dict) else None
        if status and status != 'success':
            log_activity(
                auth=auth,
                action='api_call',
                operation='update',
                domain=domain,
                record_type=record_type,
                record_name=hostname,
                source_ip=client_ip,
                status='error',
                status_reason=result.get('message', 'API error')
            )
            return jsonify({
                'error': 'api_error',
                'message': result.get('message', 'Failed to update record')
            }), 502
        
        log_activity(
            auth=auth,
            action='api_call',
            operation='update',
            domain=domain,
            record_type=record_type,
            record_name=hostname,
            source_ip=client_ip,
            status='success',
            response_summary={
                'status': 'updated' if existing else 'created',
                'hostname': hostname,
                'type': record_type,
                'destination': ip
            }
        )
        
        return jsonify({
            'status': 'updated' if existing else 'created',
            'hostname': hostname,
            'type': record_type,
            'destination': ip,
            'fqdn': f'{hostname}.{domain}' if hostname != '@' else domain
        })
    
    except Exception as e:
        logger.exception(f"Error in DDNS update for {domain}")
        log_activity(
            auth=auth,
            action='api_call',
            operation='update',
            domain=domain,
            record_type=record_type,
            record_name=hostname,
            source_ip=client_ip,
            status='error',
            status_reason=str(e)
        )
        return jsonify({'error': 'internal', 'message': 'Internal server error'}), 500

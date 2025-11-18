"""
Netcup API Filter Proxy
A filtering proxy for the Netcup DNS API that provides granular access control
"""
import logging
import re
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import yaml
from typing import Dict, Any
from werkzeug.middleware.proxy_fix import ProxyFix

from netcup_client import NetcupClient, NetcupAPIError
from access_control import AccessControl
from client_portal import client_portal_bp
from utils import get_build_info

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.register_blueprint(client_portal_bp)


@app.context_processor
def inject_build_metadata():
    """Expose build metadata to every Jinja template."""
    return {'build_info': get_build_info()}

# Security: Set maximum content length (10MB)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

# Security: Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"],
    storage_uri="memory://",
)

# Global configuration
config: Dict[str, Any] = {}
netcup_client: NetcupClient = None
access_control: AccessControl = None

# Domain name validation regex (RFC 1035)
DOMAIN_REGEX = re.compile(
    r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$'
)

# DNS hostname validation regex (simplified to avoid ReDoS)
# Allows alphanumeric, dash, underscore, asterisk, and dots
# Max length checked separately
HOSTNAME_REGEX = re.compile(
    r'^[a-zA-Z0-9_\*\-\.]+$'
)


def load_config(config_path: str = "config.yaml"):
    """Load configuration from YAML file"""
    global config, netcup_client, access_control
    
    try:
        # Security: Limit config file size to 1MB
        import os
        file_size = os.path.getsize(config_path)
        if file_size > 1024 * 1024:  # 1MB
            logger.error(f"Configuration file too large: {file_size} bytes")
            return False
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Validate config structure
        if not isinstance(config, dict):
            logger.error("Invalid configuration: root must be a dictionary")
            return False
        
        # Initialize Netcup client
        netcup_config = config.get("netcup", {})
        netcup_client = NetcupClient(
            customer_id=netcup_config.get("customer_id"),
            api_key=netcup_config.get("api_key"),
            api_password=netcup_config.get("api_password"),
            api_url=netcup_config.get("api_url", "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON")
        )
        app.config['netcup_client'] = netcup_client
        
        # Initialize access control
        tokens_config = config.get("tokens", [])
        if not isinstance(tokens_config, list):
            logger.error("Invalid configuration: tokens must be a list")
            return False
            
        access_control = AccessControl(tokens_config)
        app.config['access_control'] = access_control
        
        logger.info(f"Configuration loaded successfully. {len(tokens_config)} tokens configured.")
        return True
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return False


def get_token_from_request() -> str:
    """Extract authentication token from request"""
    # Check Authorization header (preferred method)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    
    # Check X-API-Token header (alternative)
    token = request.headers.get("X-API-Token", "")
    if token:
        return token
    
    # Security: Deprecated - token in query param (insecure, logged in access logs)
    # Only use as fallback for backward compatibility
    # Consider removing this in production
    token = request.args.get("token", "")
    if token:
        logger.warning("Token passed in query parameter (insecure). Use Authorization header instead.")
        return token
    
    return ""


def validate_domain_name(domain: str) -> bool:
    """
    Validate domain name against DNS specification
    
    Args:
        domain: Domain name to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not domain or len(domain) > 253:
        return False
    return bool(DOMAIN_REGEX.match(domain))


def validate_hostname(hostname: str) -> bool:
    """
    Validate DNS hostname (supports wildcards for patterns)
    
    Args:
        hostname: Hostname to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not hostname or len(hostname) > 253:
        return False
    return bool(HOSTNAME_REGEX.match(hostname))


@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'  # Allow admin UI to load in same origin
    # Prevent MIME sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Enable XSS protection
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Content Security Policy - Allow UI resources for admin + client portals
    # Allow self for scripts/styles plus Bootstrap/jQuery CDNs
    if request.path.startswith('/admin') or request.path.startswith('/client'):
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://code.jquery.com https://stackpath.bootstrapcdn.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://stackpath.bootstrapcdn.com; "
            "img-src 'self' data:; "
            "font-src 'self' https://stackpath.bootstrapcdn.com; "
            "connect-src 'self'"
        )
    else:
        response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
    # Referrer policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Remove server header
    response.headers.pop('Server', None)
    # Strict Transport Security (HSTS) - force HTTPS
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


@app.route("/", methods=["GET"])
@limiter.exempt
def index():
    """Health check endpoint"""
    return jsonify({
        "service": "Netcup API Filter Proxy",
        "status": "running",
        "version": "1.0.0"
    })


@app.route("/api", methods=["POST"])
@limiter.limit("10 per minute")  # Stricter limit for API endpoint
def api_proxy():
    """Main API proxy endpoint"""
    # Security: Validate Content-Type
    content_type = request.headers.get('Content-Type', '')
    if not content_type.startswith('application/json'):
        return jsonify({
            "status": "error",
            "message": "Content-Type must be application/json"
        }), 400
    
    # Get authentication token
    token = get_token_from_request()
    if not token:
        return jsonify({
            "status": "error",
            "message": "Authentication token required"
        }), 401
    
    # Security: Validate token format (should be hex string)
    if not re.match(r'^[a-fA-F0-9]{32,128}$', token):
        logger.warning(f"Invalid token format attempted from {request.remote_addr}")
        send_admin_alert("AUTHENTICATION_FAILURE", "Invalid token format")
        return jsonify({
            "status": "error",
            "message": "Invalid authentication token"
        }), 401
    
    if not access_control.validate_token(token):
        logger.warning(f"Invalid token attempted from {request.remote_addr}")
        send_admin_alert("AUTHENTICATION_FAILURE", "Invalid token")
        return jsonify({
            "status": "error",
            "message": "Invalid authentication token"
        }), 401
    
    # Check origin restrictions (IP/domain whitelist)
    client_ip = request.remote_addr
    origin_host = request.headers.get("Host", "")
    if not access_control.check_origin(token, client_ip, origin_host):
        logger.warning(f"Access denied for token from origin: {client_ip} / {origin_host}")
        send_admin_alert("ORIGIN_VIOLATION", f"Access from {client_ip} / {origin_host}")
        return jsonify({
            "status": "error",
            "message": "Access denied: origin not allowed"
        }), 403
    
    # Parse request
    try:
        data = request.get_json(force=False, silent=False)
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object")
        
        action = data.get("action")
        param = data.get("param", {})
        
        if not isinstance(param, dict):
            raise ValueError("param must be a JSON object")
            
    except Exception as e:
        logger.error(f"Invalid request format from {request.remote_addr}: {e}")
        return jsonify({
            "status": "error",
            "message": "Invalid request format"
        }), 400
    
    # Handle different actions
    try:
        if action == "infoDnsZone":
            return handle_info_dns_zone(token, param)
        elif action == "infoDnsRecords":
            return handle_info_dns_records(token, param)
        elif action == "updateDnsRecords":
            return handle_update_dns_records(token, param)
        else:
            return jsonify({
                "status": "error",
                "message": f"Unsupported action: {action}"
            }), 400
    except NetcupAPIError as e:
        logger.error(f"Netcup API error: {e}")
        return jsonify({
            "status": "error",
            "message": "API request failed"
        }), 500
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({
            "status": "error",
            "message": "Internal server error"
        }), 500


def handle_info_dns_zone(token: str, param: Dict[str, Any]):
    """Handle infoDnsZone action"""
    domain = param.get("domainname", "")
    if not domain:
        return jsonify({
            "status": "error",
            "message": "domainname parameter required"
        }), 400
    
    # Security: Validate domain name
    if not validate_domain_name(domain):
        logger.warning(f"Invalid domain name: {domain}")
        log_request(token, "infoDnsZone", domain, False, "Invalid domain name")
        return jsonify({
            "status": "error",
            "message": "Invalid domain name"
        }), 400
    
    # Check permission
    if not access_control.check_permission(token, "read", domain):
        log_request(token, "infoDnsZone", domain, False, "Permission denied")
        send_admin_alert("PERMISSION_DENIED", f"infoDnsZone on {domain}")
        return jsonify({
            "status": "error",
            "message": "Permission denied"
        }), 403
    
    try:
        # Forward to Netcup API
        zone_info = netcup_client.info_dns_zone(domain)
        
        # Log successful request
        log_request(token, "infoDnsZone", domain, True, 
                   request_data={"action": "infoDnsZone", "param": param},
                   response_data={"status": "success", "responsedata": zone_info})
        
        return jsonify({
            "status": "success",
            "responsedata": zone_info
        })
    except Exception as e:
        log_request(token, "infoDnsZone", domain, False, str(e))
        raise


def handle_info_dns_records(token: str, param: Dict[str, Any]):
    """Handle infoDnsRecords action"""
    domain = param.get("domainname", "")
    if not domain:
        return jsonify({
            "status": "error",
            "message": "domainname parameter required"
        }), 400
    
    # Security: Validate domain name
    if not validate_domain_name(domain):
        logger.warning(f"Invalid domain name: {domain}")
        log_request(token, "infoDnsRecords", domain, False, "Invalid domain name")
        return jsonify({
            "status": "error",
            "message": "Invalid domain name"
        }), 400
    
    # Check permission
    if not access_control.check_permission(token, "read", domain):
        log_request(token, "infoDnsRecords", domain, False, "Permission denied")
        send_admin_alert("PERMISSION_DENIED", f"infoDnsRecords on {domain}")
        return jsonify({
            "status": "error",
            "message": "Permission denied"
        }), 403
    
    try:
        # Get records from Netcup API
        all_records = netcup_client.info_dns_records(domain)
        
        # Filter records based on token permissions
        filtered_records = access_control.filter_dns_records(token, domain, all_records)
        
        # Log successful request
        log_request(token, "infoDnsRecords", domain, True,
                   record_details={"total_records": len(all_records), "filtered_records": len(filtered_records)},
                   request_data={"action": "infoDnsRecords", "param": param},
                   response_data={"status": "success", "responsedata": {"dnsrecords": filtered_records}})
        
        return jsonify({
            "status": "success",
            "responsedata": {
                "dnsrecords": filtered_records
            }
        })
    except Exception as e:
        log_request(token, "infoDnsRecords", domain, False, str(e))
        raise


def handle_update_dns_records(token: str, param: Dict[str, Any]):
    """Handle updateDnsRecords action"""
    domain = param.get("domainname", "")
    if not domain:
        return jsonify({
            "status": "error",
            "message": "domainname parameter required"
        }), 400
    
    # Security: Validate domain name
    if not validate_domain_name(domain):
        logger.warning(f"Invalid domain name: {domain}")
        log_request(token, "updateDnsRecords", domain, False, "Invalid domain name")
        return jsonify({
            "status": "error",
            "message": "Invalid domain name"
        }), 400
    
    dns_record_set = param.get("dnsrecordset", {})
    if not isinstance(dns_record_set, dict):
        return jsonify({
            "status": "error",
            "message": "dnsrecordset must be an object"
        }), 400
    
    dns_records = dns_record_set.get("dnsrecords", [])
    
    if not dns_records:
        return jsonify({
            "status": "error",
            "message": "dnsrecords required"
        }), 400
    
    if not isinstance(dns_records, list):
        return jsonify({
            "status": "error",
            "message": "dnsrecords must be an array"
        }), 400
    
    # Security: Limit number of records per request
    if len(dns_records) > 100:
        log_request(token, "updateDnsRecords", domain, False, "Too many records")
        return jsonify({
            "status": "error",
            "message": "Too many records (maximum 100 per request)"
        }), 400
    
    # Security: Validate each record's hostname
    for record in dns_records:
        if not isinstance(record, dict):
            return jsonify({
                "status": "error",
                "message": "Each DNS record must be an object"
            }), 400
        
        hostname = record.get("hostname", "")
        if hostname and not validate_hostname(hostname):
            logger.warning(f"Invalid hostname in DNS record: {hostname}")
            log_request(token, "updateDnsRecords", domain, False, f"Invalid hostname: {hostname}")
            return jsonify({
                "status": "error",
                "message": f"Invalid hostname: {hostname}"
            }), 400
    
    # Validate permissions for all records
    is_valid, error_msg = access_control.validate_dns_records_update(token, domain, dns_records)
    if not is_valid:
        log_request(token, "updateDnsRecords", domain, False, error_msg,
                   record_details={"records_count": len(dns_records)})
        send_admin_alert("PERMISSION_DENIED", f"updateDnsRecords on {domain}: {error_msg}")
        return jsonify({
            "status": "error",
            "message": error_msg
        }), 403
    
    try:
        # Forward to Netcup API
        result = netcup_client.update_dns_records(domain, dns_records)
        
        # Log successful request
        log_request(token, "updateDnsRecords", domain, True,
                   record_details={"records_count": len(dns_records), "records": dns_records},
                   request_data={"action": "updateDnsRecords", "param": param},
                   response_data={"status": "success", "responsedata": result})
        
        return jsonify({
            "status": "success",
            "responsedata": result
        })
    except Exception as e:
        log_request(token, "updateDnsRecords", domain, False, str(e))
        raise


def log_request(token: str, action: str, domain: str, success: bool, 
                error_message: str = None, record_details: Dict[str, Any] = None,
                request_data: Dict[str, Any] = None, response_data: Dict[str, Any] = None):
    """
    Log request to audit logger and send email notifications if configured
    
    Args:
        token: Authentication token
        action: Action performed
        domain: Domain accessed
        success: Whether the request succeeded
        error_message: Optional error message
        record_details: Optional record details
        request_data: Optional request data
        response_data: Optional response data
    """
    # Get audit logger if available
    audit_logger = app.config.get('audit_logger')
    if audit_logger:
        # Get client info
        token_info = None
        client_id = None
        
        if access_control:
            token_info = access_control.get_token_info(token)
            if token_info:
                client_id = token_info.get('client_id', token_info.get('description', 'unknown'))
        
        # Log the access
        audit_logger.log_access(
            client_id=client_id,
            ip_address=request.remote_addr,
            operation=action,
            domain=domain,
            record_details=record_details,
            success=success,
            error_message=error_message,
            request_data=request_data,
            response_data=response_data
        )
        
        # Send email notification if enabled for this client
        if token_info and token_info.get('email_notifications_enabled'):
            email_address = token_info.get('email_address')
            if email_address:
                from datetime import datetime
                from email_notifier import get_email_notifier_from_config
                from database import get_system_config
                
                email_config = get_system_config('email_config')
                if email_config:
                    notifier = get_email_notifier_from_config(email_config)
                    if notifier:
                        notifier.send_client_notification(
                            client_id=client_id,
                            to_email=email_address,
                            timestamp=datetime.utcnow(),
                            operation=action,
                            ip_address=request.remote_addr,
                            success=success,
                            domain=domain,
                            record_details=record_details,
                            error_message=error_message
                        )


def send_admin_alert(event_type: str, details: str):
    """
    Send admin alert for security events
    
    Args:
        event_type: Type of security event
        details: Event details
    """
    # Log security event
    audit_logger = app.config.get('audit_logger')
    if audit_logger:
        audit_logger.log_security_event(
            event_type=event_type,
            details=details,
            ip_address=request.remote_addr
        )
    
    # Send admin email if configured
    try:
        from datetime import datetime
        from email_notifier import get_email_notifier_from_config
        from database import get_system_config
        
        email_config = get_system_config('email_config')
        admin_email_config = get_system_config('admin_email_config')
        
        if email_config and admin_email_config:
            admin_email = admin_email_config.get('admin_email')
            if admin_email:
                notifier = get_email_notifier_from_config(email_config)
                if notifier:
                    notifier.send_admin_notification(
                        admin_email=admin_email,
                        event_type=event_type,
                        details=details,
                        ip_address=request.remote_addr,
                        timestamp=datetime.utcnow()
                    )
    except Exception as e:
        logger.error(f"Failed to send admin alert: {e}")


def main():
    """Main entry point"""
    import sys
    
    config_file = "config.yaml"
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    
    if not load_config(config_file):
        logger.error("Failed to load configuration. Exiting.")
        sys.exit(1)
    
    server_config = config.get("server", {})
    host = server_config.get("host", "0.0.0.0")
    port = server_config.get("port", 5000)
    debug = server_config.get("debug", False)
    
    logger.info(f"Starting Netcup API Filter Proxy on {host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()

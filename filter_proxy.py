"""
Netcup API Filter Proxy
A filtering proxy for the Netcup DNS API that provides granular access control
"""
import logging
from flask import Flask, request, jsonify
import yaml
from typing import Dict, Any

from netcup_client import NetcupClient, NetcupAPIError
from access_control import AccessControl

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global configuration
config: Dict[str, Any] = {}
netcup_client: NetcupClient = None
access_control: AccessControl = None


def load_config(config_path: str = "config.yaml"):
    """Load configuration from YAML file"""
    global config, netcup_client, access_control
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Initialize Netcup client
        netcup_config = config.get("netcup", {})
        netcup_client = NetcupClient(
            customer_id=netcup_config.get("customer_id"),
            api_key=netcup_config.get("api_key"),
            api_password=netcup_config.get("api_password"),
            api_url=netcup_config.get("api_url", "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON")
        )
        
        # Initialize access control
        tokens_config = config.get("tokens", [])
        access_control = AccessControl(tokens_config)
        
        logger.info(f"Configuration loaded successfully. {len(tokens_config)} tokens configured.")
        return True
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return False


def get_token_from_request() -> str:
    """Extract authentication token from request"""
    # Check Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    
    # Check X-API-Token header
    token = request.headers.get("X-API-Token", "")
    if token:
        return token
    
    # Check query parameter
    token = request.args.get("token", "")
    if token:
        return token
    
    return ""


@app.route("/", methods=["GET"])
def index():
    """Health check endpoint"""
    return jsonify({
        "service": "Netcup API Filter Proxy",
        "status": "running",
        "version": "1.0.0"
    })


@app.route("/api", methods=["POST"])
def api_proxy():
    """Main API proxy endpoint"""
    # Get authentication token
    token = get_token_from_request()
    if not token:
        return jsonify({
            "status": "error",
            "message": "Authentication token required"
        }), 401
    
    if not access_control.validate_token(token):
        return jsonify({
            "status": "error",
            "message": "Invalid authentication token"
        }), 401
    
    # Parse request
    try:
        data = request.get_json()
        action = data.get("action")
        param = data.get("param", {})
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Invalid request format: {e}"
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
            "message": str(e)
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
    
    # Check permission
    if not access_control.check_permission(token, "read", domain):
        return jsonify({
            "status": "error",
            "message": "Permission denied"
        }), 403
    
    # Forward to Netcup API
    zone_info = netcup_client.info_dns_zone(domain)
    
    return jsonify({
        "status": "success",
        "responsedata": zone_info
    })


def handle_info_dns_records(token: str, param: Dict[str, Any]):
    """Handle infoDnsRecords action"""
    domain = param.get("domainname", "")
    if not domain:
        return jsonify({
            "status": "error",
            "message": "domainname parameter required"
        }), 400
    
    # Check permission
    if not access_control.check_permission(token, "read", domain):
        return jsonify({
            "status": "error",
            "message": "Permission denied"
        }), 403
    
    # Get records from Netcup API
    all_records = netcup_client.info_dns_records(domain)
    
    # Filter records based on token permissions
    filtered_records = access_control.filter_dns_records(token, domain, all_records)
    
    return jsonify({
        "status": "success",
        "responsedata": {
            "dnsrecords": filtered_records
        }
    })


def handle_update_dns_records(token: str, param: Dict[str, Any]):
    """Handle updateDnsRecords action"""
    domain = param.get("domainname", "")
    if not domain:
        return jsonify({
            "status": "error",
            "message": "domainname parameter required"
        }), 400
    
    dns_record_set = param.get("dnsrecordset", {})
    dns_records = dns_record_set.get("dnsrecords", [])
    
    if not dns_records:
        return jsonify({
            "status": "error",
            "message": "dnsrecords required"
        }), 400
    
    # Validate permissions for all records
    is_valid, error_msg = access_control.validate_dns_records_update(token, domain, dns_records)
    if not is_valid:
        return jsonify({
            "status": "error",
            "message": error_msg
        }), 403
    
    # Forward to Netcup API
    result = netcup_client.update_dns_records(domain, dns_records)
    
    return jsonify({
        "status": "success",
        "responsedata": result
    })


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

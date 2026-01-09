"""
WSGI Application Entry Point for Phusion Passenger
Account → Realms → Tokens with Bearer token authentication
"""
import sys
import os
import logging
from datetime import datetime
from pathlib import Path

# Determine important paths
# This file is copied to deployment root, so __file__ is at app_root/passenger_wsgi.py
app_root = Path(__file__).resolve().parent
src_root = app_root / "src"

# Add src root to Python path for the netcup_api_filter package
sys.path.insert(0, str(src_root))

# Support for vendored dependencies (for FTP-only deployment)
vendor_dir = os.path.join(app_root, 'vendor')
if os.path.isdir(vendor_dir):
    sys.path.insert(0, vendor_dir)

# Configure logging
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()

try:
    log_file_path = os.path.join(app_root, 'netcup_filter.log')
    file_handler = logging.FileHandler(log_file_path, mode='a')
    file_handler.setLevel(getattr(logging, LOG_LEVEL))
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(getattr(logging, LOG_LEVEL))
    stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized to {log_file_path} at level {LOG_LEVEL}")
except Exception as e:
    logging.basicConfig(level=getattr(logging, LOG_LEVEL))
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to setup file logging: {e}")

# Auto-detect database location if not explicitly set
if 'NETCUP_FILTER_DB_PATH' not in os.environ:
    db_path = os.path.join(app_root, 'netcup_filter.db')
    os.environ['NETCUP_FILTER_DB_PATH'] = db_path
    logger.info(f"Using database at: {db_path}")

# Load SECRET_KEY from .env.webhosting if present (for webhosting deployments)
# This file is created by deployment script and contains production secrets
webhosting_env = os.path.join(app_root, '.env.webhosting')
if os.path.exists(webhosting_env):
    logger.info(f"Loading webhosting environment from: {webhosting_env}")
    with open(webhosting_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if key.strip() not in os.environ:
                    os.environ[key.strip()] = value.strip()

# Ensure SECRET_KEY is available (persists across deployments)
# Priority: 1. Environment variable, 2. Database (loaded after app creation)
# Note: Database approach is deferred until after create_app() ensures tables exist
if 'SECRET_KEY' not in os.environ:
    # Generate temporary key for initial app creation
    # Will be replaced with database-persisted key after app is ready
    import secrets
    os.environ['SECRET_KEY'] = secrets.token_hex(32)
    logger.info("Using temporary SECRET_KEY (will attempt to load/persist from database after app initialization)")

try:
    from netcup_api_filter.app import create_app
    from netcup_api_filter.filter_proxy import filter_proxy_bp
    
    logger.info("Starting Netcup API Filter with Passenger...")
    logger.info(f"Application directory: {app_root}")
    
    if os.path.isdir(vendor_dir):
        logger.info(f"Using vendored dependencies from: {vendor_dir}")
    else:
        logger.info("Using system-installed dependencies")
    
    # Create application
    app = create_app()
    
    # Register filter proxy blueprint (additional to blueprints from app)
    app.register_blueprint(filter_proxy_bp)
    
    # Initialize Netcup API client and load/persist SECRET_KEY
    with app.app_context():
        from netcup_api_filter.database import db, get_setting, set_setting
        from netcup_api_filter.models import Settings
        
        # Load app-config.toml if present (first-run customization)
        # This file is read once and then deleted
        config_path = os.path.join(app_root, 'app-config.toml')
        if os.path.exists(config_path):
            try:
                logger.info(f"Found app-config.toml at {config_path}, loading initial configuration...")
                
                # Try tomllib first (Python 3.11+), fallback to tomli
                try:
                    import tomllib
                    toml_parser = tomllib
                    logger.info("Using tomllib (Python 3.11+) for TOML parsing")
                except ImportError:
                    import tomli
                    toml_parser = tomli
                    logger.info("Using tomli for TOML parsing")
                
                with open(config_path, 'rb') as f:
                    config = toml_parser.load(f)
                
                logger.info(f"Parsed app-config.toml sections: {list(config.keys())}")
                
                # Apply rate limits
                if 'rate_limits' in config:
                    logger.info(f"Processing rate_limits section with {len(config['rate_limits'])} entries")
                    for key, value in config['rate_limits'].items():
                        setting_key = f"{key}_rate_limit"
                        set_setting(setting_key, value)
                        logger.info(f"  ✓ Set {setting_key} = '{value}'")
                else:
                    logger.info("No [rate_limits] section found in app-config.toml")
                
                # Apply security settings
                if 'security' in config:
                    logger.info(f"Processing security section with {len(config['security'])} entries")
                    for key, value in config['security'].items():
                        set_setting(key, str(value))
                        logger.info(f"  ✓ Set {key} = '{value}'")
                else:
                    logger.info("No [security] section found in app-config.toml")
                
                # Apply SMTP/email config using TOML field names directly
                if 'smtp' in config or 'email' in config:  # Support both [smtp] (new) and [email] (legacy)
                    import json
                    smtp_config = config.get('smtp') or config.get('email')
                    logger.info(f"Processing smtp section with {len(smtp_config)} entries")
                    logger.info(f"  SMTP config keys: {list(smtp_config.keys())}")
                    
                    # Use TOML field names directly (no mapping)
                    smtp_data = {
                        'smtp_host': smtp_config.get('smtp_host', ''),
                        'smtp_port': smtp_config.get('smtp_port', 465),
                        'smtp_security': smtp_config.get('smtp_security', 'ssl'),
                        'use_ssl': smtp_config.get('smtp_security', 'ssl') == 'ssl',
                        'smtp_username': smtp_config.get('smtp_username', ''),
                        'smtp_password': smtp_config.get('smtp_password', ''),
                        'from_email': smtp_config.get('from_email', ''),
                        'from_name': smtp_config.get('from_name', 'Netcup API Filter'),
                        'reply_to': smtp_config.get('reply_to', ''),
                        'admin_email': smtp_config.get('admin_email', ''),
                        'notify_new_account': smtp_config.get('notify_new_account', False),
                        'notify_realm_request': smtp_config.get('notify_realm_request', False),
                        'notify_security': smtp_config.get('notify_security', False),
                    }
                    
                    set_setting('smtp_config', json.dumps(smtp_data))
                    logger.info(f"  ✓ Set smtp_config (TOML field names)")
                    logger.info(f"    - smtp_host: {smtp_data['smtp_host']}")
                    logger.info(f"    - smtp_port: {smtp_data['smtp_port']}")
                    logger.info(f"    - smtp_security: {smtp_data['smtp_security']}")
                    logger.info(f"    - from_email: {smtp_data['from_email']}")
                else:
                    logger.info("No [smtp] or [email] section found in app-config.toml")
                
                # Apply Netcup API config (DEPRECATED - use [[backends]] arrays)
                # Legacy [netcup] section support - store as single JSON object
                if 'netcup' in config:
                    import json
                    netcup = config['netcup']
                    logger.warning("[netcup] section is deprecated - use [[backends]] arrays instead")
                    logger.info(f"Processing legacy [netcup] section with {len(netcup)} entries")
                    
                    # Admin UI expects single 'netcup_config' JSON object
                    netcup_config = {
                        'customer_id': netcup.get('customer_id', ''),
                        'api_key': netcup.get('api_key', ''),
                        'api_password': netcup.get('api_password', ''),
                        'api_url': netcup.get('api_url', 'https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON'),
                        'timeout': netcup.get('timeout', 30),
                    }
                    
                    set_setting('netcup_config', json.dumps(netcup_config))
                    logger.info(f"  ✓ Set netcup_config as JSON object")
                    logger.info(f"    - customer_id: {netcup_config['customer_id']}")
                    logger.info(f"    - api_key: {netcup_config['api_key'][:8]}... (truncated)")
                    logger.info(f"    - api_password: {'***' if netcup_config['api_password'] else '(empty)'}")
                    logger.info(f"    - api_url: {netcup_config['api_url']}")
                    logger.info(f"    - timeout: {netcup_config['timeout']}s")
                else:
                    logger.info("No legacy [netcup] section found (use [[backends]] arrays)")
                
                # Process [[backends]] arrays (NEW PREFERRED STRUCTURE)
                if 'backends' in config:
                    import json
                    backends = config['backends']
                    logger.info(f"Processing [[backends]] arrays: {len(backends)} backend(s) defined")
                    
                    # Store backends config as JSON array for bootstrap processing
                    backends_data = []
                    for idx, backend in enumerate(backends, 1):
                        service_name = backend.get('service_name', f'backend-{idx}')
                        provider = backend.get('provider', '')
                        owner = backend.get('owner', 'platform')
                        display_name = backend.get('display_name', service_name)
                        config_dict = backend.get('config', {})
                        
                        backends_data.append({
                            'service_name': service_name,
                            'provider': provider,
                            'owner': owner,
                            'display_name': display_name,
                            'config': config_dict,
                        })
                        
                        logger.info(f"  [{idx}] {service_name}")
                        logger.info(f"      - provider: {provider}")
                        logger.info(f"      - owner: {owner}")
                        logger.info(f"      - display_name: {display_name}")
                        logger.info(f"      - config keys: {list(config_dict.keys())}")
                    
                    set_setting('backends_config', json.dumps(backends_data))
                    logger.info(f"  ✓ Set backends_config ({len(backends_data)} backend(s))")
                else:
                    logger.info("No [[backends]] arrays found in app-config.toml")
                
                # Process [[domain_roots]] arrays (NEW PREFERRED STRUCTURE)
                if 'domain_roots' in config:
                    import json
                    domain_roots = config['domain_roots']
                    logger.info(f"Processing [[domain_roots]] arrays: {len(domain_roots)} domain(s) defined")
                    
                    # Store domain roots config as JSON array for bootstrap processing
                    domain_roots_data = []
                    for idx, domain_root in enumerate(domain_roots, 1):
                        backend = domain_root.get('backend', '')
                        domain = domain_root.get('domain', '')
                        dns_zone = domain_root.get('dns_zone', domain)
                        visibility = domain_root.get('visibility', 'private')
                        display_name = domain_root.get('display_name', domain)
                        description = domain_root.get('description', '')
                        allow_apex_access = domain_root.get('allow_apex_access', False)
                        min_subdomain_depth = domain_root.get('min_subdomain_depth', 1)
                        max_subdomain_depth = domain_root.get('max_subdomain_depth', 3)
                        allowed_record_types = domain_root.get('allowed_record_types')
                        allowed_operations = domain_root.get('allowed_operations')
                        max_hosts_per_user = domain_root.get('max_hosts_per_user')
                        require_email_verification = domain_root.get('require_email_verification', False)
                        
                        domain_roots_data.append({
                            'backend': backend,
                            'domain': domain,
                            'dns_zone': dns_zone,
                            'visibility': visibility,
                            'display_name': display_name,
                            'description': description,
                            'allow_apex_access': allow_apex_access,
                            'min_subdomain_depth': min_subdomain_depth,
                            'max_subdomain_depth': max_subdomain_depth,
                            'allowed_record_types': allowed_record_types,
                            'allowed_operations': allowed_operations,
                            'max_hosts_per_user': max_hosts_per_user,
                            'require_email_verification': require_email_verification,
                        })
                        
                        logger.info(f"  [{idx}] {domain} (backend: {backend})")
                        logger.info(f"      - dns_zone: {dns_zone}")
                        logger.info(f"      - visibility: {visibility}")
                        logger.info(f"      - display_name: {display_name}")
                        logger.info(f"      - max_hosts_per_user: {max_hosts_per_user}")
                    
                    set_setting('domain_roots_config', json.dumps(domain_roots_data))
                    logger.info(f"  ✓ Set domain_roots_config ({len(domain_roots_data)} domain(s))")
                else:
                    logger.info("No [[domain_roots]] arrays found in app-config.toml")
                
                # Process [[users]] arrays (OPTIONAL USER PRESEEDING)
                if 'users' in config:
                    import json
                    users = config['users']
                    logger.info(f"Processing [[users]] arrays: {len(users)} user(s) to preseed")
                    
                    # Store users config as JSON array for bootstrap processing
                    users_data = []
                    for idx, user in enumerate(users, 1):
                        username = user.get('username', '')
                        email = user.get('email', '')
                        password = user.get('password', 'generate')  # Special value "generate"
                        is_approved = user.get('is_approved', True)
                        must_change_password = user.get('must_change_password', False)
                        
                        users_data.append({
                            'username': username,
                            'email': email,
                            'password': password,
                            'is_approved': is_approved,
                            'must_change_password': must_change_password,
                        })
                        
                        logger.info(f"  [{idx}] {username} ({email})")
                        logger.info(f"      - password: {'<generated>' if password == 'generate' else '<explicit>'}")
                        logger.info(f"      - is_approved: {is_approved}")
                        logger.info(f"      - must_change_password: {must_change_password}")
                    
                    set_setting('users_config', json.dumps(users_data))
                    logger.info(f"  ✓ Set users_config ({len(users_data)} user(s))")
                else:
                    logger.info("No [[users]] arrays found in app-config.toml")
                
                # Apply GeoIP config using TOML field names directly (stored as JSON)
                if 'geoip' in config:
                    import json
                    geoip = config['geoip']
                    logger.info(f"Processing geoip section with {len(geoip)} entries")
                    
                    geoip_data = {
                        'account_id': geoip.get('account_id', ''),
                        'license_key': geoip.get('license_key', ''),
                        'api_url': geoip.get('api_url', 'https://geoip.maxmind.com'),
                        'edition_ids': geoip.get('edition_ids', 'GeoLite2-ASN GeoLite2-City GeoLite2-Country'),
                    }
                    
                    set_setting('geoip_config', json.dumps(geoip_data))
                    logger.info(f"  ✓ Set geoip_config (TOML field names)")
                    logger.info(f"    - account_id: {geoip_data['account_id']}")
                    logger.info(f"    - license_key: ***")
                    logger.info(f"    - api_url: {geoip_data['api_url']}")
                    logger.info(f"    - edition_ids: {geoip_data['edition_ids']}")
                else:
                    logger.info("No [geoip] section found in app-config.toml")
                
                # Apply Free Domains config
                if 'free_domains' in config:
                    import json
                    free_domains = config['free_domains']
                    logger.info(f"Processing free_domains section with {len(free_domains)} entries")
                    
                    free_domains_data = {
                        'enabled': free_domains.get('enabled', False),
                        'domains': free_domains.get('domains', []),
                        'max_hosts_per_user': free_domains.get('max_hosts_per_user', 5),
                        'require_email_verification': free_domains.get('require_email_verification', True),
                    }
                    
                    set_setting('free_domains_config', json.dumps(free_domains_data))
                    logger.info(f"  ✓ Set free_domains_config")
                    logger.info(f"    - enabled: {free_domains_data['enabled']}")
                    logger.info(f"    - domains: {free_domains_data['domains']}")
                    logger.info(f"    - max_hosts_per_user: {free_domains_data['max_hosts_per_user']}")
                else:
                    logger.info("No [free_domains] section found in app-config.toml")
                
                # Apply Platform Backends config
                if 'platform_backends' in config:
                    import json
                    platform_backends = config['platform_backends']
                    logger.info(f"Processing platform_backends section with {len(platform_backends)} entries")
                    
                    platform_backends_data = {
                        'powerdns_enabled': platform_backends.get('powerdns_enabled', False),
                        'powerdns_api_url': platform_backends.get('powerdns_api_url', ''),
                        'netcup_platform_backend': platform_backends.get('netcup_platform_backend', False),
                    }
                    
                    set_setting('platform_backends_config', json.dumps(platform_backends_data))
                    logger.info(f"  ✓ Set platform_backends_config")
                    logger.info(f"    - powerdns_enabled: {platform_backends_data['powerdns_enabled']}")
                    logger.info(f"    - powerdns_api_url: {platform_backends_data['powerdns_api_url'] or 'auto-detect'}")
                    logger.info(f"    - netcup_platform_backend: {platform_backends_data['netcup_platform_backend']}")
                else:
                    logger.info("No [platform_backends] section found in app-config.toml")
                
                db.session.commit()
                logger.info("✓ All settings committed to database")
                
                # Initialize platform backends and free domains
                try:
                    from netcup_api_filter.bootstrap.platform_backends import initialize_platform_backends
                    initialize_platform_backends()
                    logger.info("✓ Platform backends initialized")
                except Exception as e:
                    logger.error(f"Failed to initialize platform backends: {e}", exc_info=True)
                
                # Delete the config file after successful import
                os.remove(config_path)
                logger.info(f"✓ app-config.toml imported and deleted successfully")
                
            except ImportError as e:
                logger.warning(f"tomllib/tomli not available: {e}, cannot load app-config.toml")
            except Exception as e:
                logger.error(f"Failed to load app-config.toml: {e}", exc_info=True)
        
        # Load/persist SECRET_KEY from database (survives deployment wipes)
        if 'SECRET_KEY' in os.environ:
            temp_key = os.environ['SECRET_KEY']
            
            # Try to load persisted key from database
            try:
                persisted_key = get_setting('secret_key')
                
                if persisted_key:
                    # Use persisted key (stable across restarts)
                    os.environ['SECRET_KEY'] = persisted_key
                    app.config['SECRET_KEY'] = persisted_key
                    logger.info("Loaded SECRET_KEY from database (persistent across deployments)")
                else:
                    # Persist the temporary key we generated
                    set_setting('secret_key', temp_key)
                    logger.info("Persisted SECRET_KEY to database for future deployments")
            except Exception as e:
                logger.warning(f"Could not load/persist SECRET_KEY from database: {e}")
                logger.warning("Using temporary SECRET_KEY (sessions will be invalidated on restart)")
        
        # Get Netcup credentials from settings or environment
        netcup_customer_id = os.environ.get('NETCUP_CUSTOMER_ID') or Settings.get('netcup_customer_id')
        netcup_api_key = os.environ.get('NETCUP_API_KEY') or Settings.get('netcup_api_key')
        netcup_api_password = os.environ.get('NETCUP_API_PASSWORD') or Settings.get('netcup_api_password')
        
        if netcup_customer_id and netcup_api_key and netcup_api_password:
            logger.info("Netcup API credentials configured")
        else:
            logger.warning("Netcup API credentials not fully configured - API proxy will fail")
    
    logger.info("Netcup API Filter started successfully")
    
    # WSGI application
    application = app

except ImportError as e:
    error_msg = str(e)
    logger.error(f"Failed to import required module: {error_msg}", exc_info=True)
    logger.error(f"Python path: {sys.path[:5]}")
    
    def application(environ, start_response):
        status = '500 Internal Server Error'
        response_headers = [('Content-type', 'text/html; charset=utf-8')]
        start_response(status, response_headers)
        
        error_html = f"""
        <html>
        <head><title>Application Error</title></head>
        <body>
            <h1>Application Failed to Start</h1>
            <h2>Import Error</h2>
            <p><strong>Error:</strong> {error_msg}</p>
            <h3>Troubleshooting Steps:</h3>
            <ol>
                <li>Verify all files were uploaded (especially vendor/ directory)</li>
                <li>Check that Passenger App Root points to this directory</li>
                <li>Ensure Python version is 3.9 or higher</li>
                <li>Review error logs for more details</li>
            </ol>
            <h3>Python Path (first 5):</h3>
            <pre>{sys.path[:5]}</pre>
            <h3>Application Directory:</h3>
            <pre>{app_root}</pre>
        </body>
        </html>
        """
        return [error_html.encode('utf-8')]

except Exception as e:
    error_msg = str(e)
    logger.error(f"Failed to start application: {error_msg}", exc_info=True)
    
    def application(environ, start_response):
        status = '500 Internal Server Error'
        response_headers = [('Content-type', 'text/html; charset=utf-8')]
        start_response(status, response_headers)
        
        error_html = f"""
        <html>
        <head><title>Application Error</title></head>
        <body>
            <h1>Application Failed to Start</h1>
            <p><strong>Error:</strong> {error_msg}</p>
            <h3>Application Directory:</h3>
            <pre>{app_root}</pre>
        </body>
        </html>
        """
        return [error_html.encode('utf-8')]

if __name__ == "__main__":
    debug_mode = os.environ.get('FLASK_DEBUG', '').lower() == 'true'
    port = int(os.environ.get('FLASK_PORT', '5100'))
    app.run(debug=debug_mode, port=port, host='0.0.0.0')

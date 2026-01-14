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

# Expose app root for modules that need to locate deployment artifacts
os.environ.setdefault('NETCUP_FILTER_APP_ROOT', str(app_root))

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
        # NOTE: gunicorn may start multiple workers; protect this one-time import
        # from races by atomically "claiming" the file.
        claimed_config_path: str | None = None
        if os.path.exists(config_path):
            processing_path = f"{config_path}.processing.{os.getpid()}"
            try:
                os.replace(config_path, processing_path)
                claimed_config_path = processing_path
                logger.info(f"Claimed app-config.toml for one-time import: {processing_path}")
            except FileNotFoundError:
                # Another worker likely claimed it first.
                claimed_config_path = None

        if claimed_config_path:
            try:
                logger.info(f"Found app-config.toml at {claimed_config_path}, loading initial configuration...")
                
                # Try tomllib first (Python 3.11+), fallback to tomli
                try:
                    import tomllib
                    toml_parser = tomllib
                    logger.info("Using tomllib (Python 3.11+) for TOML parsing")
                except ImportError:
                    import tomli
                    toml_parser = tomli
                    logger.info("Using tomli for TOML parsing")
                
                with open(claimed_config_path, 'rb') as f:
                    config = toml_parser.load(f)
                
                logger.info(f"Parsed app-config.toml sections: {list(config.keys())}")
                
                # Define all valid top-level sections (CRITICAL: keep this updated!)
                VALID_SECTIONS = {
                    'rate_limits', 'security', 'smtp',  # Core settings
                    'session', 'admin', 'logging', 'notifications',  # Additional settings (NEW)
                    'netcup',  # Legacy, deprecated
                    'backends', 'domain_roots', 'users',  # Array-based config (new)
                    'geoip', 'free_domains', 'platform_backends'
                }
                
                # Validate: Fail on unknown sections (prevents typos and config drift)
                unknown_sections = set(config.keys()) - VALID_SECTIONS
                if unknown_sections:
                    error_msg = f"Unknown sections in app-config.toml: {sorted(unknown_sections)}"
                    logger.error(error_msg)
                    logger.error(f"Valid sections: {sorted(VALID_SECTIONS)}")
                    raise ValueError(error_msg)
                
                logger.info(f"✓ All sections valid: {sorted(config.keys())}")
                
                # Helper function to validate section keys (fail-fast on unknown keys)
                def validate_section_keys(section_name, actual_keys, valid_keys, is_warning=False):
                    """Validate that all keys in a section are known/expected.
                    
                    Args:
                        section_name: Name of the section (for error messages)
                        actual_keys: Set of keys found in the config
                        valid_keys: Set of valid/expected keys
                        is_warning: If True, log warning instead of raising error
                    """
                    unknown_keys = actual_keys - valid_keys
                    if unknown_keys:
                        error_msg = f"Unknown keys in [{section_name}]: {sorted(unknown_keys)}"
                        logger.error(error_msg)
                        logger.error(f"Valid keys for [{section_name}]: {sorted(valid_keys)}")
                        if is_warning:
                            logger.warning(f"Ignoring unknown keys (non-critical): {sorted(unknown_keys)}")
                        else:
                            raise ValueError(error_msg)
                    else:
                        logger.debug(f"✓ All keys valid in [{section_name}]")

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
                    
                    # Validate keys (fail-fast on unknown keys)
                    VALID_SECURITY_KEYS = {
                        'allowed_ip_ranges', 'blocked_ip_ranges', 'require_https',
                        'max_request_size', 'session_timeout', 'enable_2fa',
                        'password_min_length', 'password_require_uppercase',
                        'password_require_lowercase', 'password_require_digit',
                        'password_require_special',
                        'password_reset_expiry_hours', 'invite_expiry_hours'  # From example file
                    }
                    validate_section_keys('security', set(config['security'].keys()), VALID_SECURITY_KEYS)
                    
                    for key, value in config['security'].items():
                        set_setting(key, str(value))
                        logger.info(f"  ✓ Set {key} = '{value}'")
                else:
                    logger.info("No [security] section found in app-config.toml")
                
                # Apply SMTP config using TOML field names directly
                if 'smtp' in config:
                    import json
                    smtp_config = config['smtp']
                    logger.info(f"Processing smtp section with {len(smtp_config)} entries")
                    logger.info(f"  SMTP config keys: {list(smtp_config.keys())}")
                    
                    # Validate keys (fail-fast on unknown keys)
                    VALID_SMTP_KEYS = {
                        'smtp_host', 'smtp_port', 'smtp_security', 'use_ssl',
                        'smtp_username', 'smtp_password', 'from_email', 'from_name',
                        'reply_to', 'admin_email', 'notify_new_account',
                        'notify_realm_request', 'notify_security'
                    }
                    validate_section_keys('smtp', set(smtp_config.keys()), VALID_SMTP_KEYS)
                    
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
                    logger.info("No [smtp] section found in app-config.toml")
                
                # Apply session configuration (NEW)
                if 'session' in config:
                    import json
                    session_config = config['session']
                    logger.info(f"Processing session section with {len(session_config)} entries")
                    
                    # Validate keys
                    VALID_SESSION_KEYS = {
                        'cookie_secure', 'cookie_httponly', 'cookie_samesite', 'lifetime_seconds'
                    }
                    validate_section_keys('session', set(session_config.keys()), VALID_SESSION_KEYS)
                    
                    session_data = {
                        'cookie_secure': session_config.get('cookie_secure', 'auto'),
                        'cookie_httponly': session_config.get('cookie_httponly', True),
                        'cookie_samesite': session_config.get('cookie_samesite', 'Lax'),
                        'lifetime_seconds': session_config.get('lifetime_seconds', 3600),
                    }
                    
                    set_setting('session_config', json.dumps(session_data))
                    logger.info(f"  ✓ Set session_config")
                    logger.info(f"    - cookie_secure: {session_data['cookie_secure']}")
                    logger.info(f"    - cookie_httponly: {session_data['cookie_httponly']}")
                    logger.info(f"    - cookie_samesite: {session_data['cookie_samesite']}")
                    logger.info(f"    - lifetime_seconds: {session_data['lifetime_seconds']}")
                else:
                    logger.info("No [session] section found in app-config.toml")
                
                # Apply admin security configuration (NEW)
                if 'admin' in config:
                    import json
                    admin_config = config['admin']
                    logger.info(f"Processing admin section with {len(admin_config)} entries")
                    
                    # Validate keys
                    VALID_ADMIN_KEYS = {
                        'ip_whitelist', 'bind_session_to_ip', 'require_2fa'
                    }
                    validate_section_keys('admin', set(admin_config.keys()), VALID_ADMIN_KEYS)
                    
                    admin_data = {
                        'ip_whitelist': admin_config.get('ip_whitelist', []),
                        'bind_session_to_ip': admin_config.get('bind_session_to_ip', False),
                        'require_2fa': admin_config.get('require_2fa', False),
                    }
                    
                    set_setting('admin_security_config', json.dumps(admin_data))
                    logger.info(f"  ✓ Set admin_security_config")
                    logger.info(f"    - ip_whitelist: {admin_data['ip_whitelist']}")
                    logger.info(f"    - bind_session_to_ip: {admin_data['bind_session_to_ip']}")
                    logger.info(f"    - require_2fa: {admin_data['require_2fa']}")
                else:
                    logger.info("No [admin] section found in app-config.toml")
                
                # Apply logging configuration (NEW)
                if 'logging' in config:
                    import json
                    logging_config = config['logging']
                    logger.info(f"Processing logging section with {len(logging_config)} entries")
                    
                    # Validate keys
                    VALID_LOGGING_KEYS = {
                        'level', 'max_size_mb', 'backup_count'
                    }
                    validate_section_keys('logging', set(logging_config.keys()), VALID_LOGGING_KEYS)
                    
                    logging_data = {
                        'level': logging_config.get('level', 'INFO'),
                        'max_size_mb': logging_config.get('max_size_mb', 10),
                        'backup_count': logging_config.get('backup_count', 5),
                    }
                    
                    set_setting('logging_config', json.dumps(logging_data))
                    logger.info(f"  ✓ Set logging_config")
                    logger.info(f"    - level: {logging_data['level']}")
                    logger.info(f"    - max_size_mb: {logging_data['max_size_mb']}")
                    logger.info(f"    - backup_count: {logging_data['backup_count']}")
                else:
                    logger.info("No [logging] section found in app-config.toml")
                
                # Apply notification settings (NEW)
                if 'notifications' in config:
                    import json
                    notif_config = config['notifications']
                    logger.info(f"Processing notifications section with {len(notif_config)} entries")
                    
                    # Validate keys
                    VALID_NOTIFICATION_KEYS = {
                        'admin_email', 'notify_new_account', 'notify_realm_request',
                        'notify_security_events', 'notify_token_expiring_days'
                    }
                    validate_section_keys('notifications', set(notif_config.keys()), VALID_NOTIFICATION_KEYS)
                    
                    notif_data = {
                        'admin_email': notif_config.get('admin_email', ''),
                        'notify_new_account': notif_config.get('notify_new_account', True),
                        'notify_realm_request': notif_config.get('notify_realm_request', True),
                        'notify_security_events': notif_config.get('notify_security_events', True),
                        'notify_token_expiring_days': notif_config.get('notify_token_expiring_days', 7),
                    }
                    
                    set_setting('notifications_config', json.dumps(notif_data))
                    logger.info(f"  ✓ Set notifications_config")
                    logger.info(f"    - admin_email: {notif_data['admin_email']}")
                    logger.info(f"    - notify_new_account: {notif_data['notify_new_account']}")
                    logger.info(f"    - notify_realm_request: {notif_data['notify_realm_request']}")
                    logger.info(f"    - notify_security_events: {notif_data['notify_security_events']}")
                    logger.info(f"    - notify_token_expiring_days: {notif_data['notify_token_expiring_days']}")
                else:
                    logger.info("No [notifications] section found in app-config.toml")
                
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
                    
                    # Valid keys for each backend entry
                    VALID_BACKEND_KEYS = {
                        'service_name', 'provider', 'owner', 'display_name', 'config', 'description'
                    }
                    
                    # Store backends config as JSON array for bootstrap processing
                    backends_data = []
                    for idx, backend in enumerate(backends, 1):
                        # Validate backend keys
                        validate_section_keys(f'backends[{idx}]', set(backend.keys()), VALID_BACKEND_KEYS)
                        
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
                    
                    # Valid keys for each domain_root entry
                    VALID_DOMAIN_ROOT_KEYS = {
                        'backend', 'domain', 'dns_zone', 'visibility', 'display_name',
                        'description', 'allow_apex_access', 'min_subdomain_depth',
                        'max_subdomain_depth', 'allowed_record_types', 'allowed_operations',
                        'max_hosts_per_user', 'require_email_verification'
                    }
                    
                    # Store domain roots config as JSON array for bootstrap processing
                    domain_roots_data = []
                    for idx, domain_root in enumerate(domain_roots, 1):
                        # Validate domain_root keys
                        validate_section_keys(f'domain_roots[{idx}]', set(domain_root.keys()), VALID_DOMAIN_ROOT_KEYS)
                        
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
                users = config.get('users', [])
                if users:
                    import json
                    logger.info(f"Processing [[users]] arrays: {len(users)} user(s) to preseed")

                    # Store users config as JSON array for bootstrap processing
                    users_data = []
                    seen_usernames: set[str] = set()

                    for idx, user in enumerate(users, 1):
                        # Validate per-user keys (fail-fast on typos)
                        VALID_USER_KEYS = {
                            'username', 'email', 'password',
                            'is_approved', 'must_change_password',
                            'is_admin',
                        }
                        validate_section_keys(f'users[{idx}]', set(user.keys()), VALID_USER_KEYS)

                        username = user.get('username', '')
                        email = user.get('email', '')
                        password = user.get('password', 'generate')  # Special value "generate"
                        is_approved = user.get('is_approved', True)
                        must_change_password = user.get('must_change_password', False)
                        is_admin = user.get('is_admin', False)

                        username = username.strip()
                        email = email.strip()
                        if not username:
                            raise ValueError(f"users[{idx}].username is required")
                        if not email:
                            raise ValueError(f"users[{idx}].email is required")

                        if username in seen_usernames:
                            raise ValueError(
                                f"Duplicate username in [[users]]: {username}"
                            )
                        seen_usernames.add(username)
                        
                        users_data.append({
                            'username': username,
                            'email': email,
                            'password': password,
                            'is_approved': is_approved,
                            'must_change_password': must_change_password,
                            'is_admin': is_admin,
                        })
                        
                        logger.info(f"  [{idx}] {username} ({email})")
                        logger.info(f"      - password: {'<generated>' if password == 'generate' else '<explicit>'}")
                        logger.info(f"      - is_approved: {is_approved}")
                        logger.info(f"      - must_change_password: {must_change_password}")
                        logger.info(f"      - is_admin: {is_admin}")
                    
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
                try:
                    os.remove(claimed_config_path)
                except FileNotFoundError:
                    pass
                logger.info("✓ app-config.toml imported and deleted successfully")
                
            except ImportError as e:
                logger.warning(f"tomllib/tomli not available: {e}, cannot load app-config.toml")
            except Exception as e:
                logger.error(f"Failed to load app-config.toml: {e}", exc_info=True)
                # Best-effort: if import failed, restore the file for debugging/retry.
                try:
                    if claimed_config_path and not os.path.exists(config_path):
                        os.replace(claimed_config_path, config_path)
                        logger.warning("Restored app-config.toml after failed import")
                except Exception:
                    logger.warning("Could not restore app-config.toml after failed import", exc_info=True)
        
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

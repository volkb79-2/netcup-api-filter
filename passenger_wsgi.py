"""
WSGI Application Entry Point for Phusion Passenger
For deployment on Netcup webhosting or other shared hosting with Passenger support
"""
import sys
import os
import logging

# Add the application directory to the Python path
app_dir = os.path.dirname(__file__) or os.getcwd()
sys.path.insert(0, app_dir)

# Support for vendored dependencies (for FTP-only deployment)
vendor_dir = os.path.join(app_dir, 'vendor')
if os.path.isdir(vendor_dir):
    # Add vendor directory to the beginning of sys.path
    # This allows Python to find all packages extracted there
    sys.path.insert(0, vendor_dir)

# Configure logging
try:
    log_file_path = os.path.join(app_dir, 'netcup_filter.log')
    file_handler = logging.FileHandler(log_file_path, mode='a')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized to {log_file_path}")
except Exception as e:
    # Fallback to just stdout if file logging fails
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to setup file logging: {e}")

# Auto-detect database location if not explicitly set
if 'NETCUP_FILTER_DB_PATH' not in os.environ:
    # Always use application directory for database
    db_path = os.path.join(app_dir, 'netcup_filter.db')
    os.environ['NETCUP_FILTER_DB_PATH'] = db_path
    logger.info(f"Using database at: {db_path}")

try:
    from flask import Flask
    from database import init_db
    from admin_ui import setup_admin_ui
    import filter_proxy
    from filter_proxy import app, limiter
    from access_control import AccessControl
    from audit_logger import get_audit_logger
    from netcup_client import NetcupClient
    import yaml
    
    logger.info("Starting Netcup API Filter with Passenger...")
    logger.info(f"Application directory: {app_dir}")
    
    # Log vendor directory status
    if os.path.isdir(vendor_dir):
        logger.info(f"Using vendored dependencies from: {vendor_dir}")
    else:
        logger.info("Using system-installed dependencies")
    
    # Set up secret key for Flask sessions
    # SECURITY: Use environment variable or generate persistent key
    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key:
        # Generate a persistent secret key and store it
        secret_file = os.path.join(os.getcwd(), '.secret_key')
        try:
            if os.path.exists(secret_file):
                with open(secret_file, 'r') as f:
                    secret_key = f.read().strip()
            else:
                secret_key = os.urandom(24).hex()
                with open(secret_file, 'w') as f:
                    f.write(secret_key)
                os.chmod(secret_file, 0o600)  # Restrict permissions
                logger.info("Generated new persistent secret key")
        except Exception as e:
            logger.warning(f"Failed to persist secret key: {e}, using temporary key")
            secret_key = os.urandom(24).hex()
    
    app.config['SECRET_KEY'] = secret_key
    
    # Configure template and static folders for deployment
    deploy_templates = os.path.join(app_dir, 'deploy', 'templates')
    deploy_static = os.path.join(app_dir, 'deploy', 'static')
    
    if os.path.exists(deploy_templates):
        app.template_folder = deploy_templates
        logger.info(f"Using deploy templates from: {deploy_templates}")
    else:
        logger.warning(f"Deploy templates not found at: {deploy_templates}")
    
    if os.path.exists(deploy_static):
        app.static_folder = deploy_static
        logger.info(f"Using deploy static files from: {deploy_static}")
    else:
        logger.warning(f"Deploy static files not found at: {deploy_static}")
    
    # SECURITY: Configure secure session cookies (100% config-driven from environment)
    # Read from .env.defaults (NO HARDCODED VALUES!)
    secure_cookie = os.environ.get('FLASK_SESSION_COOKIE_SECURE', 'auto')
    if secure_cookie == 'auto':
        # Auto-detect: disable Secure flag only for local_test environment
        app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') != 'local_test'
    else:
        # Explicit override from config
        app.config['SESSION_COOKIE_SECURE'] = secure_cookie.lower() in ('true', '1', 'yes')
    
    app.config['SESSION_COOKIE_HTTPONLY'] = os.environ.get('FLASK_SESSION_COOKIE_HTTPONLY', 'True').lower() in ('true', '1', 'yes')
    app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get('FLASK_SESSION_COOKIE_SAMESITE', 'Lax')
    app.config['PERMANENT_SESSION_LIFETIME'] = int(os.environ.get('FLASK_SESSION_LIFETIME', '3600'))
    
    # Initialize database
    try:
        init_db(app)
        logger.info("Database initialized successfully")
        
        # DEBUG: Check admin user state
        with app.app_context():
            from database import AdminUser
            from utils import verify_password
            admin = AdminUser.query.filter_by(username='admin').first()
            if admin:
                logger.info(f"Admin user found: {admin.username}, must_change={admin.must_change_password}")
                password_valid = verify_password('admin', admin.password_hash)
                logger.info(f"Admin password verification: {password_valid}")
            else:
                logger.error("Admin user not found in database!")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    # Setup admin UI
    try:
        setup_admin_ui(app)
        logger.info("Admin UI initialized successfully")
    except Exception as e:
        logger.error(f"Failed to setup admin UI: {e}")
        raise
    
    # Initialize components for API proxy
    with app.app_context():
        from database import get_system_config, get_client_by_token
        
        # Load Netcup configuration from database
        netcup_config = get_system_config('netcup_config')
        if netcup_config:
            app.config['netcup_client'] = NetcupClient(
                customer_id=netcup_config.get('customer_id'),
                api_key=netcup_config.get('api_key'),
                api_password=netcup_config.get('api_password'),
                api_url=netcup_config.get('api_url', 'https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON')
            )
            filter_proxy.netcup_client = app.config['netcup_client']
            logger.info("Netcup client initialized from database")
        else:
            logger.warning("No Netcup configuration found in database")
        
        # Initialize access control with database mode
        app.config['access_control'] = AccessControl(use_database=True)
        filter_proxy.access_control = app.config['access_control']
        logger.info("Access control initialized in database mode")
        
        # Initialize audit logger
        log_file_path = os.path.join(os.getcwd(), 'netcup_filter_audit.log')
        app.config['audit_logger'] = get_audit_logger(log_file_path=log_file_path, enable_db=True)
        logger.info("Audit logger initialized")
        
        # Initialize email notifier (lazy loaded when needed)
        app.config['email_notifier'] = None
    
    logger.info("Netcup API Filter started successfully with Passenger")
    
    # NOTE: ProxyFix middleware is already applied in filter_proxy.py (line 27)
    # No need to apply it again here - doing so would create double-wrapping
    # and trust 2 proxies instead of 1, which is a security issue.
    
    # WSGI application
    application = app

except ImportError as e:
    logger.error(f"Failed to import required module: {e}", exc_info=True)
    logger.error("If using vendored dependencies, ensure vendor/ directory was uploaded correctly")
    logger.error(f"Python path: {sys.path[:5]}")
    
    # Create a minimal error application
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
            <p><strong>Error:</strong> {str(e)}</p>
            <h3>Troubleshooting Steps:</h3>
            <ol>
                <li>Verify all files were uploaded via FTP (especially vendor/ directory)</li>
                <li>Check that .htaccess PassengerPython path is correct</li>
                <li>Ensure Python version is 3.7 or higher</li>
                <li>Review error logs for more details</li>
            </ol>
            <h3>Python Path:</h3>
            <pre>{sys.path[:5]}</pre>
            <h3>Application Directory:</h3>
            <pre>{app_dir}</pre>
        </body>
        </html>
        """
        return [error_html.encode('utf-8')]

except Exception as e:
    logger.error(f"Failed to start application: {e}", exc_info=True)
    
    # Create a minimal error application
    def application(environ, start_response):
        status = '500 Internal Server Error'
        response_headers = [('Content-type', 'text/html; charset=utf-8')]
        start_response(status, response_headers)
        
        error_html = f"""
        <html>
        <head><title>Application Error</title></head>
        <body>
            <h1>Application Failed to Start</h1>
            <p><strong>Error:</strong> {str(e)}</p>
            <h3>Troubleshooting Steps:</h3>
            <ol>
                <li>Check .htaccess configuration (verify all paths are correct)</li>
                <li>Ensure netcup_filter.db file has correct permissions</li>
                <li>Verify all application files were uploaded</li>
                <li>Check error logs for detailed information</li>
            </ol>
            <h3>Application Directory:</h3>
            <pre>{app_dir}</pre>
        </body>
        </html>
        """
        return [error_html.encode('utf-8')]

if __name__ == "__main__":
    # For local testing only - never use debug=True in production
    import os
    debug_mode = os.environ.get('FLASK_DEBUG', '').lower() == 'true'
    app.run(debug=debug_mode)

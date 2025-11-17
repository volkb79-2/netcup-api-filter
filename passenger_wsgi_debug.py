"""
WSGI Application Entry Point for Phusion Passenger - DEBUG VERSION
This version captures and displays errors that occur during startup
"""
import sys
import os
import traceback

# Add the application directory to the Python path
app_dir = os.path.dirname(__file__) or os.getcwd()
sys.path.insert(0, app_dir)

# Support for vendored dependencies
vendor_dir = os.path.join(app_dir, 'vendor')
if os.path.isdir(vendor_dir):
    sys.path.insert(0, vendor_dir)

def create_error_app(error_info):
    """Create a WSGI app that displays the error"""
    def application(environ, start_response):
        status = '500 Internal Server Error'
        response_headers = [('Content-Type', 'text/html; charset=utf-8')]
        start_response(status, response_headers)
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Application Startup Error</title>
    <style>
        body {{ font-family: monospace; margin: 20px; background: #1e1e1e; color: #d4d4d4; }}
        .error {{ background: #5a1d1d; padding: 20px; border-left: 4px solid #f44336; margin: 20px 0; }}
        .traceback {{ background: #2d2d2d; padding: 15px; overflow-x: auto; white-space: pre; }}
        h1 {{ color: #f44336; }}
        .info {{ background: #1e3a5f; padding: 15px; border-left: 4px solid #2196f3; margin: 20px 0; }}
    </style>
</head>
<body>
    <h1>❌ Application Failed to Start</h1>
    <div class="error">
        <h2>Error Details:</h2>
        <div class="traceback">{error_info}</div>
    </div>
    <div class="info">
        <h3>Debug Information:</h3>
        <p><strong>App Directory:</strong> {app_dir}</p>
        <p><strong>Vendor Directory Exists:</strong> {os.path.isdir(vendor_dir)}</p>
        <p><strong>Python Version:</strong> {sys.version}</p>
        <p><strong>Python Path (first 5):</strong></p>
        <pre>{chr(10).join(sys.path[:5])}</pre>
    </div>
    <div class="info">
        <h3>Next Steps:</h3>
        <ul>
            <li>Check that all files from vendor/ directory were uploaded</li>
            <li>Verify Python version compatibility (needs 3.9+)</li>
            <li>Check file permissions</li>
            <li>Look for specific import errors above</li>
        </ul>
    </div>
</body>
</html>
"""
        return [html.encode('utf-8')]
    return application

# Try to import and start the application
try:
    import logging
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(app_dir, 'netcup_filter.log')),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    
    # Auto-detect database location
    if 'NETCUP_FILTER_DB_PATH' not in os.environ:
        db_path = os.path.join(app_dir, 'netcup_filter.db')
        if os.path.exists(db_path):
            os.environ['NETCUP_FILTER_DB_PATH'] = db_path
            logger.info(f"Auto-detected database at: {db_path}")
    
    logger.info("=" * 60)
    logger.info("Starting Netcup API Filter with Passenger...")
    logger.info(f"Application directory: {app_dir}")
    logger.info(f"Vendor directory: {vendor_dir}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Python path: {sys.path[:5]}")
    
    # Import Flask and dependencies
    logger.info("Importing Flask...")
    from flask import Flask
    
    logger.info("Importing database module...")
    from database import init_db
    
    logger.info("Importing admin_ui module...")
    from admin_ui import setup_admin_ui
    
    logger.info("Importing filter_proxy module...")
    import filter_proxy
    from filter_proxy import app, limiter
    
    logger.info("Importing access_control module...")
    from access_control import AccessControl
    
    logger.info("Importing audit_logger module...")
    from audit_logger import get_audit_logger
    
    logger.info("Importing netcup_client module...")
    from netcup_client import NetcupClient
    
    logger.info("Importing yaml module...")
    import yaml
    
    logger.info("All imports successful!")
    
    # Set up secret key for Flask sessions
    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key:
        secret_file = os.path.join(app_dir, '.secret_key')
        try:
            if os.path.exists(secret_file):
                with open(secret_file, 'r') as f:
                    secret_key = f.read().strip()
                logger.info("Loaded existing secret key")
            else:
                secret_key = os.urandom(24).hex()
                with open(secret_file, 'w') as f:
                    f.write(secret_key)
                os.chmod(secret_file, 0o600)
                logger.info("Generated new persistent secret key")
        except Exception as e:
            logger.warning(f"Failed to persist secret key: {e}, using temporary key")
            secret_key = os.urandom(24).hex()
    
    app.config['SECRET_KEY'] = secret_key
    
    # SECURITY: Configure secure session cookies
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600
    
    # Initialize database
    logger.info("Initializing database...")
    init_db(app)
    logger.info("Database initialized")
    
    # Setup admin UI
    logger.info("Setting up admin UI...")
    setup_admin_ui(app)
    logger.info("Admin UI initialized")
    
    # Initialize components
    with app.app_context():
        from database import get_system_config, get_client_by_token
        
        # Load Netcup configuration
        netcup_config = get_system_config('netcup_config')
        if netcup_config:
            app.config['netcup_client'] = NetcupClient(
                customer_id=netcup_config.get('customer_id'),
                api_key=netcup_config.get('api_key'),
                api_password=netcup_config.get('api_password'),
                api_url=netcup_config.get('api_url', 'https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON')
            )
            filter_proxy.netcup_client = app.config['netcup_client']
            logger.info("Netcup client initialized")
        else:
            logger.warning("No Netcup configuration found")
        
        # Initialize access control
        app.config['access_control'] = AccessControl(use_database=True)
        filter_proxy.access_control = app.config['access_control']
        logger.info("Access control initialized")
        
        # Initialize audit logger
        log_file_path = os.path.join(app_dir, 'netcup_filter_audit.log')
        app.config['audit_logger'] = get_audit_logger(log_file_path=log_file_path, enable_db=True)
        logger.info("Audit logger initialized")
        
        # Initialize email notifier (lazy loaded)
        app.config['email_notifier'] = None
    
    logger.info("✅ Netcup API Filter started successfully!")
    logger.info("=" * 60)
    
    # WSGI application
    application = app

except Exception as e:
    # Capture the full error with traceback
    error_details = traceback.format_exc()
    
    # Try to log it
    try:
        with open(os.path.join(app_dir, 'netcup_filter_startup_error.log'), 'w') as f:
            f.write(f"STARTUP ERROR at {os.path.basename(__file__)}\n")
            f.write("=" * 60 + "\n")
            f.write(error_details)
            f.write("\n" + "=" * 60 + "\n")
            f.write(f"App directory: {app_dir}\n")
            f.write(f"Vendor exists: {os.path.isdir(vendor_dir)}\n")
            f.write(f"Python version: {sys.version}\n")
    except:
        pass  # If we can't write the log, continue anyway
    
    # Create error application
    application = create_error_app(error_details.replace('<', '&lt;').replace('>', '&gt;'))

if __name__ == "__main__":
    # For local testing
    app.run(debug=False)

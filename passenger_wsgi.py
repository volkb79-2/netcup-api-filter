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
    # Add vendor directory itself
    sys.path.insert(0, vendor_dir)
    
    # Add all subdirectories in vendor (for package structures)
    try:
        for item in os.listdir(vendor_dir):
            item_path = os.path.join(vendor_dir, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                sys.path.insert(0, item_path)
    except OSError as e:
        # Log but don't fail if we can't read vendor directory
        pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('netcup_filter.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Auto-detect database location if not explicitly set
if 'NETCUP_FILTER_DB_PATH' not in os.environ:
    # Try application directory first
    db_path = os.path.join(app_dir, 'netcup_filter.db')
    if os.path.exists(db_path):
        os.environ['NETCUP_FILTER_DB_PATH'] = db_path
        logger.info(f"Auto-detected database at: {db_path}")

try:
    from flask import Flask
    from database import init_db
    from admin_ui import setup_admin_ui
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
    
    # SECURITY: Configure secure session cookies
    app.config['SESSION_COOKIE_SECURE'] = True  # Only send over HTTPS
    app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour session timeout
    
    # Initialize database
    try:
        init_db(app)
        logger.info("Database initialized successfully")
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
            logger.info("Netcup client initialized from database")
        else:
            logger.warning("No Netcup configuration found in database")
        
        # Initialize access control with database mode
        app.config['access_control'] = AccessControl(use_database=True)
        logger.info("Access control initialized in database mode")
        
        # Initialize audit logger
        log_file_path = os.path.join(os.getcwd(), 'netcup_filter_audit.log')
        app.config['audit_logger'] = get_audit_logger(log_file_path=log_file_path, enable_db=True)
        logger.info("Audit logger initialized")
        
        # Initialize email notifier (lazy loaded when needed)
        app.config['email_notifier'] = None
    
    logger.info("Netcup API Filter started successfully with Passenger")
    
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

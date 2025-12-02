"""
WSGI Application Entry Point for Phusion Passenger
Account → Realms → Tokens with Bearer token authentication
"""
import sys
import os
import logging
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
    
    # Initialize Netcup API client
    with app.app_context():
        from netcup_api_filter.database import db
        from netcup_api_filter.models import Settings
        
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

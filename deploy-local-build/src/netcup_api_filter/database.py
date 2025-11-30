"""
Database models and operations for netcup-api-filter
Uses SQLAlchemy for ORM and SQLite for storage
"""
import logging
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, text
import json

from .config_defaults import require_default

logger = logging.getLogger(__name__)

# Initialize SQLAlchemy
db = SQLAlchemy()


class Client(db.Model):
    """Client configuration with two-factor authentication (client_id + secret_key)"""
    __tablename__ = 'clients'
    
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.String(255), unique=True, nullable=False, index=True)  # Cleartext identifier, manageable in UI
    secret_key_hash = db.Column(db.String(255), nullable=False)  # Hashed secret key (bcrypt), never retrievable
    description = db.Column(db.Text)
    realm_type = db.Column(db.String(20), nullable=False)  # 'host' or 'subdomain'
    realm_value = db.Column(db.String(255), nullable=False)
    allowed_record_types = db.Column(db.Text, nullable=False)  # JSON array
    allowed_operations = db.Column(db.Text, nullable=False)  # JSON array
    allowed_ip_ranges = db.Column(db.Text)  # JSON array, optional
    email_address = db.Column(db.String(255))
    email_notifications_enabled = db.Column(db.Integer, default=0)
    token_expires_at = db.Column(db.DateTime)
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        CheckConstraint("realm_type IN ('host', 'subdomain')", name='check_realm_type'),
    )
    
    def get_allowed_record_types(self) -> List[str]:
        """Parse allowed_record_types from JSON"""
        try:
            return json.loads(self.allowed_record_types) if self.allowed_record_types else []
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Failed to parse allowed_record_types for client {self.client_id}")
            return []
    
    def set_allowed_record_types(self, types: List[str]):
        """Set allowed_record_types as JSON"""
        self.allowed_record_types = json.dumps(types)
    
    def get_allowed_operations(self) -> List[str]:
        """Parse allowed_operations from JSON"""
        try:
            return json.loads(self.allowed_operations) if self.allowed_operations else []
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Failed to parse allowed_operations for client {self.client_id}")
            return []
    
    def set_allowed_operations(self, operations: List[str]):
        """Set allowed_operations as JSON"""
        self.allowed_operations = json.dumps(operations)
    
    def get_allowed_ip_ranges(self) -> List[str]:
        """Parse allowed_ip_ranges from JSON"""
        try:
            return json.loads(self.allowed_ip_ranges) if self.allowed_ip_ranges else []
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Failed to parse allowed_ip_ranges for client {self.client_id}")
            return []
    
    def set_allowed_ip_ranges(self, ranges: List[str]):
        """Set allowed_ip_ranges as JSON"""
        self.allowed_ip_ranges = json.dumps(ranges) if ranges else None
    
    def __repr__(self):
        return f'<Client {self.client_id}>'


class AuditLog(db.Model):
    """Audit log entries for API access"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    client_id = db.Column(db.String(255), index=True)
    ip_address = db.Column(db.String(45))  # IPv6 max length
    operation = db.Column(db.String(50), index=True)
    domain = db.Column(db.String(255), index=True)
    record_details = db.Column(db.Text)  # JSON
    success = db.Column(db.Integer, index=True)
    error_message = db.Column(db.Text)
    request_data = db.Column(db.Text)  # JSON
    response_data = db.Column(db.Text)  # JSON
    
    def get_record_details(self) -> Dict[str, Any]:
        """Parse record_details from JSON"""
        try:
            return json.loads(self.record_details) if self.record_details else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_record_details(self, details: Dict[str, Any]):
        """Set record_details as JSON"""
        self.record_details = json.dumps(details) if details else None
    
    def get_request_data(self) -> Dict[str, Any]:
        """Parse request_data from JSON"""
        try:
            return json.loads(self.request_data) if self.request_data else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_request_data(self, data: Dict[str, Any]):
        """Set request_data as JSON"""
        # Mask sensitive data
        if data:
            masked_data = data.copy()
            if 'param' in masked_data and isinstance(masked_data['param'], dict):
                for key in ['apipassword', 'apisessionid', 'apikey']:
                    if key in masked_data['param']:
                        masked_data['param'][key] = '***MASKED***'
            self.request_data = json.dumps(masked_data)
        else:
            self.request_data = None
    
    def get_response_data(self) -> Dict[str, Any]:
        """Parse response_data from JSON"""
        try:
            return json.loads(self.response_data) if self.response_data else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_response_data(self, data: Dict[str, Any]):
        """Set response_data as JSON"""
        # Mask sensitive data
        if data:
            masked_data = data.copy()
            if 'responsedata' in masked_data and isinstance(masked_data['responsedata'], dict):
                if 'apisessionid' in masked_data['responsedata']:
                    masked_data['responsedata']['apisessionid'] = '***MASKED***'
            self.response_data = json.dumps(masked_data)
        else:
            self.response_data = None
    
    def __repr__(self):
        return f'<AuditLog {self.timestamp} {self.client_id} {self.operation}>'


class AdminUser(db.Model):
    """Admin user for web UI access"""
    __tablename__ = 'admin_users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    must_change_password = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<AdminUser {self.username}>'


class SystemConfig(db.Model):
    """System configuration key-value store"""
    __tablename__ = 'system_config'
    
    key = db.Column(db.String(255), primary_key=True)
    value = db.Column(db.Text)  # JSON
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_value(self) -> Dict[str, Any]:
        """Parse value from JSON"""
        try:
            return json.loads(self.value) if self.value else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_value(self, data: Dict[str, Any]):
        """Set value as JSON"""
        self.value = json.dumps(data) if data else None
    
    def __repr__(self):
        return f'<SystemConfig {self.key}>'


def get_db_path() -> str:
    """
    Get database file path
    Priority: environment variable > current directory
    """
    db_path = os.environ.get('NETCUP_FILTER_DB_PATH')
    if db_path:
        logger.info(f"Using database path from environment: {db_path}")
        return db_path
    
    # Default to current directory
    db_path = os.path.join(os.getcwd(), 'netcup_filter.db')
    logger.info(f"Using default database path: {db_path}")
    return db_path


def init_db(app):
    """Initialize database with Flask app"""
    db_path = get_db_path()
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }
    
    db.init_app(app)
    
    with app.app_context():
        # Create all tables
        db.create_all()
        logger.info("Database tables created/verified")
        
        # Seed default admin user (demo clients optional)
        from .bootstrap import seed_default_entities

        seed_demo = os.environ.get('SEED_DEMO_CLIENTS', '').lower() in {'1', 'true', 'yes'}
        seed_default_entities(seed_demo_clients_flag=seed_demo)
        if seed_demo:
            logger.info("Default admin user and demo clients seeded")
        else:
            logger.info("Default admin user seeded (demo clients disabled)")


def get_client_by_token(token: str) -> Optional[Client]:
    """
    Get client by authentication token (client_id:secret_key format).
    
    Args:
        token: Authentication token in format "client_id:secret_key"
        
    Returns:
        Client object if valid, None otherwise
    """
    from .utils import verify_password
    
    # Parse two-factor format: client_id:secret_key
    if ':' not in token:
        logger.warning("Invalid token format - expected client_id:secret_key")
        return None
    
    parts = token.split(':', 1)
    if len(parts) != 2:
        logger.warning("Invalid token format - expected exactly one colon separator")
        return None
    
    client_id, secret_key = parts
    
    # Fast O(1) lookup by client_id
    client = Client.query.filter_by(client_id=client_id, is_active=1).first()
    
    if not client:
        logger.debug(f"Client not found: {client_id}")
        return None
    
    if not verify_password(secret_key, client.secret_key_hash):
        logger.warning(f"Invalid secret key for client: {client_id}")
        return None
    
    # Check expiration
    if client.token_expires_at and client.token_expires_at < datetime.utcnow():
        logger.warning(f"Client {client.client_id} token expired")
        return None
    
    return client


def get_client_by_id(client_id: str) -> Optional[Client]:
    """Get client by client_id"""
    return Client.query.filter_by(client_id=client_id, is_active=1).first()


def create_audit_log(client_id: Optional[str], ip_address: str, operation: str,
                     domain: str, record_details: Optional[Dict[str, Any]],
                     success: bool, error_message: Optional[str],
                     request_data: Optional[Dict[str, Any]],
                     response_data: Optional[Dict[str, Any]]) -> AuditLog:
    """Create and save an audit log entry"""
    log = AuditLog(
        client_id=client_id,
        ip_address=ip_address,
        operation=operation,
        domain=domain,
        success=1 if success else 0,
        error_message=error_message
    )
    
    if record_details:
        log.set_record_details(record_details)
    if request_data:
        log.set_request_data(request_data)
    if response_data:
        log.set_response_data(response_data)
    
    db.session.add(log)
    db.session.commit()
    
    return log


def get_system_config(key: str) -> Optional[Dict[str, Any]]:
    """Get system configuration value"""
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        return config.get_value()
    return None


def set_system_config(key: str, value: Dict[str, Any]):
    """Set system configuration value"""
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.set_value(value)
        config.updated_at = datetime.utcnow()
    else:
        config = SystemConfig(key=key)
        config.set_value(value)
        db.session.add(config)
    
    db.session.commit()


def create_app(config_path: str = "config.yaml"):
    """
    Create and configure the Flask application
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        Configured Flask application instance
    """
    from flask import Flask
    from werkzeug.middleware.proxy_fix import ProxyFix
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    import yaml
    import os
    
    # Import here to avoid circular imports
    from .filter_proxy import load_config as load_filter_config
    from .admin_ui import setup_admin_ui
    from .access_control import AccessControl
    from .audit_logger import get_audit_logger
    from .netcup_client import NetcupClient
    from .client_portal import client_portal_bp
    from .utils import get_build_info
    
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    
    # Register blueprints
    app.register_blueprint(client_portal_bp)
    
    # Context processor for build metadata
    @app.context_processor
    def inject_build_metadata():
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
    
    # Set up secret key for Flask sessions
    secret_key = os.environ.get('SECRET_KEY') or require_default('SECRET_KEY')
    app.config['SECRET_KEY'] = secret_key
    
    # Configure template and static folders for deployment
    deploy_templates = os.path.join(os.getcwd(), 'deploy', 'templates')
    deploy_static = os.path.join(os.getcwd(), 'deploy', 'static')
    
    if os.path.exists(deploy_templates):
        app.template_folder = deploy_templates
    if os.path.exists(deploy_static):
        app.static_folder = deploy_static
    
    # SECURITY: Configure secure session cookies
    app.config['SESSION_COOKIE_SECURE'] = True  # Only send over HTTPS
    app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour session timeout
    
    # Initialize database
    init_db(app)
    
    # Setup admin UI
    setup_admin_ui(app)
    
    # Load configuration and initialize components
    try:
        load_filter_config(config_path)
        
        # Initialize components within app context
        with app.app_context():
            # Load Netcup configuration from database
            netcup_config = get_system_config('netcup_config')
            if netcup_config:
                from .filter_proxy import netcup_client as fp_netcup_client
                app.config['netcup_client'] = NetcupClient(
                    customer_id=netcup_config.get('customer_id'),
                    api_key=netcup_config.get('api_key'),
                    api_password=netcup_config.get('api_password'),
                    api_url=netcup_config.get('api_url', 'https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON')
                )
                fp_netcup_client = app.config['netcup_client']
            
            # Initialize access control with database mode
            from .filter_proxy import access_control as fp_access_control
            app.config['access_control'] = AccessControl(use_database=True)
            fp_access_control = app.config['access_control']
            
            # Initialize audit logger
            log_file_path = os.path.join(os.getcwd(), 'netcup_filter_audit.log')
            app.config['audit_logger'] = get_audit_logger(log_file_path=log_file_path, enable_db=True)
            
            # Initialize email notifier (lazy loaded when needed)
            app.config['email_notifier'] = None
    
    except Exception as e:
        logger.warning(f"Failed to load configuration from {config_path}: {e}")
        # Continue with minimal configuration for testing
    
    return app

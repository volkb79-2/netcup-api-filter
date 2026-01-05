"""
Flask Application Factory (Account/Realms/Tokens architecture).

This application factory uses:
- New database schema (Account, AccountRealm, APIToken)
- Bearer token authentication for API
- Session-based authentication for UI
"""
import logging
import os
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from .config_defaults import get_default, require_default
from .database import init_db, db
from .api import account_bp, admin_bp, dns_api_bp, ddns_protocols_bp

logger = logging.getLogger(__name__)

# Initialize CSRF protection globally
csrf = CSRFProtect()


def create_app(config_path: str = "config.yaml") -> Flask:
    """
    Create and configure the Flask application.
    
    Args:
        config_path: Path to configuration file (legacy, may not be used)
        
    Returns:
        Configured Flask application instance
    """
    app = Flask(__name__)
    
    # Trust proxy headers (for reverse proxy deployments)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    
    # =========================================================================
    # Security Configuration
    # =========================================================================
    
    # Secret key for sessions (with production validation)
    secret_key = os.environ.get('SECRET_KEY')
    
    # In production, SECRET_KEY must be set and not use default
    flask_env = os.environ.get('FLASK_ENV', '')
    if not flask_env or flask_env == 'production':
        default_secret = get_default('SECRET_KEY', '')
        if not secret_key:
            raise RuntimeError(
                "SECRET_KEY environment variable not set. "
                "Generate one with: openssl rand -hex 32"
            )
        if secret_key == default_secret and default_secret:
            raise RuntimeError(
                f"SECRET_KEY is using insecure default value ('{default_secret[:20]}...'). "
                "Generate a secure key with: openssl rand -hex 32"
            )
    
    # Development/testing can use default if not provided
    if not secret_key:
        secret_key = require_default('SECRET_KEY')
    
    app.config['SECRET_KEY'] = secret_key
    
    # Maximum request size (10 MB)
    app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_CONTENT_LENGTH', 10 * 1024 * 1024))
    
    # Session cookie configuration (config-driven)
    
    # Secure cookie - auto mode: off for local testing, on for production
    secure_setting = os.environ.get('FLASK_SESSION_COOKIE_SECURE', 
                                    get_default('FLASK_SESSION_COOKIE_SECURE', 'auto'))
    if secure_setting == 'auto':
        app.config['SESSION_COOKIE_SECURE'] = flask_env != 'local_test'
    else:
        app.config['SESSION_COOKIE_SECURE'] = secure_setting.lower() in ('true', '1', 'yes')
    
    app.config['SESSION_COOKIE_HTTPONLY'] = os.environ.get(
        'FLASK_SESSION_COOKIE_HTTPONLY',
        get_default('FLASK_SESSION_COOKIE_HTTPONLY', 'True')
    ).lower() in ('true', '1', 'yes')
    
    app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get(
        'FLASK_SESSION_COOKIE_SAMESITE',
        get_default('FLASK_SESSION_COOKIE_SAMESITE', 'Lax')
    )
    
    app.config['PERMANENT_SESSION_LIFETIME'] = int(os.environ.get(
        'FLASK_SESSION_LIFETIME',
        get_default('FLASK_SESSION_LIFETIME', '3600')
    ))
    
    # =========================================================================
    # Template and Static Configuration
    # =========================================================================
    
    # Template auto-reload for development (config-driven)
    templates_auto_reload = os.environ.get('TEMPLATES_AUTO_RELOAD', 'false').lower() in ('true', '1', 'yes')
    app.config['TEMPLATES_AUTO_RELOAD'] = templates_auto_reload
    
    # Static file cache control - disable caching in local test mode
    static_max_age = int(os.environ.get('SEND_FILE_MAX_AGE_DEFAULT', '0' if flask_env == 'local_test' else '43200'))
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = static_max_age
    
    # Configure template and static folders for deployment
    deploy_templates = os.path.join(os.getcwd(), 'src', 'netcup_api_filter', 'templates')
    deploy_static = os.path.join(os.getcwd(), 'src', 'netcup_api_filter', 'static')
    
    # Check various possible locations
    for templates_path in [
        deploy_templates,
        os.path.join(os.getcwd(), 'deploy', 'src', 'netcup_api_filter', 'templates'),
        os.path.join(os.getcwd(), 'templates'),
    ]:
        if os.path.exists(templates_path):
            app.template_folder = templates_path
            break
    
    for static_path in [
        deploy_static,
        os.path.join(os.getcwd(), 'deploy', 'src', 'netcup_api_filter', 'static'),
        os.path.join(os.getcwd(), 'static'),
    ]:
        if os.path.exists(static_path):
            app.static_folder = static_path
            break
    
    # =========================================================================
    # Database Initialization
    # =========================================================================
    
    init_db(app)
    
    # =========================================================================
    # CSRF Protection
    # =========================================================================
    
    csrf.init_app(app)
    
    # Exempt API endpoints from CSRF (they use Bearer tokens)
    csrf.exempt(dns_api_bp)
    csrf.exempt(ddns_protocols_bp)
    
    # =========================================================================
    # Rate Limiting
    # =========================================================================
    
    flask_env = os.environ.get('FLASK_ENV', 'production')
    
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        
        # Disable rate limiting for local testing
        if flask_env == 'local_test':
            limiter = Limiter(
                app=app,
                key_func=get_remote_address,
                enabled=False,  # Disabled for testing
                storage_uri="memory://",
            )
            logger.info("Rate limiting disabled for local_test environment")
        else:
            limiter = Limiter(
                app=app,
                key_func=get_remote_address,
                default_limits=["200 per hour", "50 per minute"],
                storage_uri="memory://",
            )
            
            # Apply stricter limits to auth endpoints
            limiter.limit("10 per minute")(admin_bp)
            limiter.limit("10 per minute")(account_bp)
        
    except ImportError:
        logger.warning("flask-limiter not installed, rate limiting disabled")
    
    # =========================================================================
    # Register Blueprints
    # =========================================================================
    
    app.register_blueprint(admin_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(dns_api_bp)
    app.register_blueprint(ddns_protocols_bp)
    
    # =========================================================================
    # Template Filters
    # =========================================================================
    
    @app.template_filter('format_realm')
    def format_realm_filter(realm):
        """Format realm for display with intuitive type indicators.
        
        Returns a formatted string showing the realm scope:
        - host type: exact hostname (vpn.example.com)
        - subdomain type: * prefix indicating wildcard (*.iot.example.com)
        - subdomain_only type: *. prefix indicating children only (*.client.example.com, not client.example.com)
        - empty realm_value: just the domain (apex)
        """
        if not realm:
            return '—'
        
        domain = realm.domain
        realm_value = realm.realm_value or ''
        realm_type = realm.realm_type
        
        if realm_value:
            fqdn = f'{realm_value}.{domain}'
        else:
            fqdn = domain
        
        if realm_type == 'host':
            # Exact match - just show the hostname
            return fqdn
        elif realm_type == 'subdomain':
            # Apex + all children - use * prefix
            return f'*.{fqdn}' if realm_value else f'*.{domain}'
        elif realm_type == 'subdomain_only':
            # Children only, not apex - use *. prefix (dot emphasized)
            return f'*/{fqdn}'  # Using */ to indicate "children of" not including self
        else:
            return fqdn
    
    @app.template_filter('realm_type_badge')
    def realm_type_badge_filter(realm_type):
        """Return appropriate badge class and label for realm type."""
        badges = {
            'host': ('bg-primary', 'Exact'),
            'subdomain': ('bg-success', 'Wildcard'),
            'subdomain_only': ('bg-info', 'Children Only'),
        }
        return badges.get(realm_type, ('bg-secondary', realm_type))
    
    # Context Processors
    # =========================================================================
    
    @app.context_processor
    def inject_build_metadata():
        """Inject build info into all templates."""
        try:
            from .utils import get_build_info
            return {'build_info': get_build_info() or {}}
        except Exception:
            return {'build_info': {}}
    
    @app.context_processor
    def inject_geoip_functions():
        """Inject GeoIP lookup functions into templates."""
        try:
            from .geoip_service import geoip_location, lookup as geoip_lookup
            return {
                'geoip_location': geoip_location,
                'geoip_lookup': geoip_lookup
            }
        except ImportError:
            # GeoIP not available - provide stub functions
            return {
                'geoip_location': lambda ip: 'Unknown',
                'geoip_lookup': lambda ip: None
            }
    
    # =========================================================================
    # Error Handlers
    # =========================================================================
    
    @app.errorhandler(400)
    def bad_request(e):
        from flask import jsonify, request, render_template
        if request.path.startswith('/api/'):
            return jsonify({'error': 'bad_request', 'message': str(e.description) if hasattr(e, 'description') else 'Bad request'}), 400
        return render_template('errors/400.html'), 400
    
    @app.errorhandler(401)
    def unauthorized(e):
        from flask import jsonify, request, render_template
        if request.path.startswith('/api/'):
            return jsonify({'error': 'unauthorized', 'message': 'Authentication required'}), 401
        return render_template('errors/401.html'), 401
    
    @app.errorhandler(403)
    def forbidden(e):
        from flask import jsonify, request, render_template
        if request.path.startswith('/api/'):
            return jsonify({'error': 'forbidden', 'message': 'Access forbidden'}), 403
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(404)
    def not_found(e):
        from flask import jsonify, request, render_template
        if request.path.startswith('/api/'):
            return jsonify({'error': 'not_found', 'message': 'Endpoint not found'}), 404
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(429)
    def rate_limited(e):
        from flask import jsonify, request, render_template
        retry_after = getattr(e, 'retry_after', 60)
        if request.path.startswith('/api/'):
            response = jsonify({'error': 'rate_limited', 'message': 'Too many requests', 'retry_after': retry_after})
            response.headers['Retry-After'] = str(retry_after)
            return response, 429
        return render_template('errors/429.html', retry_after=retry_after), 429
    
    @app.errorhandler(500)
    def internal_error(e):
        from flask import jsonify, request, render_template
        import uuid
        error_id = str(uuid.uuid4())[:8]
        logger.exception(f"Internal server error [{error_id}]")
        if request.path.startswith('/api/'):
            return jsonify({'error': 'internal', 'message': 'Internal server error', 'error_id': error_id}), 500
        return render_template('errors/500.html', error_id=error_id), 500
    
    # =========================================================================
    # Health Check
    # =========================================================================
    
    @app.route('/health')
    def health():
        """Health check endpoint."""
        from flask import jsonify
        return jsonify({'status': 'ok'})
    
    # =========================================================================
    # Cache Control (for local development)
    # =========================================================================
    
    if flask_env == 'local_test':
        @app.after_request
        def add_cache_control_headers(response):
            """Add no-cache headers for HTML in local test mode."""
            if response.content_type and 'text/html' in response.content_type:
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
            return response
    
    # =========================================================================
    # Root Redirect
    # =========================================================================
    
    @app.route('/')
    def index():
        """Redirect root to appropriate portal."""
        from flask import redirect, session, url_for
        
        # Check if admin is logged in
        if session.get('admin_id'):
            return redirect(url_for('admin.dashboard'))
        
        # Check if account is logged in
        if session.get('account_id'):
            return redirect(url_for('account.dashboard'))
        
        # Default to account login (user-facing portal)
        return redirect(url_for('account.login'))
    
    # =========================================================================
    # Design System Demos (public)
    # Demo pages are organized under src/netcup_api_filter/demos/
    # =========================================================================
    
    @app.route('/theme-demo')
    def theme_demo():
        """Theme demo page for previewing all UI themes."""
        from flask import send_from_directory
        return send_from_directory('demos/theme-demo', 'index.html')
    
    @app.route('/component-demo')
    def component_demo():
        """Component demo page for design system reference (custom CSS)."""
        from flask import send_from_directory
        return send_from_directory('demos/component-demo', 'index.html')
    
    @app.route('/component-demo-bs5')
    def component_demo_bs5():
        """Component demo page using Bootstrap 5 theming."""
        from flask import send_from_directory
        return send_from_directory('demos/component-demo-bs5', 'index.html')
    
    @app.route('/theme-demo2')
    def theme_demo2():
        """Theme demo v2 with 17 themes for CSS comparison."""
        from flask import send_from_directory
        return send_from_directory(
            'demos/theme-demo2',
            'Theme Demo - Netcup API Filter.html'
        )

    @app.route('/theme-demo2/<path:filename>')
    def theme_demo2_static(filename):
        """Serve static assets for theme demo v2."""
        from flask import send_from_directory
        return send_from_directory('demos/theme-demo2', filename)
    
    logger.info("Flask application created successfully")
    
    return app

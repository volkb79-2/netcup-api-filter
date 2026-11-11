"""
Flask Application Factory (Account/Realms/Tokens architecture).

This application factory uses:
- New database schema (Account, AccountRealm, APIToken)
- Bearer token authentication for API
- Session-based authentication for UI
"""
import logging
import os
import threading
from urllib.parse import urlsplit, urlunsplit

from flask import Flask, has_request_context, request
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from .config_defaults import get_default
from .database import init_db
from .api import account_bp, admin_bp, dns_api_bp, ddns_protocols_bp, telegram_bp
from .public_url import get_configured_public_base_url, host_is_valid
from .utils import parse_bool

logger = logging.getLogger(__name__)

_forwarded_header_warning_logged = False
_forwarded_header_warning_lock = threading.Lock()


def _validate_cookie_domain(value: str) -> str:
    """Validate an explicit cookie Domain attribute; empty means host-only."""
    domain = value[1:] if value.startswith(".") else value
    if (
        value.lower() == "auto"
        or value != value.strip()
        or not domain
        or any(char in value for char in ":/?#@[]\\")
        or not host_is_valid(domain, allow_ip=False)
    ):
        raise RuntimeError(
            "FLASK_SESSION_COOKIE_DOMAIN must be empty for host-only cookies or a valid cookie domain"
        )
    return value


def _trusted_proxy_hops() -> int:
    raw_value = os.environ.get("TRUSTED_PROXY_HOPS", get_default("TRUSTED_PROXY_HOPS"))
    try:
        hops = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("TRUSTED_PROXY_HOPS must be a non-negative integer") from exc
    if hops < 0:
        raise RuntimeError("TRUSTED_PROXY_HOPS must be a non-negative integer")
    return hops


class NAFFlask(Flask):
    """Flask app whose external URL generation can use the configured public origin."""

    def url_for(self, endpoint: str, **values) -> str:
        public_base_url = self.config.get("PUBLIC_BASE_URL")
        if not public_base_url:
            return super().url_for(endpoint, **values)

        explicit_external = values.get("_external")
        has_scheme = values.get("_scheme") is not None
        if explicit_external is False:
            return super().url_for(endpoint, **values)

        if has_request_context() and explicit_external is None and not has_scheme:
            # A configured SERVER_NAME enables outside-request URL generation;
            # preserve Flask's former request-context default of relative URLs.
            values["_external"] = False
            return super().url_for(endpoint, **values)

        should_be_external = (
            explicit_external is True
            or has_scheme
            or (explicit_external is None and not has_request_context())
        )
        if not should_be_external:
            return super().url_for(endpoint, **values)

        relative_values = dict(values)
        relative_values["_external"] = False
        relative_values.pop("_scheme", None)
        relative_url = super().url_for(endpoint, **relative_values)
        base = urlsplit(public_base_url)
        target = urlsplit(relative_url)
        return urlunsplit((base.scheme, base.netloc, target.path, target.query, target.fragment))

# Initialize CSRF protection globally
csrf = CSRFProtect()


def require_demo_pages(view):
    """Return 404 unless demo/design pages are enabled.

    Demo pages are a single feature flag (DEMO_PAGES_ENABLED); routing the check
    through one decorator means a new demo route can't accidentally ship without
    the guard.
    """
    from functools import wraps
    from flask import current_app, abort

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_app.config.get("DEMO_PAGES_ENABLED", False):
            abort(404)
        return view(*args, **kwargs)

    return wrapper


def _safe_getcwd(fallback: str = None) -> str:
    """Get current working directory, handling deletion gracefully.
    
    When gunicorn workers reload or the cwd is deleted, os.getcwd() raises OSError.
    This helper catches that and returns a fallback (typically __file__ parent).
    """
    try:
        return os.getcwd()
    except (OSError, FileNotFoundError):
        # Working directory was deleted or became inaccessible
        if fallback:
            return fallback
        # Use the location of this file as fallback
        # This file is in src/netcup_api_filter/app.py, so go up 3 levels to get to deploy root
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_app(config_path: str = "config.yaml") -> Flask:
    """
    Create and configure the Flask application.
    
    Args:
        config_path: Path to configuration file (legacy, may not be used)
        
    Returns:
        Configured Flask application instance
    """
    app = NAFFlask(__name__)

    trusted_proxy_hops = _trusted_proxy_hops()
    app.config["TRUSTED_PROXY_HOPS"] = trusted_proxy_hops
    if trusted_proxy_hops > 0:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=trusted_proxy_hops,
            x_proto=trusted_proxy_hops,
            x_host=0,
        )
    else:
        @app.before_request
        def warn_if_forwarded_headers_are_ignored():
            if not any(name.lower().startswith("x-forwarded-") for name in request.headers.keys()):
                return

            global _forwarded_header_warning_logged
            with _forwarded_header_warning_lock:
                if _forwarded_header_warning_logged:
                    return
                _forwarded_header_warning_logged = True
            logger.warning(
                "Forwarded headers are ignored because TRUSTED_PROXY_HOPS=0; "
                "set TRUSTED_PROXY_HOPS to the number of trusted proxies in front of this app."
            )

    public_base_url = get_configured_public_base_url()
    if public_base_url:
        parsed_public_base_url = urlsplit(public_base_url)
        scheme, authority = parsed_public_base_url.scheme, parsed_public_base_url.netloc
        app.config["PUBLIC_BASE_URL"] = public_base_url
        # SERVER_NAME enables URL building outside a request context. NAFFlask
        # keeps request-context links relative unless the caller asks for an
        # external URL, and then replaces the request origin with this origin.
        app.config["SERVER_NAME"] = authority
        app.config["PREFERRED_URL_SCHEME"] = scheme
    else:
        app.config["PUBLIC_BASE_URL"] = ""
        logger.warning(
            "PUBLIC_BASE_URL is unset; externally generated URLs use the request origin, "
            "so an untrusted Host can poison emailed links. Set PUBLIC_BASE_URL to the public origin."
        )
    
    # =========================================================================
    # Security Configuration
    # =========================================================================
    
    # Secret key for sessions/CSRF. Single rule for every entry point (Passenger,
    # OCI image, ciu app stack, e2e instance, unit tests):
    #   1. SECRET_KEY_FILE (a mounted secret, e.g. a ciu GEN_LOCAL secret) or the
    #      SECRET_KEY environment variable (not both; must not be trivially short);
    #   2. otherwise the database-persisted key, created race-free on first start
    #      (database.ensure_persisted_secret_key, finalized right after init_db).
    flask_env = os.environ.get('FLASK_ENV', '')
    env_secret_key = os.environ.get('SECRET_KEY', '')
    secret_key_file = os.environ.get('SECRET_KEY_FILE', '').strip()
    if secret_key_file:
        if env_secret_key:
            raise RuntimeError("Set only one of SECRET_KEY and SECRET_KEY_FILE")
        try:
            with open(secret_key_file, encoding='utf-8') as handle:
                env_secret_key = handle.read().strip()
        except OSError as exc:
            raise RuntimeError(f"SECRET_KEY_FILE is not readable: {secret_key_file}") from exc
    if env_secret_key and len(env_secret_key) < 16:
        raise RuntimeError(
            "SECRET_KEY is set but shorter than 16 characters. "
            "Generate one with: openssl rand -hex 32 (or unset it to use the persisted key)"
        )
    app.config['SECRET_KEY'] = env_secret_key or None
    
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
    
    # Empty is host-only. A configured domain is explicit and validated.
    domain_setting = os.environ.get(
        'FLASK_SESSION_COOKIE_DOMAIN',
        get_default('FLASK_SESSION_COOKIE_DOMAIN'),
    )
    if domain_setting:
        app.config['SESSION_COOKIE_DOMAIN'] = _validate_cookie_domain(domain_setting)
        logger.info("Session cookies use an explicitly configured domain.")
    
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
    cwd = _safe_getcwd()
    deploy_templates = os.path.join(cwd, 'src', 'netcup_api_filter', 'templates')
    deploy_static = os.path.join(cwd, 'src', 'netcup_api_filter', 'static')
    
    # Check various possible locations
    for templates_path in [
        deploy_templates,
        os.path.join(cwd, 'deploy', 'src', 'netcup_api_filter', 'templates'),
        os.path.join(cwd, 'templates'),
    ]:
        if os.path.exists(templates_path):
            app.template_folder = templates_path
            break
    
    for static_path in [
        deploy_static,
        os.path.join(cwd, 'deploy', 'src', 'netcup_api_filter', 'static'),
        os.path.join(cwd, 'static'),
    ]:
        if os.path.exists(static_path):
            app.static_folder = static_path
            break
    
    # =========================================================================
    # Database Initialization
    # =========================================================================
    
    init_db(app)

    if not app.config['SECRET_KEY']:
        from .database import ensure_persisted_secret_key
        with app.app_context():
            app.config['SECRET_KEY'] = ensure_persisted_secret_key()
        logger.info("SECRET_KEY: using the database-persisted key (no SECRET_KEY env var)")

    # =========================================================================
    # Feature Flags (config-driven)
    # =========================================================================

    # Demo/design pages can be disabled in production to reduce surface area.
    # Priority:
    # 1) Environment variable override (DEMO_PAGES_ENABLED)
    # 2) Settings table key: enable_demo_pages (seeded at build time)
    # 3) Default: disabled (safe)
    demo_pages_enabled_env = os.environ.get("DEMO_PAGES_ENABLED")
    if demo_pages_enabled_env is not None:
        demo_pages_enabled = parse_bool(demo_pages_enabled_env, default=False)
    else:
        from .database import get_setting

        with app.app_context():
            demo_pages_enabled = parse_bool(get_setting("enable_demo_pages"), default=False)

    app.config["DEMO_PAGES_ENABLED"] = demo_pages_enabled
    logger.info(f"Demo pages enabled: {demo_pages_enabled}")
    
    # Create startup timestamp file for uptime tracking
    try:
        db_path = os.environ.get('NETCUP_FILTER_DB_PATH', 'netcup_filter.db')
        startup_file = os.path.join(os.path.dirname(os.path.abspath(db_path)), '.app_startup')
        # Touch the file to update its modification time
        with open(startup_file, 'w') as f:
            from datetime import datetime
            f.write(datetime.now().isoformat())
    except Exception:
        pass  # Non-critical feature, don't fail startup
    
    # =========================================================================
    # CSRF Protection
    # =========================================================================
    
    csrf.init_app(app)
    
    # Exempt API endpoints from CSRF (they use Bearer tokens)
    csrf.exempt(dns_api_bp)
    csrf.exempt(ddns_protocols_bp)
    # Bot callbacks authenticate with a shared secret header, not cookies.
    csrf.exempt(telegram_bp)
    
    # =========================================================================
    # Rate Limiting
    # =========================================================================
    
    flask_env = os.environ.get('FLASK_ENV', 'production')
    
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        from .database import get_setting
        
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
            
        # Apply rate limiting to admin and account routes
        # Priority: 1. Database settings, 2. Environment variables, 3. Hardcoded defaults
        with app.app_context():
            admin_rate_limit = get_setting('admin_rate_limit') or os.environ.get('ADMIN_RATE_LIMIT', '50 per minute')
            account_rate_limit = get_setting('account_rate_limit') or os.environ.get('ACCOUNT_RATE_LIMIT', '50 per minute')
            api_rate_limit = get_setting('api_rate_limit') or os.environ.get('API_RATE_LIMIT', '60 per minute')
        limiter.limit(admin_rate_limit)(admin_bp)
        limiter.limit(account_rate_limit)(account_bp)
        # The Telegram bot->app callback is unauthenticated apart from a shared
        # secret; rate-limit it so the secret can't be brute-forced/timed at will.
        limiter.limit(api_rate_limit)(telegram_bp)
        # Bearer-token DNS/DDNS API: cap per-IP request rate so a stolen or
        # misbehaving token can't hammer the provider backend.
        limiter.limit(api_rate_limit)(dns_api_bp)
        limiter.limit(api_rate_limit)(ddns_protocols_bp)

        logger.info(
            f"Rate limiting enabled: admin={admin_rate_limit}, "
            f"account={account_rate_limit}, api={api_rate_limit}"
        )
    except ImportError:
        logger.warning("Flask-Limiter not available - rate limiting disabled")
    
    # =========================================================================
    # Register Blueprints
    # =========================================================================
    
    app.register_blueprint(admin_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(dns_api_bp)
    app.register_blueprint(ddns_protocols_bp)
    app.register_blueprint(telegram_bp)
    
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
    def inject_public_base_url():
        configured_origin = app.config['PUBLIC_BASE_URL']
        if configured_origin:
            return {'public_base_url': f"{configured_origin}/"}
        return {'public_base_url': request.url_root}
    
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
    # Security Headers
    # =========================================================================
    
    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses.
        
        These headers protect against common web vulnerabilities:
        - X-Frame-Options: Prevents clickjacking attacks
        - X-Content-Type-Options: Prevents MIME-type sniffing
        - X-XSS-Protection: Enables browser XSS filter (legacy browsers)
        - Referrer-Policy: Controls referrer information leakage
        - Permissions-Policy: Restricts browser features
        """
        # Prevent clickjacking - page cannot be embedded in frames
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        
        # Prevent MIME type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # Enable XSS filter in browsers
        # Note: This header is deprecated in modern browsers in favor of CSP,
        # but is kept for legacy browser support (IE, older Edge).
        # Modern browsers ignore this header when CSP is present.
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Control referrer information sent with requests
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Restrict browser features (modern replacement for many headers)
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
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
    @require_demo_pages
    def theme_demo():
        """Theme demo page for previewing all UI themes."""
        from flask import send_from_directory
        return send_from_directory('demos/theme-demo', 'index.html')

    @app.route('/component-demo')
    @require_demo_pages
    def component_demo():
        """Component demo page for design system reference (custom CSS)."""
        from flask import send_from_directory
        return send_from_directory('demos/component-demo', 'index.html')

    @app.route('/component-demo-bs5')
    @require_demo_pages
    def component_demo_bs5():
        """Component demo page using Bootstrap 5 theming."""
        from flask import send_from_directory
        return send_from_directory('demos/component-demo-bs5', 'index.html')

    @app.route('/theme-demo2')
    @require_demo_pages
    def theme_demo2():
        """Theme demo v2 with 17 themes for CSS comparison."""
        from flask import send_from_directory
        return send_from_directory(
            'demos/theme-demo2',
            'Theme Demo - Netcup API Filter.html'
        )

    @app.route('/theme-demo2/<path:filename>')
    @require_demo_pages
    def theme_demo2_static(filename):
        """Serve static assets for theme demo v2."""
        from flask import send_from_directory
        return send_from_directory('demos/theme-demo2', filename)
    
    logger.info("Flask application created successfully")
    
    return app

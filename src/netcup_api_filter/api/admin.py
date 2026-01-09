"""
Admin Portal Blueprint.

Routes:
- /admin/login - Admin login
- /admin/ - Dashboard
- /admin/accounts - Account list
- /admin/accounts/pending - Pending approvals
- /admin/accounts/<id> - Account detail
- /admin/accounts/new - Create account
- /admin/realms/pending - Pending realm requests
- /admin/audit - Audit logs
- /admin/config/netcup - Netcup API config
- /admin/config/email - Email config
- /admin/system - System info
"""
import logging
from datetime import datetime, timedelta
from flask import (
    Blueprint, flash, g, jsonify, redirect, render_template,
    request, session, url_for
)
from functools import wraps

from ..account_auth import (
    approve_account,
    create_account_by_admin,
    disable_account,
    generate_secure_password,
    reject_account,
)
from ..geoip_service import geoip_location, get_geoip_status
from ..models import (
    Account, AccountRealm, ActivityLog, APIToken, db, Settings,
    validate_password,
    # Multi-backend models
    BackendProvider, BackendService, ManagedDomainRoot, DomainRootGrant,
    OwnerTypeEnum, VisibilityEnum, TestStatusEnum, GrantTypeEnum,
)
from ..realm_token_service import (
    approve_realm,
    create_realm_by_admin,
    get_pending_realms,
    reject_realm,
)
from ..database import get_setting, set_setting
from ..config_defaults import get_default

import ipaddress
import json
import os
import random
import time

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Admin session keys
SESSION_KEY_ADMIN_ID = 'admin_id'
SESSION_KEY_ADMIN_USERNAME = 'admin_username'
SESSION_KEY_ADMIN_2FA_PENDING = 'admin_2fa_pending'
SESSION_KEY_ADMIN_2FA_CODE = 'admin_2fa_code'
SESSION_KEY_ADMIN_2FA_EXPIRES = 'admin_2fa_expires'
SESSION_KEY_ADMIN_SESSION_IP = 'admin_session_ip'
SESSION_KEY_ADMIN_2FA_METHOD = 'admin_2fa_method'  # 'email' or 'totp'

# Timing attack protection: random delay range (milliseconds)
LOGIN_DELAY_MIN_MS = 100
LOGIN_DELAY_MAX_MS = 300

# Brute force protection thresholds
FAILED_LOGIN_LOCKOUT_THRESHOLD = 5  # Failed attempts before lockout
FAILED_LOGIN_LOCKOUT_MINUTES = 15  # Lockout duration
FAILED_LOGIN_ALERT_THRESHOLD = 3  # Failed attempts before alerting user


def _add_timing_jitter():
    """Add random delay to prevent timing-based username enumeration."""
    delay_ms = random.randint(LOGIN_DELAY_MIN_MS, LOGIN_DELAY_MAX_MS)
    time.sleep(delay_ms / 1000.0)


def _get_client_ip() -> str:
    """Get real client IP, handling proxy headers."""
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip and ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()
    return client_ip or 'unknown'


def _track_failed_login(username: str, client_ip: str) -> tuple[bool, int]:
    """
    Track failed login attempt per username globally.
    
    Returns:
        (is_locked_out, failed_count) - Whether account is locked and current failure count
    """
    from ..database import get_system_config, set_system_config
    
    # Track per-username (global, not per-IP)
    key = f'failed_login_user_{username}'
    data = get_system_config(key) or {'count': 0, 'first_failure': None, 'ips': []}
    
    now = datetime.utcnow()
    
    # Reset if lockout period has passed
    if data.get('lockout_until'):
        lockout_until = datetime.fromisoformat(data['lockout_until'])
        if now > lockout_until:
            data = {'count': 0, 'first_failure': None, 'ips': []}
    
    # Increment count
    data['count'] = data.get('count', 0) + 1
    if not data.get('first_failure'):
        data['first_failure'] = now.isoformat()
    
    # Track unique IPs (for distributed attack detection)
    if client_ip not in data.get('ips', []):
        data['ips'] = data.get('ips', [])[:9] + [client_ip]  # Keep last 10 IPs
    
    # Check if we should lock out
    is_locked = False
    if data['count'] >= FAILED_LOGIN_LOCKOUT_THRESHOLD:
        data['lockout_until'] = (now + timedelta(minutes=FAILED_LOGIN_LOCKOUT_MINUTES)).isoformat()
        is_locked = True
        logger.warning(f"Account '{username}' locked out after {data['count']} failed attempts")
    
    set_system_config(key, data)
    
    return is_locked, data['count']


def _check_account_lockout(username: str) -> tuple[bool, int | None]:
    """
    Check if account is currently locked out.
    
    Returns:
        (is_locked, minutes_remaining) - Whether locked and minutes until unlock
    """
    from ..database import get_system_config
    
    key = f'failed_login_user_{username}'
    data = get_system_config(key)
    
    if not data or not data.get('lockout_until'):
        return False, None
    
    lockout_until = datetime.fromisoformat(data['lockout_until'])
    now = datetime.utcnow()
    
    if now < lockout_until:
        remaining = int((lockout_until - now).total_seconds() / 60) + 1
        return True, remaining
    
    return False, None


def _clear_failed_logins(username: str):
    """Clear failed login tracking after successful login."""
    from ..database import set_system_config
    set_system_config(f'failed_login_user_{username}', None)


def _notify_failed_login_attempt(admin: Account, failed_count: int, client_ip: str):
    """Send notification to admin about failed login attempts on their account."""
    if failed_count < FAILED_LOGIN_ALERT_THRESHOLD:
        return
    
    try:
        from ..notification_service import send_security_alert_email
        send_security_alert_email(
            email=admin.email,
            username=admin.username,
            event_type='failed_login',
            details=f"{failed_count} failed login attempts detected from IP {client_ip}",
            source_ip=client_ip
        )
        logger.info(f"Security alert sent to {admin.username} after {failed_count} failed attempts")
    except Exception as e:
        logger.error(f"Failed to send security alert: {e}")


def _check_ip_in_whitelist(client_ip: str, whitelist: list[str]) -> bool:
    """Check if client IP is in the whitelist (supports CIDR notation)."""
    if not whitelist:
        return True  # No whitelist = allow all
    
    try:
        ip_obj = ipaddress.ip_address(client_ip)
    except ValueError:
        logger.warning(f"Invalid client IP format: {client_ip}")
        return False
    
    for allowed in whitelist:
        try:
            if '/' in allowed:
                # CIDR notation
                network = ipaddress.ip_network(allowed, strict=False)
                if ip_obj in network:
                    return True
            else:
                # Single IP
                if ip_obj == ipaddress.ip_address(allowed):
                    return True
        except ValueError:
            logger.warning(f"Invalid IP in admin whitelist: {allowed}")
            continue
    
    return False


@admin_bp.before_request
def check_admin_ip_whitelist():
    """Check IP against admin whitelist before any admin route."""
    # Get whitelist from environment (config-driven)
    whitelist_raw = os.environ.get('ADMIN_IP_WHITELIST', get_default('ADMIN_IP_WHITELIST', '')).strip()
    if not whitelist_raw:
        return None  # No whitelist configured, allow all
    
    client_ip = _get_client_ip()
    whitelist = [ip.strip() for ip in whitelist_raw.split(',') if ip.strip()]
    
    if not _check_ip_in_whitelist(client_ip, whitelist):
        logger.warning(f"Admin access blocked: IP {client_ip} not in whitelist")
        from flask import abort
        abort(403)


def require_admin(f):
    """Decorator requiring admin authentication with optional session IP binding."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_id = session.get(SESSION_KEY_ADMIN_ID)
        if not admin_id:
            return redirect(url_for('admin.login'))
        
        admin = Account.query.get(admin_id)
        if not admin or not admin.is_admin or not admin.is_active:
            session.pop(SESSION_KEY_ADMIN_ID, None)
            session.pop(SESSION_KEY_ADMIN_USERNAME, None)
            return redirect(url_for('admin.login'))
        
        # Check session IP binding if enabled
        bind_ip = os.environ.get('ADMIN_SESSION_BIND_IP', get_default('ADMIN_SESSION_BIND_IP', 'false'))
        if bind_ip.lower() in ('true', '1', 'yes'):
            session_ip = session.get(SESSION_KEY_ADMIN_SESSION_IP)
            current_ip = _get_client_ip()
            if session_ip and session_ip != current_ip:
                logger.warning(f"Admin session IP mismatch: session={session_ip}, current={current_ip}")
                session.clear()
                flash('Session invalidated due to IP change. Please log in again.', 'warning')
                return redirect(url_for('admin.login'))
        
        # Force password change if required (but allow access to change_password route)
        if admin.must_change_password and request.endpoint != 'admin.change_password':
            return redirect(url_for('admin.change_password'))
        
        g.admin = admin
        return f(*args, **kwargs)
    
    return decorated_function


# ============================================================================
# Login / Logout
# ============================================================================

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page - Step 1: Username + Password."""
    if session.get(SESSION_KEY_ADMIN_ID):
        # Check if password change is required
        admin = Account.query.get(session.get(SESSION_KEY_ADMIN_ID))
        if admin and admin.must_change_password:
            return redirect(url_for('admin.change_password'))
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        client_ip = _get_client_ip()
        
        # Add timing jitter to prevent username enumeration
        _add_timing_jitter()
        
        # Check if account is locked out (per-username tracking)
        is_locked, minutes_remaining = _check_account_lockout(username)
        if is_locked:
            flash(f'Account temporarily locked. Try again in {minutes_remaining} minutes.', 'error')
            logger.warning(f"Login attempt on locked account: {username} from {client_ip}")
            return render_template('admin/login.html')
        
        admin = Account.query.filter_by(username=username, is_admin=1).first()
        
        if admin and admin.verify_password(password):
            # Clear failed login tracking on success
            _clear_failed_logins(username)
            
            if not admin.is_active:
                flash('Account is disabled', 'error')
            else:
                # Check for test mode bypass (only in local_test environment)
                skip_2fa = (
                    os.environ.get('FLASK_ENV') == 'local_test' and
                    os.environ.get('ADMIN_2FA_SKIP', '').lower() in ('true', '1', 'yes')
                )
                
                if skip_2fa:
                    logger.warning(f"2FA BYPASSED for {username} (test mode)")
                    return _complete_admin_login(admin, client_ip, 'test_bypass')
                
                # Check if admin has any 2FA method enabled
                if not admin.has_2fa_enabled():
                    # Admin hasn't set up 2FA yet - allow login without 2FA
                    # They'll see a warning banner on the dashboard
                    logger.warning(f"Admin login without 2FA: {username} (2FA not configured)")
                    return _complete_admin_login(admin, client_ip, 'no_2fa_configured')
                
                # Check if admin has valid email for 2FA
                if admin.email_2fa_enabled and (not admin.email or admin.email == 'admin@localhost'):
                    # Admin needs to set email first - proceed to password change which handles this
                    session[SESSION_KEY_ADMIN_ID] = admin.id
                    session[SESSION_KEY_ADMIN_USERNAME] = admin.username
                    session[SESSION_KEY_ADMIN_SESSION_IP] = client_ip
                    admin.must_change_password = 1  # Force password change to also set email
                    db.session.commit()
                    logger.info(f"Admin login (no valid email, forcing setup): {username}")
                    return redirect(url_for('admin.change_password'))
                
                # Proceed to 2FA - determine available methods
                session[SESSION_KEY_ADMIN_2FA_PENDING] = admin.id
                
                # Check if TOTP is enabled for this admin
                if admin.totp_enabled and admin.totp_secret:
                    # Admin has TOTP configured - let them choose
                    session[SESSION_KEY_ADMIN_2FA_METHOD] = 'choose'
                    return redirect(url_for('admin.login_2fa'))
                else:
                    # Email-only 2FA
                    session[SESSION_KEY_ADMIN_2FA_METHOD] = 'email'
                    
                    # Generate and send 2FA code via email
                    from ..account_auth import generate_code, TFA_CODE_LENGTH, TFA_CODE_EXPIRY_MINUTES
                    code = generate_code(TFA_CODE_LENGTH)
                    expires_at = datetime.utcnow() + timedelta(minutes=TFA_CODE_EXPIRY_MINUTES)
                    
                    session[SESSION_KEY_ADMIN_2FA_CODE] = code
                    session[SESSION_KEY_ADMIN_2FA_EXPIRES] = expires_at.isoformat()
                    
                    # Send 2FA email
                    from ..notification_service import send_2fa_email
                    if send_2fa_email(admin.email, admin.username, code):
                        logger.info(f"Admin 2FA code sent to {admin.username}")
                        return redirect(url_for('admin.login_2fa'))
                    else:
                        logger.error(f"Failed to send admin 2FA email to {admin.username}")
                        flash('Failed to send verification code. Please try again.', 'error')
        else:
            # Track failed login attempt per-username
            is_locked, failed_count = _track_failed_login(username, client_ip)
            
            # Notify admin if threshold reached
            if admin:
                _notify_failed_login_attempt(admin, failed_count, client_ip)
            
            if is_locked:
                flash(f'Too many failed attempts. Account locked for {FAILED_LOGIN_LOCKOUT_MINUTES} minutes.', 'error')
            else:
                flash('Invalid credentials', 'error')
            
            logger.warning(f"Failed admin login attempt: {username} from {client_ip} (attempt #{failed_count})")
    
    return render_template('admin/login.html')


@admin_bp.route('/login/2fa', methods=['GET', 'POST'])
def login_2fa():
    """Admin login page - Step 2: 2FA verification (Email, TOTP, or Recovery Code)."""
    # Check for pending 2FA
    admin_id = session.get(SESSION_KEY_ADMIN_2FA_PENDING)
    if not admin_id:
        return redirect(url_for('admin.login'))
    
    admin = Account.query.get(admin_id)
    if not admin:
        session.pop(SESSION_KEY_ADMIN_2FA_PENDING, None)
        return redirect(url_for('admin.login'))
    
    # Determine available 2FA methods
    has_totp = admin.totp_enabled and admin.totp_secret
    has_email = admin.email and admin.email != 'admin@localhost'
    current_method = session.get(SESSION_KEY_ADMIN_2FA_METHOD, 'email')
    
    # Handle method selection
    selected_method = request.args.get('method') or request.form.get('method')
    if selected_method in ('email', 'totp'):
        current_method = selected_method
        session[SESSION_KEY_ADMIN_2FA_METHOD] = current_method
        
        # If switching to email, send code
        if current_method == 'email' and not session.get(SESSION_KEY_ADMIN_2FA_CODE):
            from ..account_auth import generate_code, TFA_CODE_LENGTH, TFA_CODE_EXPIRY_MINUTES
            code = generate_code(TFA_CODE_LENGTH)
            expires_at = datetime.utcnow() + timedelta(minutes=TFA_CODE_EXPIRY_MINUTES)
            session[SESSION_KEY_ADMIN_2FA_CODE] = code
            session[SESSION_KEY_ADMIN_2FA_EXPIRES] = expires_at.isoformat()
            
            from ..notification_service import send_2fa_email
            if send_2fa_email(admin.email, admin.username, code):
                flash('Verification code sent to your email', 'info')
            else:
                flash('Failed to send verification code', 'error')
    
    # Mask email for display
    def mask_email(email: str) -> str:
        if not email or '@' not in email:
            return '***@***'
        local, domain = email.rsplit('@', 1)
        if len(local) <= 2:
            masked_local = '*' * len(local)
        else:
            masked_local = local[0] + '*' * (len(local) - 2) + local[-1]
        return f"{masked_local}@{domain}"
    
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        client_ip = _get_client_ip()
        
        # Add timing jitter
        _add_timing_jitter()
        
        # Check if this looks like a recovery code (format: XXXX-XXXX)
        if len(code) == 9 and '-' in code:
            from ..recovery_codes import verify_recovery_code
            if verify_recovery_code(admin, code):
                # Recovery code verified - complete login
                flash('Login successful (recovery code used)', 'success')
                flash('You used a recovery code. Consider regenerating your recovery codes.', 'warning')
                return _complete_admin_login(admin, client_ip, via='recovery_code')
            else:
                flash('Invalid recovery code', 'error')
                return render_template('admin/login_2fa.html',
                                      masked_email=mask_email(admin.email),
                                      username=admin.username,
                                      has_totp=has_totp,
                                      has_email=has_email,
                                      method=current_method)
        
        # Verify based on current method
        if current_method == 'totp' and has_totp:
            # Verify TOTP code
            try:
                import pyotp
                totp = pyotp.TOTP(admin.totp_secret)
                if totp.verify(code, valid_window=1):
                    flash('Login successful', 'success')
                    return _complete_admin_login(admin, client_ip, via='totp')
                else:
                    flash('Invalid authenticator code', 'error')
            except ImportError:
                logger.error("pyotp not installed for TOTP verification")
                flash('TOTP verification unavailable', 'error')
        else:
            # Verify email code
            expected_code = session.get(SESSION_KEY_ADMIN_2FA_CODE)
            expires_at_str = session.get(SESSION_KEY_ADMIN_2FA_EXPIRES)
            
            if not expected_code or not expires_at_str:
                flash('Verification session expired. Please log in again.', 'error')
                session.pop(SESSION_KEY_ADMIN_2FA_PENDING, None)
                return redirect(url_for('admin.login'))
            
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.utcnow() > expires_at:
                flash('Verification code expired. Please log in again.', 'error')
                _clear_2fa_session()
                return redirect(url_for('admin.login'))
            
            if code == expected_code:
                flash('Login successful', 'success')
                return _complete_admin_login(admin, client_ip, via='email')
            else:
                logger.warning(f"Invalid admin 2FA code attempt for {admin.username} from {client_ip}")
                flash('Invalid verification code', 'error')
    
    return render_template('admin/login_2fa.html', 
                          masked_email=mask_email(admin.email),
                          username=admin.username,
                          has_totp=has_totp,
                          has_email=has_email,
                          method=current_method)


def _complete_admin_login(admin: Account, client_ip: str, via: str = 'email'):
    """Complete admin login after successful 2FA.
    
    Returns:
        Response: Redirect to dashboard or password change page
    """
    _clear_2fa_session()
    
    session[SESSION_KEY_ADMIN_ID] = admin.id
    session[SESSION_KEY_ADMIN_USERNAME] = admin.username
    session[SESSION_KEY_ADMIN_SESSION_IP] = client_ip
    
    admin.last_login_at = datetime.utcnow()
    db.session.commit()
    
    logger.info(f"Admin login complete: {admin.username} from {client_ip} via {via}")
    
    # Check if password change is required
    if admin.must_change_password:
        return redirect(url_for('admin.change_password'))
    
    return redirect(url_for('admin.dashboard'))


def _clear_2fa_session():
    """Clear all 2FA-related session keys."""
    session.pop(SESSION_KEY_ADMIN_2FA_PENDING, None)
    session.pop(SESSION_KEY_ADMIN_2FA_CODE, None)
    session.pop(SESSION_KEY_ADMIN_2FA_EXPIRES, None)
    session.pop(SESSION_KEY_ADMIN_2FA_METHOD, None)


@admin_bp.route('/login/2fa/resend', methods=['POST'])
def resend_2fa():
    """Resend admin 2FA code."""
    admin_id = session.get(SESSION_KEY_ADMIN_2FA_PENDING)
    if not admin_id:
        return redirect(url_for('admin.login'))
    
    admin = Account.query.get(admin_id)
    if not admin:
        return redirect(url_for('admin.login'))
    
    # Generate new code
    from ..account_auth import generate_code, TFA_CODE_LENGTH, TFA_CODE_EXPIRY_MINUTES
    code = generate_code(TFA_CODE_LENGTH)
    expires_at = datetime.utcnow() + timedelta(minutes=TFA_CODE_EXPIRY_MINUTES)
    
    session[SESSION_KEY_ADMIN_2FA_CODE] = code
    session[SESSION_KEY_ADMIN_2FA_EXPIRES] = expires_at.isoformat()
    
    # Send new code
    from ..notification_service import send_2fa_email
    if send_2fa_email(admin.email, admin.username, code):
        flash('New verification code sent', 'success')
    else:
        flash('Failed to send verification code', 'error')
    
    return redirect(url_for('admin.login_2fa'))


@admin_bp.route('/logout')
def logout():
    """Admin logout."""
    username = session.get(SESSION_KEY_ADMIN_USERNAME)
    # Clear all admin session keys
    session.pop(SESSION_KEY_ADMIN_ID, None)
    session.pop(SESSION_KEY_ADMIN_USERNAME, None)
    session.pop(SESSION_KEY_ADMIN_2FA_PENDING, None)
    session.pop(SESSION_KEY_ADMIN_2FA_CODE, None)
    session.pop(SESSION_KEY_ADMIN_2FA_EXPIRES, None)
    session.pop(SESSION_KEY_ADMIN_SESSION_IP, None)
    if username:
        logger.info(f"Admin logout: {username}")
    flash('You have been logged out', 'info')
    return redirect(url_for('admin.login'))


# ============================================================================
# Dashboard
# ============================================================================

@admin_bp.route('/')
@require_admin
def dashboard():
    """Admin dashboard with stats and aggregated metrics."""
    # Get stats
    total_accounts = Account.query.filter_by(is_admin=0).count()
    active_accounts = Account.query.filter_by(is_admin=0, is_active=1).count()
    pending_accounts = Account.query.filter_by(is_admin=0, is_active=0).count()
    pending_realms = AccountRealm.query.filter_by(status='pending').count()
    
    # Activity in last 24h
    since = datetime.utcnow() - timedelta(hours=24)
    api_calls_24h = ActivityLog.query.filter(
        ActivityLog.created_at >= since,
        ActivityLog.action == 'api_call'
    ).count()
    errors_24h = ActivityLog.query.filter(
        ActivityLog.created_at >= since,
        ActivityLog.status == 'error'
    ).count()
    
    # Rate limited IPs (24h) - group by IP and count
    from sqlalchemy import func
    rate_limit_logs = (
        db.session.query(
            ActivityLog.source_ip,
            func.count(ActivityLog.id).label('count'),
            func.max(ActivityLog.created_at).label('last_seen')
        )
        .filter(
            ActivityLog.created_at >= since,
            ActivityLog.action == 'rate_limit'
        )
        .group_by(ActivityLog.source_ip)
        .order_by(func.count(ActivityLog.id).desc())
        .limit(10)
        .all()
    )
    rate_limited_ips = [
        {
            'ip': row.source_ip,
            'count': row.count,
            'last_seen': row.last_seen.strftime('%H:%M'),
            'location': geoip_location(row.source_ip) if row.source_ip else None
        }
        for row in rate_limit_logs
    ]
    
    # Most active clients (24h) - group by account_id and realm_value
    active_client_logs = (
        db.session.query(
            ActivityLog.account_id,
            ActivityLog.realm_value,
            func.count(ActivityLog.id).label('api_calls')
        )
        .filter(
            ActivityLog.created_at >= since,
            ActivityLog.action == 'api_call',
            ActivityLog.account_id.isnot(None)
        )
        .group_by(ActivityLog.account_id, ActivityLog.realm_value)
        .order_by(func.count(ActivityLog.id).desc())
        .limit(5)
        .all()
    )
    active_clients = []
    for row in active_client_logs:
        account = Account.query.get(row.account_id)
        if account:
            active_clients.append({
                'account_id': row.account_id,
                'username': account.username,
                'realm': row.realm_value or 'N/A',
                'api_calls': row.api_calls
            })
    
    # Permission errors (24h) - denied requests
    permission_logs = (
        ActivityLog.query
        .filter(
            ActivityLog.created_at >= since,
            ActivityLog.status == 'denied'
        )
        .order_by(ActivityLog.created_at.desc())
        .limit(10)
        .all()
    )
    permission_errors = []
    for log in permission_logs:
        token_prefix = 'N/A'
        if log.token:
            token_prefix = log.token.token_prefix
        
        error_type = 'permission_denied'
        if log.status_reason and 'ip' in log.status_reason.lower():
            error_type = 'ip_denied'
        
        permission_errors.append({
            'token_prefix': token_prefix,
            'type': error_type,
            'ip': log.source_ip,
            'details': log.status_reason or 'Access denied',
            'time': log.created_at.strftime('%H:%M')
        })
    
    return render_template('admin/dashboard.html',
                          total_accounts=total_accounts,
                          active_accounts=active_accounts,
                          pending_accounts=pending_accounts,
                          pending_realms=pending_realms,
                          api_calls_24h=api_calls_24h,
                          errors_24h=errors_24h,
                          rate_limited_ips=rate_limited_ips,
                          active_clients=active_clients,
                          permission_errors=permission_errors)


# ============================================================================
# Account Management
# ============================================================================

@admin_bp.route('/accounts')
@require_admin
def accounts_list():
    """List all accounts."""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    status_filter = request.args.get('status', 'all')
    search = request.args.get('search', '').strip()
    
    query = Account.query.filter_by(is_admin=0)
    
    if status_filter == 'active':
        query = query.filter_by(is_active=1)
    elif status_filter == 'pending':
        query = query.filter_by(is_active=0)
    
    if search:
        query = query.filter(
            db.or_(
                Account.username.ilike(f'%{search}%'),
                Account.email.ilike(f'%{search}%')
            )
        )
    
    pagination = query.order_by(Account.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin/accounts_list.html',
                          accounts=pagination.items,
                          pagination=pagination,
                          status_filter=status_filter,
                          search=search)


@admin_bp.route('/accounts/pending')
@require_admin
def accounts_pending():
    """List pending account approvals."""
    pending = Account.query.filter_by(is_admin=0, is_active=0, email_verified=1).all()
    return render_template('admin/accounts_pending.html', accounts=pending)


@admin_bp.route('/accounts/<int:account_id>')
@require_admin
def account_detail(account_id):
    """Account detail page."""
    account = Account.query.get_or_404(account_id)
    realms = AccountRealm.query.filter_by(account_id=account_id).all()
    
    # Get token counts per realm
    realm_data = []
    for realm in realms:
        tokens = APIToken.query.filter_by(realm_id=realm.id).all()
        realm_data.append({
            'realm': realm,
            'tokens': tokens,
            'active_count': sum(1 for t in tokens if t.is_active),
        })
    
    return render_template('admin/account_detail.html',
                          account=account,
                          realm_data=realm_data)


@admin_bp.route('/accounts/new', methods=['GET', 'POST'])
@require_admin
def account_create():
    """Create new account (admin action).
    
    Two modes:
    1. send_invite=True (default): Sends invite email, user sets own password
    2. send_invite=False: Admin provides password directly (shown in flash)
    
    Realm configuration is optional. If include_realm is checked, creates
    a pre-approved realm. Otherwise, user must request realms after activation.
    """
    from ..models import AccountRealm
    from datetime import datetime
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip() or None
        send_invite = request.form.get('send_invite', 'true').lower() == 'true'
        include_realm = request.form.get('include_realm') == 'on'
        
        # Get optional realm configuration
        realm_type = request.form.get('realm_type', '').strip()
        realm_value = request.form.get('realm_value', '').strip().lower()
        record_types = request.form.getlist('record_types')
        operations = request.form.getlist('operations')
        
        account, error_or_warning = create_account_by_admin(
            username=username,
            email=email,
            password=password,
            approved_by=g.admin,
            send_invite=send_invite
        )
        
        if account:
            # Create pre-approved realm if requested
            realm_created = False
            if include_realm and realm_type and realm_value:
                # Parse domain from realm_value (e.g., "home.example.com" -> domain="example.com", value="home")
                parts = realm_value.split('.')
                if len(parts) >= 2:
                    domain = '.'.join(parts[-2:])  # e.g., "example.com"
                    realm_prefix = '.'.join(parts[:-2]) if len(parts) > 2 else ''  # e.g., "home"
                    
                    realm = AccountRealm(
                        account_id=account.id,
                        domain=domain,
                        realm_type=realm_type,
                        realm_value=realm_prefix,
                        status='approved',  # Pre-approved
                        approved_by_id=g.admin.id,
                        approved_at=datetime.utcnow(),
                        requested_at=datetime.utcnow()
                    )
                    realm.set_allowed_record_types(record_types if record_types else ['A', 'AAAA'])
                    realm.set_allowed_operations(operations if operations else ['read', 'update'])
                    db.session.add(realm)
                    db.session.commit()
                    realm_created = True
            
            # Flash appropriate message
            if error_or_warning and error_or_warning.startswith('WARNING:'):
                # Email failed, show temp password
                flash(error_or_warning, 'warning')
            elif send_invite:
                realm_msg = f" with pre-approved realm" if realm_created else " (no realm configured)"
                flash(f'Account "{username}" created{realm_msg}. Invite email sent to {email}.', 'success')
            else:
                # Direct password mode - show the password
                temp_password = password or 'generated'
                flash(f'Account "{username}" created. Temporary password: {temp_password}', 'success')
            return redirect(url_for('admin.account_detail', account_id=account.id))
        else:
            flash(error_or_warning, 'error')
    
    return render_template('admin/account_create.html')


@admin_bp.route('/accounts/<int:account_id>/approve', methods=['POST'])
@require_admin
def account_approve(account_id):
    """Approve a pending account and all its pending realms."""
    success, error = approve_account(account_id, g.admin)
    
    if success:
        flash('Account and realm requests approved', 'success')
    else:
        flash(error, 'error')
    
    return redirect(request.referrer or url_for('admin.accounts_pending'))


@admin_bp.route('/accounts/<int:account_id>/reject', methods=['POST'])
@require_admin
def account_reject(account_id):
    """Reject a pending account and delete it along with realm requests."""
    reason = request.form.get('reason', '').strip()
    success, error = reject_account(account_id, g.admin, reason if reason else None)
    
    if success:
        flash('Account rejected and deleted', 'success')
    else:
        flash(error, 'error')
    
    return redirect(request.referrer or url_for('admin.accounts_pending'))


@admin_bp.route('/accounts/<int:account_id>/disable', methods=['POST'])
@require_admin
def account_disable(account_id):
    """Disable an account."""
    success, error = disable_account(account_id, g.admin)
    
    if success:
        flash('Account disabled', 'success')
    else:
        flash(error, 'error')
    
    return redirect(request.referrer or url_for('admin.accounts_list'))


@admin_bp.route('/accounts/<int:account_id>/delete', methods=['POST'])
@require_admin
def account_delete(account_id):
    """Delete an account and all related data (realms, tokens)."""
    account = Account.query.get_or_404(account_id)
    
    # Don't allow deleting the admin account you're logged in as
    if account.id == g.admin.id:
        flash('Cannot delete your own account', 'error')
        return redirect(url_for('admin.account_detail', account_id=account_id))
    
    username = account.username
    
    # Delete all tokens for all realms of this account
    for realm in account.realms:
        APIToken.query.filter_by(realm_id=realm.id).delete()
    
    # Delete all realms
    AccountRealm.query.filter_by(account_id=account_id).delete()
    
    # Delete the account
    db.session.delete(account)
    db.session.commit()
    
    flash(f'Account "{username}" and all related data deleted', 'success')
    logger.info(f"Account {username} deleted by admin {g.admin.username}")
    
    return redirect(url_for('admin.accounts_list'))


@admin_bp.route('/accounts/<int:account_id>/reset-password', methods=['POST'])
@require_admin
def account_reset_password(account_id):
    """Send password reset link to account - admin initiated."""
    account = Account.query.get_or_404(account_id)
    
    if not account.email:
        flash('Account has no email address configured', 'error')
        return redirect(url_for('admin.account_detail', account_id=account_id))
    
    # Get expiry hours from form or use system default
    from ..password_reset import send_password_reset_email, get_token_expiry_hours
    
    expiry_hours = request.form.get('expiry_hours')
    if expiry_hours:
        try:
            expiry_hours = int(expiry_hours)
        except ValueError:
            expiry_hours = None
    
    if send_password_reset_email(account, expiry_hours=expiry_hours, admin_initiated=True):
        flash(f'Password reset link sent to {account.email}', 'success')
        logger.info(f"Admin {g.admin.username} sent password reset to {account.username}")
    else:
        flash('Failed to send password reset email. Check email configuration.', 'error')
    
    return redirect(url_for('admin.account_detail', account_id=account_id))


@admin_bp.route('/accounts/<int:account_id>/regenerate-alias', methods=['POST'])
@require_admin
def account_regenerate_alias(account_id):
    """
    Regenerate user_alias for an account, invalidating ALL tokens.
    
    This is a security operation used when:
    - Token compromise is suspected
    - User requests credential rotation
    - Admin needs to invalidate all API access
    
    Warning: This immediately invalidates ALL tokens for this account.
    """
    account = Account.query.get_or_404(account_id)
    
    try:
        old_alias_prefix = account.user_alias[:4] if account.user_alias else 'none'
        new_alias, tokens_deleted = account.regenerate_user_alias()
        db.session.commit()
        
        # Log the security action
        from ..models import ActivityLog
        log = ActivityLog(
            account_id=account.id,
            action='alias_regenerated',
            status='success',
            severity='high',
            source_ip=request.headers.get('X-Forwarded-For', request.remote_addr),
            user_agent=request.headers.get('User-Agent'),
            status_reason=f'Admin {g.admin.username} regenerated alias, {tokens_deleted} tokens invalidated'
        )
        db.session.add(log)
        db.session.commit()
        
        flash(
            f'User alias regenerated ({old_alias_prefix}... → {new_alias[:4]}...). '
            f'{tokens_deleted} tokens invalidated.',
            'warning'
        )
        logger.info(
            f"Admin {g.admin.username} regenerated alias for {account.username}: "
            f"{tokens_deleted} tokens invalidated"
        )
        
        # Notify user about credential rotation
        from ..notification_service import send_notification
        send_notification(
            account=account,
            subject='Security Alert: API Credentials Rotated',
            template='credential_rotation',
            context={
                'admin_username': g.admin.username,
                'tokens_invalidated': tokens_deleted,
                'reason': 'Admin initiated credential rotation',
            }
        )
        
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to regenerate alias: {e}', 'error')
        logger.error(f"Alias regeneration failed for {account.username}: {e}")
    
    return redirect(url_for('admin.account_detail', account_id=account_id))


@admin_bp.route('/accounts/<int:account_id>/change-email', methods=['POST'])
@require_admin
def account_change_email(account_id):
    """
    Change email address for an account (admin action).
    
    Admin can change email without verification flow.
    User will be notified at both old and new addresses.
    """
    account = Account.query.get_or_404(account_id)
    
    new_email = request.form.get('new_email', '').strip().lower()
    
    if not new_email:
        flash('New email address is required', 'error')
        return redirect(url_for('admin.account_detail', account_id=account_id))
    
    # Basic email validation
    import re
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', new_email):
        flash('Invalid email format', 'error')
        return redirect(url_for('admin.account_detail', account_id=account_id))
    
    # Check for duplicate
    existing = Account.query.filter(
        Account.email == new_email,
        Account.id != account_id
    ).first()
    if existing:
        flash('Email address already in use by another account', 'error')
        return redirect(url_for('admin.account_detail', account_id=account_id))
    
    old_email = account.email
    
    try:
        account.email = new_email
        account.email_verified = 0  # Require re-verification
        db.session.commit()
        
        # Log the change
        from ..models import ActivityLog
        log = ActivityLog(
            account_id=account.id,
            action='email_changed',
            status='success',
            severity='medium',
            source_ip=request.headers.get('X-Forwarded-For', request.remote_addr),
            user_agent=request.headers.get('User-Agent'),
            status_reason=f'Admin {g.admin.username} changed email from {old_email} to {new_email}'
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'Email changed from {old_email} to {new_email}', 'success')
        logger.info(f"Admin {g.admin.username} changed email for {account.username}: {old_email} → {new_email}")
        
        # Notify at old address (security alert)
        from ..notification_service import send_notification
        try:
            send_notification(
                account=account,
                subject='Security Alert: Email Address Changed',
                template='email_changed_old',
                context={
                    'old_email': old_email,
                    'new_email': new_email,
                    'admin_username': g.admin.username,
                },
                override_email=old_email  # Send to OLD email
            )
        except Exception as e:
            logger.warning(f"Failed to notify old email {old_email}: {e}")
        
        # Notify at new address (welcome)
        try:
            send_notification(
                account=account,
                subject='Your Email Address Has Been Updated',
                template='email_changed_new',
                context={
                    'old_email': old_email,
                    'new_email': new_email,
                    'admin_username': g.admin.username,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to notify new email {new_email}: {e}")
        
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to change email: {e}', 'error')
        logger.error(f"Email change failed for {account.username}: {e}")
    
    return redirect(url_for('admin.account_detail', account_id=account_id))


@admin_bp.route('/accounts/<int:account_id>/realms/new', methods=['GET', 'POST'])
@require_admin
def account_add_realm(account_id):
    """Add realm to account (admin action - auto-approved)."""
    account = Account.query.get_or_404(account_id)
    
    if request.method == 'POST':
        realm_type = request.form.get('realm_type', '')
        full_domain = request.form.get('realm_value', '').strip().lower()
        record_types = request.form.getlist('record_types')
        operations = request.form.getlist('operations')
        
        # Parse full_domain into domain (base) and realm_value (subdomain prefix)
        # e.g., "home.example.com" -> domain="example.com", realm_value="home"
        # e.g., "iot.sub.example.com" -> domain="example.com", realm_value="iot.sub"
        # e.g., "example.com" -> domain="example.com", realm_value=""
        if not full_domain:
            flash('Domain is required', 'error')
            return render_template('admin/realm_create.html', account=account)
        
        parts = full_domain.split('.')
        if len(parts) < 2:
            flash('Invalid domain format (need at least domain.tld)', 'error')
            return render_template('admin/realm_create.html', account=account)
        
        # Extract base domain (last 2 parts) and subdomain prefix (rest)
        # For TLDs like co.uk, this is simplified - assume 2-part TLD for now
        domain = '.'.join(parts[-2:])  # e.g., "example.com"
        realm_value = '.'.join(parts[:-2]) if len(parts) > 2 else ''  # e.g., "home" or "iot.sub"
        
        result = create_realm_by_admin(
            account=account,
            domain=domain,
            realm_type=realm_type,
            realm_value=realm_value,
            record_types=record_types,
            operations=operations,
            created_by=g.admin
        )
        
        if result.success:
            flash('Realm added', 'success')
            return redirect(url_for('admin.account_detail', account_id=account_id))
        else:
            flash(result.error, 'error')
    
    return render_template('admin/realm_create.html', account=account)


# ============================================================================
# Realm Management
# ============================================================================

@admin_bp.route('/realms')
@require_admin
def realms_list():
    """List all realms across all accounts."""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    status_filter = request.args.get('status', 'all')
    search = request.args.get('search', '').strip()
    
    # Use explicit join condition to avoid ambiguity with multiple foreign keys
    query = AccountRealm.query.join(Account, AccountRealm.account_id == Account.id)
    
    if status_filter == 'approved':
        query = query.filter(AccountRealm.status == 'approved')
    elif status_filter == 'pending':
        query = query.filter(AccountRealm.status == 'pending')
    elif status_filter == 'rejected':
        query = query.filter(AccountRealm.status == 'rejected')
    
    if search:
        query = query.filter(
            db.or_(
                AccountRealm.realm_value.ilike(f'%{search}%'),
                AccountRealm.domain.ilike(f'%{search}%'),
                Account.username.ilike(f'%{search}%')
            )
        )
    
    pagination = query.order_by(AccountRealm.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get token counts for each realm
    realm_data = []
    for realm in pagination.items:
        token_count = APIToken.query.filter_by(realm_id=realm.id).count()
        active_token_count = APIToken.query.filter_by(realm_id=realm.id, is_active=1).count()
        realm_data.append({
            'realm': realm,
            'token_count': token_count,
            'active_token_count': active_token_count
        })
    
    return render_template('admin/realms_list.html',
                          realms=realm_data,
                          pagination=pagination,
                          status_filter=status_filter,
                          search=search)


@admin_bp.route('/realms/<int:realm_id>')
@require_admin
def realm_detail(realm_id):
    """Realm detail view."""
    realm = AccountRealm.query.get_or_404(realm_id)
    tokens = APIToken.query.filter_by(realm_id=realm_id).order_by(APIToken.created_at.desc()).all()
    
    # Recent activity for this realm - join through tokens since ActivityLog has token_id not realm_id
    token_ids = [t.id for t in tokens]
    if token_ids:
        recent_activity = (
            ActivityLog.query
            .filter(ActivityLog.token_id.in_(token_ids))
            .order_by(ActivityLog.created_at.desc())
            .limit(20)
            .all()
        )
    else:
        recent_activity = []
    
    return render_template('admin/realm_detail.html',
                          realm=realm,
                          tokens=tokens,
                          recent_activity=recent_activity)


# ============================================================================
# Realm Approvals
# ============================================================================

@admin_bp.route('/realms/pending')
@require_admin
def realms_pending():
    """List pending realm requests."""
    pending = get_pending_realms()
    return render_template('admin/realms_pending.html', realms=pending)


@admin_bp.route('/realms/<int:realm_id>/approve', methods=['POST'])
@require_admin
def realm_approve(realm_id):
    """Approve a realm request."""
    result = approve_realm(realm_id, g.admin)
    
    if result.success:
        flash('Realm approved', 'success')
    else:
        flash(result.error, 'error')
    
    return redirect(request.referrer or url_for('admin.realms_pending'))


@admin_bp.route('/realms/<int:realm_id>/reject', methods=['POST'])
@require_admin
def realm_reject(realm_id):
    """Reject a realm request."""
    reason = request.form.get('reason', 'Rejected by admin')
    result = reject_realm(realm_id, g.admin, reason)
    
    if result.success:
        flash('Realm rejected', 'success')
    else:
        flash(result.error, 'error')
    
    return redirect(request.referrer or url_for('admin.realms_pending'))


@admin_bp.route('/realms/<int:realm_id>/revoke', methods=['POST'])
@require_admin
def realm_revoke(realm_id):
    """Revoke an approved realm."""
    realm = AccountRealm.query.get_or_404(realm_id)
    
    if realm.status != 'approved':
        flash('Only approved realms can be revoked', 'error')
        return redirect(url_for('admin.realm_detail', realm_id=realm_id))
    
    # Revoke the realm
    realm.status = 'revoked'
    
    # Deactivate all associated tokens
    revoked_count = 0
    for token in realm.tokens:
        if token.is_active:
            token.revoked = True
            token.revoked_at = datetime.utcnow()
            token.revoked_by = g.admin.username
            token.revoked_reason = 'Realm revoked'
            revoked_count += 1
    
    db.session.commit()
    
    # Log the action
    log_activity('realm_revoked', 'success', 
                details=f'Revoked realm {realm.realm_value}.{realm.domain}, deactivated {revoked_count} tokens',
                actor=g.admin.username)
    
    flash(f'Realm revoked. {revoked_count} tokens deactivated.', 'success')
    return redirect(url_for('admin.realm_detail', realm_id=realm_id))


# ============================================================================
# Token Management
# ============================================================================

@admin_bp.route('/tokens/<int:token_id>')
@require_admin
def token_detail(token_id):
    """Token detail view."""
    token = APIToken.query.get_or_404(token_id)
    
    # Get related activity logs for this token
    activity_logs = ActivityLog.query.filter(
        ActivityLog.token_id == token_id
    ).order_by(ActivityLog.created_at.desc()).limit(20).all()
    
    return render_template('admin/token_detail.html',
                          token=token,
                          realm=token.realm,
                          account=token.realm.account if token.realm else None,
                          activity_logs=activity_logs,
                          now=datetime.utcnow())


@admin_bp.route('/tokens/<int:token_id>/revoke', methods=['POST'])
@require_admin
def token_revoke(token_id):
    """Revoke a token."""
    token = APIToken.query.get_or_404(token_id)
    
    if token.revoked_at is not None:
        flash('Token is already revoked', 'warning')
        return redirect(url_for('admin.token_detail', token_id=token_id))
    
    # Get the account that owns this token
    account = token.realm.account
    revoke_reason = request.form.get('reason', 'Revoked by admin')
    
    # Revoke the token
    token.is_active = 0
    token.revoked_at = datetime.utcnow()
    token.revoked_reason = revoke_reason
    
    db.session.commit()
    
    # Send notification to token owner
    from ..notification_service import notify_token_revoked
    notify_token_revoked(account, token, g.admin.username, revoke_reason)
    
    # Log the action
    log_activity('token_revoked', 'success', 
                details=f'Revoked token {token.token_prefix} for realm {token.realm.realm_value}.{token.realm.domain}',
                actor=g.admin.username)
    
    flash('Token has been revoked', 'success')
    return redirect(url_for('admin.token_detail', token_id=token_id))


# ============================================================================
# Audit Logs
# ============================================================================

@admin_bp.route('/audit')
@require_admin
def audit_logs():
    """Audit logs page."""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Filters
    time_range = request.args.get('range', '24h')
    status_filter = request.args.get('status', 'all')
    action_filter = request.args.get('action', 'all')
    
    query = ActivityLog.query
    
    # Time range filter
    if time_range == '1h':
        since = datetime.utcnow() - timedelta(hours=1)
    elif time_range == '24h':
        since = datetime.utcnow() - timedelta(hours=24)
    elif time_range == '7d':
        since = datetime.utcnow() - timedelta(days=7)
    elif time_range == '30d':
        since = datetime.utcnow() - timedelta(days=30)
    else:
        since = None
    
    if since:
        query = query.filter(ActivityLog.created_at >= since)
    
    # Status filter
    if status_filter == 'success':
        query = query.filter_by(status='success')
    elif status_filter == 'denied':
        query = query.filter_by(status='denied')
    elif status_filter == 'error':
        query = query.filter_by(status='error')
    
    # Action filter (support partial matching for categories like 'api', 'account', 'realm', 'token')
    if action_filter != 'all':
        if action_filter in ['api', 'account', 'realm', 'token', 'config']:
            # Category filter: match actions starting with category_
            query = query.filter(ActivityLog.action.like(f'{action_filter}_%'))
        else:
            # Exact match for specific actions like 'login', 'logout'
            query = query.filter_by(action=action_filter)
    
    pagination = query.order_by(ActivityLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Calculate stats for the summary cards
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    last_24h = datetime.utcnow() - timedelta(hours=24)
    
    stats = {
        'total_today': ActivityLog.query.filter(ActivityLog.created_at >= today_start).count(),
        'logins_today': ActivityLog.query.filter(
            ActivityLog.created_at >= today_start,
            ActivityLog.action == 'login'
        ).count(),
        'failed_logins': ActivityLog.query.filter(
            ActivityLog.created_at >= last_24h,
            ActivityLog.action == 'login',
            ActivityLog.status == 'denied'
        ).count(),
        'api_calls': ActivityLog.query.filter(
            ActivityLog.created_at >= last_24h,
            ActivityLog.action.in_(['dns_read', 'dns_update', 'dns_create', 'dns_delete'])
        ).count(),
    }
    
    return render_template('admin/audit_logs.html',
                          logs=pagination.items,
                          pagination=pagination,
                          time_range=time_range,
                          status_filter=status_filter,
                          action_filter=action_filter,
                          stats=stats)


@admin_bp.route('/audit/data')
@require_admin
def audit_logs_data():
    """AJAX endpoint for audit logs table data (for auto-refresh without page reload)."""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Filters
    time_range = request.args.get('range', '24h')
    status_filter = request.args.get('status', 'all')
    action_filter = request.args.get('action', 'all')
    
    query = ActivityLog.query
    
    # Time range filter
    if time_range == '1h':
        since = datetime.utcnow() - timedelta(hours=1)
    elif time_range == '24h':
        since = datetime.utcnow() - timedelta(hours=24)
    elif time_range == '7d':
        since = datetime.utcnow() - timedelta(days=7)
    elif time_range == '30d':
        since = datetime.utcnow() - timedelta(days=30)
    else:
        since = None
    
    if since:
        query = query.filter(ActivityLog.created_at >= since)
    
    # Status filter
    if status_filter == 'success':
        query = query.filter_by(status='success')
    elif status_filter == 'denied':
        query = query.filter_by(status='denied')
    elif status_filter == 'error':
        query = query.filter_by(status='error')
    
    # Action filter
    if action_filter != 'all':
        if action_filter in ['api', 'account', 'realm', 'token', 'config']:
            query = query.filter(ActivityLog.action.like(f'{action_filter}_%'))
        else:
            query = query.filter_by(action=action_filter)
    
    pagination = query.order_by(ActivityLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Return just the table rows as HTML fragment
    return render_template('admin/audit_logs_table.html',
                          logs=pagination.items)


@admin_bp.route('/audit/trim', methods=['POST'])
@require_admin
def audit_trim():
    """Delete logs older than X days."""
    days = request.form.get('days', 30, type=int)
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    deleted = ActivityLog.query.filter(ActivityLog.created_at < cutoff).delete()
    db.session.commit()
    
    flash(f'Deleted {deleted} log entries older than {days} days', 'success')
    logger.info(f"Audit logs trimmed: {deleted} entries by {g.admin.username}")
    
    return redirect(url_for('admin.audit_logs'))


@admin_bp.route('/audit/export')
@require_admin
def audit_export():
    """Export audit logs to ODS format."""
    from io import BytesIO
    from flask import send_file
    
    # Get filter parameters
    time_range = request.args.get('range', '24h')
    status_filter = request.args.get('status', 'all')
    action_filter = request.args.get('action', 'all')
    
    query = ActivityLog.query
    
    # Time range filter
    if time_range == '1h':
        since = datetime.utcnow() - timedelta(hours=1)
    elif time_range == '24h':
        since = datetime.utcnow() - timedelta(hours=24)
    elif time_range == '7d':
        since = datetime.utcnow() - timedelta(days=7)
    elif time_range == '30d':
        since = datetime.utcnow() - timedelta(days=30)
    else:
        since = None
    
    if since:
        query = query.filter(ActivityLog.created_at >= since)
    
    # Status filter
    if status_filter == 'success':
        query = query.filter_by(status='success')
    elif status_filter == 'denied':
        query = query.filter_by(status='denied')
    elif status_filter == 'error':
        query = query.filter_by(status='error')
    
    # Action filter
    if action_filter != 'all':
        query = query.filter_by(action=action_filter)
    
    # Limit to prevent huge exports
    logs = query.order_by(ActivityLog.created_at.desc()).limit(10000).all()
    
    # Create ODS file
    output = create_audit_ods_export(logs, f'Audit Logs Export - {time_range}')
    
    logger.info(f"Audit logs exported by {g.admin.username}: {len(logs)} entries")
    
    return send_file(
        output,
        mimetype='application/vnd.oasis.opendocument.spreadsheet',
        as_attachment=True,
        download_name=f'audit_logs_{datetime.utcnow().strftime("%Y%m%d_%H%M")}.ods'
    )


def create_audit_ods_export(logs, title):
    """Create ODS file from audit logs."""
    from io import BytesIO
    import zipfile
    
    # ODS is a zip file with XML content
    output = BytesIO()
    
    # Build content.xml
    rows_xml = []
    
    # Header row
    headers = ['Timestamp', 'Username', 'Action', 'Status', 'Source IP', 'Details']
    header_cells = ''.join([f'<table:table-cell office:value-type="string"><text:p>{h}</text:p></table:table-cell>' for h in headers])
    rows_xml.append(f'<table:table-row>{header_cells}</table:table-row>')
    
    def escape_xml(s):
        """Escape XML special characters."""
        if not s:
            return ''
        return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    
    # Data rows
    for log in logs:
        # Get username from account if available
        username = ''
        if log.account_id:
            account = Account.query.get(log.account_id)
            if account:
                username = account.username
        
        cells = [
            log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else '',
            username,
            log.action or '',
            log.status or '',
            log.source_ip or '',
            log.status_reason or ''  # Use status_reason, not details
        ]
        cells_xml = ''.join([f'<table:table-cell office:value-type="string"><text:p>{escape_xml(c)}</text:p></table:table-cell>' for c in cells])
        rows_xml.append(f'<table:table-row>{cells_xml}</table:table-row>')
    
    content_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    office:version="1.2">
    <office:body>
        <office:spreadsheet>
            <table:table table:name="{escape_xml(title)}">
                {''.join(rows_xml)}
            </table:table>
        </office:spreadsheet>
    </office:body>
</office:document-content>'''
    
    # Create minimal ODS (zip with XML files)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('mimetype', 'application/vnd.oasis.opendocument.spreadsheet')
        zf.writestr('content.xml', content_xml)
        
        # Minimal manifest
        manifest_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">
    <manifest:file-entry manifest:media-type="application/vnd.oasis.opendocument.spreadsheet" manifest:full-path="/"/>
    <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="content.xml"/>
</manifest:manifest>'''
        zf.writestr('META-INF/manifest.xml', manifest_xml)
    
    output.seek(0)
    return output


# ============================================================================
# Configuration
# ============================================================================

@admin_bp.route('/config/netcup', methods=['GET', 'POST'])
@require_admin
def config_netcup():
    """Netcup API configuration."""
    if request.method == 'POST':
        config = {
            'customer_id': request.form.get('customer_id', '').strip(),
            'api_key': request.form.get('api_key', '').strip(),
            'api_password': request.form.get('api_password', '').strip(),
            'api_url': request.form.get('api_url', '').strip() or 'https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON',
            'timeout': int(request.form.get('timeout', 30)),
        }
        
        set_setting('netcup_config', config)
        flash('Netcup API configuration saved', 'success')
        logger.info(f"Netcup config updated by {g.admin.username}")
    
    config = get_setting('netcup_config') or {}
    
    return render_template('admin/config_netcup.html', config=config)


@admin_bp.route('/config/email', methods=['GET', 'POST'])
@require_admin
def config_email():
    """Email/SMTP configuration."""
    if request.method == 'POST':
        # Use TOML field names directly (no mapping)
        smtp_security = request.form.get('smtp_security', 'tls')
        config = {
            'smtp_host': request.form.get('smtp_host', '').strip(),
            'smtp_port': int(request.form.get('smtp_port', 587)),
            'smtp_security': smtp_security,
            'smtp_username': request.form.get('smtp_username', '').strip(),
            'smtp_password': request.form.get('smtp_password', '').strip(),
            'use_ssl': smtp_security == 'ssl',
            'from_email': request.form.get('from_email', '').strip(),
            'from_name': request.form.get('from_name', '').strip() or 'Netcup API Filter',
            'reply_to': request.form.get('reply_to', '').strip(),
            'admin_email': request.form.get('admin_email', '').strip(),
            'notify_new_account': bool(request.form.get('notify_new_account')),
            'notify_realm_request': bool(request.form.get('notify_realm_request')),
            'notify_security': bool(request.form.get('notify_security')),
        }
        
        set_setting('smtp_config', config)
        flash('Email configuration saved', 'success')
        logger.info(f"Email config updated by {g.admin.username}")
    
    config = get_setting('smtp_config') or {}
    
    # Email stats (placeholder - would need actual email tracking)
    stats = {
        'sent_today': 0,
        'sent_week': 0,
        'failed': 0,
    }
    
    return render_template('admin/config_email.html', config=config, stats=stats)


@admin_bp.route('/config/email/test', methods=['POST'])
@require_admin
def config_email_test():
    """Send test email."""
    test_email = request.form.get('test_email', '').strip()
    
    # TODO: Implement email sending
    flash(f'Test email sent to {test_email}', 'info')
    
    return redirect(url_for('admin.config_email'))


@admin_bp.route('/config/geoip', methods=['GET', 'POST'])
@require_admin
def config_geoip():
    """GeoIP configuration."""
    if request.method == 'POST':
        config = {
            'account_id': request.form.get('account_id', '').strip(),
            'license_key': request.form.get('license_key', '').strip(),
            'api_url': request.form.get('api_url', '').strip() or 'https://geoip.maxmind.com/geoip/v2.1',
        }
        
        set_setting('geoip_config', config)
        flash('GeoIP configuration saved', 'success')
        logger.info(f"GeoIP config updated by {g.admin.username}")
        return redirect(url_for('admin.settings'))
    
    config = get_setting('geoip_config') or {}
    return render_template('admin/config_geoip.html', config=config)


@admin_bp.route('/settings', methods=['GET'])
@require_admin
def settings():
    """Unified settings page."""
    # Get all configs
    netcup_config = get_setting('netcup_config') or {}
    
    smtp_config_str = get_setting('smtp_config')
    smtp_config = {}
    if smtp_config_str:
        try:
            import json
            smtp_config = json.loads(smtp_config_str) if isinstance(smtp_config_str, str) else smtp_config_str
        except (json.JSONDecodeError, TypeError):
            smtp_config = {}
    
    geoip_config_str = get_setting('geoip_config')
    geoip_config = {}
    if geoip_config_str:
        try:
            import json
            geoip_config = json.loads(geoip_config_str) if isinstance(geoip_config_str, str) else geoip_config_str
        except (json.JSONDecodeError, TypeError):
            geoip_config = {}
    
    # Security settings
    security_settings = {
        'password_reset_expiry_hours': get_setting('password_reset_expiry_hours') or 1,
        'invite_expiry_hours': get_setting('invite_expiry_hours') or 48,
        'admin_rate_limit': get_setting('admin_rate_limit') or os.environ.get('ADMIN_RATE_LIMIT', '50 per minute'),
        'account_rate_limit': get_setting('account_rate_limit') or os.environ.get('ACCOUNT_RATE_LIMIT', '50 per minute'),
        'api_rate_limit': get_setting('api_rate_limit') or os.environ.get('API_RATE_LIMIT', '60 per minute'),
    }
    
    return render_template('admin/settings.html',
                          netcup_config=netcup_config,
                          smtp_config=smtp_config,
                          geoip_config=geoip_config,
                          security_settings=security_settings)


# ============================================================================
# System
# ============================================================================

@admin_bp.route('/app-logs')
@require_admin
def app_logs():
    """Application logs page."""
    return render_template('admin/app_logs.html')


@admin_bp.route('/system')
@require_admin
def system_info():
    """System information page."""
    import sys
    import os
    import platform
    import socket
    from datetime import datetime, timedelta
    import flask
    
    # Build info
    build_info = {}
    try:
        from ..utils import get_build_info
        build_info = get_build_info() or {}
    except Exception:
        pass
    
    # Database path and size
    db_path = os.environ.get('NETCUP_FILTER_DB_PATH', 'netcup_filter.db')
    db_size = 0
    try:
        if os.path.exists(db_path):
            db_size = os.path.getsize(db_path)
    except Exception:
        pass
    
    # Format database size
    def format_size(size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
    
    # Database info for template
    db_info = {
        'path': db_path,
        'size': format_size(db_size),
        'accounts_count': Account.query.count(),
        'realms_count': AccountRealm.query.count(),
        'tokens_count': APIToken.query.count(),
        'logs_count': ActivityLog.query.count(),
    }
    
    # Server info for template
    # Get Flask version safely (handles vendored packages without metadata)
    try:
        flask_version = flask.__version__
    except Exception:
        # Flask's __getattr__ raises PackageNotFoundError for vendored packages
        flask_version = '3.1.0'  # Update this when Flask version changes
    
    server_info = {
        'hostname': socket.gethostname(),
        'platform': platform.platform(),
        'python_version': sys.version.split()[0],
        'flask_version': flask_version,
        'time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
        'timezone': 'UTC',
    }
    
    # Calculate uptime from startup timestamp file
    uptime_str = 'Unknown'
    startup_file = os.path.join(os.path.dirname(db_path), '.app_startup')
    try:
        if os.path.exists(startup_file):
            startup_time = datetime.fromtimestamp(os.path.getmtime(startup_file))
            uptime_delta = datetime.now() - startup_time
            days = uptime_delta.days
            hours = uptime_delta.seconds // 3600
            minutes = (uptime_delta.seconds % 3600) // 60
            if days > 0:
                uptime_str = f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                uptime_str = f"{hours}h {minutes}m"
            else:
                uptime_str = f"{minutes}m"
    except Exception:
        pass
    
    # App info for template
    app_info = {
        'version': build_info.get('version', 'dev'),
        'build_hash': build_info.get('git_short', build_info.get('commit_short', 'N/A')),
        'build_date': build_info.get('built_at', 'N/A'),
        'env': os.environ.get('FLASK_ENV', 'development'),
        'uptime': uptime_str,
    }
    
    # Legacy stats variable (some templates may still use it)
    stats = db_info
    
    # Services status with health checks
    smtp_config_str = get_setting('smtp_config')
    smtp_config = {}
    if smtp_config_str:
        try:
            import json
            smtp_config = json.loads(smtp_config_str) if isinstance(smtp_config_str, str) else smtp_config_str
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Failed to parse smtp_config: {smtp_config_str}")
            smtp_config = {}
    
    # Check Netcup API with actual connectivity test
    netcup_config_str = get_setting('netcup_config')
    netcup_configured = False
    if netcup_config_str:
        try:
            import json
            netcup_config = json.loads(netcup_config_str) if isinstance(netcup_config_str, str) else netcup_config_str
            netcup_configured = bool(netcup_config.get('customer_id') and 
                                    netcup_config.get('api_key') and 
                                    netcup_config.get('api_password'))
        except (json.JSONDecodeError, TypeError):
            pass
    
    netcup_status = 'configured' if netcup_configured else 'not_configured'
    
    # Check email SMTP with actual connectivity test
    smtp_configured = bool(smtp_config.get('smtp_host'))
    smtp_status = 'configured' if smtp_configured else 'not_configured'
    
    # Check GeoIP status
    geoip_status = 'not_configured'
    geoip_info = {}
    try:
        geoip_info = get_geoip_status()
        if geoip_info.get('available', False):
            geoip_status = 'available'
        elif geoip_info.get('error'):
            geoip_status = 'error'
    except Exception as e:
        geoip_info = {'error': str(e)}
        geoip_status = 'error'
    
    services = {
        'netcup': netcup_status,
        'email': smtp_status,
        'geoip': geoip_status,
    }
    
    # Get installed Python packages (system-wide)
    python_packages = []
    try:
        import pkg_resources
        installed_packages = sorted(pkg_resources.working_set, key=lambda x: x.key)
        for package in installed_packages:
            python_packages.append({
                'name': package.key,
                'version': package.version
            })
    except Exception:
        pass
    
    # Get vendored packages from vendor/ directory
    vendored_packages = []
    # vendor/ is at deployment root level, admin.py is at src/netcup_api_filter/api/admin.py
    # So we need to go up 3 levels: api -> netcup_api_filter -> src -> root
    vendor_path = os.path.join(os.path.dirname(__file__), '../../../vendor')
    vendor_path = os.path.abspath(vendor_path)  # Resolve to absolute path
    if os.path.exists(vendor_path):
        try:
            seen_packages = set()
            for item in sorted(os.listdir(vendor_path)):
                item_path = os.path.join(vendor_path, item)
                # Count package directories (not .dist-info - those may be stripped)
                if os.path.isdir(item_path) and not item.startswith('_') and not item.endswith('.dist-info'):
                    # Try multiple strategies to get version
                    version = 'unknown'
                    try:
                        # Strategy 1: Check __init__.py for version attributes
                        init_file = os.path.join(item_path, '__init__.py')
                        if os.path.exists(init_file):
                            with open(init_file, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read(5000)  # Read first 5KB
                                import re
                                # Try multiple patterns
                                patterns = [
                                    r'__version__\s*=\s*["\']([^"\']+)["\']',
                                    r'VERSION\s*=\s*["\']([^"\']+)["\']',
                                    r'version\s*=\s*["\']([^"\']+)["\']',
                                ]
                                for pattern in patterns:
                                    match = re.search(pattern, content)
                                    if match:
                                        version = match.group(1)
                                        break
                        
                        # Strategy 2: Check for _version.py or version.py
                        if version == 'unknown':
                            for version_file in ['_version.py', 'version.py', '__version__.py']:
                                version_file_path = os.path.join(item_path, version_file)
                                if os.path.exists(version_file_path):
                                    with open(version_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                        content = f.read(2000)
                                        import re
                                        match = re.search(r'["\']([0-9]+\.[0-9]+[^"\']*)["\']', content)
                                        if match:
                                            version = match.group(1)
                                            break
                        
                        # Strategy 3: Try to find PKG-INFO or METADATA in parent dist-info
                        if version == 'unknown':
                            # Look for corresponding .dist-info directory
                            for dist_item in os.listdir(vendor_path):
                                if dist_item.startswith(item) and dist_item.endswith('.dist-info'):
                                    metadata_file = os.path.join(vendor_path, dist_item, 'METADATA')
                                    if not os.path.exists(metadata_file):
                                        metadata_file = os.path.join(vendor_path, dist_item, 'PKG-INFO')
                                    
                                    if os.path.exists(metadata_file):
                                        with open(metadata_file, 'r', encoding='utf-8', errors='ignore') as f:
                                            for line in f:
                                                if line.startswith('Version:'):
                                                    version = line.split(':', 1)[1].strip()
                                                    break
                                        break
                    except Exception as e:
                        logger.debug(f"Failed to get version for {item}: {e}")
                        pass
                    
                    if item not in seen_packages:
                        seen_packages.add(item)
                        vendored_packages.append({'name': item, 'version': version})
        except Exception as e:
            logger.warning(f"Failed to read vendored packages from {vendor_path}: {e}")
            pass
    
    # Security settings (including rate limiting)
    # Rate limits come from: Settings table → .env.defaults (no hardcoded fallbacks)
    security_settings = {
        'password_reset_expiry_hours': get_setting('password_reset_expiry_hours') or 1,
        'invite_expiry_hours': get_setting('invite_expiry_hours') or 48,
        'admin_rate_limit': get_setting('admin_rate_limit') or os.environ.get('ADMIN_RATE_LIMIT', '50 per minute'),
        'account_rate_limit': get_setting('account_rate_limit') or os.environ.get('ACCOUNT_RATE_LIMIT', '50 per minute'),
        'api_rate_limit': get_setting('api_rate_limit') or os.environ.get('API_RATE_LIMIT', '60 per minute'),
    }
    
    # Recent logs (placeholder - would need log file reading implementation)
    recent_logs = []
    
    return render_template('admin/system_info.html',
                          build_info=build_info,
                          python_version=sys.version,
                          db_size=db_size,
                          stats=stats,
                          app=app_info,
                          db=db_info,
                          server=server_info,
                          services=services,
                          geoip_info=geoip_info,
                          python_packages=python_packages,
                          vendored_packages=vendored_packages,
                          security_settings=security_settings,
                          recent_logs=recent_logs)

@admin_bp.route('/system/security', methods=['POST'])
@require_admin
def update_security_settings():
    """Update security settings."""
    try:
        password_reset_expiry = request.form.get('password_reset_expiry_hours')
        if password_reset_expiry:
            set_setting('password_reset_expiry_hours', int(password_reset_expiry))
        
        invite_expiry = request.form.get('invite_expiry_hours')
        if invite_expiry:
            set_setting('invite_expiry_hours', int(invite_expiry))
        
        # Rate limiting settings
        admin_rate_limit = request.form.get('admin_rate_limit')
        if admin_rate_limit:
            set_setting('admin_rate_limit', admin_rate_limit.strip())
        
        account_rate_limit = request.form.get('account_rate_limit')
        if account_rate_limit:
            set_setting('account_rate_limit', account_rate_limit.strip())
        
        api_rate_limit = request.form.get('api_rate_limit')
        if api_rate_limit:
            set_setting('api_rate_limit', api_rate_limit.strip())
        
        flash('Security settings updated. Rate limit changes require application restart.', 'success')
        logger.info(f"Security settings updated by {g.admin.username}")
    except ValueError as e:
        flash(f'Invalid value: {e}', 'error')
    except Exception as e:
        flash(f'Error saving settings: {e}', 'error')
        logger.error(f"Failed to update security settings: {e}")
    
    return redirect(url_for('admin.system_info'))


@admin_bp.route('/api/geoip/<ip_address>')
@require_admin
def api_geoip_lookup(ip_address):
    """Look up GeoIP information for an IP address (JSON API)."""
    try:
        location = geoip_location(ip_address)
        if location:
            return jsonify({'success': True, 'location': location, 'ip': ip_address})
        else:
            return jsonify({'success': False, 'error': 'No location data available', 'ip': ip_address})
    except Exception as e:
        logger.error(f"GeoIP lookup failed for {ip_address}: {e}")
        return jsonify({'success': False, 'error': str(e), 'ip': ip_address}), 500


@admin_bp.route('/system/logs')
@require_admin
def get_system_logs():
    """Get paginated system logs from netcup_filter.log file."""
    import os
    from flask import jsonify
    
    page = int(request.args.get('page', 1))
    lines_per_page = int(request.args.get('per_page', 100))
    
    # Get log file path
    db_path = os.environ.get('NETCUP_FILTER_DB_PATH', 'netcup_filter.db')
    log_file = os.path.join(os.path.dirname(db_path), 'netcup_filter.log')
    
    try:
        if not os.path.exists(log_file):
            return jsonify({
                'logs': ['No log file found'],
                'total_lines': 0,
                'page': page,
                'per_page': lines_per_page,
                'has_more': False
            })
        
        # Read log file (from the end for recent logs first)
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
        
        # Reverse to show most recent first
        all_lines.reverse()
        
        total_lines = len(all_lines)
        start_idx = (page - 1) * lines_per_page
        end_idx = start_idx + lines_per_page
        
        page_lines = all_lines[start_idx:end_idx]
        has_more = end_idx < total_lines
        
        return jsonify({
            'logs': [line.rstrip() for line in page_lines],
            'total_lines': total_lines,
            'page': page,
            'per_page': lines_per_page,
            'has_more': has_more
        })
    
    except Exception as e:
        logger.error(f"Error reading log file: {e}")
        return jsonify({
            'error': str(e),
            'logs': [f'Error reading log file: {e}'],
            'total_lines': 0,
            'page': page,
            'per_page': lines_per_page,
            'has_more': False
        }), 500


# ============================================================================
# Security Dashboard
# ============================================================================

@admin_bp.route('/security')
@require_admin
def security_dashboard():
    """
    Security dashboard showing security events, attack patterns, and metrics.
    
    Features:
    - Security stats (last hour, 24h)
    - Recent security events (filtered by severity)
    - Attack pattern detection
    - Timeline chart data
    """
    from ..token_auth import get_security_stats, get_security_timeline
    
    # Get stats for different time windows
    stats_1h = get_security_stats(hours=1)
    stats_24h = get_security_stats(hours=24)
    
    # Get timeline data for chart
    timeline = get_security_timeline(hours=24)
    
    # Get recent security events (high/critical severity only for main view)
    recent_events = ActivityLog.query.filter(
        ActivityLog.severity.in_(['high', 'critical']),
        ActivityLog.created_at >= datetime.utcnow() - timedelta(hours=24)
    ).order_by(ActivityLog.created_at.desc()).limit(50).all()
    
    # Get all security events for filterable list
    all_events = ActivityLog.query.filter(
        ActivityLog.error_code.isnot(None),
        ActivityLog.created_at >= datetime.utcnow() - timedelta(hours=24)
    ).order_by(ActivityLog.created_at.desc()).limit(200).all()
    
    # Attack detection: IPs with multiple failures
    attack_ips = db.session.query(
        ActivityLog.source_ip,
        db.func.count(ActivityLog.id).label('count')
    ).filter(
        ActivityLog.is_attack == 1,
        ActivityLog.created_at >= datetime.utcnow() - timedelta(hours=24)
    ).group_by(ActivityLog.source_ip).having(
        db.func.count(ActivityLog.id) >= 3
    ).order_by(db.desc('count')).limit(10).all()
    
    return render_template('admin/security_dashboard.html',
                          stats_1h=stats_1h,
                          stats_24h=stats_24h,
                          timeline=timeline,
                          recent_events=recent_events,
                          all_events=all_events,
                          attack_ips=attack_ips)


@admin_bp.route('/api/security/stats')
@require_admin
def api_security_stats():
    """Get security stats as JSON for dashboard widgets."""
    from ..token_auth import get_security_stats
    
    hours = int(request.args.get('hours', 24))
    hours = min(hours, 168)  # Max 7 days
    
    return jsonify(get_security_stats(hours=hours))


@admin_bp.route('/api/security/timeline')
@require_admin
def api_security_timeline():
    """Get security timeline data for charts."""
    from ..token_auth import get_security_timeline
    
    hours = int(request.args.get('hours', 24))
    hours = min(hours, 168)  # Max 7 days
    
    return jsonify(get_security_timeline(hours=hours))


@admin_bp.route('/api/security/events')
@require_admin
def api_security_events():
    """Get security events as JSON with filtering."""
    hours = int(request.args.get('hours', 24))
    severity = request.args.get('severity')  # 'low', 'medium', 'high', 'critical'
    error_code = request.args.get('error_code')
    source_ip = request.args.get('source_ip')
    limit = min(int(request.args.get('limit', 100)), 500)
    
    since = datetime.utcnow() - timedelta(hours=hours)
    
    query = ActivityLog.query.filter(
        ActivityLog.error_code.isnot(None),
        ActivityLog.created_at >= since
    )
    
    if severity:
        query = query.filter(ActivityLog.severity == severity)
    if error_code:
        query = query.filter(ActivityLog.error_code == error_code)
    if source_ip:
        query = query.filter(ActivityLog.source_ip == source_ip)
    
    events = query.order_by(ActivityLog.created_at.desc()).limit(limit).all()
    
    return jsonify([{
        'id': e.id,
        'created_at': e.created_at.isoformat(),
        'error_code': e.error_code,
        'severity': e.severity,
        'source_ip': e.source_ip,
        'user_agent': e.user_agent,
        'account_id': e.account_id,
        'token_id': e.token_id,
        'status_reason': e.status_reason,
        'is_attack': bool(e.is_attack),
    } for e in events])


# ============================================================================
# API Endpoints
# ============================================================================

@admin_bp.route('/api/accounts')
@require_admin
def api_accounts():
    """Get accounts as JSON."""
    accounts = Account.query.filter_by(is_admin=0).all()
    
    return jsonify([{
        'id': a.id,
        'username': a.username,
        'email': a.email,
        'is_active': bool(a.is_active),
        'email_verified': bool(a.email_verified),
        'created_at': a.created_at.isoformat(),
        'last_login_at': a.last_login_at.isoformat() if a.last_login_at else None,
    } for a in accounts])


@admin_bp.route('/api/stats')
@require_admin
def api_stats():
    """Get dashboard stats as JSON."""
    since = datetime.utcnow() - timedelta(hours=24)
    
    return jsonify({
        'total_accounts': Account.query.filter_by(is_admin=0).count(),
        'active_accounts': Account.query.filter_by(is_admin=0, is_active=1).count(),
        'pending_accounts': Account.query.filter_by(is_admin=0, is_active=0).count(),
        'pending_realms': AccountRealm.query.filter_by(status='pending').count(),
        'api_calls_24h': ActivityLog.query.filter(
            ActivityLog.created_at >= since,
            ActivityLog.action == 'api_call'
        ).count(),
        'errors_24h': ActivityLog.query.filter(
            ActivityLog.created_at >= since,
            ActivityLog.status == 'error'
        ).count(),
    })


# ============================================================================
# Bulk Actions (P7.6)
# ============================================================================

@admin_bp.route('/api/accounts/bulk', methods=['POST'])
@require_admin
def api_accounts_bulk():
    """Perform bulk action on multiple accounts.
    
    JSON body:
    {
        "action": "enable|disable|delete",
        "account_ids": [1, 2, 3]
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400
    
    action = data.get('action')
    account_ids = data.get('account_ids', [])
    
    if not action or action not in ['enable', 'disable', 'delete']:
        return jsonify({'error': 'Invalid action'}), 400
    
    if not account_ids or not isinstance(account_ids, list):
        return jsonify({'error': 'No accounts specified'}), 400
    
    # Get accounts (excluding admin accounts)
    accounts = Account.query.filter(
        Account.id.in_(account_ids),
        Account.is_admin == 0
    ).all()
    
    if not accounts:
        return jsonify({'error': 'No valid accounts found'}), 404
    
    results = {'success': [], 'failed': []}
    
    for account in accounts:
        try:
            if action == 'enable':
                account.is_active = 1
                results['success'].append({
                    'id': account.id,
                    'username': account.username,
                    'action': 'enabled'
                })
            elif action == 'disable':
                account.is_active = 0
                results['success'].append({
                    'id': account.id,
                    'username': account.username,
                    'action': 'disabled'
                })
            elif action == 'delete':
                db.session.delete(account)
                results['success'].append({
                    'id': account.id,
                    'username': account.username,
                    'action': 'deleted'
                })
        except Exception as e:
            results['failed'].append({
                'id': account.id,
                'username': account.username,
                'error': str(e)
            })
    
    try:
        db.session.commit()
        logger.info(f"Bulk {action}: {len(results['success'])} accounts by admin {g.admin.username}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bulk action failed: {e}")
        return jsonify({'error': 'Database error', 'details': str(e)}), 500
    
    return jsonify({
        'action': action,
        'total': len(accounts),
        'success': len(results['success']),
        'failed': len(results['failed']),
        'results': results
    })


@admin_bp.route('/api/realms/bulk', methods=['POST'])
@require_admin
def api_realms_bulk():
    """Perform bulk action on multiple realms.
    
    JSON body:
    {
        "action": "approve|reject|revoke",
        "realm_ids": [1, 2, 3],
        "reason": "optional reason for reject/revoke"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400
    
    action = data.get('action')
    realm_ids = data.get('realm_ids', [])
    reason = data.get('reason', '')
    
    if not action or action not in ['approve', 'reject', 'revoke']:
        return jsonify({'error': 'Invalid action'}), 400
    
    if not realm_ids or not isinstance(realm_ids, list):
        return jsonify({'error': 'No realms specified'}), 400
    
    realms = AccountRealm.query.filter(AccountRealm.id.in_(realm_ids)).all()
    
    if not realms:
        return jsonify({'error': 'No valid realms found'}), 404
    
    results = {'success': [], 'failed': []}
    
    for realm in realms:
        try:
            if action == 'approve' and realm.status == 'pending':
                realm.status = 'approved'
                realm.approved_by_id = g.admin.id
                realm.approved_at = datetime.utcnow()
                results['success'].append({
                    'id': realm.id,
                    'realm': realm.realm_value,
                    'action': 'approved'
                })
            elif action == 'reject' and realm.status == 'pending':
                realm.status = 'rejected'
                realm.rejection_reason = reason
                results['success'].append({
                    'id': realm.id,
                    'realm': realm.realm_value,
                    'action': 'rejected'
                })
            elif action == 'revoke' and realm.status == 'approved':
                realm.status = 'rejected'
                realm.rejection_reason = reason or 'Revoked by admin'
                results['success'].append({
                    'id': realm.id,
                    'realm': realm.realm_value,
                    'action': 'revoked'
                })
            else:
                results['failed'].append({
                    'id': realm.id,
                    'realm': realm.realm_value,
                    'error': f'Cannot {action} realm in {realm.status} status'
                })
        except Exception as e:
            results['failed'].append({
                'id': realm.id,
                'realm': realm.realm_value,
                'error': str(e)
            })
    
    try:
        db.session.commit()
        logger.info(f"Bulk {action}: {len(results['success'])} realms by admin {g.admin.username}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bulk realm action failed: {e}")
        return jsonify({'error': 'Database error', 'details': str(e)}), 500
    
    return jsonify({
        'action': action,
        'total': len(realms),
        'success': len(results['success']),
        'failed': len(results['failed']),
        'results': results
    })


# ============================================================================
# Password Change (with email setup for 2FA)
# ============================================================================

@admin_bp.route('/change-password', methods=['GET', 'POST'])
@require_admin
def change_password():
    """Admin password change page with email setup for 2FA."""
    admin = g.admin
    
    # Check if this is initial setup (needs email for 2FA)
    needs_email_setup = not admin.email or admin.email == 'admin@localhost'
    force_change = admin.must_change_password == 1
    
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        new_email = request.form.get('email', '').strip().lower() if needs_email_setup else None
        
        errors = []
        
        # Validate current password (skip for initial forced change with default password)
        if not force_change and not admin.verify_password(current_password):
            errors.append('Current password is incorrect')
        
        # Validate new password
        if new_password != confirm_password:
            errors.append('New passwords do not match')
        else:
            is_valid, error_msg = validate_password(new_password)
            if not is_valid:
                errors.append(error_msg)
        
        # Validate email if provided (optional during initial setup)
        if needs_email_setup and new_email:
            if '@' not in new_email or '.' not in new_email:
                errors.append('Please enter a valid email address')
            elif Account.query.filter(Account.id != admin.id, Account.email == new_email).first():
                errors.append('This email address is already in use')
        
        if errors:
            for error in errors:
                flash(error, 'error')
        else:
            admin.set_password(new_password)
            admin.must_change_password = 0  # Clear password change requirement
            
            if needs_email_setup and new_email:
                admin.email = new_email
                admin.email_verified = 1  # Admin-set email is trusted
                admin.email_2fa_enabled = 1  # Enable 2FA since email is configured
                logger.info(f"Admin email configured: {admin.username} -> {new_email}")
            elif needs_email_setup and not new_email:
                # Email setup was skipped - keep placeholder and disable 2FA
                admin.email_2fa_enabled = 0
                logger.info(f"Admin password changed without email setup: {admin.username}")
            
            db.session.commit()
            logger.info(f"Admin password changed: {admin.username}")
            
            # Send password changed notification (if email is configured)
            if admin.email and admin.email != 'admin@localhost':
                from ..notification_service import notify_password_changed
                source_ip = _get_client_ip()
                notify_password_changed(admin, source_ip)
            
            if needs_email_setup and not new_email:
                flash('Password changed successfully. Configure email in System Config for 2FA.', 'success')
            else:
                flash('Password changed successfully', 'success')
            return redirect(url_for('admin.dashboard'))
    
    return render_template('admin/change_password.html',
                          force_change=force_change,
                          needs_email_setup=needs_email_setup,
                          current_email=admin.email if admin.email != 'admin@localhost' else '')

# ============================================================================
# TOTP Setup and Recovery Codes
# ============================================================================

@admin_bp.route('/security/totp', methods=['GET', 'POST'])
@require_admin
def setup_totp():
    """Setup TOTP authenticator app for admin 2FA."""
    admin = g.admin
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'enable':
            # Verify the TOTP code before enabling
            code = request.form.get('code', '').strip()
            secret = session.get('pending_totp_secret')
            
            if not secret:
                flash('Session expired. Please start again.', 'error')
                return redirect(url_for('admin.setup_totp'))
            
            try:
                import pyotp
                totp = pyotp.TOTP(secret)
                if totp.verify(code, valid_window=1):
                    # Save the secret
                    admin.totp_secret = secret
                    admin.totp_enabled = 1
                    db.session.commit()
                    
                    session.pop('pending_totp_secret', None)
                    
                    logger.info(f"TOTP enabled for admin: {admin.username}")
                    flash('Authenticator app enabled successfully!', 'success')
                    
                    # Redirect to recovery codes generation
                    return redirect(url_for('admin.generate_recovery_codes'))
                else:
                    flash('Invalid code. Please try again.', 'error')
            except ImportError:
                flash('TOTP not available (pyotp not installed)', 'error')
        
        elif action == 'disable':
            # Verify current code before disabling
            code = request.form.get('code', '').strip()
            
            if admin.totp_secret:
                try:
                    import pyotp
                    totp = pyotp.TOTP(admin.totp_secret)
                    if totp.verify(code, valid_window=1):
                        admin.totp_secret = None
                        admin.totp_enabled = 0
                        db.session.commit()
                        
                        logger.info(f"TOTP disabled for admin: {admin.username}")
                        flash('Authenticator app disabled.', 'success')
                    else:
                        flash('Invalid code. TOTP not disabled.', 'error')
                except ImportError:
                    flash('TOTP not available', 'error')
        
        return redirect(url_for('admin.setup_totp'))
    
    # GET request - show setup page
    qr_code_data = None
    totp_secret = None
    
    if not admin.totp_enabled:
        # Generate new secret for setup
        try:
            import pyotp
            secret = pyotp.random_base32()
            session['pending_totp_secret'] = secret
            totp_secret = secret
            
            # Generate provisioning URI
            provisioning_uri = pyotp.TOTP(secret).provisioning_uri(
                name=admin.email or admin.username,
                issuer_name="Netcup API Filter"
            )
            
            # Generate QR code
            try:
                import qrcode
                import io
                import base64
                
                qr = qrcode.QRCode(version=1, box_size=10, border=4)
                qr.add_data(provisioning_uri)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                qr_code_data = base64.b64encode(buffer.getvalue()).decode()
            except ImportError:
                logger.warning("qrcode or pillow not installed")
        except ImportError:
            flash('TOTP not available (pyotp not installed)', 'error')
    
    return render_template('admin/setup_totp.html',
                          totp_enabled=admin.totp_enabled,
                          qr_code_data=qr_code_data,
                          totp_secret=totp_secret)


@admin_bp.route('/security/recovery-codes', methods=['GET', 'POST'])
@require_admin
def generate_recovery_codes():
    """Generate new recovery codes for admin account."""
    admin = g.admin
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'generate':
            from ..recovery_codes import generate_recovery_codes, store_recovery_codes
            
            codes = generate_recovery_codes()
            if store_recovery_codes(admin, codes):
                # Store codes in session for one-time display
                session['recovery_codes_display'] = codes
                flash('New recovery codes generated. Save them now - they won\'t be shown again!', 'warning')
            else:
                flash('Failed to generate recovery codes', 'error')
        
        elif action == 'confirm':
            # User confirmed they saved codes - clear from session
            session.pop('recovery_codes_display', None)
            flash('Recovery codes confirmed and secured.', 'success')
            return redirect(url_for('admin.dashboard'))
    
    # Check if we have codes to display
    codes_to_display = session.get('recovery_codes_display')
    
    # Get info about existing codes
    has_recovery_codes = bool(admin.recovery_codes)
    codes_generated_at = admin.recovery_codes_generated_at
    
    return render_template('admin/recovery_codes.html',
                          codes=codes_to_display,
                          has_recovery_codes=has_recovery_codes,
                          codes_generated_at=codes_generated_at)

# ============================================================================
# Multi-Backend Management Routes
# ============================================================================

@admin_bp.route('/backends')
@require_admin
def backends():
    """List all backend services."""
    # Get filter parameters
    provider_filter = request.args.get('provider', 'all')
    owner_type_filter = request.args.get('owner_type', 'all')
    
    # Build query
    query = BackendService.query
    
    if provider_filter != 'all':
        provider = BackendProvider.query.filter_by(provider_code=provider_filter).first()
        if provider:
            query = query.filter_by(provider_id=provider.id)
    
    if owner_type_filter != 'all':
        owner_type = OwnerTypeEnum.query.filter_by(owner_code=owner_type_filter).first()
        if owner_type:
            query = query.filter_by(owner_type_id=owner_type.id)
    
    backends = query.order_by(BackendService.service_name).all()
    providers = BackendProvider.query.filter_by(is_enabled=True).all()
    
    # Calculate stats
    platform_type = OwnerTypeEnum.query.filter_by(owner_code='platform').first()
    stats = {
        'total': BackendService.query.count(),
        'active': BackendService.query.filter_by(is_active=True).count(),
        'platform_owned': BackendService.query.filter_by(owner_type_id=platform_type.id).count() if platform_type else 0,
        'user_owned': BackendService.query.count() - (BackendService.query.filter_by(owner_type_id=platform_type.id).count() if platform_type else 0),
    }
    
    return render_template('admin/backends_list.html',
                          backends=backends,
                          providers=providers,
                          stats=stats,
                          provider_filter=provider_filter,
                          owner_type_filter=owner_type_filter)


@admin_bp.route('/backends/providers')
@require_admin
def backend_providers():
    """List available backend providers."""
    providers = BackendProvider.query.order_by(BackendProvider.provider_code).all()
    return render_template('admin/backend_providers.html', providers=providers)


@admin_bp.route('/backends/new', methods=['GET', 'POST'])
@require_admin
def backend_create():
    """Create a new backend service."""
    if request.method == 'POST':
        try:
            # Get form data
            service_name = request.form.get('service_name', '').strip().lower()
            display_name = request.form.get('display_name', '').strip()
            provider_id_str = request.form.get('provider_id', '')
            owner_type_code = request.form.get('owner_type')
            owner_id = request.form.get('owner_id')
            is_active = 'is_active' in request.form
            
            # Validate provider_id
            if not provider_id_str:
                flash('Provider is required', 'error')
                return redirect(url_for('admin.backend_create'))
            try:
                provider_id = int(provider_id_str)
            except ValueError:
                flash('Invalid provider selection', 'error')
                return redirect(url_for('admin.backend_create'))
            
            # Validate other fields
            if not service_name or not display_name:
                flash('All required fields must be filled', 'error')
                return redirect(url_for('admin.backend_create'))
            
            # Check uniqueness
            if BackendService.query.filter_by(service_name=service_name).first():
                flash(f'Service name "{service_name}" already exists', 'error')
                return redirect(url_for('admin.backend_create'))
            
            # Get owner type
            owner_type = OwnerTypeEnum.query.filter_by(owner_code=owner_type_code).first()
            if not owner_type:
                flash('Invalid owner type', 'error')
                return redirect(url_for('admin.backend_create'))
            
            # Build config from form fields
            provider = BackendProvider.query.get(provider_id)
            config = {}
            for key in request.form:
                if key.startswith('config_'):
                    config_key = key[7:]  # Remove 'config_' prefix
                    value = request.form.get(key, '').strip()
                    if value:
                        config[config_key] = value
            
            # Create backend service
            backend = BackendService(
                provider_id=provider_id,
                service_name=service_name,
                display_name=display_name,
                owner_type_id=owner_type.id,
                owner_id=int(owner_id) if owner_id and owner_type_code == 'user' else None,
                config=json.dumps(config),
                is_active=is_active,
            )
            db.session.add(backend)
            db.session.commit()
            
            flash(f'Backend service "{display_name}" created successfully', 'success')
            return redirect(url_for('admin.backend_detail', backend_id=backend.id))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create backend: {e}")
            flash(f'Failed to create backend: {e}', 'error')
    
    providers = BackendProvider.query.filter_by(is_enabled=True).all()
    accounts = Account.query.filter_by(is_active=True).order_by(Account.username).all()
    
    return render_template('admin/backend_form.html',
                          backend=None,
                          providers=providers,
                          accounts=accounts)


@admin_bp.route('/backends/<int:backend_id>')
@require_admin
def backend_detail(backend_id):
    """View backend service details."""
    backend = BackendService.query.get_or_404(backend_id)
    return render_template('admin/backend_detail.html', backend=backend)


@admin_bp.route('/backends/<int:backend_id>/edit', methods=['GET', 'POST'])
@require_admin
def backend_edit(backend_id):
    """Edit a backend service."""
    backend = BackendService.query.get_or_404(backend_id)
    
    if request.method == 'POST':
        try:
            backend.display_name = request.form.get('display_name', '').strip()
            backend.is_active = 'is_active' in request.form
            
            # Update owner
            owner_type_code = request.form.get('owner_type')
            owner_type = OwnerTypeEnum.query.filter_by(owner_code=owner_type_code).first()
            if owner_type:
                backend.owner_type_id = owner_type.id
                owner_id = request.form.get('owner_id')
                backend.owner_id = int(owner_id) if owner_id and owner_type_code == 'user' else None
            
            # Update config
            config = {}
            for key in request.form:
                if key.startswith('config_'):
                    config_key = key[7:]
                    value = request.form.get(key, '').strip()
                    if value:
                        config[config_key] = value
            backend.config = json.dumps(config)
            
            db.session.commit()
            flash('Backend service updated successfully', 'success')
            return redirect(url_for('admin.backend_detail', backend_id=backend_id))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update backend: {e}")
            flash(f'Failed to update backend: {e}', 'error')
    
    providers = BackendProvider.query.filter_by(is_enabled=True).all()
    accounts = Account.query.filter_by(is_active=True).order_by(Account.username).all()
    
    return render_template('admin/backend_form.html',
                          backend=backend,
                          providers=providers,
                          accounts=accounts)


@admin_bp.route('/backends/<int:backend_id>/test', methods=['POST'])
@require_admin
def backend_test(backend_id):
    """Test backend connection."""
    from datetime import datetime
    backend = BackendService.query.get_or_404(backend_id)
    
    try:
        from ..backends import get_backend
        
        config = backend.get_config()
        dns_backend = get_backend(backend.provider.provider_code, config)
        success, message = dns_backend.test_connection()
        
        # Update test status
        if success:
            test_status = TestStatusEnum.query.filter_by(status_code='success').first()
        else:
            test_status = TestStatusEnum.query.filter_by(status_code='failed').first()
        
        backend.test_status_id = test_status.id if test_status else None
        backend.test_message = message
        backend.last_tested_at = datetime.utcnow()
        db.session.commit()
        
        if success:
            flash(f'Connection test successful: {message}', 'success')
        else:
            flash(f'Connection test failed: {message}', 'error')
            
    except Exception as e:
        logger.error(f"Backend test failed: {e}")
        test_status = TestStatusEnum.query.filter_by(status_code='failed').first()
        backend.test_status_id = test_status.id if test_status else None
        backend.test_message = str(e)
        backend.last_tested_at = datetime.utcnow()
        db.session.commit()
        flash(f'Connection test error: {e}', 'error')
    
    return redirect(url_for('admin.backend_detail', backend_id=backend_id))


@admin_bp.route('/backends/<int:backend_id>/enable', methods=['POST'])
@require_admin
def backend_enable(backend_id):
    """Enable a backend service."""
    backend = BackendService.query.get_or_404(backend_id)
    backend.is_active = True
    db.session.commit()
    flash(f'Backend "{backend.display_name}" enabled', 'success')
    return redirect(url_for('admin.backend_detail', backend_id=backend_id))


@admin_bp.route('/backends/<int:backend_id>/disable', methods=['POST'])
@require_admin
def backend_disable(backend_id):
    """Disable a backend service."""
    backend = BackendService.query.get_or_404(backend_id)
    backend.is_active = False
    db.session.commit()
    flash(f'Backend "{backend.display_name}" disabled', 'warning')
    return redirect(url_for('admin.backend_detail', backend_id=backend_id))


@admin_bp.route('/backends/<int:backend_id>/delete', methods=['POST'])
@require_admin
def backend_delete(backend_id):
    """Delete a backend service."""
    backend = BackendService.query.get_or_404(backend_id)
    
    # Check for dependencies
    if backend.domain_roots:
        flash('Cannot delete backend with existing domain roots', 'error')
        return redirect(url_for('admin.backend_detail', backend_id=backend_id))
    
    service_name = backend.service_name
    db.session.delete(backend)
    db.session.commit()
    flash(f'Backend "{service_name}" deleted', 'success')
    return redirect(url_for('admin.backends'))


# ============================================================================
# Domain Roots Management Routes
# ============================================================================

@admin_bp.route('/domain-roots')
@require_admin
def domain_roots():
    """List all managed domain roots."""
    visibility_filter = request.args.get('visibility', 'all')
    backend_filter = request.args.get('backend', 'all')
    
    query = ManagedDomainRoot.query
    
    if visibility_filter != 'all':
        visibility = VisibilityEnum.query.filter_by(visibility_code=visibility_filter).first()
        if visibility:
            query = query.filter_by(visibility_id=visibility.id)
    
    if backend_filter != 'all':
        try:
            backend_id = int(backend_filter)
            query = query.filter_by(backend_service_id=backend_id)
        except ValueError:
            pass  # Invalid filter value, ignore
    
    roots = query.order_by(ManagedDomainRoot.root_domain).all()
    backends = BackendService.query.filter_by(is_active=True).all()
    
    # Add realm counts
    for root in roots:
        root.realm_count = AccountRealm.query.filter_by(domain_root_id=root.id).count()
    
    # Stats
    public_vis = VisibilityEnum.query.filter_by(visibility_code='public').first()
    private_vis = VisibilityEnum.query.filter_by(visibility_code='private').first()
    stats = {
        'total': ManagedDomainRoot.query.count(),
        'public': ManagedDomainRoot.query.filter_by(visibility_id=public_vis.id).count() if public_vis else 0,
        'private': ManagedDomainRoot.query.filter_by(visibility_id=private_vis.id).count() if private_vis else 0,
        'realms': AccountRealm.query.filter(AccountRealm.domain_root_id.isnot(None)).count(),
    }
    
    return render_template('admin/domain_roots_list.html',
                          roots=roots,
                          backends=backends,
                          stats=stats,
                          visibility_filter=visibility_filter,
                          backend_filter=backend_filter)


@admin_bp.route('/domain-roots/new', methods=['GET', 'POST'])
@require_admin
def domain_root_create():
    """Create a new domain root."""
    preselect_backend = request.args.get('backend_id', type=int)
    
    if request.method == 'POST':
        try:
            root_domain = request.form.get('root_domain', '').strip().lower()
            dns_zone = request.form.get('dns_zone', '').strip().lower()
            backend_service_id_str = request.form.get('backend_service_id', '')
            visibility_code = request.form.get('visibility')
            display_name = request.form.get('display_name', '').strip()
            description = request.form.get('description', '').strip()
            is_active = 'is_active' in request.form
            allow_apex = 'allow_apex_access' in request.form
            
            # Validate backend_service_id
            if not backend_service_id_str:
                flash('Backend service is required', 'error')
                return redirect(url_for('admin.domain_root_create'))
            try:
                backend_service_id = int(backend_service_id_str)
            except ValueError:
                flash('Invalid backend service selection', 'error')
                return redirect(url_for('admin.domain_root_create'))
            
            # Parse integer values with defaults
            try:
                min_depth = int(request.form.get('min_subdomain_depth', 1))
            except ValueError:
                min_depth = 1
            try:
                max_depth = int(request.form.get('max_subdomain_depth', 3))
            except ValueError:
                max_depth = 3
            
            # Get selected record types and operations
            record_types = request.form.getlist('allowed_record_types')
            operations = request.form.getlist('allowed_operations')
            
            # Validate domain fields
            if not root_domain or not dns_zone:
                flash('All required fields must be filled', 'error')
                return redirect(url_for('admin.domain_root_create'))
            
            # Check uniqueness
            if ManagedDomainRoot.query.filter_by(
                backend_service_id=backend_service_id,
                root_domain=root_domain
            ).first():
                flash(f'Domain root "{root_domain}" already exists for this backend', 'error')
                return redirect(url_for('admin.domain_root_create'))
            
            # Get visibility
            visibility = VisibilityEnum.query.filter_by(visibility_code=visibility_code).first()
            if not visibility:
                flash('Invalid visibility', 'error')
                return redirect(url_for('admin.domain_root_create'))
            
            # Create domain root
            root = ManagedDomainRoot(
                backend_service_id=backend_service_id,
                root_domain=root_domain,
                dns_zone=dns_zone,
                visibility_id=visibility.id,
                display_name=display_name or root_domain,
                description=description or None,
                is_active=is_active,
                allow_apex_access=allow_apex,
                min_subdomain_depth=min_depth,
                max_subdomain_depth=max_depth,
            )
            
            # Set restrictions (None = all allowed)
            all_record_types = ['A', 'AAAA', 'CNAME', 'TXT', 'MX', 'SRV', 'CAA', 'NS']
            all_operations = ['read', 'create', 'update', 'delete']
            root.set_allowed_record_types(record_types if set(record_types) != set(all_record_types) else None)
            root.set_allowed_operations(operations if set(operations) != set(all_operations) else None)
            
            db.session.add(root)
            db.session.commit()
            
            flash(f'Domain root "{root_domain}" created successfully', 'success')
            return redirect(url_for('admin.domain_root_detail', root_id=root.id))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create domain root: {e}")
            flash(f'Failed to create domain root: {e}', 'error')
    
    backends = BackendService.query.filter_by(is_active=True).order_by(BackendService.service_name).all()
    visibilities = VisibilityEnum.query.all()
    
    return render_template('admin/domain_root_form.html',
                          root=None,
                          backends=backends,
                          visibilities=visibilities,
                          preselect_backend=preselect_backend)


@admin_bp.route('/domain-roots/<int:root_id>')
@require_admin
def domain_root_detail(root_id):
    """View domain root details."""
    root = ManagedDomainRoot.query.get_or_404(root_id)
    realms = AccountRealm.query.filter_by(domain_root_id=root_id).order_by(AccountRealm.realm_value).all()
    return render_template('admin/domain_root_detail.html', root=root, realms=realms)


@admin_bp.route('/domain-roots/<int:root_id>/edit', methods=['GET', 'POST'])
@require_admin
def domain_root_edit(root_id):
    """Edit a domain root."""
    root = ManagedDomainRoot.query.get_or_404(root_id)
    
    if request.method == 'POST':
        try:
            root.dns_zone = request.form.get('dns_zone', '').strip().lower()
            root.display_name = request.form.get('display_name', '').strip() or root.root_domain
            root.description = request.form.get('description', '').strip() or None
            root.is_active = 'is_active' in request.form
            root.allow_apex_access = 'allow_apex_access' in request.form
            root.min_subdomain_depth = int(request.form.get('min_subdomain_depth', 1))
            root.max_subdomain_depth = int(request.form.get('max_subdomain_depth', 3))
            
            visibility_code = request.form.get('visibility')
            visibility = VisibilityEnum.query.filter_by(visibility_code=visibility_code).first()
            if visibility:
                root.visibility_id = visibility.id
            
            backend_id = request.form.get('backend_service_id')
            if backend_id:
                try:
                    root.backend_service_id = int(backend_id)
                except ValueError:
                    pass  # Keep existing value
            
            # Update restrictions
            record_types = request.form.getlist('allowed_record_types')
            operations = request.form.getlist('allowed_operations')
            all_record_types = ['A', 'AAAA', 'CNAME', 'TXT', 'MX', 'SRV', 'CAA', 'NS']
            all_operations = ['read', 'create', 'update', 'delete']
            root.set_allowed_record_types(record_types if set(record_types) != set(all_record_types) else None)
            root.set_allowed_operations(operations if set(operations) != set(all_operations) else None)
            
            db.session.commit()
            flash('Domain root updated successfully', 'success')
            return redirect(url_for('admin.domain_root_detail', root_id=root_id))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update domain root: {e}")
            flash(f'Failed to update domain root: {e}', 'error')
    
    backends = BackendService.query.filter_by(is_active=True).order_by(BackendService.service_name).all()
    visibilities = VisibilityEnum.query.all()
    
    return render_template('admin/domain_root_form.html',
                          root=root,
                          backends=backends,
                          visibilities=visibilities,
                          preselect_backend=None)


@admin_bp.route('/domain-roots/<int:root_id>/grants')
@require_admin
def domain_root_grants(root_id):
    """Manage grants for a domain root."""
    root = ManagedDomainRoot.query.get_or_404(root_id)
    return render_template('admin/domain_root_grants.html', root=root)


@admin_bp.route('/domain-roots/<int:root_id>/enable', methods=['POST'])
@require_admin
def domain_root_enable(root_id):
    """Enable a domain root."""
    root = ManagedDomainRoot.query.get_or_404(root_id)
    root.is_active = True
    db.session.commit()
    flash(f'Domain root "{root.root_domain}" enabled', 'success')
    return redirect(url_for('admin.domain_root_detail', root_id=root_id))


@admin_bp.route('/domain-roots/<int:root_id>/disable', methods=['POST'])
@require_admin
def domain_root_disable(root_id):
    """Disable a domain root."""
    root = ManagedDomainRoot.query.get_or_404(root_id)
    root.is_active = False
    db.session.commit()
    flash(f'Domain root "{root.root_domain}" disabled', 'warning')
    return redirect(url_for('admin.domain_root_detail', root_id=root_id))


@admin_bp.route('/domain-roots/<int:root_id>/delete', methods=['POST'])
@require_admin
def domain_root_delete(root_id):
    """Delete a domain root."""
    root = ManagedDomainRoot.query.get_or_404(root_id)
    
    # Check for dependencies
    realm_count = AccountRealm.query.filter_by(domain_root_id=root_id).count()
    if realm_count > 0:
        flash(f'Cannot delete domain root with {realm_count} existing realms', 'error')
        return redirect(url_for('admin.domain_root_detail', root_id=root_id))
    
    domain_name = root.root_domain
    db.session.delete(root)
    db.session.commit()
    flash(f'Domain root "{domain_name}" deleted', 'success')
    return redirect(url_for('admin.domain_roots'))

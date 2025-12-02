"""
Account Portal Blueprint.

Routes:
- /account/login - Login page
- /account/login/2fa - 2FA verification
- /account/register - Registration
- /account/register/verify - Email verification
- /account/dashboard - Main dashboard (realms + tokens)
- /account/settings - Account settings
- /account/realms/<id>/tokens/new - Create token
- /account/tokens/<id>/activity - Token activity
"""
import logging
from datetime import datetime, timedelta
from flask import (
    Blueprint, flash, g, jsonify, redirect, render_template,
    request, session, url_for
)

from ..account_auth import (
    change_password,
    create_session,
    get_current_account,
    is_authenticated,
    login_step1,
    logout,
    register_account,
    require_account_auth,
    resend_verification,
    send_2fa_code,
    verify_2fa,
    verify_registration,
)
from ..models import Account, AccountRealm, ActivityLog, APIToken, RegistrationRequest, db
from ..realm_token_service import (
    create_token,
    get_realms_for_account,
    get_token_activity,
    get_tokens_for_realm,
    request_realm as request_realm_service,
    revoke_token,
    update_token,
)

logger = logging.getLogger(__name__)

account_bp = Blueprint('account', __name__, url_prefix='/account')


# ============================================================================
# Login / Logout
# ============================================================================

@account_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page - step 1: username + password."""
    if is_authenticated():
        return redirect(url_for('account.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        result = login_step1(username, password, request.remote_addr)
        
        if result.success:
            # Redirect to 2FA
            return redirect(url_for('account.login_2fa'))
        else:
            flash(result.error, 'error')
    
    return render_template('account/login.html')


@account_bp.route('/login/2fa', methods=['GET', 'POST'])
def login_2fa():
    """Login page - step 2: 2FA verification."""
    # Check for pending 2FA
    account_id = session.get('2fa_pending')
    if not account_id:
        return redirect(url_for('account.login'))
    
    account = Account.query.get(account_id)
    if not account:
        session.clear()
        return redirect(url_for('account.login'))
    
    # Determine available 2FA methods
    tfa_methods = []
    if account.email_2fa_enabled:
        tfa_methods.append('email')
    if account.totp_enabled:
        tfa_methods.append('totp')
    if account.telegram_enabled:
        tfa_methods.append('telegram')
    
    if request.method == 'GET':
        # Default to email if available
        method = request.args.get('method', 'email')
        if method in tfa_methods and method != 'totp':
            # Send code for non-TOTP methods
            success, error = send_2fa_code(account_id, method, request.remote_addr)
            if not success:
                flash(error, 'error')
    
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        
        result = verify_2fa(code, request.remote_addr)
        
        if result.success:
            flash('Login successful', 'success')
            return redirect(url_for('account.dashboard'))
        else:
            flash(result.error, 'error')
    
    return render_template('account/login_2fa.html', 
                          account=account, 
                          tfa_methods=tfa_methods,
                          masked_email=mask_email(account.email))


@account_bp.route('/logout')
def account_logout():
    """Logout and clear session."""
    logout()
    flash('You have been logged out', 'info')
    return redirect(url_for('account.login'))


# ============================================================================
# Registration
# ============================================================================

@account_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page."""
    if is_authenticated():
        return redirect(url_for('account.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validate passwords match
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('account/register.html')
        
        result = register_account(username, email, password)
        
        if result.success:
            session['registration_id'] = result.request_id
            return redirect(url_for('account.verify_email'))
        else:
            flash(result.error, 'error')
    
    return render_template('account/register.html')


@account_bp.route('/register/verify', methods=['GET', 'POST'])
def verify_email():
    """Email verification page."""
    request_id = session.get('registration_id')
    if not request_id:
        return redirect(url_for('account.register'))
    
    reg_request = RegistrationRequest.query.get(request_id)
    if not reg_request:
        session.pop('registration_id', None)
        return redirect(url_for('account.register'))
    
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        
        result = verify_registration(request_id, code)
        
        if result.success:
            session.pop('registration_id', None)
            flash('Email verified! Your account is pending admin approval.', 'success')
            return redirect(url_for('account.pending'))
        else:
            flash(result.error, 'error')
    
    return render_template('account/verify_email.html', 
                          email=reg_request.email,
                          expires_minutes=30)


@account_bp.route('/register/resend', methods=['POST'])
def resend_code():
    """Resend verification code."""
    request_id = session.get('registration_id')
    if not request_id:
        return redirect(url_for('account.register'))
    
    result = resend_verification(request_id)
    
    if result.success:
        flash('Verification code resent', 'success')
    else:
        flash(result.error, 'error')
    
    return redirect(url_for('account.verify_email'))


@account_bp.route('/register/pending')
def pending():
    """Pending approval page."""
    return render_template('account/pending.html')


# ============================================================================
# Dashboard
# ============================================================================

@account_bp.route('/dashboard')
@require_account_auth
def dashboard():
    """Main dashboard showing realms and tokens."""
    account = g.account
    
    # Get all realms with their tokens
    realms = get_realms_for_account(account)
    
    # Build realm data with token counts
    realm_data = []
    for realm in realms:
        tokens = get_tokens_for_realm(realm) if realm.status == 'approved' else []
        active_tokens = [t for t in tokens if t.is_active]
        realm_data.append({
            'realm': realm,
            'tokens': tokens,
            'active_count': len(active_tokens),
            'total_count': len(tokens)
        })
    
    return render_template('account/dashboard.html',
                          account=account,
                          realm_data=realm_data)


# ============================================================================
# Realm Management
# ============================================================================

@account_bp.route('/realms/request', methods=['GET', 'POST'])
@require_account_auth
def request_realm_view():
    """Request a new realm."""
    account = g.account
    
    if request.method == 'POST':
        domain = request.form.get('domain', '').strip().lower()
        realm_type = request.form.get('realm_type', '')
        realm_value = request.form.get('realm_value', '').strip().lower()
        record_types = request.form.getlist('record_types')
        operations = request.form.getlist('operations')
        
        result = request_realm_service(
            account=account,
            domain=domain,
            realm_type=realm_type,
            realm_value=realm_value,
            record_types=record_types,
            operations=operations
        )
        
        if result.success:
            flash('Realm request submitted. Awaiting admin approval.', 'success')
            return redirect(url_for('account.dashboard'))
        else:
            flash(result.error, 'error')
    
    return render_template('account/request_realm.html')


# ============================================================================
# Token Management
# ============================================================================

@account_bp.route('/realms/<int:realm_id>/tokens/new', methods=['GET', 'POST'])
@require_account_auth
def create_new_token(realm_id):
    """Create a new token for a realm."""
    account = g.account
    
    # Get realm and verify ownership
    realm = AccountRealm.query.get_or_404(realm_id)
    if realm.account_id != account.id:
        flash('Access denied', 'error')
        return redirect(url_for('account.dashboard'))
    
    if realm.status != 'approved':
        flash('Cannot create tokens for unapproved realms', 'error')
        return redirect(url_for('account.dashboard'))
    
    if request.method == 'POST':
        token_name = request.form.get('token_name', '').strip()
        description = request.form.get('description', '').strip() or None
        record_types = request.form.getlist('record_types') or None
        operations = request.form.getlist('operations') or None
        ip_ranges_str = request.form.get('ip_ranges', '').strip()
        ip_ranges = [ip.strip() for ip in ip_ranges_str.split('\n') if ip.strip()] or None
        
        expires_option = request.form.get('expires', 'never')
        expires_at = None
        if expires_option == '1month':
            expires_at = datetime.utcnow() + timedelta(days=30)
        elif expires_option == '3months':
            expires_at = datetime.utcnow() + timedelta(days=90)
        elif expires_option == '1year':
            expires_at = datetime.utcnow() + timedelta(days=365)
        elif expires_option == 'custom':
            custom_date = request.form.get('expires_custom', '')
            if custom_date:
                try:
                    expires_at = datetime.strptime(custom_date, '%Y-%m-%d')
                except ValueError:
                    flash('Invalid date format', 'error')
                    return render_template('account/create_token.html', realm=realm)
        
        result = create_token(
            realm=realm,
            token_name=token_name,
            description=description,
            record_types=record_types,
            operations=operations,
            ip_ranges=ip_ranges,
            expires_at=expires_at
        )
        
        if result.success:
            # Show success page with token (one time only)
            return render_template('account/token_created.html',
                                  token=result.token_obj,
                                  token_plain=result.token_plain,
                                  realm=realm)
        else:
            flash(result.error, 'error')
    
    return render_template('account/create_token.html', realm=realm)


@account_bp.route('/tokens/<int:token_id>/revoke', methods=['POST'])
@require_account_auth
def revoke_user_token(token_id):
    """Revoke a token."""
    account = g.account
    
    token = APIToken.query.get_or_404(token_id)
    realm = token.realm
    
    # Verify ownership
    if realm.account_id != account.id:
        flash('Access denied', 'error')
        return redirect(url_for('account.dashboard'))
    
    reason = request.form.get('reason', 'User revoked')
    result = revoke_token(token_id, account, reason)
    
    if result.success:
        flash(f'Token "{token.token_name}" revoked', 'success')
    else:
        flash(result.error, 'error')
    
    return redirect(url_for('account.dashboard'))


@account_bp.route('/tokens/<int:token_id>/activity')
@require_account_auth
def token_activity(token_id):
    """View token activity timeline."""
    account = g.account
    
    token = APIToken.query.get_or_404(token_id)
    realm = token.realm
    
    # Verify ownership
    if realm.account_id != account.id:
        flash('Access denied', 'error')
        return redirect(url_for('account.dashboard'))
    
    # Get activity
    activity = get_token_activity(token, limit=100)
    
    return render_template('account/token_activity.html',
                          token=token,
                          realm=realm,
                          activity=activity)


# ============================================================================
# Settings
# ============================================================================

@account_bp.route('/settings', methods=['GET', 'POST'])
@require_account_auth
def settings():
    """Account settings page."""
    account = g.account
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            notification_email = request.form.get('notification_email', '').strip() or None
            account.notification_email = notification_email
            account.notify_new_ip = int(request.form.get('notify_new_ip', '0'))
            account.notify_failed_auth = int(request.form.get('notify_failed_auth', '0'))
            account.notify_token_expiring = int(request.form.get('notify_token_expiring', '0'))
            db.session.commit()
            flash('Settings updated', 'success')
        
        elif action == 'change_password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            if new_password != confirm_password:
                flash('Passwords do not match', 'error')
            else:
                success, error = change_password(account, current_password, new_password)
                if success:
                    flash('Password changed successfully', 'success')
                else:
                    flash(error, 'error')
    
    return render_template('account/settings.html', account=account)


# ============================================================================
# API Endpoints
# ============================================================================

@account_bp.route('/api/realms')
@require_account_auth
def api_realms():
    """Get account's realms as JSON."""
    account = g.account
    realms = get_realms_for_account(account)
    
    return jsonify([{
        'id': r.id,
        'realm_type': r.realm_type,
        'realm_value': r.realm_value,
        'status': r.status,
        'record_types': r.get_allowed_record_types(),
        'operations': r.get_allowed_operations(),
    } for r in realms])


@account_bp.route('/api/realms/<int:realm_id>/tokens')
@require_account_auth
def api_realm_tokens(realm_id):
    """Get tokens for a realm as JSON."""
    account = g.account
    realm = AccountRealm.query.get_or_404(realm_id)
    
    if realm.account_id != account.id:
        return jsonify({'error': 'Access denied'}), 403
    
    tokens = get_tokens_for_realm(realm)
    
    return jsonify([{
        'id': t.id,
        'name': t.token_name,
        'description': t.token_description,
        'is_active': bool(t.is_active),
        'last_used_at': t.last_used_at.isoformat() if t.last_used_at else None,
        'use_count': t.use_count,
        'expires_at': t.expires_at.isoformat() if t.expires_at else None,
    } for t in tokens])


# ============================================================================
# Realms and Tokens List Views
# ============================================================================

@account_bp.route('/realms')
@require_account_auth
def realms():
    """View all realms."""
    account = g.account
    realms = get_realms_for_account(account)
    return render_template('account/realms.html', account=account, realms=realms)


@account_bp.route('/tokens')
@require_account_auth
def tokens():
    """View all tokens across all realms."""
    account = g.account
    realms = get_realms_for_account(account)
    
    # Get all tokens from all approved realms
    all_tokens = []
    for realm in realms:
        if realm.status == 'approved':
            tokens_for_realm = get_tokens_for_realm(realm, include_revoked=True)
            all_tokens.extend(tokens_for_realm)
    
    return render_template('account/tokens.html', 
                          account=account, 
                          tokens=all_tokens)


@account_bp.route('/tokens/new', methods=['GET', 'POST'])
@require_account_auth
def create_token_select():
    """Create token - select realm first if not specified."""
    account = g.account
    realm_id = request.args.get('realm_id', type=int)
    
    if realm_id:
        # Redirect to realm-specific token creation
        return redirect(url_for('account.create_new_token', realm_id=realm_id))
    
    # Show realm selection
    realms = [r for r in get_realms_for_account(account) if r.status == 'approved']
    
    if len(realms) == 1:
        # Only one approved realm, go directly to token creation
        return redirect(url_for('account.create_new_token', realm_id=realms[0].id))
    
    return render_template('account/create_token.html', 
                          realm=None, 
                          realms=realms)


# ============================================================================
# 2FA Management
# ============================================================================

@account_bp.route('/2fa/verify', methods=['POST'])
def verify_2fa_code():
    """Verify 2FA code during login."""
    account_id = session.get('2fa_pending')
    if not account_id:
        return redirect(url_for('account.login'))
    
    code = request.form.get('code', '').strip()
    result = verify_2fa(code, request.remote_addr)
    
    if result.success:
        flash('Login successful', 'success')
        return redirect(url_for('account.dashboard'))
    else:
        flash(result.error, 'error')
        return redirect(url_for('account.login_2fa'))


@account_bp.route('/2fa/resend', methods=['POST'])
def resend_2fa_code():
    """Resend 2FA code."""
    account_id = session.get('2fa_pending')
    if not account_id:
        return redirect(url_for('account.login'))
    
    method = request.form.get('method', 'email')
    success, error = send_2fa_code(account_id, method, request.remote_addr)
    
    if success:
        flash(f'Verification code sent via {method}', 'success')
    else:
        flash(error, 'error')
    
    return redirect(url_for('account.login_2fa', method=method))


@account_bp.route('/settings/totp/setup', methods=['GET', 'POST'])
@require_account_auth
def setup_totp():
    """Setup TOTP for account."""
    account = g.account
    
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        secret = session.get('totp_setup_secret')
        
        if not secret:
            flash('Please start TOTP setup again', 'error')
            return redirect(url_for('account.settings'))
        
        # Verify code against pending secret
        import pyotp
        totp = pyotp.TOTP(secret)
        if totp.verify(code):
            account.totp_secret = secret
            account.totp_enabled = 1
            db.session.commit()
            session.pop('totp_setup_secret', None)
            flash('TOTP enabled successfully', 'success')
            return redirect(url_for('account.settings'))
        else:
            flash('Invalid code. Please try again.', 'error')
    
    # Generate new secret for setup
    import pyotp
    secret = pyotp.random_base32()
    session['totp_setup_secret'] = secret
    
    # Generate QR code URI
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=account.email,
        issuer_name='Netcup API Filter'
    )
    
    return render_template('account/setup_totp.html',
                          account=account,
                          secret=secret,
                          provisioning_uri=provisioning_uri)


@account_bp.route('/settings/telegram/link', methods=['GET', 'POST'])
@require_account_auth
def link_telegram():
    """Link Telegram for 2FA."""
    account = g.account
    
    if request.method == 'POST':
        telegram_id = request.form.get('telegram_id', '').strip()
        
        if not telegram_id or not telegram_id.isdigit():
            flash('Invalid Telegram ID', 'error')
        else:
            account.telegram_id = telegram_id
            account.telegram_enabled = 1
            db.session.commit()
            flash('Telegram linked successfully', 'success')
            return redirect(url_for('account.settings'))
    
    return render_template('account/link_telegram.html', account=account)


# ============================================================================
# API Documentation
# ============================================================================

@account_bp.route('/docs')
@require_account_auth
def api_docs():
    """API documentation page."""
    account = g.account
    return render_template('account/api_docs.html', account=account)


# ============================================================================
# Aliases for template compatibility
# ============================================================================

# These route names align with template url_for() calls

@account_bp.route('/realms/new', methods=['GET', 'POST'])
@require_account_auth
def request_realm():
    """Alias for request_realm_view."""
    return request_realm_view()


# Make url_for('account.create_token') work for templates
create_token_view = create_token_select


# ============================================================================
# Helpers
# ============================================================================

def mask_email(email: str) -> str:
    """Mask email for display: j***@example.com"""
    if not email or '@' not in email:
        return '***'
    local, domain = email.rsplit('@', 1)
    if len(local) <= 2:
        masked_local = local[0] + '***'
    else:
        masked_local = local[0] + '***' + local[-1]
    return f'{masked_local}@{domain}'

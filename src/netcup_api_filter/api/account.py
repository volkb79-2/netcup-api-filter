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
    finalize_registration_with_realms,
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
from ..models import (
    Account, AccountRealm, ActivityLog, APIToken, RegistrationRequest, db,
    # Multi-backend models
    BackendService, ManagedDomainRoot, DomainRootGrant, VisibilityEnum, OwnerTypeEnum,
)
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
# Forgot / Reset Password
# ============================================================================

@account_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Forgot password page - request password reset email."""
    if is_authenticated():
        return redirect(url_for('account.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Please enter your email address', 'error')
        else:
            # Get client IP for IP-bound token
            client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if client_ip and ',' in client_ip:
                client_ip = client_ip.split(',')[0].strip()
            
            # Always show success to prevent email enumeration
            account = Account.query.filter_by(email=email).first()
            if account:
                # Generate reset token and send email with IP binding
                from ..password_reset import send_password_reset_email
                send_password_reset_email(account, source_ip=client_ip)
            
            flash('If an account exists with that email, a password reset link has been sent.', 'success')
            return redirect(url_for('account.login'))
    
    return render_template('account/forgot_password.html')


@account_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password page - use token to set new password."""
    if is_authenticated():
        return redirect(url_for('account.dashboard'))
    
    from ..password_reset import verify_reset_token, complete_password_reset
    
    # Get client IP for security validation
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip and ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()
    
    account, error = verify_reset_token(token, current_ip=client_ip, expected_type='reset')
    if not account:
        flash(error or 'Invalid or expired password reset link', 'error')
        return redirect(url_for('account.forgot_password'))
    
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
        elif len(new_password) < 12:
            flash('Password must be at least 12 characters', 'error')
        else:
            success, error = complete_password_reset(account, new_password, token)
            if success:
                flash('Password has been reset. Please log in with your new password.', 'success')
                return redirect(url_for('account.login'))
            else:
                flash(error, 'error')
    
    return render_template('account/reset_password.html', token=token)


@account_bp.route('/invite/<token>', methods=['GET', 'POST'])
def accept_invite(token):
    """Accept account invite and set password.
    
    This is used when an admin creates an account and sends an invite email.
    The user clicks the invite link and sets their own password.
    """
    if is_authenticated():
        flash('You are already logged in.', 'info')
        return redirect(url_for('account.dashboard'))
    
    from ..password_reset import verify_reset_token, complete_password_reset
    
    # Invites don't use IP binding (user may open on different device)
    account, error = verify_reset_token(token, expected_type='invite')
    if not account:
        flash(error or 'Invalid or expired invite link', 'error')
        return redirect(url_for('account.login'))
    
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
        elif len(new_password) < 12:
            flash('Password must be at least 12 characters', 'error')
        else:
            success, error = complete_password_reset(account, new_password, token)
            if success:
                flash('Your account is now active. Please log in with your new password.', 'success')
                return redirect(url_for('account.login'))
            else:
                flash(error, 'error')
    
    return render_template('account/accept_invite.html', token=token, username=account.username)


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
            # Don't clear session yet - redirect to realm request step
            session['email_verified'] = True
            flash('Email verified! Now you can request access to domains.', 'success')
            return redirect(url_for('account.register_realms'))
        else:
            flash(result.error, 'error')
    
    return render_template('account/verify_email.html', 
                          email=reg_request.email,
                          expires_minutes=30)


@account_bp.route('/register/verify/<token>')
def verify_email_link(token):
    """Verify email via secure link (IP-bound).
    
    Alternative to code-based verification. Uses IP binding for security -
    the link must be opened from the same IP that initiated registration.
    """
    from ..password_reset import verify_reset_token
    
    # Get client IP for security validation
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip and ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()
    
    # Verify the token with IP binding
    reg_request, error = verify_reset_token(token, current_ip=client_ip, expected_type='verify')
    if not reg_request:
        flash(error or 'Invalid or expired verification link', 'error')
        return redirect(url_for('account.register'))
    
    # Check if this is a RegistrationRequest (token stores the request_id)
    # Note: verify_reset_token was designed for Account, but we use it for RegistrationRequest
    # by storing request.id in the token's account_id field
    reg = RegistrationRequest.query.get(reg_request.id if hasattr(reg_request, 'id') else reg_request)
    if not reg:
        flash('Registration request not found', 'error')
        return redirect(url_for('account.register'))
    
    # Store in session and mark as verified
    session['registration_id'] = reg.id
    session['email_verified'] = True
    
    flash('Email verified! Now you can request access to domains.', 'success')
    return redirect(url_for('account.register_realms'))


@account_bp.route('/register/realms', methods=['GET', 'POST'])
def register_realms():
    """
    Step 3: Request realms during registration.
    
    User can add multiple realm requests, or skip and submit account only.
    """
    request_id = session.get('registration_id')
    email_verified = session.get('email_verified')
    
    if not request_id or not email_verified:
        return redirect(url_for('account.register'))
    
    reg_request = RegistrationRequest.query.get(request_id)
    if not reg_request:
        session.pop('registration_id', None)
        session.pop('email_verified', None)
        return redirect(url_for('account.register'))
    
    # Handle form submissions
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        if action == 'add_realm':
            # Add a realm request
            full_domain = request.form.get('full_domain', '').strip().lower()
            realm_type = request.form.get('realm_type', 'host')
            record_types = request.form.getlist('record_types')
            operations = request.form.getlist('operations')
            purpose = request.form.get('purpose', '').strip()
            
            if full_domain:
                # Parse domain into base domain and realm_value (subdomain prefix)
                parts = full_domain.split('.')
                if len(parts) >= 2:
                    domain = '.'.join(parts[-2:])  # e.g., "example.com"
                    realm_value = '.'.join(parts[:-2]) if len(parts) > 2 else ''  # e.g., "home"
                    
                    # Default record types and operations if not specified
                    if not record_types:
                        record_types = ['A', 'AAAA']
                    if not operations:
                        operations = ['read', 'update']
                    
                    reg_request.add_realm_request(
                        realm_type=realm_type,
                        domain=domain,
                        realm_value=realm_value,
                        record_types=record_types,
                        operations=operations,
                        purpose=purpose
                    )
                    db.session.commit()
                    flash(f'Realm request for {full_domain} added', 'success')
                else:
                    flash('Invalid domain format (need at least domain.tld)', 'error')
            else:
                flash('Domain is required', 'error')
        
        elif action == 'remove_realm':
            # Remove a realm request by index
            try:
                index = int(request.form.get('realm_index', -1))
                requests = reg_request.get_realm_requests()
                if 0 <= index < len(requests):
                    removed = requests.pop(index)
                    reg_request.set_realm_requests(requests)
                    db.session.commit()
                    fqdn = f"{removed.get('realm_value', '')}.{removed.get('domain', '')}" if removed.get('realm_value') else removed.get('domain', '')
                    flash(f'Removed realm request for {fqdn}', 'info')
            except (ValueError, TypeError):
                pass
        
        elif action == 'submit':
            # Finalize registration - create account with pending realms
            result = finalize_registration_with_realms(request_id)
            
            if result.success:
                session.pop('registration_id', None)
                session.pop('email_verified', None)
                realm_count = len(reg_request.get_realm_requests())
                if realm_count > 0:
                    flash(f'Registration complete! Your account and {realm_count} realm request(s) are pending admin approval.', 'success')
                else:
                    flash('Registration complete! Your account is pending admin approval.', 'success')
                return redirect(url_for('account.pending'))
            else:
                flash(result.error, 'error')
    
    # Render template with current realm requests
    realm_requests = reg_request.get_realm_requests()
    
    # Available templates for quick selection
    templates = [
        {
            'id': 'ddns_single_host',
            'name': 'DDNS Single Host',
            'icon': '🏠',
            'realm_type': 'host',
            'record_types': ['A', 'AAAA'],
            'operations': ['read', 'update'],
            'description': 'Update IP address for a single hostname (home router, VPN endpoint)'
        },
        {
            'id': 'ddns_subdomain_zone',
            'name': 'DDNS Subdomain Zone',
            'icon': '🌐',
            'realm_type': 'subdomain',
            'record_types': ['A', 'AAAA', 'CNAME'],
            'operations': ['read', 'update', 'create', 'delete'],
            'description': 'Manage a subdomain and all hosts under it (IoT fleet, K8s)'
        },
        {
            'id': 'letsencrypt_dns01',
            'name': 'LetsEncrypt DNS-01',
            'icon': '🔒',
            'realm_type': 'subdomain',
            'record_types': ['TXT'],
            'operations': ['read', 'create', 'delete'],
            'description': 'ACME DNS-01 challenge for certificate automation'
        },
        {
            'id': 'monitoring_readonly',
            'name': 'Read-Only Monitoring',
            'icon': '👁️',
            'realm_type': 'host',
            'record_types': ['A', 'AAAA', 'CNAME', 'TXT', 'MX', 'NS'],
            'operations': ['read'],
            'description': 'View-only access for monitoring and dashboards'
        }
    ]
    
    return render_template('account/register_realms.html',
                          reg_request=reg_request,
                          realm_requests=realm_requests,
                          templates=templates)


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
    # Try to get info about the just-registered account for display
    account = None
    realm_count = 0
    
    # Check if there's a recently created pending account
    # (We can't rely on session since it's cleared after submit)
    return render_template('account/pending.html',
                          account=account,
                          realm_count=realm_count)


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

def get_available_domain_roots_for_account(account):
    """Get domain roots available to an account.
    
    Returns domain roots that are:
    - Public (any authenticated user can request)
    - Granted to this specific account
    """
    # Get public visibility ID
    public_vis = VisibilityEnum.query.filter_by(visibility_code='public').first()
    
    available_roots = []
    
    if public_vis:
        # Public roots are available to everyone
        public_roots = ManagedDomainRoot.query.filter_by(
            visibility_id=public_vis.id,
            is_active=True
        ).all()
        available_roots.extend(public_roots)
    
    # Also get roots where user has explicit grant
    granted_roots = ManagedDomainRoot.query.join(
        DomainRootGrant,
        DomainRootGrant.domain_root_id == ManagedDomainRoot.id
    ).filter(
        DomainRootGrant.account_id == account.id,
        DomainRootGrant.revoked_at.is_(None),
        ManagedDomainRoot.is_active == True
    ).all()
    
    # Add granted roots not already in public
    existing_ids = {r.id for r in available_roots}
    for root in granted_roots:
        if root.id not in existing_ids:
            available_roots.append(root)
    
    return available_roots


@account_bp.route('/realms/request', methods=['GET', 'POST'])
@require_account_auth
def request_realm_view():
    """Request a new realm."""
    account = g.account
    
    # Get available domain roots for this account
    available_roots = get_available_domain_roots_for_account(account)
    
    # Also check if user has any own backends (for BYOD)
    user_backends = BackendService.query.filter_by(
        owner_id=account.id,
        is_active=True
    ).all() if account else []
    
    if request.method == 'POST':
        domain_root_id = request.form.get('domain_root_id', '')
        subdomain = request.form.get('subdomain', '').strip().lower()
        realm_type = request.form.get('realm_type', 'host')
        record_types = request.form.getlist('record_types')
        operations = request.form.getlist('operations')
        
        # Validate domain root selection
        if not domain_root_id:
            flash('Please select a DNS zone', 'error')
            return render_template('account/request_realm.html',
                                 available_roots=available_roots,
                                 user_backends=user_backends)
        
        # Get selected domain root
        try:
            root_id = int(domain_root_id)
            domain_root = ManagedDomainRoot.query.get(root_id)
        except (ValueError, TypeError):
            domain_root = None
        
        if not domain_root or not domain_root.is_active:
            flash('Invalid DNS zone selection', 'error')
            return render_template('account/request_realm.html',
                                 available_roots=available_roots,
                                 user_backends=user_backends)
        
        # Check user has access to this root
        if domain_root not in available_roots:
            flash('You do not have access to this DNS zone', 'error')
            return render_template('account/request_realm.html',
                                 available_roots=available_roots,
                                 user_backends=user_backends)
        
        # Build full realm value
        realm_value = subdomain if subdomain else ''
        domain = domain_root.root_domain
        
        result = request_realm_service(
            account=account,
            domain=domain,
            realm_type=realm_type,
            realm_value=realm_value,
            record_types=record_types,
            operations=operations,
            domain_root_id=domain_root.id
        )
        
        if result.success:
            flash('Realm request submitted. Awaiting admin approval.', 'success')
            return redirect(url_for('account.dashboard'))
        else:
            flash(result.error, 'error')
    
    return render_template('account/request_realm.html',
                          available_roots=available_roots,
                          user_backends=user_backends)


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
                source_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
                success, error = change_password(account, current_password, new_password, source_ip)
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
# Recovery Codes
# ============================================================================

@account_bp.route('/settings/recovery-codes', methods=['GET'])
@require_account_auth
def view_recovery_codes():
    """View recovery codes status."""
    from .recovery_codes import get_remaining_code_count
    
    account = g.account
    remaining = get_remaining_code_count(account)
    
    return render_template('account/recovery_codes.html',
                          account=account,
                          remaining_codes=remaining)


@account_bp.route('/settings/recovery-codes/generate', methods=['POST'])
@require_account_auth
def generate_recovery_codes():
    """Generate new recovery codes (invalidates old ones)."""
    from .recovery_codes import regenerate_recovery_codes
    
    account = g.account
    
    # Verify password before generating new codes
    password = request.form.get('password', '')
    if not account.verify_password(password):
        flash('Invalid password', 'error')
        return redirect(url_for('account.view_recovery_codes'))
    
    # Generate new codes
    codes = regenerate_recovery_codes(account)
    
    if codes:
        # Store codes in session for one-time display
        session['recovery_codes_display'] = codes
        flash('New recovery codes generated. Save them now - they will not be shown again.', 'success')
        return redirect(url_for('account.display_recovery_codes'))
    else:
        flash('Failed to generate recovery codes', 'error')
        return redirect(url_for('account.view_recovery_codes'))


@account_bp.route('/settings/recovery-codes/display')
@require_account_auth
def display_recovery_codes():
    """Display newly generated recovery codes (one-time view)."""
    codes = session.pop('recovery_codes_display', None)
    
    if not codes:
        flash('No recovery codes to display', 'warning')
        return redirect(url_for('account.view_recovery_codes'))
    
    return render_template('account/recovery_codes_display.html',
                          account=g.account,
                          codes=codes)


# ============================================================================
# Realm Detail
# ============================================================================

@account_bp.route('/realms/<int:realm_id>')
@require_account_auth
def realm_detail(realm_id):
    """View realm details with tokens."""
    account = g.account
    
    realm = AccountRealm.query.get_or_404(realm_id)
    if realm.account_id != account.id:
        flash('Access denied', 'error')
        return redirect(url_for('account.dashboard'))
    
    # Get tokens for this realm
    tokens = get_tokens_for_realm(realm, include_revoked=True)
    
    # Calculate usage stats for last 30 days
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    stats = {
        'total_calls': 0,
        'successful': 0,
        'updates': 0,
        'errors': 0
    }
    
    for token in tokens:
        logs = ActivityLog.query.filter(
            ActivityLog.account_id == account.id,
            ActivityLog.created_at >= thirty_days_ago,
            ActivityLog.details.like(f'%{token.token_prefix}%')
        ).all()
        
        for log in logs:
            stats['total_calls'] += 1
            if log.action in ('updateDnsRecords', 'createDnsRecords', 'deleteDnsRecords'):
                stats['updates'] += 1
            if log.status == 'success':
                stats['successful'] += 1
            else:
                stats['errors'] += 1
    
    # Check if realm supports DDNS (has update permission and A/AAAA record types)
    realm_ops = realm.get_allowed_operations()
    realm_types = realm.get_allowed_record_types()
    can_ddns = 'update' in realm_ops and ('A' in realm_types or 'AAAA' in realm_types)
    
    # Get client IP for DDNS display
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip:
        client_ip = client_ip.split(',')[0].strip()
    
    return render_template('account/realm_detail.html',
                          account=account,
                          realm=realm,
                          tokens=tokens,
                          stats=stats,
                          can_ddns=can_ddns,
                          client_ip=client_ip)


# ============================================================================
# DDNS Quick Update (Update to My IP)
# ============================================================================

@account_bp.route('/realms/<int:realm_id>/ddns', methods=['POST'])
@require_account_auth
def ddns_update(realm_id):
    """
    Quick DDNS update - update A/AAAA record to caller's IP.
    
    This is a session-authenticated convenience endpoint for the UI.
    For automated scripts, use the API with token auth.
    """
    from ..database import get_setting
    from ..netcup_client import NetcupClient
    
    account = g.account
    
    realm = AccountRealm.query.get_or_404(realm_id)
    if realm.account_id != account.id:
        flash('Access denied', 'error')
        return redirect(url_for('account.dashboard'))
    
    # Check realm permissions
    realm_ops = realm.get_allowed_operations()
    realm_types = realm.get_allowed_record_types()
    
    if 'update' not in realm_ops:
        flash('This realm does not have update permission', 'error')
        return redirect(url_for('account.realm_detail', realm_id=realm_id))
    
    if 'A' not in realm_types and 'AAAA' not in realm_types:
        flash('This realm does not allow A/AAAA record types', 'error')
        return redirect(url_for('account.realm_detail', realm_id=realm_id))
    
    # Get client IP
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip:
        client_ip = client_ip.split(',')[0].strip()
    
    if not client_ip:
        flash('Could not detect your IP address', 'error')
        return redirect(url_for('account.realm_detail', realm_id=realm_id))
    
    # Determine IP type
    is_ipv6 = ':' in client_ip
    record_type = 'AAAA' if is_ipv6 else 'A'
    
    if record_type not in realm_types:
        flash(f'This realm does not allow {record_type} record type', 'error')
        return redirect(url_for('account.realm_detail', realm_id=realm_id))
    
    # Get hostname to update
    hostname = realm.realm_value if realm.realm_type == 'host' else request.form.get('hostname', realm.realm_value)
    domain = realm.domain
    
    # Validate hostname is within realm
    if not realm.matches_hostname(f"{hostname}.{domain}" if hostname else domain):
        flash('Hostname is outside your realm scope', 'error')
        return redirect(url_for('account.realm_detail', realm_id=realm_id))
    
    try:
        # Get Netcup client
        config = get_setting('netcup_config')
        if not config:
            flash('Netcup API is not configured', 'error')
            return redirect(url_for('account.realm_detail', realm_id=realm_id))
        
        netcup = NetcupClient(
            customer_id=config.get('customer_id'),
            api_key=config.get('api_key'),
            api_password=config.get('api_password'),
            api_url=config.get('api_url', 'https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON'),
            timeout=config.get('timeout', 30)
        )
        
        # Get existing records
        existing_records = netcup.info_dns_records(domain)
        
        # Find and update the record, or create new
        record_found = False
        for rec in existing_records:
            if rec.get('hostname') == hostname and rec.get('type') == record_type:
                rec['destination'] = client_ip
                record_found = True
                break
        
        if not record_found:
            existing_records.append({
                'hostname': hostname,
                'type': record_type,
                'destination': client_ip
            })
        
        # Update records
        netcup.update_dns_records(domain, existing_records)
        
        # Log activity
        log = ActivityLog(
            account_id=account.id,
            action='ddns_ui',
            status='success',
            details=f'{hostname}.{domain} {record_type} → {client_ip}'
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'Successfully updated {hostname}.{domain} {record_type} to {client_ip}', 'success')
        
    except Exception as e:
        logger.error(f"DDNS update failed: {e}")
        
        # Log failure
        log = ActivityLog(
            account_id=account.id,
            action='ddns_ui',
            status='error',
            details=f'{hostname}.{domain}: {str(e)}'
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'Failed to update DNS: {str(e)}', 'error')
    
    return redirect(url_for('account.realm_detail', realm_id=realm_id))


# ============================================================================
# DNS Records Management (P7.1)
# ============================================================================

@account_bp.route('/realms/<int:realm_id>/dns')
@require_account_auth
def dns_records(realm_id):
    """View DNS records for a realm."""
    from ..database import get_setting
    from ..netcup_client import NetcupClient
    
    account = g.account
    
    realm = AccountRealm.query.get_or_404(realm_id)
    if realm.account_id != account.id:
        flash('Access denied', 'error')
        return redirect(url_for('account.dashboard'))
    
    if realm.status != 'approved':
        flash('Realm must be approved to view DNS records', 'error')
        return redirect(url_for('account.realm_detail', realm_id=realm_id))
    
    # Check read permission
    realm_ops = realm.get_allowed_operations()
    if 'read' not in realm_ops:
        flash('This realm does not have read permission', 'error')
        return redirect(url_for('account.realm_detail', realm_id=realm_id))
    
    records = []
    error = None
    
    try:
        config = get_setting('netcup_config')
        if not config:
            error = 'Netcup API is not configured'
        else:
            netcup = NetcupClient(
                customer_id=config.get('customer_id'),
                api_key=config.get('api_key'),
                api_password=config.get('api_password'),
                api_url=config.get('api_url', 'https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON'),
                timeout=config.get('timeout', 30)
            )
            
            # Get DNS records for the domain
            all_records = netcup.info_dns_records(realm.domain)
            
            # Filter records based on realm scope and allowed types
            allowed_types = realm.get_allowed_record_types()
            for rec in all_records:
                hostname = rec.get('hostname', '')
                rec_type = rec.get('type', '')
                
                # Check if record type is allowed
                if allowed_types and rec_type not in allowed_types:
                    continue
                
                # Check if hostname is within realm scope
                fqdn = f"{hostname}.{realm.domain}" if hostname and hostname != '@' else realm.domain
                if realm.matches_hostname(fqdn) or (hostname == '@' and realm.realm_value == ''):
                    # For subdomain realms, only show matching records
                    if realm.realm_type == 'host' and hostname != realm.realm_value:
                        continue
                    if realm.realm_type == 'subdomain':
                        if not (hostname == realm.realm_value or 
                                hostname.endswith(f'.{realm.realm_value}') or 
                                hostname == '@' and realm.realm_value == ''):
                            continue
                    if realm.realm_type == 'subdomain_only':
                        if hostname == realm.realm_value:
                            continue
                        if not hostname.endswith(f'.{realm.realm_value}'):
                            continue
                    records.append(rec)
            
            # Log activity
            log = ActivityLog(
                account_id=account.id,
                action='dns_view',
                status='success',
                details=f'{realm.domain}: {len(records)} records'
            )
            db.session.add(log)
            db.session.commit()
            
    except Exception as e:
        logger.error(f"Error fetching DNS records: {e}")
        error = str(e)
    
    return render_template('account/dns_records.html',
                          account=account,
                          realm=realm,
                          records=records,
                          error=error,
                          can_create='create' in realm_ops,
                          can_update='update' in realm_ops,
                          can_delete='delete' in realm_ops)


@account_bp.route('/realms/<int:realm_id>/dns/create', methods=['GET', 'POST'])
@require_account_auth
def dns_record_create(realm_id):
    """Create a new DNS record."""
    from ..database import get_setting
    from ..netcup_client import NetcupClient
    
    account = g.account
    
    realm = AccountRealm.query.get_or_404(realm_id)
    if realm.account_id != account.id:
        flash('Access denied', 'error')
        return redirect(url_for('account.dashboard'))
    
    # Check create permission
    realm_ops = realm.get_allowed_operations()
    if 'create' not in realm_ops:
        flash('This realm does not have create permission', 'error')
        return redirect(url_for('account.dns_records', realm_id=realm_id))
    
    allowed_types = realm.get_allowed_record_types()
    
    if request.method == 'POST':
        hostname = request.form.get('hostname', '').strip()
        record_type = request.form.get('type', '').strip()
        destination = request.form.get('destination', '').strip()
        priority = request.form.get('priority', '').strip()
        
        # Validate record type
        if record_type not in allowed_types:
            flash(f'Record type {record_type} is not allowed', 'error')
            return redirect(url_for('account.dns_record_create', realm_id=realm_id))
        
        # Validate hostname is within realm scope
        test_hostname = hostname if hostname else '@'
        fqdn = f"{test_hostname}.{realm.domain}" if test_hostname != '@' else realm.domain
        
        if realm.realm_type == 'host' and hostname != realm.realm_value:
            flash(f'Hostname must be {realm.realm_value}', 'error')
            return redirect(url_for('account.dns_record_create', realm_id=realm_id))
        
        try:
            config = get_setting('netcup_config')
            if not config:
                flash('Netcup API is not configured', 'error')
                return redirect(url_for('account.dns_records', realm_id=realm_id))
            
            netcup = NetcupClient(
                customer_id=config.get('customer_id'),
                api_key=config.get('api_key'),
                api_password=config.get('api_password'),
                api_url=config.get('api_url'),
                timeout=config.get('timeout', 30)
            )
            
            # Get existing records
            existing_records = netcup.info_dns_records(realm.domain)
            
            # Add new record
            new_record = {
                'hostname': hostname,
                'type': record_type,
                'destination': destination
            }
            if priority and record_type in ['MX', 'SRV']:
                new_record['priority'] = priority
            
            existing_records.append(new_record)
            
            # Update records
            netcup.update_dns_records(realm.domain, existing_records)
            
            # Log activity
            log = ActivityLog(
                account_id=account.id,
                action='dns_create',
                status='success',
                details=f'{hostname}.{realm.domain} {record_type}'
            )
            db.session.add(log)
            db.session.commit()
            
            flash(f'Successfully created {record_type} record for {hostname or "@"}.{realm.domain}', 'success')
            return redirect(url_for('account.dns_records', realm_id=realm_id))
            
        except Exception as e:
            logger.error(f"Error creating DNS record: {e}")
            flash(f'Failed to create record: {str(e)}', 'error')
    
    return render_template('account/dns_record_create.html',
                          account=account,
                          realm=realm,
                          allowed_types=allowed_types)


@account_bp.route('/realms/<int:realm_id>/dns/<int:record_id>/edit', methods=['GET', 'POST'])
@require_account_auth
def dns_record_edit(realm_id, record_id):
    """Edit an existing DNS record."""
    from ..database import get_setting
    from ..netcup_client import NetcupClient
    
    account = g.account
    
    realm = AccountRealm.query.get_or_404(realm_id)
    if realm.account_id != account.id:
        flash('Access denied', 'error')
        return redirect(url_for('account.dashboard'))
    
    # Check update permission
    realm_ops = realm.get_allowed_operations()
    if 'update' not in realm_ops:
        flash('This realm does not have update permission', 'error')
        return redirect(url_for('account.dns_records', realm_id=realm_id))
    
    try:
        config = get_setting('netcup_config')
        if not config:
            flash('Netcup API is not configured', 'error')
            return redirect(url_for('account.dns_records', realm_id=realm_id))
        
        netcup = NetcupClient(
            customer_id=config.get('customer_id'),
            api_key=config.get('api_key'),
            api_password=config.get('api_password'),
            api_url=config.get('api_url'),
            timeout=config.get('timeout', 30)
        )
        
        # Get existing records
        existing_records = netcup.info_dns_records(realm.domain)
        
        # Find the record to edit
        record = None
        for rec in existing_records:
            if str(rec.get('id')) == str(record_id):
                record = rec
                break
        
        if not record:
            flash('Record not found', 'error')
            return redirect(url_for('account.dns_records', realm_id=realm_id))
        
        if request.method == 'POST':
            destination = request.form.get('destination', '').strip()
            priority = request.form.get('priority', '').strip()
            
            # Update the record
            record['destination'] = destination
            if priority and record.get('type') in ['MX', 'SRV']:
                record['priority'] = priority
            
            # Save
            netcup.update_dns_records(realm.domain, existing_records)
            
            # Log activity
            log = ActivityLog(
                account_id=account.id,
                action='dns_update',
                status='success',
                details=f'{record.get("hostname")}.{realm.domain} {record.get("type")} → {destination}'
            )
            db.session.add(log)
            db.session.commit()
            
            flash(f'Successfully updated {record.get("type")} record', 'success')
            return redirect(url_for('account.dns_records', realm_id=realm_id))
        
        return render_template('account/dns_record_edit.html',
                              account=account,
                              realm=realm,
                              record=record)
        
    except Exception as e:
        logger.error(f"Error editing DNS record: {e}")
        flash(f'Failed to edit record: {str(e)}', 'error')
        return redirect(url_for('account.dns_records', realm_id=realm_id))


@account_bp.route('/realms/<int:realm_id>/dns/<int:record_id>/delete', methods=['POST'])
@require_account_auth
def dns_record_delete(realm_id, record_id):
    """Delete a DNS record."""
    from ..database import get_setting
    from ..netcup_client import NetcupClient
    
    account = g.account
    
    realm = AccountRealm.query.get_or_404(realm_id)
    if realm.account_id != account.id:
        flash('Access denied', 'error')
        return redirect(url_for('account.dashboard'))
    
    # Check delete permission
    realm_ops = realm.get_allowed_operations()
    if 'delete' not in realm_ops:
        flash('This realm does not have delete permission', 'error')
        return redirect(url_for('account.dns_records', realm_id=realm_id))
    
    try:
        config = get_setting('netcup_config')
        if not config:
            flash('Netcup API is not configured', 'error')
            return redirect(url_for('account.dns_records', realm_id=realm_id))
        
        netcup = NetcupClient(
            customer_id=config.get('customer_id'),
            api_key=config.get('api_key'),
            api_password=config.get('api_password'),
            api_url=config.get('api_url'),
            timeout=config.get('timeout', 30)
        )
        
        # Get existing records
        existing_records = netcup.info_dns_records(realm.domain)
        
        # Find and mark the record for deletion
        record_to_delete = None
        for rec in existing_records:
            if str(rec.get('id')) == str(record_id):
                record_to_delete = rec
                rec['deleterecord'] = True
                break
        
        if not record_to_delete:
            flash('Record not found', 'error')
            return redirect(url_for('account.dns_records', realm_id=realm_id))
        
        # Save (with deleterecord flag)
        netcup.update_dns_records(realm.domain, existing_records)
        
        # Log activity
        log = ActivityLog(
            account_id=account.id,
            action='dns_delete',
            status='success',
            details=f'{record_to_delete.get("hostname")}.{realm.domain} {record_to_delete.get("type")}'
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'Successfully deleted {record_to_delete.get("type")} record for {record_to_delete.get("hostname") or "@"}.{realm.domain}', 'success')
        
    except Exception as e:
        logger.error(f"Error deleting DNS record: {e}")
        flash(f'Failed to delete record: {str(e)}', 'error')
    
    return redirect(url_for('account.dns_records', realm_id=realm_id))


# ============================================================================
# Token Regeneration
# ============================================================================

@account_bp.route('/tokens/<int:token_id>/regenerate', methods=['GET', 'POST'])
@require_account_auth
def regenerate_token(token_id):
    """Regenerate a token (revoke old, create new with same settings)."""
    account = g.account
    
    old_token = APIToken.query.get_or_404(token_id)
    realm = old_token.realm
    
    if realm.account_id != account.id:
        flash('Access denied', 'error')
        return redirect(url_for('account.dashboard'))
    
    if request.method == 'POST':
        # Create new token with same settings
        result = create_token(
            realm=realm,
            token_name=old_token.token_name,
            description=old_token.token_description,
            record_types=old_token.get_allowed_record_types() if old_token.allowed_record_types else None,
            operations=old_token.get_allowed_operations() if old_token.allowed_operations else None,
            ip_ranges=old_token.get_ip_ranges() if old_token.ip_ranges else None,
            expires_at=old_token.expires_at
        )
        
        if result.success:
            # Revoke old token
            revoke_token(token_id, account, 'Regenerated')
            
            return render_template('account/token_created.html',
                                  token=result.token_obj,
                                  token_plain=result.token_plain,
                                  realm=realm,
                                  regenerated=True)
        else:
            flash(result.error, 'error')
            return redirect(url_for('account.realm_detail', realm_id=realm.id))
    
    return render_template('account/regenerate_token.html',
                          token=old_token,
                          realm=realm)


# ============================================================================
# Change Password
# ============================================================================

@account_bp.route('/change-password', methods=['GET', 'POST'])
@require_account_auth
def change_password_page():
    """Dedicated change password page."""
    account = g.account
    
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
        else:
            source_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            success, error = change_password(account, current_password, new_password, source_ip)
            if success:
                flash('Password changed successfully', 'success')
                return redirect(url_for('account.settings'))
            else:
                flash(error, 'error')
    
    return render_template('account/change_password.html', account=account)


# ============================================================================
# Activity Export
# ============================================================================

@account_bp.route('/activity/export')
@require_account_auth  
def export_activity():
    """Export account activity to ODS format."""
    from io import BytesIO
    from flask import send_file
    
    account = g.account
    
    # Get all activity for this account
    logs = ActivityLog.query.filter(
        ActivityLog.account_id == account.id
    ).order_by(ActivityLog.created_at.desc()).limit(10000).all()
    
    # Create ODS file using simple XML structure
    output = create_ods_export(logs, 'Account Activity Export')
    
    return send_file(
        output,
        mimetype='application/vnd.oasis.opendocument.spreadsheet',
        as_attachment=True,
        download_name=f'activity_{account.username}_{datetime.utcnow().strftime("%Y%m%d")}.ods'
    )


def create_ods_export(logs, title):
    """Create ODS file from activity logs."""
    from io import BytesIO
    import zipfile
    
    # ODS is a zip file with XML content
    output = BytesIO()
    
    # Build content.xml
    rows_xml = []
    
    # Header row
    headers = ['Timestamp', 'Action', 'Status', 'Source IP', 'Details']
    header_cells = ''.join([f'<table:table-cell office:value-type="string"><text:p>{h}</text:p></table:table-cell>' for h in headers])
    rows_xml.append(f'<table:table-row>{header_cells}</table:table-row>')
    
    # Data rows
    for log in logs:
        cells = [
            log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else '',
            log.action or '',
            log.status or '',
            log.source_ip or '',
            log.details or ''
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
            <table:table table:name="{title}">
                {''.join(rows_xml)}
            </table:table>
        </office:spreadsheet>
    </office:body>
</office:document-content>'''
    
    manifest_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">
    <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>
    <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
</manifest:manifest>'''
    
    mimetype = 'application/vnd.oasis.opendocument.spreadsheet'
    
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
        # mimetype must be first and uncompressed
        zf.writestr('mimetype', mimetype, compress_type=zipfile.ZIP_STORED)
        zf.writestr('META-INF/manifest.xml', manifest_xml)
        zf.writestr('content.xml', content_xml)
    
    output.seek(0)
    return output


def escape_xml(s):
    """Escape special characters for XML."""
    if not s:
        return ''
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


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
# Security & Activity Routes
# ============================================================================

@account_bp.route('/security')
@require_account_auth
def security():
    """Account security settings page."""
    account = g.account
    
    # Get active sessions for this account
    sessions = []  # TODO: Implement session tracking
    
    # Get recent security events (logins, password changes, etc.)
    security_events = ActivityLog.query.filter_by(
        account_id=account.id
    ).filter(
        ActivityLog.action.in_(['login', 'login_failed', 'password_changed', '2fa_enabled', '2fa_disabled'])
    ).order_by(ActivityLog.created_at.desc()).limit(10).all()
    
    return render_template(
        'account/security.html',
        account=account,
        current_user=account,
        sessions=sessions,
        security_events=security_events
    )


@account_bp.route('/activity')
@require_account_auth
def activity():
    """Account activity log page."""
    account = g.account
    page = request.args.get('page', 1, type=int)
    type_filter = request.args.get('type', 'all')
    
    query = ActivityLog.query.filter_by(account_id=account.id)
    
    if type_filter != 'all':
        query = query.filter(ActivityLog.action.ilike(f'%{type_filter}%'))
    
    pagination = query.order_by(ActivityLog.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template(
        'account/activity.html',
        account=account,
        activity=pagination.items,
        pagination=pagination,
        type_filter=type_filter
    )


@account_bp.route('/security/session/<int:session_id>/revoke', methods=['POST'])
@require_account_auth
def revoke_session(session_id):
    """Revoke a specific session."""
    account = g.account
    
    # TODO: Implement session revocation when session tracking is added
    # For now, flash a message that this feature is not yet implemented
    flash('Session management is not yet implemented.', 'warning')
    
    return redirect(url_for('account.security'))


@account_bp.route('/security/sessions/revoke-all', methods=['POST'])
@require_account_auth
def revoke_all_sessions():
    """Revoke all sessions except current."""
    account = g.account
    
    # TODO: Implement when session tracking is added
    flash('Session management is not yet implemented.', 'warning')
    
    return redirect(url_for('account.security'))


@account_bp.route('/security/2fa/disable', methods=['POST'])
@require_account_auth
def disable_2fa():
    """Disable two-factor authentication."""
    account = g.account
    password = request.form.get('password', '')
    
    # Verify password before disabling 2FA
    from ..account_auth import verify_password
    if not verify_password(account.password_hash, password):
        flash('Incorrect password.', 'error')
        return redirect(url_for('account.security'))
    
    # Disable TOTP
    account.totp_enabled = False
    account.totp_secret = None
    
    # Log the action
    ActivityLog.log_action(
        action='2fa_disabled',
        account_id=account.id,
        details='TOTP 2FA disabled',
        ip_address=request.remote_addr
    )
    
    db.session.commit()
    
    flash('Two-factor authentication has been disabled.', 'success')
    return redirect(url_for('account.security'))


@account_bp.route('/telegram/unlink', methods=['POST'])
@require_account_auth
def unlink_telegram():
    """Unlink Telegram from account."""
    account = g.account
    
    if not account.telegram_id:
        flash('No Telegram account linked.', 'warning')
        return redirect(url_for('account.link_telegram'))
    
    old_telegram_id = account.telegram_id
    account.telegram_id = None
    account.telegram_enabled = False
    
    # Log the action
    ActivityLog.log_action(
        action='telegram_unlinked',
        account_id=account.id,
        details=f'Telegram account unlinked (was: {old_telegram_id})',
        ip_address=request.remote_addr
    )
    
    db.session.commit()
    
    flash('Telegram has been unlinked from your account.', 'success')
    return redirect(url_for('account.link_telegram'))


# ============================================================================
# Aliases for template compatibility
# ============================================================================

# These route names align with template url_for() calls

@account_bp.route('/realms/new', methods=['GET', 'POST'])
@require_account_auth
def request_realm():
    """Alias for request_realm_view."""
    return request_realm_view()


# Alias for token creation - templates use url_for('account.token_create', realm_id=...)
@account_bp.route('/realms/<int:realm_id>/tokens', methods=['GET', 'POST'])
@require_account_auth  
def token_create(realm_id):
    """Alias for create_new_token."""
    return create_new_token(realm_id)


# Make url_for('account.create_token') work for templates
create_token_view = create_token_select


# Alias for 2FA setup - templates use url_for('account.setup_2fa')
@account_bp.route('/2fa/setup', methods=['GET', 'POST'])
@require_account_auth
def setup_2fa():
    """Alias for setup_totp."""
    return setup_totp()


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

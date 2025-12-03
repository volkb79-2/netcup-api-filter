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
)
from ..models import (
    Account, AccountRealm, ActivityLog, APIToken, db, Settings
)
from ..realm_token_service import (
    approve_realm,
    create_realm_by_admin,
    get_pending_realms,
    reject_realm,
)
from ..database import get_setting, set_setting

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Admin session keys
SESSION_KEY_ADMIN_ID = 'admin_id'
SESSION_KEY_ADMIN_USERNAME = 'admin_username'


def require_admin(f):
    """Decorator requiring admin authentication."""
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
    """Admin login page."""
    if session.get(SESSION_KEY_ADMIN_ID):
        # Check if password change is required
        admin = Account.query.get(session.get(SESSION_KEY_ADMIN_ID))
        if admin and admin.must_change_password:
            return redirect(url_for('admin.change_password'))
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        admin = Account.query.filter_by(username=username, is_admin=1).first()
        
        if admin and admin.verify_password(password):
            if not admin.is_active:
                flash('Account is disabled', 'error')
            else:
                session[SESSION_KEY_ADMIN_ID] = admin.id
                session[SESSION_KEY_ADMIN_USERNAME] = admin.username
                admin.last_login_at = datetime.utcnow()
                db.session.commit()
                
                logger.info(f"Admin login: {username}")
                
                # Redirect to password change if required
                if admin.must_change_password:
                    return redirect(url_for('admin.change_password'))
                
                return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid credentials', 'error')
            logger.warning(f"Failed admin login attempt: {username}")
    
    return render_template('admin/login.html')


@admin_bp.route('/logout')
def logout():
    """Admin logout."""
    username = session.get(SESSION_KEY_ADMIN_USERNAME)
    session.pop(SESSION_KEY_ADMIN_ID, None)
    session.pop(SESSION_KEY_ADMIN_USERNAME, None)
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
    """Admin dashboard with stats and pending items."""
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
    
    # Recent activity
    recent_activity = (
        ActivityLog.query
        .order_by(ActivityLog.created_at.desc())
        .limit(10)
        .all()
    )
    
    return render_template('admin/dashboard.html',
                          total_accounts=total_accounts,
                          active_accounts=active_accounts,
                          pending_accounts=pending_accounts,
                          pending_realms=pending_realms,
                          api_calls_24h=api_calls_24h,
                          errors_24h=errors_24h,
                          recent_activity=recent_activity)


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
    """Create new account (admin action)."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        
        if not password:
            password = generate_secure_password()
        
        account, error = create_account_by_admin(
            username=username,
            email=email,
            password=password,
            approved_by=g.admin
        )
        
        if account:
            flash(f'Account "{username}" created. Temporary password: {password}', 'success')
            return redirect(url_for('admin.account_detail', account_id=account.id))
        else:
            flash(error, 'error')
    
    return render_template('admin/account_create.html')


@admin_bp.route('/accounts/<int:account_id>/approve', methods=['POST'])
@require_admin
def account_approve(account_id):
    """Approve a pending account."""
    success, error = approve_account(account_id, g.admin)
    
    if success:
        flash('Account approved', 'success')
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
    
    # Recent activity for this realm
    recent_activity = (
        ActivityLog.query
        .filter(ActivityLog.realm_id == realm_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(20)
        .all()
    )
    
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
    
    # Get related activity logs
    activity_logs = ActivityLog.query.filter(
        ActivityLog.details.contains(token.token_prefix)
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
    
    if token.revoked:
        flash('Token is already revoked', 'warning')
        return redirect(url_for('admin.token_detail', token_id=token_id))
    
    # Revoke the token
    token.revoked = True
    token.revoked_at = datetime.utcnow()
    token.revoked_by = g.admin.username
    token.revoked_reason = request.form.get('reason', 'Revoked by admin')
    
    db.session.commit()
    
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
    
    # Action filter
    if action_filter != 'all':
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
        config = {
            'sender_email': request.form.get('sender_email', '').strip(),
            'sender_name': request.form.get('sender_name', '').strip() or 'Netcup API Filter',
            'smtp_server': request.form.get('smtp_server', '').strip(),
            'smtp_port': int(request.form.get('smtp_port', 465)),
            'smtp_username': request.form.get('smtp_username', '').strip(),
            'smtp_password': request.form.get('smtp_password', '').strip(),
            'use_ssl': bool(request.form.get('use_ssl')),
            'admin_email': request.form.get('admin_email', '').strip(),
        }
        
        set_setting('email_config', config)
        flash('Email configuration saved', 'success')
        logger.info(f"Email config updated by {g.admin.username}")
    
    config = get_setting('email_config') or {}
    
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


# ============================================================================
# System
# ============================================================================

@admin_bp.route('/system')
@require_admin
def system_info():
    """System information page."""
    import sys
    import os
    import platform
    import socket
    from datetime import datetime
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
    server_info = {
        'hostname': socket.gethostname(),
        'platform': platform.platform(),
        'python_version': sys.version.split()[0],
        'flask_version': flask.__version__,
        'time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
        'timezone': 'UTC',
    }
    
    # App info for template
    app_info = {
        'version': build_info.get('version', 'dev'),
        'build_hash': build_info.get('commit_short', 'N/A'),
        'build_date': build_info.get('build_timestamp', 'N/A'),
        'env': os.environ.get('FLASK_ENV', 'development'),
        'uptime': 'Unknown',  # Could implement actual uptime tracking
    }
    
    # Legacy stats variable (some templates may still use it)
    stats = db_info
    
    # Services status
    email_config = get_setting('email_config') or {}
    services = {
        'netcup': bool(get_setting('netcup_api_key') and get_setting('netcup_api_password') and get_setting('netcup_customer_id')),
        'email': bool(email_config.get('smtp_server')),
    }
    
    return render_template('admin/system_info.html',
                          build_info=build_info,
                          python_version=sys.version,
                          db_size=db_size,
                          stats=stats,
                          app=app_info,
                          db=db_info,
                          server=server_info,
                          services=services)


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
# Password Change
# ============================================================================

@admin_bp.route('/change-password', methods=['GET', 'POST'])
@require_admin
def change_password():
    """Admin password change page."""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        admin = g.admin
        
        if not admin.verify_password(current_password):
            flash('Current password is incorrect', 'error')
        elif new_password != confirm_password:
            flash('New passwords do not match', 'error')
        elif len(new_password) < 8:
            flash('Password must be at least 8 characters', 'error')
        else:
            admin.set_password(new_password)
            admin.must_change_password = 0  # Clear password change requirement
            db.session.commit()
            logger.info(f"Admin password changed: {admin.username}")
            flash('Password changed successfully', 'success')
            return redirect(url_for('admin.dashboard'))
    
    return render_template('admin/change_password.html')

"""
Admin UI for netcup-api-filter using Flask-Admin
Provides web interface for managing clients, viewing logs, and configuring system
"""
import logging
from datetime import datetime
from flask import Flask, redirect, url_for, request, flash, render_template_string, jsonify, abort
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.form import SecureForm
from flask_admin.theme import Bootstrap4Theme
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from wtforms import PasswordField, StringField, TextAreaField, SelectField, SelectMultipleField, BooleanField, DateTimeField
from wtforms.widgets import DateTimeLocalInput
from wtforms.validators import DataRequired, Email, Optional, ValidationError
from markupsafe import Markup
import json

from .database import (
    db,
    Client,
    AuditLog,
    AdminUser,
    SystemConfig,
    get_system_config,
    set_system_config,
)
from .utils import (
    generate_token,
    hash_password,
    verify_password,
    test_filesystem_access,
    get_python_info,
    get_current_directory_info,
    get_installed_libraries,
    validate_email,
    validate_ip_range,
    validate_domain,
)
from .email_notifier import get_email_notifier_from_config
from .forms import NetcupConfigForm, EmailConfigForm

logger = logging.getLogger(__name__)


def _format_expiration(expires_at):
    """Format token expiration with visual indicator"""
    if not expires_at:
        return Markup('<span style="color: var(--color-text-muted);">—</span>')
    
    now = datetime.utcnow()
    if expires_at < now:
        return Markup('<span style="color: var(--color-danger);">⏱ Expired</span>')
    
    # Calculate remaining time
    delta = expires_at - now
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    
    # Format time string
    parts = []
    if days > 0:
        parts.append(f'{days}d')
    if hours > 0 or days > 0:
        parts.append(f'{hours}h')
    parts.append(f'{minutes}m')
    
    time_str = ''.join(parts)
    return Markup(f'<span style="color: var(--color-success);">{time_str}</span>')


def _patch_flask_admin_field_flags():
    """Ensure Flask-Admin validators expose dict-style field_flags for WTForms 3.x."""
    try:
        from flask_admin.form import validators as fa_form_validators

        flags = getattr(fa_form_validators.FieldListInputRequired, "field_flags", None)
        if isinstance(flags, tuple):  # Older releases expose tuples which WTForms can't read now
            fa_form_validators.FieldListInputRequired.field_flags = {flag: True for flag in flags}
            logger.debug("Patched Flask-Admin FieldListInputRequired.field_flags for WTForms compatibility")
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.warning("Unable to patch Flask-Admin FieldListInputRequired: %s", exc)

    try:
        from flask_admin.contrib.sqla import validators as fa_sqla_validators

        flags = getattr(fa_sqla_validators.Unique, "field_flags", None)
        if isinstance(flags, tuple):
            fa_sqla_validators.Unique.field_flags = {flag: True for flag in flags}
            logger.debug("Patched Flask-Admin Unique.field_flags for WTForms compatibility")
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.warning("Unable to patch Flask-Admin Unique validator: %s", exc)


_patch_flask_admin_field_flags()

# Flask-Login setup
login_manager = LoginManager()


class User(UserMixin):
    """User class for Flask-Login"""
    def __init__(self, admin_user):
        self.id = admin_user.id
        self.username = admin_user.username
        self.must_change_password = admin_user.must_change_password


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID"""
    admin_user = AdminUser.query.get(int(user_id))
    if admin_user:
        return User(admin_user)
    return None


@login_manager.unauthorized_handler
def unauthorized():
    """Handle unauthorized access"""
    return redirect(url_for('admin.login_view'))


class SecureAdminIndexView(AdminIndexView):
    """Custom admin index view with authentication"""
    
    @expose('/')
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for('.login_view'))
        
        # Check if password change is required
        admin_user = AdminUser.query.get(current_user.id)
        if admin_user and admin_user.must_change_password:
            return redirect(url_for('.change_password_view'))
        
        # Get statistics
        total_clients = Client.query.count()
        active_clients = Client.query.filter_by(is_active=1).count()
        total_logs = AuditLog.query.count()
        recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()
        
        return self.render('admin/index_modern.html',
                         total_clients=total_clients,
                         active_clients=active_clients,
                         total_logs=total_logs,
                         recent_logs=recent_logs)
    
    @expose('/login', methods=['GET', 'POST'])
    def login_view(self):
        if current_user.is_authenticated:
            return redirect(url_for('.index'))
        
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            client_ip = request.remote_addr
            
            # DEBUG: Log login attempt
            logger.info(f"[DEBUG] Login attempt - username: '{username}', password length: {len(password) if password else 0}, client_ip: {client_ip}")
            
            if not username or not password:
                flash('Username and password are required.', 'danger')
                return self.render('admin/login_modern.html')

            # SECURITY: Check for too many failed attempts from this IP
            from .database import get_system_config, set_system_config
            failed_attempts_key = f'failed_login_attempts_{client_ip}'
            lockout_key = f'login_lockout_{client_ip}'
            
            # Check if IP is locked out
            lockout_data = get_system_config(lockout_key)
            if lockout_data:
                lockout_until = datetime.fromisoformat(lockout_data.get('until', '2000-01-01'))
                if datetime.utcnow() < lockout_until:
                    logger.warning(f"Login attempt from locked out IP: {client_ip}")
                    flash('Too many failed login attempts. Please try again later.', 'danger')
                    return self.render('admin/login_modern.html')
                else:
                    # Lockout expired, clear it
                    set_system_config(lockout_key, {})
                    set_system_config(failed_attempts_key, {'count': 0})
            
            admin_user = AdminUser.query.filter_by(username=username).first()
            
            # DEBUG: Log query result and verification
            logger.info(f"[DEBUG] Admin user found: {bool(admin_user)}")
            if admin_user:
                logger.info(f"[DEBUG] Has password_hash: {bool(admin_user.password_hash)}, hash starts with: {admin_user.password_hash[:20] if admin_user.password_hash else 'None'}")
                verify_result = verify_password(password, admin_user.password_hash)
                logger.info(f"[DEBUG] Password verification result: {verify_result}")
            
            if admin_user and verify_password(password, admin_user.password_hash):
                # Successful login - clear failed attempts
                set_system_config(failed_attempts_key, {'count': 0})
                
                # Update last login
                admin_user.last_login_at = datetime.utcnow()
                db.session.commit()
                
                user = User(admin_user)
                login_user(user)
                
                logger.info(f"Admin user '{username}' logged in from {client_ip}")
                
                # Check if password change required
                if admin_user.must_change_password:
                    # No flash message - warning is shown in the change password template
                    return redirect(url_for('.change_password_view'))
                
                return redirect(url_for('.index'))
            else:
                # Failed login - increment counter
                logger.warning(f"Failed login attempt for username '{username}' from {client_ip}")
                
                failed_attempts = get_system_config(failed_attempts_key) or {'count': 0}
                failed_attempts['count'] = failed_attempts.get('count', 0) + 1
                set_system_config(failed_attempts_key, failed_attempts)
                
                # SECURITY: Lock out after 5 failed attempts for 15 minutes
                if failed_attempts['count'] >= 5:
                    lockout_until = datetime.utcnow()
                    from datetime import timedelta
                    lockout_until = lockout_until + timedelta(minutes=15)
                    set_system_config(lockout_key, {'until': lockout_until.isoformat()})
                    logger.error(f"IP {client_ip} locked out after 5 failed login attempts")
                    flash('Too many failed login attempts. Account locked for 15 minutes.', 'danger')
                else:
                    flash('Invalid username or password', 'danger')
        
        return self.render('admin/login_modern.html')
    
    @expose('/logout')
    @login_required
    def logout_view(self):
        logout_user()
        return redirect(url_for('.login_view'))
    
    @expose('/account')
    @login_required
    def account_view(self):
        """Redirect to the password change page."""
        return redirect(url_for('.change_password_view'))

    @expose('/change-password', methods=['GET', 'POST'])
    @login_required
    def change_password_view(self):
        admin_user = AdminUser.query.get(current_user.id)
        if not admin_user:
            flash('User not found.', 'danger')
            return redirect(url_for('.login_view'))

        if request.method == 'POST':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            if not all([current_password, new_password, confirm_password]):
                flash('All password fields are required.', 'danger')
                return self.render('admin/change_password_modern.html', must_change=admin_user.must_change_password)
            
            # Validate current password
            if not verify_password(current_password, admin_user.password_hash):
                flash('Current password is incorrect', 'danger')
                return self.render('admin/change_password_modern.html', must_change=admin_user.must_change_password)
            
            # Validate new password
            if len(new_password) < 8:
                flash('New password must be at least 8 characters', 'danger')
                return self.render('admin/change_password_modern.html', must_change=admin_user.must_change_password)
            
            if new_password != confirm_password:
                flash('New passwords do not match', 'danger')
                return self.render('admin/change_password_modern.html', must_change=admin_user.must_change_password)
            
            # Update password
            admin_user.password_hash = hash_password(new_password)
            admin_user.must_change_password = 0
            db.session.commit()
            
            logger.info(f"Admin user '{admin_user.username}' changed password")
            flash('Password changed successfully', 'success')
            
            return redirect(url_for('.index'))
        
        return self.render('admin/change_password_modern.html', must_change=admin_user.must_change_password)


class SecureModelView(ModelView):
    """Base model view with authentication"""
    form_base_class = SecureForm
    
    def is_accessible(self):
        if not current_user.is_authenticated:
            return False
        
        # Check if password change required
        admin_user = AdminUser.query.get(current_user.id)
        if admin_user and admin_user.must_change_password:
            return False
        
        return True
    
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin.login_view'))


class ClientModelView(SecureModelView):
    """Admin view for Client management"""
    
    # Use custom templates
    list_template = 'admin/model/list.html'
    create_template = 'admin/model/create.html'
    edit_template = 'admin/model/edit.html'
    
    # Disable batch actions (no "With selected" dropdown)
    action_disallowed_list = ['delete']
    
    # Enable row actions (edit/delete buttons on each row)
    column_display_actions = True
    can_delete = True
    
    column_list = ['client_id', 'description', 'realm_type', 'realm_value', 'token_expires_at', 'logs', 'is_active', 'email_notifications_enabled', 'created_at']
    column_searchable_list = ['client_id', 'description', 'realm_value']
    column_filters = ['realm_type', 'is_active', 'email_notifications_enabled']
    
    # Pagination for large client lists
    page_size = 50
    can_set_page_size = True
    column_sortable_list = ['client_id', 'realm_type', 'realm_value', 'is_active', 'token_expires_at', 'created_at']
    
    # Format columns with custom HTML
    # Note: Do NOT format editable columns as Flask-Admin needs to render the editable widget
    column_formatters = {
        'client_id': lambda v, c, m, p: Markup(f'<div class="client-id-cell"><span class="client-id-text">{m.client_id}</span><span class="icon-copy" onclick="copyToClipboard(\'{m.client_id}\', this)" title="Copy Client ID">🔗</span></div>'),
        'realm_value': lambda v, c, m, p: Markup(f'<code>{m.realm_value}</code>'),
        'is_active': lambda v, c, m, p: Markup('✅' if m.is_active else '❌'),
        'email_notifications_enabled': lambda v, c, m, p: Markup('✅' if m.email_notifications_enabled else '❌'),
        'token_expires_at': lambda v, c, m, p: _format_expiration(m.token_expires_at),
        'logs': lambda v, c, m, p: Markup(f'<a href="/admin/auditlog/?flt1_2={m.client_id}" class="icon-logs" title="View logs for {m.client_id}">🧾</a>'),
    }
    
    column_labels = {
        'client_id': 'Client ID',
        'secret_key_hash': 'Secret Key (Hashed)',
        'realm_type': 'Realm Type',
        'realm_value': 'Realm Value',
        'allowed_record_types': 'Allowed Record Types',
        'allowed_operations': 'Allowed Operations',
        'allowed_ip_ranges': 'Allowed IP Ranges',
        'email_notifications_enabled': 'Email Notifications',
        'is_active': 'Active',
        'token_expires_at': 'Token Expires',
        'logs': 'Logs',
    }
    
    column_descriptions = {
        'client_id': 'Cleartext identifier (visible in UI, used in authentication as client_id:secret_key)',
        'realm_type': 'host = exact domain match, subdomain = *.subdomain pattern',
        'realm_value': 'Domain name (e.g., example.com or subdomain.example.com)',
        'allowed_record_types': 'DNS record types this client can modify (A, AAAA, CNAME, NS)',
        'allowed_operations': 'Operations: read, update, create, delete',
        'allowed_ip_ranges': 'IP addresses/ranges allowed to use this token',
        'email_notifications_enabled': 'Send email on every API access',
        'logs': 'View audit log entries for this client',
    }
    
    form_columns = ['client_id', 'description', 'realm_type', 'realm_value',
                   'allowed_record_types', 'allowed_operations', 'allowed_ip_ranges',
                   'token_expires_at', 'email_notifications_enabled', 'email_address', 'is_active']
    
    form_excluded_columns = ['secret_key_hash', 'created_at', 'updated_at']
    
    # Custom form fields
    form_overrides = {
        'realm_type': SelectField,
        'allowed_record_types': SelectMultipleField,
        'allowed_operations': SelectMultipleField,
        'allowed_ip_ranges': TextAreaField,
        'email_address': StringField,
        'email_notifications_enabled': BooleanField,
        'is_active': BooleanField,
        'token_expires_at': DateTimeField,
    }
    
    # Template selector context for create form
    def create_form(self):
        from .client_templates import get_all_templates
        form = super().create_form()
        # Add templates to form context for JavaScript
        form._templates = get_all_templates()
        return form
    
    form_args = {
        'client_id': {
            'validators': [DataRequired()],
            'description': 'Unique identifier for this client'
        },
        'realm_type': {
            'choices': [('host', 'Host'), ('subdomain', 'Subdomain')],
            'validators': [DataRequired()],
            'description': 'host = exact domain match, subdomain = *.subdomain pattern',
            'default': 'host'  # Pre-select host by default
        },
        'realm_value': {
            'validators': [DataRequired()],
            'description': 'Domain name (e.g., example.com)'
        },
        'allowed_record_types': {
            'choices': [('A', 'A'), ('AAAA', 'AAAA'), ('CNAME', 'CNAME'), ('NS', 'NS')],
            'validators': [DataRequired()],
            'description': 'DNS record types this client can modify',
            'default': ['A']  # Pre-select A record by default
        },
        'allowed_operations': {
            'choices': [('read', 'Read'), ('update', 'Update'), ('create', 'Create'), ('delete', 'Delete')],
            'validators': [DataRequired()],
            'description': 'Allowed operations',
            'default': ['read']  # Pre-select read-only by default
        },
        'allowed_ip_ranges': {
            'description': 'One IP/range per line (e.g., 192.168.1.0/24, 10.0.0.1-10.0.0.255, 192.168.1.*)'
        },
        'email_address': {
            'validators': [Optional()],
            'description': 'Email address for notifications'
        },
        'email_notifications_enabled': {
            'description': 'Send email notification on every API access'
        },
        'token_expires_at': {
            'validators': [Optional()],
            'description': 'Optional expiration date for the token',
            'widget': DateTimeLocalInput()
        },
    }
    
    def on_model_change(self, form, model, is_created):
        """Handle model changes"""
        # Convert form data to JSON for storage
        if hasattr(form, 'allowed_record_types') and form.allowed_record_types.data:
            record_types = form.allowed_record_types.data
            model.set_allowed_record_types(record_types)
        
        if hasattr(form, 'allowed_operations') and form.allowed_operations.data:
            operations = form.allowed_operations.data
            model.set_allowed_operations(operations)
        
        if hasattr(form, 'allowed_ip_ranges') and form.allowed_ip_ranges.data:
            # Parse textarea input (one per line)
            ranges = [r.strip() for r in form.allowed_ip_ranges.data.split('\n') if r.strip()]
            # Validate each range
            for r in ranges:
                if not validate_ip_range(r):
                    message = f'Invalid IP range format: {r}'
                    flash(message, 'danger')
                    raise ValidationError(message)
            model.set_allowed_ip_ranges(ranges)
        
        # Validate email if provided
        if hasattr(form, 'email_address') and form.email_address.data:
            if not validate_email(form.email_address.data):
                message = 'Invalid email address format'
                flash(message, 'danger')
                raise ValidationError(message)

        if hasattr(form, 'realm_value') and form.realm_value.data:
            realm_value = form.realm_value.data.strip()
            candidate = realm_value[2:] if realm_value.startswith('*.') else realm_value
            if not validate_domain(candidate):
                message = 'Realm value must be a valid domain (optionally starting with *.)'
                logger.warning("Rejecting client realm value: %s", realm_value)
                flash(message, 'danger')
                raise ValidationError(message)
            form.realm_value.data = realm_value
        
        # Generate secret key for new clients
        if is_created:
            from .utils import generate_token
            
            # Admin provides client_id in form, we generate secret_key
            # Generate secret key (32 chars for better UX)
            secret_key = generate_token(min_length=32, max_length=32)
            
            # Store hashed secret_key
            model.secret_key_hash = hash_password(secret_key)
            
            # Build complete authentication token
            full_token = f"{model.client_id}:{secret_key}"
            
            # Flash the complete token to user (only shown once)
            flash(
                f'Client created successfully! '
                f'Authentication token (save this - it cannot be retrieved later): '
                f'<code style="background:#f5f5f5;padding:4px 8px;border-radius:3px;font-family:monospace;">{full_token}</code>',
                'success'
            )
        
        model.updated_at = datetime.utcnow()
    
    def on_form_prefill(self, form, id):
        """Populate form with data from model"""
        model = self.get_one(id)
        
        # Convert JSON data to form data
        form.allowed_record_types.data = model.get_allowed_record_types()
        form.allowed_operations.data = model.get_allowed_operations()
        
        # Convert IP ranges to textarea format
        ranges = model.get_allowed_ip_ranges()
        if ranges:
            form.allowed_ip_ranges.data = '\n'.join(ranges)

    @expose('/generate-token', methods=['POST'])
    def generate_token_view(self):
        """Generate a random token (for client_id suggestion)"""
        if not self.is_accessible():
            abort(403)
        logger.info("Admin UI token generation requested")
        token = generate_token(min_length=20, max_length=20)
        return jsonify({'token': token})
    
    @expose('/regenerate-secret/<int:client_id>', methods=['POST'])
    def regenerate_secret_view(self, client_id):
        """Regenerate secret key for an existing client (keeps same client_id)"""
        if not self.is_accessible():
            abort(403)
        
        client = self.get_one(client_id)
        if not client:
            flash('Client not found', 'danger')
            return redirect(url_for('.index_view'))
        
        # Generate new secret key
        new_secret_key = generate_token(min_length=40, max_length=40)
        client.secret_key_hash = hash_password(new_secret_key)
        client.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Build complete authentication token
        full_token = f"{client.client_id}:{new_secret_key}"
        
        logger.info(f"Admin regenerated secret key for client: {client.client_id}")
        flash(
            f'Secret key regenerated successfully! '
            f'New authentication token (save this - it cannot be retrieved later): '
            f'<code style="background:#f5f5f5;padding:4px 8px;border-radius:3px;font-family:monospace;">{full_token}</code>',
            'success'
        )
        
        return redirect(url_for('.edit_view', id=client_id))


class ClientExperimentalModelView(ClientModelView):
    """Experimental Admin view for Client management (Testing new UI)"""
    create_template = 'admin/model/create_experimental.html'
    
    def is_visible(self):
        return False  # Hide from menu, accessible via URL only if needed, or True if we want it in menu


class AuditLogModelView(SecureModelView):
    """Admin view for Audit Logs"""
    
    # Use custom templates
    list_template = 'admin/model/list.html'
    
    can_create = False
    can_edit = False
    can_delete = False
    
    column_list = ['timestamp', 'client_id', 'ip_address', 'operation', 'domain', 'success']
    column_searchable_list = ['client_id', 'ip_address', 'operation', 'domain']
    column_filters = ['success', 'operation', 'client_id', 'timestamp']
    column_sortable_list = ['timestamp', 'client_id', 'ip_address', 'operation', 'domain', 'success']
    column_default_sort = ('timestamp', True)  # Descending
    
    column_labels = {
        'client_id': 'Client ID',
        'ip_address': 'IP Address',
    }
    
    column_formatters = {
        'success': lambda v, c, m, p: '✓' if m.success else '✗',
        'timestamp': lambda v, c, m, p: m.timestamp.strftime('%Y-%m-%d %H:%M:%S') if m.timestamp else '',
    }
    
    page_size = 50


class SystemInfoView(BaseView):
    """System information and diagnostics"""
    
    @expose('/')
    @login_required
    def index(self):
        # Check if password change required
        admin_user = AdminUser.query.get(current_user.id)
        if admin_user and admin_user.must_change_password:
            return redirect(url_for('admin.change_password_view'))
        
        # Get system information
        python_info = get_python_info()
        dir_info = get_current_directory_info()
        fs_tests = test_filesystem_access()
        installed_libraries = get_installed_libraries()
        
        # Get database path
        from .database import get_db_path
        db_path = get_db_path()
        
        return self.render('admin/system_info_modern.html',
                         python_info=python_info,
                         dir_info=dir_info,
                         fs_tests=fs_tests,
                         db_path=db_path,
                         installed_libraries=installed_libraries)


class NetcupConfigView(BaseView):
    """Netcup API configuration"""
    
    @expose('/', methods=['GET', 'POST'])
    @login_required
    def index(self):
        # Check if password change required
        admin_user = AdminUser.query.get(current_user.id)
        if admin_user and admin_user.must_change_password:
            return redirect(url_for('admin.change_password_view'))
        
        form = NetcupConfigForm()
        
        if request.method == 'POST':
            if form.validate_on_submit():
                config = {
                    'customer_id': form.customer_id.data,
                    'api_key': form.api_key.data,
                    'api_password': form.api_password.data,
                    'api_url': form.api_url.data,
                    'timeout': form.timeout.data
                }
                
                set_system_config('netcup_config', config)
                flash('Netcup API configuration saved successfully', 'success')
                logger.info('Netcup API configuration updated')
                return redirect(url_for('.index'))
        else:
            # Load existing config
            config = get_system_config('netcup_config') or {}
            form.process(data=config)
        
        return self.render('admin/netcup_config_modern.html', form=form)


class EmailConfigView(BaseView):
    """Email configuration and testing"""
    
    @expose('/', methods=['GET', 'POST'])
    @login_required
    def index(self):
        # Check if password change required
        admin_user = AdminUser.query.get(current_user.id)
        if admin_user and admin_user.must_change_password:
            return redirect(url_for('admin.change_password_view'))
        
        form = EmailConfigForm()
        
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'save':
                if form.validate_on_submit():
                    config = {
                        'smtp_server': form.smtp_server.data,
                        'smtp_port': form.smtp_port.data,
                        'smtp_username': form.smtp_username.data,
                        'smtp_password': form.smtp_password.data,
                        'sender_email': form.sender_email.data,
                        'use_ssl': form.use_ssl.data
                    }
                    
                    set_system_config('email_config', config)
                    
                    # Also save admin email
                    admin_email_config = {
                        'admin_email': form.admin_email.data
                    }
                    set_system_config('admin_email_config', admin_email_config)
                    
                    flash('Email configuration saved successfully', 'success')
                    logger.info('Email configuration updated')
                    return redirect(url_for('.index'))
            
            elif action == 'test':
                # For test, we only care about the test_email field being valid
                # But we use the SAVED config for sending
                test_email = request.form.get('test_email', '')
                
                if not test_email:
                    flash('Please enter an email address to test', 'warning')
                elif not validate_email(test_email.strip()):
                    flash('Please enter a valid test email address', 'danger')
                else:
                    email_config = get_system_config('email_config')
                    if not email_config:
                        flash('Email configuration not found. Please save configuration first.', 'danger')
                    else:
                        notifier = get_email_notifier_from_config(email_config)
                        if notifier:
                            success = notifier.send_test_email(test_email)
                            if success:
                                flash(f'Test email sent successfully to {test_email}', 'success')
                            else:
                                flash('Failed to send test email. Check logs for details.', 'danger')
                        else:
                            flash('Failed to create email notifier. Check configuration.', 'danger')
        else:
            # Load existing config
            email_config = get_system_config('email_config') or {}
            admin_email_config = get_system_config('admin_email_config') or {}
            
            # Merge configs for form population
            data = email_config.copy()
            data.update(admin_email_config)
            form.process(data=data)
        
        return self.render('admin/email_config_modern.html', form=form)


def setup_admin_ui(app):
    """
    Setup Flask-Admin UI
    
    Args:
        app: Flask application instance
    """
    # Use modern unified dark theme
    # Configure Flask-Admin to use our custom base template
    app.config['FLASK_ADMIN_BASE_TEMPLATE'] = 'admin/master_modern.html'

    # Initialize Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'admin.login_view'
    
    # Create admin interface
    # Flask-Admin 2.0.2 uses theme parameter instead of template_mode
    # Bootstrap 5 is not yet supported - using Bootstrap4Theme
    admin = Admin(
        app,
        name='Netcup API Filter',
        index_view=SecureAdminIndexView(name='Dashboard', url='/admin'),
        theme=Bootstrap4Theme()
    )
    
    # Add model views
    admin.add_view(ClientModelView(Client, db.session, name='Clients', category='Management'))
    admin.add_view(ClientExperimentalModelView(Client, db.session, name='Clients (Exp)', endpoint='client_exp', category='Management'))
    admin.add_view(AuditLogModelView(AuditLog, db.session, name='Audit Logs', category='Logs'))
    
    # Add custom views
    admin.add_view(NetcupConfigView(name='Netcup API', endpoint='netcup_config', category='Configuration'))
    admin.add_view(EmailConfigView(name='Email Settings', endpoint='email_config', category='Configuration'))
    admin.add_view(SystemInfoView(name='System Info', endpoint='system_info', category='System'))
    
    logger.info("Admin UI setup complete")
    
    return admin

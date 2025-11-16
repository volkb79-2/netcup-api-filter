"""
Admin UI for netcup-api-filter using Flask-Admin
Provides web interface for managing clients, viewing logs, and configuring system
"""
import logging
from datetime import datetime
from flask import Flask, redirect, url_for, request, flash, render_template_string
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.form import SecureForm
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from wtforms import PasswordField, StringField, TextAreaField, SelectField, SelectMultipleField, BooleanField, DateTimeField
from wtforms.validators import DataRequired, Email, Optional, ValidationError
import json

from database import db, Client, AuditLog, AdminUser, SystemConfig, get_system_config, set_system_config
from utils import generate_token, hash_password, verify_password, test_filesystem_access, get_python_info, get_current_directory_info, validate_email, validate_ip_range
from email_notifier import get_email_notifier_from_config

logger = logging.getLogger(__name__)

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
        
        return self.render('admin/index.html',
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
            
            admin_user = AdminUser.query.filter_by(username=username).first()
            
            if admin_user and verify_password(password, admin_user.password_hash):
                # Update last login
                admin_user.last_login_at = datetime.utcnow()
                db.session.commit()
                
                user = User(admin_user)
                login_user(user)
                
                logger.info(f"Admin user '{username}' logged in")
                
                # Check if password change required
                if admin_user.must_change_password:
                    flash('You must change your password before continuing.', 'warning')
                    return redirect(url_for('.change_password_view'))
                
                return redirect(url_for('.index'))
            else:
                logger.warning(f"Failed login attempt for username '{username}'")
                flash('Invalid username or password', 'danger')
        
        return self.render('admin/login.html')
    
    @expose('/logout')
    @login_required
    def logout_view(self):
        logout_user()
        return redirect(url_for('.login_view'))
    
    @expose('/change-password', methods=['GET', 'POST'])
    @login_required
    def change_password_view(self):
        admin_user = AdminUser.query.get(current_user.id)
        
        if request.method == 'POST':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            # Validate current password
            if not verify_password(current_password, admin_user.password_hash):
                flash('Current password is incorrect', 'danger')
                return self.render('admin/change_password.html', must_change=admin_user.must_change_password)
            
            # Validate new password
            if len(new_password) < 8:
                flash('New password must be at least 8 characters', 'danger')
                return self.render('admin/change_password.html', must_change=admin_user.must_change_password)
            
            if new_password != confirm_password:
                flash('New passwords do not match', 'danger')
                return self.render('admin/change_password.html', must_change=admin_user.must_change_password)
            
            # Update password
            admin_user.password_hash = hash_password(new_password)
            admin_user.must_change_password = 0
            db.session.commit()
            
            logger.info(f"Admin user '{admin_user.username}' changed password")
            flash('Password changed successfully', 'success')
            
            return redirect(url_for('.index'))
        
        return self.render('admin/change_password.html', must_change=admin_user.must_change_password)


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
    
    column_list = ['client_id', 'description', 'realm_type', 'realm_value', 'is_active', 'email_notifications_enabled', 'created_at']
    column_searchable_list = ['client_id', 'description', 'realm_value']
    column_filters = ['realm_type', 'is_active', 'email_notifications_enabled']
    column_sortable_list = ['client_id', 'realm_type', 'realm_value', 'is_active', 'created_at']
    
    column_labels = {
        'client_id': 'Client ID',
        'secret_token': 'Secret Token',
        'realm_type': 'Realm Type',
        'realm_value': 'Realm Value',
        'allowed_record_types': 'Allowed Record Types',
        'allowed_operations': 'Allowed Operations',
        'allowed_ip_ranges': 'Allowed IP Ranges',
        'email_notifications_enabled': 'Email Notifications',
        'is_active': 'Active',
        'token_expires_at': 'Token Expires',
    }
    
    column_descriptions = {
        'client_id': 'Unique identifier for this client',
        'realm_type': 'host = exact domain match, subdomain = *.subdomain pattern',
        'realm_value': 'Domain name (e.g., example.com or subdomain.example.com)',
        'allowed_record_types': 'DNS record types this client can modify (A, AAAA, CNAME, NS)',
        'allowed_operations': 'Operations: read, update, create, delete',
        'allowed_ip_ranges': 'IP addresses/ranges allowed to use this token',
        'email_notifications_enabled': 'Send email on every API access',
    }
    
    form_columns = ['client_id', 'description', 'realm_type', 'realm_value',
                   'allowed_record_types', 'allowed_operations', 'allowed_ip_ranges',
                   'email_address', 'email_notifications_enabled', 'token_expires_at', 'is_active']
    
    form_excluded_columns = ['secret_token', 'created_at', 'updated_at']
    
    # Custom form fields
    form_overrides = {
        'realm_type': SelectField,
        'allowed_record_types': SelectMultipleField,
        'allowed_operations': SelectMultipleField,
        'allowed_ip_ranges': TextAreaField,
        'email_address': StringField,
        'email_notifications_enabled': BooleanField,
        'is_active': BooleanField,
    }
    
    form_args = {
        'client_id': {
            'validators': [DataRequired()],
            'description': 'Unique identifier for this client'
        },
        'realm_type': {
            'choices': [('host', 'Host'), ('subdomain', 'Subdomain')],
            'validators': [DataRequired()],
            'description': 'host = exact domain match, subdomain = *.subdomain pattern'
        },
        'realm_value': {
            'validators': [DataRequired()],
            'description': 'Domain name (e.g., example.com)'
        },
        'allowed_record_types': {
            'choices': [('A', 'A'), ('AAAA', 'AAAA'), ('CNAME', 'CNAME'), ('NS', 'NS')],
            'validators': [DataRequired()],
            'description': 'DNS record types this client can modify'
        },
        'allowed_operations': {
            'choices': [('read', 'Read'), ('update', 'Update'), ('create', 'Create'), ('delete', 'Delete')],
            'validators': [DataRequired()],
            'description': 'Allowed operations'
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
            'description': 'Optional expiration date for the token'
        },
    }
    
    def on_model_change(self, form, model, is_created):
        """Handle model changes"""
        # Convert form data to JSON for storage
        if hasattr(form, 'allowed_record_types') and form.allowed_record_types.data:
            model.set_allowed_record_types(form.allowed_record_types.data)
        
        if hasattr(form, 'allowed_operations') and form.allowed_operations.data:
            model.set_allowed_operations(form.allowed_operations.data)
        
        if hasattr(form, 'allowed_ip_ranges') and form.allowed_ip_ranges.data:
            # Parse textarea input (one per line)
            ranges = [r.strip() for r in form.allowed_ip_ranges.data.split('\n') if r.strip()]
            # Validate each range
            for r in ranges:
                if not validate_ip_range(r):
                    raise ValidationError(f'Invalid IP range format: {r}')
            model.set_allowed_ip_ranges(ranges)
        
        # Validate email if provided
        if hasattr(form, 'email_address') and form.email_address.data:
            if not validate_email(form.email_address.data):
                raise ValidationError('Invalid email address format')
        
        # Generate token for new clients
        if is_created:
            new_token = generate_token()
            model.secret_token = hash_password(new_token)
            
            # Flash the token to user (only shown once)
            flash(f'Client created successfully! Secret token (save this - it cannot be retrieved later): {new_token}', 'success')
        
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


class AuditLogModelView(SecureModelView):
    """Admin view for Audit Logs"""
    
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
        
        # Get database path
        from database import get_db_path
        db_path = get_db_path()
        
        return self.render('admin/system_info.html',
                         python_info=python_info,
                         dir_info=dir_info,
                         fs_tests=fs_tests,
                         db_path=db_path)


class NetcupConfigView(BaseView):
    """Netcup API configuration"""
    
    @expose('/', methods=['GET', 'POST'])
    @login_required
    def index(self):
        # Check if password change required
        admin_user = AdminUser.query.get(current_user.id)
        if admin_user and admin_user.must_change_password:
            return redirect(url_for('admin.change_password_view'))
        
        if request.method == 'POST':
            config = {
                'customer_id': request.form.get('customer_id', ''),
                'api_key': request.form.get('api_key', ''),
                'api_password': request.form.get('api_password', ''),
                'api_url': request.form.get('api_url', 'https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON'),
                'timeout': int(request.form.get('timeout', 30))
            }
            
            set_system_config('netcup_config', config)
            flash('Netcup API configuration saved successfully', 'success')
            logger.info('Netcup API configuration updated')
        
        config = get_system_config('netcup_config') or {}
        
        return self.render('admin/netcup_config.html', config=config)


class EmailConfigView(BaseView):
    """Email configuration and testing"""
    
    @expose('/', methods=['GET', 'POST'])
    @login_required
    def index(self):
        # Check if password change required
        admin_user = AdminUser.query.get(current_user.id)
        if admin_user and admin_user.must_change_password:
            return redirect(url_for('admin.change_password_view'))
        
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'save':
                config = {
                    'smtp_server': request.form.get('smtp_server', ''),
                    'smtp_port': int(request.form.get('smtp_port', 465)),
                    'smtp_username': request.form.get('smtp_username', ''),
                    'smtp_password': request.form.get('smtp_password', ''),
                    'sender_email': request.form.get('sender_email', ''),
                    'use_ssl': request.form.get('use_ssl') == 'on'
                }
                
                set_system_config('email_config', config)
                flash('Email configuration saved successfully', 'success')
                logger.info('Email configuration updated')
                
                # Also save admin email
                admin_email_config = {
                    'admin_email': request.form.get('admin_email', '')
                }
                set_system_config('admin_email_config', admin_email_config)
            
            elif action == 'test':
                test_email = request.form.get('test_email', '')
                
                if not test_email:
                    flash('Please enter an email address to test', 'warning')
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
        
        email_config = get_system_config('email_config') or {}
        admin_email_config = get_system_config('admin_email_config') or {}
        
        return self.render('admin/email_config.html',
                         email_config=email_config,
                         admin_email_config=admin_email_config)


def setup_admin_ui(app):
    """
    Setup Flask-Admin UI
    
    Args:
        app: Flask application instance
    """
    # Initialize Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'admin.login_view'
    
    # Create admin interface
    admin = Admin(
        app,
        name='Netcup API Filter',
        template_mode='bootstrap4',
        index_view=SecureAdminIndexView(name='Dashboard', url='/admin'),
        base_template='admin/base.html'
    )
    
    # Add model views
    admin.add_view(ClientModelView(Client, db.session, name='Clients', category='Management'))
    admin.add_view(AuditLogModelView(AuditLog, db.session, name='Audit Logs', category='Logs'))
    
    # Add custom views
    admin.add_view(NetcupConfigView(name='Netcup API', endpoint='netcup_config', category='Configuration'))
    admin.add_view(EmailConfigView(name='Email Settings', endpoint='email_config', category='Configuration'))
    admin.add_view(SystemInfoView(name='System Info', endpoint='system_info', category='System'))
    
    logger.info("Admin UI setup complete")
    
    return admin

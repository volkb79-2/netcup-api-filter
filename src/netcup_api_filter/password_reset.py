"""
Password Reset Service.

Handles:
- Generating secure password reset tokens
- Sending password reset emails
- Verifying reset tokens
- Completing password resets

Security: Tokens can be bound to the requesting IP address to prevent
interception attacks. This is configurable per-environment.

CRITICAL: Uses database storage (ResetToken model) for multi-worker support.
In-memory storage breaks when gunicorn uses multiple workers because each
worker has its own memory space - tokens created by one worker are invisible
to other workers.
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from .models import Account, ResetToken, RegistrationRequest, db

logger = logging.getLogger(__name__)


def _hash_token(raw_token: str) -> str:
    """Hash a token with SHA256 for storage."""
    return hashlib.sha256(raw_token.encode()).hexdigest()

# Default token validity period (can be overridden by system settings)
DEFAULT_TOKEN_EXPIRY_HOURS = 1


def get_token_expiry_hours() -> int:
    """Get token expiry hours from system settings or default."""
    from .database import get_setting
    
    try:
        expiry = get_setting('password_reset_expiry_hours')
        if expiry is not None:
            return int(expiry)
    except (ValueError, TypeError):
        pass
    
    # Fall back to environment variable or default
    env_value = os.environ.get('PASSWORD_RESET_EXPIRY_HOURS')
    if env_value:
        try:
            return int(env_value)
        except ValueError:
            pass
    
    return DEFAULT_TOKEN_EXPIRY_HOURS


def is_ip_binding_enabled() -> bool:
    """Check if IP binding for tokens is enabled.
    
    IP binding adds security by requiring the redemption IP to match
    the requesting IP. Can be disabled for mobile users who may change IPs.
    """
    from .database import get_setting
    
    try:
        setting = get_setting('token_ip_binding_enabled')
        if setting is not None:
            return bool(setting)
    except (ValueError, TypeError):
        pass
    
    # Default: enabled for security
    env_value = os.environ.get('TOKEN_IP_BINDING_ENABLED', 'true')
    return env_value.lower() in ('true', '1', 'yes')


def generate_reset_token(
    target,  # Account or RegistrationRequest
    expiry_hours: int | None = None,
    source_ip: str | None = None,
    token_type: str = 'reset'
) -> tuple[str, int]:
    """Generate a secure token for an account or registration request.
    
    Uses database storage (ResetToken model) for multi-worker support.
    
    Args:
        target: Object with .id attribute (Account or RegistrationRequest)
        expiry_hours: Optional custom expiry hours (uses system setting if None)
        source_ip: IP address that requested the token (for IP binding)
        token_type: Type of token ('reset', 'invite', 'verify')
    
    Returns:
        Tuple of (raw_token, expiry_hours_used)
        The raw token is to be sent in email, only the hash is stored.
    """
    target_id = target.id
    target_name = getattr(target, 'username', f'id={target_id}')
    
    # Determine target type for database storage
    target_type = 'account' if isinstance(target, Account) else 'registration'
    
    # Invalidate any existing tokens of same type for this target
    invalidate_tokens_for_account(target_id, token_type, target_type)
    
    # Get expiry hours from param, or system settings/default
    if expiry_hours is None:
        expiry_hours = get_token_expiry_hours()
    
    # Generate secure random token
    raw_token = secrets.token_urlsafe(48)
    
    # Store hash of token in database
    token_hash = _hash_token(raw_token)
    expires_at = datetime.utcnow() + timedelta(hours=expiry_hours)
    
    reset_token = ResetToken(
        token_hash=token_hash,
        target_id=target_id,
        target_type=target_type,
        token_type=token_type,
        expires_at=expires_at,
        source_ip=source_ip if is_ip_binding_enabled() else None
    )
    db.session.add(reset_token)
    db.session.commit()
    
    logger.info(
        f"Token ({token_type}) generated for {target_name} "
        f"(expires in {expiry_hours}h, IP={source_ip or 'not bound'})"
    )
    return raw_token, expiry_hours


def invalidate_tokens_for_account(
    target_id: int,
    token_type: str | None = None,
    target_type: str = 'account'
) -> None:
    """Invalidate reset tokens for an account or registration.
    
    Args:
        target_id: Account or RegistrationRequest ID
        token_type: If provided, only invalidate tokens of this type
        target_type: 'account' or 'registration'
    """
    query = ResetToken.query.filter_by(target_id=target_id, target_type=target_type)
    if token_type:
        query = query.filter_by(token_type=token_type)
    
    # Filter out already used tokens (keep for audit)
    query = query.filter(ResetToken.used_at == None)  # noqa: E711 - SQLAlchemy requires == None
    
    tokens = query.all()
    for token in tokens:
        db.session.delete(token)
    
    if tokens:
        db.session.commit()
        logger.debug(f"Invalidated {len(tokens)} tokens for {target_type}:{target_id}")


def verify_reset_token(
    raw_token: str,
    current_ip: str | None = None,
    expected_type: str | None = None
) -> tuple[Optional[Account], str | None]:
    """Verify a password reset token and return the associated account.
    
    Args:
        raw_token: The token from the URL
        current_ip: Current request IP (for IP binding validation)
        expected_type: Expected token type (None = any type)
    
    Returns:
        (target, error_message) - target is None if validation fails
        target can be Account or RegistrationRequest depending on token type
    """
    token_hash = _hash_token(raw_token)
    
    reset_token = ResetToken.query.filter_by(token_hash=token_hash).first()
    if not reset_token:
        logger.debug("Password reset token not found in database")
        return None, "Invalid or expired link"
    
    # Check token type if specified
    if expected_type and reset_token.token_type != expected_type:
        logger.debug(f"Token type mismatch: expected {expected_type}, got {reset_token.token_type}")
        return None, "Invalid link type"
    
    # Check if already used
    if reset_token.is_used():
        logger.debug(f"Token already used for target_id={reset_token.target_id}")
        return None, "Link has already been used"
    
    # Check expiration
    if reset_token.is_expired():
        db.session.delete(reset_token)
        db.session.commit()
        logger.debug(f"Token expired for target_id={reset_token.target_id}")
        return None, "Link has expired"
    
    # Check IP binding if enabled and source IP was recorded
    if reset_token.source_ip and current_ip:
        if reset_token.source_ip != current_ip:
            logger.warning(
                f"IP mismatch for token: expected {reset_token.source_ip}, got {current_ip} "
                f"(target_id={reset_token.target_id})"
            )
            return None, "Security check failed - please request a new link from the same network"
    
    # Get target based on type
    if reset_token.target_type == 'account':
        target = Account.query.get(reset_token.target_id)
        if not target:
            db.session.delete(reset_token)
            db.session.commit()
            logger.debug(f"Account not found for reset token: target_id={reset_token.target_id}")
            return None, "Account not found"
    else:  # registration
        target = RegistrationRequest.query.get(reset_token.target_id)
        if not target:
            db.session.delete(reset_token)
            db.session.commit()
            logger.debug(f"Registration not found for reset token: target_id={reset_token.target_id}")
            return None, "Registration request not found"
    
    return target, None


def complete_password_reset(account: Account, new_password: str, raw_token: str) -> Tuple[bool, str]:
    """Complete a password reset by setting new password.
    
    Returns (success, error_message).
    """
    import bcrypt
    
    # Verify token is still valid
    token_hash = _hash_token(raw_token)
    reset_token = ResetToken.query.filter_by(token_hash=token_hash).first()
    
    if not reset_token:
        return False, "Reset link is no longer valid"
    
    if reset_token.is_used():
        return False, "Reset link has already been used"
    
    # Update password
    password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    account.password_hash = password_hash
    account.updated_at = datetime.utcnow()
    
    # Clear must_change_password flag if set
    if hasattr(account, 'must_change_password'):
        account.must_change_password = False
    
    # Mark token as used (keep for audit trail)
    reset_token.mark_used()
    
    db.session.commit()
    
    # Invalidate all other tokens for this account (security)
    invalidate_tokens_for_account(account.id, target_type='account')
    
    logger.info(f"Password reset completed for account {account.username}")
    return True, ""


def send_password_reset_email(
    account: Account,
    expiry_hours: int | None = None,
    admin_initiated: bool = False,
    source_ip: str | None = None
) -> bool:
    """Send password reset email to account.
    
    Args:
        account: The account to send reset email to
        expiry_hours: Optional custom expiry hours (uses system setting if None)
        admin_initiated: If True, indicates this was triggered by an admin
        source_ip: IP address of the requester (for IP-bound token security)
    
    Returns True if email sent successfully.
    """
    from flask import url_for, current_app
    from .email_notifier import get_email_notifier_from_config
    from .database import get_system_config
    import json
    
    # Check if account has an email
    if not account.email:
        logger.warning(f"No email address for account {account.username}")
        return False
    
    # Generate token with expiry and IP binding
    raw_token, actual_expiry = generate_reset_token(
        account,
        expiry_hours,
        source_ip=source_ip,
        token_type='reset'
    )
    
    # Build reset URL
    try:
        reset_url = url_for('account.reset_password', token=raw_token, _external=True)
    except RuntimeError:
        # If we're outside request context, build manually
        base_url = os.environ.get('BASE_URL', 'http://localhost:5100')
        reset_url = f"{base_url}/account/reset-password/{raw_token}"
    
    # Get email configuration
    smtp_config = get_system_config('smtp_config') or get_system_config('email_config')
    if not smtp_config:
        logger.warning("SMTP configuration not set - cannot send password reset email")
        return False

    if isinstance(smtp_config, str):
        try:
            smtp_config = json.loads(smtp_config)
        except json.JSONDecodeError:
            logger.warning("SMTP configuration invalid JSON")
            return False

    if not isinstance(smtp_config, dict):
        logger.warning("SMTP configuration has unexpected type")
        return False

    notifier = get_email_notifier_from_config(smtp_config)
    if not notifier:
        logger.warning("Failed to create email notifier from config")
        return False
    
    # Build email content - different messaging for admin vs user initiated
    if admin_initiated:
        subject = "[Netcup API Filter] Password Reset Required"
        intro = "An administrator has requested a password reset for your account."
    else:
        subject = "[Netcup API Filter] Password Reset Request"
        intro = "A password reset was requested for your account."
    
    body = f"""
Password Reset

Hello {account.username},

{intro}

Click the link below to set a new password:
{reset_url}

This link will expire in {actual_expiry} hour(s).

If you did not expect this email, please contact your administrator.

---
Netcup API Filter
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #3498db;">Password Reset</h2>
    
    <p>Hello <strong>{account.username}</strong>,</p>
    
    <p>{intro}</p>
    
    <p>Click the button below to set a new password:</p>
    
    <p style="margin: 20px 0;">
        <a href="{reset_url}" style="background-color: #3498db; color: white; padding: 12px 24px; 
           text-decoration: none; border-radius: 4px; display: inline-block;">
            Reset Password
        </a>
    </p>
    
    <p style="color: #666; font-size: 14px;">
        Or copy this link: <a href="{reset_url}">{reset_url}</a>
    </p>
    
    <p style="color: #888;">
        This link will expire in {actual_expiry} hour(s).
    </p>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    
    <p style="color: #888; font-size: 12px;">
        If you did not expect this password reset, please contact your administrator.
    </p>
</body>
</html>
"""
    
    # Send email
    try:
        notifier._send_email_sync(account.email, subject, body, html_body)
        logger.info(f"Password reset email sent to {account.email} (admin_initiated={admin_initiated})")
        return True
    except Exception as e:
        logger.error(f"Failed to send password reset email to {account.email}: {e}")
        return False


def send_registration_verification_email(
    reg_request,
    expiry_hours: int | None = None,
    source_ip: str | None = None
) -> bool:
    """Send registration verification email with secure link.
    
    The link is IP-bound for security - the email must be opened from the
    same IP that initiated the registration to prevent interception.
    
    Args:
        reg_request: RegistrationRequest object with email and username
        expiry_hours: Optional custom expiry hours (default: 1 hour)
        source_ip: IP address of the registrant (for IP-bound token security)
    
    Returns True if email sent successfully.
    """
    from flask import url_for
    from .email_notifier import get_email_notifier_from_config
    from .database import get_system_config
    
    email = reg_request.email
    username = reg_request.username
    
    if not email:
        logger.warning(f"No email address for registration {username}")
        return False
    
    # Default expiry: 1 hour for registration verification
    if expiry_hours is None:
        expiry_hours = int(os.environ.get('REGISTRATION_VERIFY_EXPIRY_HOURS', '1'))
    
    # Generate verification token with IP binding
    # reg_request has .id and .username, which is what generate_reset_token needs
    raw_token, actual_expiry = generate_reset_token(
        reg_request,
        expiry_hours,
        source_ip=source_ip,
        token_type='verify'
    )
    
    # Build verify URL
    try:
        verify_url = url_for('account.verify_email_link', token=raw_token, _external=True)
    except RuntimeError:
        # If we're outside request context, build manually
        base_url = os.environ.get('BASE_URL', 'http://localhost:5100')
        verify_url = f"{base_url}/account/register/verify/{raw_token}"
    
    # Get email configuration
    email_config = get_system_config('email_config')
    if not email_config:
        logger.warning("Email configuration not set - cannot send verification email")
        return False
    
    notifier = get_email_notifier_from_config(email_config)
    if not notifier:
        logger.warning("Failed to create email notifier from config")
        return False
    
    subject = "[Netcup API Filter] Verify Your Email Address"
    body = f"""
Email Verification

Hello {username},

Please verify your email address by clicking the link below:
{verify_url}

This link will expire in {actual_expiry} hour(s).

IMPORTANT: For security, you must open this link from the same network
you used to register. If you change networks, you'll need to request
a new verification link.

If you did not request this registration, you can ignore this email.

---
Netcup API Filter
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #3498db;">Email Verification</h2>
    
    <p>Hello <strong>{username}</strong>,</p>
    
    <p>Please verify your email address by clicking the button below:</p>
    
    <p style="margin: 20px 0;">
        <a href="{verify_url}" style="background-color: #27ae60; color: white; padding: 12px 24px; 
           text-decoration: none; border-radius: 4px; display: inline-block;">
            Verify Email
        </a>
    </p>
    
    <p style="color: #666; font-size: 14px;">
        Or copy this link: <a href="{verify_url}">{verify_url}</a>
    </p>
    
    <p style="color: #888;">
        This link will expire in {actual_expiry} hour(s).
    </p>
    
    <p style="color: #e74c3c; font-size: 14px;">
        <strong>Security Notice:</strong> You must open this link from the same network
        you used to register. If you change networks, request a new verification link.
    </p>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    
    <p style="color: #888; font-size: 12px;">
        If you did not request this registration, you can ignore this email.
    </p>
</body>
</html>
"""
    
    # Send email
    try:
        notifier._send_email_sync(email, subject, body, html_body)
        logger.info(f"Registration verification email sent to {email} (IP={source_ip or 'not bound'})")
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email to {email}: {e}")
        return False


def send_account_invite_email(
    account: Account,
    expiry_hours: int | None = None,
    admin_username: str | None = None,
    include_realm: bool = True
) -> bool:
    """Send account invite email for admin-created accounts.
    
    This is sent when an admin creates an account. The user must click the
    invite link to set their password and activate the account.
    
    Args:
        account: The account to send invite to
        expiry_hours: Optional custom expiry hours (default: 48 hours for invites)
        admin_username: Username of the admin who created the account
    
    Returns True if email sent successfully.
    """
    from flask import url_for
    from .email_notifier import get_email_notifier_from_config
    from .database import get_system_config
    
    # Check if account has an email
    if not account.email:
        logger.warning(f"No email address for account {account.username}")
        return False
    
    # Invites have longer expiry by default (48 hours)
    if expiry_hours is None:
        expiry_hours = int(os.environ.get('ACCOUNT_INVITE_EXPIRY_HOURS', '48'))
    
    # Generate invite token (no IP binding for invites - user may open on different device)
    raw_token, actual_expiry = generate_reset_token(
        account,
        expiry_hours,
        source_ip=None,  # No IP binding for invites
        token_type='invite'
    )
    
    # Build invite URL
    try:
        invite_url = url_for('account.accept_invite', token=raw_token, _external=True)
    except RuntimeError:
        # If we're outside request context, build manually
        base_url = os.environ.get('BASE_URL', 'http://localhost:5100')
        invite_url = f"{base_url}/account/invite/{raw_token}"
    
    # Get email configuration
    email_config = get_system_config('email_config')
    if not email_config:
        logger.warning("Email configuration not set - cannot send invite email")
        return False
    
    notifier = get_email_notifier_from_config(email_config)
    if not notifier:
        logger.warning("Failed to create email notifier from config")
        return False
    
    admin_text = f" by {admin_username}" if admin_username else ""
    
    subject = "[Netcup API Filter] Your Account Has Been Created"
    body = f"""
Account Invitation

Hello {account.username},

An account has been created for you{admin_text} on the Netcup API Filter system.

To activate your account and set your password, please click the link below:
{invite_url}

This link will expire in {actual_expiry} hours.

If you did not expect this invitation, please contact your administrator.

---
Netcup API Filter
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #3498db;">Account Invitation</h2>
    
    <p>Hello <strong>{account.username}</strong>,</p>
    
    <p>An account has been created for you{admin_text} on the Netcup API Filter system.</p>
    
    <p>To activate your account and set your password, click the button below:</p>
    
    <p style="margin: 20px 0;">
        <a href="{invite_url}" style="background-color: #27ae60; color: white; padding: 12px 24px; 
           text-decoration: none; border-radius: 4px; display: inline-block;">
            Activate Account
        </a>
    </p>
    
    <p style="color: #666; font-size: 14px;">
        Or copy this link: <a href="{invite_url}">{invite_url}</a>
    </p>
    
    <p style="color: #888;">
        This link will expire in {actual_expiry} hours.
    </p>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    
    <p style="color: #888; font-size: 12px;">
        If you did not expect this invitation, please contact your administrator.
    </p>
</body>
</html>
"""
    
    # Send email
    try:
        notifier._send_email_sync(account.email, subject, body, html_body)
        logger.info(f"Account invite email sent to {account.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send invite email to {account.email}: {e}")
        return False
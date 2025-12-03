"""
Notification service for netcup-api-filter.

Centralizes all notification triggers and templates.
Supports email notifications with optional expansion to other channels.

Notification triggers (from UI_REQUIREMENTS.md P7.5):
- Token expiring (7 days warning)
- Failed login attempts
- New IP detected
- Account approved
- Account rejected
- Realm approved/rejected
"""
import logging
from datetime import datetime
from typing import Optional

from .database import db
from .models import Account, AccountRealm, APIToken

logger = logging.getLogger(__name__)


def _get_notifier():
    """Get email notifier from config (lazy load to avoid circular imports)."""
    from .email_notifier import get_email_notifier_from_config
    from .database import get_system_config
    
    email_config = get_system_config('email_config')
    if not email_config:
        logger.debug("Email configuration not set")
        return None
    
    return get_email_notifier_from_config(email_config)


def _get_admin_email() -> Optional[str]:
    """Get admin notification email from config."""
    from .database import get_system_config
    
    email_config = get_system_config('email_config')
    if email_config:
        return email_config.get('admin_notification_email')
    return None


def _get_base_url() -> str:
    """Get base URL for links in emails."""
    from .database import get_system_config
    import os
    
    # Try config first, then environment
    general_config = get_system_config('general')
    if general_config and general_config.get('base_url'):
        return general_config['base_url'].rstrip('/')
    
    return os.environ.get('NAF_BASE_URL', 'https://naf.example.com')


# =============================================================================
# Registration Notifications
# =============================================================================

def send_verification_email(email: str, username: str, code: str, expires_minutes: int = 30) -> bool:
    """
    Send email verification code for new registration.
    
    Args:
        email: Recipient email address
        username: New account username
        code: 6-digit verification code
        expires_minutes: Code validity in minutes
        
    Returns:
        True if email sent successfully, False otherwise
    """
    notifier = _get_notifier()
    if not notifier:
        logger.warning(f"Email notifier not configured - cannot send verification to {email}")
        return False
    
    subject = "[Netcup API Filter] Verify Your Email Address"
    
    body = f"""Hello {username},

Thank you for registering with Netcup API Filter.

Your verification code is:

    {code}

This code expires in {expires_minutes} minutes.

Enter this code on the verification page to complete your registration.

What's next:
- Enter the code above to verify your email
- Your account will await admin approval
- You'll receive an email once approved

If you didn't create an account, you can safely ignore this email.

---
This is an automated message from Netcup API Filter.
"""
    
    html_body = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; background-color: #1a1a2e; color: #f3f4f6; }}
    </style>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; background-color: #1a1a2e; color: #f3f4f6; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #0f172a; border-radius: 12px; padding: 30px; border: 1px solid rgba(59, 130, 246, 0.2);">
        <h2 style="margin: 0 0 20px; color: #f3f4f6; font-size: 20px; font-weight: 600;">
            Verify Your Email Address
        </h2>
        
        <p style="margin: 0 0 20px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            Hi <strong style="color: #f3f4f6;">{username}</strong>,
        </p>
        
        <p style="margin: 0 0 25px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            Thank you for registering with Netcup API Filter. Please use the verification code below to confirm your email address:
        </p>
        
        <div style="text-align: center;">
            <div style="display: inline-block; background: linear-gradient(135deg, rgba(59, 130, 246, 0.15) 0%, rgba(59, 130, 246, 0.05) 100%); border: 2px solid rgba(59, 130, 246, 0.4); border-radius: 12px; padding: 25px 50px;">
                <span style="font-family: 'Courier New', Courier, monospace; font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #3b82f6;">
                    {code}
                </span>
            </div>
        </div>
        
        <p style="margin: 25px 0 0; color: #6b7280; font-size: 13px; text-align: center;">
            This code expires in <strong style="color: #f59e0b;">{expires_minutes} minutes</strong>.
        </p>
        
        <hr style="border: none; border-top: 1px solid rgba(59, 130, 246, 0.15); margin: 30px 0;">
        
        <p style="margin: 0; color: #6b7280; font-size: 13px; line-height: 1.6;">
            <strong>What's next?</strong>
        </p>
        <ul style="margin: 10px 0 0 20px; padding: 0; color: #6b7280; font-size: 13px; line-height: 1.8;">
            <li>Enter the code above to verify your email</li>
            <li>Your account will await admin approval</li>
            <li>You'll receive an email once approved</li>
        </ul>
        
        <p style="margin: 25px 0 0; color: #6b7280; font-size: 12px;">
            If you didn't create an account, you can safely ignore this email.
        </p>
        
        <hr style="border: none; border-top: 1px solid rgba(59, 130, 246, 0.15); margin: 30px 0;">
        <p style="margin: 0; color: #4b5563; font-size: 11px; text-align: center;">
            This is an automated message from Netcup API Filter.
        </p>
    </div>
</body>
</html>
"""
    
    try:
        # Send immediately (no delay for verification emails)
        notifier._send_email_sync(email, subject, body, html_body)
        logger.info(f"Sent verification email to {email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email to {email}: {e}")
        return False


# =============================================================================
# Account Notifications
# =============================================================================

def notify_account_approved(account: Account) -> bool:
    """
    Send notification when account is approved.
    
    Args:
        account: The approved account
        
    Returns:
        True if notification sent, False otherwise
    """
    if not account.email:
        logger.debug(f"No email for account {account.username}")
        return False
    
    notifier = _get_notifier()
    if not notifier:
        return False
    
    base_url = _get_base_url()
    login_url = f"{base_url}/account/login"
    
    subject = "[Netcup API Filter] Your Account Has Been Approved"
    
    body = f"""Hello {account.username},

Great news! Your account has been approved.

You can now log in and start managing your DNS tokens:
{login_url}

Username: {account.username}

If you have any questions, please contact the administrator.

---
This is an automated message from Netcup API Filter.
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #10b981;">🎉 Account Approved!</h2>
    
    <p>Hello <strong>{account.username}</strong>,</p>
    
    <p>Great news! Your account has been approved.</p>
    
    <p>You can now log in and start managing your DNS tokens:</p>
    
    <p style="margin: 20px 0;">
        <a href="{login_url}" 
           style="background-color: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
            Log In Now
        </a>
    </p>
    
    <p><strong>Username:</strong> <code>{account.username}</code></p>
    
    <p style="color: #666;">If you have any questions, please contact the administrator.</p>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    <p style="color: #888; font-size: 12px;">
        This is an automated message from Netcup API Filter.
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body)
        logger.info(f"Sent account approved notification to {account.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send account approved notification: {e}")
        return False


def notify_account_rejected(account: Account, reason: str) -> bool:
    """
    Send notification when account is rejected.
    
    Args:
        account: The rejected account
        reason: Rejection reason
        
    Returns:
        True if notification sent, False otherwise
    """
    if not account.email:
        logger.debug(f"No email for account {account.username}")
        return False
    
    notifier = _get_notifier()
    if not notifier:
        return False
    
    subject = "[Netcup API Filter] Account Application Update"
    
    body = f"""Hello {account.username},

We regret to inform you that your account application has not been approved.

Reason: {reason}

If you believe this is an error or would like more information, 
please contact the administrator.

---
This is an automated message from Netcup API Filter.
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #ef4444;">Account Application Update</h2>
    
    <p>Hello <strong>{account.username}</strong>,</p>
    
    <p>We regret to inform you that your account application has not been approved.</p>
    
    <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 12px; margin: 16px 0;">
        <strong>Reason:</strong> {reason}
    </div>
    
    <p>If you believe this is an error or would like more information, 
    please contact the administrator.</p>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    <p style="color: #888; font-size: 12px;">
        This is an automated message from Netcup API Filter.
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body)
        logger.info(f"Sent account rejected notification to {account.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send account rejected notification: {e}")
        return False


# =============================================================================
# Realm Notifications
# =============================================================================

def notify_realm_pending(realm: AccountRealm) -> bool:
    """
    Notify admin of pending realm request.
    
    Args:
        realm: The pending realm
        
    Returns:
        True if notification sent, False otherwise
    """
    admin_email = _get_admin_email()
    if not admin_email:
        logger.debug("No admin email configured for realm pending notification")
        return False
    
    notifier = _get_notifier()
    if not notifier:
        return False
    
    base_url = _get_base_url()
    admin_url = f"{base_url}/admin/realms/pending"
    
    subject = f"[Netcup API Filter] New Realm Request: {realm.realm_type}:{realm.realm_value}"
    
    account = realm.account
    
    body = f"""A new realm request requires your approval.

Account: {account.username}
Domain: {realm.domain}
Type: {realm.realm_type}
Value: {realm.realm_value}
Record Types: {realm.allowed_record_types}
Operations: {realm.allowed_operations}

Review and approve/reject at:
{admin_url}

---
This is an automated message from Netcup API Filter.
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #f59e0b;">📋 New Realm Request</h2>
    
    <p>A new realm request requires your approval.</p>
    
    <table style="border-collapse: collapse; width: 100%; max-width: 500px; margin: 16px 0;">
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Account</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{account.username}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Domain</td>
            <td style="padding: 8px; border: 1px solid #ddd;"><code>{realm.domain}</code></td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Type</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{realm.realm_type}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Value</td>
            <td style="padding: 8px; border: 1px solid #ddd;"><code>{realm.realm_value}</code></td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Record Types</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{realm.allowed_record_types}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Operations</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{realm.allowed_operations}</td>
        </tr>
    </table>
    
    <p>
        <a href="{admin_url}" 
           style="background-color: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
            Review Pending Realms
        </a>
    </p>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    <p style="color: #888; font-size: 12px;">
        This is an automated message from Netcup API Filter.
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(admin_email, subject, body, html_body)
        logger.info(f"Sent realm pending notification to admin")
        return True
    except Exception as e:
        logger.error(f"Failed to send realm pending notification: {e}")
        return False


def notify_realm_approved(realm: AccountRealm) -> bool:
    """
    Notify account owner when their realm is approved.
    
    Args:
        realm: The approved realm
        
    Returns:
        True if notification sent, False otherwise
    """
    account = realm.account
    if not account.email:
        logger.debug(f"No email for account {account.username}")
        return False
    
    notifier = _get_notifier()
    if not notifier:
        return False
    
    base_url = _get_base_url()
    tokens_url = f"{base_url}/account/realms/{realm.id}/tokens"
    
    subject = f"[Netcup API Filter] Realm Approved: {realm.realm_value}"
    
    body = f"""Hello {account.username},

Your realm request has been approved!

Realm Details:
- Domain: {realm.domain}
- Type: {realm.realm_type}
- Value: {realm.realm_value}
- Record Types: {realm.allowed_record_types}
- Operations: {realm.allowed_operations}

You can now create tokens for this realm:
{tokens_url}

---
This is an automated message from Netcup API Filter.
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #10b981;">✅ Realm Approved!</h2>
    
    <p>Hello <strong>{account.username}</strong>,</p>
    
    <p>Your realm request has been approved!</p>
    
    <h3>Realm Details</h3>
    <table style="border-collapse: collapse; width: 100%; max-width: 500px; margin: 16px 0;">
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Domain</td>
            <td style="padding: 8px; border: 1px solid #ddd;"><code>{realm.domain}</code></td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Type</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{realm.realm_type}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Value</td>
            <td style="padding: 8px; border: 1px solid #ddd;"><code>{realm.realm_value}</code></td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Record Types</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{realm.allowed_record_types}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Operations</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{realm.allowed_operations}</td>
        </tr>
    </table>
    
    <p>
        <a href="{tokens_url}" 
           style="background-color: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
            Create Tokens
        </a>
    </p>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    <p style="color: #888; font-size: 12px;">
        This is an automated message from Netcup API Filter.
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body)
        logger.info(f"Sent realm approved notification to {account.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send realm approved notification: {e}")
        return False


def notify_realm_rejected(realm: AccountRealm, reason: str) -> bool:
    """
    Notify account owner when their realm is rejected.
    
    Args:
        realm: The rejected realm
        reason: Rejection reason
        
    Returns:
        True if notification sent, False otherwise
    """
    account = realm.account
    if not account.email:
        logger.debug(f"No email for account {account.username}")
        return False
    
    notifier = _get_notifier()
    if not notifier:
        return False
    
    subject = f"[Netcup API Filter] Realm Request Update: {realm.realm_value}"
    
    body = f"""Hello {account.username},

Unfortunately, your realm request has not been approved.

Realm Details:
- Domain: {realm.domain}
- Type: {realm.realm_type}
- Value: {realm.realm_value}

Reason: {reason}

If you believe this is an error or would like more information,
please contact the administrator.

---
This is an automated message from Netcup API Filter.
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #ef4444;">Realm Request Update</h2>
    
    <p>Hello <strong>{account.username}</strong>,</p>
    
    <p>Unfortunately, your realm request has not been approved.</p>
    
    <h3>Realm Details</h3>
    <table style="border-collapse: collapse; width: 100%; max-width: 500px; margin: 16px 0;">
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Domain</td>
            <td style="padding: 8px; border: 1px solid #ddd;"><code>{realm.domain}</code></td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Type</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{realm.realm_type}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Value</td>
            <td style="padding: 8px; border: 1px solid #ddd;"><code>{realm.realm_value}</code></td>
        </tr>
    </table>
    
    <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 12px; margin: 16px 0;">
        <strong>Reason:</strong> {reason}
    </div>
    
    <p>If you believe this is an error or would like more information,
    please contact the administrator.</p>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    <p style="color: #888; font-size: 12px;">
        This is an automated message from Netcup API Filter.
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body)
        logger.info(f"Sent realm rejected notification to {account.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send realm rejected notification: {e}")
        return False


# =============================================================================
# Security Notifications
# =============================================================================

def notify_failed_login(account: Account, ip_address: str, attempts: int) -> bool:
    """
    Notify account owner of failed login attempts.
    
    Args:
        account: The target account
        ip_address: Source IP of failed attempts
        attempts: Number of failed attempts
        
    Returns:
        True if notification sent, False otherwise
    """
    if not account.email:
        return False
    
    notifier = _get_notifier()
    if not notifier:
        return False
    
    subject = f"[Netcup API Filter] Security Alert: Failed Login Attempts"
    
    body = f"""Hello {account.username},

We detected {attempts} failed login attempt(s) to your account.

IP Address: {ip_address}
Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

If this was you, you can ignore this message.
If you did not attempt to log in, please change your password immediately.

---
This is an automated security notification from Netcup API Filter.
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #f59e0b;">⚠️ Security Alert</h2>
    
    <p>Hello <strong>{account.username}</strong>,</p>
    
    <p>We detected <strong>{attempts}</strong> failed login attempt(s) to your account.</p>
    
    <table style="border-collapse: collapse; margin: 16px 0;">
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">IP Address</td>
            <td style="padding: 8px; border: 1px solid #ddd;"><code>{ip_address}</code></td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Time</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
        </tr>
    </table>
    
    <p>If this was you, you can ignore this message.</p>
    <p><strong>If you did not attempt to log in, please change your password immediately.</strong></p>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    <p style="color: #888; font-size: 12px;">
        This is an automated security notification from Netcup API Filter.
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body, delay=0)
        logger.info(f"Sent failed login notification to {account.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send failed login notification: {e}")
        return False


def notify_new_ip_login(account: Account, ip_address: str, location: Optional[str] = None) -> bool:
    """
    Notify account owner of login from new IP address.
    
    Args:
        account: The account
        ip_address: New IP address
        location: Optional GeoIP location string
        
    Returns:
        True if notification sent, False otherwise
    """
    if not account.email:
        return False
    
    notifier = _get_notifier()
    if not notifier:
        return False
    
    location_str = f" ({location})" if location else ""
    
    subject = "[Netcup API Filter] New Login Location Detected"
    
    body = f"""Hello {account.username},

We noticed a login to your account from a new IP address.

IP Address: {ip_address}{location_str}
Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

If this was you, you can ignore this message.
If you did not log in from this location, please change your password immediately.

---
This is an automated security notification from Netcup API Filter.
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #3b82f6;">📍 New Login Location</h2>
    
    <p>Hello <strong>{account.username}</strong>,</p>
    
    <p>We noticed a login to your account from a new IP address.</p>
    
    <table style="border-collapse: collapse; margin: 16px 0;">
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">IP Address</td>
            <td style="padding: 8px; border: 1px solid #ddd;"><code>{ip_address}</code>{location_str}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Time</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
        </tr>
    </table>
    
    <p>If this was you, you can ignore this message.</p>
    <p><strong>If you did not log in from this location, please change your password immediately.</strong></p>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    <p style="color: #888; font-size: 12px;">
        This is an automated security notification from Netcup API Filter.
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body, delay=0)
        logger.info(f"Sent new IP login notification to {account.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send new IP login notification: {e}")
        return False


# =============================================================================
# Token Expiration Notifications
# =============================================================================

def notify_token_expiring(token: APIToken, days_remaining: int) -> bool:
    """
    Notify account owner that token is expiring soon.
    
    Args:
        token: The expiring token
        days_remaining: Days until expiration
        
    Returns:
        True if notification sent, False otherwise
    """
    account = token.realm.account
    if not account.email:
        return False
    
    notifier = _get_notifier()
    if not notifier:
        return False
    
    base_url = _get_base_url()
    tokens_url = f"{base_url}/account/realms/{token.realm_id}/tokens"
    
    subject = f"[Netcup API Filter] Token Expiring: {token.token_name or token.token_prefix}"
    
    body = f"""Hello {account.username},

One of your API tokens is expiring soon.

Token Details:
- Name: {token.token_name}
- Description: {token.token_description or '(none)'}
- Prefix: {token.token_prefix}
- Realm: {token.realm.realm_value}
- Expires: {token.expires_at.strftime('%Y-%m-%d') if token.expires_at else 'Never'}
- Days Remaining: {days_remaining}

To continue using this token, please regenerate it before it expires:
{tokens_url}

---
This is an automated message from Netcup API Filter.
"""
    
    urgency_color = "#ef4444" if days_remaining <= 3 else "#f59e0b"
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: {urgency_color};">⏰ Token Expiring Soon</h2>
    
    <p>Hello <strong>{account.username}</strong>,</p>
    
    <p>One of your API tokens is expiring in <strong>{days_remaining} day(s)</strong>.</p>
    
    <table style="border-collapse: collapse; width: 100%; max-width: 500px; margin: 16px 0;">
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Description</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{token.token_name}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Prefix</td>
            <td style="padding: 8px; border: 1px solid #ddd;"><code>{token.token_prefix}</code></td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Realm</td>
            <td style="padding: 8px; border: 1px solid #ddd;"><code>{token.realm.realm_value}</code></td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Expires</td>
            <td style="padding: 8px; border: 1px solid #ddd; color: {urgency_color}; font-weight: bold;">
                {token.expires_at.strftime('%Y-%m-%d') if token.expires_at else 'Never'}
            </td>
        </tr>
    </table>
    
    <p>To continue using this token, please regenerate it before it expires:</p>
    
    <p>
        <a href="{tokens_url}" 
           style="background-color: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
            Manage Tokens
        </a>
    </p>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    <p style="color: #888; font-size: 12px;">
        This is an automated message from Netcup API Filter.
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body)
        logger.info(f"Sent token expiring notification to {account.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send token expiring notification: {e}")
        return False

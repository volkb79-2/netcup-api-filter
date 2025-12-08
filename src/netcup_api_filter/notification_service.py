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

Each email includes a reference ID in the footer for traceability.
Format: NAF-{type}-{timestamp}-{random}
"""
import logging
from datetime import datetime
from typing import Optional

from .database import db
from .email_reference import generate_email_ref
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
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('verify', username)
    
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
Ref: {email_ref}
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
        <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
            Ref: {email_ref}
        </p>
    </div>
</body>
</html>
"""
    
    try:
        # Send immediately (no delay for verification emails)
        notifier._send_email_sync(email, subject, body, html_body)
        logger.info(f"Sent verification email to {email} [ref={email_ref}]")
        return True
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email to {email}: {e}")
        return False


def send_2fa_email(email: str, username: str, code: str, expires_minutes: int = 5) -> bool:
    """
    Send 2FA verification code via email.
    
    Args:
        email: Recipient email address
        username: Account username
        code: 6-digit verification code
        expires_minutes: Code validity in minutes (default 5)
        
    Returns:
        True if email sent successfully, False otherwise
    """
    notifier = _get_notifier()
    if not notifier:
        logger.warning(f"Email notifier not configured - cannot send 2FA code to {email}")
        return False
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('2fa', username)
    
    subject = "[Netcup API Filter] Your Login Verification Code"
    
    body = f"""Hello {username},

Your login verification code is:

    {code}

This code expires in {expires_minutes} minutes.

If you did not attempt to log in, please change your password immediately.

---
This is an automated message from Netcup API Filter.
Ref: {email_ref}
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; background-color: #1a1a2e; color: #f3f4f6; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #0f172a; border-radius: 12px; padding: 30px; border: 1px solid rgba(59, 130, 246, 0.2);">
        <h2 style="margin: 0 0 20px; color: #f3f4f6; font-size: 20px; font-weight: 600;">
            Login Verification Code
        </h2>
        
        <p style="margin: 0 0 20px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            Hi <strong style="color: #f3f4f6;">{username}</strong>,
        </p>
        
        <p style="margin: 0 0 25px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            Here is your login verification code:
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
        
        <p style="margin: 0; color: #ef4444; font-size: 13px;">
            ⚠️ If you did not attempt to log in, please change your password immediately.
        </p>
        
        <hr style="border: none; border-top: 1px solid rgba(59, 130, 246, 0.15); margin: 30px 0;">
        <p style="margin: 0; color: #4b5563; font-size: 11px; text-align: center;">
            This is an automated message from Netcup API Filter.
        </p>
        <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
            Ref: {email_ref}
        </p>
    </div>
</body>
</html>
"""
    
    try:
        # Send immediately (2FA codes are time-sensitive)
        notifier._send_email_sync(email, subject, body, html_body)
        logger.info(f"Sent 2FA code via email to {email} [ref={email_ref}]")
        return True
        return True
    except Exception as e:
        logger.error(f"Failed to send 2FA email to {email}: {e}")
        return False


def notify_admin_pending_account(account_username: str, account_email: str, realm_count: int = 0) -> bool:
    """
    Notify admin of a new account pending approval.
    
    Args:
        account_username: Username of the pending account
        account_email: Email of the pending account
        realm_count: Number of realm requests included with registration
        
    Returns:
        True if notification sent, False otherwise
    """
    admin_email = _get_admin_email()
    if not admin_email:
        logger.debug("No admin email configured for pending account notification")
        return False
    
    notifier = _get_notifier()
    if not notifier:
        return False
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('notify', account_username)
    
    base_url = _get_base_url()
    admin_url = f"{base_url}/admin/accounts/pending"
    
    realm_info = f"\nRealm Requests: {realm_count}" if realm_count > 0 else ""
    realm_badge = f' + {realm_count} realm(s)' if realm_count > 0 else ""
    
    subject = f"[Netcup API Filter] New Account Pending: {account_username}{realm_badge}"
    
    body = f"""A new account registration requires your approval.

Username: {account_username}
Email: {account_email}{realm_info}

Review and approve/reject at:
{admin_url}

---
This is an automated message from Netcup API Filter.
"""
    
    realm_row = ""
    if realm_count > 0:
        realm_row = f"""
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Realm Requests</td>
            <td style="padding: 8px; border: 1px solid #ddd;"><span style="background-color: #fef3c7; color: #92400e; padding: 2px 8px; border-radius: 4px;">{realm_count} pending</span></td>
        </tr>"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #f59e0b;">👤 New Account Pending Approval</h2>
    
    <p>A new account registration requires your approval.</p>
    
    <table style="border-collapse: collapse; width: 100%; max-width: 400px; margin: 16px 0;">
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Username</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{account_username}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">Email</td>
            <td style="padding: 8px; border: 1px solid #ddd;"><a href="mailto:{account_email}">{account_email}</a></td>
        </tr>{realm_row}
    </table>
    
    <p>
        <a href="{admin_url}" 
           style="background-color: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
            Review Pending Accounts
        </a>
    </p>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    <p style="color: #888; font-size: 12px;">
        This is an automated message from Netcup API Filter.
    </p>
    <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
        Ref: {email_ref}
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(admin_email, subject, body, html_body)
        logger.info(f"Sent pending account notification to admin for {account_username} with {realm_count} realm requests [ref={email_ref}]")
        return True
    except Exception as e:
        logger.error(f"Failed to send pending account notification: {e}")
        return False


def send_password_reset_email(email: str, username: str, code: str, expires_minutes: int = 30) -> bool:
    """
    Send password reset code via email.
    
    Args:
        email: Recipient email address
        username: Account username
        code: 6-digit reset code
        expires_minutes: Code validity in minutes
        
    Returns:
        True if email sent successfully, False otherwise
    """
    notifier = _get_notifier()
    if not notifier:
        logger.warning(f"Email notifier not configured - cannot send password reset to {email}")
        return False
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('reset', username)
    
    base_url = _get_base_url()
    reset_url = f"{base_url}/account/reset-password"
    
    subject = "[Netcup API Filter] Password Reset Request"
    
    body = f"""Hello {username},

You requested a password reset for your account.

Your reset code is:

    {code}

This code expires in {expires_minutes} minutes.

Enter this code at: {reset_url}

If you didn't request a password reset, you can safely ignore this email.
Your password will remain unchanged.

---
This is an automated message from Netcup API Filter.
Ref: {email_ref}
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; background-color: #1a1a2e; color: #f3f4f6; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #0f172a; border-radius: 12px; padding: 30px; border: 1px solid rgba(59, 130, 246, 0.2);">
        <h2 style="margin: 0 0 20px; color: #f3f4f6; font-size: 20px; font-weight: 600;">
            Password Reset Request
        </h2>
        
        <p style="margin: 0 0 20px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            Hi <strong style="color: #f3f4f6;">{username}</strong>,
        </p>
        
        <p style="margin: 0 0 25px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            You requested a password reset for your account. Here is your reset code:
        </p>
        
        <div style="text-align: center;">
            <div style="display: inline-block; background: linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(239, 68, 68, 0.05) 100%); border: 2px solid rgba(239, 68, 68, 0.4); border-radius: 12px; padding: 25px 50px;">
                <span style="font-family: 'Courier New', Courier, monospace; font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #ef4444;">
                    {code}
                </span>
            </div>
        </div>
        
        <p style="margin: 25px 0 0; color: #6b7280; font-size: 13px; text-align: center;">
            This code expires in <strong style="color: #f59e0b;">{expires_minutes} minutes</strong>.
        </p>
        
        <p style="margin: 20px 0; text-align: center;">
            <a href="{reset_url}" 
               style="background-color: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                Reset Password
            </a>
        </p>
        
        <hr style="border: none; border-top: 1px solid rgba(59, 130, 246, 0.15); margin: 30px 0;">
        
        <p style="margin: 0; color: #6b7280; font-size: 13px;">
            If you didn't request a password reset, you can safely ignore this email.
            Your password will remain unchanged.
        </p>
        
        <hr style="border: none; border-top: 1px solid rgba(59, 130, 246, 0.15); margin: 30px 0;">
        <p style="margin: 0; color: #4b5563; font-size: 11px; text-align: center;">
            This is an automated message from Netcup API Filter.
        </p>
        <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
            Ref: {email_ref}
        </p>
    </div>
</body>
</html>
"""
    
    try:
        # Send immediately (password reset codes are time-sensitive)
        notifier._send_email_sync(email, subject, body, html_body)
        logger.info(f"Sent password reset email to {email} [ref={email_ref}]")
        return True
    except Exception as e:
        logger.error(f"Failed to send password reset email to {email}: {e}")
        return False


# =============================================================================
# Account Notifications
# =============================================================================

def notify_account_approved(account: Account, realm_count: int = 0) -> bool:
    """
    Send notification when account is approved.
    
    Args:
        account: The approved account
        realm_count: Number of realm requests that were also approved
        
    Returns:
        True if notification sent, False otherwise
    """
    if not account.email:
        logger.debug(f"No email for account {account.username}")
        return False
    
    notifier = _get_notifier()
    if not notifier:
        return False
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('notify', account.username)
    
    base_url = _get_base_url()
    login_url = f"{base_url}/account/login"
    
    # Build realm info text
    realm_text = ""
    realm_html = ""
    if realm_count > 0:
        realm_word = "domain" if realm_count == 1 else "domains"
        realm_text = f"\n\nYour {realm_count} requested {realm_word} have also been approved. You can now create tokens for these domains."
        realm_html = f"""
    <p style="background-color: #d1fae5; padding: 12px; border-radius: 6px; border-left: 4px solid #10b981;">
        ✅ Your <strong>{realm_count} requested {realm_word}</strong> have also been approved. 
        You can now create tokens for these domains.
    </p>
"""
    
    subject = "[Netcup API Filter] Your Account Has Been Approved"
    
    body = f"""Hello {account.username},

Great news! Your account has been approved.{realm_text}

You can now log in and start managing your DNS tokens:
{login_url}

Username: {account.username}

If you have any questions, please contact the administrator.

---
This is an automated message from Netcup API Filter.
Ref: {email_ref}
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #10b981;">🎉 Account Approved!</h2>
    
    <p>Hello <strong>{account.username}</strong>,</p>
    
    <p>Great news! Your account has been approved.</p>
    {realm_html}
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
    <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
        Ref: {email_ref}
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body)
        logger.info(f"Sent account approved notification to {account.email} [ref={email_ref}]")
        return True
    except Exception as e:
        logger.error(f"Failed to send account approved notification: {e}")
        return False


def notify_account_rejected(email: str, username: str, reason: str | None = None) -> bool:
    """
    Send notification when account is rejected.
    
    Args:
        email: Email address to notify
        username: Username of the rejected account
        reason: Optional rejection reason
        
    Returns:
        True if notification sent, False otherwise
    """
    if not email:
        logger.debug(f"No email for account {username}")
        return False
    
    notifier = _get_notifier()
    if not notifier:
        return False
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('notify', username)
    
    reason_text = reason or "No specific reason provided."
    
    subject = "[Netcup API Filter] Account Application Update"
    
    body = f"""Hello {username},

We regret to inform you that your account application has not been approved.

Reason: {reason_text}

If you believe this is an error or would like more information, 
please contact the administrator.

---
This is an automated message from Netcup API Filter.
Ref: {email_ref}
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #ef4444;">Account Application Update</h2>
    
    <p>Hello <strong>{username}</strong>,</p>
    
    <p>We regret to inform you that your account application has not been approved.</p>
    
    <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 12px; margin: 16px 0;">
        <strong>Reason:</strong> {reason_text}
    </div>
    
    <p>If you believe this is an error or would like more information, 
    please contact the administrator.</p>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    <p style="color: #888; font-size: 12px;">
        This is an automated message from Netcup API Filter.
    </p>
    <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
        Ref: {email_ref}
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(email, subject, body, html_body)
        logger.info(f"Sent account rejected notification to {email} [ref={email_ref}]")
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
    
    account = realm.account
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('notify', account.username)
    
    base_url = _get_base_url()
    admin_url = f"{base_url}/admin/realms/pending"
    
    subject = f"[Netcup API Filter] New Realm Request: {realm.realm_type}:{realm.realm_value}"
    
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
Ref: {email_ref}
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
    <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
        Ref: {email_ref}
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(admin_email, subject, body, html_body)
        logger.info(f"Sent realm pending notification to admin [ref={email_ref}]")
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
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('notify', account.username)
    
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
Ref: {email_ref}
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
    <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
        Ref: {email_ref}
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body)
        logger.info(f"Sent realm approved notification to {account.email} [ref={email_ref}]")
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
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('notify', account.username)
    
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
Ref: {email_ref}
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
    <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
        Ref: {email_ref}
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body)
        logger.info(f"Sent realm rejected notification to {account.email} [ref={email_ref}]")
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
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('alert', account.username)
    
    subject = f"[Netcup API Filter] Security Alert: Failed Login Attempts"
    
    body = f"""Hello {account.username},

We detected {attempts} failed login attempt(s) to your account.

IP Address: {ip_address}
Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

If this was you, you can ignore this message.
If you did not attempt to log in, please change your password immediately.

---
This is an automated security notification from Netcup API Filter.
Ref: {email_ref}
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
    <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
        Ref: {email_ref}
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body, delay=0)
        logger.info(f"Sent failed login notification to {account.email} [ref={email_ref}]")
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
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('notify', account.username)
    
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
Ref: {email_ref}
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
    <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
        Ref: {email_ref}
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body, delay=0)
        logger.info(f"Sent new IP login notification to {account.email} [ref={email_ref}]")
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
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('notify', account.username)
    
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
Ref: {email_ref}
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
    <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
        Ref: {email_ref}
    </p>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body)
        logger.info(f"Sent token expiring notification to {account.email} [ref={email_ref}]")
        return True
    except Exception as e:
        logger.error(f"Failed to send token expiring notification: {e}")
        return False


# =============================================================================
# Password Changed Notification
# =============================================================================

def notify_password_changed(account: Account, source_ip: Optional[str] = None) -> bool:
    """
    Send notification when password is changed.
    
    Security alert to inform user their password was changed.
    
    Args:
        account: Account whose password was changed
        source_ip: IP address where change was made (optional)
        
    Returns:
        True if notification sent successfully
    """
    notifier = _get_notifier()
    if not notifier:
        logger.warning(f"Email notifier not configured - cannot send password changed notification")
        return False
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('notify', account.username)
    
    base_url = _get_base_url()
    login_url = f"{base_url}/account/login"
    reset_url = f"{base_url}/account/forgot-password"
    
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    ip_info = f"from IP address {source_ip}" if source_ip else ""
    
    subject = "[Netcup API Filter] Password Changed"
    
    body = f"""Hello {account.username},

Your password was successfully changed {ip_info}.

Time: {timestamp}

If you made this change, no further action is needed.

If you did NOT change your password:
1. Someone may have access to your account
2. Request a password reset immediately: {reset_url}
3. Review your account security settings
4. Contact your administrator if you need assistance

---
This is an automated security notification from Netcup API Filter.
Ref: {email_ref}
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
            🔐 Password Changed
        </h2>
        
        <p style="margin: 0 0 20px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            Hi <strong style="color: #f3f4f6;">{account.username}</strong>,
        </p>
        
        <p style="margin: 0 0 20px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            Your password was successfully changed{' ' + ip_info if ip_info else ''}.
        </p>
        
        <div style="background-color: rgba(34, 197, 94, 0.1); border-left: 4px solid #22c55e; padding: 15px; margin: 20px 0;">
            <p style="margin: 0; color: #22c55e; font-size: 14px;">
                <strong>Time:</strong> {timestamp}
            </p>
        </div>
        
        <p style="margin: 20px 0; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            If you made this change, no further action is needed.
        </p>
        
        <div style="background-color: rgba(239, 68, 68, 0.1); border-left: 4px solid #ef4444; padding: 15px; margin: 20px 0;">
            <p style="margin: 0 0 10px; color: #ef4444; font-weight: bold;">
                ⚠️ If you did NOT change your password:
            </p>
            <ol style="margin: 0; padding-left: 20px; color: #fca5a5;">
                <li>Someone may have access to your account</li>
                <li>Request a password reset immediately</li>
                <li>Review your account security settings</li>
                <li>Contact your administrator if needed</li>
            </ol>
        </div>
        
        <p style="margin: 20px 0;">
            <a href="{reset_url}" 
               style="display: inline-block; background-color: #ef4444; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: 600;">
                Reset Password Now
            </a>
        </p>
        
        <hr style="border: none; border-top: 1px solid rgba(59, 130, 246, 0.15); margin: 30px 0;">
        
        <p style="margin: 0; color: #6b7280; font-size: 12px;">
            This is an automated security notification from Netcup API Filter.
        </p>
        <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
            Ref: {email_ref}
        </p>
    </div>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body)
        logger.info(f"Sent password changed notification to {account.email} [ref={email_ref}]")
        return True
    except Exception as e:
        logger.error(f"Failed to send password changed notification: {e}")
        return False


# =============================================================================
# Token Revoked Notification
# =============================================================================

def notify_token_revoked(
    account: Account,
    token: APIToken,
    revoked_by: str,
    reason: Optional[str] = None
) -> bool:
    """
    Send notification when a token is revoked.
    
    Informs token owner their token has been revoked.
    
    Args:
        account: Account that owns the token
        token: The revoked token
        revoked_by: Username who revoked the token
        reason: Optional reason for revocation
        
    Returns:
        True if notification sent successfully
    """
    notifier = _get_notifier()
    if not notifier:
        logger.warning(f"Email notifier not configured - cannot send token revoked notification")
        return False
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('notify', account.username)
    
    base_url = _get_base_url()
    tokens_url = f"{base_url}/account/tokens"
    
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    reason_text = f"\nReason: {reason}" if reason else ""
    
    subject = "[Netcup API Filter] API Token Revoked"
    
    body = f"""Hello {account.username},

One of your API tokens has been revoked.

Token Details:
- Name: {token.token_name}
- Prefix: {token.token_prefix}
- Realm: {token.realm.realm_value}
- Revoked By: {revoked_by}
- Time: {timestamp}{reason_text}

This token can no longer be used for API access. Any applications or scripts using
this token will need to be updated with a new token.

To create a new token, visit:
{tokens_url}

If you did not authorize this revocation, please contact your administrator immediately.

---
This is an automated notification from Netcup API Filter.
Ref: {email_ref}
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
        <h2 style="margin: 0 0 20px; color: #ef4444; font-size: 20px; font-weight: 600;">
            🔴 API Token Revoked
        </h2>
        
        <p style="margin: 0 0 20px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            Hi <strong style="color: #f3f4f6;">{account.username}</strong>,
        </p>
        
        <p style="margin: 0 0 20px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            One of your API tokens has been revoked and can no longer be used.
        </p>
        
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0; background-color: rgba(15, 23, 42, 0.5); border-radius: 8px; overflow: hidden;">
            <tr>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #9ca3af; width: 30%;">Token Name</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #f3f4f6;">{token.token_name}</td>
            </tr>
            <tr>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #9ca3af;">Prefix</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #f3f4f6;">
                    <code style="background-color: rgba(59, 130, 246, 0.1); padding: 2px 6px; border-radius: 4px;">{token.token_prefix}</code>
                </td>
            </tr>
            <tr>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #9ca3af;">Realm</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #f3f4f6;">{token.realm.realm_value}</td>
            </tr>
            <tr>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #9ca3af;">Revoked By</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #f3f4f6;">{revoked_by}</td>
            </tr>
            <tr>
                <td style="padding: 12px 16px; color: #9ca3af;">Time</td>
                <td style="padding: 12px 16px; color: #f3f4f6;">{timestamp}</td>
            </tr>
            {f'<tr><td style="padding: 12px 16px; color: #9ca3af;">Reason</td><td style="padding: 12px 16px; color: #fca5a5;">{reason}</td></tr>' if reason else ''}
        </table>
        
        <div style="background-color: rgba(245, 158, 11, 0.1); border-left: 4px solid #f59e0b; padding: 15px; margin: 20px 0;">
            <p style="margin: 0; color: #fbbf24; font-size: 14px;">
                ⚠️ Applications using this token will no longer work. Create a new token if needed.
            </p>
        </div>
        
        <p style="margin: 20px 0;">
            <a href="{tokens_url}" 
               style="display: inline-block; background-color: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: 600;">
                Manage Tokens
            </a>
        </p>
        
        <hr style="border: none; border-top: 1px solid rgba(59, 130, 246, 0.15); margin: 30px 0;">
        
        <p style="margin: 0; color: #6b7280; font-size: 12px;">
            If you did not authorize this revocation, please contact your administrator immediately.
        </p>
        <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
            Ref: {email_ref}
        </p>
    </div>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body)
        logger.info(f"Sent token revoked notification to {account.email} for token {token.token_prefix} [ref={email_ref}]")
        return True
    except Exception as e:
        logger.error(f"Failed to send token revoked notification: {e}")
        return False


# =============================================================================
# Credential Rotation Notification
# =============================================================================

def notify_credential_rotation(
    account: Account,
    tokens_invalidated: int,
    reason: str,
    admin_username: Optional[str] = None
) -> bool:
    """
    Send notification when user_alias is regenerated, invalidating all tokens.
    
    This is a critical security notification.
    
    Args:
        account: Account whose credentials were rotated
        tokens_invalidated: Number of tokens that were invalidated
        reason: Why rotation was performed
        admin_username: Admin who initiated (None if self-service)
        
    Returns:
        True if notification sent successfully
    """
    notifier = _get_notifier()
    if not notifier:
        logger.warning(f"Email notifier not configured - cannot send credential rotation notification")
        return False
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('alert', account.username)
    
    base_url = _get_base_url()
    tokens_url = f"{base_url}/account/tokens"
    
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    initiator = f"admin ({admin_username})" if admin_username else "you"
    
    subject = "[Netcup API Filter] ⚠️ All API Credentials Rotated"
    
    body = f"""SECURITY ALERT: Credential Rotation

Hello {account.username},

All of your API credentials have been rotated by {initiator}.

Details:
- Time: {timestamp}
- Tokens Invalidated: {tokens_invalidated}
- Reason: {reason}

IMPORTANT: All existing API tokens are now INVALID.

What this means:
- Any applications using your tokens will stop working
- You must generate new tokens in your account
- This action cannot be undone

If you did not authorize this:
1. Contact your administrator immediately
2. Review your account security settings
3. Check for unauthorized access

Generate new tokens: {tokens_url}

---
This is a critical security notification from Netcup API Filter.
Ref: {email_ref}
"""
    
    html_body = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; background-color: #1a1a2e; color: #f3f4f6; }}
    </style>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; background-color: #1a1a2e; color: #f3f4f6; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #0f172a; border-radius: 12px; padding: 30px; border: 1px solid rgba(239, 68, 68, 0.3);">
        <h2 style="margin: 0 0 20px; color: #ef4444; font-size: 20px; font-weight: 600;">
            ⚠️ All API Credentials Rotated
        </h2>
        
        <p style="margin: 0 0 20px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            Hi <strong style="color: #f3f4f6;">{account.username}</strong>,
        </p>
        
        <div style="background-color: rgba(239, 68, 68, 0.1); border-left: 4px solid #ef4444; padding: 15px; margin: 20px 0;">
            <p style="margin: 0; color: #fca5a5; font-size: 14px;">
                <strong>All of your API credentials have been rotated.</strong>
            </p>
        </div>
        
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0; background-color: rgba(15, 23, 42, 0.5); border-radius: 8px; overflow: hidden;">
            <tr>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #9ca3af; width: 30%;">Initiated By</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #f3f4f6;">{initiator.title()}</td>
            </tr>
            <tr>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #9ca3af;">Time</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #f3f4f6;">{timestamp}</td>
            </tr>
            <tr>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #9ca3af;">Tokens Invalidated</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #ef4444; font-weight: bold;">{tokens_invalidated}</td>
            </tr>
            <tr>
                <td style="padding: 12px 16px; color: #9ca3af;">Reason</td>
                <td style="padding: 12px 16px; color: #f3f4f6;">{reason}</td>
            </tr>
        </table>
        
        <p style="margin: 20px 0; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            <strong style="color: #f3f4f6;">All existing API tokens are now INVALID.</strong>
            Any applications using your tokens will stop working until you generate new ones.
        </p>
        
        <p style="margin: 20px 0;">
            <a href="{tokens_url}" 
               style="display: inline-block; background-color: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: 600;">
                Generate New Tokens
            </a>
        </p>
        
        <hr style="border: none; border-top: 1px solid rgba(59, 130, 246, 0.15); margin: 30px 0;">
        
        <p style="margin: 0; color: #ef4444; font-size: 12px;">
            ⚠️ If you did not authorize this action, contact your administrator immediately.
        </p>
        <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
            Ref: {email_ref}
        </p>
    </div>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(account.email, subject, body, html_body)
        logger.info(f"Sent credential rotation notification to {account.email} ({tokens_invalidated} tokens) [ref={email_ref}]")
        return True
    except Exception as e:
        logger.error(f"Failed to send credential rotation notification: {e}")
        return False


# =============================================================================
# Email Changed Notifications
# =============================================================================

def notify_email_changed_old(
    account: Account,
    old_email: str,
    new_email: str,
    admin_username: Optional[str] = None
) -> bool:
    """
    Send security alert to OLD email when address is changed.
    
    Args:
        account: Account whose email was changed
        old_email: Previous email address (where notification goes)
        new_email: New email address
        admin_username: Admin who made change (None if self-service)
        
    Returns:
        True if notification sent successfully
    """
    notifier = _get_notifier()
    if not notifier:
        logger.warning(f"Email notifier not configured - cannot send email changed notification")
        return False
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('alert', account.username)
    
    base_url = _get_base_url()
    
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    initiator = f"administrator ({admin_username})" if admin_username else "you"
    
    subject = "[Netcup API Filter] ⚠️ Your Email Address Was Changed"
    
    body = f"""SECURITY ALERT: Email Address Changed

Hello {account.username},

Your email address was changed by {initiator}.

Details:
- Time: {timestamp}
- Old Email: {old_email}
- New Email: {new_email}

If you authorized this change, no action is needed.

If you did NOT authorize this change:
1. Contact your administrator IMMEDIATELY
2. Your account may be compromised
3. Request a password reset

---
This is a critical security notification from Netcup API Filter.
Ref: {email_ref}
"""
    
    html_body = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; background-color: #1a1a2e; color: #f3f4f6; }}
    </style>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; background-color: #1a1a2e; color: #f3f4f6; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #0f172a; border-radius: 12px; padding: 30px; border: 1px solid rgba(239, 68, 68, 0.3);">
        <h2 style="margin: 0 0 20px; color: #ef4444; font-size: 20px; font-weight: 600;">
            ⚠️ Your Email Address Was Changed
        </h2>
        
        <p style="margin: 0 0 20px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            Hi <strong style="color: #f3f4f6;">{account.username}</strong>,
        </p>
        
        <div style="background-color: rgba(239, 68, 68, 0.1); border-left: 4px solid #ef4444; padding: 15px; margin: 20px 0;">
            <p style="margin: 0; color: #fca5a5; font-size: 14px;">
                <strong>Your account email was changed by {initiator}.</strong>
            </p>
        </div>
        
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0; background-color: rgba(15, 23, 42, 0.5); border-radius: 8px; overflow: hidden;">
            <tr>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #9ca3af; width: 30%;">Time</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #f3f4f6;">{timestamp}</td>
            </tr>
            <tr>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #9ca3af;">Old Email</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #f3f4f6;">{old_email}</td>
            </tr>
            <tr>
                <td style="padding: 12px 16px; color: #9ca3af;">New Email</td>
                <td style="padding: 12px 16px; color: #fbbf24;">{new_email}</td>
            </tr>
        </table>
        
        <hr style="border: none; border-top: 1px solid rgba(59, 130, 246, 0.15); margin: 30px 0;">
        
        <p style="margin: 0; color: #ef4444; font-size: 12px;">
            ⚠️ If you did not authorize this change, contact your administrator IMMEDIATELY.
        </p>
        <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
            Ref: {email_ref}
        </p>
    </div>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(old_email, subject, body, html_body)
        logger.info(f"Sent email changed alert to old address {old_email} [ref={email_ref}]")
        return True
    except Exception as e:
        logger.error(f"Failed to send email changed notification to old address: {e}")
        return False


def notify_email_changed_new(
    account: Account,
    old_email: str,
    new_email: str,
    admin_username: Optional[str] = None
) -> bool:
    """
    Send confirmation to NEW email when address is changed.
    
    Args:
        account: Account whose email was changed
        old_email: Previous email address
        new_email: New email address (where notification goes)
        admin_username: Admin who made change (None if self-service)
        
    Returns:
        True if notification sent successfully
    """
    notifier = _get_notifier()
    if not notifier:
        logger.warning(f"Email notifier not configured - cannot send email changed notification")
        return False
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('notify', account.username)
    
    base_url = _get_base_url()
    login_url = f"{base_url}/account/login"
    
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    initiator = f"administrator ({admin_username})" if admin_username else "you"
    
    subject = "[Netcup API Filter] Email Address Updated"
    
    body = f"""Hello {account.username},

Your email address was updated by {initiator}.

Details:
- Time: {timestamp}
- Old Email: {old_email}
- New Email: {new_email} (this address)

This email will now be used for:
- Login notifications
- Security alerts
- Password resets
- Account notifications

Login to your account: {login_url}

---
This is an automated notification from Netcup API Filter.
Ref: {email_ref}
"""
    
    html_body = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; background-color: #1a1a2e; color: #f3f4f6; }}
    </style>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; background-color: #1a1a2e; color: #f3f4f6; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #0f172a; border-radius: 12px; padding: 30px; border: 1px solid rgba(34, 197, 94, 0.2);">
        <h2 style="margin: 0 0 20px; color: #22c55e; font-size: 20px; font-weight: 600;">
            ✅ Email Address Updated
        </h2>
        
        <p style="margin: 0 0 20px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            Hi <strong style="color: #f3f4f6;">{account.username}</strong>,
        </p>
        
        <p style="margin: 0 0 20px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            Your account email has been updated by {initiator}.
        </p>
        
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0; background-color: rgba(15, 23, 42, 0.5); border-radius: 8px; overflow: hidden;">
            <tr>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #9ca3af; width: 30%;">Time</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #f3f4f6;">{timestamp}</td>
            </tr>
            <tr>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #9ca3af;">Old Email</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid rgba(59, 130, 246, 0.1); color: #6b7280;">{old_email}</td>
            </tr>
            <tr>
                <td style="padding: 12px 16px; color: #9ca3af;">New Email</td>
                <td style="padding: 12px 16px; color: #22c55e; font-weight: bold;">{new_email}</td>
            </tr>
        </table>
        
        <p style="margin: 20px 0;">
            <a href="{login_url}" 
               style="display: inline-block; background-color: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: 600;">
                Login to Account
            </a>
        </p>
        
        <hr style="border: none; border-top: 1px solid rgba(59, 130, 246, 0.15); margin: 30px 0;">
        
        <p style="margin: 0; color: #6b7280; font-size: 12px;">
            This email will now receive all account notifications and security alerts.
        </p>
        <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
            Ref: {email_ref}
        </p>
    </div>
</body>
</html>
"""
    
    try:
        notifier.send_email_async(new_email, subject, body, html_body)
        logger.info(f"Sent email changed confirmation to new address {new_email} [ref={email_ref}]")
        return True
    except Exception as e:
        logger.error(f"Failed to send email changed notification to new address: {e}")
        return False


# =============================================================================
# Generic send_notification Function
# =============================================================================

def send_notification(
    account: Account,
    subject: str,
    template: str,
    context: dict,
    override_email: Optional[str] = None
) -> bool:
    """
    Generic notification sender that dispatches to specific functions.
    
    Args:
        account: Account to notify
        subject: Email subject (may be overridden by template)
        template: Template name to use
        context: Template context variables
        override_email: Send to this email instead of account.email
        
    Returns:
        True if notification sent successfully
    """
    # Map template names to functions
    if template == 'credential_rotation':
        return notify_credential_rotation(
            account=account,
            tokens_invalidated=context.get('tokens_invalidated', 0),
            reason=context.get('reason', 'Unknown'),
            admin_username=context.get('admin_username')
        )
    
    elif template == 'email_changed_old':
        return notify_email_changed_old(
            account=account,
            old_email=context.get('old_email', ''),
            new_email=context.get('new_email', ''),
            admin_username=context.get('admin_username')
        )
    
    elif template == 'email_changed_new':
        return notify_email_changed_new(
            account=account,
            old_email=context.get('old_email', ''),
            new_email=context.get('new_email', ''),
            admin_username=context.get('admin_username')
        )
    
    else:
        logger.warning(f"Unknown notification template: {template}")
        return False


def send_security_alert_email(
    email: str,
    username: str,
    alert_type: str,
    details: dict
) -> bool:
    """
    Send a security alert email (failed logins, suspicious activity, etc).
    
    Args:
        email: Recipient email address
        username: Account username
        alert_type: Type of alert (failed_login, account_lockout, ip_blocked, etc)
        details: Dictionary with alert-specific details
            - failed_count: Number of failed attempts
            - source_ip: IP address of attempts
            - lockout_minutes: Duration of lockout
            - timestamp: When this happened
        
    Returns:
        True if email sent successfully, False otherwise
    """
    notifier = _get_notifier()
    if not notifier:
        logger.warning(f"Email notifier not configured - cannot send security alert to {email}")
        return False
    
    # Generate email reference ID for traceability
    email_ref = generate_email_ref('alert', username)
    
    # Build subject based on alert type
    subjects = {
        'failed_login': "[SECURITY ALERT] Multiple Failed Login Attempts",
        'account_lockout': "[SECURITY ALERT] Account Temporarily Locked",
        'ip_blocked': "[SECURITY ALERT] IP Address Blocked",
        'suspicious_activity': "[SECURITY ALERT] Suspicious Activity Detected",
    }
    subject = subjects.get(alert_type, "[SECURITY ALERT] Security Notice")
    
    # Extract details
    failed_count = details.get('failed_count', 0)
    source_ip = details.get('source_ip', 'Unknown')
    lockout_minutes = details.get('lockout_minutes', 0)
    timestamp = details.get('timestamp', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'))
    
    # Build body based on alert type
    if alert_type == 'failed_login':
        body = f"""Hello {username},

We detected {failed_count} failed login attempts on your admin account.

Details:
- Source IP: {source_ip}
- Time: {timestamp}

If this was you, no action is needed. If you do not recognize this activity, please:
1. Change your password immediately
2. Review your account security settings
3. Enable two-factor authentication if not already enabled

---
This is an automated security alert from Netcup API Filter.
Ref: {email_ref}
"""
        alert_icon = "⚠️"
        alert_color = "#f59e0b"  # amber
        
    elif alert_type == 'account_lockout':
        body = f"""Hello {username},

Your admin account has been temporarily locked due to multiple failed login attempts.

Details:
- Failed attempts: {failed_count}
- Source IP: {source_ip}
- Locked until: {lockout_minutes} minutes from now

If this was you, wait for the lockout to expire and try again.
If you do not recognize this activity, please contact your system administrator.

---
This is an automated security alert from Netcup API Filter.
Ref: {email_ref}
"""
        alert_icon = "🔒"
        alert_color = "#ef4444"  # red
        
    else:
        body = f"""Hello {username},

A security alert has been triggered on your admin account.

Details:
- Alert type: {alert_type}
- Source IP: {source_ip}
- Time: {timestamp}

Please review your account security settings.

---
This is an automated security alert from Netcup API Filter.
Ref: {email_ref}
"""
        alert_icon = "🛡️"
        alert_color = "#3b82f6"  # blue
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; background-color: #1a1a2e; color: #f3f4f6; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #0f172a; border-radius: 12px; padding: 30px; border: 1px solid {alert_color}40;">
        <div style="text-align: center; margin-bottom: 20px;">
            <span style="font-size: 48px;">{alert_icon}</span>
        </div>
        
        <h2 style="margin: 0 0 20px; color: {alert_color}; font-size: 20px; font-weight: 600; text-align: center;">
            Security Alert
        </h2>
        
        <p style="margin: 0 0 20px; color: #9ca3af; font-size: 15px; line-height: 1.6;">
            Hi <strong style="color: #f3f4f6;">{username}</strong>,
        </p>
        
        <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 20px; margin: 20px 0;">
            <table style="width: 100%; color: #f3f4f6; font-size: 14px;">
                <tr>
                    <td style="padding: 8px 0; color: #9ca3af;">Alert Type:</td>
                    <td style="padding: 8px 0; text-align: right; font-weight: bold;">{alert_type.replace('_', ' ').title()}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #9ca3af;">Source IP:</td>
                    <td style="padding: 8px 0; text-align: right; font-family: monospace;">{source_ip}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #9ca3af;">Failed Attempts:</td>
                    <td style="padding: 8px 0; text-align: right; font-weight: bold; color: #ef4444;">{failed_count}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #9ca3af;">Time:</td>
                    <td style="padding: 8px 0; text-align: right;">{timestamp}</td>
                </tr>
            </table>
        </div>
        
        <p style="margin: 20px 0; color: #9ca3af; font-size: 14px; line-height: 1.6;">
            If you do not recognize this activity:
        </p>
        <ul style="color: #9ca3af; font-size: 14px; margin: 0 0 20px; padding-left: 20px;">
            <li>Change your password immediately</li>
            <li>Review your account security settings</li>
            <li>Enable two-factor authentication</li>
        </ul>
        
        <hr style="border: none; border-top: 1px solid rgba(59, 130, 246, 0.15); margin: 30px 0;">
        <p style="margin: 0; color: #4b5563; font-size: 11px; text-align: center;">
            This is an automated security alert from Netcup API Filter.
        </p>
        <p style="margin: 8px 0 0; color: #374151; font-size: 10px; text-align: center;">
            Ref: {email_ref}
        </p>
    </div>
</body>
</html>
"""
    
    try:
        # Send immediately (security alerts are time-sensitive)
        notifier._send_email_sync(email, subject, body, html_body)
        logger.info(f"Sent security alert ({alert_type}) to {email} [ref={email_ref}]")
        return True
    except Exception as e:
        logger.error(f"Failed to send security alert to {email}: {e}")
        return False

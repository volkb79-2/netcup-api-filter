"""
Password Reset Service.

Handles:
- Generating secure password reset tokens
- Sending password reset emails
- Verifying reset tokens
- Completing password resets
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from .models import Account, db

logger = logging.getLogger(__name__)

# Token storage - in production would use database or Redis
# Format: {token_hash: (account_id, expires_at)}
_reset_tokens: dict[str, Tuple[int, datetime]] = {}

# Token validity period
TOKEN_EXPIRY_HOURS = 1


def generate_reset_token(account: Account) -> str:
    """Generate a secure password reset token for an account.
    
    Returns the raw token (to be sent in email).
    Only the hash is stored.
    """
    # Invalidate any existing tokens for this account
    invalidate_tokens_for_account(account.id)
    
    # Generate secure random token
    raw_token = secrets.token_urlsafe(48)
    
    # Store hash of token
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)
    
    _reset_tokens[token_hash] = (account.id, expires_at)
    
    logger.info(f"Password reset token generated for account {account.username}")
    return raw_token


def invalidate_tokens_for_account(account_id: int) -> None:
    """Invalidate all reset tokens for an account."""
    to_remove = [
        token_hash for token_hash, (aid, _) in _reset_tokens.items()
        if aid == account_id
    ]
    for token_hash in to_remove:
        del _reset_tokens[token_hash]


def verify_reset_token(raw_token: str) -> Optional[Account]:
    """Verify a password reset token and return the associated account.
    
    Returns None if token is invalid or expired.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    
    token_data = _reset_tokens.get(token_hash)
    if not token_data:
        logger.debug("Password reset token not found")
        return None
    
    account_id, expires_at = token_data
    
    if datetime.utcnow() > expires_at:
        # Token expired - remove it
        del _reset_tokens[token_hash]
        logger.debug(f"Password reset token expired for account_id={account_id}")
        return None
    
    account = Account.query.get(account_id)
    if not account:
        del _reset_tokens[token_hash]
        logger.debug(f"Account not found for reset token: account_id={account_id}")
        return None
    
    return account


def complete_password_reset(account: Account, new_password: str, raw_token: str) -> Tuple[bool, str]:
    """Complete a password reset by setting new password.
    
    Returns (success, error_message).
    """
    import bcrypt
    
    # Verify token is still valid
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    if token_hash not in _reset_tokens:
        return False, "Reset link is no longer valid"
    
    # Update password
    password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    account.password_hash = password_hash
    account.updated_at = datetime.utcnow()
    
    # Clear must_change_password flag if set
    if hasattr(account, 'must_change_password'):
        account.must_change_password = False
    
    db.session.commit()
    
    # Invalidate the used token
    del _reset_tokens[token_hash]
    
    # Invalidate all other tokens for this account
    invalidate_tokens_for_account(account.id)
    
    logger.info(f"Password reset completed for account {account.username}")
    return True, ""


def send_password_reset_email(account: Account) -> bool:
    """Send password reset email to account.
    
    Returns True if email sent successfully.
    """
    from flask import url_for, current_app
    from .email_notifier import get_email_notifier_from_config
    from .database import get_system_config
    
    # Check if account has an email
    if not account.email:
        logger.warning(f"No email address for account {account.username}")
        return False
    
    # Generate token
    raw_token = generate_reset_token(account)
    
    # Build reset URL
    try:
        reset_url = url_for('account.reset_password', token=raw_token, _external=True)
    except RuntimeError:
        # If we're outside request context, build manually
        base_url = os.environ.get('BASE_URL', 'http://localhost:5100')
        reset_url = f"{base_url}/account/reset-password/{raw_token}"
    
    # Get email configuration
    email_config = get_system_config('email_config')
    if not email_config:
        logger.warning("Email configuration not set - cannot send password reset email")
        return False
    
    notifier = get_email_notifier_from_config(email_config)
    if not notifier:
        logger.warning("Failed to create email notifier from config")
        return False
    
    # Build email content
    subject = "[Netcup API Filter] Password Reset Request"
    
    body = f"""
Password Reset Request

Hello {account.username},

A password reset was requested for your account.

Click the link below to reset your password:
{reset_url}

This link will expire in {TOKEN_EXPIRY_HOURS} hour(s).

If you did not request this, please ignore this email.

---
Netcup API Filter
"""
    
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #3498db;">Password Reset Request</h2>
    
    <p>Hello <strong>{account.username}</strong>,</p>
    
    <p>A password reset was requested for your account.</p>
    
    <p>Click the button below to reset your password:</p>
    
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
        This link will expire in {TOKEN_EXPIRY_HOURS} hour(s).
    </p>
    
    <hr style="margin-top: 20px; border: none; border-top: 1px solid #ddd;">
    
    <p style="color: #888; font-size: 12px;">
        If you did not request this password reset, please ignore this email.<br>
        Your password will remain unchanged.
    </p>
</body>
</html>
"""
    
    # Send email
    try:
        notifier._send_email_sync(account.email, subject, body, html_body)
        logger.info(f"Password reset email sent to {account.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send password reset email to {account.email}: {e}")
        return False

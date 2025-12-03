"""
Account authentication service for UI login.

Handles:
- Account registration with email verification
- Login with mandatory 2FA (email, TOTP, or Telegram)
- Password management
- Session handling

2FA Flow:
1. User submits username + password
2. If valid, system generates 2FA code
3. Code sent via preferred method (email, TOTP, Telegram)
4. User submits code
5. If valid, session created
"""
import logging
import os
import random
import string
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, NamedTuple, Optional

from flask import g, redirect, request, session, url_for

from .config_defaults import get_default
from .models import (
    Account,
    ActivityLog,
    RegistrationRequest,
    db,
    validate_username,
)

logger = logging.getLogger(__name__)

# Session configuration
SESSION_KEY_USER_ID = 'account_id'
SESSION_KEY_USERNAME = 'account_username'
SESSION_KEY_2FA_PENDING = '2fa_pending'
SESSION_KEY_2FA_CODE = '2fa_code'
SESSION_KEY_2FA_EXPIRES = '2fa_expires'
SESSION_KEY_2FA_METHOD = '2fa_method'

# 2FA configuration
TFA_CODE_LENGTH = 6
TFA_CODE_EXPIRY_MINUTES = 5
TFA_MAX_ATTEMPTS = 5

# Verification code configuration
VERIFICATION_CODE_LENGTH = 6
VERIFICATION_EXPIRY_MINUTES = 30


class RegistrationResult(NamedTuple):
    """Result of registration attempt."""
    success: bool
    request_id: Optional[int] = None
    error: Optional[str] = None
    field: Optional[str] = None  # Which field had error (for form validation)


class LoginResult(NamedTuple):
    """Result of login attempt."""
    success: bool
    account: Optional[Account] = None
    requires_2fa: bool = False
    tfa_methods: Optional[list[str]] = None  # Available 2FA methods
    error: Optional[str] = None


class TwoFactorResult(NamedTuple):
    """Result of 2FA verification."""
    success: bool
    account: Optional[Account] = None
    error: Optional[str] = None


def generate_code(length: int = 6) -> str:
    """Generate a random numeric code."""
    return ''.join(random.choices(string.digits, k=length))


def generate_secure_password(length: int = 16) -> str:
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choices(alphabet, k=length))


# ============================================================================
# Registration
# ============================================================================

def register_account(
    username: str,
    email: str,
    password: str
) -> RegistrationResult:
    """
    Start account registration.
    
    Creates a registration request with verification code.
    Does NOT create the account until email is verified AND admin approves.
    
    Returns:
        RegistrationResult with request_id on success
    """
    # Validate username
    is_valid, error_msg = validate_username(username)
    if not is_valid:
        return RegistrationResult(success=False, error=error_msg, field='username')
    
    # Check username not taken
    if Account.query.filter_by(username=username).first():
        return RegistrationResult(
            success=False, 
            error="Username already registered",
            field='username'
        )
    
    if RegistrationRequest.query.filter_by(username=username).first():
        return RegistrationResult(
            success=False,
            error="Username already has pending registration",
            field='username'
        )
    
    # Validate email format (basic check)
    if not email or '@' not in email or '.' not in email:
        return RegistrationResult(
            success=False,
            error="Invalid email address",
            field='email'
        )
    
    # Check email not taken
    if Account.query.filter_by(email=email).first():
        return RegistrationResult(
            success=False,
            error="Email already registered",
            field='email'
        )
    
    if RegistrationRequest.query.filter_by(email=email).first():
        return RegistrationResult(
            success=False,
            error="Email already has pending registration",
            field='email'
        )
    
    # Validate password (minimum requirements)
    if len(password) < 12:
        return RegistrationResult(
            success=False,
            error="Password must be at least 12 characters",
            field='password'
        )
    
    # Create registration request
    reg_request = RegistrationRequest(
        username=username,
        email=email,
        verification_code=generate_code(VERIFICATION_CODE_LENGTH),
        verification_expires_at=datetime.utcnow() + timedelta(minutes=VERIFICATION_EXPIRY_MINUTES)
    )
    reg_request.set_password(password)
    
    db.session.add(reg_request)
    db.session.commit()
    
    logger.info(f"Registration request created: {username} ({email})")
    
    # Send verification email
    from .notification_service import send_verification_email
    send_verification_email(
        email=email,
        username=username,
        code=reg_request.verification_code,
        expires_minutes=VERIFICATION_EXPIRY_MINUTES
    )
    
    return RegistrationResult(success=True, request_id=reg_request.id)


def verify_registration(request_id: int, code: str) -> RegistrationResult:
    """
    Verify email with verification code.
    
    On success, creates the Account (still pending admin approval).
    """
    reg_request = RegistrationRequest.query.get(request_id)
    if not reg_request:
        return RegistrationResult(success=False, error="Registration not found")
    
    # Check if expired
    if reg_request.is_expired():
        db.session.delete(reg_request)
        db.session.commit()
        return RegistrationResult(success=False, error="Verification code expired")
    
    # Check if locked
    if reg_request.is_locked():
        return RegistrationResult(success=False, error="Too many verification attempts")
    
    # Verify code
    if reg_request.verification_code != code:
        reg_request.verification_attempts += 1
        db.session.commit()
        attempts_left = 5 - reg_request.verification_attempts
        return RegistrationResult(
            success=False,
            error=f"Invalid verification code. {attempts_left} attempts remaining."
        )
    
    # Create account (pending approval)
    account = Account(
        username=reg_request.username,
        email=reg_request.email,
        password_hash=reg_request.password_hash,
        email_verified=1,
        email_2fa_enabled=1,  # Email 2FA mandatory
        is_active=0,  # Pending admin approval
    )
    
    db.session.add(account)
    db.session.delete(reg_request)
    db.session.commit()
    
    logger.info(f"Account created (pending approval): {account.username}")
    
    # TODO: Notify admin of pending approval
    
    return RegistrationResult(success=True)


def resend_verification(request_id: int) -> RegistrationResult:
    """
    Resend verification code with new code and extended expiry.
    """
    reg_request = RegistrationRequest.query.get(request_id)
    if not reg_request:
        return RegistrationResult(success=False, error="Registration not found")
    
    # Generate new code
    reg_request.verification_code = generate_code(VERIFICATION_CODE_LENGTH)
    reg_request.verification_expires_at = datetime.utcnow() + timedelta(minutes=VERIFICATION_EXPIRY_MINUTES)
    reg_request.verification_attempts = 0  # Reset attempts
    
    db.session.commit()
    
    logger.info(f"Verification code resent for: {reg_request.username}")
    
    # Send verification email
    from .notification_service import send_verification_email
    send_verification_email(
        email=reg_request.email,
        username=reg_request.username,
        code=reg_request.verification_code,
        expires_minutes=VERIFICATION_EXPIRY_MINUTES
    )
    
    return RegistrationResult(success=True, request_id=request_id)


# ============================================================================
# Login
# ============================================================================

def login_step1(username: str, password: str, source_ip: str) -> LoginResult:
    """
    First step of login: verify username and password.
    
    If valid, returns the available 2FA methods.
    Does NOT create session yet.
    """
    # Find account
    account = Account.query.filter_by(username=username).first()
    
    if not account:
        # Log failed attempt (don't reveal if username exists)
        log_login_attempt(
            username=username,
            source_ip=source_ip,
            success=False,
            reason="Invalid credentials"
        )
        return LoginResult(success=False, error="Invalid username or password")
    
    # Check password
    if not account.verify_password(password):
        log_login_attempt(
            username=username,
            source_ip=source_ip,
            success=False,
            reason="Invalid password"
        )
        return LoginResult(success=False, error="Invalid username or password")
    
    # Check account is active
    if not account.is_active:
        log_login_attempt(
            username=username,
            source_ip=source_ip,
            success=False,
            reason="Account pending approval"
        )
        return LoginResult(success=False, error="Account is pending admin approval")
    
    # Check email verified
    if not account.email_verified:
        return LoginResult(success=False, error="Email not verified")
    
    # Determine available 2FA methods
    tfa_methods = []
    if account.email_2fa_enabled:
        tfa_methods.append('email')
    if account.totp_enabled:
        tfa_methods.append('totp')
    if account.telegram_enabled:
        tfa_methods.append('telegram')
    
    # At least one 2FA method required
    if not tfa_methods:
        # This shouldn't happen due to DB constraint, but handle gracefully
        logger.error(f"Account {username} has no 2FA methods enabled")
        return LoginResult(success=False, error="2FA configuration error")
    
    # Store pending 2FA in session
    session[SESSION_KEY_2FA_PENDING] = account.id
    
    logger.info(f"Login step 1 passed for {username}, 2FA required")
    
    return LoginResult(
        success=True,
        account=account,
        requires_2fa=True,
        tfa_methods=tfa_methods
    )


def send_2fa_code(account_id: int, method: str, source_ip: str) -> tuple[bool, str | None]:
    """
    Generate and send 2FA code via specified method.
    
    Args:
        account_id: Account to send code to
        method: 'email', 'totp', or 'telegram'
        source_ip: For logging
    
    Returns:
        (success, error_message)
    """
    account = Account.query.get(account_id)
    if not account:
        return False, "Account not found"
    
    code = generate_code(TFA_CODE_LENGTH)
    expires_at = datetime.utcnow() + timedelta(minutes=TFA_CODE_EXPIRY_MINUTES)
    
    # Store code in session
    session[SESSION_KEY_2FA_CODE] = code
    session[SESSION_KEY_2FA_EXPIRES] = expires_at.isoformat()
    session[SESSION_KEY_2FA_METHOD] = method
    
    if method == 'email':
        # TODO: Send email with code
        # send_2fa_email(account.email, code)
        logger.info(f"2FA code sent via email to {account.username}")
        return True, None
    
    elif method == 'totp':
        # TOTP doesn't need code sent - user generates from authenticator
        # Clear the code we generated - TOTP verification handles its own
        session.pop(SESSION_KEY_2FA_CODE, None)
        logger.info(f"TOTP requested for {account.username}")
        return True, None
    
    elif method == 'telegram':
        if not account.telegram_chat_id:
            return False, "Telegram not configured"
        # TODO: Send telegram message
        # send_telegram_2fa(account.telegram_chat_id, code)
        logger.info(f"2FA code sent via Telegram to {account.username}")
        return True, None
    
    return False, f"Unknown 2FA method: {method}"


def verify_2fa(code: str, source_ip: str) -> TwoFactorResult:
    """
    Verify 2FA code and complete login.
    
    On success, creates session and returns account.
    Also accepts recovery codes as fallback.
    """
    # Get pending 2FA from session
    account_id = session.get(SESSION_KEY_2FA_PENDING)
    if not account_id:
        return TwoFactorResult(success=False, error="No pending 2FA verification")
    
    account = Account.query.get(account_id)
    if not account:
        clear_2fa_session()
        return TwoFactorResult(success=False, error="Account not found")
    
    method = session.get(SESSION_KEY_2FA_METHOD, 'email')
    
    # Check if code looks like a recovery code (format: XXXX-XXXX)
    if len(code) == 9 and '-' in code:
        from .recovery_codes import verify_recovery_code
        if verify_recovery_code(account, code):
            # Recovery code verified - complete login
            clear_2fa_session()
            create_session(account)
            account.last_login_at = datetime.utcnow()
            db.session.commit()
            
            log_login_attempt(
                username=account.username,
                source_ip=source_ip,
                success=True,
                reason="Recovery code used"
            )
            
            logger.info(f"Login complete for {account.username} via recovery code")
            return TwoFactorResult(success=True, account=account)
    
    if method == 'totp':
        # Verify TOTP code
        if not account.totp_secret:
            return TwoFactorResult(success=False, error="TOTP not configured")
        
        try:
            import pyotp
            totp = pyotp.TOTP(account.totp_secret)
            if not totp.verify(code, valid_window=1):
                log_login_attempt(
                    username=account.username,
                    source_ip=source_ip,
                    success=False,
                    reason="Invalid TOTP code"
                )
                return TwoFactorResult(success=False, error="Invalid code")
        except ImportError:
            logger.error("pyotp not installed for TOTP verification")
            return TwoFactorResult(success=False, error="TOTP not available")
    
    else:
        # Verify email/telegram code from session
        expected_code = session.get(SESSION_KEY_2FA_CODE)
        expires_at_str = session.get(SESSION_KEY_2FA_EXPIRES)
        
        if not expected_code or not expires_at_str:
            return TwoFactorResult(success=False, error="No code pending verification")
        
        # Check expiry
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.utcnow() > expires_at:
            clear_2fa_session()
            return TwoFactorResult(success=False, error="Code has expired")
        
        # Verify code
        if code != expected_code:
            log_login_attempt(
                username=account.username,
                source_ip=source_ip,
                success=False,
                reason="Invalid 2FA code"
            )
            return TwoFactorResult(success=False, error="Invalid code")
    
    # 2FA verified - create session
    clear_2fa_session()
    create_session(account)
    
    # Update last login
    account.last_login_at = datetime.utcnow()
    db.session.commit()
    
    log_login_attempt(
        username=account.username,
        source_ip=source_ip,
        success=True
    )
    
    logger.info(f"Login complete for {account.username}")
    
    return TwoFactorResult(success=True, account=account)


def clear_2fa_session():
    """Clear 2FA-related session data."""
    session.pop(SESSION_KEY_2FA_PENDING, None)
    session.pop(SESSION_KEY_2FA_CODE, None)
    session.pop(SESSION_KEY_2FA_EXPIRES, None)
    session.pop(SESSION_KEY_2FA_METHOD, None)


def create_session(account: Account):
    """Create authenticated session for account."""
    session[SESSION_KEY_USER_ID] = account.id
    session[SESSION_KEY_USERNAME] = account.username
    session.permanent = True


def logout():
    """Clear session and log out."""
    username = session.get(SESSION_KEY_USERNAME)
    session.clear()
    if username:
        logger.info(f"Logged out: {username}")


def get_current_account() -> Optional[Account]:
    """Get currently logged-in account from session."""
    account_id = session.get(SESSION_KEY_USER_ID)
    if not account_id:
        return None
    return Account.query.get(account_id)


def is_authenticated() -> bool:
    """Check if user is authenticated."""
    return SESSION_KEY_USER_ID in session


def require_account_auth(f):
    """
    Decorator for routes requiring account authentication.
    
    Redirects to login if not authenticated.
    Sets g.account with current Account.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        account = get_current_account()
        if not account:
            return redirect(url_for('account.login'))
        
        if not account.is_active:
            logout()
            return redirect(url_for('account.login'))
        
        g.account = account
        return f(*args, **kwargs)
    
    return decorated_function


# ============================================================================
# Password Management
# ============================================================================

def change_password(account: Account, current_password: str, new_password: str) -> tuple[bool, str | None]:
    """
    Change account password.
    
    Returns:
        (success, error_message)
    """
    # Verify current password
    if not account.verify_password(current_password):
        return False, "Current password is incorrect"
    
    # Validate new password
    if len(new_password) < 12:
        return False, "Password must be at least 12 characters"
    
    if new_password == current_password:
        return False, "New password must be different"
    
    # Update password
    account.set_password(new_password)
    account.updated_at = datetime.utcnow()
    db.session.commit()
    
    logger.info(f"Password changed for {account.username}")
    
    return True, None


def request_password_reset(email: str) -> tuple[bool, str | None]:
    """
    Initiate password reset flow.
    
    Sends reset code to email if account exists.
    Always returns success to prevent email enumeration.
    """
    account = Account.query.filter_by(email=email).first()
    
    if account and account.is_active:
        # Generate reset code and store in session or temp storage
        # TODO: Implement password reset flow
        logger.info(f"Password reset requested for {email}")
    
    # Always return success to prevent enumeration
    return True, None


# ============================================================================
# Logging
# ============================================================================

def log_login_attempt(
    username: str,
    source_ip: str,
    success: bool,
    reason: str | None = None
):
    """Log login attempt for auditing."""
    account = Account.query.filter_by(username=username).first()
    
    log_entry = ActivityLog(
        account_id=account.id if account else None,
        action='login',
        source_ip=source_ip,
        user_agent=request.headers.get('User-Agent') if request else None,
        status='success' if success else 'denied',
        status_reason=reason
    )
    
    db.session.add(log_entry)
    db.session.commit()


# ============================================================================
# Admin Account Management
# ============================================================================

def create_account_by_admin(
    username: str,
    email: str,
    password: str,
    approved_by: Account
) -> tuple[Account | None, str | None]:
    """
    Create account by admin (bypasses email verification and approval).
    
    Returns:
        (account, error_message)
    """
    # Validate username
    is_valid, error_msg = validate_username(username)
    if not is_valid:
        return None, error_msg
    
    # Check username not taken
    if Account.query.filter_by(username=username).first():
        return None, "Username already registered"
    
    # Check email not taken
    if Account.query.filter_by(email=email).first():
        return None, "Email already registered"
    
    # Validate password
    if len(password) < 12:
        return None, "Password must be at least 12 characters"
    
    # Create account (active, verified)
    account = Account(
        username=username,
        email=email,
        email_verified=1,
        email_2fa_enabled=1,
        is_active=1,  # Already approved
        approved_by_id=approved_by.id,
        approved_at=datetime.utcnow()
    )
    account.set_password(password)
    
    db.session.add(account)
    db.session.commit()
    
    logger.info(f"Account created by admin: {username}")
    
    return account, None


def approve_account(account_id: int, approved_by: Account) -> tuple[bool, str | None]:
    """Approve a pending account."""
    account = Account.query.get(account_id)
    if not account:
        return False, "Account not found"
    
    if account.is_active:
        return False, "Account already active"
    
    account.is_active = 1
    account.approved_by_id = approved_by.id
    account.approved_at = datetime.utcnow()
    
    db.session.commit()
    
    logger.info(f"Account approved: {account.username} by {approved_by.username}")
    
    # Notify user of approval
    from .notification_service import notify_account_approved
    notify_account_approved(account)
    
    return True, None


def disable_account(account_id: int, disabled_by: Account) -> tuple[bool, str | None]:
    """Disable an account."""
    account = Account.query.get(account_id)
    if not account:
        return False, "Account not found"
    
    if account.id == disabled_by.id:
        return False, "Cannot disable your own account"
    
    account.is_active = 0
    db.session.commit()
    
    logger.info(f"Account disabled: {account.username} by {disabled_by.username}")
    
    return True, None

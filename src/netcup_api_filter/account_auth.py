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
    generate_user_alias,
    validate_password,
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
SESSION_KEY_2FA_EMAIL_REF = '2fa_email_ref'
# Full email reference (e.g. NAF-2FA-...-TOKEN). Stored so resends keep the same
# reference for a single 2FA challenge.
SESSION_KEY_2FA_EMAIL_REF_FULL = '2fa_email_ref_full'

# 2FA configuration
TFA_CODE_LENGTH = 6
TFA_CODE_EXPIRY_MINUTES = 5
TFA_MAX_ATTEMPTS = 5
TFA_LOCKOUT_MINUTES = 30  # Lock account after max failed attempts

# Recovery code rate limiting
RECOVERY_CODE_MAX_ATTEMPTS = 3  # Max failures before lockout
RECOVERY_CODE_LOCKOUT_MINUTES = 30  # Lockout duration

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


def _generate_unique_user_alias() -> str:
    """
    Generate a unique user_alias for a new account.
    
    The user_alias is used in tokens instead of username for security.
    Retries up to 10 times to find a unique value.
    
    Returns:
        A unique 16-char alphanumeric string
        
    Raises:
        RuntimeError: If unable to generate unique alias after 10 attempts
    """
    for _ in range(10):
        alias = generate_user_alias()
        if not Account.query.filter_by(user_alias=alias).first():
            return alias
    raise RuntimeError("Failed to generate unique user_alias after 10 attempts")


def generate_secure_password(length: int = 16) -> str:
    """Generate a secure random password.
    
    Uses safe printable ASCII characters that don't cause shell escaping issues.
    Excludes: ! (shell history), ` (command substitution), ' " (quoting)
    """
    # Safe special chars: -=_+;:,.|/?@#$%^&*
    alphabet = string.ascii_letters + string.digits + "-=_+;:,.|/?@#$%^&*"
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
    
    # Validate password (format and entropy)
    is_valid, error_msg = validate_password(password)
    if not is_valid:
        return RegistrationResult(
            success=False,
            error=error_msg,
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
    
    Marks registration as verified but does NOT create account yet.
    Account creation happens in finalize_registration_with_realms()
    after user optionally adds realm requests.
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
    
    # Email verified - extend expiry for realm request step
    reg_request.verification_expires_at = datetime.utcnow() + timedelta(hours=24)
    db.session.commit()
    
    logger.info(f"Email verified for registration: {reg_request.username}")
    
    return RegistrationResult(success=True, request_id=request_id)


def finalize_registration_with_realms(request_id: int) -> RegistrationResult:
    """
    Create account and pending realm requests from registration.
    
    Called after email verification and optional realm request step.
    Creates account (pending approval) and any realm requests as pending.
    """
    from .models import AccountRealm
    
    reg_request = RegistrationRequest.query.get(request_id)
    if not reg_request:
        return RegistrationResult(success=False, error="Registration not found")
    
    # Generate unique user_alias for token attribution
    user_alias = _generate_unique_user_alias()
    
    # Create account (pending approval)
    account = Account(
        username=reg_request.username,
        user_alias=user_alias,
        email=reg_request.email,
        password_hash=reg_request.password_hash,
        email_verified=1,
        email_2fa_enabled=1,  # Email 2FA mandatory
        is_active=0,  # Pending admin approval
    )
    
    db.session.add(account)
    db.session.flush()  # Get account.id before creating realms
    
    # Create pending realm requests
    realm_requests = reg_request.get_realm_requests()
    for realm_data in realm_requests:
        realm = AccountRealm(
            account_id=account.id,
            domain=realm_data.get('domain', ''),
            realm_type=realm_data.get('realm_type', 'host'),
            realm_value=realm_data.get('realm_value', ''),
            status='pending',
            requested_at=datetime.utcnow()
        )
        realm.set_allowed_record_types(realm_data.get('record_types', ['A', 'AAAA']))
        realm.set_allowed_operations(realm_data.get('operations', ['read', 'update']))
        db.session.add(realm)
    
    # Delete registration request
    db.session.delete(reg_request)
    db.session.commit()
    
    logger.info(f"Account created (pending approval): {account.username} with {len(realm_requests)} realm requests")
    
    # Notify admin of pending approval (include realm count)
    from .notification_service import notify_admin_pending_account
    notify_admin_pending_account(account.username, account.email, len(realm_requests))
    
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
        # Send 2FA code via email
        from .email_reference import email_ref_token, generate_email_ref
        from .notification_service import send_2fa_email

        # Keep the email reference stable across resends for this 2FA session.
        full_ref = session.get(SESSION_KEY_2FA_EMAIL_REF_FULL)
        if not full_ref:
            full_ref = generate_email_ref('2fa', account.username)
            session[SESSION_KEY_2FA_EMAIL_REF_FULL] = full_ref

        token = email_ref_token(full_ref) or full_ref
        session[SESSION_KEY_2FA_EMAIL_REF] = token

        if send_2fa_email(account.email, account.username, code, email_ref=full_ref):
            logger.info(f"2FA code sent via email to {account.username}")
            return True, None
        else:
            logger.error(f"Failed to send 2FA email to {account.username}")
            return False, "Failed to send verification email"
    
    elif method == 'totp':
        # TOTP doesn't need code sent - user generates from authenticator
        # Clear the code we generated - TOTP verification handles its own
        session.pop(SESSION_KEY_2FA_CODE, None)
        session.pop(SESSION_KEY_2FA_EMAIL_REF, None)
        session.pop(SESSION_KEY_2FA_EMAIL_REF_FULL, None)
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
    Implements lockout after max failures.
    """
    # Get pending 2FA from session
    account_id = session.get(SESSION_KEY_2FA_PENDING)
    if not account_id:
        return TwoFactorResult(success=False, error="No pending 2FA verification")
    
    account = Account.query.get(account_id)
    if not account:
        clear_2fa_session()
        return TwoFactorResult(success=False, error="Account not found")
    
    # Check if account is locked due to 2FA failures
    if is_2fa_locked(account):
        lockout_mins = TFA_LOCKOUT_MINUTES
        return TwoFactorResult(
            success=False, 
            error=f"Too many failed 2FA attempts. Account locked for {lockout_mins} minutes."
        )
    
    method = session.get(SESSION_KEY_2FA_METHOD, 'email')
    
    # Check if code looks like a recovery code (format: XXXX-XXXX)
    if len(code) == 9 and '-' in code:
        # Check recovery code rate limiting
        if is_recovery_code_locked(account):
            lockout_mins = RECOVERY_CODE_LOCKOUT_MINUTES
            log_login_attempt(
                username=account.username,
                source_ip=source_ip,
                success=False,
                reason=f"Recovery code locked (rate limit)"
            )
            return TwoFactorResult(
                success=False, 
                error=f"Too many failed recovery code attempts. Locked for {lockout_mins} minutes."
            )
        
        from .recovery_codes import verify_recovery_code
        if verify_recovery_code(account, code):
            # Recovery code verified - complete login
            clear_2fa_session()
            reset_2fa_failures(account)  # Clear lockout counters
            reset_recovery_code_failures(account)  # Clear recovery code lockout
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
        else:
            # Invalid recovery code - increment failure counter
            increment_recovery_code_failures(account)
            log_login_attempt(
                username=account.username,
                source_ip=source_ip,
                success=False,
                reason="Invalid recovery code"
            )
            return TwoFactorResult(success=False, error="Invalid recovery code")
    
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
            increment_2fa_failures(account)
            attempts_left = TFA_MAX_ATTEMPTS - get_2fa_failure_count(account)
            log_login_attempt(
                username=account.username,
                source_ip=source_ip,
                success=False,
                reason="Invalid 2FA code"
            )
            if attempts_left > 0:
                return TwoFactorResult(
                    success=False, 
                    error=f"Invalid code. {attempts_left} attempts remaining."
                )
            else:
                return TwoFactorResult(
                    success=False, 
                    error=f"Too many failed attempts. Account locked for {TFA_LOCKOUT_MINUTES} minutes."
                )
    
    # 2FA verified - create session
    clear_2fa_session()
    reset_2fa_failures(account)  # Clear lockout counters
    reset_recovery_code_failures(account)  # Clear recovery code lockout
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
    session.pop(SESSION_KEY_2FA_EMAIL_REF, None)
    session.pop(SESSION_KEY_2FA_EMAIL_REF_FULL, None)


def create_session(account: Account):
    """Create authenticated session for account."""
    # Regenerate session ID to prevent session fixation attacks
    old_session_data = dict(session)
    session.clear()
    session.update(old_session_data)
    session.modified = True
    
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

def change_password(
    account: Account,
    current_password: str,
    new_password: str,
    source_ip: str | None = None
) -> tuple[bool, str | None]:
    """
    Change account password.
    
    Args:
        account: Account to change password for
        current_password: Current password for verification
        new_password: New password to set
        source_ip: IP address where change was made (for notification)
    
    Returns:
        (success, error_message)
    """
    # Verify current password
    if not account.verify_password(current_password):
        return False, "Current password is incorrect"
    
    # Validate new password (format and entropy)
    is_valid, error_msg = validate_password(new_password)
    if not is_valid:
        return False, error_msg
    
    if new_password == current_password:
        return False, "New password must be different"
    
    # Update password
    account.set_password(new_password)
    account.updated_at = datetime.utcnow()
    db.session.commit()
    
    logger.info(f"Password changed for {account.username}")
    
    # Send notification email
    from .notification_service import notify_password_changed
    notify_password_changed(account, source_ip)
    
    return True, None


def request_password_reset(email: str) -> tuple[bool, str | None]:
    """
    Initiate password reset flow.
    
    Sends reset code to email if account exists.
    Always returns success to prevent email enumeration.
    """
    account = Account.query.filter_by(email=email).first()
    
    if account and account.is_active:
        # Generate reset code
        code = generate_code(6)
        expires_at = datetime.utcnow() + timedelta(minutes=30)
        
        # Store reset info on account (temporary)
        account.password_reset_code = code
        account.password_reset_expires = expires_at
        db.session.commit()
        
        # Send reset email
        from .notification_service import send_password_reset_email
        send_password_reset_email(account.email, account.username, code, expires_minutes=30)
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
    password: str | None,
    approved_by: Account,
    send_invite: bool = True
) -> tuple[Account | None, str | None]:
    """
    Create account by admin.
    
    Two modes of operation:
    1. send_invite=True (default): Account is created in "invite pending" state.
       An invite email is sent to the user to set their own password.
       The provided password is used as a temporary fallback if email fails.
    
    2. send_invite=False: Account is immediately active with the given password.
       Useful for service accounts or when the admin will communicate the
       password through other secure means.
    
    Args:
        username: Account username
        email: Account email
        password: Temporary password (generated if None)
        approved_by: Admin performing the creation
        send_invite: If True, send invite email for user to set password
    
    Returns:
        (account, error_message)
    """
    from .password_reset import send_account_invite_email
    from .utils import generate_token
    
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
    
    # Generate password if not provided
    if not password:
        password = generate_token(24)
    
    # Validate password (even temp passwords should be strong)
    if len(password) < 12:
        return None, "Password must be at least 12 characters"
    
    # Generate unique user_alias for token attribution
    user_alias = _generate_unique_user_alias()
    
    # Create account
    # When sending invite: account is active but password must be changed
    # Without invite: account is immediately usable
    account = Account(
        username=username,
        user_alias=user_alias,
        email=email,
        email_verified=1,  # Admin-created accounts skip email verification
        email_2fa_enabled=1,
        is_active=1,  # Account is approved
        must_change_password=send_invite,  # Must set own password if invite mode
        approved_by_id=approved_by.id,
        approved_at=datetime.utcnow()
    )
    account.set_password(password)
    
    db.session.add(account)
    db.session.commit()
    
    logger.info(f"Account created by admin: {username} (invite_mode={send_invite})")
    
    # Send invite email if requested
    if send_invite:
        email_sent = send_account_invite_email(
            account,
            admin_username=approved_by.username
        )
        if not email_sent:
            logger.warning(
                f"Failed to send invite email to {email}. "
                f"Fallback: admin should share temporary password manually."
            )
            # Return success but with warning message
            return account, f"WARNING: Invite email failed. Temporary password: {password}"
    
    return account, None


def approve_account(account_id: int, approved_by: Account, approve_realms: bool = True) -> tuple[bool, str | None]:
    """
    Approve a pending account and optionally all pending realm requests.
    
    Args:
        account_id: ID of the account to approve
        approved_by: Admin account performing the approval
        approve_realms: If True, also approve all pending realm requests
        
    Returns:
        (success, error_message)
    """
    from .models import AccountRealm
    
    account = Account.query.get(account_id)
    if not account:
        return False, "Account not found"
    
    if account.is_active:
        return False, "Account already active"
    
    # Approve account
    account.is_active = 1
    account.approved_by_id = approved_by.id
    account.approved_at = datetime.utcnow()
    
    # Approve all pending realm requests if requested
    approved_realm_count = 0
    if approve_realms:
        pending_realms = AccountRealm.query.filter_by(
            account_id=account_id,
            status='pending'
        ).all()
        
        for realm in pending_realms:
            realm.status = 'approved'
            realm.approved_by_id = approved_by.id
            realm.approved_at = datetime.utcnow()
            approved_realm_count += 1
    
    db.session.commit()
    
    logger.info(f"Account approved: {account.username} by {approved_by.username} with {approved_realm_count} realms")
    
    # Notify user of approval (include realm count)
    from .notification_service import notify_account_approved
    notify_account_approved(account, approved_realm_count)
    
    return True, None


def reject_account(account_id: int, rejected_by: Account, reason: str = None) -> tuple[bool, str | None]:
    """
    Reject and delete a pending account and all its realm requests.
    
    Args:
        account_id: ID of the account to reject
        rejected_by: Admin account performing the rejection
        reason: Optional reason for rejection
        
    Returns:
        (success, error_message)
    """
    from .models import AccountRealm
    
    account = Account.query.get(account_id)
    if not account:
        return False, "Account not found"
    
    if account.is_active:
        return False, "Cannot reject an active account"
    
    username = account.username
    email = account.email
    
    # Delete all realm requests for this account
    AccountRealm.query.filter_by(account_id=account_id).delete()
    
    # Delete the account
    db.session.delete(account)
    db.session.commit()
    
    logger.info(f"Account rejected and deleted: {username} by {rejected_by.username}, reason: {reason or 'No reason given'}")
    
    # Notify user of rejection
    from .notification_service import notify_account_rejected
    notify_account_rejected(email, username, reason)
    
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


# ============================================================================
# 2FA Failure Tracking (Security)
# ============================================================================

def get_2fa_failure_count(account: Account) -> int:
    """Get number of recent 2FA failures for account."""
    from .models import Settings
    key = f"2fa_failures:{account.id}"
    data = Settings.get(key)
    if not data:
        return 0
    
    # Check if lockout expired
    last_failure = datetime.fromisoformat(data.get('last_failure', datetime.utcnow().isoformat()))
    if datetime.utcnow() - last_failure > timedelta(minutes=TFA_LOCKOUT_MINUTES):
        # Lockout expired, reset
        Settings.delete(key)
        return 0
    
    return data.get('count', 0)


def increment_2fa_failures(account: Account):
    """Increment 2FA failure counter for account."""
    from .models import Settings
    key = f"2fa_failures:{account.id}"
    data = Settings.get(key) or {'count': 0}
    data['count'] = data.get('count', 0) + 1
    data['last_failure'] = datetime.utcnow().isoformat()
    Settings.set(key, data)
    logger.warning(f"2FA failure #{data['count']} for account {account.username}")


def reset_2fa_failures(account: Account):
    """Reset 2FA failure counter after successful login."""
    from .models import Settings
    key = f"2fa_failures:{account.id}"
    Settings.delete(key)


def is_2fa_locked(account: Account) -> bool:
    """Check if account is locked due to too many 2FA failures."""
    count = get_2fa_failure_count(account)
    return count >= TFA_MAX_ATTEMPTS


# ============================================================================
# Recovery Code Rate Limiting (Security)
# ============================================================================

def get_recovery_code_failure_count(account: Account) -> int:
    """Get number of recent recovery code failures for account."""
    from .models import Settings
    key = f"recovery_failures:{account.id}"
    data = Settings.get(key)
    if not data:
        return 0
    
    # Check if lockout expired
    last_failure = datetime.fromisoformat(data.get('last_failure', datetime.utcnow().isoformat()))
    if datetime.utcnow() - last_failure > timedelta(minutes=RECOVERY_CODE_LOCKOUT_MINUTES):
        # Lockout expired, reset
        Settings.delete(key)
        return 0
    
    return data.get('count', 0)


def increment_recovery_code_failures(account: Account):
    """Increment recovery code failure counter for account."""
    from .models import Settings
    key = f"recovery_failures:{account.id}"
    data = Settings.get(key) or {'count': 0}
    data['count'] = data.get('count', 0) + 1
    data['last_failure'] = datetime.utcnow().isoformat()
    Settings.set(key, data)
    logger.warning(f"Recovery code failure #{data['count']} for account {account.username}")


def reset_recovery_code_failures(account: Account):
    """Reset recovery code failure counter after successful login."""
    from .models import Settings
    key = f"recovery_failures:{account.id}"
    Settings.delete(key)


def is_recovery_code_locked(account: Account) -> bool:
    """Check if account is locked due to too many recovery code failures."""
    count = get_recovery_code_failure_count(account)
    return count >= RECOVERY_CODE_MAX_ATTEMPTS

"""
Email Reference ID Generator.

Generates unique, traceable reference IDs for emails sent by the system.
These IDs appear in email footers and logs, enabling:
- Correlation between emails and log entries
- Debugging email delivery issues
- User support ticket tracking

Format: NAF-{type}-{timestamp}-{random}
Example: NAF-RST-20241207123456-A1B2C3

Type codes:
- RST: Password reset
- INV: Account invite
- VER: Email verification
- 2FA: Two-factor authentication code
- NTF: Notification (account approved, rejected, etc.)
- ALR: Security alert
"""
import secrets
import string
from datetime import datetime

from .config_defaults import get_default


# Type codes for different email categories
EMAIL_TYPE_CODES = {
    'reset': 'RST',
    'invite': 'INV',
    'verify': 'VER',
    '2fa': '2FA',
    'notification': 'NTF',
    'alert': 'ALR',
    'test': 'TST',
}


def generate_email_ref(email_type: str, context: str = '') -> str:
    """
    Generate a unique email reference ID.
    
    Args:
        email_type: Type of email (reset, invite, verify, 2fa, notification, alert)
        context: Optional context (e.g., username) - NOT included in ref, just for logging
    
    Returns:
        Reference ID like 'NAF-RST-20241207123456-A1B2C3'
    """
    import os

    type_code = EMAIL_TYPE_CODES.get(email_type, 'GEN')
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')

    # Random part format is config-driven.
    # For production-parity 2FA + IMAP polling, a longer token reduces risk of
    # picking up stale emails.
    group_size_raw = os.environ.get(
        'NAF_EMAIL_REF_RANDOM_GROUP_SIZE',
        get_default('NAF_EMAIL_REF_RANDOM_GROUP_SIZE', '6'),
    )
    groups_raw = os.environ.get(
        'NAF_EMAIL_REF_RANDOM_GROUPS',
        get_default('NAF_EMAIL_REF_RANDOM_GROUPS', '1'),
    )
    try:
        group_size = max(1, int(group_size_raw))
    except Exception:
        group_size = 6
    try:
        groups = max(1, int(groups_raw))
    except Exception:
        groups = 1

    alphabet = string.ascii_uppercase + string.digits
    parts = [
        ''.join(secrets.choice(alphabet) for _ in range(group_size))
        for _ in range(groups)
    ]
    random_part = '-'.join(parts)
    
    return f"NAF-{type_code}-{timestamp}-{random_part}"


def parse_email_ref(ref: str) -> dict | None:
    """
    Parse an email reference ID into its components.
    
    Args:
        ref: Reference ID string
    
    Returns:
        Dict with 'type_code', 'timestamp', 'random' or None if invalid
    """
    if not ref or not ref.startswith('NAF-'):
        return None
    
    parts = ref.split('-')
    # Historically this was exactly 4 parts: NAF-{type}-{timestamp}-{random}.
    # We now allow dashed random tokens (e.g., FIHY56-AVJE34) so there can be
    # more segments.
    if len(parts) < 4:
        return None

    _, type_code, timestamp, *random_parts = parts
    random_part = '-'.join(random_parts)
    
    try:
        # Validate timestamp format
        datetime.strptime(timestamp, '%Y%m%d%H%M%S')
    except ValueError:
        return None
    
    return {
        'type_code': type_code,
        'timestamp': timestamp,
        'random': random_part,
        'full_ref': ref
    }


def email_ref_token(ref: str) -> str | None:
    """Return the user-facing ref token portion (random part) of an email ref."""
    parsed = parse_email_ref(ref)
    if not parsed:
        return None
    token = parsed.get('random')
    return token if isinstance(token, str) and token else None

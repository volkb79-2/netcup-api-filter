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
    type_code = EMAIL_TYPE_CODES.get(email_type, 'GEN')
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    
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
    if len(parts) != 4:
        return None
    
    _, type_code, timestamp, random_part = parts
    
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

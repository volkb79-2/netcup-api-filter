"""
Recovery codes for 2FA backup.

Recovery codes provide a fallback authentication method when primary 2FA
methods (email, TOTP, Telegram) are unavailable. Each code can only be
used once.

Usage:
1. Account enables TOTP → system generates recovery codes
2. User downloads/prints recovery codes (one-time display)
3. If user loses 2FA device, they can use a recovery code to login
4. Used codes are invalidated immediately
"""
import hashlib
import json
import logging
import os
import secrets
from datetime import datetime
from typing import Optional

from .models import Account, db

logger = logging.getLogger(__name__)

# Configuration
def _recovery_code_count() -> int:
    """Read RECOVERY_CODE_COUNT, tolerating bad values and bounding the range.

    Parsed defensively so a malformed env value (empty string, non-numeric)
    can't raise at import time and 500 every 2FA/recovery route. Bounded to a
    sane range to preserve the brute-force resistance of a small code set.
    """
    raw = os.environ.get("RECOVERY_CODE_COUNT", "3")
    try:
        count = int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning(f"Invalid RECOVERY_CODE_COUNT={raw!r}; defaulting to 3")
        return 3
    return max(1, min(count, 20))


RECOVERY_CODE_COUNT = _recovery_code_count()
RECOVERY_CODE_LENGTH = 8  # Characters per code (e.g., "ABCD-1234")
RECOVERY_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # Excludes confusables: I,O,0,1


def generate_recovery_codes() -> list[str]:
    """
    Generate a set of recovery codes.
    
    Returns:
        List of plaintext recovery codes (e.g., ["ABCD-1234", "EFGH-5678", ...])
    """
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        # Generate random characters
        chars = ''.join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
        # Format as XXXX-XXXX
        formatted = f"{chars[:4]}-{chars[4:]}"
        codes.append(formatted)
    return codes


def hash_recovery_code(code: str) -> str:
    """
    Hash a recovery code for storage.
    
    Args:
        code: Plaintext recovery code (e.g., "ABCD-1234")
        
    Returns:
        SHA-256 hash of normalized code
    """
    # Normalize: uppercase, remove dashes
    normalized = code.upper().replace("-", "").strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


def store_recovery_codes(account: Account, codes: list[str]) -> bool:
    """
    Store hashed recovery codes for an account.
    
    Args:
        account: Account to store codes for
        codes: List of plaintext recovery codes
        
    Returns:
        True if stored successfully
    """
    try:
        # Hash all codes
        hashed_codes = [hash_recovery_code(code) for code in codes]
        
        # Store as JSON
        account.recovery_codes = json.dumps(hashed_codes)
        account.recovery_codes_generated_at = datetime.utcnow()
        db.session.commit()
        
        logger.info(f"Generated {len(codes)} recovery codes for account {account.username}")
        return True
    except Exception as e:
        logger.error(f"Failed to store recovery codes for {account.username}: {e}")
        db.session.rollback()
        return False


def verify_recovery_code(account: Account, code: str) -> bool:
    """
    Verify and consume a recovery code.
    
    Args:
        account: Account to verify code for
        code: Plaintext recovery code to verify
        
    Returns:
        True if code valid and consumed, False otherwise
    """
    if not account.recovery_codes:
        logger.warning(f"No recovery codes for account {account.username}")
        return False
    
    try:
        stored_hashes = json.loads(account.recovery_codes)
    except json.JSONDecodeError:
        logger.error(f"Invalid recovery codes JSON for {account.username}")
        return False
    
    # Hash the provided code
    code_hash = hash_recovery_code(code)
    
    # Check if code matches any stored hash
    if code_hash in stored_hashes:
        # Remove used code (one-time use)
        stored_hashes.remove(code_hash)
        account.recovery_codes = json.dumps(stored_hashes) if stored_hashes else None
        
        # If no codes left, clear the generation timestamp
        if not stored_hashes:
            account.recovery_codes_generated_at = None
            logger.info(f"All recovery codes used for account {account.username}")
        
        db.session.commit()
        logger.info(f"Recovery code used for account {account.username}, {len(stored_hashes)} remaining")
        return True
    
    logger.warning(f"Invalid recovery code attempt for account {account.username}")
    return False


def get_remaining_code_count(account: Account) -> int:
    """
    Get count of remaining recovery codes.
    
    Args:
        account: Account to check
        
    Returns:
        Number of unused recovery codes
    """
    if not account.recovery_codes:
        return 0
    
    try:
        stored_hashes = json.loads(account.recovery_codes)
        return len(stored_hashes)
    except json.JSONDecodeError:
        return 0


def regenerate_recovery_codes(account: Account) -> Optional[list[str]]:
    """
    Regenerate recovery codes (invalidates old codes).
    
    Args:
        account: Account to regenerate codes for
        
    Returns:
        List of new plaintext codes, or None on failure
    """
    codes = generate_recovery_codes()
    if store_recovery_codes(account, codes):
        return codes
    return None

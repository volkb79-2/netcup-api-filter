"""
Utility functions for netcup-api-filter
Token generation, password hashing, validation helpers
"""
import secrets
import bcrypt
import os
import logging
import ipaddress
import re
import json
from datetime import datetime
from functools import lru_cache
from typing import List, Dict
import string

logger = logging.getLogger(__name__)


def generate_token(min_length: int = 63, max_length: int = 65) -> str:
    """
    Generate a cryptographically secure alphanumeric token.

    Args:
        min_length: Minimum number of characters the token must contain (inclusive).
        max_length: Maximum number of characters the token may contain (inclusive).

    Returns:
        Random token composed of [a-zA-Z0-9] with a length between min_length and max_length.
    """
    if min_length <= 0 or max_length <= 0:
        raise ValueError("Token length must be positive")
    if min_length > max_length:
        raise ValueError("min_length cannot exceed max_length")

    alphabet = string.ascii_letters + string.digits
    span = max_length - min_length + 1
    length = min_length + secrets.randbelow(span)
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_client_credentials(client_id_length: int = 20, secret_key_length: int = 40) -> tuple[str, str]:
    """
    Generate two-factor client authentication credentials.
    
    Creates a client_id (cleartext, manageable in UI) and secret_key (to be hashed).
    The complete authentication token format is: "client_id:secret_key"
    
    Args:
        client_id_length: Length of the client_id (default 20 chars)
        secret_key_length: Length of the secret_key (default 40 chars)
        
    Returns:
        Tuple of (client_id, secret_key, full_token)
        - client_id: Cleartext identifier for admin UI management
        - secret_key: Secret to be hashed and stored (never shown again)
        - full_token: Complete "client_id:secret_key" for client usage
        
    Example:
        >>> client_id, secret_key, full_token = generate_client_credentials()
        >>> # client_id: "AbC123xYz456PqRs7890"
        >>> # secret_key: "sK7mN2pQ9rT4vW1xZ5aB8cD3eF6gH0jK2lM4nP7"
        >>> # full_token: "AbC123xYz456PqRs7890:sK7mN2pQ9rT4vW1xZ5aB8cD3eF6gH0jK2lM4nP7"
    """
    client_id = generate_token(min_length=client_id_length, max_length=client_id_length)
    secret_key = generate_token(min_length=secret_key_length, max_length=secret_key_length)
    full_token = f"{client_id}:{secret_key}"
    
    return client_id, secret_key, full_token


def hash_password(password: str, cost: int = 12) -> str:
    """
    Hash a password using bcrypt
    
    Args:
        password: Plain text password
        cost: Bcrypt cost factor (default 12)
        
    Returns:
        Bcrypt hash as string
    """
    salt = bcrypt.gensalt(rounds=cost)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify a password against a bcrypt hash
    
    Args:
        password: Plain text password to verify
        hashed: Bcrypt hash to check against
        
    Returns:
        True if password matches, False otherwise
    """
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


def test_filesystem_access() -> List[Dict[str, str]]:
    """
    Test filesystem access for various paths
    
    Returns:
        List of dicts describing each test result
    """
    results = []

    def check_path(path: str, label: str):
        record = {
            'name': label,
            'path': path,
            'success': False,
            'message': '',
            'error': ''
        }
        test_file = os.path.join(path, '.write_test_netcup_filter')
        try:
            with open(test_file, 'w', encoding='utf-8') as handle:
                handle.write('test')
            os.remove(test_file)
            record['success'] = True
            record['message'] = f"{path} is writable"
        except Exception as exc:  # pragma: no cover - environment dependent
            record['error'] = f"{path} not writable: {exc}"
        results.append(record)

    check_path(os.getcwd(), 'Working Directory')
    check_path('/tmp', '/tmp Directory')

    home_dir = os.path.expanduser('~')
    if home_dir != '~':
        check_path(home_dir, 'Home Directory')

    return results


def validate_ip_range(ip_range: str) -> bool:
    """
    Validate IP address or range format
    
    Supports:
    - Single IP: 192.168.1.1
    - CIDR notation: 192.168.1.0/24
    - IP range: 192.168.1.1-192.168.1.254
    - Wildcard: 192.168.1.* or *
    
    Args:
        ip_range: IP address or range to validate
        
    Returns:
        True if valid format, False otherwise
    """
    if not ip_range:
        return False
    
    # Allow wildcard
    if ip_range == '*':
        return True
    
    # Check for CIDR notation
    if '/' in ip_range:
        try:
            ipaddress.ip_network(ip_range, strict=False)
            return True
        except ValueError:
            return False
    
    # Check for range notation (e.g., 192.168.1.1-192.168.1.254)
    if '-' in ip_range:
        parts = ip_range.split('-')
        if len(parts) == 2:
            try:
                ipaddress.ip_address(parts[0].strip())
                ipaddress.ip_address(parts[1].strip())
                return True
            except ValueError:
                return False
    
    # Check for wildcard in IP (e.g., 192.168.1.*)
    if '*' in ip_range:
        # Simple validation - should be IP-like with * in place of octets
        pattern = r'^(\d{1,3}|\*)\.(\d{1,3}|\*)\.(\d{1,3}|\*)\.(\d{1,3}|\*)$'
        if re.match(pattern, ip_range):
            # Validate numeric octets are in range
            parts = ip_range.split('.')
            for part in parts:
                if part != '*':
                    try:
                        num = int(part)
                        if num < 0 or num > 255:
                            return False
                    except ValueError:
                        return False
            return True
        
        # IPv6 wildcard pattern
        if ':' in ip_range:
            return True  # Basic support for IPv6 wildcards
    
    # Check for single IP address
    try:
        ipaddress.ip_address(ip_range)
        return True
    except ValueError:
        return False


def validate_domain(domain: str) -> bool:
    """
    Validate domain name format
    
    Args:
        domain: Domain name to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not domain or len(domain) > 253:
        return False
    
    # RFC 1035 domain name pattern
    pattern = r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$'
    return bool(re.match(pattern, domain))


def validate_email(email: str) -> bool:
    """
    Basic email validation
    
    Args:
        email: Email address to validate
        
    Returns:
        True if valid format, False otherwise
    """
    if not email:
        return False
    
    # Basic email pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent directory traversal
    
    Args:
        filename: Filename to sanitize
        
    Returns:
        Sanitized filename
    """
    # Remove path components
    filename = os.path.basename(filename)
    
    # Remove or replace dangerous characters
    filename = re.sub(r'[^\w\-\.]', '_', filename)
    
    # Prevent hidden files
    if filename.startswith('.'):
        filename = '_' + filename
    
    return filename


def get_python_info() -> dict:
    """
    Get Python environment information
    
    Returns:
        Dictionary with Python version and environment info
    """
    import sys
    import platform
    
    return {
        'python_version': sys.version,
        'python_implementation': platform.python_implementation(),
        'platform': platform.platform(),
        'architecture': platform.architecture(),
        'executable': sys.executable,
        'prefix': sys.prefix,
    }


def get_current_directory_info() -> dict:
    """
    Get current directory information
    
    Returns:
        Dictionary with directory paths
    """
    return {
        'cwd': os.getcwd(),
        'script_dir': os.path.dirname(os.path.abspath(__file__)),
        'home': os.path.expanduser('~'),
    }


def test_filesystem_access() -> dict:
    """
    Test filesystem write/read access in various locations
    
    Returns:
        Dictionary with test results for different locations and file types
    """
    import tempfile
    from datetime import datetime
    
    results = {}
    test_content = f"Test write at {datetime.utcnow().isoformat()}"
    
    # Test locations to try
    test_locations = [
        ('cwd', os.getcwd()),
        ('tmp_subdir', os.path.join(os.getcwd(), 'tmp')),
        ('system_tmp', tempfile.gettempdir()),
        ('parent', os.path.dirname(os.getcwd())),
    ]
    
    for loc_name, loc_path in test_locations:
        result = {
            'path': loc_path,
            'exists': os.path.exists(loc_path),
            'writable': False,
            'readable': False,
            'file_test': None,
            'sqlite_test': None,
            'error': None
        }
        
        try:
            # Check if directory is accessible
            if result['exists']:
                result['writable'] = os.access(loc_path, os.W_OK)
                result['readable'] = os.access(loc_path, os.R_OK)
            
            # Test regular file write/read
            if result['exists'] and result['writable']:
                test_file = os.path.join(loc_path, f'write_test_{loc_name}.txt')
                try:
                    with open(test_file, 'w') as f:
                        f.write(test_content)
                    
                    with open(test_file, 'r') as f:
                        read_content = f.read()
                    
                    if read_content == test_content:
                        result['file_test'] = 'SUCCESS'
                        # Clean up
                        os.remove(test_file)
                    else:
                        result['file_test'] = 'CONTENT_MISMATCH'
                except Exception as e:
                    result['file_test'] = f'FAILED: {str(e)}'
                
                # Test SQLite database write
                db_test_file = os.path.join(loc_path, f'test_db_{loc_name}.db')
                try:
                    import sqlite3
                    conn = sqlite3.connect(db_test_file)
                    cursor = conn.cursor()
                    cursor.execute('CREATE TABLE test (id INTEGER PRIMARY KEY, data TEXT)')
                    cursor.execute('INSERT INTO test (data) VALUES (?)', (test_content,))
                    conn.commit()
                    cursor.execute('SELECT data FROM test WHERE id = 1')
                    row = cursor.fetchone()
                    conn.close()
                    
                    if row and row[0] == test_content:
                        result['sqlite_test'] = 'SUCCESS'
                        # Clean up
                        os.remove(db_test_file)
                    else:
                        result['sqlite_test'] = 'DATA_MISMATCH'
                except Exception as e:
                    result['sqlite_test'] = f'FAILED: {str(e)}'
        
        except Exception as e:
            result['error'] = str(e)
        
        results[loc_name] = result
    
    # Test if we can list parent directories
    try:
        parent = os.path.dirname(os.getcwd())
        results['parent_listing'] = {
            'path': parent,
            'contents': os.listdir(parent) if os.path.exists(parent) else None,
            'accessible': os.access(parent, os.R_OK) if os.path.exists(parent) else False
        }
    except Exception as e:
        results['parent_listing'] = {'error': str(e)}
    
    return results


@lru_cache(maxsize=1)
def get_build_info() -> Dict[str, str]:
    """Return build metadata loaded from build_info.json if present."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    fallback = {
        'environment': 'development',
        'built_at': datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
        'git_commit': 'local',
        'git_branch': 'local',
        'source': 'runtime-generated'
    }

    candidates = [
        os.environ.get('NETCUP_BUILD_INFO_PATH'),
        os.path.join(base_dir, 'build_info.json')
    ]

    for candidate in candidates:
        if not candidate:
            continue
        if os.path.exists(candidate):
            try:
                with open(candidate, 'r', encoding='utf-8') as handle:
                    data = json.load(handle)
                    if isinstance(data, dict):
                        return data
            except Exception as exc:
                logger.warning('Failed to read build info from %s: %s', candidate, exc)

    return fallback

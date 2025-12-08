"""
Live DNS Verification Tests

These tests verify that DNS record changes made through the application
are actually propagated to DNS servers. This provides end-to-end verification
that the Netcup API integration is working correctly.

Prerequisites:
- Netcup API credentials configured
- A domain under your control for testing
- DNS_TEST_SUBDOMAIN_PREFIX configured in .env

Usage:
    pytest ui_tests/tests/test_live_dns_verification.py -v --mode live

Note: These tests only run in live mode (--mode live) as they require
real DNS infrastructure and may take several minutes for propagation.
"""
import os

try:
    import dns.resolver
    HAS_DNSPYTHON = True
except ImportError:
    HAS_DNSPYTHON = False
    dns = None  # type: ignore
import time
import logging
import random
import string
from datetime import datetime
from typing import Optional, List

import pytest

# Skip entire module if dnspython not available or not in live mode
pytestmark = [
    pytest.mark.skipif(not HAS_DNSPYTHON, reason="dnspython not installed"),
]

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

def get_dns_config() -> dict:
    """Get DNS test configuration from environment variables."""
    return {
        'test_subdomain_prefix': os.environ.get('DNS_TEST_SUBDOMAIN_PREFIX', '_naftest'),
        'propagation_timeout': int(os.environ.get('DNS_PROPAGATION_TIMEOUT', '300')),
        'check_servers': os.environ.get('DNS_CHECK_SERVERS', '8.8.8.8,1.1.1.1').split(','),
    }


def is_dns_test_configured() -> bool:
    """Check if DNS testing is properly configured."""
    # Need at least a test client with valid realm
    return os.environ.get('DEPLOYMENT_MODE') == 'live'


# =============================================================================
# DNS Query Helpers
# =============================================================================

def query_dns(
    hostname: str,
    record_type: str = 'A',
    nameserver: Optional[str] = None,
    timeout: float = 10.0,
) -> List[str]:
    """
    Query DNS for a record.
    
    Args:
        hostname: Fully qualified domain name
        record_type: Record type (A, AAAA, TXT, CNAME, etc.)
        nameserver: Specific DNS server to query (None = system default)
        timeout: Query timeout in seconds
        
    Returns:
        List of record values
    """
    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout
    
    if nameserver:
        resolver.nameservers = [nameserver]
    
    try:
        answers = resolver.resolve(hostname, record_type)
        return [str(rdata) for rdata in answers]
    except dns.resolver.NXDOMAIN:
        return []
    except dns.resolver.NoAnswer:
        return []
    except dns.resolver.NoNameservers:
        logger.warning(f"No nameservers available for {hostname}")
        return []
    except dns.exception.Timeout:
        logger.warning(f"DNS query timeout for {hostname}")
        return []


def wait_for_dns_propagation(
    hostname: str,
    expected_value: str,
    record_type: str = 'A',
    nameservers: Optional[List[str]] = None,
    timeout: int = 300,
    poll_interval: int = 10,
) -> bool:
    """
    Wait for DNS record to propagate.
    
    Args:
        hostname: Fully qualified domain name
        expected_value: Expected record value
        record_type: Record type (A, TXT, etc.)
        nameservers: List of nameservers to check
        timeout: Maximum time to wait (seconds)
        poll_interval: Time between checks (seconds)
        
    Returns:
        True if record propagated to all nameservers, False otherwise
    """
    if nameservers is None:
        config = get_dns_config()
        nameservers = config['check_servers']
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        all_propagated = True
        
        for ns in nameservers:
            records = query_dns(hostname, record_type, nameserver=ns)
            
            # For TXT records, values may be quoted
            normalized_records = [r.strip('"') for r in records]
            
            if expected_value not in records and expected_value not in normalized_records:
                all_propagated = False
                logger.debug(f"Record not yet propagated on {ns}: got {records}")
                break
        
        if all_propagated:
            elapsed = time.time() - start_time
            logger.info(f"DNS propagated in {elapsed:.1f}s")
            return True
        
        logger.debug(f"Waiting {poll_interval}s for propagation...")
        time.sleep(poll_interval)
    
    logger.warning(f"DNS propagation timeout after {timeout}s")
    return False


def wait_for_dns_removal(
    hostname: str,
    record_type: str = 'A',
    nameservers: Optional[List[str]] = None,
    timeout: int = 300,
    poll_interval: int = 10,
) -> bool:
    """
    Wait for DNS record to be removed (NXDOMAIN or empty).
    
    Args:
        hostname: Fully qualified domain name
        record_type: Record type (A, TXT, etc.)
        nameservers: List of nameservers to check
        timeout: Maximum time to wait (seconds)
        poll_interval: Time between checks (seconds)
        
    Returns:
        True if record removed from all nameservers, False otherwise
    """
    if nameservers is None:
        config = get_dns_config()
        nameservers = config['check_servers']
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        all_removed = True
        
        for ns in nameservers:
            records = query_dns(hostname, record_type, nameserver=ns)
            
            if records:
                all_removed = False
                logger.debug(f"Record still exists on {ns}: {records}")
                break
        
        if all_removed:
            elapsed = time.time() - start_time
            logger.info(f"DNS record removed in {elapsed:.1f}s")
            return True
        
        logger.debug(f"Waiting {poll_interval}s for removal...")
        time.sleep(poll_interval)
    
    logger.warning(f"DNS removal timeout after {timeout}s")
    return False


def generate_test_hostname(domain: str) -> str:
    """Generate a unique test hostname."""
    config = get_dns_config()
    prefix = config['test_subdomain_prefix']
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = ''.join(random.choices(string.ascii_lowercase, k=4))
    return f"{prefix}-{timestamp}-{random_suffix}.{domain}"


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def skip_unless_live():
    """Skip test if not in live mode."""
    mode = os.environ.get('DEPLOYMENT_MODE', 'mock')
    if mode != 'live':
        pytest.skip("Test requires live mode (--mode live)")


@pytest.fixture
def dns_config():
    """Provide DNS configuration."""
    return get_dns_config()


# =============================================================================
# Tests
# =============================================================================

@pytest.mark.live
class TestDNSQueries:
    """Test DNS query functionality."""
    
    def test_query_known_record(self, skip_unless_live):
        """Verify DNS queries work against known records."""
        # Query Google's DNS (should always resolve)
        records = query_dns('dns.google', 'A')
        assert len(records) > 0, "Should resolve dns.google"
        logger.info(f"dns.google A records: {records}")
    
    def test_query_specific_nameserver(self, skip_unless_live):
        """Test querying specific nameservers."""
        records = query_dns('example.com', 'A', nameserver='8.8.8.8')
        assert len(records) > 0, "Should resolve example.com via 8.8.8.8"
    
    def test_query_nonexistent_domain(self, skip_unless_live):
        """Test NXDOMAIN handling."""
        records = query_dns('this-domain-does-not-exist-12345.com', 'A')
        assert records == [], "Should return empty for nonexistent domain"


@pytest.mark.live
class TestDNSRecordLifecycle:
    """Test creating, verifying, and deleting DNS records."""
    
    def test_create_a_record(self, skip_unless_live, dns_config):
        """
        Test creating an A record.
        
        1. Create test A record via API
        2. Verify record resolves via dig/DNS query
        3. Delete test record
        4. Verify record no longer resolves
        """
        pytest.skip("Skeleton test - implement API record creation")
        
        # Example implementation:
        # test_domain = os.environ.get('TEST_DOMAIN', 'example.com')
        # hostname = generate_test_hostname(test_domain)
        # test_ip = '192.0.2.1'  # TEST-NET-1 IP
        
        # Create record via API
        # response = api_client.create_record(hostname, 'A', test_ip)
        # assert response.success
        
        # Wait for propagation
        # assert wait_for_dns_propagation(hostname, test_ip, 'A')
        
        # Delete record
        # response = api_client.delete_record(hostname, 'A')
        # assert response.success
        
        # Verify removal
        # assert wait_for_dns_removal(hostname, 'A')
    
    def test_create_txt_record(self, skip_unless_live, dns_config):
        """
        Test creating a TXT record (common for DNS-01 challenges).
        
        1. Create test TXT record via API
        2. Verify record resolves
        3. Delete test record
        4. Verify removal
        """
        pytest.skip("Skeleton test - implement TXT record lifecycle")
    
    def test_update_existing_record(self, skip_unless_live, dns_config):
        """
        Test updating an existing DNS record.
        
        1. Create initial record
        2. Update to new value
        3. Verify new value propagates
        4. Cleanup
        """
        pytest.skip("Skeleton test - implement record update")


@pytest.mark.live
class TestDNSPropagation:
    """Test DNS propagation across multiple nameservers."""
    
    def test_propagation_to_google_dns(self, skip_unless_live):
        """Verify record propagates to Google DNS (8.8.8.8)."""
        pytest.skip("Skeleton test - implement propagation check")
    
    def test_propagation_to_cloudflare_dns(self, skip_unless_live):
        """Verify record propagates to Cloudflare DNS (1.1.1.1)."""
        pytest.skip("Skeleton test - implement propagation check")
    
    def test_propagation_timing(self, skip_unless_live):
        """Measure propagation time across nameservers."""
        pytest.skip("Skeleton test - implement timing measurement")


@pytest.mark.live
class TestDDNSFlow:
    """Test Dynamic DNS update flow end-to-end."""
    
    def test_ddns_update_from_ui(self, page, skip_unless_live):
        """
        Test DDNS update triggered from client portal.
        
        1. Login to client portal
        2. Navigate to DDNS update page
        3. Trigger update
        4. Verify DNS record updated
        """
        pytest.skip("Skeleton test - implement DDNS UI flow")
    
    def test_ddns_update_via_api(self, skip_unless_live):
        """
        Test DDNS update via API token.
        
        1. Get API token
        2. Call DDNS update endpoint
        3. Verify DNS record updated
        """
        pytest.skip("Skeleton test - implement DDNS API flow")


# =============================================================================
# Utility for Manual Testing
# =============================================================================

if __name__ == '__main__':
    """Run manual DNS test."""
    import sys
    
    print("DNS Verification Utility")
    print("=" * 40)
    
    config = get_dns_config()
    print(f"Test subdomain prefix: {config['test_subdomain_prefix']}")
    print(f"DNS servers: {config['check_servers']}")
    print(f"Propagation timeout: {config['propagation_timeout']}s")
    
    # Test query
    hostname = sys.argv[1] if len(sys.argv) > 1 else 'dns.google'
    record_type = sys.argv[2] if len(sys.argv) > 2 else 'A'
    
    print(f"\nQuerying {hostname} ({record_type})...")
    
    for ns in config['check_servers']:
        records = query_dns(hostname, record_type, nameserver=ns)
        print(f"  {ns}: {records or 'NXDOMAIN'}")

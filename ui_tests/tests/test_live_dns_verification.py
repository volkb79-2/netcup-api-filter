"""
Live DNS Verification Tests

These tests verify that DNS record changes made through the application
are actually propagated to DNS servers. This provides end-to-end verification
that the Netcup API integration is working correctly.

Prerequisites:
- DEPLOYMENT_MODE=live
- A domain under your control for testing (DNS_TEST_DOMAIN)

Backend options:
- PowerDNS (recommended for local/self-hosted authoritative DNS):
    - POWERDNS_API_URL (usually comes from .env.services)
    - POWERDNS_API_KEY
    - Zone DNS_TEST_DOMAIN must exist in PowerDNS

Note: Netcup CCP API integration may also work, but these tests currently
implement record lifecycle via PowerDNS HTTP API because it is deterministic
and works in local dev setups.

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

from netcup_api_filter.backends.powerdns import PowerDNSBackend

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
        'test_domain': os.environ.get('DNS_TEST_DOMAIN', '').strip().rstrip('.'),
        'test_subdomain_prefix': os.environ.get('DNS_TEST_SUBDOMAIN_PREFIX', '_naftest'),
        'propagation_timeout': int(os.environ.get('DNS_PROPAGATION_TIMEOUT', '300')),
        'propagation_poll_interval': int(os.environ.get('DNS_PROPAGATION_POLL_INTERVAL', '10')),
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
    poll_interval: Optional[int] = None,
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

    if poll_interval is None:
        config = get_dns_config()
        poll_interval = int(config.get('propagation_poll_interval') or 10)
    
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
    poll_interval: Optional[int] = None,
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

    if poll_interval is None:
        config = get_dns_config()
        poll_interval = int(config.get('propagation_poll_interval') or 10)
    
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


def generate_test_label() -> str:
    """Generate a unique DNS label suitable for creating records within a zone."""
    config = get_dns_config()
    prefix = config['test_subdomain_prefix']
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = ''.join(random.choices(string.ascii_lowercase, k=6))
    return f"{prefix}-{timestamp}-{random_suffix}"


def _ensure_live_dns_domain(dns_config: dict) -> str:
    domain = (dns_config.get('test_domain') or '').strip().rstrip('.')
    if not domain:
        pytest.skip("DNS_TEST_DOMAIN not set (configure live DNS domain to run lifecycle tests)")
    return domain


@pytest.fixture
def powerdns_backend(skip_unless_live):
    """Construct a PowerDNS backend if configured; otherwise skip."""
    api_url = (os.environ.get('POWERDNS_API_URL') or '').strip()
    api_key = (os.environ.get('POWERDNS_API_KEY') or '').strip()
    if not api_url:
        pytest.skip("POWERDNS_API_URL not set (source .env.services or set explicitly)")
    if not api_key:
        pytest.skip("POWERDNS_API_KEY not set")

    backend = PowerDNSBackend({'api_url': api_url, 'api_key': api_key})
    ok, msg = backend.test_connection()
    if not ok:
        pytest.skip(f"PowerDNS API not reachable: {msg}")
    return backend


@pytest.fixture
def dns_test_domain(skip_unless_live, dns_config, powerdns_backend):
    """Validate DNS_TEST_DOMAIN exists in PowerDNS and return it."""
    domain = _ensure_live_dns_domain(dns_config)
    ok, msg = powerdns_backend.validate_zone_access(domain)
    if not ok:
        pytest.skip(
            f"DNS_TEST_DOMAIN zone not accessible in PowerDNS: {domain} ({msg}). "
            "Create the zone in PowerDNS (tooling/backend-powerdns) and retry."
        )
    return domain


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
        # Implemented via PowerDNS HTTP API
        api_url = (os.environ.get('POWERDNS_API_URL') or '').strip()
        api_key = (os.environ.get('POWERDNS_API_KEY') or '').strip()
        if not api_url or not api_key:
            pytest.skip("PowerDNS not configured (need POWERDNS_API_URL and POWERDNS_API_KEY)")

        backend = PowerDNSBackend({'api_url': api_url, 'api_key': api_key})
        test_domain = _ensure_live_dns_domain(dns_config)
        ok, msg = backend.validate_zone_access(test_domain)
        if not ok:
            pytest.skip(f"DNS_TEST_DOMAIN not accessible in PowerDNS: {msg}")

        label = generate_test_label()
        hostname = f"{label}.{test_domain}"
        test_ip = '192.0.2.1'  # TEST-NET-1 IP

        record = {'hostname': label, 'type': 'A', 'destination': test_ip, 'ttl': 60}
        created = backend.create_record(test_domain, record)
        assert created['destination'] == test_ip

        assert wait_for_dns_propagation(
            hostname,
            test_ip,
            'A',
            timeout=dns_config['propagation_timeout'],
        ), f"A record did not propagate for {hostname}"

        record_id = f"{hostname}.:A"
        assert backend.delete_record(test_domain, record_id) is True

        assert wait_for_dns_removal(
            hostname,
            'A',
            timeout=dns_config['propagation_timeout'],
        ), f"A record did not get removed for {hostname}"
    
    def test_create_txt_record(self, skip_unless_live, dns_config, powerdns_backend, dns_test_domain):
        """
        Test creating a TXT record (common for DNS-01 challenges).
        
        1. Create test TXT record via API
        2. Verify record resolves
        3. Delete test record
        4. Verify removal
        """
        label = generate_test_label()
        hostname = f"{label}.{dns_test_domain}"
        txt_value = f"naf-live-{label}"

        record = {'hostname': label, 'type': 'TXT', 'destination': f'"{txt_value}"', 'ttl': 60}
        created = powerdns_backend.create_record(dns_test_domain, record)
        assert txt_value in created['destination']

        assert wait_for_dns_propagation(
            hostname,
            txt_value,
            'TXT',
            timeout=dns_config['propagation_timeout'],
        ), f"TXT record did not propagate for {hostname}"

        record_id = f"{hostname}.:TXT"
        assert powerdns_backend.delete_record(dns_test_domain, record_id) is True

        assert wait_for_dns_removal(
            hostname,
            'TXT',
            timeout=dns_config['propagation_timeout'],
        ), f"TXT record did not get removed for {hostname}"
    
    def test_update_existing_record(self, skip_unless_live, dns_config, powerdns_backend, dns_test_domain):
        """
        Test updating an existing DNS record.
        
        1. Create initial record
        2. Update to new value
        3. Verify new value propagates
        4. Cleanup
        """
        label = generate_test_label()
        hostname = f"{label}.{dns_test_domain}"
        ip1 = '192.0.2.1'
        ip2 = '192.0.2.2'

        powerdns_backend.create_record(dns_test_domain, {'hostname': label, 'type': 'A', 'destination': ip1, 'ttl': 60})
        assert wait_for_dns_propagation(
            hostname,
            ip1,
            'A',
            timeout=dns_config['propagation_timeout'],
        ), f"Initial A record did not propagate for {hostname}"

        powerdns_backend.update_record(dns_test_domain, f"{hostname}.:A", {'hostname': label, 'type': 'A', 'destination': ip2, 'ttl': 60})
        assert wait_for_dns_propagation(
            hostname,
            ip2,
            'A',
            timeout=dns_config['propagation_timeout'],
        ), f"Updated A record did not propagate for {hostname}"

        assert powerdns_backend.delete_record(dns_test_domain, f"{hostname}.:A") is True
        assert wait_for_dns_removal(
            hostname,
            'A',
            timeout=dns_config['propagation_timeout'],
        ), f"A record did not get removed for {hostname}"


@pytest.mark.live
class TestDNSPropagation:
    """Test DNS propagation across multiple nameservers."""
    
    def test_propagation_to_google_dns(self, skip_unless_live, dns_config, powerdns_backend, dns_test_domain):
        """Verify record propagates to Google DNS (8.8.8.8)."""
        label = generate_test_label()
        hostname = f"{label}.{dns_test_domain}"
        test_ip = '192.0.2.10'  # TEST-NET-1 IP

        record = {'hostname': label, 'type': 'A', 'destination': test_ip, 'ttl': 60}
        powerdns_backend.create_record(dns_test_domain, record)

        assert wait_for_dns_propagation(
            hostname,
            test_ip,
            'A',
            nameservers=['8.8.8.8'],
            timeout=dns_config['propagation_timeout'],
            poll_interval=dns_config['propagation_poll_interval'],
        ), f"A record did not propagate to 8.8.8.8 for {hostname}"

        assert powerdns_backend.delete_record(dns_test_domain, f"{hostname}.:A") is True
        assert wait_for_dns_removal(
            hostname,
            'A',
            nameservers=['8.8.8.8'],
            timeout=dns_config['propagation_timeout'],
            poll_interval=dns_config['propagation_poll_interval'],
        ), f"A record was not removed from 8.8.8.8 for {hostname}"
    
    def test_propagation_to_cloudflare_dns(self, skip_unless_live, dns_config, powerdns_backend, dns_test_domain):
        """Verify record propagates to Cloudflare DNS (1.1.1.1)."""
        label = generate_test_label()
        hostname = f"{label}.{dns_test_domain}"
        test_ip = '192.0.2.11'  # TEST-NET-1 IP

        record = {'hostname': label, 'type': 'A', 'destination': test_ip, 'ttl': 60}
        powerdns_backend.create_record(dns_test_domain, record)

        assert wait_for_dns_propagation(
            hostname,
            test_ip,
            'A',
            nameservers=['1.1.1.1'],
            timeout=dns_config['propagation_timeout'],
            poll_interval=dns_config['propagation_poll_interval'],
        ), f"A record did not propagate to 1.1.1.1 for {hostname}"

        assert powerdns_backend.delete_record(dns_test_domain, f"{hostname}.:A") is True
        assert wait_for_dns_removal(
            hostname,
            'A',
            nameservers=['1.1.1.1'],
            timeout=dns_config['propagation_timeout'],
            poll_interval=dns_config['propagation_poll_interval'],
        ), f"A record was not removed from 1.1.1.1 for {hostname}"
    
    def test_propagation_timing(self, skip_unless_live, dns_config, powerdns_backend, dns_test_domain):
        """Measure propagation time across configured nameservers."""
        label = generate_test_label()
        hostname = f"{label}.{dns_test_domain}"
        test_ip = '192.0.2.12'  # TEST-NET-1 IP

        record = {'hostname': label, 'type': 'A', 'destination': test_ip, 'ttl': 60}
        powerdns_backend.create_record(dns_test_domain, record)

        timings: dict[str, float] = {}
        deadline = time.monotonic() + dns_config['propagation_timeout']
        poll_interval = dns_config['propagation_poll_interval']

        for ns in [s.strip() for s in dns_config['check_servers'] if s.strip()]:
            start = time.monotonic()
            while time.monotonic() < deadline:
                values = query_dns(hostname, 'A', nameserver=ns)
                if test_ip in values:
                    timings[ns] = time.monotonic() - start
                    break
                time.sleep(poll_interval)

        try:
            missing = [ns for ns in [s.strip() for s in dns_config['check_servers'] if s.strip()] if ns not in timings]
            assert not missing, (
                f"Record did not propagate to all resolvers within {dns_config['propagation_timeout']}s: {missing}. "
                f"timings={timings}"
            )
        finally:
            # Best-effort cleanup
            try:
                powerdns_backend.delete_record(dns_test_domain, f"{hostname}.:A")
            except Exception:
                pass

        logger.info(f"Propagation timing (seconds) for {hostname}: {timings}")


@pytest.mark.live
class TestDDNSFlow:
    """Test Dynamic DNS update flow end-to-end."""
    
    def test_ddns_update_from_ui(self, skip_unless_live, dns_config, powerdns_backend, dns_test_domain):
        """DDNS-style update using the DynDNS2 protocol endpoint.

        This is a live integration test:
        - Calls /api/ddns/dyndns2/update with Bearer token
        - Verifies the resulting A record resolves via public resolvers
        """
        import httpx
        import re

        from ui_tests.config import settings

        label = generate_test_label()
        hostname = f"{label}.{dns_test_domain}"

        ip1 = '192.0.2.20'
        ip2 = '192.0.2.21'

        url = settings.url("/api/ddns/dyndns2/update")
        headers = {"Authorization": f"Bearer {settings.client_token}"}

        def _call(ip: str) -> tuple[int, str]:
            with httpx.Client(verify=False, timeout=30.0) as client:
                resp = client.get(url, headers=headers, params={"hostname": hostname, "myip": ip})
                return resp.status_code, resp.text.strip()

        status, text = _call(ip1)
        assert status == 200, f"Expected 200 from DDNS endpoint, got {status}: {text}"
        assert re.match(r"^(good|nochg)\s+", text), f"Unexpected DDNS response: {text!r}"
        assert ip1 in text, f"DDNS response should contain IP {ip1}: {text!r}"

        assert wait_for_dns_propagation(
            hostname,
            ip1,
            'A',
            timeout=dns_config['propagation_timeout'],
            poll_interval=dns_config['propagation_poll_interval'],
        ), f"DDNS update did not propagate for {hostname}"

        # Update to a new IP and verify propagation
        status, text = _call(ip2)
        assert status == 200, f"Expected 200 from DDNS endpoint, got {status}: {text}"
        assert re.match(r"^(good|nochg)\s+", text), f"Unexpected DDNS response: {text!r}"
        assert ip2 in text, f"DDNS response should contain IP {ip2}: {text!r}"

        assert wait_for_dns_propagation(
            hostname,
            ip2,
            'A',
            timeout=dns_config['propagation_timeout'],
            poll_interval=dns_config['propagation_poll_interval'],
        ), f"DDNS updated IP did not propagate for {hostname}"

        # Cleanup via authoritative backend (best-effort)
        assert powerdns_backend.delete_record(dns_test_domain, f"{hostname}.:A") is True
        assert wait_for_dns_removal(
            hostname,
            'A',
            timeout=dns_config['propagation_timeout'],
            poll_interval=dns_config['propagation_poll_interval'],
        ), f"DDNS record did not get removed for {hostname}"
    
    def test_ddns_update_via_api(self, skip_unless_live, dns_config, powerdns_backend, dns_test_domain):
        """DDNS update endpoint supports plain-text protocol responses and changes DNS."""
        import httpx
        import re

        from ui_tests.config import settings

        label = generate_test_label()
        hostname = f"{label}.{dns_test_domain}"
        test_ip = '192.0.2.22'

        url = settings.url("/api/ddns/dyndns2/update")
        headers = {"Authorization": f"Bearer {settings.client_token}"}

        with httpx.Client(verify=False, timeout=30.0) as client:
            resp = client.get(url, headers=headers, params={"hostname": hostname, "myip": test_ip})

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        text = resp.text.strip()
        assert re.match(r"^(good|nochg)\s+", text), f"Unexpected DDNS response: {text!r}"
        assert test_ip in text, f"DDNS response should contain IP {test_ip}: {text!r}"
        assert 'text/plain' in resp.headers.get('content-type', ''), (
            f"Expected text/plain, got {resp.headers.get('content-type')}"
        )

        assert wait_for_dns_propagation(
            hostname,
            test_ip,
            'A',
            timeout=dns_config['propagation_timeout'],
            poll_interval=dns_config['propagation_poll_interval'],
        ), f"DDNS A record did not propagate for {hostname}"

        assert powerdns_backend.delete_record(dns_test_domain, f"{hostname}.:A") is True


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

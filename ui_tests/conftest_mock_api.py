"""Pytest fixtures for mock Netcup API testing."""
import pytest
import threading
import time
from werkzeug.serving import make_server

from ui_tests.mock_netcup_api import (
    create_mock_api_app,
    reset_mock_state,
    seed_test_domain,
    MOCK_CUSTOMER_ID,
    MOCK_API_KEY,
    MOCK_API_PASSWORD
)


class MockNetcupAPIServer:
    """Wrapper for running mock Netcup API in a background thread."""
    
    def __init__(self, host='127.0.0.1', port=5555):
        self.host = host
        self.port = port
        self.app = create_mock_api_app()
        self.server = None
        self.thread = None
    
    def start(self):
        """Start the mock API server in a background thread."""
        self.server = make_server(self.host, self.port, self.app, threaded=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        
        # Wait for server to be ready
        for _ in range(50):  # 5 seconds max
            try:
                import requests
                requests.get(f"http://{self.host}:{self.port}/", timeout=0.5)
                break
            except:
                time.sleep(0.1)
    
    def stop(self):
        """Stop the mock API server."""
        if self.server:
            self.server.shutdown()
            self.thread.join(timeout=5)
    
    @property
    def url(self):
        """Get the base URL for the mock API."""
        return f"http://{self.host}:{self.port}/run/webservice/servers/endpoint.php"


@pytest.fixture(scope='function')
def mock_netcup_api_server():
    """Fixture that provides a running mock Netcup API server.
    
    Usage:
        def test_something(mock_netcup_api_server):
            api_url = mock_netcup_api_server.url
            # Use api_url in tests
    """
    reset_mock_state()
    server = MockNetcupAPIServer()
    server.start()
    
    yield server
    
    server.stop()
    reset_mock_state()


@pytest.fixture(scope='function')
def mock_netcup_credentials():
    """Fixture that provides mock Netcup API credentials."""
    return {
        'customer_id': MOCK_CUSTOMER_ID,
        'api_key': MOCK_API_KEY,
        'api_password': MOCK_API_PASSWORD
    }


@pytest.fixture(scope='function')
def seeded_test_domain(mock_netcup_api_server):
    """Fixture that provides a mock API server with a seeded test domain.
    
    The domain 'test-e2e.example.com' is pre-seeded with:
    - @ A record pointing to 192.0.2.1
    - www A record pointing to 192.0.2.1
    - @ AAAA record pointing to 2001:db8::1
    """
    domain = "test-e2e.example.com"
    seed_test_domain(domain)
    
    return {
        'server': mock_netcup_api_server,
        'domain': domain,
        'api_url': mock_netcup_api_server.url
    }

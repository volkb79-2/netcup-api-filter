"""Local development WSGI application with database access control.

This module bootstraps the Flask app in database mode, seeds the default admin
and test client, and wires a lightweight fake Netcup client so that the client
portal can load without calling the real API.  Run it via:

    LOCAL_DB_PATH=./tmp/local-netcup.db \
    gunicorn tooling.local_proxy.local_app:app -b 0.0.0.0:5100

"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add project root and src package to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_ROOT))

from netcup_api_filter.database import create_app
from netcup_api_filter.access_control import AccessControl
from netcup_api_filter.bootstrap import AdminSeedOptions, ClientSeedOptions, seed_default_entities

DEFAULT_SECRET_KEY = os.environ.get("LOCAL_SECRET_KEY", "local-dev-secret-key")

DEFAULT_DB_PATH = Path(os.environ.get("LOCAL_DB_PATH") or (Path.cwd() / "tmp" / "local-netcup.db"))
DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_ADMIN_USERNAME = os.environ.get("LOCAL_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("LOCAL_ADMIN_PASSWORD", "admin")
DEFAULT_CLIENT_ID = os.environ.get("LOCAL_CLIENT_ID", "test_qweqweqwe_vi")
DEFAULT_CLIENT_SECRET_KEY = os.environ.get("LOCAL_CLIENT_SECRET_KEY", "qweqweqwe_vi_readonly_secret_key_12345")
DEFAULT_CLIENT_TOKEN = f"{DEFAULT_CLIENT_ID}:{DEFAULT_CLIENT_SECRET_KEY}"  # Two-factor format: client_id:secret_key
DEFAULT_CLIENT_DOMAIN = os.environ.get("LOCAL_CLIENT_DOMAIN", "qweqweqwe.vi")
DEFAULT_CLIENT_RECORD_TYPES = os.environ.get("LOCAL_CLIENT_RECORD_TYPES", "A").split(",")
DEFAULT_CLIENT_OPERATIONS = os.environ.get("LOCAL_CLIENT_OPERATIONS", "read").split(",")


class FakeNetcupClient:
    """Minimal stub returned to the portal when exercising DNS flows locally."""

    def info_dns_zone(self, domain: str) -> Dict[str, Any]:
        return {
            "domainname": domain,
            "zoneroot": domain,
            "zoneconfig": {"ttl": 3600},
        }

    def info_dns_records(self, domain: str) -> List[Dict[str, Any]]:
        return [
            {
                "hostname": "@",
                "type": "A",
                "destination": "192.0.2.10",
                "state": "yes",
                "ttl": 3600,
            },
            {
                "hostname": "www",
                "type": "A",
                "destination": "192.0.2.20",
                "state": "yes",
                "ttl": 3600,
            },
        ]

    def update_dns_records(self, domain: str, payload: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover - local dev helper
        return {"status": "noop", "domainname": domain, "payload": payload}


def _configure_app() -> Any:
    # Set database path
    os.environ.setdefault("NETCUP_FILTER_DB_PATH", str(DEFAULT_DB_PATH))
    
    # Set seeding defaults via environment variables (create_app will seed automatically)
    os.environ.setdefault("DEFAULT_ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME)
    os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
    os.environ.setdefault("DEFAULT_TEST_CLIENT_ID", DEFAULT_CLIENT_ID)
    os.environ.setdefault("DEFAULT_TEST_CLIENT_SECRET_KEY", DEFAULT_CLIENT_SECRET_KEY)
    os.environ.setdefault("DEFAULT_TEST_CLIENT_REALM_VALUE", DEFAULT_CLIENT_DOMAIN)
    os.environ.setdefault("DEFAULT_TEST_CLIENT_RECORD_TYPES", ",".join(DEFAULT_CLIENT_RECORD_TYPES))
    os.environ.setdefault("DEFAULT_TEST_CLIENT_OPERATIONS", ",".join(DEFAULT_CLIENT_OPERATIONS))
    
    # Create the full app with admin UI (will seed automatically using env vars)
    app = create_app()
    
    # Override with fake Netcup client for local testing
    fake_client = FakeNetcupClient()
    app.config["netcup_client"] = fake_client
    import filter_proxy
    filter_proxy.netcup_client = fake_client

    return app


app = _configure_app()
application = app
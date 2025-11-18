"""Local development WSGI application with database access control.

This module bootstraps the Flask app in database mode, seeds the default admin
and test client, and wires a lightweight fake Netcup client so that the client
portal can load without calling the real API.  Run it via:

    LOCAL_DB_PATH=./tmp/local-netcup.db \
    gunicorn tooling.local_proxy.local_app:app -b 0.0.0.0:5100

"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import filter_proxy
from access_control import AccessControl
from admin_ui import setup_admin_ui
from database import Client, AdminUser, db, init_db
from utils import hash_password

DEFAULT_SECRET_KEY = os.environ.get("LOCAL_SECRET_KEY", "local-dev-secret-key")

DEFAULT_DB_PATH = Path(os.environ.get("LOCAL_DB_PATH") or (Path.cwd() / "tmp" / "local-netcup.db"))
DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_ADMIN_USERNAME = os.environ.get("LOCAL_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("LOCAL_ADMIN_PASSWORD", "admin")
DEFAULT_CLIENT_ID = os.environ.get("LOCAL_CLIENT_ID", "test_qweqweqwe_vi")
DEFAULT_CLIENT_TOKEN = os.environ.get("LOCAL_CLIENT_TOKEN", "qweqweqwe-vi-readonly")
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


def _seed_database() -> None:
    with filter_proxy.app.app_context():
        admin = AdminUser.query.filter_by(username=DEFAULT_ADMIN_USERNAME).first()
        if not admin:
            admin = AdminUser(
                username=DEFAULT_ADMIN_USERNAME,
                password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
                must_change_password=0,
            )
            db.session.add(admin)
        else:
            admin.password_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
            admin.must_change_password = 0

        client = Client.query.filter_by(client_id=DEFAULT_CLIENT_ID).first()
        if not client:
            client = Client(
                client_id=DEFAULT_CLIENT_ID,
                secret_token=hash_password(DEFAULT_CLIENT_TOKEN),
                description="Local test client",
                realm_type="host",
                realm_value=DEFAULT_CLIENT_DOMAIN,
                is_active=1,
            )
            client.set_allowed_record_types([item.strip() for item in DEFAULT_CLIENT_RECORD_TYPES if item.strip()])
            client.set_allowed_operations([item.strip() for item in DEFAULT_CLIENT_OPERATIONS if item.strip()])
            db.session.add(client)

        db.session.commit()


def _configure_app() -> Any:
    os.environ.setdefault("NETCUP_FILTER_DB_PATH", str(DEFAULT_DB_PATH))

    app = filter_proxy.app
    init_db(app)
    app.secret_key = DEFAULT_SECRET_KEY  # local dev sessions need a key
    setup_admin_ui(app)
    _seed_database()

    access_control = AccessControl(use_database=True)
    app.config["access_control"] = access_control
    filter_proxy.access_control = access_control

    fake_client = FakeNetcupClient()
    app.config["netcup_client"] = fake_client
    filter_proxy.netcup_client = fake_client

    return app


app = _configure_app()
application = app
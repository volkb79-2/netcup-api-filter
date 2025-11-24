"""Reusable helpers for seeding default admins, clients, and config."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence

from database import AdminUser, Client, db, set_system_config
from utils import hash_password

logger = logging.getLogger(__name__)


def _load_env_defaults() -> dict:
    """Load default values from .env.defaults file.
    
    Returns dict with DEFAULT_* keys loaded from .env.defaults.
    Falls back to hardcoded values if file not found.
    """
    defaults = {
        "DEFAULT_ADMIN_USERNAME": "admin",
        "DEFAULT_ADMIN_PASSWORD": "admin",
        "DEFAULT_TEST_CLIENT_ID": "test_qweqweqwe_vi",
        "DEFAULT_TEST_CLIENT_SECRET_KEY": "qweqweqwe_vi_readonly_secret_key_12345",
        "DEFAULT_TEST_CLIENT_DESCRIPTION": "Sample read-only client",
        "DEFAULT_TEST_CLIENT_REALM_TYPE": "host",
        "DEFAULT_TEST_CLIENT_REALM_VALUE": "qweqweqwe.vi",
        "DEFAULT_TEST_CLIENT_RECORD_TYPES": "A",
        "DEFAULT_TEST_CLIENT_OPERATIONS": "read",
    }
    
    # Try to find .env.defaults
    env_paths = [
        Path.cwd() / ".env.defaults",
        Path(__file__).parent.parent / ".env.defaults",
    ]
    
    for env_path in env_paths:
        if env_path.exists():
            try:
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, value = line.split('=', 1)
                            defaults[key.strip()] = value.strip()
                logger.info("Loaded defaults from %s", env_path)
                break
            except Exception as e:
                logger.warning("Failed to read %s: %s", env_path, e)
    
    return defaults


_ENV_DEFAULTS = _load_env_defaults()


@dataclass
class AdminSeedOptions:
    username: str = None
    password: str = None
    must_change_password: bool = True
    
    def __post_init__(self):
        if self.username is None:
            self.username = _ENV_DEFAULTS.get("DEFAULT_ADMIN_USERNAME", "admin")
        if self.password is None:
            self.password = _ENV_DEFAULTS.get("DEFAULT_ADMIN_PASSWORD", "admin")


@dataclass
class ClientSeedOptions:
    client_id: str
    token: str
    description: str
    realm_type: str = "host"
    realm_value: str = ""
    record_types: Sequence[str] = field(default_factory=lambda: ["A", "AAAA", "CNAME", "NS"])
    operations: Sequence[str] = field(default_factory=lambda: ["read"])
    allowed_ip_ranges: Sequence[str] = field(default_factory=list)
    is_active: bool = True


def _get_default_test_client_options() -> ClientSeedOptions:
    """Create default test client options from .env.defaults."""
    return ClientSeedOptions(
        client_id=_ENV_DEFAULTS.get("DEFAULT_TEST_CLIENT_ID", "test_qweqweqwe_vi"),
        token=_ENV_DEFAULTS.get("DEFAULT_TEST_CLIENT_SECRET_KEY", "qweqweqwe_vi_readonly_secret_key_12345"),
        description=_ENV_DEFAULTS.get("DEFAULT_TEST_CLIENT_DESCRIPTION", "Sample read-only client"),
        realm_type=_ENV_DEFAULTS.get("DEFAULT_TEST_CLIENT_REALM_TYPE", "host"),
        realm_value=_ENV_DEFAULTS.get("DEFAULT_TEST_CLIENT_REALM_VALUE", "qweqweqwe.vi"),
        record_types=tuple(_ENV_DEFAULTS.get("DEFAULT_TEST_CLIENT_RECORD_TYPES", "A").split(',')),
        operations=tuple(_ENV_DEFAULTS.get("DEFAULT_TEST_CLIENT_OPERATIONS", "read").split(',')),
    )


DEFAULT_TEST_CLIENT_OPTIONS = _get_default_test_client_options()


def ensure_admin_user(options: AdminSeedOptions) -> AdminUser:
    admin = AdminUser.query.filter_by(username=options.username).first()
    if not admin:
        admin = AdminUser(username=options.username)
        admin.password_hash = hash_password(options.password)
        admin.must_change_password = 1 if options.must_change_password else 0
        db.session.add(admin)
        logger.info("Created admin user %s with default password", options.username)
    else:
        logger.info("Admin user %s already exists, keeping existing password", options.username)
    return admin


def ensure_client(options: ClientSeedOptions) -> Client:
    client = Client.query.filter_by(client_id=options.client_id).first()
    if not client:
        client = Client(
            client_id=options.client_id,
            description=options.description,
            realm_type=options.realm_type,
            realm_value=options.realm_value,
            is_active=1 if options.is_active else 0,
        )
        db.session.add(client)
        logger.info("Created client %s", options.client_id)
    else:
        logger.info("Refreshed client %s", options.client_id)
    
    # Store hashed secret key (token parameter contains just the secret_key part)
    client.secret_key_hash = hash_password(options.token)
    client.description = options.description
    client.realm_type = options.realm_type
    client.realm_value = options.realm_value
    client.is_active = 1 if options.is_active else 0
    client.set_allowed_record_types(list(options.record_types) or ["A"])
    client.set_allowed_operations(list(options.operations) or ["read"])
    if options.allowed_ip_ranges:
        client.set_allowed_ip_ranges(list(options.allowed_ip_ranges))
    else:
        client.allowed_ip_ranges = None
    return client


def seed_default_entities(
    admin_options: AdminSeedOptions | None = None,
    client_options: ClientSeedOptions | None = None,
) -> None:
    ensure_admin_user(admin_options or AdminSeedOptions())
    ensure_client(client_options or DEFAULT_TEST_CLIENT_OPTIONS)
    logger.info("Seeded default admin user and test client")
    db.session.commit()


def seed_from_config(config: dict) -> None:
    """Apply structured config (e.g., config.yaml) to the database."""
    netcup_config = config.get("netcup")
    if netcup_config:
        logger.info("Applying Netcup API configuration from config")
        set_system_config("netcup_config", {
            "customer_id": netcup_config.get("customer_id", ""),
            "api_key": netcup_config.get("api_key", ""),
            "api_password": netcup_config.get("api_password", ""),
            "api_url": netcup_config.get(
                "api_url",
                "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON",
            ),
            "timeout": int(netcup_config.get("timeout", 30)),
        })

    tokens: Iterable[dict] = config.get("tokens", []) or []
    if tokens:
        logger.info("Seeding %d clients from config", len(tokens))
    else:
        logger.warning("No tokens found in config; skipping client import")
    for idx, token in enumerate(tokens):
        description = token.get("description") or f"client_{idx+1}"
        permissions: List[dict] = token.get("permissions") or []
        if not permissions:
            logger.warning("Token %s has no permissions; skipping", description)
            continue
        primary = permissions[0]
        domain = primary.get("domain", "").strip()
        if not domain:
            logger.warning("Token %s missing domain; skipping", description)
            continue
        if domain.startswith("*."):
            realm_type = "subdomain"
            realm_value = domain[2:]
        elif "*" in domain:
            realm_type = "subdomain"
            realm_value = domain.replace("*", "")
        else:
            realm_type = "host"
            realm_value = domain
        record_types = primary.get("record_types") or ["A"]
        allowed_types = ["A", "AAAA", "CNAME", "NS"]
        record_types = [rt for rt in record_types if rt in allowed_types or rt == "*"]
        if "*" in record_types:
            record_types = allowed_types
        operations = primary.get("operations") or ["read"]
        allowed_origins = token.get("allowed_origins") or []
        token_value = token.get("token")
        if not token_value:
            logger.warning("Token %s missing secret token; skipping", description)
            continue
        ensure_client(
            ClientSeedOptions(
                client_id=token.get("client_id") or description.replace(" ", "_"),
                token=token_value,
                description=description,
                realm_type=realm_type,
                realm_value=realm_value,
                record_types=record_types,
                operations=operations,
                allowed_ip_ranges=allowed_origins,
            )
        )
        logger.info(
            "Seeded client %s for %s %s",
            token.get("client_id") or description,
            realm_type,
            realm_value or "<all>",
        )
    db.session.commit()

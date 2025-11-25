"""Reusable helpers for seeding default admins, clients, and config."""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

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
        "DEFAULT_TEST_CLIENT_DESCRIPTION": "Sample read-only client",
        "DEFAULT_TEST_CLIENT_REALM_TYPE": "host",
        "DEFAULT_TEST_CLIENT_REALM_VALUE": "example.com",
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


def generate_test_client_credentials() -> Tuple[str, str]:
    """Generate secure random credentials for test client.
    
    Returns:
        Tuple of (client_id, secret_key)
    """
    # Generate random client_id: test_<8_random_chars>
    random_suffix = secrets.token_urlsafe(6)[:8]  # Get 8 URL-safe chars
    client_id = f"test_{random_suffix}"
    
    # Generate random secret key: <random>_readonly_secret_<random>
    secret_part1 = secrets.token_urlsafe(12)
    secret_part2 = secrets.token_urlsafe(8)
    secret_key = f"{secret_part1}_readonly_secret_{secret_part2}"
    
    return client_id, secret_key


def create_default_test_client_options() -> ClientSeedOptions:
    """Create default test client options with generated credentials."""
    client_id, secret_key = generate_test_client_credentials()
    return ClientSeedOptions(
        client_id=client_id,
        token=secret_key,
        description=_ENV_DEFAULTS.get("DEFAULT_TEST_CLIENT_DESCRIPTION", "Sample read-only client"),
        realm_type=_ENV_DEFAULTS.get("DEFAULT_TEST_CLIENT_REALM_TYPE", "host"),
        realm_value=_ENV_DEFAULTS.get("DEFAULT_TEST_CLIENT_REALM_VALUE", "example.com"),
        record_types=tuple(_ENV_DEFAULTS.get("DEFAULT_TEST_CLIENT_RECORD_TYPES", "A").split(',')),
        operations=tuple(_ENV_DEFAULTS.get("DEFAULT_TEST_CLIENT_OPERATIONS", "read").split(',')),
    )


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


def seed_demo_audit_logs() -> None:
    """Seed demo audit logs for empty database."""
    from database import AuditLog
    from datetime import datetime, timedelta
    import json
    
    # Only seed if no logs exist
    if AuditLog.query.first():
        logger.info("Audit logs already exist, skipping demo seed")
        return
    
    logger.info("Seeding demo audit logs")
    base_time = datetime.utcnow() - timedelta(hours=2)
    
    demo_logs = [
        {"client_id": "test_qweqweqwe_vi", "operation": "infoDnsZone", "domain": "test.example.com", 
         "success": True, "ip": "192.168.1.100", "minutes_ago": 120},
        {"client_id": "test_qweqweqwe_vi", "operation": "infoDnsRecords", "domain": "test.example.com",
         "success": True, "ip": "192.168.1.100", "minutes_ago": 115},
        {"client_id": "test_qweqweqwe_vi", "operation": "updateDnsRecords", "domain": "test.example.com",
         "success": True, "ip": "192.168.1.100", "minutes_ago": 110},
        {"client_id": "monitoring_client", "operation": "infoDnsRecords", "domain": "example.com",
         "success": True, "ip": "10.0.0.50", "minutes_ago": 90},
        {"client_id": "test_qweqweqwe_vi", "operation": "infoDnsRecords", "domain": "test.example.com",
         "success": True, "ip": "192.168.1.100", "minutes_ago": 60},
        {"client_id": "invalid_client", "operation": "infoDnsZone", "domain": "unauthorized.com",
         "success": False, "ip": "203.0.113.42", "minutes_ago": 45},
        {"client_id": "test_qweqweqwe_vi", "operation": "updateDnsRecords", "domain": "test.example.com",
         "success": True, "ip": "192.168.1.100", "minutes_ago": 30},
        {"client_id": "monitoring_client", "operation": "infoDnsZone", "domain": "example.com",
         "success": True, "ip": "10.0.0.50", "minutes_ago": 15},
    ]
    
    for log_data in demo_logs:
        timestamp = base_time + timedelta(minutes=log_data["minutes_ago"])
        log = AuditLog(
            timestamp=timestamp,
            client_id=log_data["client_id"],
            ip_address=log_data["ip"],
            operation=log_data["operation"],
            domain=log_data["domain"],
            request_data=json.dumps({"action": log_data["operation"], "param": {"domainname": log_data["domain"]}}),
            response_data=json.dumps({"status": "success" if log_data["success"] else "error"}),
            success=log_data["success"],
            error_message=None if log_data["success"] else "Permission denied"
        )
        db.session.add(log)
    
    db.session.commit()
    logger.info("Seeded %d demo audit logs", len(demo_logs))


def seed_demo_clients() -> list[Tuple[str, str, str]]:
    """Seed multiple demo clients with different permission configurations.
    
    Returns:
        List of tuples (client_id, secret_key, description)
    """
    clients = []
    
    # 1. Read-only host client (basic monitoring)
    client_id_1, secret_1 = generate_test_client_credentials()
    ensure_client(ClientSeedOptions(
        client_id=client_id_1,
        token=secret_1,
        description="Read-only monitoring for example.com",
        realm_type="host",
        realm_value="example.com",
        record_types=["A", "AAAA"],
        operations=["read"],
    ))
    clients.append((client_id_1, secret_1, "Read-only host"))
    logger.info(f"Created read-only host client: {client_id_1}")
    
    # 2. Full control host client (can update DNS records)
    client_id_2, secret_2 = generate_test_client_credentials()
    ensure_client(ClientSeedOptions(
        client_id=client_id_2,
        token=secret_2,
        description="Full DNS management for api.example.com",
        realm_type="host",
        realm_value="api.example.com",
        record_types=["A", "AAAA", "CNAME"],
        operations=["read", "update", "create", "delete"],
    ))
    clients.append((client_id_2, secret_2, "Full control host"))
    logger.info(f"Created full-control host client: {client_id_2}")
    
    # 3. Subdomain wildcard read-only (monitoring all subdomains)
    client_id_3, secret_3 = generate_test_client_credentials()
    ensure_client(ClientSeedOptions(
        client_id=client_id_3,
        token=secret_3,
        description="Monitor all *.example.com subdomains",
        realm_type="subdomain",
        realm_value="example.com",
        record_types=["A", "AAAA", "CNAME"],
        operations=["read"],
    ))
    clients.append((client_id_3, secret_3, "Subdomain read-only"))
    logger.info(f"Created subdomain read-only client: {client_id_3}")
    
    # 4. Subdomain wildcard with update (dynamic DNS service)
    client_id_4, secret_4 = generate_test_client_credentials()
    ensure_client(ClientSeedOptions(
        client_id=client_id_4,
        token=secret_4,
        description="Dynamic DNS for *.dyn.example.com",
        realm_type="subdomain",
        realm_value="dyn.example.com",
        record_types=["A", "AAAA"],
        operations=["read", "update", "create"],
    ))
    clients.append((client_id_4, secret_4, "Subdomain with update"))
    logger.info(f"Created subdomain update client: {client_id_4}")
    
    # 5. Multi-record type client (DNS provider integration)
    client_id_5, secret_5 = generate_test_client_credentials()
    ensure_client(ClientSeedOptions(
        client_id=client_id_5,
        token=secret_5,
        description="DNS provider for services.example.com",
        realm_type="host",
        realm_value="services.example.com",
        record_types=["A", "AAAA", "CNAME", "NS"],
        operations=["read", "update", "create", "delete"],
    ))
    clients.append((client_id_5, secret_5, "Multi-record full control"))
    logger.info(f"Created multi-record client: {client_id_5}")
    
    db.session.commit()
    logger.info(f"Seeded {len(clients)} demo clients with varied permissions")
    return clients


def seed_default_entities(
    admin_options: AdminSeedOptions | None = None,
    client_options: ClientSeedOptions | None = None,
    seed_demo_clients_flag: bool = True,
) -> Tuple[str, str, list]:
    """Seed default admin and test clients.
    
    Args:
        admin_options: Optional admin user configuration
        client_options: Optional single test client (backward compatibility)
        seed_demo_clients_flag: Whether to seed multiple demo clients (default True)
    
    Returns:
        Tuple of (primary_client_id, primary_secret_key, all_demo_clients)
        where all_demo_clients is list of (client_id, secret_key, description) tuples
    """
    ensure_admin_user(admin_options or AdminSeedOptions())
    
    all_demo_clients = []
    
    # For backward compatibility: if client_options provided, use it
    if client_options is not None:
        ensure_client(client_options)
        primary_client_id = client_options.client_id
        primary_secret = client_options.token
        all_demo_clients = [(primary_client_id, primary_secret, client_options.description)]
    else:
        # Create multiple demo clients with different configurations
        if seed_demo_clients_flag:
            all_demo_clients = seed_demo_clients()
            # Return first client as primary (for backward compatibility)
            primary_client_id, primary_secret, _ = all_demo_clients[0]
        else:
            # Fallback: create single default client
            client_options = create_default_test_client_options()
            ensure_client(client_options)
            primary_client_id = client_options.client_id
            primary_secret = client_options.token
            all_demo_clients = [(primary_client_id, primary_secret, client_options.description)]
    
    seed_demo_audit_logs()
    logger.info("Seeded default admin user, test clients, and demo audit logs")
    db.session.commit()
    
    # Return the primary client credentials and all demo clients
    return primary_client_id, primary_secret, all_demo_clients


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

"""
Platform Backend Initialization

This module handles creation of platform-owned BackendService and ManagedDomainRoot
entries from app-config.toml imports.

Called after app-config.toml is imported and settings are in database.
"""
import json
import logging
import os
from typing import Optional

from netcup_api_filter.database import db, get_setting
from netcup_api_filter.models import (
    Account,
    BackendService,
    BackendProvider,
    ManagedDomainRoot,
    OwnerTypeEnum,
    VisibilityEnum,
)
from netcup_api_filter.bootstrap.seeding import (
    seed_backend_providers,
    create_backend_service,
    create_domain_root,
)

logger = logging.getLogger(__name__)


def get_public_fqdn() -> Optional[str]:
    """Get PUBLIC_FQDN from environment (.env.workspace)."""
    return os.environ.get('PUBLIC_FQDN')


def get_powerdns_api_url() -> str:
    """
    Get PowerDNS API URL with auto-detection.
    
    Priority:
    1. platform_backends_config.powerdns_api_url (if set)
    2. Internal container hostname (if running in Docker network)
    3. PUBLIC_FQDN-based HTTPS URL (if PUBLIC_FQDN available)
    
    Returns:
        PowerDNS API URL
    """
    # Check config first
    platform_backends_str = get_setting('platform_backends_config')
    if platform_backends_str:
        try:
            platform_backends = json.loads(platform_backends_str)
            if platform_backends.get('powerdns_api_url'):
                return platform_backends['powerdns_api_url']
        except (json.JSONDecodeError, TypeError):
            pass
    
    # Try internal container hostname (works in Docker network)
    powerdns_hostname = os.environ.get('HOSTNAME_POWERDNS', 'naf-dev-powerdns')
    internal_url = f"http://{powerdns_hostname}:8081"
    
    # Check if we can reach internal hostname (Docker network check)
    # For now, just return internal URL if HOSTNAME_POWERDNS is set
    if os.environ.get('HOSTNAME_POWERDNS'):
        logger.info(f"Using internal PowerDNS URL: {internal_url}")
        return internal_url
    
    # Fall back to PUBLIC_FQDN-based HTTPS URL
    public_fqdn = get_public_fqdn()
    if public_fqdn:
        https_url = f"https://{public_fqdn}/backend-powerdns"
        logger.info(f"Using public PowerDNS URL: {https_url}")
        return https_url
    
    # Last resort - localhost (probably won't work in production)
    logger.warning("Could not detect PowerDNS URL, using localhost")
    return "http://localhost:8081"


def setup_platform_powerdns() -> Optional[BackendService]:
    """
    Create platform PowerDNS BackendService if enabled.
    
    Uses POWERDNS_API_KEY from environment.
    PowerDNS limitation: Single API key = platform-owned only (not user BYOD).
    
    Returns:
        Created BackendService or None if disabled/already exists
    """
    # Check if enabled
    platform_backends_str = get_setting('platform_backends_config')
    if not platform_backends_str:
        logger.info("No platform_backends_config found, skipping PowerDNS setup")
        return None
    
    try:
        platform_backends = json.loads(platform_backends_str)
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse platform_backends_config")
        return None
    
    if not platform_backends.get('powerdns_enabled'):
        logger.info("PowerDNS platform backend disabled")
        return None
    
    # Get API key from environment
    api_key = os.environ.get('POWERDNS_API_KEY')
    if not api_key:
        logger.warning("POWERDNS_API_KEY not set, cannot create PowerDNS backend")
        return None
    
    # Check if service already exists
    existing = BackendService.query.filter_by(service_name='platform-powerdns').first()
    if existing:
        logger.info("Platform PowerDNS backend already exists")
        return existing
    
    # Get or create provider
    provider = BackendProvider.query.filter_by(provider_code='powerdns').first()
    if not provider:
        seed_backend_providers()
        provider = BackendProvider.query.filter_by(provider_code='powerdns').first()
    
    if not provider:
        logger.error("PowerDNS provider not found after seeding")
        return None
    
    # Get API URL
    api_url = get_powerdns_api_url()
    
    # Create platform BackendService
    config = {
        'api_url': api_url,
        'api_key': api_key,
        'server_id': 'localhost',  # Default PowerDNS server ID
    }
    
    service = create_backend_service(
        provider_code='powerdns',
        service_name='platform-powerdns',
        display_name='Platform PowerDNS',
        config=config,
        owner_type='platform',
        is_active=True,
    )
    
    logger.info(f"Created platform PowerDNS backend: {api_url}")
    return service


def setup_platform_netcup() -> Optional[BackendService]:
    """
    Create platform Netcup BackendService if enabled.
    
    Uses netcup_config from database (imported from [netcup] section).
    Netcup supports multiple API keys, so users can BYOD with their own credentials.
    
    Returns:
        Created BackendService or None if disabled/already exists
    """
    # Check if enabled
    platform_backends_str = get_setting('platform_backends_config')
    if not platform_backends_str:
        return None
    
    try:
        platform_backends = json.loads(platform_backends_str)
    except (json.JSONDecodeError, TypeError):
        return None
    
    if not platform_backends.get('netcup_platform_backend'):
        logger.info("Netcup platform backend disabled")
        return None
    
    # Get netcup_config
    netcup_config_str = get_setting('netcup_config')
    if not netcup_config_str:
        logger.warning("netcup_config not found, cannot create Netcup backend")
        return None
    
    try:
        netcup_config = json.loads(netcup_config_str)
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse netcup_config")
        return None
    
    # Validate required fields
    if not all(k in netcup_config for k in ['customer_id', 'api_key', 'api_password']):
        logger.warning("netcup_config missing required fields")
        return None
    
    # Check if service already exists
    existing = BackendService.query.filter_by(service_name='platform-netcup').first()
    if existing:
        logger.info("Platform Netcup backend already exists")
        return existing
    
    # Create platform BackendService
    service = create_backend_service(
        provider_code='netcup',
        service_name='platform-netcup',
        display_name='Platform Netcup',
        config=netcup_config,
        owner_type='platform',
        is_active=True,
    )
    
    logger.info("Created platform Netcup backend")
    return service


def setup_free_domains(backend_service: BackendService) -> list[ManagedDomainRoot]:
    """
    Create ManagedDomainRoot entries for free domains.
    
    Reads free_domains_config from database and creates public domain roots.
    
    Args:
        backend_service: Platform BackendService to link domains to
    
    Returns:
        List of created ManagedDomainRoot entries
    """
    free_domains_str = get_setting('free_domains_config')
    if not free_domains_str:
        logger.info("No free_domains_config found")
        return []
    
    try:
        free_domains_config = json.loads(free_domains_str)
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse free_domains_config")
        return []
    
    if not free_domains_config.get('enabled'):
        logger.info("Free domains feature disabled")
        return []
    
    domains = free_domains_config.get('domains', [])
    if not domains:
        logger.info("No free domains configured")
        return []
    
    created_roots = []
    for domain in domains:
        # Check if already exists
        existing = ManagedDomainRoot.query.filter_by(
            backend_service_id=backend_service.id,
            root_domain=domain
        ).first()
        
        if existing:
            logger.info(f"Domain root for {domain} already exists")
            continue
        
        # Create public domain root
        root = create_domain_root(
            backend_service=backend_service,
            root_domain=domain,
            dns_zone=domain,  # Assume zone name = domain name
            visibility='public',
            display_name=f"Free DDNS: {domain}",
            description=f"Public DDNS domain - users can create hosts under {domain} without approval",
            allowed_record_types=['A', 'AAAA', 'CNAME', 'TXT'],  # Common DDNS types
            allowed_operations=['read', 'create', 'update', 'delete'],
        )
        created_roots.append(root)
        logger.info(f"Created free domain root: {domain}")
    
    return created_roots


def initialize_platform_backends():
    """
    Main entry point for platform backend initialization.
    
    Processes:
    1. [[backends]] arrays - Creates BackendService entries
    2. [[domain_roots]] arrays - Creates ManagedDomainRoot entries
    3. [[users]] arrays - Creates preseeded Account entries
    
    Falls back to legacy [netcup]/[platform_backends]/[free_domains] structure.
    Safe to call multiple times - checks for existing entries.
    """
    logger.info("Initializing platform backends...")
    
    # Ensure backend providers are seeded
    seed_backend_providers()
    
    # Process NEW array-based structure (PREFERRED)
    backends_str = get_setting('backends_config')
    domain_roots_str = get_setting('domain_roots_config')
    users_str = get_setting('users_config')
    
    if backends_str or domain_roots_str or users_str:
        logger.info("Processing NEW array-based TOML structure")
        
        # Step 1: Process [[users]] arrays (must exist before user-owned backends)
        users_created = {}
        if users_str:
            try:
                users_config = json.loads(users_str)
                for user_data in users_config:
                    username = user_data.get('username', '')
                    email = user_data.get('email', '')
                    password = user_data.get('password', 'generate')
                    is_approved = user_data.get('is_approved', True)
                    must_change_password = user_data.get('must_change_password', False)
                    
                    # Check if user already exists
                    existing = Account.query.filter_by(username=username).first()
                    if existing:
                        logger.info(f"User {username} already exists")
                        users_created[username] = existing
                        continue
                    
                    # Generate password if needed
                    if password == 'generate':
                        from netcup_api_filter.utils import generate_token
                        password = generate_token(32)
                        logger.info(f"Generated password for {username}: {password} (SAVE THIS - shown once)")
                    
                    # Create user account
                    from netcup_api_filter.utils import hash_password
                    from netcup_api_filter.models import generate_user_alias
                    account = Account(
                        username=username,
                        user_alias=generate_user_alias(),  # Required field for token attribution
                        email=email,
                        password_hash=hash_password(password),
                        is_active=1 if is_approved else 0,  # is_approved maps to is_active
                        must_change_password=1 if must_change_password else 0,
                    )
                    db.session.add(account)
                    db.session.flush()  # Get ID before commit
                    users_created[username] = account
                    logger.info(f"Created preseeded user: {username} ({email})")
                
                db.session.commit()
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to parse users_config: {e}")
        
        # Step 2: Process [[backends]] arrays
        backends_created = {}
        if backends_str:
            try:
                backends_config = json.loads(backends_str)
                for backend_data in backends_config:
                    service_name = backend_data.get('service_name', '')
                    provider = backend_data.get('provider', '')
                    owner = backend_data.get('owner', 'platform')
                    display_name = backend_data.get('display_name', service_name)
                    config = backend_data.get('config', {})
                    
                    # Check if service already exists
                    existing = BackendService.query.filter_by(service_name=service_name).first()
                    if existing:
                        logger.info(f"Backend {service_name} already exists")
                        backends_created[service_name] = existing
                        continue
                    
                    # Process environment variable substitution in config
                    processed_config = {}
                    for key, value in config.items():
                        if isinstance(value, str):
                            # Handle ${ENV_VAR} substitution
                            if value.startswith('${') and value.endswith('}'):
                                env_var = value[2:-1]
                                value = os.environ.get(env_var, '')
                                if not value:
                                    logger.warning(f"Environment variable {env_var} not set for {service_name}.{key}")
                            # Handle "auto" URL detection for PowerDNS
                            elif value == 'auto' and key == 'api_url' and provider == 'powerdns':
                                value = get_powerdns_api_url()
                                logger.info(f"Auto-detected PowerDNS URL: {value}")
                        processed_config[key] = value
                    
                    # Determine owner type and account
                    if owner == 'platform':
                        owner_type = 'platform'
                        owner_account = None
                    else:
                        # User-owned backend
                        owner_account = users_created.get(owner) or Account.query.filter_by(username=owner).first()
                        if not owner_account:
                            logger.error(f"User {owner} not found for backend {service_name}, skipping")
                            continue
                        owner_type = 'user'
                    
                    # Create backend service
                    service = create_backend_service(
                        provider_code=provider,
                        service_name=service_name,
                        display_name=display_name,
                        config=processed_config,
                        owner_type=owner_type,
                        owner=owner_account,  # Pass Account object, not ID
                        is_active=True,
                    )
                    backends_created[service_name] = service
                    logger.info(f"Created backend: {service_name} ({provider}, owner={owner})")
                
                db.session.commit()
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to parse backends_config: {e}")
        
        # Step 3: Process [[domain_roots]] arrays
        if domain_roots_str:
            try:
                domain_roots_config = json.loads(domain_roots_str)
                for domain_data in domain_roots_config:
                    backend_name = domain_data.get('backend', '')
                    domain = domain_data.get('domain', '')
                    dns_zone = domain_data.get('dns_zone', domain)
                    visibility = domain_data.get('visibility', 'private')
                    display_name = domain_data.get('display_name', domain)
                    description = domain_data.get('description', '')
                    allow_apex_access = domain_data.get('allow_apex_access', False)
                    min_subdomain_depth = domain_data.get('min_subdomain_depth', 1)
                    max_subdomain_depth = domain_data.get('max_subdomain_depth', 3)
                    allowed_record_types = domain_data.get('allowed_record_types')
                    allowed_operations = domain_data.get('allowed_operations')
                    max_hosts_per_user = domain_data.get('max_hosts_per_user')
                    require_email_verification = domain_data.get('require_email_verification', False)
                    
                    # Find backend service
                    backend_service = backends_created.get(backend_name)
                    if not backend_service:
                        backend_service = BackendService.query.filter_by(service_name=backend_name).first()
                    
                    if not backend_service:
                        logger.error(f"Backend {backend_name} not found for domain {domain}, skipping")
                        continue
                    
                    # Check if domain root already exists
                    existing = ManagedDomainRoot.query.filter_by(
                        backend_service_id=backend_service.id,
                        root_domain=domain
                    ).first()
                    
                    if existing:
                        logger.info(f"Domain root {domain} already exists")
                        continue
                    
                    # Create domain root
                    root = create_domain_root(
                        backend_service=backend_service,
                        root_domain=domain,
                        dns_zone=dns_zone,
                        visibility=visibility,
                        display_name=display_name,
                        description=description,
                        allow_apex_access=allow_apex_access,
                        min_subdomain_depth=min_subdomain_depth,
                        max_subdomain_depth=max_subdomain_depth,
                        allowed_record_types=allowed_record_types,
                        allowed_operations=allowed_operations,
                    )
                    
                    # Set max_hosts_per_user if specified
                    if max_hosts_per_user is not None:
                        root.user_quotas = json.dumps({'max_hosts_per_user': max_hosts_per_user})
                    
                    # Set require_email_verification if specified
                    if require_email_verification:
                        root.require_email_verification = require_email_verification
                    
                    logger.info(f"Created domain root: {domain} (backend={backend_name}, visibility={visibility})")
                
                db.session.commit()
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to parse domain_roots_config: {e}")
        
        logger.info("✓ Platform backends initialized (NEW array-based structure)")
        return
    
    # LEGACY FALLBACK: Process old [netcup]/[platform_backends]/[free_domains] structure
    logger.info("Processing LEGACY TOML structure ([netcup], [platform_backends], [free_domains])")
    
    # Setup PowerDNS if enabled
    powerdns_service = setup_platform_powerdns()
    
    # Setup Netcup if enabled
    netcup_service = setup_platform_netcup()
    
    # Determine which backend to use for free domains
    backend_service = powerdns_service or netcup_service
    
    if not backend_service:
        logger.warning("No platform backend available for free domains")
        return
    
    # Setup free domains
    free_domain_roots = setup_free_domains(backend_service)
    
    logger.info(f"✓ Platform backends initialized (LEGACY): {len(free_domain_roots)} free domain(s)")


"""
Migration script to convert config.yaml to database
Idempotent - can be run multiple times safely
"""
import sys
import os
import yaml
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_config_to_db(config_file='config.yaml'):
    """
    Migrate configuration from YAML file to database
    
    Args:
        config_file: Path to config.yaml file
    """
    # Import Flask app components
    from flask import Flask
    from database import db, init_db, Client, SystemConfig, set_system_config
    from utils import hash_password, validate_domain
    
    # Create minimal Flask app for database context
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'migration-temp-key'
    
    # Initialize database
    init_db(app)
    
    with app.app_context():
        # Load YAML config
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_file}")
            return False
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            return False
        
        logger.info(f"Loaded configuration from {config_file}")
        
        # Migrate Netcup API configuration
        netcup_config = config.get('netcup', {})
        if netcup_config:
            existing_config = SystemConfig.query.filter_by(key='netcup_config').first()
            if existing_config:
                logger.info("Netcup config already exists in database, updating...")
            else:
                logger.info("Migrating Netcup API configuration...")
            
            set_system_config('netcup_config', {
                'customer_id': netcup_config.get('customer_id', ''),
                'api_key': netcup_config.get('api_key', ''),
                'api_password': netcup_config.get('api_password', ''),
                'api_url': netcup_config.get('api_url', 'https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON'),
                'timeout': netcup_config.get('timeout', 30)
            })
            logger.info("✓ Netcup configuration migrated")
        
        # Migrate tokens to clients
        tokens_config = config.get('tokens', [])
        if not tokens_config:
            logger.warning("No tokens found in configuration")
        else:
            logger.info(f"Migrating {len(tokens_config)} tokens...")
            
            for idx, token_config in enumerate(tokens_config):
                token = token_config.get('token')
                if not token:
                    logger.warning(f"Token #{idx+1} missing 'token' field, skipping")
                    continue
                
                # Check if client already exists with this token
                # We'll use the description as client_id if available, otherwise generate one
                description = token_config.get('description', '')
                client_id = description.replace(' ', '_').lower() if description else f'client_{idx+1}'
                
                # Check if already migrated
                existing_client = Client.query.filter_by(client_id=client_id).first()
                if existing_client:
                    logger.info(f"  - Client '{client_id}' already exists, skipping")
                    continue
                
                # Extract permissions
                permissions = token_config.get('permissions', [])
                if not permissions:
                    logger.warning(f"  - Token '{client_id}' has no permissions, skipping")
                    continue
                
                # Use first permission to determine realm
                # In the old config, each token could have multiple permissions
                # We'll convert the first one to the primary realm
                first_perm = permissions[0]
                domain = first_perm.get('domain', '')
                
                if not domain:
                    logger.warning(f"  - Token '{client_id}' has no domain, skipping")
                    continue
                
                # Determine realm type
                # If domain starts with *, treat as subdomain, otherwise as host
                if domain.startswith('*.'):
                    realm_type = 'subdomain'
                    realm_value = domain[2:]  # Remove *.
                elif '*' in domain:
                    # Wildcard pattern, treat as subdomain
                    realm_type = 'subdomain'
                    realm_value = domain.replace('*', '')
                else:
                    realm_type = 'host'
                    realm_value = domain
                
                # Get allowed record types from first permission
                record_types = first_perm.get('record_types', ['A', 'AAAA', 'CNAME', 'NS'])
                # Filter to only allowed types
                allowed_types = ['A', 'AAAA', 'CNAME', 'NS']
                record_types = [rt for rt in record_types if rt in allowed_types or rt == '*']
                if '*' in record_types:
                    record_types = allowed_types
                
                # Get allowed operations
                operations = first_perm.get('operations', ['read'])
                
                # Get allowed origins
                allowed_origins = token_config.get('allowed_origins', [])
                
                # Hash the token
                hashed_token = hash_password(token)
                
                # Create client
                client = Client(
                    client_id=client_id,
                    secret_token=hashed_token,
                    description=description,
                    realm_type=realm_type,
                    realm_value=realm_value,
                    is_active=1
                )
                
                client.set_allowed_record_types(record_types)
                client.set_allowed_operations(operations)
                
                if allowed_origins:
                    client.set_allowed_ip_ranges(allowed_origins)
                
                db.session.add(client)
                
                logger.info(f"  ✓ Migrated client '{client_id}' ({realm_type}: {realm_value})")
            
            # Commit all clients
            db.session.commit()
            logger.info(f"✓ All tokens migrated successfully")
        
        logger.info("\n" + "="*60)
        logger.info("Migration completed successfully!")
        logger.info("="*60)
        
        # Print summary
        total_clients = Client.query.count()
        active_clients = Client.query.filter_by(is_active=1).count()
        
        logger.info(f"\nDatabase Summary:")
        logger.info(f"  Total clients: {total_clients}")
        logger.info(f"  Active clients: {active_clients}")
        logger.info(f"  Database location: {db.engine.url}")
        
        logger.info(f"\nNext steps:")
        logger.info(f"  1. Review migrated clients in admin UI at /admin")
        logger.info(f"  2. Update client configurations as needed")
        logger.info(f"  3. Regenerate tokens for enhanced security")
        logger.info(f"  4. Consider backing up {config_file} and switching to database-only config")
        
        return True


if __name__ == '__main__':
    config_file = 'config.yaml'
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    
    success = migrate_config_to_db(config_file)
    sys.exit(0 if success else 1)

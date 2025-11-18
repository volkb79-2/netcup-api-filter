"""
Migration script to convert config.yaml to database
Idempotent - can be run multiple times safely
"""
import sys
import yaml
import logging

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
    from database import db, init_db, Client
    from bootstrap import seed_from_config
    
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
        
        if config:
            logger.info("Applying configuration to database via bootstrap.seeding...")
            seed_from_config(config)
            logger.info("✓ Configuration applied successfully")
        
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

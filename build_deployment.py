#!/usr/bin/env python3
"""
Build deployment package for netcup webhosting FTP-only deployment.

This script creates a ready-to-deploy package containing:
- All application files
- Vendored dependencies (no pip install needed)
- Pre-initialized SQLite database with default credentials from .env/.env.defaults
- DEPLOY_README.md with upload instructions
- .env.webhosting with initial deployment state

Output: deploy.zip and deploy.zip.sha256
"""

import os
import sys
import shutil
import subprocess
import tempfile
import zipfile
import hashlib
import logging
import json
import re
from datetime import datetime
from typing import Tuple
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


_APP_CONFIG_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _render_app_config_toml(raw_text: str) -> str:
    """Render ${VAR} placeholders using the current process environment.

    This is intentionally strict and fail-fast:
    - If app-config.toml contains ${VAR} and VAR is missing/empty in env, build fails.
    - This ensures the deployed app-config.toml is self-contained on webhosting
      (where devcontainer-only env vars like PUBLIC_FQDN are not present).
    """

    missing: set[str] = set()

    def repl(match: re.Match[str]) -> str:
        var_name = match.group(1)
        value = os.environ.get(var_name)
        if not value:
            missing.add(var_name)
            return match.group(0)
        return value

    rendered = _APP_CONFIG_ENV_PATTERN.sub(repl, raw_text)

    if missing:
        # Do not echo secrets; just names.
        raise RuntimeError(
            "app-config.toml contains unresolved placeholders: "
            + ", ".join(sorted(missing))
            + ". Ensure these are set in your environment (.env.workspace/.env/.env.defaults) before building."
        )

    return rendered


def create_directory_structure(deploy_dir):
    """Create the deployment directory structure."""
    logger.info("Creating deployment directory structure...")
    
    deploy_path = Path(deploy_dir)
    deploy_path.mkdir(exist_ok=True)
    
    vendor_dir = deploy_path / "vendor"
    vendor_dir.mkdir(exist_ok=True)
    
    return deploy_path, vendor_dir


def download_and_extract_dependencies(vendor_dir, requirements_file):
    """Download all dependencies and extract them to vendor directory."""
    logger.info("Downloading dependencies...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Download all packages as wheels
        logger.info(f"Running pip download for {requirements_file}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "download", 
             "-d", temp_dir, 
             "-r", requirements_file,
             "--only-binary", ":all:",
             "--python-version", "3.11",  # Match webhosting Python 3.11
             "--platform", "manylinux2014_x86_64",
             "--platform", "any"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.warning("Binary-only download failed, retrying with source packages...")
            # Retry without binary-only restriction
            result = subprocess.run(
                [sys.executable, "-m", "pip", "download",
                 "-d", temp_dir,
                 "-r", requirements_file],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to download dependencies: {result.stderr}")
                raise RuntimeError("Failed to download dependencies")
        
        logger.info(f"Downloaded packages to {temp_dir}")
        
        # Extract all wheel files to vendor directory
        logger.info("Extracting packages to vendor directory...")
        wheel_files = list(Path(temp_dir).glob("*.whl"))
        
        if not wheel_files:
            logger.error("No wheel files found after download")
            raise RuntimeError("No packages downloaded")
        
        logger.info(f"Found {len(wheel_files)} packages to extract")
        
        for wheel_file in wheel_files:
            logger.info(f"Extracting {wheel_file.name}...")
            with zipfile.ZipFile(wheel_file, 'r') as zip_ref:
                # Extract all files
                for member in zip_ref.namelist():
                    # Skip .dist-info directories and files
                    if '.dist-info/' in member:
                        continue
                    
                    # Extract to vendor directory
                    zip_ref.extract(member, vendor_dir)
        
        logger.info(f"Successfully extracted {len(wheel_files)} packages")


def copy_application_files(deploy_dir):
    """Copy all application files to deployment directory."""
    logger.info("Copying application files...")
    
    deploy_path = Path(deploy_dir)
    
    # Files to copy
    files_to_copy = [
        ("src/netcup_api_filter/passenger_wsgi.py", "passenger_wsgi.py"),
        # Env files copied temporarily for database seeding during build, then removed.
        # .env may contain secrets and must NEVER ship in deploy.zip.
        ".env.defaults",  # Defaults skeleton (may be used as fallback during seeding)
        ".env",  # Preferred env file (if present)
        "TROUBLESHOOTING.md",  # Comprehensive troubleshooting guide
        "DEBUG_QUICK_START.md",  # Quick debugging reference
        "READY_TO_DEPLOY.md",  # Instructions based on working hello world
        "DEBUG_404_ERROR.md",  # How to debug 404 errors with debug version
        ("src/netcup_api_filter/diagnostics/passenger_wsgi_hello.py", "passenger_wsgi_hello.py"),
    ]
    
    for entry in files_to_copy:
        if isinstance(entry, tuple):
            source_path, target_name = entry
        else:
            source_path = target_name = entry

        if os.path.exists(source_path):
            destination = deploy_path / target_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)
            logger.info(f"Copied {source_path} -> {target_name}")
    
    # Copy src tree (canonical application code)
    if os.path.exists("src"):
        shutil.copytree("src", deploy_path / "src", dirs_exist_ok=True)
        logger.info("Copied src directory")


def write_build_metadata(deploy_dir, client_id: str, secret_key: str, all_demo_clients: list):
    """Write build metadata (timestamp, git info) to deploy directory.
    
    NOTE: This file is deployed to webhosting and MUST NOT contain secrets.
    Secrets are stored separately in deployment_state_<target>.json in REPO_ROOT.
    
    Args:
        deploy_dir: Path to deployment directory
        client_id: (unused - kept for API compatibility)
        secret_key: (unused - kept for API compatibility)  
        all_demo_clients: (unused - kept for API compatibility)
    """
    logger.info("Recording build metadata (public, no secrets)...")

    def git_output(*args, default="unknown"):
        try:
            result = subprocess.run([
                "git", *args
            ], capture_output=True, text=True, check=True)
            return result.stdout.strip() or default
        except Exception:
            return default

    # Public build info only - NO SECRETS
    build_info = {
        "built_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "git_commit": git_output("rev-parse", "HEAD", default="unknown"),
        "git_short": git_output("rev-parse", "--short", "HEAD", default="unknown"),
        "git_branch": git_output("rev-parse", "--abbrev-ref", "HEAD", default="unknown"),
        "builder": os.environ.get("USER") or os.environ.get("USERNAME") or "unknown",
        "source": "build_deployment.py",
        # Count of clients for display purposes only
        "demo_client_count": len(all_demo_clients),
    }

    metadata_path = Path(deploy_dir) / "build_info.json"
    with open(metadata_path, "w", encoding="utf-8") as fh:
        json.dump(build_info, fh, indent=2)

    logger.info(
        "Build metadata written: commit %s @ %s",
        build_info["git_short"],
        build_info["built_at"],
    )


def _load_env_defaults() -> dict:
    """Load defaults from .env (preferred) or .env.defaults (fallback).

    This is used only for non-secret defaults needed at build time (e.g.,
    DEFAULT_ADMIN_USERNAME / DEFAULT_ADMIN_PASSWORD for fresh DB seeding).
    """
    defaults: dict[str, str] = {}

    candidate_paths = [Path(".env"), Path(".env.defaults")]
    env_path = next((p for p in candidate_paths if p.exists()), None)
    if env_path is None:
        raise RuntimeError(
            "Neither .env nor .env.defaults found. "
            "Create .env by copying .env.defaults and adding secrets/overrides."
        )

    with env_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            defaults[key.strip()] = value.strip()

    return defaults


def create_deployment_state(deploy_dir, client_id, secret_key, all_demo_clients, target="local"):
    """Create deployment state file with credentials in REPO_ROOT (not deployed).
    
    This file is the single source of truth for deployment state:
    - Build-time metadata (git info, timestamps)
    - Admin credentials (updated when passwords change)
    - Client credentials (for testing)
    
    IMPORTANT: This file is written to REPO_ROOT, NOT the deploy directory.
    It contains secrets and must NEVER be included in deploy.zip.
    
    Tests read this file FRESH each time to get the latest state.
    
    Args:
        deploy_dir: Deploy directory (used only to derive REPO_ROOT and deploy_path)
        client_id: Primary client ID
        secret_key: Primary client secret
        all_demo_clients: List of (client_id, secret, description) tuples
        target: Deployment target ("local" or "webhosting")
    """
    # State file goes in REPO_ROOT, named by target
    repo_root = Path(__file__).parent.absolute()
    state_filename = f"deployment_state_{target}.json"
    state_path = repo_root / state_filename
    
    logger.info(f"Creating {state_filename} in REPO_ROOT (contains secrets, not deployed)...")
    
    defaults = _load_env_defaults()
    
    def git_output(*args, default=""):
        """Run git command and return output."""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                capture_output=True, text=True, check=True
            )
            return result.stdout.strip() or default
        except Exception:
            return default
    
    admin_username = defaults.get('DEFAULT_ADMIN_USERNAME')
    admin_password = defaults.get('DEFAULT_ADMIN_PASSWORD')
    if not admin_username or not admin_password:
        raise RuntimeError(
            "DEFAULT_ADMIN_USERNAME/DEFAULT_ADMIN_PASSWORD not found in .env/.env.defaults. "
            "Check your env files before building a deployment."
        )

    # Build unified state structure
    state = {
        "target": target,
        "deploy_dir": str(Path(deploy_dir).absolute()),
        "build": {
            "built_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "git_commit": git_output("rev-parse", "--short", "HEAD", default="unknown"),
            "git_branch": git_output("rev-parse", "--abbrev-ref", "HEAD", default="unknown"),
            "builder": os.environ.get("USER") or os.environ.get("USERNAME") or "unknown",
            "source": "build_deployment.py",
        },
        "admin": {
            "username": admin_username,
            "password": admin_password,
            "password_changed_at": None,  # Set when password is changed
        },
        "clients": [
            {
                "client_id": cid,
                "secret_key": secret,
                "description": desc,
                "is_primary": (i == 0),  # First client is primary
            }
            for i, (cid, secret, desc) in enumerate(all_demo_clients)
        ],
        "last_updated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "updated_by": "build_deployment.py",
    }
    
    with open(state_path, 'w') as f:
        json.dump(state, f, indent=2)
    
    logger.info(f"Created {state_path}")
    return state


def create_initial_env_webhosting(deploy_dir):
    """Create .env.webhosting with initial deployment state from .env/.env.defaults.
    
    DEPRECATED: Use deployment_state.json instead.
    This file is kept for backward compatibility with existing test infrastructure.
    """
    logger.info("Creating initial .env.webhosting (legacy compatibility)...")
    
    defaults = _load_env_defaults()
    
    # Generate unique SECRET_KEY for this deployment if not already set
    import secrets
    secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    # Create .env.webhosting with deployment state
    env_webhosting_path = Path(deploy_dir) / ".env.webhosting"
    with open(env_webhosting_path, 'w') as f:
        f.write("# DEPRECATED: Use deployment_state.json instead\n")
        f.write("# Deployment state - updated by tests when passwords change\n\n")
        f.write(f"# Flask Secret Key (generated at build time)\n")
        f.write(f"SECRET_KEY={secret_key}\n\n")
        f.write(f"DEPLOYED_ADMIN_USERNAME={defaults.get('DEFAULT_ADMIN_USERNAME', '')}\n")
        f.write(f"DEPLOYED_ADMIN_PASSWORD={defaults.get('DEFAULT_ADMIN_PASSWORD', '')}\n")
        f.write(f"DEPLOYED_AT={datetime.utcnow().replace(microsecond=0).isoformat()}Z\n")
    
    logger.info(f"Created {env_webhosting_path} with initial deployment state (including SECRET_KEY)")


def initialize_database(deploy_dir, is_local: bool = False, seed_demo: bool = False) -> Tuple[str, str, list]:
    """Initialize SQLite database with default admin user and dynamically generated client credentials.
    
    Args:
        deploy_dir: Path to the deployment directory
        is_local: If True, seed email config for mock mode (Mailpit)
        seed_demo: If True, seed comprehensive demo data for UI screenshots
    
    Returns:
        Tuple of (client_id, secret_key, all_demo_clients)
        where all_demo_clients is list of (client_id, secret_key, description) tuples
    """
    logger.info("Initializing database...")
    if is_local:
        logger.info("Local deployment - will seed mock email config")
    
    # Save current directory
    original_dir = os.getcwd()
    
    # Temporarily add deploy directory to path to import modules
    deploy_path = Path(deploy_dir).resolve()
    src_path = deploy_path / "src"
    # Add src/ to path so netcup_api_filter package can be imported
    sys.path.insert(0, str(src_path))
    sys.path.insert(0, str(deploy_path))
    sys.path.insert(0, str(deploy_path / "vendor"))
    
    try:
        # Load service names from .env.services BEFORE changing directory
        # (file is in repo root, not deploy directory)
        # Use bash to evaluate the file since it contains bash syntax like ${VAR:-default}
        env_services_path = Path(original_dir) / ".env.services"
        if env_services_path.exists():
            try:
                # Source the file with bash and export all variables
                result = subprocess.run(
                    ['/bin/bash', '-c', f'set -a && source "{env_services_path}" && env'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                # Parse the output and set environment variables
                for line in result.stdout.split('\n'):
                    if '=' in line:
                        key, _, value = line.partition('=')
                        os.environ[key] = value
                
                logger.info(f"Loaded service names from .env.services (SERVICE_MAILPIT={os.environ.get('SERVICE_MAILPIT', 'mailpit')})")
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to load .env.services: {e}")
        else:
            logger.warning(f".env.services not found at {env_services_path}")
        
        # Set MOCK_SMTP_HOST to use dynamic service name
        # For local deployments, use the actual container name from .env.services
        if is_local and 'SERVICE_MAILPIT' in os.environ:
            os.environ['MOCK_SMTP_HOST'] = os.environ['SERVICE_MAILPIT']
            logger.info(f"Set MOCK_SMTP_HOST={os.environ['MOCK_SMTP_HOST']} for local deployment")
        elif is_local:
            # Fallback if .env.services not loaded
            os.environ['MOCK_SMTP_HOST'] = 'naf-dev-mailpit'
            logger.info(f"Set MOCK_SMTP_HOST={os.environ['MOCK_SMTP_HOST']} (fallback)")
        
        # Change to deploy directory so SQLite can create the database
        os.chdir(deploy_path)

        # Provide explicit deployment target for config-driven seeding.
        # This is consumed by netcup_api_filter.bootstrap.seeding.seed_settings_from_env().
        os.environ['DEPLOYMENT_TARGET'] = 'local' if is_local else 'webhosting'
        
        # Set database path (absolute path)
        db_path = deploy_path / "netcup_filter.db"
        os.environ['NETCUP_FILTER_DB_PATH'] = str(db_path)
        
        # Import required modules (netcup_api_filter is under src/)
        from flask import Flask
        from netcup_api_filter import database
        from netcup_api_filter.bootstrap import AdminSeedOptions, seed_default_entities, seed_comprehensive_demo_data
        
        # Create Flask app with template_folder in deploy directory
        app = Flask(__name__, template_folder=str(deploy_path / "src" / "netcup_api_filter" / "templates"))
        app.config['SECRET_KEY'] = 'build-temp-key'
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        # Initialize database
        database.db.init_app(app)
        
        generated_client_id = None
        generated_secret_key = None
        
        with app.app_context():
            # Create all tables
            database.db.create_all()
            logger.info("Database tables created")
            
            # Seed Settings table from env defaults (BEFORE seeding accounts)
            # This ensures rate limits and security settings are available immediately
            from netcup_api_filter.bootstrap.seeding import seed_settings_from_env
            seeded_count = seed_settings_from_env()
            if seeded_count > 0:
                logger.info(f"Seeded {seeded_count} settings from env defaults")

            # Seed with defaults - enable demo clients for comprehensive local testing
            # Demo clients provide multiple permission configurations for E2E tests
            generated_client_id, generated_secret_key, all_demo_clients = seed_default_entities(
                seed_demo_clients_flag=True,  # Enable demo clients with varied permissions
                seed_mock_email=is_local,  # Seed Mailpit config for local builds
            )
            # Seed comprehensive demo data if requested
            if seed_demo:
                from netcup_api_filter.models import Account
                admin = Account.query.filter_by(is_admin=1).first()
                if admin:
                    seed_comprehensive_demo_data(admin)
                    logger.info("Comprehensive demo data seeded for UI screenshots")
            
            logger.info(
                "Database seeded with default admin and %d demo clients (primary: %s)",
                len(all_demo_clients),
                generated_client_id,
            )
        
        logger.info(f"Database initialized at {db_path}")
        
        # Return primary credentials and all demo clients for build_info
        return generated_client_id, generated_secret_key, all_demo_clients
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise
    finally:
        # Restore original directory
        os.chdir(original_dir)
        
        # Clean up sys.path
        sys.path.remove(str(src_path))
        sys.path.remove(str(deploy_path))
        sys.path.remove(str(deploy_path / "vendor"))
    
    return generated_client_id, generated_secret_key, all_demo_clients


def create_deploy_readme(deploy_dir):
    """Create DEPLOY_README.md with deployment instructions."""
    logger.info("Creating DEPLOY_README.md...")
    
    readme_content = """# Netcup API Filter - Quick Deployment Guide

This package is ready for FTP-only deployment to netcup webhosting (or similar).
No command line access needed!

## What's Included

- ✅ All application files
- ✅ All Python dependencies (pre-installed in `vendor/` directory)
- ✅ Pre-initialized SQLite database with admin account
- ✅ This deployment guide

## 5-Step Deployment

### Step 1: Download the Package

You should already have `deploy.zip` - that's this package!

### Step 2: Upload via FTP/SFTP

1. Connect to your netcup webhosting via FTP/SFTP
   - Host: `ftp.yourdomain.com` or `ssh.webhosting-XXX.your-server.de`
   - Use your netcup webhosting credentials

2. Navigate to your domain directory (e.g., `/www/htdocs/w0123456/yourdomain.com/`)

3. Create a directory for the application (e.g., `netcup-filter/`)

4. Upload ALL files from `deploy.zip` to this directory
   - Make sure to upload the `vendor/` directory with all subdirectories
   - Make sure to upload the `templates/` directory
   - Upload all `.py` files
   - Upload `netcup_filter.db` file

### Step 3: Point Passenger to the app entrypoint

1. In the netcup control panel, open the Passenger configuration for your domain.
2. Set the **App Root** to the directory where you uploaded this package (e.g., `/www/htdocs/w0123456/yourdomain.com/netcup-api-filter`).
3. Ensure the startup file is `passenger_wsgi.py` (default). No `.htaccess` overrides are required.
4. To relocate the SQLite database, define `NETCUP_FILTER_DB_PATH` via the control panel's environment variables.

### Step 4: Access the Admin Interface

1. Open your browser and navigate to: `https://yourdomain.com/admin`
   (or `https://yourdomain.com/netcup-filter/admin` if installed in a subdirectory)

2. You should see the login page

### Step 5: Login and Configure

1. **Login with default credentials:**
   - Username: `admin`
   - Password: `admin`

2. **Change your password** (you'll be forced to do this on first login)

3. **Configure Netcup API credentials:**
   - Go to "Configuration" → "Netcup API"
   - Enter your Netcup customer ID, API key, and API password
   - Click "Save"

4. **Create API tokens:**
   - Go to "Management" → "Clients"
   - Click "Create" to add a new client
   - Configure permissions (realm, record types, operations)
   - Copy the generated token (shown only once!)

5. **Test the setup:**
   - Use the token to make an API request to your proxy endpoint
   - Check the audit logs in the admin interface

## Troubleshooting

### Problem: 500 Internal Server Error

**Solution:**
1. Check that all files were uploaded correctly
2. Verify the Passenger App Root in the control panel points to the uploaded directory
3. Check error logs (usually in `~/logs/error.log` or via control panel)
4. Ensure `netcup_filter.db` has correct permissions (readable/writable by web server)

### Problem: Admin page shows "Module not found" error

**Solution:**
1. Verify the entire `vendor/` directory was uploaded
2. Check that `passenger_wsgi.py` was uploaded
3. Verify PassengerPython points to correct Python interpreter

### Problem: Database errors

**Solution:**
1. Ensure `netcup_filter.db` file was uploaded
2. Check file permissions (should be readable/writable by web server user)
3. Verify directory is writable for SQLite journal files

### Problem: Cannot access admin interface

**Solution:**
1. Verify Passenger App Root and startup file match the uploaded directory
2. Try accessing root URL first: `https://yourdomain.com/`
3. Check that `templates/` directory with all HTML files was uploaded

## File Permissions

If using SFTP/SSH, set appropriate permissions:

```bash
chmod 755 /path/to/netcup-filter/
chmod 644 /path/to/netcup-filter/*.py
chmod 644 /path/to/netcup-filter/netcup_filter.db
chmod 755 /path/to/netcup-filter/vendor/
chmod 755 /path/to/netcup-filter/templates/
```

## Security Notes

1. **Change the default password immediately** after first login
2. **Protect sensitive files** - Use the hosting control panel to deny direct access to:
    - `netcup_filter.db` (database)
    - `.env` files
    - `*.log` files

3. **Use HTTPS** - Always access the admin interface over HTTPS

4. **Regular backups** - Backup your database file regularly:
   - Download `netcup_filter.db` via FTP
   - Store securely offline

## Next Steps

After successful deployment:

1. **Configure email notifications** (optional)
   - Go to "Configuration" → "Email Settings"
   - Enter SMTP details
   - Test email functionality

2. **Create additional admin users** (optional)
   - Go to "Management" → "Admin Users"

3. **Review security settings**
   - Check IP restrictions for tokens
   - Review audit logs regularly

4. **Read the documentation**
   - See README.md for detailed usage
   - See ADMIN_GUIDE.md for admin interface guide

## Support

For issues or questions:
- Check the GitHub repository: https://github.com/volkb79-2/netcup-api-filter
- Review WEBHOSTING_DEPLOYMENT.md for detailed deployment info
- Check netcup support for Passenger configuration help

## Package Information

This package was built with `build_deployment.py` and includes:
- Application version: Latest from repository
- Python dependencies: From requirements.txt
- Database: Pre-initialized SQLite with default admin account
- Configuration: Config-driven defaults from .env/.env.defaults

Enjoy using Netcup API Filter! 🚀
"""
    
    readme_path = Path(deploy_dir) / "DEPLOY_README.md"
    with open(readme_path, 'w') as f:
        f.write(readme_content)
    
    logger.info(f"Created {readme_path}")


def create_zip_package(deploy_dir, output_filename="deploy.zip"):
    """Create zip package and sha256 hash file."""
    logger.info(f"Creating deployment package: {output_filename}...")
    
    zip_path = output_filename
    deploy_path = Path(deploy_dir)
    
    # Remove old zip if exists
    if os.path.exists(zip_path):
        os.remove(zip_path)
        logger.info(f"Removed old {zip_path}")
    
    # Create zip file
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(deploy_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(deploy_path)
                zipf.write(file_path, arcname)
                
    zip_size = os.path.getsize(zip_path)
    logger.info(f"Created {zip_path} ({zip_size / (1024*1024):.2f} MB)")
    
    # Calculate SHA256 hash
    logger.info("Calculating SHA256 hash...")
    sha256_hash = hashlib.sha256()
    with open(zip_path, "rb") as f:
        while True:
            chunk = f.read(4096)
            if not chunk:
                break
            sha256_hash.update(chunk)
    
    hash_value = sha256_hash.hexdigest()
    
    # Write hash to file
    hash_file = f"{zip_path}.sha256"
    with open(hash_file, 'w') as f:
        f.write(f"{hash_value}  {zip_path}\n")
    
    logger.info(f"Created {hash_file}")
    logger.info(f"SHA256: {hash_value}")
    
    return zip_path, hash_file


def main():
    """Main build process."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Build deployment package")
    parser.add_argument("--output", default="deploy.zip", help="Output zip filename")
    parser.add_argument("--build-dir", default="deploy", help="Directory to build the package in")
    parser.add_argument("--local", action="store_true", help="Build for local testing (sets target=local)")
    parser.add_argument("--target", choices=["local", "webhosting"], default=None,
                        help="Deployment target (local or webhosting). --local sets this to 'local'")
    parser.add_argument("--seed-demo", action="store_true", 
                        help="Seed comprehensive demo data for UI screenshots")
    parser.add_argument("--bundle-app-config", action="store_true",
                        help="Include app-config.toml in deployment if it exists (WARNING: contains secrets)")
    args = parser.parse_args()
    
    # Determine deployment target
    if args.local:
        deployment_target = "local"
    elif args.target:
        deployment_target = args.target
    else:
        # Default based on build directory name
        deployment_target = "local" if "local" in args.build_dir else "webhosting"

    logger.info("=" * 60)
    logger.info("Netcup API Filter - Deployment Package Builder")
    logger.info(f"Target: {deployment_target}")
    logger.info("=" * 60)
    
    requirements_path = "./requirements.webhosting.txt"

    # Check if running from repository root
    if not os.path.exists(requirements_path):
        logger.error(f"{requirements_path} not found. Run this script from the repository root.")
        sys.exit(1)
    
    entrypoint_path = "src/netcup_api_filter/passenger_wsgi.py"
    if not os.path.exists(entrypoint_path):
        logger.error(f"{entrypoint_path} not found. Run this script from the repository root.")
        sys.exit(1)
    
    try:
        # Create deploy directory
        deploy_dir = args.build_dir
        if os.path.exists(deploy_dir):
            logger.info(f"Removing existing {deploy_dir} directory...")
            shutil.rmtree(deploy_dir)
        
        deploy_path, vendor_dir = create_directory_structure(deploy_dir)
        
        # Download and extract dependencies
        download_and_extract_dependencies(vendor_dir, requirements_path)
        
        # Copy application files
        copy_application_files(deploy_dir)
        
        # Initialize database and get generated credentials
        # For local builds, seed mock email config (Mailpit)
        is_local_build = deployment_target == "local"
        client_id, secret_key, all_demo_clients = initialize_database(deploy_dir, is_local=is_local_build, seed_demo=args.seed_demo)
        
        # Create unified deployment state (primary state file)
        create_deployment_state(deploy_dir, client_id, secret_key, all_demo_clients, target=deployment_target)

        # Record build metadata with generated credentials for runtime display
        # NOTE: build_info.json is deprecated, use deployment_state.json instead
        write_build_metadata(deploy_dir, client_id, secret_key, all_demo_clients)
        
        # Create deployment README
        create_deploy_readme(deploy_dir)
        
        # Remove env files from deployment package (database already seeded)
        # IMPORTANT: .env may contain secrets and must NEVER ship in deploy.zip.
        for env_name in (".env", ".env.defaults"):
            env_path = Path(deploy_dir) / env_name
            if env_path.exists():
                env_path.unlink()
                logger.info("Removed %s from deployment (database pre-seeded, config from env vars)", env_name)
        
        # Optionally bundle app-config.toml (contains secrets - opt-in only)
        if args.bundle_app_config:
            app_config_source = Path("app-config.toml")
            if app_config_source.exists():
                app_config_dest = Path(deploy_dir) / "app-config.toml"

                raw_text = app_config_source.read_text(encoding="utf-8")
                rendered = _render_app_config_toml(raw_text)
                app_config_dest.write_text(rendered, encoding="utf-8")

                logger.warning("⚠️  Bundled app-config.toml (contains secrets - handle carefully!)")
            else:
                logger.warning("--bundle-app-config specified but app-config.toml not found")
        
        # Create zip package
        zip_path, hash_file = create_zip_package(deploy_dir, args.output)
        
        logger.info("=" * 60)
        logger.info("✅ Deployment package built successfully!")
        logger.info("=" * 60)
        logger.info(f"Package: {zip_path}")
        logger.info(f"Hash file: {hash_file}")
        logger.info(f"Deploy directory: {deploy_dir}/")
        logger.info("")
        logger.info("Next steps:")
        logger.info(f"1. Download {zip_path}")
        logger.info("2. Extract and upload contents via FTP to your webhosting")
        logger.info("3. Access /admin and login with your seeded admin credentials")
        logger.info("4. Read DEPLOY_README.md for detailed instructions")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Build failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

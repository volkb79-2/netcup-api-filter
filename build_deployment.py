#!/usr/bin/env python3
"""
Build deployment package for netcup webhosting FTP-only deployment.

This script creates a ready-to-deploy package containing:
- All application files
- Vendored dependencies (no pip install needed)
- Pre-initialized SQLite database holding only the shipped admin (must_change_password)
- DEPLOY_README.md with upload instructions
- app-defaults.env (runtime defaults; no .env.defaults, no credentials)

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
from datetime import UTC, datetime
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


def _utc_now_iso() -> str:
    """UTC timestamp, seconds precision, 'Z' suffix.

    Equivalent to the old (deprecated) ``datetime.utcnow().replace(microsecond=0)
    .isoformat() + "Z"`` pattern, but built on the timezone-aware
    ``datetime.now(UTC)`` API.
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _assert_interpreter_matches_target(python_version: str | None) -> None:
    """Refuse to seed the database under a mismatched interpreter (naf-I03).

    ``download_and_extract_dependencies`` resolves target-ABI wheels via
    ``pip download --only-binary :all: --python-version <ver> --platform
    manylinux2014_x86_64``, which is safe under ANY host interpreter because it never
    executes the downloaded code. ``initialize_database`` is different: it puts
    ``vendor/`` on ``sys.path`` and IMPORTS the app (and therefore the vendored
    cp311/cp314 ``.so`` extensions) to seed the SQLite DB. If that import happens under
    a different interpreter than the one those wheels were resolved for,
    version-tagged C extensions are silently NOT import candidates at all (packages
    with a pure-Python fallback silently use it; C-only ones ImportError), and an
    abi3 extension (e.g. bcrypt) loads a wrong-version binary without complaint. Either
    way, seeding proves nothing about the real target closure.

    Pass ``python_version=None`` to skip this check entirely — for callers that seed a
    database with NO vendored cross-version wheels involved at all.
    """
    if python_version is None:
        return

    try:
        wanted = tuple(int(part) for part in python_version.split(".")[:2])
        if len(wanted) != 2:
            raise ValueError("expected MAJOR.MINOR")
    except ValueError as exc:
        raise RuntimeError(f"Invalid --python-version {python_version!r}: {exc}") from exc

    actual = sys.version_info[:2]
    if actual != wanted:
        raise RuntimeError(
            "Refusing to seed the database under a mismatched interpreter: this "
            f"process is running Python {actual[0]}.{actual[1]}, but --python-version "
            f"{python_version} was requested (vendor/ wheels were resolved for "
            f"cp{wanted[0]}{wanted[1]}). Seeding under the wrong interpreter makes "
            "version-tagged C extensions silently not import candidates and validates "
            "nothing about the target closure. Run build_deployment.py UNDER a "
            f"Python {python_version} interpreter — e.g. inside the matching "
            f"netcup-api-filter/test-runner:py{python_version.replace('.', '')} runner "
            "(`run-gate local-build` does this for the local build)."
        )


def create_directory_structure(deploy_dir):
    """Create the deployment directory structure."""
    logger.info("Creating deployment directory structure...")
    
    deploy_path = Path(deploy_dir)
    deploy_path.mkdir(exist_ok=True)
    
    vendor_dir = deploy_path / "vendor"
    vendor_dir.mkdir(exist_ok=True)
    
    return deploy_path, vendor_dir


def download_and_extract_dependencies(
    vendor_dir,
    requirements_file,
    python_version="3.11",
    allow_unsafe_sdist_fallback=False,
):
    """Download all dependencies and extract them to vendor directory."""
    logger.info(f"Downloading dependencies (target Python {python_version})...")

    with tempfile.TemporaryDirectory() as temp_dir:
        # Download all packages as wheels
        logger.info(f"Running pip download for {requirements_file}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "download",
             "-d", temp_dir,
             "-r", requirements_file,
             "--only-binary", ":all:",
             "--python-version", python_version,
             "--platform", "manylinux2014_x86_64",
             "--platform", "any"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            logger.warning(
                f"Binary-only download failed for Python {python_version} "
                f"(manylinux2014_x86_64). pip stderr:\n{result.stderr}"
            )

            if not allow_unsafe_sdist_fallback:
                raise RuntimeError(
                    f"No binary (manylinux2014_x86_64) wheel available for one or more "
                    f"dependencies in {requirements_file} for Python {python_version}. "
                    "Refusing to fall back to sdist: sdists are built by "
                    f"{sys.executable!r} — i.e. the HOST interpreter running this "
                    "script, NOT the --python-version target — and would silently "
                    "poison this vendor/ tree with wrong-ABI artifacts. Either add a "
                    "version constraint that resolves to a wheel-having release, or "
                    "pass --allow-unsafe-sdist-fallback to opt in explicitly (only "
                    "safe when the host interpreter genuinely matches the target)."
                )

            # Opted in explicitly: every occurrence of this fallback is unsafe by
            # construction (sdists build against the HOST interpreter, not
            # --python-version), so the warning always fires here — no more
            # `if python_version != "3.11"` gate that silently hid it for the
            # single most common target.
            logger.warning(
                f"UNSAFE sdist fallback opted in (--allow-unsafe-sdist-fallback) for "
                f"target Python {python_version}: sdists are built for the HOST "
                f"Python running this script ({sys.version_info.major}."
                f"{sys.version_info.minor}), not the target. Cross-version source "
                "builds may produce wrong-version artifacts."
            )
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


def write_build_metadata(deploy_dir):
    """Write build metadata (timestamp, git info) to deploy directory.
    
    NOTE: This file is deployed to webhosting and MUST NOT contain secrets.
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
        "built_at": _utc_now_iso(),
        "git_commit": git_output("rev-parse", "HEAD", default="unknown"),
        "git_short": git_output("rev-parse", "--short", "HEAD", default="unknown"),
        "git_branch": git_output("rev-parse", "--abbrev-ref", "HEAD", default="unknown"),
        "builder": os.environ.get("USER") or os.environ.get("USERNAME") or "unknown",
        # naf-I03: the local image ID (`docker image inspect --format='{{.Id}}'`) of
        # the test-runner container build_deployment.py ran inside, stamped by
        # the ciu runner (docker exec) via NAF_BUILDER_IMAGE_DIGEST.
        # These images are never pushed to a registry, so there is no RepoDigest —
        # the content-addressed local image ID is the strongest provenance available.
        # "unknown" for non-containerized runs (e.g. local target, or a bare CLI
        # invocation outside the managed build path).
        "builder_image_digest": os.environ.get("NAF_BUILDER_IMAGE_DIGEST", "unknown"),
        "source": "build_deployment.py",
    }

    metadata_path = Path(deploy_dir) / "build_info.json"
    with open(metadata_path, "w", encoding="utf-8") as fh:
        json.dump(build_info, fh, indent=2)

    logger.info(
        "Build metadata written: commit %s @ %s",
        build_info["git_short"],
        build_info["built_at"],
    )


def _local_service_var(name: str) -> str:
    """Service value of a LOCAL build: *name* from the environment, else from .env.services.

    .env.services is bash syntax (``${VAR:-default}``), so it is evaluated by bash into a
    dict; this process's environment is never modified. Missing or empty is an error.
    """
    value = os.environ.get(name, "").strip()
    if value:
        return value
    services = Path(".env.services")
    if not services.is_file():
        raise RuntimeError(f"{name} is not set and .env.services is missing")
    result = subprocess.run(
        ["/bin/bash", "-c", f'set -a && source "{services}" >/dev/null && printf %s "${{{name}:-}}"'],
        capture_output=True, text=True, check=True,
    )
    value = result.stdout.strip()
    if not value:
        raise RuntimeError(f"{name} is empty after evaluating {services}")
    return value


def _mailpit_host() -> str:
    """Resolved Mailpit container identity supplied by `.env.services`."""
    return _local_service_var("MAILPIT_HOST")


def _local_mock_email():
    """Mailpit email config of a LOCAL build: host per _mailpit_host, rest from the defaults catalog."""
    from netcup_api_filter.bootstrap import MockEmail
    from netcup_api_filter.config_defaults import require_default

    return MockEmail(
        smtp_host=_mailpit_host(),
        smtp_port=int(require_default("LOCAL_MAILPIT_SMTP_PORT")),
        from_email=require_default("LOCAL_MAIL_FROM"),
        admin_email=require_default("LOCAL_MAIL_ADMIN_EMAIL"),
    )


def _local_mock_netcup():
    """Mock Netcup backend of a LOCAL build: URL from MOCK_NETCUP_API_URL, rest from the defaults catalog."""
    from netcup_api_filter.bootstrap import MockNetcup
    from netcup_api_filter.config_defaults import require_default

    base = _local_service_var("MOCK_NETCUP_API_URL").rstrip("/")
    return MockNetcup(
        api_url=f"{base}/run/webservice/servers/endpoint.php",
        customer_id=require_default("LOCAL_MOCK_NETCUP_CUSTOMER_ID"),
        api_key=require_default("LOCAL_MOCK_NETCUP_API_KEY"),
        api_password=require_default("LOCAL_MOCK_NETCUP_API_PASSWORD"),
        timeout=int(require_default("LOCAL_MOCK_NETCUP_TIMEOUT")),
    )


def initialize_database(
    deploy_dir,
    is_local: bool = False,
    seed_demo: bool = False,
    python_version: str | None = None,
) -> None:
    """Initialize the deploy tree's SQLite database with the shipped content only.

    Args:
        deploy_dir: Path to the deployment directory
        is_local: If True, seed email config for mock mode (Mailpit)
        seed_demo: If True, seed comprehensive demo data for UI screenshots
        python_version: Expected "MAJOR.MINOR" of the RUNNING interpreter (naf-I03
            host-vs-target guard). Pass the same value used to resolve vendor/'s
            wheels; None skips the check (see _assert_interpreter_matches_target).
    """
    logger.info("Initializing database...")
    _assert_interpreter_matches_target(python_version)
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
        # Resolved against the repo root, i.e. BEFORE the chdir below.
        mock_email = _local_mock_email() if is_local else None
        mock_netcup = _local_mock_netcup() if is_local else None

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
        from netcup_api_filter.bootstrap import seed_shipped_database, seed_comprehensive_demo_data
        
        # Create Flask app with template_folder in deploy directory
        app = Flask(__name__, template_folder=str(deploy_path / "src" / "netcup_api_filter" / "templates"))
        app.config['SECRET_KEY'] = 'build-temp-key'
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        # Initialize database
        database.db.init_app(app)
        
        with app.app_context():
            # Create all tables
            database.db.create_all()
            logger.info("Database tables created")
            
            # The one shipped-database seeder: enums/providers, default settings,
            # the pre-set admin and (local only) the Mailpit email config and the mock Netcup backend.
            admin = seed_shipped_database(mock_email=mock_email, mock_netcup=mock_netcup)
            # Seed comprehensive demo data if requested
            if seed_demo:
                seed_comprehensive_demo_data(admin)
                logger.info("Comprehensive demo data seeded for UI screenshots")
            
            logger.info("Database seeded with the shipped admin (must_change_password)")
        
        logger.info(f"Database initialized at {db_path}")
        
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
    parser.add_argument("--python-version", default="3.11",
                        help="Target Python version for vendored wheel download (default: 3.11). "
                             "Cross-resolves binary wheels for the given version via pip download. "
                             "Example: --python-version 3.11 produces a 3.11-compatible vendor/ dir.")
    parser.add_argument("--seed-demo", action="store_true",
                        help="Seed comprehensive demo data for UI screenshots")
    parser.add_argument("--bundle-app-config", action="store_true",
                        help="Include app-config.toml in deployment if it exists (WARNING: contains secrets)")
    parser.add_argument("--allow-unsafe-sdist-fallback", action="store_true",
                        help="If binary wheel resolution fails for --python-version, fall back to "
                             "downloading sdists (built by the HOST interpreter running this script, "
                             "NOT the target). UNSAFE for cross-version builds; off by default so a "
                             "missing wheel fails loudly instead of silently poisoning vendor/.")
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
    logger.info(f"Python: {args.python_version}")
    logger.info("=" * 60)
    
    requirements_path = "./requirements-runtime.txt"

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
        download_and_extract_dependencies(
            vendor_dir,
            requirements_path,
            python_version=args.python_version,
            allow_unsafe_sdist_fallback=args.allow_unsafe_sdist_fallback,
        )

        # Copy application files
        copy_application_files(deploy_dir)

        # Initialize database and get generated credentials
        # For local builds, seed mock email config (Mailpit)
        # python_version=args.python_version enforces the naf-I03 host-vs-target guard:
        # this process MUST be running under the same interpreter that vendor/'s wheels
        # were resolved for, or seeding is refused (see _assert_interpreter_matches_target).
        is_local_build = deployment_target == "local"
        initialize_database(
            deploy_dir,
            is_local=is_local_build,
            seed_demo=args.seed_demo,
            python_version=args.python_version,
        )
        
        # Record public build metadata (no secrets).
        write_build_metadata(deploy_dir)
        
        # Create deployment README
        create_deploy_readme(deploy_dir)
        
        # Ship the runtime defaults catalog (allowlisted runtime keys of .env.defaults), then
        # remove the env files (database already seeded). .env may contain secrets and
        # .env.defaults holds the pre-set admin password: neither may ship.
        from netcup_api_filter.config_defaults import write_shipped_defaults
        write_shipped_defaults(Path(".env.defaults"), Path(deploy_dir))
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

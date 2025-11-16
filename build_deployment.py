#!/usr/bin/env python3
"""
Build deployment package for netcup webhosting FTP-only deployment.

This script creates a ready-to-deploy package containing:
- All application files
- Vendored dependencies (no pip install needed)
- Pre-initialized SQLite database with admin/admin credentials
- .htaccess configuration file
- DEPLOY_README.md with upload instructions

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
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
             "--python-version", "39",  # Target Python 3.9+ for compatibility
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
        "filter_proxy.py",
        "netcup_client.py",
        "access_control.py",
        "database.py",
        "admin_ui.py",
        "audit_logger.py",
        "email_notifier.py",
        "utils.py",
        "passenger_wsgi.py",
        "wsgi.py",
        "cgi_handler.py",
        "generate_token.py",
        "migrate_yaml_to_db.py",
        "example_client.py",
        "requirements.txt",
        "config.example.yaml",
        ".env.example",
    ]
    
    for file_name in files_to_copy:
        if os.path.exists(file_name):
            shutil.copy2(file_name, deploy_path / file_name)
            logger.info(f"Copied {file_name}")
    
    # Copy templates directory
    if os.path.exists("templates"):
        shutil.copytree("templates", deploy_path / "templates", dirs_exist_ok=True)
        logger.info("Copied templates directory")


def initialize_database(deploy_dir):
    """Create and initialize SQLite database with admin user."""
    logger.info("Initializing database...")
    
    # Save current directory
    original_dir = os.getcwd()
    
    # Temporarily add deploy directory to path to import modules
    deploy_path = Path(deploy_dir).resolve()
    sys.path.insert(0, str(deploy_path))
    sys.path.insert(0, str(deploy_path / "vendor"))
    
    try:
        # Change to deploy directory so SQLite can create the database
        os.chdir(deploy_path)
        
        # Set database path (absolute path)
        db_path = deploy_path / "netcup_filter.db"
        os.environ['NETCUP_FILTER_DB_PATH'] = str(db_path)
        
        # Import required modules
        from flask import Flask
        from database import db, AdminUser, init_db
        from utils import hash_password
        
        # Create Flask app with template_folder in deploy directory
        app = Flask(__name__, template_folder=str(deploy_path / "templates"))
        app.config['SECRET_KEY'] = 'build-temp-key'
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        # Initialize database
        db.init_app(app)
        
        with app.app_context():
            # Create all tables
            db.create_all()
            logger.info("Database tables created")
            
            # Create admin user with admin/admin credentials
            admin = AdminUser.query.filter_by(username='admin').first()
            if not admin:
                admin = AdminUser(
                    username='admin',
                    password_hash=hash_password('admin'),
                    must_change_password=1
                )
                db.session.add(admin)
                db.session.commit()
                logger.info("Admin user created (username: admin, password: admin)")
            else:
                logger.info("Admin user already exists")
        
        logger.info(f"Database initialized at {db_path}")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise
    finally:
        # Restore original directory
        os.chdir(original_dir)
        
        # Clean up sys.path
        sys.path.remove(str(deploy_path))
        sys.path.remove(str(deploy_path / "vendor"))


def create_htaccess(deploy_dir):
    """Create .htaccess configuration file."""
    logger.info("Creating .htaccess file...")
    
    htaccess_content = """# .htaccess for Phusion Passenger deployment
# Netcup API Filter

# Enable Passenger
PassengerEnabled on

# IMPORTANT: Edit this line with your actual path
PassengerAppRoot /path/to/your/domain/netcup-filter

# Python configuration (edit if needed)
PassengerPython /path/to/your/domain/netcup-filter/venv/bin/python3
PassengerStartupFile passenger_wsgi.py
PassengerAppType wsgi

# Optional: Set environment variables
# SetEnv NETCUP_FILTER_DB_PATH /path/to/your/domain/netcup-filter/netcup_filter.db

# Protect sensitive files
<FilesMatch "^(config\\.yaml|\\.env|netcup_filter\\.db|.*\\.log)$">
    Require all denied
</FilesMatch>

# Allow admin UI access
<Location /admin>
    Require all granted
</Location>

# Security headers
<IfModule mod_headers.c>
    Header set X-Content-Type-Options "nosniff"
    Header set X-Frame-Options "SAMEORIGIN"
    Header set X-XSS-Protection "1; mode=block"
</IfModule>
"""
    
    htaccess_path = Path(deploy_dir) / ".htaccess"
    with open(htaccess_path, 'w') as f:
        f.write(htaccess_content)
    
    logger.info(f"Created {htaccess_path}")


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
- ✅ Ready-to-use `.htaccess` configuration
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
   - Upload `.htaccess` file
   - Upload `netcup_filter.db` file

### Step 3: Edit .htaccess

Open `.htaccess` in your FTP client's editor (or download, edit, re-upload):

**Find these lines:**
```apache
PassengerAppRoot /path/to/your/domain/netcup-filter
PassengerPython /path/to/your/domain/netcup-filter/venv/bin/python3
```

**Replace with your actual paths:**
```apache
PassengerAppRoot /www/htdocs/w0123456/yourdomain.com/netcup-filter
PassengerPython /usr/bin/python3
```

**Note:** 
- Replace `w0123456` with your actual webhosting ID
- Replace `yourdomain.com` with your actual domain
- For PassengerPython, use the system Python (typically `/usr/bin/python3`)
- Do NOT use a venv path since we're using vendored dependencies

**Optional:** If you want the database in a different location:
```apache
SetEnv NETCUP_FILTER_DB_PATH /full/path/to/netcup_filter.db
```

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
2. Verify `.htaccess` paths are correct
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
1. Check that `.htaccess` file was uploaded
2. Verify PassengerAppRoot path is correct
3. Try accessing root URL first: `https://yourdomain.com/`
4. Check that `templates/` directory with all HTML files was uploaded

## File Permissions

If using SFTP/SSH, set appropriate permissions:

```bash
chmod 755 /path/to/netcup-filter/
chmod 644 /path/to/netcup-filter/*.py
chmod 644 /path/to/netcup-filter/.htaccess
chmod 644 /path/to/netcup-filter/netcup_filter.db
chmod 755 /path/to/netcup-filter/vendor/
chmod 755 /path/to/netcup-filter/templates/
```

## Security Notes

1. **Change the default password immediately** after first login
2. **Protect sensitive files** - The .htaccess includes rules to block access to:
   - `netcup_filter.db` (database)
   - `config.yaml` (if you create one)
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
- Configuration: Ready-to-use .htaccess template

Enjoy using Netcup API Filter! 🚀
"""
    
    readme_path = Path(deploy_dir) / "DEPLOY_README.md"
    with open(readme_path, 'w') as f:
        f.write(readme_content)
    
    logger.info(f"Created {readme_path}")


def create_zip_package(deploy_dir):
    """Create deploy.zip and deploy.zip.sha256."""
    logger.info("Creating deployment package...")
    
    zip_path = "deploy.zip"
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
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    
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
    logger.info("=" * 60)
    logger.info("Netcup API Filter - Deployment Package Builder")
    logger.info("=" * 60)
    
    # Check if running from repository root
    if not os.path.exists("requirements.txt"):
        logger.error("requirements.txt not found. Run this script from the repository root.")
        sys.exit(1)
    
    if not os.path.exists("passenger_wsgi.py"):
        logger.error("passenger_wsgi.py not found. Run this script from the repository root.")
        sys.exit(1)
    
    try:
        # Create deploy directory
        deploy_dir = "deploy"
        if os.path.exists(deploy_dir):
            logger.info(f"Removing existing {deploy_dir} directory...")
            shutil.rmtree(deploy_dir)
        
        deploy_path, vendor_dir = create_directory_structure(deploy_dir)
        
        # Download and extract dependencies
        download_and_extract_dependencies(vendor_dir, "requirements.txt")
        
        # Copy application files
        copy_application_files(deploy_dir)
        
        # Initialize database
        initialize_database(deploy_dir)
        
        # Create .htaccess
        create_htaccess(deploy_dir)
        
        # Create deployment README
        create_deploy_readme(deploy_dir)
        
        # Create zip package
        zip_path, hash_file = create_zip_package(deploy_dir)
        
        logger.info("=" * 60)
        logger.info("✅ Deployment package built successfully!")
        logger.info("=" * 60)
        logger.info(f"Package: {zip_path}")
        logger.info(f"Hash file: {hash_file}")
        logger.info(f"Deploy directory: {deploy_dir}/")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Download deploy.zip")
        logger.info("2. Extract and upload contents via FTP to your webhosting")
        logger.info("3. Edit .htaccess with your actual paths")
        logger.info("4. Access /admin and login with admin/admin")
        logger.info("5. Read DEPLOY_README.md for detailed instructions")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Build failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

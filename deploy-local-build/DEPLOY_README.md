# Netcup API Filter - Quick Deployment Guide

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
- Configuration: Config-driven defaults from .env.defaults

Enjoy using Netcup API Filter! 🚀

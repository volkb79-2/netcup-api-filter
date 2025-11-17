#!/bin/bash
# Cleanup script - removes old/legacy UI files

echo "Cleaning up legacy files..."

# Remove old root HTML files (Flask-Admin generated)
rm -f change_password.html
rm -f clients.html  
rm -f dashboard.html
rm -f email_config.html
rm -f netcup_config.html
rm -f netcup_config_full.html
rm -f system_info.html

# Remove old CSS files (replaced by app.css)
rm -f static/css/unified-dark.css
rm -f static/css/admin-dark.css
rm -f static/css/client-portal.css

# Remove old template files
rm -f templates/base.html
rm -f templates/admin/login.html
rm -f templates/admin/index.html
rm -f templates/admin/change_password.html
rm -f templates/admin/master.html
rm -f templates/admin/netcup_config.html
rm -f templates/admin/email_config.html
rm -f templates/admin/system_info.html
rm -f templates/client/layout.html
rm -f templates/client/login.html
rm -f templates/client/dashboard.html
rm -f templates/client/domain_detail.html
rm -f templates/client/record_form.html
rm -f templates/client/activity.html

echo "Legacy files removed."
echo "New modern UI is active!"

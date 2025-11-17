#!/bin/bash
# Upload simple debug version to server

echo "Uploading passenger_wsgi_simple_debug.py to server..."

scp passenger_wsgi_simple_debug.py \
    hosting218629@hosting218629.ae98d.netcup.net:/netcup-api-filter/

echo ""
echo "✅ File uploaded!"
echo ""
echo "Next steps:"
echo "1. Go to Control Panel → Python settings"
echo "2. Change 'Startup Datei' to: passenger_wsgi_simple_debug.py"
echo "3. Click 'Konfiguration neu schreiben'"
echo "4. Click 'Anwendung Neuladen'"
echo "5. Visit https://hosting.vxxu.de/netcup-api-filter"
echo ""
echo "You should see either:"
echo "  - The working admin interface, OR"
echo "  - A detailed error page showing what failed"
echo ""
echo "Also check the file: startup_error.txt in your app directory"

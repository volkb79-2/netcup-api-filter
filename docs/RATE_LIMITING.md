# Rate Limiting Configuration

## Overview

Rate limiting protects the application from abuse by restricting the number of requests per time period. The system uses a **three-tier configuration hierarchy** to support both traditional hosting environments and development/testing scenarios.

## Configuration Hierarchy

Rate limits are applied in this order of priority:

1. **Database Settings** (Highest Priority)
   - Managed via Admin UI → System Info → Security Settings
   - Stored in `settings` table
   - Editable at runtime without code changes
   - **Requires application restart** to take effect

2. **Environment Variables** (Medium Priority)
   - Set via `.env.defaults` or deployment environment
   - Used when no database setting exists
   - Examples:
     ```bash
     ADMIN_RATE_LIMIT=10 per minute
     ACCOUNT_RATE_LIMIT=10 per minute
     API_RATE_LIMIT=60 per minute
     ```

3. **Hardcoded Defaults** (Lowest Priority)
   - Fallback values in code
   - Only used if neither database nor environment has values
   - Default: `10 per minute` for admin/account, `60 per minute` for API

## Format

Rate limits use the format: `"X per Y"` where:
- **X** = Number of requests
- **Y** = Time period (`minute`, `hour`, or `day`)

Examples:
- `10 per minute` - 10 requests per minute
- `100 per hour` - 100 requests per hour
- `1000 per day` - 1000 requests per day

## Default Values

From `.env.defaults`:
```bash
ADMIN_RATE_LIMIT=10 per minute
ACCOUNT_RATE_LIMIT=10 per minute
API_RATE_LIMIT=60 per minute
```

## Editing via Admin UI

1. Navigate to **Admin → Config → System Info**
2. Scroll to **Security Settings** card
3. Edit rate limit values:
   - **Admin Portal**: Rate limit for `/admin/*` routes
   - **Account Portal**: Rate limit for `/account/*` routes
   - **API Endpoints**: Rate limit for `/api/*` routes
4. Click **Save Security Settings**
5. **Restart application** for changes to take effect

### Why Restart is Required

Flask-Limiter applies rate limits at application startup. Runtime changes to the database settings won't affect already-initialized limiters. On Passenger-based webhosting:

```bash
# SSH into server
ssh hosting218629@hosting218629.ae98d.netcup.net

# Restart application
touch /netcup-api-filter/tmp/restart.txt
```

## Deployment

### Webhosting (Passenger)

1. **Initial deployment** uses values from `.env.defaults`
2. **Database seeding** copies these values to `settings` table
3. Admin can modify via UI
4. Changes persist across deployments (database is not overwritten)
5. Restart required after changing settings

### Local Development

Rate limits respect the same hierarchy:
1. Check database settings first
2. Fall back to environment variables
3. Use hardcoded defaults last

For local testing, set `FLASK_ENV=local_test` to disable rate limiting entirely.

## Security Considerations

- **Conservative defaults**: Start with low limits (10/min) and increase based on usage patterns
- **Monitor logs**: Watch for legitimate users hitting limits
- **Separate limits**: Admin and account portals have different limits to prevent admin lockout
- **API limits**: Higher default (60/min) for programmatic access
- **Testing**: Always test limit changes in staging before production

## Troubleshooting

### Rate Limit Not Applied

1. Check database value: `SELECT * FROM settings WHERE key LIKE '%rate_limit%'`
2. Check environment variables: `echo $ADMIN_RATE_LIMIT`
3. Check application logs for rate limit initialization message
4. Verify application was restarted after changing settings

### Users Getting Rate Limited

1. Review audit logs for affected users
2. Check if limit is too conservative
3. Consider increasing limit or implementing IP whitelisting
4. Check for automated tools/scripts causing excessive requests

### Format Errors

Invalid format will cause application startup failure. Always use:
- Correct format: `"X per minute|hour|day"`
- No quotes in database storage
- Spaces between components
- Valid time units only

## Code Reference

- **Configuration loading**: `src/netcup_api_filter/app.py` lines 155-195
- **Admin UI**: `src/netcup_api_filter/templates/admin/system_info.html`
- **Backend handler**: `src/netcup_api_filter/api/admin.py` - `update_security_settings()`
- **Database schema**: `src/netcup_api_filter/models.py` - `Setting` model

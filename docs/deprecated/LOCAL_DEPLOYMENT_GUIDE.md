# Local Deployment Guide

> **Status:** Archived walkthrough. Use `OPERATIONS_GUIDE.md` for the up-to-date local deployment steps.

## Overview

**YES**, you can already run **complete tests including mocked services** locally! The infrastructure is fully set up.

## Architecture Comparison

### Webhosting Deployment (Production)
```
┌─────────────────────────────────────┐
│ Netcup Webhosting                   │
│ https://naf.vxxu.de                 │
│                                     │
│ passenger_wsgi.py                   │
│  ├─ Real database mode              │
│  ├─ Admin UI (Flask-Admin)          │
│  ├─ Client Portal                   │
│  ├─ Filter Proxy                    │
│  └─ Real Netcup API client          │
│                                     │
│ Database: netcup_filter.db          │
└─────────────────────────────────────┘
```

### Local Deployment (Development/Testing)
```
┌─────────────────────────────────────────────────────────┐
│ Local Docker Network: naf-local                          │
│                                                          │
│ ┌──────────────────┐   ┌───────────────────────────┐   │
│ │ Devcontainer     │   │ Nginx TLS Proxy           │   │
│ │                  │   │ https://naf.localtest.me  │   │
│ │ Gunicorn         │◄──┤ or custom domain          │   │
│ │ :5100            │   │ (Let's Encrypt certs)     │   │
│ │                  │   └───────────────────────────┘   │
│ │ local_app.py     │                                   │
│ │  ├─ Database mode│   ┌───────────────────────────┐   │
│ │  ├─ Admin UI     │   │ Playwright Container      │   │
│ │  ├─ Client Portal│   │                           │   │
│ │  ├─ Filter Proxy │   │ Mock Netcup API :5555    │   │
│ │  └─ FAKE Netcup  │◄──┤ Mock SMTP :1025          │   │
│ │                  │   │                           │   │
│ │ Database:        │   │ Browser automation        │   │
│ │ tmp/local.db     │   │ Test runner              │   │
│ └──────────────────┘   └───────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Key Differences: Local vs Webhosting

### 1. **Database Location**
- **Webhosting**: `/netcup-api-filter/netcup_filter.db` (persistent)
- **Local**: `tmp/local-netcup.db` (ephemeral, reseeded each run)

### 2. **Netcup Client**
- **Webhosting**: Real `NetcupClient` connecting to Netcup CCP API
  ```python
  # passenger_wsgi.py
  netcup_config = get_system_config('netcup_config')
  app.config['netcup_client'] = NetcupClient(
      customer_id=netcup_config.get('customer_id'),
      api_key=netcup_config.get('api_key'),
      api_password=netcup_config.get('api_password'),
      api_url='https://ccp.netcup.net/...'
  )
  ```

- **Local**: Fake `FakeNetcupClient` returning mock data
  ```python
  # local_app.py
  class FakeNetcupClient:
      def info_dns_zone(self, domain: str):
          return {"domainname": domain, "ttl": 3600}
      
      def info_dns_records(self, domain: str):
          return [
              {"hostname": "@", "type": "A", "destination": "192.0.2.10"},
              {"hostname": "www", "type": "A", "destination": "192.0.2.20"},
          ]
  
  fake_client = FakeNetcupClient()
  app.config["netcup_client"] = fake_client
  filter_proxy.netcup_client = fake_client
  ```

### 3. **WSGI Server**
- **Webhosting**: Phusion Passenger (Apache module)
- **Local**: Gunicorn (Python WSGI server)

### 4. **TLS/HTTPS**
- **Webhosting**: Handled by hoster's nginx
- **Local**: Optional nginx reverse proxy with Let's Encrypt certs

### 5. **Test Infrastructure**
- **Webhosting**: None (tests run from Playwright container against live server)
- **Local**: Mock Netcup API and Mock SMTP running in Playwright container
  - Both accessible via Docker network
  - Tests can inspect mock state
  - Fixtures can seed/reset mock data

### 6. **Database Seeding**
- **Webhosting**: Done via `bootstrap/seeding.py` at app startup once
- **Local**: Done every time via `local_app.py` with test credentials

## Running All Tests Locally

### Quick Start (All-in-One)

```bash
# 1. Configure environment
cd /workspaces/netcup-api-filter
cp tooling/local_proxy/proxy.env.example tooling/local_proxy/proxy.env

# Edit proxy.env with your settings (or use defaults for localtest.me)
# Most important: Set LOCAL_TLS_DOMAIN to your public hostname

# 2. Run everything
tooling/run-ui-validation.sh
```

**What this script does**:
1. ✅ Creates Docker network `naf-local`
2. ✅ Attaches devcontainer to network
3. ✅ Renders nginx config from templates
4. ✅ Stages Let's Encrypt certificates
5. ✅ Starts Gunicorn with `local_app.py`
6. ✅ Starts nginx TLS proxy
7. ✅ Starts Playwright container with mocks
8. ✅ Runs **all 47 tests** (26 functional + 21 E2E)
9. ✅ Cleans up containers on exit

### Manual Step-by-Step

If you want more control:

```bash
# 1. Start local Flask app
LOCAL_DB_PATH=./tmp/local-netcup.db \
LOCAL_ADMIN_PASSWORD=admin \
LOCAL_CLIENT_ID=test_local \
LOCAL_CLIENT_SECRET_KEY=local_secret_key_12345 \
gunicorn tooling.local_proxy.local_app:app -b 0.0.0.0:5100

# 2. Start Playwright container (includes mocks)
cd tooling/playwright
docker-compose up -d

# 3. Run tests pointing to local Flask
docker exec playwright pytest /workspace/ui_tests/tests/ \
  -e UI_BASE_URL="http://host.docker.internal:5100" \
  -e UI_ADMIN_PASSWORD="admin" \
  -e UI_CLIENT_ID="test_local" \
  -e UI_CLIENT_SECRET_KEY="local_secret_key_12345" \
  -vv
```

## Environment Variables

### Local Development

```bash
# Flask App
LOCAL_DB_PATH=./tmp/local-netcup.db              # Ephemeral test database
LOCAL_ADMIN_USERNAME=admin                        # Test admin
LOCAL_ADMIN_PASSWORD=admin                        # Test password
LOCAL_CLIENT_ID=test_qweqweqwe_vi                # Test client ID
LOCAL_CLIENT_SECRET_KEY=qweqweqwe_vi_readonly_secret_key_12345  # Test secret
LOCAL_CLIENT_DOMAIN=qweqweqwe.vi                 # Test domain
LOCAL_SECRET_KEY=local-dev-secret-key            # Flask sessions

# TLS Proxy (optional)
LOCAL_TLS_DOMAIN=naf.localtest.me                # Public hostname
LOCAL_APP_HOST=devcontainer-name                 # Flask container name
LOCAL_APP_PORT=5100                              # Flask port
LOCAL_TLS_BIND_HTTPS=443                         # HTTPS port
LE_CERT_BASE=/path/to/letsencrypt               # Certificate path

# Test Runner
UI_BASE_URL=http://localhost:5100                # Where Flask is
UI_ADMIN_USERNAME=admin
UI_ADMIN_PASSWORD=admin
UI_CLIENT_ID=test_qweqweqwe_vi
UI_CLIENT_SECRET_KEY=qweqweqwe_vi_readonly_secret_key_12345
PLAYWRIGHT_HEADLESS=true                         # Headless browser
```

### Production (Webhosting)

```bash
# Auto-detected by passenger_wsgi.py
NETCUP_FILTER_DB_PATH=/netcup-api-filter/netcup_filter.db  # Auto-detected
SECRET_KEY=<generated-and-persisted>                        # Auto-generated

# Configured via Admin UI (stored in database)
# - Netcup customer_id, api_key, api_password, api_url
# - SMTP settings
# - Email notifications
```

## Test Coverage

### Functional Tests (26 tests) - Run on Both Local and Production
- ✅ Admin authentication flow
- ✅ Admin dashboard and navigation
- ✅ Admin audit logs
- ✅ Admin client management (CRUD)
- ✅ Admin configuration (Netcup, Email)
- ✅ API proxy authentication
- ✅ API proxy authorization (domain, operation, record type)
- ✅ Client portal login and dashboard
- ✅ Client portal domain management
- ✅ Audit log recording

### E2E Tests (21 tests) - Run ONLY Locally
- ⏭️  E2E DNS operations (7 tests) - Requires mock Netcup API
- ⏭️  E2E Email notifications (8 tests) - Requires mock SMTP
- ⏭️  E2E with mock API (5 tests) - Requires network-accessible mocks
- ⏭️  E2E comprehensive workflow (1 test) - Requires mocking

## Why Mock Services Work Locally

```
┌─────────────────────────────────────────┐
│ Docker Network: naf-local                │
│                                          │
│  Devcontainer                            │
│  hostname: devcontainer-xyz              │
│  IP: 172.18.0.2                         │
│                                          │
│  Playwright Container                    │
│  hostname: playwright                    │
│  IP: 172.18.0.3                         │
│  Services:                               │
│    - Mock Netcup API on 0.0.0.0:5555    │
│    - Mock SMTP on 0.0.0.0:1025          │
│                                          │
│  ▲───────────────────────────────────▲  │
│  │     Both can reach each other     │  │
│  │     via container names or IPs    │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘

Flask app configures:
  Netcup API URL: http://playwright:5555/endpoint.php
  SMTP Server: playwright:1025
```

**Why this works**:
1. Both containers on same Docker network
2. Docker DNS resolves container names
3. Flask can reach `http://playwright:5555`
4. Tests can configure app to use mock URLs
5. Tests can inspect mock state via shared container

## Summary

| Feature | Webhosting | Local |
|---------|-----------|-------|
| Database | Persistent SQLite | Ephemeral SQLite |
| Netcup Client | Real API | Fake/Mock |
| SMTP | Real SMTP | Mock SMTP |
| WSGI Server | Passenger | Gunicorn |
| TLS | Hoster nginx | Optional local nginx |
| Tests | 26 functional | 47 total (26 + 21 E2E) |
| Mock Access | ❌ Not reachable | ✅ Same Docker network |
| Use Case | Production | Development/Testing |

**The "extra" code for local deployment** is just:
1. `tooling/local_proxy/local_app.py` - Wraps app with `FakeNetcupClient`
2. Mock servers in Playwright container (already exist)
3. Environment variable differences (test credentials vs production)

**No code changes needed** - same `filter_proxy.py`, `admin_ui.py`, `client_portal.py` work in both!

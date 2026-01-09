# Deep Dive Review: Deployment & Operations Workflow

## Context

The project implements a strict deployment workflow ensuring production parity:
- **Build process**: `build_deployment.py` creates production-identical packages
- **Local testing**: `run-local-tests.sh` tests against exact deployment package
- **HTTPS testing**: TLS proxy with real Let's Encrypt certificates
- **Webhosting deployment**: `build-and-deploy.sh` deploys to production
- **Passenger WSGI**: Python app runs under Passenger on shared hosting
- **Zero-downtime restarts**: Touch `tmp/restart.txt` to reload app

## Review Objective

Verify that the deployment process is:
1. **Production-identical** - Local tests match production exactly
2. **Automated** - Single command for complete deployment
3. **Safe** - Cannot break production, has rollback capability
4. **Auditable** - All deployments logged and trackable
5. **Documented** - Complete runbook for operations

## Review Checklist

### 1. Build Process (`build_deployment.py`)

**Files:** `build_deployment.py`, `build_deployment_lib.sh`

#### Build Phases
- [ ] **Directory preparation**: Creates `deploy/` directory
- [ ] **Source copying**: Copies `src/netcup_api_filter/` to `deploy/src/`
- [ ] **Vendor bundling**: Copies packages from `requirements.webhosting.txt` to `deploy/vendor/`
- [ ] **Passenger entry point**: Copies `passenger_wsgi.py` to deploy root
- [ ] **Database preseeding**: Creates fresh SQLite database with default data
- [ ] **Build info**: Writes `build_info.json` with timestamp, commit hash
- [ ] **Deploy README**: Includes `DEPLOY_README.md` in package
- [ ] **Archive creation**: Creates `deploy.zip` from `deploy/` directory
- [ ] **Checksum generation**: Creates SHA-256 checksum file

#### Local vs Webhosting Mode
- [ ] **`--local` flag**: Builds for local testing (uses `deploy-local/`)
- [ ] **Default mode**: Builds for webhosting (uses `deploy/`)
- [ ] **Config differences**: Different preseeding (if any)
- [ ] **Path differences**: Absolute paths vs relative paths

#### Vendor Bundling
- [ ] **All dependencies**: All packages from `requirements.webhosting.txt` included
- [ ] **Correct structure**: Packages in `deploy/vendor/` directory
- [ ] **Import path**: `sys.path.insert(0, 'vendor/')` in `passenger_wsgi.py`
- [ ] **No dev dependencies**: Only production packages bundled
- [ ] **Version locking**: Exact versions from requirements file

**Test:**
```bash
# Test build process
python3 build_deployment.py --local

# Verify structure
tree deploy-local/ -L 2
# Should show: src/, vendor/, passenger_wsgi.py, netcup_filter.db, build_info.json

# Verify vendor packages
ls deploy-local/vendor/ | wc -l
# Should match number of packages in requirements.webhosting.txt

# Verify database created
sqlite3 deploy-local/netcup_filter.db "SELECT name FROM sqlite_master WHERE type='table';"
# Should show all tables (Account, Realm, AuthToken, etc.)

# Verify build info
cat deploy-local/build_info.json
# Should show: timestamp, commit_hash, build_type, python_version
```

### 2. Local Testing Workflow

**Files:** `run-local-tests.sh`, `build-and-deploy-local.sh`

#### Workflow Steps
1. **Build**: Runs `build_deployment.py --local`
2. **Extract**: Unpacks to `deploy-local/` (or builds directly there)
3. **Start Flask**: Launches Flask dev server on port 5100
4. **Wait for ready**: Polls health check until app responds
5. **Run tests**: Executes pytest test suite
6. **Collect results**: Saves test output, screenshots, logs
7. **Stop Flask**: Kills Flask process
8. **Cleanup**: Cleans up temporary files

- [ ] **Automated**: Single command runs entire workflow
- [ ] **Production parity**: Uses exact production code structure
- [ ] **Test isolation**: Fresh database per run
- [ ] **Exit codes**: Returns 0 (success) or 1 (failure)
- [ ] **Cleanup on exit**: Cleanup runs even on failure (trap)

#### Skip Options
- [ ] **`--skip-build`**: Skips build if deployment exists
- [ ] **`--skip-tests`**: Only builds, doesn't run tests
- [ ] **Environment variables**: `SKIP_BUILD=1`, `SKIP_TESTS=1`

**Test:**
```bash
# Full test run
./run-local-tests.sh

# Expected output:
# [BUILD] Building deployment package...
# [DEPLOY] Extracting to deploy-local/...
# [START] Starting Flask on port 5100...
# [TEST] Running 90 tests...
# ==================== 90 passed ====================
# [STOP] Stopping Flask...
# [CLEANUP] Cleaning up...
# ✓ All tests passed

# Test skip-build
./run-local-tests.sh --skip-build
# Should reuse existing deploy-local/

# Test failure handling
# (Introduce failing test, verify cleanup still runs)
```

### 3. HTTPS Local Testing

**Files:** `tooling/reverse-proxy/`, `test-https-deployment.sh`

#### TLS Proxy Setup
- [ ] **nginx configuration**: Generated from template via `render-nginx-conf.sh`
- [ ] **Certificate mounting**: Let's Encrypt certs mounted read-only
- [ ] **TLS termination**: nginx handles TLS, forwards HTTP to Flask
- [ ] **Proxy headers**: X-Forwarded-Proto, X-Forwarded-For set correctly
- [ ] **Docker network**: Proxy and Flask on same network

#### Configuration Steps
1. **Detect FQDN**: Read `PUBLIC_FQDN` from `.env.workspace`
2. **Render config**: Run `render-nginx-conf.sh` to generate nginx.conf
3. **Stage files**: Run `stage-proxy-inputs.sh` to copy config/certs to /tmp
4. **Start container**: `docker compose --env-file proxy.env up -d`
5. **Verify TLS**: Test HTTPS endpoint

- [ ] **Auto-detection**: FQDN auto-detected from external IP
- [ ] **Manual override**: Can set PUBLIC_FQDN manually
- [ ] **Certificate paths**: Derived from FQDN automatically
- [ ] **Error handling**: Clear errors if certs missing

**Test:**
```bash
# Start HTTPS proxy
cd tooling/reverse-proxy
./render-nginx-conf.sh && ./stage-proxy-inputs.sh
docker compose --env-file proxy.env up -d

# Get FQDN
FQDN=$(grep LOCAL_TLS_DOMAIN proxy.env | cut -d= -f2)

# Test HTTPS
curl -v https://$FQDN/ 2>&1 | grep "SSL certificate verify ok"
# Should succeed with valid certificate

# Test Secure cookies
curl -I https://$FQDN/admin/login | grep -i "set-cookie"
# Should show: Secure; HttpOnly; SameSite=Lax

# Run UI tests against HTTPS
UI_BASE_URL="https://$FQDN" pytest ui_tests/tests -v
# Should pass all tests
```

### 4. Webhosting Deployment

**Files:** `build-and-deploy.sh`, SSH config

#### Deployment Steps
1. **Build package**: Runs `build_deployment.py` (webhosting mode)
2. **Upload to server**: `scp deploy.zip user@host:/path/`
3. **Connect via SSH**: SSH into webhosting server
4. **Backup current**: `mv /netcup-api-filter /netcup-api-filter.backup`
5. **Extract new**: `unzip deploy.zip -d /netcup-api-filter`
6. **Restart Passenger**: `touch /netcup-api-filter/tmp/restart.txt`
7. **Verify deployment**: Check health endpoint

- [ ] **Automated**: Single script performs entire deployment
- [ ] **Safe**: Creates backup before deployment
- [ ] **Rollback**: Can restore from backup if needed
- [ ] **Minimal downtime**: Passenger reload (not full restart)

#### SSH Configuration
- [ ] **Host**: `hosting218629@hosting218629.ae98d.netcup.net`
- [ ] **Directory**: `/netcup-api-filter`
- [ ] **Key-based auth**: SSH key configured (not password)
- [ ] **SSH agent**: Keys loaded in devcontainer

#### Passenger Configuration (via Hoster UI)
- [ ] **Document root**: `/netcup-api-filter/public` (or similar)
- [ ] **WSGI file**: `/netcup-api-filter/passenger_wsgi.py`
- [ ] **Python version**: 3.11 selected
- [ ] **Environment variables**: Set via control panel (if any)

**Test:**
```bash
# Deploy to production
./build-and-deploy.sh

# Expected output:
# [BUILD] Building deployment package...
# [UPLOAD] Uploading to hosting218629.ae98d.netcup.net...
# [DEPLOY] Extracting on server...
# [RESTART] Restarting Passenger...
# [VERIFY] Checking health endpoint...
# ✓ Deployment successful

# Verify deployment
curl -I https://$PUBLIC_FQDN/
# Should return 200 OK

# Check build info
curl https://$PUBLIC_FQDN/admin/system-info
# Should show latest build timestamp
```

### 5. Production Parity Validation

**Differences between local and production**

#### Must Be Identical
- [ ] **Directory structure**: Same paths (src/, vendor/, passenger_wsgi.py)
- [ ] **Python packages**: Exact same versions
- [ ] **Source code**: Byte-for-byte identical
- [ ] **Database schema**: Same tables, indexes, constraints
- [ ] **Entry point**: Same `passenger_wsgi.py:application`

#### Acceptable Differences
- [ ] **Database content**: Production has real data, local has seed data
- [ ] **Environment variables**: Different per environment
- [ ] **File paths**: Absolute paths may differ
- [ ] **Log files**: Different log locations

**Test:**
```bash
# Compare local and production package structure
diff -r deploy-local/src/ deploy/src/
# Should show no differences

# Compare vendor packages
diff <(ls deploy-local/vendor/) <(ls deploy/vendor/)
# Should show no differences

# Compare passenger_wsgi.py
diff deploy-local/passenger_wsgi.py deploy/passenger_wsgi.py
# Should show no differences
```

### 6. Database Management

**Database operations**

#### Initial Database
- [ ] **Preseeded in build**: Fresh database created during build
- [ ] **Admin account**: Default admin account created
- [ ] **Test client**: Test client preseeded (for local only)
- [ ] **Backend providers**: Netcup, PowerDNS providers seeded
- [ ] **Enum tables**: All enum tables populated

#### Database Location
- [ ] **Local**: `deploy-local/netcup_filter.db`
- [ ] **Production**: `/netcup-api-filter/netcup_filter.db`
- [ ] **Gitignored**: Database files not in version control
- [ ] **Backup**: Production database backed up before deployment

#### Migrations (Future)
- [ ] **Alembic**: Migration framework ready
- [ ] **Migration scripts**: In `migrations/` directory (if exists)
- [ ] **Upgrade command**: Can apply migrations to existing database
- [ ] **Rollback support**: Down migrations implemented

**Test:**
```bash
# Verify database structure
sqlite3 deploy-local/netcup_filter.db << EOF
.tables
.schema Account
.schema Realm
EOF

# Verify admin account
sqlite3 deploy-local/netcup_filter.db \
  "SELECT username, is_approved FROM Account WHERE username='admin';"
# Should show: admin|1

# Verify backend providers
sqlite3 deploy-local/netcup_filter.db \
  "SELECT provider_code, display_name FROM BackendProvider;"
# Should show: netcup|Netcup, powerdns|PowerDNS
```

### 7. Log Management

**Logging strategy**

#### Log Files
- [ ] **Application log**: `netcup_filter.log` (in deployment directory)
- [ ] **Passenger log**: Passenger-specific logs (hoster location)
- [ ] **Error log**: Python traceback logs (stderr)
- [ ] **Access log**: Web server access logs (hoster location)

#### Log Configuration
- [ ] **Log level**: INFO in production, DEBUG in local_test
- [ ] **Log format**: Structured logging (timestamp, level, logger, message)
- [ ] **Log rotation**: Rotated by size/date (if configured)
- [ ] **Log retention**: Kept for X days (configured)

#### Production Logs
- [ ] **Access method**: SSH + less/tail
- [ ] **Download**: Can scp logs to local machine
- [ ] **Monitoring**: (If monitoring service configured)

**Test:**
```bash
# View local logs
tail -f deploy-local/netcup_filter.log

# View production logs
ssh hosting218629@hosting218629.ae98d.netcup.net \
  "tail -f /netcup-api-filter/netcup_filter.log"

# Search logs
grep "ERROR" deploy-local/netcup_filter.log
# Should show error events

# Check log format
head -1 deploy-local/netcup_filter.log
# Should show structured format: [timestamp] [level] logger: message
```

### 8. Health Checks & Monitoring

**Application health monitoring**

#### Health Endpoint
- [ ] **Endpoint**: `/` returns 200 OK
- [ ] **Quick response**: < 100ms response time
- [ ] **No authentication**: Publicly accessible
- [ ] **Database check**: (Optional) Verifies database accessible
- [ ] **Uptime monitors**: Pingdom, UptimeRobot, etc.

#### System Info Endpoint
- [ ] **Endpoint**: `/admin/system-info` (admin only)
- [ ] **Build info**: Shows build timestamp, commit hash
- [ ] **Python version**: Shows Python version
- [ ] **Database size**: Shows database file size
- [ ] **Package versions**: Lists installed packages

**Test:**
```bash
# Test health endpoint
curl -I http://localhost:5100/
# Should return: 200 OK

# Test response time
time curl -s http://localhost:5100/ > /dev/null
# Should be < 0.1s

# Test system info (requires auth)
curl -u admin:admin http://localhost:5100/admin/system-info
# Should return JSON with build_info, python_version, etc.
```

### 9. Rollback Procedures

**Disaster recovery**

#### Backup Strategy
- [ ] **Pre-deployment backup**: Before each deployment
- [ ] **Database backup**: Database backed up separately
- [ ] **Configuration backup**: `.env` and config files backed up
- [ ] **Backup retention**: Last N backups kept

#### Rollback Steps
1. **Stop application**: (If needed)
2. **Restore from backup**: `mv /netcup-api-filter.backup /netcup-api-filter`
3. **Restart Passenger**: `touch /netcup-api-filter/tmp/restart.txt`
4. **Verify health**: Check health endpoint
5. **Investigate issue**: Review logs for root cause

- [ ] **Documented**: Rollback procedure documented in runbook
- [ ] **Tested**: Rollback tested in local environment
- [ ] **Quick**: Can rollback in < 5 minutes

**Test:**
```bash
# Simulate failed deployment and rollback
cd /netcup-api-filter
mv . ../netcup-api-filter.backup
# Extract new package
unzip ../deploy.zip -d .
# Simulate failure (e.g., missing dependency)
# Rollback:
cd ..
rm -rf netcup-api-filter
mv netcup-api-filter.backup netcup-api-filter
touch netcup-api-filter/tmp/restart.txt
# Verify health
curl http://localhost/
```

### 10. Deployment Checklist

**Pre-deployment verification**

#### Before Deployment
- [ ] **All tests pass**: `./run-local-tests.sh` passes
- [ ] **UI tests pass**: Playwright tests pass
- [ ] **No console errors**: Browser console clean
- [ ] **Database migrations**: Migrations applied (if any)
- [ ] **Changelog updated**: RECENT_CHANGES.md updated
- [ ] **Version tagged**: Git tag created (if using tags)

#### During Deployment
- [ ] **Backup created**: Pre-deployment backup exists
- [ ] **Upload successful**: deploy.zip transferred completely
- [ ] **Extraction successful**: Unzip completes without errors
- [ ] **Passenger restart**: tmp/restart.txt touched

#### Post-Deployment
- [ ] **Health check**: Health endpoint responds
- [ ] **Login test**: Admin can log in
- [ ] **Critical workflows**: Key features work (create account, realm, token)
- [ ] **No errors in logs**: No errors in netcup_filter.log
- [ ] **SSL certificate valid**: HTTPS works correctly
- [ ] **DNS updates work**: API calls succeed

**Checklist template:**
```markdown
## Deployment Checklist - [Date]

### Pre-Deployment
- [ ] All tests pass locally
- [ ] UI tests pass
- [ ] Changelog updated
- [ ] Git tag created

### Deployment
- [ ] Backup created
- [ ] Uploaded deploy.zip
- [ ] Extracted successfully
- [ ] Passenger restarted

### Post-Deployment
- [ ] Health check OK
- [ ] Admin login works
- [ ] API test succeeds
- [ ] No errors in logs

### Rollback Plan (if needed)
1. SSH to server
2. `mv /netcup-api-filter.backup /netcup-api-filter`
3. `touch /netcup-api-filter/tmp/restart.txt`
```

### 11. Continuous Deployment Readiness

**CI/CD considerations**

#### GitHub Actions (or similar CI)
- [ ] **Test workflow**: Runs tests on every push/PR
- [ ] **Build workflow**: Builds deployment package
- [ ] **Deploy workflow**: (Optional) Auto-deploy to staging
- [ ] **Artifacts**: Saves deploy.zip as artifact

#### Automated Testing
- [ ] **Unit tests**: Run on every commit
- [ ] **Integration tests**: Run on every commit
- [ ] **UI tests**: Run on PR creation
- [ ] **Coverage reporting**: Coverage tracked over time

#### Deployment Triggers
- [ ] **Manual trigger**: Deploy button in GitHub Actions
- [ ] **Tag trigger**: Deploy on version tag (e.g., v1.0.0)
- [ ] **Branch trigger**: Auto-deploy main branch to staging

**Example workflow:**
```yaml
name: Deploy
on:
  push:
    tags:
      - 'v*'
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Build deployment
        run: python3 build_deployment.py
      - name: Upload to server
        run: |
          scp deploy.zip ${{ secrets.SSH_USER }}@${{ secrets.SSH_HOST }}:/tmp/
          ssh ${{ secrets.SSH_USER }}@${{ secrets.SSH_HOST }} \
            'cd /netcup-api-filter && bash deploy.sh'
```

### 12. Documentation & Runbook

**Operational documentation**

#### Documentation Files
- [ ] **DEPLOYMENT_WORKFLOW.md**: Complete deployment guide
- [ ] **OPERATIONS_GUIDE.md**: Day-to-day operations
- [ ] **LOCAL_TESTING_GUIDE.md**: Local testing instructions
- [ ] **HTTPS_LOCAL_TESTING.md**: HTTPS testing setup
- [ ] **docs/READY_TO_DEPLOY.md**: Production readiness checklist

#### Runbook Contents
- [ ] **Build procedure**: How to build deployment package
- [ ] **Deploy procedure**: Step-by-step deployment
- [ ] **Rollback procedure**: How to rollback
- [ ] **Log access**: How to access logs
- [ ] **Troubleshooting**: Common issues and solutions
- [ ] **Contact info**: Who to contact for issues

**Test:**
```bash
# Verify documentation exists
ls docs/ | grep -E "(DEPLOYMENT|OPERATIONS|TESTING)"
# Should show: DEPLOYMENT_WORKFLOW.md, OPERATIONS_GUIDE.md, LOCAL_TESTING_GUIDE.md

# Verify documentation completeness (check for TODOs)
rg "TODO|FIXME" docs/*.md
# Should return no critical TODOs
```

### 13. Security Considerations

**Deployment security**

#### Access Control
- [ ] **SSH key**: Password-less SSH via key
- [ ] **Key management**: SSH keys stored securely
- [ ] **Server access**: Only authorized users have SSH access
- [ ] **File permissions**: Correct permissions on deployed files

#### Secrets Management
- [ ] **No secrets in repo**: No secrets in version control
- [ ] **Environment variables**: Secrets in environment, not files
- [ ] **Database encryption**: Sensitive data encrypted in database
- [ ] **Deploy package**: No secrets in deploy.zip (loaded from env/database)

#### Network Security
- [ ] **HTTPS only**: All production traffic over HTTPS
- [ ] **TLS 1.2+**: Only strong TLS versions
- [ ] **Strong ciphers**: No weak cipher suites
- [ ] **HSTS**: Strict-Transport-Security header set

**Test:**
```bash
# Verify no secrets in repo
rg -i "(password|api_key|secret)\s*=\s*['\"][a-zA-Z0-9]{12,}" --glob="!.env*" .
# Should return no results

# Verify SSH key auth (not password)
ssh -v hosting218629@hosting218629.ae98d.netcup.net 2>&1 | grep "Offering public key"
# Should show key-based authentication

# Verify HTTPS security
curl -I https://$PUBLIC_FQDN/ | grep "Strict-Transport-Security"
# Should show HSTS header
```

### 14. Performance Monitoring

**Production performance**

#### Metrics to Monitor
- [ ] **Response time**: Average, p95, p99 response times
- [ ] **Error rate**: 4xx, 5xx error rates
- [ ] **Throughput**: Requests per second
- [ ] **Database size**: Database file size growth
- [ ] **Log size**: Log file size growth

#### Monitoring Tools
- [ ] **Application logs**: Structured logging for analysis
- [ ] **Server logs**: Web server access/error logs
- [ ] **External monitoring**: Uptime monitors (Pingdom, etc.)
- [ ] **Alerting**: Alerts on errors, downtime, performance degradation

**Test:**
```bash
# Measure response time
ab -n 1000 -c 10 http://localhost:5100/
# Should show: Mean response time < 100ms

# Check database size
ls -lh deploy-local/netcup_filter.db
# Note size for growth monitoring

# Check log size
ls -lh deploy-local/netcup_filter.log
# Note size for rotation planning
```

### 15. Disaster Recovery Plan

**Worst-case scenarios**

#### Scenarios & Responses
- [ ] **Server crash**: Restore from backup, redeploy
- [ ] **Database corruption**: Restore from database backup
- [ ] **Bad deployment**: Rollback to previous version
- [ ] **Security breach**: Rotate secrets, investigate logs
- [ ] **Data loss**: Restore from backup, assess data loss

#### Backup Strategy
- [ ] **Frequency**: Daily automated backups
- [ ] **Retention**: Keep last 7 daily, 4 weekly, 12 monthly
- [ ] **Storage**: Off-server backup storage
- [ ] **Testing**: Regular restore tests

#### Recovery Time Objectives
- [ ] **RTO**: Target recovery time (e.g., < 1 hour)
- [ ] **RPO**: Acceptable data loss window (e.g., < 1 day)

**Test:**
```bash
# Test backup/restore process
# 1. Create backup
cp deploy-local/netcup_filter.db deploy-local/netcup_filter.db.backup

# 2. Simulate data loss
rm deploy-local/netcup_filter.db

# 3. Restore from backup
cp deploy-local/netcup_filter.db.backup deploy-local/netcup_filter.db

# 4. Verify restoration
sqlite3 deploy-local/netcup_filter.db "SELECT COUNT(*) FROM Account;"
# Should show expected account count
```

## Expected Deliverable

**Comprehensive deployment review report:**

```markdown
# Deployment & Operations Workflow - Operations Review

## Executive Summary
- Deployment automation: ✅ Fully Automated | ⚠️ Partially | ❌ Manual
- Production parity: ✅ Identical | ⚠️ Minor Differences | ❌ Major Differences
- Documentation: ✅ Complete | ⚠️ Adequate | ❌ Insufficient
- Rollback capability: ✅ Tested | ⚠️ Documented Only | ❌ None
- Critical issues: [count]

## Workflow Analysis

### Build Process
- Automation: ✅/⚠️/❌
- Production parity: ✅/⚠️/❌
- Issues: [list]

### Local Testing
- Coverage: [percentage]%
- Success rate: [percentage]%
- Issues: [list]

### Deployment Process
- Automation: ✅/⚠️/❌
- Safety: ✅/⚠️/❌
- Issues: [list]

## Production Parity Validation

### Identical Elements
- [list of confirmed identical elements]

### Acceptable Differences
- [list with explanations]

### Concerning Differences
- [list that need attention]

## Critical Issues (P0)
1. [Issue] - Component: [name] - Impact: [description] - Fix: [recommendation]

## Operational Recommendations

### Immediate Actions
1. [Action item with priority and timeline]

### Process Improvements
...

### Monitoring Enhancements
...

## Runbook Checklist

- [ ] Build procedure documented
- [ ] Deploy procedure documented
- [ ] Rollback procedure documented
- [ ] Log access documented
- [ ] Troubleshooting guide complete

## Code References
- [File:line] - [Finding]
```

---

## Usage

```
Please perform a comprehensive deployment and operations review using the checklist defined in .vscode/REVIEW_PROMPT_DEPLOYMENT_OPS.md.

Focus on:
1. Verifying production parity between local and deployed environments
2. Testing deployment automation and safety
3. Validating rollback procedures
4. Checking documentation completeness
5. Reviewing disaster recovery readiness

Provide a structured report with findings, process diagrams, and operational recommendations.
```

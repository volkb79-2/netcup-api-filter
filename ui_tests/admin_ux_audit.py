#!/usr/bin/env python3
"""
Admin UX Audit Script (DEPRECATED)

**DEPRECATION NOTICE**: This script has been superseded by Playwright tests.
The httpx-based approach has fundamental limitations:
- Cannot execute JavaScript (no client-side validation testing)
- CSRF token handling is fragile and causes authentication failures  
- Partial auth flow completion corrupts deployment_state_local.json
- Cannot test interactive elements (modals, dropdowns, themes)

Use Playwright tests instead:
    pytest ui_tests/tests/test_ui_interactive.py -v
    pytest ui_tests/tests/test_user_journeys.py -v

This file is kept for reference but is no longer part of the test pipeline.
See docs/JOURNEY_CONTRACTS.md for the canonical testing approach.

---
Original description:

Systematically tests all admin pages against UI_REQUIREMENTS.md.
Runs via httpx (no browser session issues).

Usage:
    python ui_tests/admin_ux_audit.py [--base-url URL]
    
Exit codes:
    0 = All checks passed
    N = Number of issues found
"""
# ruff: noqa: E501
# type: ignore  # BeautifulSoup type stubs are incomplete

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from bs4 import BeautifulSoup


def _get_admin_password_from_state() -> str:
    """Get admin password from deployment state file."""
    import json
    from pathlib import Path
    
    # Check environment first
    if env_pass := os.environ.get('UI_ADMIN_PASSWORD'):
        return env_pass
    
    # Try deployment state file
    target = os.environ.get('DEPLOYMENT_TARGET', 'local')
    state_file = Path(f'/workspaces/netcup-api-filter/deployment_state_{target}.json')
    if state_file.exists():
        state = json.loads(state_file.read_text())
        if 'admin' in state and 'password' in state['admin']:
            return state['admin']['password']
    
    # Fallback to default (fresh deployment)
    return 'admin'


@dataclass
class AuditResult:
    """Result of auditing a single page."""
    page: str
    checks: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    
    def check(self, name: str, passed: bool, details: str = ""):
        """Record a check result."""
        status = "✅" if passed else "❌"
        self.checks.append(f"{status} {name}")
        if not passed:
            self.issues.append(f"{name}: {details}")
    
    def report(self) -> int:
        """Print report and return issue count."""
        print(f"\n{'='*60}")
        print(f"PAGE: {self.page}")
        print('='*60)
        for check in self.checks:
            print(f"  {check}")
        if self.issues:
            print(f"\n  ISSUES ({len(self.issues)}):")
            for issue in self.issues:
                print(f"    - {issue}")
        return len(self.issues)


class AdminUXAudit:
    """Audits admin UI pages against UI_REQUIREMENTS.md."""
    
    def __init__(self, base_url: str, admin_password: str | None = None):
        self.base_url = base_url.rstrip('/')
        # Use provided password, or get from state file/environment
        self.admin_password = admin_password or _get_admin_password_from_state()
        self.default_password = "admin"
    
    def audit_login_page(self, client: httpx.Client) -> AuditResult:
        """Audit /admin/login per UI_REQUIREMENTS.md section 3.1"""
        result = AuditResult(page="/admin/login")
        
        resp = client.get(f"{self.base_url}/admin/login")
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check: Title outside card as h1
        h1 = soup.find('h1')
        result.check(
            "H1 headline 'Netcup API Filter' outside card",
            h1 and "Netcup API Filter" in h1.text,
            f"Found: {h1.text if h1 else 'No h1'}"
        )
        
        # Check: H2 for 'Admin Login'
        h2 = soup.find('h2')
        result.check(
            "H2 'Admin Login' inside card",
            h2 and "Admin Login" in h2.text,
            f"Found: {h2.text if h2 else 'No h2'}"
        )
        
        # Check: Username input
        username_input = soup.find('input', {'name': 'username'})
        result.check(
            "Username input exists",
            username_input is not None,
            "Missing username input"
        )
        
        # Check: Password input with toggle
        password_input = soup.find('input', {'name': 'password'})
        password_toggle = soup.find('button', onclick=re.compile(r'togglePassword'))
        result.check(
            "Password input with toggle button",
            password_input is not None and password_toggle is not None,
            f"Input: {password_input is not None}, Toggle: {password_toggle is not None}"
        )
        
        # Check: Submit button
        submit_btn = soup.find('button', {'type': 'submit'})
        result.check(
            "Sign In submit button",
            submit_btn and "Sign In" in submit_btn.text,
            f"Found: {submit_btn.text if submit_btn else 'None'}"
        )
        
        # Check: Security notice (not muted)
        footer = soup.find('div', class_='card-footer')
        if footer:
            small = footer.find('small')
            result.check(
                "Security notice readable (not text-muted)",
                small and 'text-muted' not in (small.get('class') or []),
                f"Classes: {small.get('class', []) if small else 'None'}"
            )
        else:
            result.check("Card footer exists", False, "No card-footer found")
        
        # Check: No navbar on login
        navbar = soup.find('nav')
        result.check(
            "No navbar on login page",
            navbar is None,
            "Navbar should not be present"
        )
        
        return result

    def audit_login_flow(self, client: httpx.Client) -> AuditResult:
        """Test actual login with default credentials."""
        result = AuditResult(page="Login Flow")
        
        # First, get the login page to extract CSRF token
        login_page = client.get(f"{self.base_url}/admin/login")
        soup = BeautifulSoup(login_page.text, 'html.parser')
        csrf_token = None
        csrf_input = soup.find('input', {'name': 'csrf_token'})
        if csrf_input:
            csrf_token = csrf_input.get('value', '')
        
        if not csrf_token:
            result.check(
                "CSRF token found on login page",
                False,
                "Cannot login without CSRF token"
            )
            return result
        
        # Try with changed password first (password may already be changed)
        login_resp = client.post(
            f"{self.base_url}/admin/login",
            data={"username": "admin", "password": self.admin_password, "csrf_token": csrf_token},
            follow_redirects=True
        )
        
        if login_resp.status_code == 200 and "/admin/" in str(login_resp.url):
            # Already authenticated with changed password
            result.check(
                "Login with changed password succeeds",
                True,
                f"Logged in to {login_resp.url}"
            )
            result.check(
                "Password already changed (skip fresh DB flow)",
                True,
                "Using existing credentials"
            )
            return result
        
        # Try with default password - need fresh CSRF token
        login_page2 = client.get(f"{self.base_url}/admin/login")
        soup2 = BeautifulSoup(login_page2.text, 'html.parser')
        csrf_input2 = soup2.find('input', {'name': 'csrf_token'})
        csrf_token2 = csrf_input2.get('value', '') if csrf_input2 else ''
        
        login_resp = client.post(
            f"{self.base_url}/admin/login",
            data={"username": "admin", "password": self.default_password, "csrf_token": csrf_token2},
            follow_redirects=True
        )
        
        result.check(
            "Login with admin/admin succeeds",
            login_resp.status_code == 200,
            f"Status: {login_resp.status_code}"
        )
        
        # Should redirect to change-password on fresh database
        result.check(
            "Redirects to change-password page (fresh DB)",
            "/change-password" in str(login_resp.url),
            f"URL: {login_resp.url}"
        )
        
        return result

    def audit_change_password_page(self, client: httpx.Client) -> AuditResult:
        """Audit /admin/change-password per UI_REQUIREMENTS.md section 3.2"""
        result = AuditResult(page="/admin/change-password")
        
        # Try to access change-password directly first
        resp = client.get(f"{self.base_url}/admin/change-password", follow_redirects=False)
        
        # If redirected to login, password is already changed (page requires must_change_password)
        if resp.status_code == 302 or "login" in str(resp.headers.get("location", "")):
            # Try logging in with default password to force change-password state
            client.post(
                f"{self.base_url}/admin/login",
                data={"username": "admin", "password": self.default_password}
            )
            resp = client.get(f"{self.base_url}/admin/change-password")
        
        # If still redirected (password already changed), skip this audit
        if resp.status_code == 302:
            result.check(
                "Password already changed (page not accessible)",
                True,
                "Change password flow not required"
            )
            return result
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check if we got the login page instead
        if soup.find('input', {'name': 'username'}):
            result.check(
                "Password already changed (redirected to login)",
                True,
                "Change password flow not required"
            )
            return result
        
        # Check: Current password field
        current_pwd = soup.find('input', {'name': 'current_password'})
        result.check(
            "Current password field exists",
            current_pwd is not None,
            "Missing current_password input"
        )
        
        # Check: New password field
        new_pwd = soup.find('input', {'name': 'new_password'})
        result.check(
            "New password field exists",
            new_pwd is not None,
            "Missing new_password input"
        )
        
        # Check: Confirm password field
        confirm_pwd = soup.find('input', {'name': 'confirm_password'})
        result.check(
            "Confirm password field exists",
            confirm_pwd is not None,
            "Missing confirm_password input"
        )
        
        # Check: Password requirements displayed (8 chars minimum per current implementation)
        requirements_text = soup.get_text()
        result.check(
            "Password requirements shown",
            "character" in requirements_text.lower() or "requirement" in requirements_text.lower(),
            "Requirements text not found"
        )
        
        # Check: Password toggle buttons
        toggles = soup.find_all('button', onclick=re.compile(r'togglePassword'))
        result.check(
            "Password toggle buttons (3 expected)",
            len(toggles) >= 3,
            f"Found {len(toggles)} toggles"
        )
        
        return result

    def _ensure_authenticated(self, client: httpx.Client) -> bool:
        """Ensure client is authenticated, changing password if needed."""
        # Get login page to extract CSRF token
        login_page = client.get(f"{self.base_url}/admin/login")
        soup = BeautifulSoup(login_page.text, 'html.parser')
        csrf_input = soup.find('input', {'name': 'csrf_token'})
        csrf_token = csrf_input.get('value', '') if csrf_input else ''
        
        # Try with changed password first
        client.post(
            f"{self.base_url}/admin/login",
            data={"username": "admin", "password": self.admin_password, "csrf_token": csrf_token}
        )
        
        # Check if we're on dashboard (not change-password page)
        check_resp = client.get(f"{self.base_url}/admin/", follow_redirects=True)
        if check_resp.status_code == 200:
            # Verify we're actually on dashboard, not stuck on change-password
            check_soup = BeautifulSoup(check_resp.text, 'html.parser')
            h1 = check_soup.find('h1')
            page_title = h1.text if h1 else ""
            
            # If we're on change-password page, we need to handle it
            if "Change Password" in page_title or "Initial Setup" in page_title:
                return self._handle_password_change(client)
            
            # If we see Dashboard or similar, we're authenticated
            if "Dashboard" in page_title or check_soup.find('nav'):
                return True
        
        # If redirected to change-password, need to change it
        if check_resp.status_code == 302 and "change-password" in check_resp.headers.get("location", ""):
            return self._handle_password_change(client)
        
        return False
    
    def _handle_password_change(self, client: httpx.Client) -> bool:
        """Handle forced password change on fresh deployment."""
        import secrets
        import string
        
        # Generate a new secure password if current one is the default
        if self.admin_password == self.default_password:
            alphabet = string.ascii_letters + string.digits + "@#$%"
            self.admin_password = ''.join(secrets.choice(alphabet) for _ in range(64))
        
        # Get fresh login page for new CSRF token
        login_page2 = client.get(f"{self.base_url}/admin/login")
        soup2 = BeautifulSoup(login_page2.text, 'html.parser')
        csrf_input2 = soup2.find('input', {'name': 'csrf_token'})
        csrf_token2 = csrf_input2.get('value', '') if csrf_input2 else ''
        
        # Login with default password
        client.post(
            f"{self.base_url}/admin/login",
            data={"username": "admin", "password": self.default_password, "csrf_token": csrf_token2}
        )
        
        # Get change-password page for CSRF token
        change_page = client.get(f"{self.base_url}/admin/change-password")
        soup3 = BeautifulSoup(change_page.text, 'html.parser')
        csrf_input3 = soup3.find('input', {'name': 'csrf_token'})
        csrf_token3 = csrf_input3.get('value', '') if csrf_input3 else ''
        
        # Change password
        change_resp = client.post(
            f"{self.base_url}/admin/change-password",
            data={
                "current_password": self.default_password,
                "new_password": self.admin_password,
                "confirm_password": self.admin_password,
                "csrf_token": csrf_token3
            },
            follow_redirects=True
        )
        
        # Verify password was changed (should be on dashboard now)
        check_soup = BeautifulSoup(change_resp.text, 'html.parser')
        h1 = check_soup.find('h1')
        page_title = h1.text if h1 else ""
        
        if "Dashboard" in page_title:
            # Update the deployment state file with new password
            self._update_deployment_state()
            return True
        
        # If still on change password, try re-login
        login_page3 = client.get(f"{self.base_url}/admin/login")
        soup4 = BeautifulSoup(login_page3.text, 'html.parser')
        csrf_input4 = soup4.find('input', {'name': 'csrf_token'})
        csrf_token4 = csrf_input4.get('value', '') if csrf_input4 else ''
        
        # Re-login with new password
        client.post(
            f"{self.base_url}/admin/login",
            data={"username": "admin", "password": self.admin_password, "csrf_token": csrf_token4}
        )
        
        self._update_deployment_state()
        return True
    
    def _update_deployment_state(self):
        """Update deployment state file with new password."""
        import json
        from pathlib import Path
        from datetime import datetime, timezone
        
        target = os.environ.get('DEPLOYMENT_TARGET', 'local')
        state_file = Path(f'/workspaces/netcup-api-filter/deployment_state_{target}.json')
        
        if state_file.exists():
            state = json.loads(state_file.read_text())
            state['admin']['password'] = self.admin_password
            state['admin']['password_changed_at'] = datetime.now(timezone.utc).isoformat()
            state['last_updated_at'] = datetime.now(timezone.utc).isoformat()
            state['updated_by'] = 'admin_ux_audit'
            state_file.write_text(json.dumps(state, indent=2))

    def audit_dashboard_page(self, client: httpx.Client) -> AuditResult:
        """Audit /admin/ dashboard per UI_REQUIREMENTS.md section 3.3"""
        result = AuditResult(page="/admin/ (Dashboard)")
        
        self._ensure_authenticated(client)
        
        resp = client.get(f"{self.base_url}/admin/")
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check: Page title/heading
        h1 = soup.find('h1')
        result.check(
            "Dashboard heading exists",
            h1 and "Dashboard" in h1.text,
            f"Found: {h1.text if h1 else 'None'}"
        )
        
        # Check: Statistics cards
        cards = soup.find_all('div', class_=re.compile(r'card'))
        result.check(
            "Statistics cards present",
            len(cards) >= 2,
            f"Found {len(cards)} cards"
        )
        
        # Check: Navbar present
        navbar = soup.find('nav') or soup.find('header', class_=re.compile(r'header'))
        result.check(
            "Navbar/header present on dashboard",
            navbar is not None,
            "Navbar missing"
        )
        
        # Check: Navigation links
        nav_links = {
            "Dashboard": "/admin/",
            "Accounts": "/admin/accounts",
            "Pending": "/admin/realms/pending",
            "Audit": "/admin/audit",
        }
        for name, href in nav_links.items():
            link = soup.find('a', href=href)
            result.check(
                f"Nav link '{name}' exists",
                link is not None,
                f"Missing link to {href}"
            )
        
        # Check: Config dropdown
        config_dropdown = soup.find('a', class_='dropdown-toggle', string=re.compile(r'Config'))
        result.check(
            "Config dropdown exists",
            config_dropdown is not None,
            "Config dropdown not found"
        )
        
        # Check: Theme switcher
        theme_icon = soup.find('i', class_='bi-palette2')
        result.check(
            "Theme switcher in navbar",
            theme_icon is not None,
            "Theme palette icon not found"
        )
        
        # Check: Logout link
        logout = soup.find('a', href='/admin/logout')
        result.check(
            "Logout link exists",
            logout is not None,
            "Logout link missing"
        )
        
        # Check: Footer
        footer = soup.find('footer') or soup.find('div', class_='app-footer')
        result.check(
            "Footer present",
            footer is not None,
            "Footer element missing"
        )
        
        if footer:
            footer_str = str(footer)
            result.check(
                "Footer is centered",
                'text-center' in footer.get('class', []) or 'text-center' in footer_str,
                f"Footer classes: {footer.get('class', [])}"
            )
        
        return result

    def audit_accounts_page(self, client: httpx.Client) -> AuditResult:
        """Audit /admin/accounts per UI_REQUIREMENTS.md section 3.4"""
        result = AuditResult(page="/admin/accounts")
        
        resp = client.get(f"{self.base_url}/admin/accounts")
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check: Page heading
        h1 = soup.find('h1')
        result.check(
            "Accounts heading",
            h1 and "Account" in h1.text,
            f"Found: {h1.text if h1 else 'None'}"
        )
        
        # Check: Create Account button
        create_btn = soup.find('a', href='/admin/accounts/new') or soup.find('a', string=re.compile(r'Create|New'))
        result.check(
            "Create Account button/link",
            create_btn is not None,
            "Create account link not found"
        )
        
        # Check: Table exists
        table = soup.find('table')
        result.check(
            "Accounts table exists",
            table is not None,
            "No table found"
        )
        
        if table:
            headers = [th.text.strip() for th in table.find_all('th')]
            result.check(
                "Table has Username column",
                any('user' in h.lower() for h in headers),
                f"Headers: {headers}"
            )
        
        return result

    def audit_accounts_new_page(self, client: httpx.Client) -> AuditResult:
        """Audit /admin/accounts/new per UI_REQUIREMENTS.md section 3.5"""
        result = AuditResult(page="/admin/accounts/new")
        
        resp = client.get(f"{self.base_url}/admin/accounts/new")
        
        if resp.status_code == 404:
            result.check("Page exists", False, "404 Not Found")
            return result
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check: Form exists
        form = soup.find('form')
        result.check(
            "Create account form exists",
            form is not None,
            "No form found"
        )
        
        if form:
            fields = {
                'username': 'Username field',
                'email': 'Email field',
                'password': 'Password field',
            }
            for field_name, label in fields.items():
                fld = form.find('input', {'name': re.compile(field_name, re.I)})
                result.check(label, fld is not None, f"Missing {field_name} input")
        
        return result

    def audit_config_netcup_page(self, client: httpx.Client) -> AuditResult:
        """Audit /admin/config/netcup per UI_REQUIREMENTS.md section 3.8"""
        result = AuditResult(page="/admin/config/netcup")
        
        resp = client.get(f"{self.base_url}/admin/config/netcup")
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check: Form exists
        form = soup.find('form')
        result.check("Config form exists", form is not None, "No form")
        
        if form:
            # Check fields (using actual field names from implementation)
            fields = ['customer_number', 'api_key', 'api_password', 'api_endpoint', 'timeout']
            for fld in fields:
                inp = form.find('input', {'name': fld}) or form.find('input', {'id': fld})
                result.check(f"Field '{fld}'", inp is not None, f"Missing {fld}")
            
            # Check: Password toggle for sensitive fields
            toggles = soup.find_all('button', onclick=re.compile(r'togglePassword'))
            result.check(
                "Password toggles for sensitive fields",
                len(toggles) >= 1,
                f"Found {len(toggles)} toggles"
            )
        
        # Check: Save button
        save_btn = soup.find('button', {'type': 'submit'})
        result.check(
            "Save button exists",
            save_btn is not None,
            "No submit button"
        )
        
        return result

    def audit_config_email_page(self, client: httpx.Client) -> AuditResult:
        """Audit /admin/config/email per UI_REQUIREMENTS.md section 3.9"""
        result = AuditResult(page="/admin/config/email")
        
        resp = client.get(f"{self.base_url}/admin/config/email")
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check: Form exists
        form = soup.find('form')
        result.check("Email config form exists", form is not None, "No form")
        
        if form:
            # Check SMTP fields (using actual field names)
            fields = ['smtp_host', 'smtp_port', 'smtp_username', 'smtp_password', 'from_email']
            for fld in fields:
                inp = form.find('input', {'name': fld}) or form.find('input', {'id': fld})
                result.check(f"Field '{fld}'", inp is not None, f"Missing {fld}")
        
        # Check: Test email section
        test_section = soup.find(string=re.compile(r'test', re.I))
        result.check(
            "Test email functionality",
            test_section is not None,
            "No test email section found"
        )
        
        return result

    def audit_audit_page(self, client: httpx.Client) -> AuditResult:
        """Audit /admin/audit per UI_REQUIREMENTS.md section 3.7"""
        result = AuditResult(page="/admin/audit")
        
        resp = client.get(f"{self.base_url}/admin/audit")
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check: Page heading
        h1 = soup.find('h1')
        result.check(
            "Audit heading",
            h1 and ("Audit" in h1.text or "Log" in h1.text or "Activity" in h1.text),
            f"Found: {h1.text if h1 else 'None'}"
        )
        
        # Check: Table or log entries
        table = soup.find('table')
        result.check(
            "Audit log table exists",
            table is not None,
            "No table found"
        )
        
        # Check: Filter controls
        filters = soup.find_all('select') or soup.find_all('input', {'type': 'search'})
        result.check(
            "Filter controls present",
            len(filters) >= 1,
            f"Found {len(filters)} filter elements"
        )
        
        return result

    def audit_system_page(self, client: httpx.Client) -> AuditResult:
        """Audit /admin/system per UI_REQUIREMENTS.md section 3.10"""
        result = AuditResult(page="/admin/system")
        
        resp = client.get(f"{self.base_url}/admin/system")
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check: Page heading
        h1 = soup.find('h1')
        result.check(
            "System heading",
            h1 and "System" in h1.text,
            f"Found: {h1.text if h1 else 'None'}"
        )
        
        # Check: Build info
        text = soup.get_text()
        result.check(
            "Build/version info displayed",
            "version" in text.lower() or "build" in text.lower() or "git" in text.lower(),
            "No build info found"
        )
        
        return result

    def audit_pending_realms_page(self, client: httpx.Client) -> AuditResult:
        """Audit /admin/realms/pending"""
        result = AuditResult(page="/admin/realms/pending")
        
        resp = client.get(f"{self.base_url}/admin/realms/pending")
        
        if resp.status_code == 404:
            result.check("Page exists", False, "404 Not Found")
            return result
        
        if resp.status_code == 500:
            result.check("Page loads without error", False, "500 Internal Server Error")
            return result
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check: Page heading
        h1 = soup.find('h1')
        result.check(
            "Pending realms heading",
            h1 is not None,
            f"Found: {h1.text if h1 else 'None'}"
        )
        
        return result

    def audit_realm_create_page(self, client: httpx.Client) -> AuditResult:
        """Audit /admin/accounts/<id>/realms/new"""
        result = AuditResult(page="/admin/accounts/<id>/realms/new")
        
        # First, get an account ID
        accounts_resp = client.get(f"{self.base_url}/admin/accounts")
        soup = BeautifulSoup(accounts_resp.text, 'html.parser')
        
        # Find first account link
        account_link = soup.find('a', href=re.compile(r'/admin/accounts/\d+$'))
        if not account_link:
            result.check("Has accounts to test with", False, "No accounts found")
            return result
        
        account_id = re.search(r'/admin/accounts/(\d+)', account_link['href']).group(1)
        
        resp = client.get(f"{self.base_url}/admin/accounts/{account_id}/realms/new")
        
        if resp.status_code == 500:
            result.check("Page loads without error", False, "500 Internal Server Error")
            return result
        
        if resp.status_code == 404:
            result.check("Page exists", False, "404 Not Found")
            return result
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Check: Form exists
        form = soup.find('form')
        result.check(
            "Realm creation form exists",
            form is not None,
            "No form found"
        )
        
        # Check: Template buttons
        templates = soup.find_all('button', onclick=re.compile(r'applyTemplate'))
        result.check(
            "Configuration templates available",
            len(templates) >= 4,
            f"Found {len(templates)} template buttons"
        )
        
        # Check: Realm type selection
        realm_types = soup.find_all('input', {'name': 'realm_type'})
        result.check(
            "Realm type options (host/subdomain/subdomain_only)",
            len(realm_types) >= 3,
            f"Found {len(realm_types)} realm type options"
        )
        
        # Check: Record type checkboxes
        record_types = soup.find_all('input', {'name': 'record_types'})
        result.check(
            "Record type checkboxes",
            len(record_types) >= 4,
            f"Found {len(record_types)} record type options"
        )
        
        # Check: Operations checkboxes
        operations = soup.find_all('input', {'name': 'operations'})
        result.check(
            "Operation checkboxes (read/create/update/delete)",
            len(operations) >= 4,
            f"Found {len(operations)} operation options"
        )
        
        return result

    def run(self) -> int:
        """Run all audits and return total issue count."""
        print("\n" + "="*60)
        print("ADMIN UX AUDIT")
        print(f"Target: {self.base_url}")
        print("Based on docs/UI_REQUIREMENTS.md")
        print("="*60)
        
        total_issues = 0
        
        # Unauthenticated pages
        with httpx.Client(follow_redirects=True, timeout=30.0) as client:
            audits = [
                self.audit_login_page,
                self.audit_login_flow,
                self.audit_change_password_page,
            ]
            
            for audit_fn in audits:
                try:
                    result = audit_fn(client)
                    total_issues += result.report()
                except Exception as e:
                    print(f"\n❌ ERROR in {audit_fn.__name__}: {e}")
                    total_issues += 1
        
        # Authenticated pages (fresh session)
        with httpx.Client(follow_redirects=True, timeout=30.0) as client:
            self._ensure_authenticated(client)
            
            authenticated_audits = [
                self.audit_dashboard_page,
                self.audit_accounts_page,
                self.audit_accounts_new_page,
                self.audit_realm_create_page,
                self.audit_config_netcup_page,
                self.audit_config_email_page,
                self.audit_audit_page,
                self.audit_system_page,
                self.audit_pending_realms_page,
            ]
            
            for audit_fn in authenticated_audits:
                try:
                    result = audit_fn(client)
                    total_issues += result.report()
                except Exception as e:
                    print(f"\n❌ ERROR in {audit_fn.__name__}: {e}")
                    total_issues += 1
        
        print("\n" + "="*60)
        if total_issues == 0:
            print("✅ AUDIT COMPLETE: All checks passed!")
        else:
            print(f"❌ AUDIT COMPLETE: {total_issues} issues found")
        print("="*60)
        
        return total_issues


def get_default_admin_password() -> str:
    """Get admin password from deployment state or environment variable."""
    # Try environment variable first
    env_password = os.environ.get("UI_ADMIN_PASSWORD")
    if env_password:
        return env_password
    
    # Try deployment_state_local.json
    state_file = Path(__file__).parent.parent / "deployment_state_local.json"
    if state_file.exists():
        try:
            import json
            with open(state_file) as f:
                state = json.load(f)
            password = state.get("admin", {}).get("password")
            if password:
                return password
        except Exception:
            pass
    
    # Default to "admin" (fresh deployment)
    return "admin"


def main():
    parser = argparse.ArgumentParser(
        description="Admin UX Audit - Tests all admin pages against UI requirements"
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("UI_BASE_URL", "http://localhost:5100"),
        help="Base URL of the application (default: $UI_BASE_URL or http://localhost:5100)"
    )
    parser.add_argument(
        "--admin-password",
        default=None,  # Will be resolved dynamically
        help="Admin password after initial change (default: from deployment_state_local.json or $UI_ADMIN_PASSWORD)"
    )
    
    args = parser.parse_args()
    
    # Resolve password: CLI arg > env var > deployment state > "admin"
    admin_password = args.admin_password or get_default_admin_password()
    
    audit = AdminUXAudit(
        base_url=args.base_url,
        admin_password=admin_password
    )
    
    return audit.run()


if __name__ == "__main__":
    sys.exit(main())

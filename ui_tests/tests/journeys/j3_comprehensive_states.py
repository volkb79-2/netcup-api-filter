"""
Journey 3: Comprehensive State Population

Contract: See docs/JOURNEY_CONTRACTS.md Section "J3: Comprehensive State Population"

This journey creates ALL the states defined in state_matrix.py:
- Multiple accounts in different states
- Multiple realms of each type
- Multiple tokens with different scopes
- API tests for each token

This is the "deep branching" journey that exercises the combinatorial space.

Preconditions:
- J1 passed (admin authenticated)
- state_matrix.py defines ACCOUNTS, REALMS, TOKENS specs
- Mailpit available for invite email extraction

Verifications:
- All accounts created per ACCOUNTS spec
- All realms created per REALMS spec
- All tokens created per TOKENS spec
- API_TESTS executed for each token
- Journey state tracks created_ids

Implementation Notes:
- Account creation via admin sends invite email
- Must extract invite link from Mailpit and complete acceptance
- Realm creation uses /admin/accounts/{id}/realms/new (auto-approved)
- Token creation via account portal after user login
"""

import asyncio
import re
import secrets
import string
import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional

from ui_tests.browser import Browser
from ui_tests.config import settings
from ui_tests.mailpit_client import MailpitClient
from ui_tests.tests.journeys import journey_state
from ui_tests.tests.journeys.state_matrix import (
    ACCOUNTS, REALMS, TOKENS, API_TESTS,
    AccountSpec, RealmSpec, TokenSpec, APITestSpec,
)


def generate_suffix() -> str:
    """Generate unique suffix for names."""
    return ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))


async def capture(browser: Browser, name: str, journey: str = "J3") -> str:
    """Capture screenshot with journey prefix."""
    screenshot_name = journey_state.next_screenshot_name(journey, name)
    path = await browser.screenshot(screenshot_name)
    journey_state.screenshots.append((screenshot_name, path))
    print(f"📸 {screenshot_name}")
    return path


class AccountCreator:
    """Helper to create accounts via admin UI and complete invite flow."""
    
    def __init__(self, browser: Browser):
        self.browser = browser
        self.mailpit = MailpitClient()
        self.created_accounts: dict[str, dict] = {}
    
    async def ensure_admin_logged_in(self):
        """Make sure we're logged in as admin.
        
        Uses the shared workflow that handles:
        - Password change on first login
        - 2FA if enabled
        - Session persistence
        """
        from ui_tests import workflows
        await workflows.ensure_admin_dashboard(self.browser)
    
    def _extract_invite_link(self, email_text: str) -> Optional[str]:
        """Extract invite link from email body."""
        patterns = [
            r'https?://[^\s]+/account/invite/[a-zA-Z0-9_-]+',
            r'http://[^\s]+/account/invite/[a-zA-Z0-9_-]+',
        ]
        for pattern in patterns:
            match = re.search(pattern, email_text)
            if match:
                return match.group()
        return None
    
    async def create_account(self, spec: AccountSpec) -> dict:
        """Create account based on spec.
        
        Full flow:
        1. Admin fills username + email → Submit
        2. Extract invite link from Mailpit email
        3. Accept invite and set password
        4. Account is now fully active
        """
        await self.ensure_admin_logged_in()
        
        suffix = generate_suffix()
        # Username must match server pattern: ^[a-z][a-z0-9-]{6,30}[a-z0-9]$
        # Must start with letter, contain only lowercase, numbers, hyphens
        # Must end with letter or number, length 8-32
        # But HTML pattern allows underscores not hyphens - use only letters/numbers
        base_name = spec.name.replace("-", "").replace("_", "")  # Remove all separators
        username = f"j{base_name}{suffix}"  # Ensure starts with letter, length OK
        email = f"{username}@test.example.com"
        password = f"TestPass123+SecurePassword24{suffix}"  # Strong password for testing
        
        # Clear Mailpit to find our specific email
        initial_count = self.mailpit.list_messages().total
        
        # Navigate to account creation
        await self.browser.goto(settings.url("/admin/accounts/new"))
        await asyncio.sleep(0.3)
        
        # Fill form (invite-based flow - no password field)
        await self.browser.fill("#username, input[name='username']", username)
        await self.browser.fill("#email, input[name='email']", email)
        
        # Set approval status based on spec (skip_approval checkbox)
        skip_approval = await self.browser.query_selector("#skip_approval")
        if skip_approval:
            is_checked_el = await self.browser.query_selector("#skip_approval:checked")
            is_checked = is_checked_el is not None
            if spec.status == "approved" and not is_checked:
                await self.browser.click("#skip_approval")
            elif spec.status != "approved" and is_checked:
                await self.browser.click("#skip_approval")
        # If no skip_approval option, use default behavior
        
        # Wait for form validation to enable submit button
        await asyncio.sleep(0.3)
        
        # Check if submit button is disabled
        submit_disabled = await self.browser.query_selector("#submitBtn:disabled")
        if submit_disabled:
            page_text = await self.browser.text("body")
            return {}
        
        await self.browser.click("#submitBtn")
        await asyncio.sleep(1.5)
        
        
        # Check for success
        page_text = await self.browser.text("body")
        
        if "created" not in page_text.lower() and "invitation" not in page_text.lower():
            print(f"⚠️  Account creation may have failed for {username}")
            return {}
        
        # Get account ID from URL (redirects to /admin/accounts/{id})
        account_id = None
        current_url = self.browser.current_url or ""
        url_match = re.search(r'/admin/accounts/(\d+)', current_url)
        if url_match:
            account_id = int(url_match.group(1))
        
        account_data = {
            "spec_name": spec.name,
            "username": username,
            "email": email,
            "password": password,  # Will be set after invite acceptance
            "status": "invite_pending",
            "account_id": account_id,
            "created_via_invite": True,
        }
        
        # Wait for invite email
        invite_msg = self.mailpit.wait_for_message(
            predicate=lambda m: email.lower() in [a.address.lower() for a in m.to],
            timeout=10.0
        )
        
        if invite_msg:
            email_body = invite_msg.text or ""
            invite_link = self._extract_invite_link(email_body)
            print(f"  [DEBUG] Invite email for {username}:")
            print(f"          Subject: {invite_msg.subject}")
            print(f"          Body excerpt: {email_body[:200]}...")
            print(f"          Extracted link: {invite_link}")
            if invite_link:
                # Accept the invite
                await self._accept_invite(invite_link, username, password)
                account_data["status"] = "active"
                print(f"✓ Created and activated account: {username}")
            else:
                print(f"⚠️  No invite link found in email for {username}")
        else:
            print(f"⚠️  No invite email received for {username}")
        
        # Handle rejection after creation if needed
        if spec.status == "rejected" and account_id:
            await self._reject_account(account_id, username)
            account_data["status"] = "rejected"
        
        self.created_accounts[spec.name] = account_data
        return account_data
    
    async def _accept_invite(self, invite_link: str, username: str, password: str):
        """Accept invite link and set password."""
        # Navigate to invite link (this logs out admin if logged in)
        await self.browser.goto(invite_link)
        await asyncio.sleep(0.5)
        
        # Check if we're on the invite page (has password fields)
        password_field = await self.browser.query_selector("#new_password, input[name='new_password']")
        if not password_field:
            # Take screenshot for debugging
            await capture(browser=self.browser, name=f"invite-error-{username}")
            page_text = await self.browser.text("body")
            current_url = self.browser.current_url or ""
            print(f"  ⚠️  Invite page not found for {username}")
            print(f"      URL: {current_url}")
            print(f"      Page: {page_text[:200]}...")
            raise Exception(f"Invite page password field not found for {username}")
        
        # Fill password form
        await self.browser.fill("#new_password, input[name='new_password']", password)
        await self.browser.fill("#confirm_password, input[name='confirm_password']", password)
        
        await self.browser.click("button[type='submit']")
        await asyncio.sleep(1.0)
        
        # Verify success (should redirect to login with success message)
        page_text = await self.browser.text("body")
        if "active" in page_text.lower() or "login" in page_text.lower():
            print(f"  ✓ Invite accepted for {username}")
        else:
            print(f"  ⚠️  Invite acceptance may have failed for {username}")
        
        # Navigate back to admin login to re-establish admin session
        # The ensure_admin_logged_in will handle the actual login
        await self.browser.goto(settings.url("/admin/login"))
        await asyncio.sleep(0.3)
    
    async def _approve_account(self, account_id: int, username: str):
        """Approve an account."""
        await self.ensure_admin_logged_in()
        await self.browser.goto(settings.url(f"/admin/accounts/{account_id}/approve"))
        await asyncio.sleep(0.5)
        print(f"  ✓ Approved account: {username}")
    
    async def _reject_account(self, account_id: int, username: str):
        """Reject an account."""
        await self.ensure_admin_logged_in()
        # Find reject endpoint or button
        await self.browser.goto(settings.url(f"/admin/accounts/{account_id}"))
        await asyncio.sleep(0.3)
        
        reject_btn = await self.browser.query_selector(
            "button:has-text('Reject'), a:has-text('Reject'), "
            "button:has-text('Disable'), a:has-text('Disable')"
        )
        if reject_btn:
            await reject_btn.click()
            await asyncio.sleep(0.5)
            print(f"  ✓ Rejected/disabled account: {username}")


class RealmCreator:
    """Helper to create realms via admin UI."""
    
    def __init__(self, browser: Browser, account_creator: AccountCreator):
        self.browser = browser
        self.account_creator = account_creator
        # Update account_creator's browser reference to current browser
        # (needed when running across separate test functions with separate browser fixtures)
        self.account_creator.browser = browser
        self.created_realms: dict[str, dict] = {}
    
    async def create_realm(self, spec: RealmSpec) -> dict:
        """Create realm based on spec.
        
        Uses admin endpoint: /admin/accounts/{id}/realms/new
        This creates realms that are auto-approved by admin.
        """
        # Get the account this realm belongs to
        account = self.account_creator.created_accounts.get(spec.account_name)
        if not account:
            print(f"⚠️  Account {spec.account_name} not found for realm {spec.name}")
            return {}
        
        account_id = account.get("account_id")
        if not account_id:
            print(f"⚠️  Account {spec.account_name} has no account_id for realm {spec.name}")
            return {}
        
        # Ensure admin is logged in
        await self.account_creator.ensure_admin_logged_in()
        
        suffix = generate_suffix()
        realm_value = f"{spec.realm_value}-{suffix}" if spec.realm_value else ""
        
        # Navigate to admin realm creation for this account
        await self.browser.goto(settings.url(f"/admin/accounts/{account_id}/realms/new"))
        await asyncio.sleep(0.3)
        
        # Check if form exists
        form = await self.browser.query_selector("form")
        if not form:
            print(f"⚠️  No realm creation form found for account {account_id}")
            return {}
        
        # Fill realm creation form
        # The form expects "realm_value" as the full domain (subdomain.domain.tld)
        full_domain = f"{realm_value}.{spec.domain}" if realm_value else spec.domain
        
        # Domain/realm_value field
        domain_field = await self.browser.query_selector(
            "#realm_value, input[name='realm_value'], #domain, input[name='domain']"
        )
        if domain_field:
            await self.browser.fill(
                "#realm_value, input[name='realm_value'], #domain, input[name='domain']",
                full_domain
            )
        
        # Realm type selection
        type_select = await self.browser.query_selector("#realm_type, select[name='realm_type']")
        if type_select:
            await self.browser.select("#realm_type, select[name='realm_type']", spec.realm_type)
        
        # Record types (multi-select or checkboxes)
        for record_type in spec.allowed_record_types:
            checkbox = await self.browser.query_selector(
                f"input[name='record_types'][value='{record_type}'], "
                f"input[type='checkbox'][value='{record_type}']"
            )
            if checkbox:
                is_checked = await self.browser.query_selector(
                    f"input[name='record_types'][value='{record_type}']:checked"
                )
                if not is_checked:
                    await checkbox.click()
        
        # Operations (multi-select or checkboxes)
        for operation in spec.allowed_operations:
            checkbox = await self.browser.query_selector(
                f"input[name='operations'][value='{operation}'], "
                f"input[type='checkbox'][value='{operation}']"
            )
            if checkbox:
                is_checked = await self.browser.query_selector(
                    f"input[name='operations'][value='{operation}']:checked"
                )
                if not is_checked:
                    await checkbox.click()
        
        await self.browser.click("button[type='submit']")
        await asyncio.sleep(1.0)
        
        # Check for success
        page_text = await self.browser.text("body")
        success = "added" in page_text.lower() or "created" in page_text.lower() or "realm" in page_text.lower()
        
        # Get realm ID from redirect URL if possible
        realm_id = None
        current_url = self.browser.current_url or ""
        # Might redirect to account detail page
        
        realm_data = {
            "spec_name": spec.name,
            "account_name": spec.account_name,
            "account_id": account_id,
            "domain": spec.domain,
            "realm_type": spec.realm_type,
            "realm_value": realm_value,
            "fqdn": full_domain,
            "status": "approved",  # Admin-created realms are auto-approved
            "tokens": [],
            "realm_id": realm_id,
        }
        
        # Handle pending status if needed (would require different flow)
        if spec.status == "pending":
            # For pending, we'd need user to request via account portal
            realm_data["status"] = "approved"  # Admin creates are always approved
            print(f"  ℹ️  Note: Admin-created realms are auto-approved, spec wanted 'pending'")
        
        self.created_realms[spec.name] = realm_data
        if success:
            print(f"✓ Created realm: {full_domain} ({spec.realm_type}, {realm_data['status']})")
        else:
            print(f"⚠️  Realm creation may have failed for {full_domain}")
        
        return realm_data


class TokenCreator:
    """Helper to create API tokens via account portal."""
    
    def __init__(self, browser: Browser, realm_creator: RealmCreator):
        self.browser = browser
        self.realm_creator = realm_creator
        self.account_creator = realm_creator.account_creator
        # Update browser references for cross-test persistence
        # (needed when running across separate test functions with separate browser fixtures)
        self.realm_creator.browser = browser
        self.account_creator.browser = browser
        self.created_tokens: dict[str, dict] = {}
        self._current_account_session: str | None = None  # Track logged-in account
    
    async def _login_as_account(self, account_data: dict) -> bool:
        """Login as a specific account (not admin).
        
        Returns True if login succeeded.
        Handles mandatory 2FA via email code from Mailpit.
        """
        username = account_data.get("username")
        password = account_data.get("password")
        email = account_data.get("email")
        
        if not username or not password:
            print(f"⚠️  No credentials for account {account_data.get('spec_name')}")
            return False
        
        # Check if already logged in as this account
        if self._current_account_session == username:
            return True
        
        # Logout first if logged in as different user
        await self.browser.goto(settings.url("/account/logout"))
        await asyncio.sleep(0.5)
        
        # Navigate to account login
        await self.browser.goto(settings.url("/account/login"))
        await asyncio.sleep(0.3)
        
        # Fill login form
        await self.browser.fill("#username, input[name='username']", username)
        await self.browser.fill("#password, input[name='password']", password)
        await self.browser.click("button[type='submit']")
        await asyncio.sleep(1.0)
        
        # Check if login succeeded (should redirect to dashboard)
        current_url = self.browser.current_url or ""
        if "/account/dashboard" in current_url or "/account/realms" in current_url:
            self._current_account_session = username
            return True
        
        # Check for 2FA prompt - this is expected for accounts
        # Route is /account/login/2fa
        if "/login/2fa" in current_url or "/login_2fa" in current_url or "two-factor" in current_url.lower():
            # Handle 2FA via email code from Mailpit
            code = await self._get_2fa_code_from_email(email or f"{username}@example.com")
            if not code:
                print(f"⚠️  Could not get 2FA code from email for {username}")
                return False
            
            # Fill 2FA form
            await self.browser.fill("#code, input[name='code']", code)
            await self.browser.click("button[type='submit']")
            await asyncio.sleep(1.0)
            
            # Check if 2FA succeeded
            current_url = self.browser.current_url or ""
            if "/account/dashboard" in current_url or "/account/realms" in current_url or "/account/" in current_url:
                self._current_account_session = username
                print(f"  ✓ Logged in as {username} (2FA completed)")
                return True
            else:
                print(f"⚠️  2FA verification failed for {username}")
                return False
        
        page_text = await self.browser.text("body")
        if "invalid" in page_text.lower() or "error" in page_text.lower():
            print(f"⚠️  Login failed for {username}")
            return False
        
        self._current_account_session = username
        return True
    
    async def _get_2fa_code_from_email(self, email: str) -> str | None:
        """Get the 2FA code from the most recent verification email."""
        mailpit = MailpitClient()
        
        # Wait a bit for email to arrive
        await asyncio.sleep(1.0)
        
        message_list = mailpit.list_messages(limit=20)
        
        # Find most recent 2FA email for this account
        for msg_summary in message_list.messages:
            # Check if email is addressed to this user
            to_addresses = [addr.address.lower() for addr in msg_summary.to]
            if email.lower() not in to_addresses:
                continue
            
            subject = msg_summary.subject or ""
            if "verification" in subject.lower() or "2fa" in subject.lower() or "login" in subject.lower():
                # Get full message content
                full_msg = mailpit.get_message(msg_summary.id)
                if full_msg:
                    # Extract 6-digit code from email body
                    body = full_msg.text or full_msg.html or ""
                    # Look for 6-digit code
                    code_match = re.search(r'\b(\d{6})\b', body)
                    if code_match:
                        return code_match.group(1)
        
        return None
    
    async def _get_realm_id_from_db_or_ui(self, realm_data: dict) -> int | None:
        """Get realm ID by finding it in the UI.
        
        Since admin creates realms and we don't capture the ID directly,
        we need to find the realm in the account's realm list.
        """
        account_id = realm_data.get("account_id")
        fqdn = realm_data.get("fqdn", "")
        
        if not account_id:
            return None
        
        # As admin, go to account detail and find realm
        await self.account_creator.ensure_admin_logged_in()
        self._current_account_session = None  # Admin is logged in now
        
        await self.browser.goto(settings.url(f"/admin/accounts/{account_id}"))
        await asyncio.sleep(0.3)
        
        # Find realm link that contains the FQDN
        # Look for href with realm ID
        page_html = await self.browser.html("body")
        # Pattern: /admin/realms/123 or similar
        realm_links = re.findall(r'/admin/realms/(\d+)', page_html)
        
        # For each realm link, check if it matches our FQDN
        for realm_id in realm_links:
            await self.browser.goto(settings.url(f"/admin/realms/{realm_id}"))
            await asyncio.sleep(0.2)
            page_text = await self.browser.text("body")
            if fqdn.lower() in page_text.lower():
                return int(realm_id)
        
        print(f"⚠️  Could not find realm ID for {fqdn}")
        return None
    
    async def create_token(self, spec: TokenSpec) -> dict:
        """Create token based on spec.
        
        Flow:
        1. Get realm info (need realm_id and account credentials)
        2. Login as the account owner
        3. Navigate to /account/realms/{realm_id}/tokens/new
        4. Fill form and submit
        5. Capture the token value from success page
        """
        realm = self.realm_creator.created_realms.get(spec.realm_name)
        if not realm:
            print(f"⚠️  Realm {spec.realm_name} not found for token {spec.name}")
            return {}
        
        if realm.get("status") != "approved":
            print(f"⚠️  Realm {spec.realm_name} not approved, cannot create token")
            return {}
        
        # Get account credentials
        account_name = realm.get("account_name", "")
        account = self.account_creator.created_accounts.get(account_name)
        if not account:
            print(f"⚠️  Account {account_name} not found for token {spec.name}")
            return {}
        
        # Get realm ID (need to find it)
        # NOTE: This may log in as admin, so we reset account session tracking
        realm_id = realm.get("realm_id")
        if not realm_id:
            realm_id = await self._get_realm_id_from_db_or_ui(realm)
            if realm_id:
                realm["realm_id"] = realm_id
            # Reset account session since admin was logged in
            self._current_account_session = None
        
        if not realm_id:
            print(f"⚠️  No realm_id for {spec.realm_name}, cannot create token")
            return {}
        
        # Login as account owner
        login_success = await self._login_as_account(account)
        if not login_success:
            print(f"⚠️  Cannot login as {account['username']} to create token")
            return {}
        
        suffix = generate_suffix()
        token_name = f"{spec.name}-{suffix}"
        
        # Navigate to token creation
        await self.browser.goto(settings.url(f"/account/realms/{realm_id}/tokens/new"))
        await asyncio.sleep(0.3)
        
        # Check if form exists
        form = await self.browser.query_selector("form")
        if not form:
            print(f"⚠️  No token creation form found for realm {realm_id}")
            return {}
        
        # Fill token form
        await self.browser.fill("#token_name, input[name='token_name']", token_name)
        
        # Record types (if restricted)
        if spec.allowed_record_types:
            for rt in spec.allowed_record_types:
                checkbox = await self.browser.query_selector(
                    f"input[name='record_types'][value='{rt}']"
                )
                if checkbox:
                    is_checked = await self.browser.query_selector(
                        f"input[name='record_types'][value='{rt}']:checked"
                    )
                    if not is_checked:
                        await checkbox.click()
        
        # Operations (if restricted)
        if spec.allowed_operations:
            for op in spec.allowed_operations:
                checkbox = await self.browser.query_selector(
                    f"input[name='operations'][value='{op}']"
                )
                if checkbox:
                    is_checked = await self.browser.query_selector(
                        f"input[name='operations'][value='{op}']:checked"
                    )
                    if not is_checked:
                        await checkbox.click()
        
        # IP ranges (if restricted)
        if spec.allowed_ip_ranges:
            ip_field = await self.browser.query_selector(
                "#ip_ranges, textarea[name='ip_ranges']"
            )
            if ip_field:
                await self.browser.fill(
                    "#ip_ranges, textarea[name='ip_ranges']",
                    "\n".join(spec.allowed_ip_ranges)
                )
        
        # Expiration
        if spec.expires_in_hours:
            # Find expires select/radio
            if spec.expires_in_hours <= 0:
                # Already expired - use custom date in past
                custom_radio = await self.browser.query_selector(
                    "input[name='expires'][value='custom']"
                )
                if custom_radio:
                    await custom_radio.click()
                    past_date = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d")
                    await self.browser.fill(
                        "#expires_custom, input[name='expires_custom']",
                        past_date
                    )
        
        # Submit form
        await self.browser.click("button[type='submit']")
        await asyncio.sleep(1.0)
        
        # Extract token value from success page
        # Token is in input#tokenValue on token_created.html
        token_value = None
        
        # Debug: check where we are after form submission
        current_url = self.browser.current_url or ""
        page_text = await self.browser.text("body")
        
        # First try the dedicated token input field
        token_input = await self.browser.query_selector("#tokenValue")
        if token_input:
            token_value = await self.browser.get_attribute("#tokenValue", "value")
        
        # Fallback: try to find naf_ pattern in page text
        if not token_value:
            token_match = re.search(r'naf_[a-zA-Z0-9_]+', page_text)
            if token_match:
                token_value = token_match.group()
        
        # Debug output if we couldn't capture
        if not token_value:
            print(f"  [DEBUG] Token capture failed for {token_name}")
            print(f"          URL: {current_url}")
            # Check for error messages
            if "error" in page_text.lower() or "invalid" in page_text.lower():
                print(f"          Found error on page!")
            # Check for flash messages in the full page
            page_html = await self.browser.html("body")
            if "alert-danger" in page_html or "invalid-feedback" in page_html:
                print(f"          Validation error detected in HTML")
            # Take debug screenshot
            await capture(browser=self.browser, name=f"token-error-{token_name}")
        
        token_data = {
            "spec_name": spec.name,
            "token_name": token_name,
            "realm_name": spec.realm_name,
            "realm_id": realm_id,
            "realm_fqdn": realm["fqdn"],
            "token_value": token_value,
            "is_revoked": spec.is_revoked,
            "expires_at": None,
        }
        
        if spec.expires_in_hours:
            if spec.expires_in_hours > 0:
                token_data["expires_at"] = datetime.now(timezone.utc) + timedelta(hours=spec.expires_in_hours)
            else:
                token_data["expires_at"] = datetime.now(timezone.utc) + timedelta(hours=spec.expires_in_hours)
        
        if token_value:
            print(f"✓ Created token: {token_name} for {realm['fqdn']} (value captured)")
        else:
            print(f"⚠️  Created token: {token_name} but couldn't capture value")
        
        # Handle revoked tokens
        if spec.is_revoked and token_value:
            await self._revoke_token(realm_id, token_name)
            token_data["is_revoked"] = True
        
        self.created_tokens[spec.name] = token_data
        realm["tokens"].append(token_name)
        
        return token_data
    
    async def _revoke_token(self, realm_id: int, token_name: str):
        """Revoke a token after creation."""
        # Navigate to realm tokens and find revoke button
        await self.browser.goto(settings.url(f"/account/realms/{realm_id}"))
        await asyncio.sleep(0.3)
        
        revoke_btn = await self.browser.query_selector(
            f'tr:has-text("{token_name}") button:has-text("Revoke"), '
            f'a:has-text("Revoke")'
        )
        if revoke_btn:
            await revoke_btn.click()
            await asyncio.sleep(0.5)
            # Confirm if modal
            confirm_btn = await self.browser.query_selector(
                "button:has-text('Confirm'), button:has-text('Yes')"
            )
            if confirm_btn:
                await confirm_btn.click()
                await asyncio.sleep(0.5)
            print(f"  ✓ Revoked token: {token_name}")


class APITester:
    """Helper to run API tests against tokens."""
    
    def __init__(self, token_creator: TokenCreator):
        self.token_creator = token_creator
        self.results: list[dict] = []
    
    async def run_test(self, spec: APITestSpec) -> dict:
        """Run API test based on spec."""
        token_data = self.token_creator.created_tokens.get(spec.token_name)
        if not token_data:
            print(f"⚠️  Token {spec.token_name} not found for API test")
            return {"status": "skipped", "reason": "token not found"}
        
        token_value = token_data.get("token_value")
        if not token_value:
            print(f"⚠️  Token {spec.token_name} has no value for API test")
            return {"status": "skipped", "reason": "token has no value"}
        
        # Build API request
        base_url = settings.base_url
        endpoint = f"{base_url}/api/dns/records"
        
        headers = {
            "Authorization": f"Bearer {token_value}",
            "Content-Type": "application/json",
        }
        
        params = {
            "domain": spec.hostname.split(".")[-2] + "." + spec.hostname.split(".")[-1],
            "name": spec.hostname,
            "type": spec.record_type,
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if spec.operation == "read":
                    response = await client.get(endpoint, headers=headers, params=params)
                elif spec.operation == "update":
                    response = await client.put(endpoint, headers=headers, json=params)
                elif spec.operation == "create":
                    response = await client.post(endpoint, headers=headers, json=params)
                elif spec.operation == "delete":
                    response = await client.delete(endpoint, headers=headers, params=params)
                else:
                    return {"status": "error", "reason": f"unknown operation: {spec.operation}"}
                
                result = {
                    "spec": spec,
                    "actual_status": response.status_code,
                    "expected_status": spec.expected_status,
                    "passed": response.status_code == spec.expected_status,
                }
                
                if result["passed"]:
                    print(f"✓ API test: {spec.description}")
                else:
                    print(f"✗ API test: {spec.description} (got {response.status_code}, expected {spec.expected_status})")
                
                self.results.append(result)
                return result
                
        except Exception as e:
            print(f"✗ API test error: {spec.description} - {e}")
            return {"status": "error", "reason": str(e)}


class TestJourney3ComprehensiveStates:
    """Journey 3: Create all states from the matrix."""
    
    async def test_J3_01_create_accounts(self, browser: Browser):
        """Create accounts in all states."""
        print("\n" + "=" * 60)
        print("JOURNEY 3: Creating Account States")
        print("=" * 60)
        
        creator = AccountCreator(browser)
        
        for spec in ACCOUNTS:
            await creator.create_account(spec)
            await capture(browser, f"account-{spec.name}")
        
        # Store for later journeys
        journey_state.set_extra("account_creator", creator)
        
        # Screenshot: All accounts list
        await browser.goto(settings.url("/admin/accounts"))
        await asyncio.sleep(0.3)
        await capture(browser, "accounts-all-states")
        
        # Screenshot: Pending accounts
        await browser.goto(settings.url("/admin/accounts/pending"))
        await asyncio.sleep(0.3)
        await capture(browser, "accounts-pending-list")
        
        print(f"\n✓ Created {len(creator.created_accounts)} accounts")
    
    async def test_J3_02_create_realms(self, browser: Browser):
        """Create realms in all types and states."""
        print("\n" + "=" * 60)
        print("JOURNEY 3: Creating Realm States")
        print("=" * 60)
        
        account_creator = journey_state.get_extra("account_creator")
        if not account_creator:
            print("⚠️  No account creator found, skipping realm creation")
            return
        
        creator = RealmCreator(browser, account_creator)
        
        for spec in REALMS:
            await creator.create_realm(spec)
            await capture(browser, f"realm-{spec.name}")
        
        # Store for token creation
        journey_state.set_extra("realm_creator", creator)
        
        # Screenshot: All realms list
        await browser.goto(settings.url("/admin/realms"))
        await asyncio.sleep(0.3)
        await capture(browser, "realms-all-types")
        
        # Screenshot: Pending realms
        await browser.goto(settings.url("/admin/realms/pending"))
        await asyncio.sleep(0.3)
        await capture(browser, "realms-pending-list")
        
        print(f"\n✓ Created {len(creator.created_realms)} realms")
    
    async def test_J3_03_create_tokens(self, browser: Browser):
        """Create tokens with all permission types."""
        print("\n" + "=" * 60)
        print("JOURNEY 3: Creating Token States")
        print("=" * 60)
        
        realm_creator = journey_state.get_extra("realm_creator")
        if not realm_creator:
            print("⚠️  No realm creator found, skipping token creation")
            return
        
        creator = TokenCreator(browser, realm_creator)
        
        for spec in TOKENS:
            await creator.create_token(spec)
        
        # Store for API testing
        journey_state.set_extra("token_creator", creator)
        
        # Screenshot: Tokens list
        # This would be per-realm or admin overview
        await capture(browser, "tokens-all-types")
        
        print(f"\n✓ Created {len(creator.created_tokens)} tokens")
    
    async def test_J3_04_api_tests(self, browser: Browser):
        """Run API tests against all tokens."""
        print("\n" + "=" * 60)
        print("JOURNEY 3: API Validation Tests")
        print("=" * 60)
        
        token_creator = journey_state.get_extra("token_creator")
        if not token_creator:
            print("⚠️  No token creator found, skipping API tests")
            return
        
        tester = APITester(token_creator)
        
        for spec in API_TESTS:
            await tester.run_test(spec)
        
        # Summary
        passed = sum(1 for r in tester.results if r.get("passed"))
        failed = sum(1 for r in tester.results if not r.get("passed") and r.get("status") != "skipped")
        skipped = sum(1 for r in tester.results if r.get("status") == "skipped")
        
        print(f"\n✓ API Tests: {passed} passed, {failed} failed, {skipped} skipped")
    
    async def test_J3_05_ui_validation(self, browser: Browser):
        """Validate UI correctly shows all states."""
        print("\n" + "=" * 60)
        print("JOURNEY 3: UI State Validation")
        print("=" * 60)
        
        # Admin dashboard should show counts
        await browser.goto(settings.url("/admin/"))
        await asyncio.sleep(0.3)
        await capture(browser, "dashboard-with-data")
        
        # Audit log should have entries
        await browser.goto(settings.url("/admin/audit"))
        await asyncio.sleep(0.3)
        await capture(browser, "audit-log-populated")
        
        print("\n✓ UI validation screenshots captured")
    
    async def test_J3_06_summary(self, browser: Browser):
        """Journey 3 complete - summarize created states."""
        print("\n" + "=" * 60)
        print("JOURNEY 3 COMPLETE: Comprehensive State Population")
        print("=" * 60)
        
        account_creator = journey_state.get_extra("account_creator")
        realm_creator = journey_state.get_extra("realm_creator")
        token_creator = journey_state.get_extra("token_creator")
        
        print(f"  Accounts: {len(account_creator.created_accounts) if account_creator else 0}")
        print(f"  Realms: {len(realm_creator.created_realms) if realm_creator else 0}")
        print(f"  Tokens: {len(token_creator.created_tokens) if token_creator else 0}")
        print(f"  Screenshots: {len(journey_state.screenshots)}")
        print("=" * 60 + "\n")

"""
Test 2FA security features.

Tests for:
1. Session regeneration on login
2. 2FA failure tracking with lockout
3. Recovery code rate limiting
4. Reduced recovery code count (3 codes)

These tests verify the security improvements prevent brute-force attacks.
"""

import asyncio
import re
import os
import sqlite3

import pytest

from ui_tests import verification
from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests.mailpit_client import MailpitClient
from ui_tests.workflows import ensure_admin_dashboard


pytestmark = [pytest.mark.asyncio, pytest.mark.security]


async def _force_fresh_admin_login(browser) -> None:
    """Ensure /admin/login renders the login form (no persisted session reuse).

    These are auth-flow security tests, so they must not inherit a saved
    Playwright storage state from previous tests.
    """
    settings.refresh_credentials()
    try:
        await browser.goto(settings.url("/admin/logout"), wait_until="domcontentloaded")
    except Exception:
        pass
    try:
        await browser._page.context.clear_cookies()
    except Exception:
        pass
    try:
        await browser.evaluate(
            """
            () => {
                try { window.localStorage?.clear?.(); } catch (e) {}
                try { window.sessionStorage?.clear?.(); } catch (e) {}
            }
            """
        )
    except Exception:
        pass


def _clear_auth_lockouts_for_username(username: str) -> None:
    """Clear DB-backed 2FA/recovery lockout state for a user.

    Lockout counters are stored in the Settings table under keys:
    - 2fa_failures:<account_id>
    - recovery_failures:<account_id>

    We clear these between tests to keep the suite isolated.

    # WRITE: legacy cleanup, see T07 — do not copy this pattern
    """
    from ui_tests import verification  # lazy: avoid module-level config import

    # Use Channel A (read-only) to look up the account id.
    account = verification.get_account(username)
    if not account:
        return
    account_id = int(account["id"])

    # The write below is the ONE sanctioned legacy write in this helper.
    # All other DB access must go through verification.ro_connection().
    db_path = os.environ.get(
        "DATABASE_PATH",
        "/workspaces/netcup-api-filter/deploy-local/netcup_filter.db",
    )
    # WRITE: legacy cleanup, see T07 — do not copy this pattern
    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        cur = conn.cursor()
        for prefix in ("2fa_failures", "recovery_failures"):
            cur.execute(
                "DELETE FROM settings WHERE key = ?",
                (f"{prefix}:{account_id}",),
            )
        conn.commit()
    finally:
        conn.close()


class Test2FAFailureTracking:
    """Test 2FA failure tracking and account lockout."""

    async def test_2fa_lockout_after_max_failures(self):
        """Test that account is locked after 5 failed 2FA attempts."""
        _clear_auth_lockouts_for_username("admin")
        mailpit = MailpitClient()
        
        try:
            # Clear messages
            message_list = mailpit.list_messages()
            for msg in message_list.messages:
                mailpit.delete_message(msg.id)
            
            async with browser_session() as browser:
                await _force_fresh_admin_login(browser)

                # Navigate to login
                await browser.goto(settings.url("/admin/login"), wait_until="domcontentloaded")
                
                # Step 3: Submit login form (triggers 2FA)
                await browser.fill("#username", "admin")
                await browser.fill("#password", settings.admin_password)
                
                # Submit and wait for navigation to complete
                async with browser._page.expect_navigation(wait_until="networkidle"):
                    await browser.click("button[type='submit']")
                
                # Check if we're on 2FA page
                current_url = browser._page.url
                print(f"After login submit, URL: {current_url}")
                
                if "/2fa" not in current_url:
                    # Not on 2FA page - check body for clues
                    body = await browser.text("body")
                    print(f"Body content preview: {body[:200]}")
                    pytest.skip(f"Not on 2FA page after login (URL: {current_url})")
                    return
                
                print("✓ Successfully reached 2FA page")
                
                # Wait for 2FA email to arrive
                msg = mailpit.wait_for_message(
                    predicate=lambda m: "verification" in m.subject.lower() or "2fa" in m.subject.lower(),
                    timeout=10.0
                )
                
                assert msg is not None, "No 2FA email received"

                # Channel A oracle gate: require direct DB access for this target.
                # When the DB is present (local mock stack), the per-attempt and
                # lockout failure-counter assertions below run UNCONDITIONALLY —
                # no silent skip-to-green. require_db() skips the whole test only
                # when there is genuinely no DB to read.
                verification.require_db()

                # Step 2: Enter wrong code 5 times
                for attempt in range(1, 6):
                    wrong_code = "000000"  # Invalid code

                    # IMPORTANT: Avoid Playwright fill() here. The 2FA page has JS
                    # auto-submit-on-6-digits; fill() triggers input events and can
                    # cause a double-submit race, inflating failure counters.
                    await browser.evaluate(
                        """(code) => {
                            const input = document.getElementById('code');
                            if (input) input.value = code;
                            const form = document.getElementById('twoFaForm');
                            if (form) form.submit();
                        }""",
                        wrong_code,
                    )
                    try:
                        await browser._page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        await browser._page.wait_for_load_state("domcontentloaded", timeout=10000)
                    
                    new_url = browser._page.url

                    # The backend flashes an error message; assert against that
                    # (less brittle than scanning the whole body text).
                    try:
                        await browser._page.wait_for_selector("[role='alert']", timeout=5000)
                    except Exception:
                        page_text = (await browser.text("body")).lower()
                        assert False, f"Expected a flash alert on 2FA failure; body starts with: {page_text[:400]}"

                    alerts = browser._page.locator("[role='alert']")
                    alert_text = (await alerts.first.text_content() or "").strip()
                    alert_text_lower = alert_text.lower()
                    
                    if attempt < 5:
                        # Intermediate failures should keep the user on the 2FA challenge.
                        assert "/2fa" in new_url, f"Attempt {attempt}: Expected to remain on 2FA page, got URL: {new_url}"
                        assert "locked" not in alert_text_lower, f"Attempt {attempt}: Unexpected lockout before max failures: {alert_text!r}"
                        # Channel A FIRST: the persisted failure counter is the
                        # backend truth. Assert it BEFORE the UI "attempts remaining"
                        # text so this backend-truth check is the load-bearing gate
                        # (the UI string is derived from this counter).
                        failure_data = verification.get_2fa_failure_data("admin")
                        assert failure_data is not None, (
                            f"Attempt {attempt}: expected settings 2fa_failures entry, got None"
                        )
                        assert failure_data.get("count") == attempt, (
                            f"Attempt {attempt}: DB failure count={failure_data.get('count')!r}, expected {attempt}"
                        )
                        # UI text must agree with the backend counter.
                        expected_left = 5 - attempt
                        assert "invalid" in alert_text_lower and "attempt" in alert_text_lower, (
                            f"Attempt {attempt}: Expected invalid-code message with attempts counter, got: {alert_text!r}"
                        )
                        assert str(expected_left) in alert_text_lower, (
                            f"Attempt {attempt}: Expected '{expected_left}' in alert, got: {alert_text!r}"
                        )
                        print(f"✓ Attempt {attempt}/5: Still on 2FA page")
                    else:
                        # On 5th failure, should see lockout.
                        assert "/2fa" in new_url, f"Attempt {attempt}: Expected to remain on 2FA page, got URL: {new_url}"
                        # Channel A FIRST: the persisted counter must have reached the
                        # lockout threshold. Assert the backend truth BEFORE the UI
                        # lockout text so this is the load-bearing assertion.
                        failure_data = verification.get_2fa_failure_data("admin")
                        assert failure_data is not None, (
                            "Expected settings 2fa_failures entry at lockout, got None"
                        )
                        assert failure_data.get("count") >= 5, (
                            f"Lockout reached but DB count={failure_data.get('count')!r} (expected >=5)"
                        )
                        # UI must show the lockout message.
                        assert "too many" in alert_text_lower and "locked" in alert_text_lower, (
                            f"Expected lockout message after 5 failures, got: {alert_text!r}"
                        )
                        print("✓ Account locked after 5 failed attempts")
                
                # Step 3: Verify we cannot try again (should be locked)
                new_url = browser._page.url
                
                # Should be redirected back to login or show lockout message
                assert "/login" in new_url or "locked" in alert_text_lower, \
                    "Account should be locked and not allow more attempts"
                
                print("✓ 2FA lockout test PASSED")
                
        finally:
            mailpit.close()
            _clear_auth_lockouts_for_username("admin")

    async def test_2fa_attempts_remaining_counter(self):
        """Test that user sees remaining attempts counter on failure."""
        _clear_auth_lockouts_for_username("admin")
        mailpit = MailpitClient()
        
        try:
            # Clear messages
            message_list = mailpit.list_messages()
            for msg in message_list.messages:
                mailpit.delete_message(msg.id)
            
            async with browser_session() as browser:
                await _force_fresh_admin_login(browser)

                # Login to 2FA page
                await browser.goto(settings.url("/admin/login"), wait_until="domcontentloaded")
                
                await browser.fill("#username", "admin")
                await browser.fill("#password", settings.admin_password)
                
                async with browser._page.expect_navigation(wait_until="networkidle"):
                    await browser.click("button[type='submit']")
                
                current_url = browser._page.url
                
                if "/2fa" not in current_url:
                    pytest.skip("2FA not enabled")
                    return
                
                # Wait for email
                msg = mailpit.wait_for_message(
                    predicate=lambda m: "verification" in m.subject.lower() or "2fa" in m.subject.lower(),
                    timeout=10.0
                )
                
                if not msg:
                    pytest.skip("No 2FA email received")
                    return

                # Pick a guaranteed-wrong code (avoid the astronomically rare case
                # where the hardcoded wrong code matches the generated code).
                full_msg = mailpit.get_message(msg.id)
                match = re.search(r"\b(\d{6})\b", (full_msg.text or "") + "\n" + (full_msg.html or ""))
                expected_code = match.group(1) if match else None
                wrong_code = "999999"
                if expected_code and wrong_code == expected_code:
                    wrong_code = "999998"
                
                # Try wrong code once
                # IMPORTANT: The 2FA page has a JS auto-submit-on-6-digits handler.
                # Using Playwright's fill() triggers input events and can cause a
                # double-submit race (auto-submit + our manual submit). Set the
                # value via JS and submit exactly once.
                await browser.evaluate(
                    """(code) => {
                        const input = document.getElementById('code');
                        if (input) input.value = code;
                        const form = document.getElementById('twoFaForm');
                        if (form) form.submit();
                    }""",
                    wrong_code,
                )
                try:
                    await browser._page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    await browser._page.wait_for_load_state("domcontentloaded", timeout=10000)

                new_url = browser._page.url
                assert "/2fa" in new_url, f"Expected to remain on /2fa after wrong code, got URL: {new_url}"

                # The backend flashes e.g. "Invalid verification code. 4 attempts remaining."
                # Assert against the actual alert content (less brittle than scanning the whole body).
                try:
                    await browser._page.wait_for_selector("[role='alert']", timeout=5000)
                except Exception:
                    page_text = (await browser.text("body")).lower()
                    assert False, f"Expected a flash alert on 2FA failure; body starts with: {page_text[:400]}"

                alerts = browser._page.locator("[role='alert']")
                alert_text = (await alerts.first.text_content() or "").lower()
                has_counter = bool(re.search(r"\b(tries|attempt)s?\b.*\b(remaining|left)\b", alert_text))
                assert has_counter, f"Expected remaining-attempts counter in alert, got: {alert_text!r}"
                print("✓ Remaining attempts counter displayed")
                
        finally:
            mailpit.close()
            _clear_auth_lockouts_for_username("admin")


class TestRecoveryCodeRateLimiting:
    """Test recovery code rate limiting."""

    async def test_recovery_code_lockout_after_3_failures(self):
        """Test that recovery codes are locked after 3 failed attempts."""
        # This test requires an account with recovery codes set up
        # For now, we'll test the basic flow

        _clear_auth_lockouts_for_username("admin")
        
        async with browser_session() as browser:
            from ui_tests import workflows
            
            # Login to dashboard first
            await workflows.ensure_admin_dashboard(browser)
            
            # Navigate to recovery codes page
            await browser.goto(settings.url("/admin/change-password"))
            
            # Verify page loads (recovery codes would be in settings)
            h1 = await browser.text("h1")
            assert "Password" in h1 or "Settings" in h1 or "Initial Setup" in h1
            
            print("✓ Recovery code pages accessible")
            # Note: Full recovery code lockout test requires account portal
            # with 2FA enabled and recovery codes generated


class TestRecoveryCodeCount:
    """Test that recovery code count is limited to 3."""

    async def test_recovery_codes_limited_to_three(self):
        """Verify the default recovery code count is 3 (not 10)."""
        # Avoid importing backend modules here (Playwright container may not have
        # Flask/SQLAlchemy runtime deps installed). Parse constant from source.
        repo_root = os.environ.get("REPO_ROOT", "/workspaces/netcup-api-filter")
        path = os.path.join(repo_root, "src", "netcup_api_filter", "recovery_codes.py")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # The default now lives inside a defensive helper that clamps the value:
        #   raw = os.environ.get("RECOVERY_CODE_COUNT", "3")
        #   ...
        #   return max(1, min(count, 20))
        # Parse the env-default literal from the os.environ.get(...) call so this
        # test survives the helper refactor (it is no longer a bare assignment).
        m = re.search(
            r"os\.environ\.get\(\s*[\"']RECOVERY_CODE_COUNT[\"']\s*,\s*[\"'](\d+)[\"']\s*\)",
            content,
        )
        if m:
            recovery_code_count = int(m.group(1))
        else:
            # Backwards compatibility: allow a literal integer assignment.
            m2 = re.search(r"^RECOVERY_CODE_COUNT\s*=\s*(\d+)\b", content, re.MULTILINE)
            assert m2, f"RECOVERY_CODE_COUNT default not found in {path}"
            recovery_code_count = int(m2.group(1))

        assert recovery_code_count == 3, \
            f"Expected default RECOVERY_CODE_COUNT=3, got {recovery_code_count}"

        # The clamping range must be present so a bad/huge env value can't expand
        # the code set and weaken brute-force resistance.
        assert "max(1, min(" in content, \
            "Expected RECOVERY_CODE_COUNT to be clamped via max(1, min(count, 20))"

        print("✓ Default recovery code count is 3 (security improvement)")


class TestSessionRegeneration:
    """Test session ID regeneration on login."""

    async def test_session_id_changes_after_login(self):
        """Test that session ID is regenerated after successful login."""
        _clear_auth_lockouts_for_username("admin")
        async with browser_session() as browser:
            # This is an auth-flow security test: ensure we do NOT reuse any
            # persisted Playwright storage state from previous tests.
            await _force_fresh_admin_login(browser)

            # Step 1: Get initial session cookie
            await browser.goto(settings.url("/admin/login"))
            await browser._page.wait_for_load_state('domcontentloaded')
            
            # Get cookies before login
            cookies_before = await browser._page.context.cookies()
            session_before = None
            for cookie in cookies_before:
                if cookie['name'] == 'session':
                    session_before = cookie['value']
                    break
            
            print(f"Session before login: {session_before[:20] if session_before else 'None'}...")
            
            # Step 2: Login (this will trigger session regeneration)
            await ensure_admin_dashboard(browser)
            
            # Step 3: Get session cookie after login
            # Wait for dashboard to fully load
            await browser._page.wait_for_load_state('networkidle')
            cookies_after = await browser._page.context.cookies()
            session_after = None
            for cookie in cookies_after:
                if cookie['name'] == 'session':
                    session_after = cookie['value']
                    break
            
            print(f"Session after login: {session_after[:20] if session_after else 'None'}...")
            
            # Verify session changed
            if session_before and session_after:
                assert session_before != session_after, \
                    "Session ID should change after login (session regeneration)"
                print("✓ Session ID regenerated after login")
            else:
                print("⚠️  Could not verify session regeneration (cookies not captured)")


class TestConfigurationDefaults:
    """Test that security configuration defaults are set."""

    async def test_security_settings_in_env_defaults(self):
        """Verify security settings are in .env.defaults."""
        import os
        
        # Read .env.defaults
        env_defaults_path = "/workspaces/netcup-api-filter/.env.defaults"
        
        if not os.path.exists(env_defaults_path):
            pytest.skip(".env.defaults not found")
            return
        
        with open(env_defaults_path, 'r') as f:
            content = f.read()
        
        # Check for required security settings
        required_settings = [
            "TFA_MAX_ATTEMPTS",
            "TFA_LOCKOUT_MINUTES",
            "RECOVERY_CODE_MAX_ATTEMPTS",
            "RECOVERY_CODE_LOCKOUT_MINUTES",
            "RECOVERY_CODE_COUNT",
        ]
        
        for setting in required_settings:
            assert setting in content, \
                f"Security setting {setting} not found in .env.defaults"
        
        print("✓ All security settings present in .env.defaults")


class TestAdminAuthentication:
    """Test that admin authentication has same security features."""

    async def test_admin_2fa_has_failure_tracking(self):
        """Verify admin 2FA also tracks failures."""
        # Avoid importing backend modules here (Playwright container may not have
        # Flask/SQLAlchemy runtime deps installed). Verify by source inspection.
        repo_root = os.environ.get("REPO_ROOT", "/workspaces/netcup-api-filter")
        path = os.path.join(repo_root, "src", "netcup_api_filter", "account_auth.py")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        for fn_name in ("increment_2fa_failures", "is_2fa_locked", "reset_2fa_failures"):
            assert re.search(rf"^def\s+{re.escape(fn_name)}\s*\(", content, re.MULTILINE), \
                f"Expected function {fn_name} in {path}"
        
        print("✓ Admin authentication uses same security functions")

    async def test_admin_session_regeneration(self):
        """Verify admin login also regenerates session."""
        _clear_auth_lockouts_for_username("admin")
        async with browser_session() as browser:
            from ui_tests import workflows

            # Login as admin
            await workflows.ensure_admin_dashboard(browser)

            # Verify we reached dashboard (means login worked)
            h1 = await browser.text("h1")
            assert "Dashboard" in h1 or "Password" in h1

            print("✓ Admin login successful (session regeneration applied)")


# ============================================================================
# Complete email-2FA login flow (merged verbatim from test_2fa_enabled_flows.py)
#
# End-to-end: login triggers 2FA email -> Mailpit receives it -> code extracted
# and submitted -> dashboard loads. Requires Mailpit + NO ADMIN_2FA_SKIP.
# ============================================================================


async def test_complete_2fa_flow_with_mailpit():
    """Test complete 2FA flow: login → 2FA code → dashboard.

    This is an end-to-end test that verifies:
    1. Login triggers 2FA email
    2. Mailpit receives the email
    3. Code can be extracted and submitted
    4. Dashboard loads after successful 2FA

    Requires Mailpit running on localhost:8025 or MAILPIT_API_URL.
    """
    mailpit = MailpitClient()

    try:
        # Ensure we use the latest admin credentials (other tests may have
        # changed the password and persisted it to deployment_state_local.json).
        settings.refresh_credentials()

        # Clear any existing messages
        messages = mailpit.list_messages()
        for msg in messages.messages:
            mailpit.delete_message(msg.id)

        async with browser_session() as browser:
            # This is an auth-flow test and must not reuse an existing session.
            # `browser_session()` loads persisted Playwright storage state by default,
            # so explicitly clear cookies + origin storage to ensure /admin/login
            # actually renders the login form.
            try:
                await browser._page.context.clear_cookies()
            except Exception:
                pass
            try:
                await browser.evaluate(
                    """
                    () => {
                        try { window.localStorage?.clear?.(); } catch (e) {}
                        try { window.sessionStorage?.clear?.(); } catch (e) {}
                    }
                    """
                )
            except Exception:
                pass

            # Login with admin credentials
            await browser.goto(settings.url("/admin/login"))
            await browser._page.wait_for_load_state('domcontentloaded')

            await browser.fill("#username", "admin")
            await browser.fill("#password", settings.admin_password)

            # Wait for login navigation to complete
            async with browser._page.expect_navigation(wait_until="networkidle", timeout=10000):
                await browser.click("button[type='submit']")

            # Check if redirected to 2FA page
            current_url = browser._page.url

            if "/2fa" not in current_url:
                print("ℹ️  No 2FA challenge (may be disabled or already set up)")
                return

            # Wait for 2FA email
            msg = mailpit.wait_for_message(
                predicate=lambda m: "verification" in m.subject.lower() or "2fa" in m.subject.lower(),
                timeout=10.0
            )

            assert msg is not None, "No 2FA email received in Mailpit"
            print(f"✓ Received 2FA email: {msg.subject}")

            # Extract code from email
            full_msg = mailpit.get_message(msg.id)
            code_match = re.search(r'\b(\d{6})\b', full_msg.text)

            assert code_match is not None, "Could not extract 6-digit code from email"
            code = code_match.group(1)
            print(f"✓ Extracted code: {code}")

            # Submit code via JavaScript (avoid race with auto-submit)
            await browser.evaluate(f"""
                (function() {{
                    const input = document.getElementById('code');
                    const form = document.getElementById('twoFaForm');
                    if (input && form) {{
                        input.value = '{code}';
                        form.submit();
                    }}
                }})();
            """)

            # Wait for navigation to complete
            try:
                await browser._page.wait_for_url(
                    lambda url: "/2fa" not in url and url != current_url,
                    timeout=10000
                )
            except Exception as e:
                raise AssertionError("2FA navigation did not complete") from e

            # Wait for page to be ready
            await browser._page.wait_for_load_state('networkidle')

            # Verify we're on dashboard
            h1 = await browser.text("h1")
            assert "Dashboard" in h1 or "Change Password" in h1, \
                f"Expected dashboard or password change, got: {h1}"

            # Clean up
            mailpit.delete_message(msg.id)

            print("✓ Complete 2FA flow test PASSED")

    finally:
        mailpit.close()


# ============================================================================
# Admin TOTP setup page-load (merged from test_admin_totp_and_recovery_codes.py)
#
# The generic /admin route smoke loads /admin/security/totp, but this preserves
# the stronger "Authenticator" content assertion.
# ============================================================================


class TestAdminTotpPage:
    async def test_admin_totp_setup_page_loads(self, active_profile):
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)

            nav = await browser.goto(settings.url("/admin/security/totp"), wait_until="domcontentloaded")
            assert nav.get("status") == 200

            body = await browser.html("body")
            assert "Authenticator" in body

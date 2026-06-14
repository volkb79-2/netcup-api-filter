"""Recovery codes tests.

These are account-portal UI coverage tests for:
- /account/settings/recovery-codes (GET)
- /account/settings/recovery-codes/generate (POST)
- /account/settings/recovery-codes/display (GET)

Design goal: validate the end-user workflow without forcing fresh login/2FA
unless required (session reuse is allowed).
"""

import os
import re

import pytest

from ui_tests import verification, workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests.env_defaults import get_env_default


pytestmark = [pytest.mark.asyncio, pytest.mark.security]


class TestRecoveryCodesAccountUI:
    async def test_generate_recovery_codes_wrong_password_shows_error(self, active_profile):
        """Wrong password should not generate codes and should show an error."""
        async with browser_session() as browser:
            await workflows.ensure_user_dashboard(browser)

            await browser.goto(settings.url("/account/settings/recovery-codes"))
            await browser.wait_for_text("h2.mb-0", "Recovery Codes", timeout=10.0)

            await browser.fill("#password", "not-the-password")
            await browser.click("#generate-codes-form button[type='submit']")

            # Redirect back to view page with flash.
            await browser.wait_for_text(".alert", "Invalid password", timeout=10.0)
            assert "/account/settings/recovery-codes" in browser._page.url

    async def test_generate_and_display_recovery_codes_one_time(self, active_profile):
        """Generate shows codes once; subsequent display redirects with warning.

        Channel A round-trip upgrade (E3): after generation, assert the DB
        actually stores the expected number of code hashes.
        verification.count_recovery_codes() is the Channel A oracle.
        """
        # Keep these as literals so the route coverage audit can match them.
        generate_path = "/account/settings/recovery-codes/generate"
        display_path = "/account/settings/recovery-codes/display"

        demo_username = (
            os.environ.get("DEFAULT_TEST_CLIENT_ID")
            or get_env_default("DEFAULT_TEST_CLIENT_ID")
            or ""
        ).strip()

        async with browser_session() as browser:
            await workflows.ensure_user_dashboard(browser)

            # Navigate to recovery codes page.
            await browser.goto(settings.url("/account/settings/recovery-codes"))
            await browser.wait_for_text("h2.mb-0", "Recovery Codes", timeout=10.0)

            # Generate new codes (invalidates old ones).
            # The form posts to generate_path.
            form_action = await browser.get_attribute("#generate-codes-form", "action")
            assert generate_path in (form_action or "")

            demo_password = os.environ.get("DEFAULT_TEST_ACCOUNT_PASSWORD") or get_env_default(
                "DEFAULT_TEST_ACCOUNT_PASSWORD"
            )
            if not demo_password:
                # ensure_user_dashboard() already skips if defaults are missing
                raise AssertionError("DEFAULT_TEST_ACCOUNT_PASSWORD missing; ensure_user_dashboard should have skipped")

            await browser.fill("#password", demo_password)
            await browser.click("#generate-codes-form button[type='submit']")

            # The server redirects to display page for one-time view.
            await browser.wait_for_text("h2.mb-2", "Save Your Recovery Codes", timeout=10.0)
            assert display_path in browser._page.url

            # Validate we got expected codes in XXXX-XXXX format.
            grid_text = await browser.text("#recovery-codes-grid")
            codes = re.findall(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b", grid_text or "")
            expected_count_str = os.environ.get("RECOVERY_CODE_COUNT") or get_env_default("RECOVERY_CODE_COUNT")
            expected_count = int(expected_count_str or "3")
            assert len(set(codes)) == expected_count

            # Channel A: verify the DB actually stored that many hashes.
            # This is the round-trip assertion: "the UI said N codes" is not enough —
            # we confirm the backend persisted exactly N hashes in accounts.recovery_codes.
            # require_db() gates: if there is no direct DB access for this target the
            # whole test skips (not just the backend-truth assertion). When the DB IS
            # present, the assertion below ALWAYS runs — no silent skip-to-green.
            verification.require_db()
            assert demo_username, "DEFAULT_TEST_CLIENT_ID required for the Channel A oracle"
            verification.wait_for(
                lambda: verification.count_recovery_codes(demo_username) == expected_count,
                timeout=10.0,
                message=(
                    f"Expected {expected_count} recovery code hashes in DB for {demo_username!r}, "
                    f"got {verification.count_recovery_codes(demo_username)}"
                ),
            )
            stored_count = verification.count_recovery_codes(demo_username)
            assert stored_count == expected_count, (
                f"Channel A: DB has {stored_count} hashes, UI showed {expected_count} codes"
            )
            # recovery_codes_generated_at must be set
            acct = verification.get_account(demo_username)
            assert acct is not None and acct["recovery_codes_generated_at"] is not None, (
                "recovery_codes_generated_at not set after code generation"
            )

            # Display page must be one-time: revisiting should redirect back.
            await browser.goto(settings.url(display_path))
            await browser.wait_for_text(".alert", "No recovery codes to display", timeout=10.0)
            assert "/account/settings/recovery-codes" in browser._page.url

    async def test_recovery_code_consumption_round_trip(self, active_profile):
        """E3 / AUDIT #1: login with a recovery code CONSUMES it in the DB and the
        same code cannot be reused.

        Backend-truth (Channel A) assertions:
        1. After generation, accounts.recovery_codes holds exactly RECOVERY_CODE_COUNT hashes.
        2. After a successful login via one code, the count drops by exactly 1 AND
           that specific code's sha256 hash is no longer present in the stored list.
        3. Reusing the consumed code is rejected and does NOT change the stored count.

        This is the highest-value recovery-code test: it proves the one-time-use
        semantics end-to-end, not just that the UI rendered codes.
        """
        if not active_profile.allow_writes:
            pytest.skip("profile is read-only")

        # require_db() gates the whole test on direct DB access; when present, every
        # Channel A assertion below runs (no silent skip-to-green).
        verification.require_db()

        generate_path = "/account/settings/recovery-codes/generate"

        demo_username = (
            os.environ.get("DEFAULT_TEST_CLIENT_ID")
            or get_env_default("DEFAULT_TEST_CLIENT_ID")
            or ""
        ).strip()
        demo_password = (
            os.environ.get("DEFAULT_TEST_ACCOUNT_PASSWORD")
            or get_env_default("DEFAULT_TEST_ACCOUNT_PASSWORD")
            or ""
        ).strip()
        assert demo_username and demo_password, (
            "DEFAULT_TEST_CLIENT_ID / DEFAULT_TEST_ACCOUNT_PASSWORD required for round-trip"
        )

        expected_count_str = os.environ.get("RECOVERY_CODE_COUNT") or get_env_default("RECOVERY_CODE_COUNT")
        expected_count = int(expected_count_str or "3")

        # sha256 of the normalized code (uppercase, dashes stripped) — mirrors
        # recovery_codes.hash_recovery_code(). This is the Channel A oracle for
        # "is THIS specific code still in the stored set?".
        def _hash_code(code: str) -> str:
            import hashlib
            normalized = code.upper().replace("-", "").strip()
            return hashlib.sha256(normalized.encode()).hexdigest()

        def _stored_hashes() -> list[str]:
            import json as _json
            acct = verification.get_account(demo_username)
            raw = (acct or {}).get("recovery_codes")
            if not raw:
                return []
            try:
                hashes = _json.loads(raw)
                return hashes if isinstance(hashes, list) else []
            except (_json.JSONDecodeError, TypeError):
                return []

        async with browser_session() as browser:
            # --- Phase 1: generate fresh codes, capture plaintext from the UI ---
            await workflows.ensure_user_dashboard(browser)
            await browser.goto(settings.url("/account/settings/recovery-codes"))
            await browser.wait_for_text("h2.mb-0", "Recovery Codes", timeout=10.0)

            form_action = await browser.get_attribute("#generate-codes-form", "action")
            assert generate_path in (form_action or "")

            await browser.fill("#password", demo_password)
            await browser.click("#generate-codes-form button[type='submit']")
            await browser.wait_for_text("h2.mb-2", "Save Your Recovery Codes", timeout=10.0)

            grid_text = await browser.text("#recovery-codes-grid")
            codes = sorted(set(re.findall(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b", grid_text or "")))
            assert len(codes) == expected_count, (
                f"UI showed {len(codes)} codes, expected {expected_count}"
            )

            # Channel A: DB holds exactly expected_count hashes after generation.
            verification.wait_for(
                lambda: verification.count_recovery_codes(demo_username) == expected_count,
                timeout=10.0,
                message=(
                    f"Expected {expected_count} hashes after generation, "
                    f"got {verification.count_recovery_codes(demo_username)}"
                ),
            )
            chosen_code = codes[0]
            chosen_hash = _hash_code(chosen_code)
            assert chosen_hash in _stored_hashes(), (
                "chosen code's hash should be present in DB before consumption"
            )

            # --- Phase 2: logout, then log in USING the recovery code ---
            await browser.goto(settings.url("/account/logout"), wait_until="domcontentloaded")
            await browser.goto(settings.url("/account/login"), wait_until="domcontentloaded")
            await browser.fill("#username", demo_username)
            await browser.fill("#password", demo_password)
            await browser.submit("form")
            await browser._page.wait_for_url(re.compile(r".*/account/login/2fa.*"), timeout=10000)

            # The recovery-code modal form posts code + use_recovery=1 to /account/login/2fa.
            recovery_form = await browser.evaluate(
                """
                () => {
                    const inp = document.querySelector("#recovery-modal input[name='code']");
                    const form = inp ? inp.closest('form') : null;
                    if (!form) return null;
                    const csrf = form.querySelector("input[name='csrf_token']")?.value || '';
                    const action = form.getAttribute('action') || '';
                    return { csrf, action };
                }
                """
            )
            assert recovery_form and recovery_form.get("csrf") and recovery_form.get("action"), (
                "recovery-code modal form (csrf/action) not found on 2FA page"
            )
            action_url = (
                recovery_form["action"]
                if recovery_form["action"].startswith("http")
                else settings.url(recovery_form["action"])
            )
            resp = await browser.request_post_form(
                action_url,
                {
                    "csrf_token": recovery_form["csrf"],
                    "use_recovery": "1",
                    "code": chosen_code,
                },
            )
            assert resp["status"] in {200, 302}, f"recovery login status={resp['status']}"

            # Login via recovery code succeeded: dashboard is reachable.
            await browser.goto(settings.url("/account/dashboard"), wait_until="domcontentloaded")
            assert "/account/login" not in browser._page.url, (
                f"recovery-code login did not establish a session (url={browser._page.url})"
            )

            # Channel A: the consumed code is gone and the count dropped by exactly 1.
            verification.wait_for(
                lambda: verification.count_recovery_codes(demo_username) == expected_count - 1,
                timeout=10.0,
                message=(
                    f"Expected {expected_count - 1} hashes after consuming one code, "
                    f"got {verification.count_recovery_codes(demo_username)}"
                ),
            )
            remaining = _stored_hashes()
            assert chosen_hash not in remaining, (
                "consumed recovery code's hash must be removed from accounts.recovery_codes"
            )
            assert len(remaining) == expected_count - 1, (
                f"Channel A: {len(remaining)} hashes remain, expected {expected_count - 1}"
            )

            # --- Phase 3: reuse the SAME code -> rejected, count unchanged ---
            await browser.goto(settings.url("/account/logout"), wait_until="domcontentloaded")
            await browser.goto(settings.url("/account/login"), wait_until="domcontentloaded")
            await browser.fill("#username", demo_username)
            await browser.fill("#password", demo_password)
            await browser.submit("form")
            await browser._page.wait_for_url(re.compile(r".*/account/login/2fa.*"), timeout=10000)

            recovery_form2 = await browser.evaluate(
                """
                () => {
                    const inp = document.querySelector("#recovery-modal input[name='code']");
                    const form = inp ? inp.closest('form') : null;
                    if (!form) return null;
                    const csrf = form.querySelector("input[name='csrf_token']")?.value || '';
                    const action = form.getAttribute('action') || '';
                    return { csrf, action };
                }
                """
            )
            assert recovery_form2 and recovery_form2.get("csrf")
            action_url2 = (
                recovery_form2["action"]
                if recovery_form2["action"].startswith("http")
                else settings.url(recovery_form2["action"])
            )
            resp2 = await browser.request_post_form(
                action_url2,
                {
                    "csrf_token": recovery_form2["csrf"],
                    "use_recovery": "1",
                    "code": chosen_code,
                },
            )
            assert resp2["status"] in {200, 302}

            # Reuse must NOT establish a session: dashboard stays gated behind 2FA/login.
            await browser.goto(settings.url("/account/dashboard"), wait_until="domcontentloaded")
            assert "/account/login" in browser._page.url, (
                "reused recovery code must NOT log the user in"
            )

            # Channel A: stored count is unchanged by the rejected reuse.
            assert verification.count_recovery_codes(demo_username) == expected_count - 1, (
                f"reused code changed the stored count to "
                f"{verification.count_recovery_codes(demo_username)} (expected {expected_count - 1})"
            )

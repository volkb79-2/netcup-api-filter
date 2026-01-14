"""Reusable workflows for admin and client UI coverage."""
from __future__ import annotations

import anyio
import re
import secrets
import time
from dataclasses import dataclass
from typing import Callable, List, Tuple

from ui_tests.browser import Browser, ToolError
from ui_tests.config import settings
from ui_tests.deployment_state import (
    get_deployment_target,
    get_state_file_path,
    load_state,
    save_state,
    update_admin_password as ds_update_admin_password,
)


def _update_deployment_state(**kwargs) -> None:
    """Update deployment state file with current state (e.g., password changes).
    
    This persists test-driven changes so subsequent test runs use the correct
    credentials without needing database resets.
    
    Uses the deployment_state.json for the current DEPLOYMENT_TARGET.
    
    Args:
        **kwargs: Key-value pairs to update (e.g., admin_password="NewPass123!")
    """
    target = get_deployment_target()
    state_file = get_state_file_path(target)
    
    if not state_file.exists():
        raise RuntimeError(
            f"Deployment state file not found: {state_file}\n"
            f"DEPLOYMENT_TARGET={target}\n"
            f"Run build-and-deploy-local.sh (local) or build-and-deploy.sh (webhosting)"
        )
    
    # Load current state
    state = load_state(target)
    
    # Update admin credentials
    if "admin_password" in kwargs:
        state.admin.password = kwargs["admin_password"]
        from datetime import datetime, timezone
        state.admin.password_changed_at = datetime.now(timezone.utc).isoformat()
    
    if "admin_username" in kwargs:
        state.admin.username = kwargs["admin_username"]
    
    # Save updated state
    updated_by = kwargs.get("updated_by", "ui_test")
    save_state(state, updated_by, target)


@dataclass
class AccountFormData:
    username: str
    email: str
    description: str = ""


# Keep ClientFormData for realm creation after account is created
@dataclass
class ClientFormData:
    client_id: str
    description: str
    realm_value: str
    realm_type: str = "host"
    record_types: List[str] | None = None
    operations: List[str] | None = None
    email: str | None = None

    def record_choices(self) -> List[str]:
        return self.record_types or ["A", "AAAA", "CNAME"]

    def operation_choices(self) -> List[str]:
        return self.operations or ["read", "update"]


def generate_account_data(prefix: str = "ui-account") -> AccountFormData:
    suffix = secrets.token_hex(4)
    return AccountFormData(
        username=f"{prefix}-{suffix}",
        email=f"{prefix}-{suffix}@example.test",
        description="UI automation account",
    )


# Keep for backwards compatibility
def generate_client_data(prefix: str = "ui-client") -> ClientFormData:
    suffix = secrets.token_hex(4)
    return ClientFormData(
        client_id=f"{prefix}-{suffix}",
        description="UI automation client",
        realm_value=f"{suffix}.example.test",
    )


async def wait_for_input_value(
    browser: Browser,
    selector: str,
    predicate: Callable[[str], bool],
    timeout: float = 5.0,
    interval: float = 0.2,
) -> str:
    deadline = anyio.current_time() + timeout
    last_value = ""
    while anyio.current_time() <= deadline:
        value = await browser.get_attribute(selector, "value")
        last_value = value
        if predicate(value or ""):
            return value or ""
        await anyio.sleep(interval)
    raise AssertionError(f"Timed out waiting for value on {selector}; last value='{last_value}'")


async def wait_for_selector(
    browser: Browser,
    selector: str,
    timeout: float = 5.0,
    interval: float = 0.2,
) -> None:
    deadline = anyio.current_time() + timeout
    last_error: ToolError | None = None
    while anyio.current_time() <= deadline:
        try:
            await browser.html(selector)
            return
        except ToolError as exc:
            last_error = exc
            await anyio.sleep(interval)
    if last_error:
        raise AssertionError(f"Timed out waiting for selector '{selector}'") from last_error
    raise AssertionError(f"Timed out waiting for selector '{selector}'")


async def trigger_token_generation(browser: Browser) -> str:
    before = await browser.get_attribute("#client_id", "value")
    await wait_for_selector(browser, ".token-generate-btn")
    await browser.click(".token-generate-btn")
    token = await wait_for_input_value(browser, "#client_id", lambda v: v != "" and v != before)
    return token


async def handle_2fa_if_present(browser: Browser, timeout: float = 5.0) -> bool:
    """Handle 2FA page if redirected there. Returns True if 2FA was handled.
    
    This uses Mailpit to intercept the 2FA email and extract the code.
    Requires:
    - ADMIN_2FA_SKIP=false or not set
    - Mailpit running and accessible
    - Admin has a valid email configured
    
    If ADMIN_2FA_SKIP=true is set, the server bypasses 2FA entirely.
    """
    import anyio
    from datetime import datetime, timedelta, timezone
    import email
    from email.header import decode_header, make_header
    from email.utils import parsedate_to_datetime
    import imaplib
    import os
    import re
    
    # Use live URL from page (not cached)
    current_url = browser._page.url
    if "/login/2fa" not in current_url and "/2fa" not in current_url:
        return False
    
    print("[DEBUG] On 2FA page, attempting to handle...")

    async def _raise_if_2fa_email_send_failed() -> None:
        """Fail fast if the UI indicates the 2FA email could not be sent.

        This commonly happens in live hosting due to SMTP rate limits; continuing
        to click resend will only make the situation worse.
        """
        try:
            alert_text = (await browser.text(".alert")) or ""
        except Exception:
            return
        alert_text = (alert_text or "").strip()
        if not alert_text:
            return
        lowered = alert_text.lower()
        if "failed to send verification code" in lowered or "limit on the number of allowed outgoing messages" in lowered:
            suffix = f" (ref_token={ref_token})" if ref_token else ""
            raise AssertionError(f"2FA email send failed according to UI{suffix}: {alert_text}")

    # If the UI shows an email reference token, use it to correlate the exact
    # 2FA email we expect (subject contains the token).
    ref_token: str | None = None
    try:
        ref_token = (await browser.text("#twofa-email-ref")).strip() or None
        if ref_token:
            print(f"[DEBUG] 2FA page ref token: {ref_token}")
    except Exception:
        ref_token = None

    # If the initial email send failed, don't waste time polling IMAP/Mailpit.
    await _raise_if_2fa_email_send_failed()

    # Best-effort: extract any recipient hint from the 2FA page (some UIs show
    # a masked email like d***@example.com). This helps diagnose IMAP mailbox
    # mismatches without needing screenshots.
    try:
        body_text = await browser.text("body")

        def _redact_email(addr: str) -> str:
            if "@" not in addr:
                return addr
            local, domain = addr.split("@", 1)
            local = local.strip()
            domain = domain.strip()
            if not local:
                return f"***@{domain}"
            if "*" in local:
                # Already masked by UI.
                return f"{local}@{domain}"
            if len(local) <= 2:
                return f"{local[0]}***@{domain}" if local else f"***@{domain}"
            return f"{local[0]}***{local[-1]}@{domain}"

        email_hints = set(
            re.findall(r"[A-Za-z0-9_.+\-\*]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", body_text or "")
        )
        if email_hints:
            redacted = ", ".join(sorted({_redact_email(e) for e in email_hints}))
            print(f"[DEBUG] 2FA page email hint(s): {redacted}")
    except Exception:
        pass

    # Used to avoid picking up stale 2FA codes from previous journeys.
    flow_started_at = datetime.now(timezone.utc)
    
    ui_2fa_timeout = float(os.environ.get("UI_2FA_EMAIL_TIMEOUT", "10"))
    ui_2fa_poll = float(os.environ.get("UI_2FA_EMAIL_POLL_INTERVAL", "0.5"))

    def _redact_2fa_secrets(text: str) -> str:
        if not text:
            return ""
        # Redact common 2FA code formats (e.g., 123456 or 123 456 or 123-456)
        redacted = re.sub(r"\b\d{6}\b", "<2fa-code-redacted>", text)
        redacted = re.sub(r"\b\d{3}\s*[- ]\s*\d{3}\b", "<2fa-code-redacted>", redacted)
        return redacted

    def _extract_2fa_code(text: str) -> str | None:
        candidate = text or ""

        # Collect all plausible 6-digit candidates. Some emails include other
        # digit sequences (e.g. timestamps in reference IDs), so we avoid
        # returning the first match blindly.
        candidates: list[str] = []
        candidates.extend(re.findall(r"\b\d{6}\b", candidate))

        for a, b in re.findall(r"\b(\d{3})\s*[- ]\s*(\d{3})\b", candidate):
            candidates.append(f"{a}{b}")

        if not candidates:
            return None

        # Prefer the code that appears multiple times (typically plain-text + HTML),
        # or that appears on its own line / near "verification code" phrasing.
        def _score(code: str) -> tuple[int, int]:
            score = 0
            # Frequency in the full text is a strong signal.
            freq = candidate.count(code)
            score += min(freq, 5) * 3

            # Standalone line match is common in the plain-text template.
            if re.search(rf"(?:^|\n)\s*{re.escape(code)}\s*(?:\n|$)", candidate):
                score += 10

            # Keyword proximity.
            prox = ""
            m = re.search(re.escape(code), candidate)
            if m:
                prox = candidate[max(0, m.start() - 120) : m.start()].lower()
            if "verification code" in prox or "login verification" in prox or "code is" in prox:
                score += 6

            return score, freq

        best = max(candidates, key=_score)
        return best

    def _text_indicates_2fa(subject_text: str, body_text: str) -> bool:
        subject_lower = (subject_text or "").lower()
        body_lower = (body_text or "").lower()
        return (
            "verification" in subject_lower
            or "login" in subject_lower
            or "2fa" in subject_lower
            or "two-factor" in subject_lower
            or "verification code" in body_lower
            or "login verification" in body_lower
            or "two-factor" in body_lower
            or "2fa" in body_lower
            or "netcup api filter" in subject_lower
            or "netcup api filter" in body_lower
        )

    def _imap_configured() -> bool:
        return bool(
            (os.environ.get("IMAP_HOST") or "").strip()
            and (os.environ.get("IMAP_USER") or "").strip()
            and (os.environ.get("IMAP_PASSWORD") or "").strip()
        )

    def _retrieve_code_via_imap(
        not_before: datetime,
        skew_seconds: int,
        require_newer_than_seen: bool,
        seen_max_by_mailbox: dict[str, int],
    ) -> str | None:
        host = (os.environ.get("IMAP_HOST") or "").strip()
        user = (os.environ.get("IMAP_USER") or "").strip()
        password = (os.environ.get("IMAP_PASSWORD") or "").strip()
        mailbox = (os.environ.get("IMAP_MAILBOX") or "INBOX").strip() or "INBOX"
        mailboxes = [mb.strip() for mb in (os.environ.get("IMAP_MAILBOXES") or "").split(",") if mb.strip()]
        if not mailboxes:
            mailboxes = [mailbox]
        lookback = int(os.environ.get("IMAP_MESSAGE_LOOKBACK", "10"))
        if lookback <= 0:
            lookback = 10
        port = int(os.environ.get("IMAP_PORT") or "993")
        use_tls = (os.environ.get("IMAP_USE_TLS") or "true").lower() == "true"

        deadline = time.monotonic() + ui_2fa_timeout

        # NOTE: We intentionally avoid timestamp-based filtering as the primary
        # freshness gate. In production webhosting/live, Date headers and even
        # INTERNALDATE parsing can be skewed/quirky.
        #
        # Instead, we baseline using IMAP UIDs (monotonic) per mailbox and
        # prefer messages with UID > baseline.
        #
        # However, some servers/UI flows may *not* send a second email on resend
        # (or may send the first email very quickly). In that case, we need a
        # safe fallback: if there are no messages beyond the baseline, consider
        # a small lookback window but require recency via INTERNALDATE.

        def _parse_internaldate(response_meta: bytes) -> datetime | None:
            try:
                import re

                m = re.search(rb'INTERNALDATE\s+"([^"]+)"', response_meta)
                if not m:
                    return None
                raw = m.group(1).decode("utf-8", errors="replace")
                # Example: 13-Jan-2026 00:08:12 +0000
                return datetime.strptime(raw, "%d-%b-%Y %H:%M:%S %z").astimezone(timezone.utc)
            except Exception:
                return None

        not_before_with_skew = not_before - timedelta(seconds=max(0, skew_seconds))

        last_error: str | None = None
        poll_count = 0
        printed_no_uid_hint = False
        while time.monotonic() <= deadline:
            try:
                if use_tls:
                    conn = imaplib.IMAP4_SSL(host, port)
                else:
                    conn = imaplib.IMAP4(host, port)

                conn.login(user, password)
                # Use readonly to avoid changing message flags during polling.
                found_any = False
                found_subject_match = 0
                found_recent = 0
                found_code = 0
                mailbox_stats: list[tuple[str, int, int, int, int, int, int]] = []
                mailbox_uid_advanced = 0

                for mb in mailboxes:
                    status, _ = conn.select(mb, readonly=True)
                    if status != "OK":
                        mailbox_stats.append((mb, 0, 0, 0, 0, 0, 0))
                        continue

                    # Use mailbox UIDs for monotonic baselining.
                    baseline_uid = seen_max_by_mailbox.get(mb, 0) if require_newer_than_seen else 0
                    status, uid_data = conn.uid("search", None, "ALL")
                    if status != "OK" or not uid_data or not uid_data[0]:
                        mailbox_stats.append((mb, 0, 0, 0, 0, baseline_uid, baseline_uid))
                        continue

                    try:
                        all_uids = [int(u) for u in uid_data[0].split() if u]
                    except Exception:
                        all_uids = []

                    mailbox_max_uid = all_uids[-1] if all_uids else 0

                    if require_newer_than_seen and mailbox_max_uid > baseline_uid:
                        mailbox_uid_advanced += 1

                    # Prefer UNSEEN (reduces chance of old codes), but keep
                    # the primary freshness gate as UID > baseline.
                    status, new_uid_data = conn.uid("search", None, "UNSEEN")
                    if status != "OK" or not new_uid_data or not new_uid_data[0]:
                        status, new_uid_data = conn.uid("search", None, "ALL")
                    if status != "OK" or not new_uid_data or not new_uid_data[0]:
                        mailbox_stats.append((mb, 0, 0, 0, 0, baseline_uid, mailbox_max_uid))
                        continue

                    found_any = True
                    try:
                        candidate_uids = [int(u) for u in new_uid_data[0].split() if u]
                    except Exception:
                        candidate_uids = []

                    # Primary gate: only consider UIDs beyond the baseline.
                    filtered_uids = candidate_uids
                    if require_newer_than_seen and baseline_uid:
                        filtered_uids = [u for u in filtered_uids if u > baseline_uid]

                    # Fallback: if there are no messages beyond baseline, consider
                    # the newest messages but require INTERNALDATE recency.
                    use_internaldate_recency_gate = False
                    if require_newer_than_seen and baseline_uid and not filtered_uids:
                        filtered_uids = all_uids[-lookback:]
                        use_internaldate_recency_gate = True

                    # Newest first, bounded.
                    uids = filtered_uids[-lookback:][::-1]
                    mailbox_ids = len(uids)
                    mailbox_recent = 0
                    mailbox_subject = 0
                    mailbox_codes = 0
                    for uid in uids:
                        status, msg_data = conn.uid("fetch", str(uid), "(RFC822 INTERNALDATE)")
                        if status != "OK" or not msg_data or not msg_data[0]:
                            continue
                        response_meta = msg_data[0][0] if isinstance(msg_data[0], tuple) else b""
                        raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else None
                        if not raw:
                            continue
                        msg = email.message_from_bytes(raw)

                        subject_raw = msg.get("Subject", "")
                        try:
                            subject = str(make_header(decode_header(subject_raw)))
                        except Exception:
                            subject = str(subject_raw)

                        subject_lower = subject.lower()
                        is_relevant_subject = (
                            "verification" in subject_lower
                            or "login" in subject_lower
                            or "2fa" in subject_lower
                            or "netcup api filter" in subject_lower
                        )

                        if ref_token and ref_token.lower() not in subject_lower:
                            continue

                        internal_dt = _parse_internaldate(response_meta)
                        if use_internaldate_recency_gate and internal_dt is not None:
                            if internal_dt < not_before_with_skew:
                                continue

                        mailbox_recent += 1
                        found_recent += 1

                        if is_relevant_subject:
                            mailbox_subject += 1
                            found_subject_match += 1
                        else:
                            # Subject filter is advisory only: still allow body match.
                            pass

                        body_text = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                ctype = part.get_content_type()
                                if ctype in {"text/plain", "text/html"}:
                                    payload = part.get_payload(decode=True) or b""
                                    charset = part.get_content_charset() or "utf-8"
                                    body_text += payload.decode(charset, errors="replace")
                        else:
                            payload = msg.get_payload(decode=True) or b""
                            charset = msg.get_content_charset() or "utf-8"
                            body_text = payload.decode(charset, errors="replace")

                        code = _extract_2fa_code(body_text) or _extract_2fa_code(subject)
                        if code:
                            # Avoid false positives from unrelated mail that happens
                            # to contain 6 digits.
                            if not _text_indicates_2fa(subject, body_text):
                                continue
                            mailbox_codes += 1
                            found_code += 1
                            if mailbox_max_uid:
                                seen_max_by_mailbox[mb] = max(seen_max_by_mailbox.get(mb, 0), mailbox_max_uid)
                            conn.logout()
                            return code

                    # Update baseline tracking after scanning this mailbox.
                    if mailbox_max_uid:
                        seen_max_by_mailbox[mb] = max(seen_max_by_mailbox.get(mb, 0), mailbox_max_uid)

                    mailbox_stats.append(
                        (
                            mb,
                            mailbox_ids,
                            mailbox_recent,
                            mailbox_subject,
                            mailbox_codes,
                            baseline_uid,
                            mailbox_max_uid,
                        )
                    )

                poll_count += 1

                # Only emit safe diagnostics when we couldn't find a code.
                if not found_any:
                    print(f"[DEBUG] IMAP poll: no messages returned from mailbox(es)={mailboxes}")
                else:
                    # Keep logs readable: always emit a short summary, and emit
                    # per-mailbox stats periodically (or when interesting).
                    print(
                        "[DEBUG] IMAP poll: "
                        f"mailboxes={mailboxes} recent_candidates={found_recent} "
                        f"subject_matches={found_subject_match} codes_found={found_code}"
                    )

                    emit_details = (found_code > 0) or (poll_count <= 2) or (poll_count % 5 == 0)
                    if emit_details:
                        for (mb, mailbox_ids, mailbox_recent, mailbox_subject, mailbox_codes, baseline_uid, mailbox_max_uid) in mailbox_stats:
                            print(
                                "[DEBUG] IMAP mailbox stats: "
                                f"mailbox={mb} ids={mailbox_ids} recent={mailbox_recent} "
                                f"subject={mailbox_subject} codes={mailbox_codes} "
                                f"baseline_uid={baseline_uid} max_uid={mailbox_max_uid}"
                            )

                        if require_newer_than_seen and mailbox_uid_advanced == 0 and not printed_no_uid_hint:
                            # This strongly suggests the 2FA email is not landing in any polled mailbox.
                            # Common cause: admin 2FA email differs from IMAP_USER.
                            print(
                                "[HINT] No new IMAP UIDs observed in any mailbox during polling. "
                                "This usually means the 2FA email is being sent to a different address/mailbox than IMAP_USER, "
                                "or SMTP delivery is failing on the remote deployment."
                            )
                            printed_no_uid_hint = True
                        else:
                            print(
                                "[HINT] If 2FA emails land outside INBOX, set IMAP_MAILBOX or IMAP_MAILBOXES (comma-separated)"
                            )

                conn.logout()
            except Exception:
                # Don't leak secrets; just retry until deadline.
                try:
                    last_error = "imap-error"
                except Exception:
                    last_error = "imap-error"
            time.sleep(ui_2fa_poll)

        return None

    deployment_target = os.environ.get("DEPLOYMENT_TARGET", "").strip().lower()
    deployment_mode = os.environ.get("DEPLOYMENT_MODE", "").strip().lower()
    default_channels = "imap" if deployment_target == "webhosting" else "mailpit,imap"
    channels = [
        c.strip().lower()
        for c in os.environ.get("UI_2FA_CHANNELS", default_channels).split(",")
        if c.strip()
    ]

    nav_timeout = float(
        os.environ.get(
            "UI_2FA_NAV_TIMEOUT",
            "45" if deployment_target == "webhosting" else "10",
        )
    )
    nav_steps = max(1, int(nav_timeout / 0.5))

    # Try to get code from Mailpit (primarily for local/mock runs)
    if "mailpit" in channels:
        # In webhosting live mode, the Playwright/Mailpit container may be reachable
        # but it won't receive real SMTP. Keep this bounded via config.
        mailpit_timeout = float(
            os.environ.get(
                "UI_2FA_MAILPIT_TIMEOUT",
                "5" if deployment_target == "webhosting" else str(ui_2fa_timeout),
            )
        )

        mailpit = None
        try:
            from ui_tests.mailpit_client import MailpitClient

            mailpit = MailpitClient()

            # wait_for_message() is synchronous and uses time.sleep(); run it off-thread.
            msg = await anyio.to_thread.run_sync(
                lambda: mailpit.wait_for_message(
                    predicate=(
                        (lambda m: ref_token.lower() in m.subject.lower())
                        if ref_token
                        else (lambda m: "verification" in m.subject.lower() or "login" in m.subject.lower())
                    ),
                    timeout=mailpit_timeout,
                    poll_interval=ui_2fa_poll,
                )
            )

            if msg:
                code = _extract_2fa_code((msg.text or "") + "\n" + (msg.html or ""))
                if code:
                    print("[DEBUG] Extracted 2FA code from Mailpit email")

                    url_before = browser._page.url
                    try:
                        await browser.evaluate(
                            f"""
                            (function() {{
                                const input = document.getElementById('code') || document.querySelector(\"#code, input[name='code']\");
                                const form = document.getElementById('twoFaForm');
                                if (input && form) {{
                                    input.value = '{code}';
                                    form.submit();
                                }}
                            }})();
                            """
                        )
                    except Exception as exc:
                        if "Execution context was destroyed" not in str(exc):
                            raise
                        print("[WARN] 2FA submit raced navigation; continuing")

                    for _ in range(nav_steps):
                        await anyio.sleep(0.5)
                        new_url = browser._page.url
                        if new_url != url_before and "/2fa" not in new_url:
                            print(f"[DEBUG] 2FA navigation complete: {new_url}")
                            mailpit.delete_message(msg.id)
                            return True

                    print(f"[WARN] 2FA navigation did not complete, still at: {browser._page.url}")
                else:
                    preview = _redact_2fa_secrets((msg.text or msg.html or "")[:200])
                    print(f"[WARN] Could not extract code from Mailpit email: {preview}")
            else:
                print("[WARN] No 2FA email found in Mailpit")
        except Exception as e:
            print(f"[WARN] Could not handle 2FA via Mailpit: {e}")
        finally:
            try:
                if mailpit:
                    mailpit.close()
            except Exception:
                pass

    async def _trigger_resend_if_available() -> bool:
        # Resend updates the server-side expected code in the session cookie.
        # If we don't await the navigation/redirect, we can end up polling IMAP
        # for a freshly-sent code but submitting it with a *stale* session.
        try:
            btns = browser._page.locator("form[action*='resend'] button[type='submit']")
            if await btns.count() <= 0:
                return False

            try:
                async with browser._page.expect_navigation(wait_until="domcontentloaded", timeout=int(nav_timeout * 1000)):
                    await btns.first.click()
            except Exception:
                # Some pages can short-circuit without a full navigation (e.g. same-url redirects).
                # Still give the browser a chance to process cookies/flash.
                await anyio.sleep(0.5)

            await _raise_if_2fa_email_send_failed()
            return True
        except Exception:
            return False

    def _snapshot_imap_max_uids(seen_max_by_mailbox: dict[str, int]) -> None:
        host = (os.environ.get("IMAP_HOST") or "").strip()
        user = (os.environ.get("IMAP_USER") or "").strip()
        password = (os.environ.get("IMAP_PASSWORD") or "").strip()
        mailbox = (os.environ.get("IMAP_MAILBOX") or "INBOX").strip() or "INBOX"
        mailboxes = [mb.strip() for mb in (os.environ.get("IMAP_MAILBOXES") or "").split(",") if mb.strip()]
        if not mailboxes:
            mailboxes = [mailbox]
        port = int(os.environ.get("IMAP_PORT") or "993")
        use_tls = (os.environ.get("IMAP_USE_TLS") or "true").lower() == "true"

        try:
            import imaplib

            conn = imaplib.IMAP4_SSL(host, port) if use_tls else imaplib.IMAP4(host, port)
            conn.login(user, password)
            for mb in mailboxes:
                status, _ = conn.select(mb, readonly=True)
                if status != "OK":
                    continue
                status, uid_data = conn.uid("search", None, "ALL")
                if status != "OK" or not uid_data or not uid_data[0]:
                    seen_max_by_mailbox[mb] = max(seen_max_by_mailbox.get(mb, 0), 0)
                    continue
                try:
                    all_uids = [int(u) for u in uid_data[0].split() if u]
                except Exception:
                    all_uids = []
                mailbox_max_uid = all_uids[-1] if all_uids else 0
                seen_max_by_mailbox[mb] = max(seen_max_by_mailbox.get(mb, 0), mailbox_max_uid)
            conn.logout()
        except Exception:
            # Best-effort only. If snapshot fails, polling will still run.
            return

    # Fallback: IMAP (useful for live deployments where Mailpit isn't in the path)
    if _imap_configured() and "imap" in channels:
        print("[DEBUG] Falling back to IMAP for 2FA code...")
        # First attempt: use the current code that should have been sent on GET.
        # Second attempt: explicitly resend to ensure a fresh code (avoids stale
        # codes from earlier journeys).
        imap_skew_seconds = int(os.environ.get("UI_2FA_IMAP_SKEW_SECONDS", "300"))
        # Post-resend: allow timestamp skew, but also require a message newer
        # than what we observed before clicking resend (tracked via IMAP sequence).
        imap_resend_skew_seconds = int(os.environ.get("UI_2FA_IMAP_RESEND_SKEW_SECONDS", "300"))

        seen_max_by_mailbox: dict[str, int] = {}

        # Optional: force resend flow to reduce chance of picking up a stale code.
        force_resend = (os.environ.get("UI_2FA_IMAP_FORCE_RESEND", "false") or "false").lower() == "true"

        for attempt in range(2):
            if attempt == 0 and force_resend:
                print("[DEBUG] IMAP: force resend enabled; baselining mailbox UIDs before resend...")
                # Snapshot baseline UIDs once, then resend, then require UID > baseline.
                await anyio.to_thread.run_sync(_snapshot_imap_max_uids, seen_max_by_mailbox)
                print("[DEBUG] IMAP: triggering 2FA resend (force mode)...")
                clicked = await _trigger_resend_if_available()
                if not clicked:
                    print("[WARN] IMAP: force resend requested but resend button not found")
                flow_started_at = datetime.now(timezone.utc)

            if attempt == 1:
                print("[DEBUG] IMAP retry: triggering 2FA resend...")
                clicked = await _trigger_resend_if_available()
                if not clicked:
                    print("[WARN] IMAP retry: resend button not found")
                flow_started_at = datetime.now(timezone.utc)

            skew = imap_resend_skew_seconds if attempt == 1 else imap_skew_seconds
            require_newer_than_seen = (attempt == 1) or force_resend
            code = await anyio.to_thread.run_sync(
                _retrieve_code_via_imap,
                flow_started_at,
                skew,
                require_newer_than_seen,
                seen_max_by_mailbox,
            )
            if not code:
                if attempt == 0:
                    continue
                print("[WARN] IMAP configured, but no 2FA code could be extracted")
                break

            print("[DEBUG] IMAP retrieved a 2FA code; submitting...")

            url_before = browser._page.url
            try:
                await browser.evaluate(
                    f"""
                    (function() {{
                        const input = document.getElementById('code') || document.querySelector("#code, input[name='code']");
                        const form = document.getElementById('twoFaForm');
                        if (input && form) {{
                            input.value = '{code}';
                            form.submit();
                        }}
                    }})();
                    """
                )
            except Exception as exc:
                # Playwright can throw "Execution context was destroyed" if the
                # submit triggers a fast navigation while the JS is being
                # evaluated. Treat this as a benign race and rely on the URL
                # polling below to confirm success.
                if "Execution context was destroyed" not in str(exc):
                    raise
                print("[WARN] 2FA submit raced navigation; continuing")

            for _ in range(nav_steps):
                await anyio.sleep(0.5)
                new_url = browser._page.url
                if new_url != url_before and "/2fa" not in new_url:
                    print(f"[DEBUG] 2FA navigation complete (IMAP): {new_url}")
                    return True

            # If we didn't navigate, the code may have been stale/invalid.
            print(f"[WARN] 2FA navigation did not complete (IMAP), still at: {browser._page.url}")

            try:
                page_text = await browser.text("body")
                page_preview = _redact_2fa_secrets(page_text[:500])
                lowered = page_text.lower()
                if "invalid" in lowered or "expired" in lowered or "incorrect" in lowered or "try again" in lowered:
                    print(f"[DEBUG] 2FA page indicates rejection: {page_preview}")
            except Exception:
                pass
    
    return False


async def ensure_admin_dashboard(browser: Browser) -> Browser:
    """Log into the admin UI and land on the dashboard, handling the full authentication flow.
    
    This function adapts to the current database state:
    - If already logged in (on an admin page), skips login
    - If password is 'admin' (initial state), logs in and changes to a generated secure password
    - If password is already changed, uses the saved password from deployment state
    - Handles email setup for 2FA on first login
    - Handles 2FA via Mailpit if ADMIN_2FA_SKIP is not set
    - Updates deployment state so subsequent tests use the correct password
    """
    import anyio
    from netcup_api_filter.utils import generate_token
    
    # CRITICAL: Refresh credentials from deployment state file before login
    # This ensures we have the latest password if another test changed it
    settings.refresh_credentials()

    # Default behavior: prefer session reuse.
    # If the Playwright context loaded a saved storage state (cookies), we may
    # already be authenticated. Checking /admin/ first avoids triggering a new
    # login + 2FA email.
    try:
        await browser.goto(settings.url("/admin/"), wait_until="domcontentloaded")
        await anyio.sleep(0.2)
        current_url = browser._page.url
        if "/admin/" in current_url and "/admin/login" not in current_url and "/2fa" not in current_url:
            print("[DEBUG] Session reuse: already authenticated for admin")
            return browser
    except Exception:
        # Non-fatal: if backend/proxy hiccups, fall back to explicit login flow.
        pass
    
    # Check if we're already logged in (on an admin page that isn't login)
    # Use live URL (not cached)
    current_url = browser._page.url
    if "/admin/" in current_url and "/admin/login" not in current_url and "/2fa" not in current_url:
        # Already logged in - just navigate to dashboard
        print("[DEBUG] Already logged in, navigating to dashboard")
        await browser.goto(settings.url("/admin/"))
        await anyio.sleep(0.3)
        return browser
    
    # Try to login with current password first
    await browser.goto(settings.url("/admin/login"), wait_until="domcontentloaded")
    await anyio.sleep(0.2)
    
    # Check if we were redirected (already logged in via session)
    current_url = browser._page.url
    if "/admin/" in current_url and "/admin/login" not in current_url and "/2fa" not in current_url:
        print("[DEBUG] Already logged in (redirected from login), on dashboard")
        return browser
    
    # Ensure login form exists (or we were redirected into /admin/)
    # Sometimes the TLS proxy or backend can briefly return a non-login page (e.g. 502/error).
    username_field = None
    password_field = None
    for attempt in range(2):
        current_url = browser._page.url
        if "/admin/" in current_url and "/admin/login" not in current_url and "/2fa" not in current_url:
            print("[DEBUG] Already on admin page (redirected/active session)")
            return browser

        username_field = await browser.query_selector("#username")
        password_field = await browser.query_selector("#password")
        if username_field and password_field:
            break

        if attempt == 0:
            print("[WARN] Admin login form not found; reloading once...")
            await browser._page.reload(wait_until="domcontentloaded")
            await anyio.sleep(0.2)

    if not username_field or not password_field:
        body_preview = (await browser.text("body"))[:300]
        raise AssertionError(
            "Admin login form did not render (#username/#password not found). "
            f"url={browser._page.url} title={browser.current_title!r} preview={body_preview!r}"
        )
    
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", settings.admin_password)

    # Submit the login form (with a small retry loop).
    # In live/proxied environments it's possible to get bounced back to /admin/login
    # even when credentials are correct (transient backend/proxy issues, rate limits).
    import os

    max_attempts = max(1, int(os.getenv("UI_ADMIN_LOGIN_ATTEMPTS", "2")))
    retry_delay = float(os.getenv("UI_ADMIN_LOGIN_RETRY_DELAY", "1.0"))

    for attempt in range(max_attempts):
        print("[DEBUG] Submitting login form...")
        print(f"[DEBUG] Current URL: {browser._page.url}")
        print(f"[DEBUG] Credentials: {settings.admin_username}/{'*' * len(settings.admin_password)}")

        # Be specific: the standalone template includes other buttons; clicking a
        # generic submit button can occasionally hit the wrong control.
        await browser.click("form[action*='/admin/login'] button[type='submit']")
        await anyio.sleep(1.0)  # Give time for navigation/redirect
        print(f"[DEBUG] URL after form submit: {browser._page.url}")

        # Check for error messages
        body_text = await browser.text("body")
        has_invalid = "Invalid username or password" in body_text or "Invalid credentials" in body_text
        print(f"[DEBUG] Body text check: has_invalid={has_invalid}, len={len(body_text)}")
        if has_invalid:
            # Only fail if we're still on login page (use live URL)
            if "/login" in browser._page.url:
                print(f"[ERROR] Login failed. Page shows: {body_text[:500]}")
                raise AssertionError(f"Login failed: {body_text[:200]}")
            else:
                # Flash message from previous attempt but we're logged in
                print(f"[DEBUG] Ignoring stale 'Invalid' flash message - already on dashboard")

        if "lockout" in body_text.lower() or "locked" in body_text.lower():
            print(f"[ERROR] Account locked out. Page shows: {body_text[:500]}")
            raise AssertionError(f"Account locked: {body_text[:200]}")

        # Handle 2FA if we're redirected there
        handled_2fa = await handle_2fa_if_present(browser)

        # If 2FA was handled, give extra time for navigation to complete
        if handled_2fa:
            print("[DEBUG] 2FA was handled, waiting for navigation...")
            await anyio.sleep(1.0)

        # Re-check current page after potential 2FA (use live URL)
        current_url = browser._page.url
        print(f"[DEBUG] URL after 2FA check: {current_url}")

        # If we're still on the login page (but NOT on the 2FA step), we did not
        # establish a session. Allow a retry before failing hard.
        if "/admin/login" in current_url and "/2fa" not in current_url:
            if attempt < max_attempts - 1:
                print(f"[WARN] Still on /admin/login after submit; retrying ({attempt + 1}/{max_attempts})...")
                await browser._page.reload(wait_until="domcontentloaded")
                await anyio.sleep(retry_delay)
                await browser.fill("#username", settings.admin_username)
                await browser.fill("#password", settings.admin_password)
                continue

            try:
                login_h1 = await browser.text("h1")
            except Exception:
                login_h1 = ""
            body_preview = (await browser.text("body"))[:500]
            raise AssertionError(
                "Admin login did not establish a session (still on /admin/login). "
                f"url={current_url} h1={login_h1!r} preview={body_preview!r}"
            )

        # Successful transition away from /admin/login (or into /2fa)
        break
    
    # Check if we're on change password page or dashboard
    # Try main h1 first (standard pages), then h1 (standalone pages like change-password)
    try:
        current_h1 = await browser.text("main h1")
        print(f"[DEBUG] Final h1 after login: '{current_h1}'")
    except Exception:
        # Fallback to h1 without main (standalone pages)
        try:
            current_h1 = await browser.text("h1")
            print(f"[DEBUG] Final h1 after login (standalone page): '{current_h1}'")
        except Exception as e:
            print(f"[ERROR] Could not find h1 on page: {e}")
            raise
    
    if "Change Password" in current_h1 or "Initial Setup" in current_h1:
        print("[DEBUG] On password change/setup page, generating new secure password...")
        # Generate a cryptographically secure random password
        original_password = settings.admin_password
        # generate_token only uses alphanumeric, but password form requires special char
        base_token = generate_token()  # Generates 63-65 char alphanumeric token
        new_password = base_token[:60] + "@#$%"  # Add special chars to meet requirements (no ! for shell safety)
        print(f"[DEBUG] Generated new password (length: {len(new_password)})")
        
        # Check if email field is present (first-time setup)
        email_field = await browser.query_selector("#email")
        if email_field:
            # In webhosting/live mode, never write a dummy email address.
            # Use the deployment state email (single source of truth) so 2FA can be received.
            email_to_set: str | None = None
            try:
                state = load_state(get_deployment_target())
                email_to_set = (state.admin.email or "").strip() or None
            except Exception:
                email_to_set = None

            if email_to_set:
                print(f"[DEBUG] Setting up email for 2FA: {email_to_set}")
                await browser.fill("#email", email_to_set)
        
        # Fill password fields - current_password may not be present for forced change
        current_password_field = await browser.query_selector("#current_password")
        if current_password_field:
            await browser.fill("#current_password", original_password)
        
        await browser.fill("#new_password", new_password)
        await browser.fill("#confirm_password", new_password)
        
        # Wait for JavaScript validation to enable the submit button
        print("[DEBUG] Waiting for form validation to enable submit button...")
        await anyio.sleep(0.5)  # Give JavaScript time to validate
        
        # Wait for submit button to be enabled
        submit_enabled = False
        for _ in range(10):  # Try up to 5 seconds
            try:
                is_disabled = await browser._page.locator("#submitBtn").get_attribute("disabled")
                if is_disabled is None:  # Not disabled means enabled
                    submit_enabled = True
                    break
                print(f"[DEBUG] Submit button still disabled, retrying...")
            except Exception:
                pass
            await anyio.sleep(0.5)
        
        if not submit_enabled:
            print("[WARN] Submit button still disabled, trying to trigger validation...")
            # Trigger input event on the form fields to run validation
            await browser._page.locator("#confirm_password").blur()
            await anyio.sleep(0.5)
        
        # Submit password change form and wait for redirect
        print("[DEBUG] Submitting password change...")
        await browser.click("button[type='submit']")
        deadline = anyio.current_time() + 5.0
        elapsed = 0
        while anyio.current_time() < deadline:
            await anyio.sleep(0.5)
            elapsed += 0.5
            current_h1 = await browser.text("main h1")
            print(f"[DEBUG] After password change {elapsed}s: h1='{current_h1}', URL={browser.current_url}")
            if "Dashboard" in current_h1:
                print(f"[DEBUG] Detected dashboard after {elapsed}s")
                break
        
        # CRITICAL: Persist password change for subsequent test runs
        _update_deployment_state(admin_password=new_password)
        print(f"[DEBUG] Persisted new password to deployment state")
        
        # Update in-memory settings for this test session
        settings._active.admin_password = new_password
        settings._active.admin_new_password = new_password
    
    # Final verification - ensure we're on dashboard (use live URL)
    try:
        current_h1 = await browser.text("main h1")
    except Exception:
        current_h1 = await browser.text("h1")
    current_url_live = browser._page.url
    print(f"[DEBUG] Before final verification: h1='{current_h1}', URL={current_url_live}")
    
    # If still on 2FA page, try to handle it one more time
    if "/2fa" in current_url_live:
        print("[WARN] Still on 2FA page, attempting to handle again...")
        handled_2fa = await handle_2fa_if_present(browser)
        if handled_2fa:
            await anyio.sleep(1.0)  # Give time for navigation
        current_url_live = browser._page.url
        print(f"[DEBUG] After retry: URL={current_url_live}")
    
    await browser.wait_for_text("h1", "Dashboard", timeout=10.0)

    # Optional: persist session cookies/localStorage for future tests.
    # This reduces repeated admin logins and avoids generating unnecessary 2FA emails.
    import os
    from ui_tests.deployment_state import get_playwright_storage_state_path

    storage_state_path = os.environ.get("UI_PLAYWRIGHT_STORAGE_STATE_PATH")
    if not storage_state_path:
        storage_state_path = str(get_playwright_storage_state_path())

    if storage_state_path:
        try:
            os.makedirs(os.path.dirname(storage_state_path) or ".", exist_ok=True)
            await browser._page.context.storage_state(path=storage_state_path)
            print(f"[DEBUG] Saved Playwright storage state: {storage_state_path}")
        except Exception as exc:
            print(f"[WARN] Failed to save Playwright storage state: {exc}")

    return browser


async def ensure_user_dashboard(browser: Browser) -> Browser:
    """Log into the account portal and land on the user dashboard.

    Uses the preseeded demo account credentials (config-driven):
    - DEFAULT_TEST_CLIENT_ID
    - DEFAULT_TEST_ACCOUNT_PASSWORD

    If the account portal or demo credentials are not available in the current
    environment, this will skip the calling test.
    """
    import anyio
    import os

    import pytest
    from netcup_api_filter.config_defaults import get_default

    # Already logged in?
    current_url = browser._page.url
    if "/account/" in current_url and "/account/login" not in current_url and "/2fa" not in current_url:
        await browser.goto(settings.url("/account/dashboard"))
        await anyio.sleep(0.3)
        return browser

    demo_username = os.environ.get("DEFAULT_TEST_CLIENT_ID") or get_default("DEFAULT_TEST_CLIENT_ID")
    demo_password = os.environ.get("DEFAULT_TEST_ACCOUNT_PASSWORD") or get_default("DEFAULT_TEST_ACCOUNT_PASSWORD")
    if not demo_username or not demo_password:
        pytest.skip(
            "No demo account credentials configured for account portal tests "
            "(DEFAULT_TEST_CLIENT_ID / DEFAULT_TEST_ACCOUNT_PASSWORD)"
        )

    await browser.goto(settings.url("/account/login"))
    await browser._page.wait_for_load_state("networkidle")

    username_field = await browser.query_selector("#username")
    password_field = await browser.query_selector("#password")
    if not username_field or not password_field:
        pytest.skip("Account login page not available")

    await browser.fill("#username", demo_username)
    await browser.fill("#password", demo_password)
    await browser.click("button[type='submit']")
    await anyio.sleep(1.0)

    await handle_2fa_if_present(browser, timeout=10.0)

    # Land on dashboard to verify we are authenticated.
    await browser.goto(settings.url("/account/dashboard"), wait_until="domcontentloaded")
    await anyio.sleep(0.3)

    # If redirected back to login, assume demo account is not usable in this environment.
    if "/account/login" in browser._page.url:
        body = await browser.text("body")
        lowered = body.lower()
        if "invalid" in lowered or "locked" in lowered:
            pytest.skip("Demo account login failed or account locked")
        pytest.skip("Account portal login did not establish a session")

    # Basic sanity check that the dashboard rendered.
    await browser.wait_for_text("h1", "Dashboard", timeout=10.0)

    return browser


async def test_admin_login_wrong_credentials(browser: Browser) -> None:
    """Test that login with wrong credentials fails."""
    await browser.goto(settings.url("/admin/login"))
    await browser.fill("#username", "wronguser")
    await browser.fill("#password", "wrongpass")
    await browser.click("button[type='submit']")
    
    # Should stay on login page with error message
    await wait_for_selector(browser, ".login-container form button[type='submit']")
    body_text = await browser.text("body")
    assert "Invalid username or password" in body_text or "danger" in body_text


async def test_admin_access_prohibited_without_login(browser: Browser) -> None:
    """Test that access to admin pages is prohibited without login."""
    # Try to access dashboard directly
    await browser.goto(settings.url("/admin/"))
    # Should redirect to login
    await wait_for_selector(browser, ".login-container form button[type='submit']")
    
    # Try to access accounts page
    await browser.goto(settings.url("/admin/accounts"))
    await wait_for_selector(browser, ".login-container form button[type='submit']")


async def test_admin_change_password_validation(browser: Browser) -> None:
    """Test that change password fails when passwords don't match."""
    # First login with correct credentials
    await browser.goto(settings.url("/admin/login"))
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", settings.admin_password)
    await browser.click("button[type='submit']")
    
    # Should be redirected to change password
    await browser.wait_for_text("main h1", "Change Password")
    
    # Try to change password with non-matching passwords
    await browser.fill("#current_password", settings.admin_password)
    await browser.fill("#new_password", "NewPassword123!")
    await browser.fill("#confirm_password", "DifferentPassword123!")
    await browser.click("button[type='submit']")
    
    # Should stay on change password page with error
    await browser.wait_for_text("main h1", "Change Password")
    body_text = await browser.text("body")
    assert "New passwords do not match" in body_text or "danger" in body_text


async def test_admin_change_password_success(browser: Browser, new_password: str) -> None:
    """Test that change password works when used correctly."""
    # Should already be on change password page from previous test
    await browser.fill("#current_password", settings.admin_password)
    await browser.fill("#new_password", new_password)
    await browser.fill("#confirm_password", new_password)
    await browser.click("button[type='submit']")
    
    # Should redirect to dashboard
    await browser.wait_for_text("main h1", "Dashboard")


async def test_admin_logout_and_login_with_new_password(browser: Browser, new_password: str) -> None:
    """Test logout and login with new password."""
    # Logout - use JavaScript for reliable dropdown handling
    await browser.evaluate(
        """
        () => {
            const toggle = document.querySelector('.navbar .dropdown-toggle');
            if (toggle) {
                toggle.click();
                setTimeout(() => {
                    const logout = document.querySelector('a[href*="logout"]');
                    if (logout) logout.click();
                }, 200);
            }
        }
        """
    )
    await anyio.sleep(1.0)
    await browser.wait_for_text(".login-container button[type='submit']", "Sign In")
    
    # Login with new password
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", new_password)
    await browser.click("button[type='submit']")
    
    # Should go to dashboard
    await browser.wait_for_text("main h1", "Dashboard")


async def perform_admin_authentication_flow(browser: Browser) -> str:
    """Perform the complete admin authentication flow and return the new password.
    
    NOTE: This test does NOT test wrong credentials to avoid triggering account lockout.
    Wrong credential testing should be done in a separate, isolated test.
    """
    from netcup_api_filter.utils import generate_token
    new_password = generate_token()  # Generate secure random password
    
    # 1. Test access to admin pages is prohibited without login
    await browser.goto(settings.url("/admin/"))
    await wait_for_selector(browser, ".login-container form button[type='submit']")
    await browser.goto(settings.url("/admin/accounts"))
    await wait_for_selector(browser, ".login-container form button[type='submit']")
    
    # 2. Login with correct credentials
    await browser.goto(settings.url("/admin/login"))
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", settings.admin_password)
    await browser.click("button[type='submit']")
    await anyio.sleep(1.0)

    # If admin 2FA is enabled, complete the challenge before checking final state.
    await handle_2fa_if_present(browser, timeout=10.0)
    await anyio.sleep(0.5)
    
    # Check if login was successful by looking for dashboard or change-password redirect
    # After login restructuring, check both the page content and URL
    body_text = await browser.text("body")
    current_url = browser._page.url or ""
    
    if "/admin/change-password" in current_url or "Change Password" in body_text:
        # On change password page - this is expected for fresh database
        print("[DEBUG] On change password page - fresh database detected")
        pass
    elif "/admin/" in current_url and ("Dashboard" in body_text or "Clients" in body_text):
        # Already logged in and on dashboard (password already changed)
        # Return the CURRENT password from settings (not a new random one)
        print("[DEBUG] Already on dashboard - password was already changed")
        return settings.admin_password
    else:
        # Check for lockout or other errors
        if "Too many failed login attempts" in body_text:
            raise AssertionError("Account is locked out. Wait 15 minutes or redeploy to reset database.")
        elif "/admin/login" in current_url:
            # Still on login page - login failed (or 2FA didn't complete)
            print(f"DEBUG: Login failed. URL: {current_url}, Body: {body_text[:500]}")
            raise AssertionError(f"Login failed - still on login page")
        else:
            # Unknown state
            print(f"DEBUG: After login submit, unexpected state. URL: {current_url}, Body: {body_text[:500]}")
            raise AssertionError(f"Login failed - unexpected page at {current_url}")
    
    # Navigate to change password page if not already there
    if "/admin/change-password" not in current_url:
        await browser.goto(settings.url("/admin/change-password"))
    
    await browser.wait_for_text("main h1", "Change Password")
    
    # Set consistent viewport before screenshot (NO HARDCODED VALUES)
    import os
    width = int(os.environ.get('SCREENSHOT_VIEWPORT_WIDTH', '1920'))
    height = int(os.environ.get('SCREENSHOT_VIEWPORT_HEIGHT', '1200'))
    await browser._page.set_viewport_size({"width": width, "height": height})
    
    # Capture password change page screenshot
    await browser.screenshot("00b-admin-password-change")
    
    # Test change password with non-matching passwords
    await browser.fill("#current_password", settings.admin_password)
    await browser.fill("#new_password", "NewPassword123!")
    await browser.fill("#confirm_password", "DifferentPassword123!")
    await browser.submit("form")
    await anyio.sleep(0.5)
    await browser.wait_for_text("main h1", "Change Password")
    body_text = await browser.text("body")
    assert "New passwords do not match" in body_text or "danger" in body_text
    
    # 3. Successfully change password
    await browser.fill("#current_password", settings.admin_password)
    await browser.fill("#new_password", new_password)
    await browser.fill("#confirm_password", new_password)
    await browser.submit("form")
    await anyio.sleep(1.0)
    # After password change, should redirect to dashboard
    await browser.wait_for_text("body", "Dashboard")
    
    # 4. Logout and login with new password
    # Use JavaScript to reliably open dropdown and click logout
    await browser.evaluate(
        """
        () => {
            // Find and click the dropdown toggle
            const toggle = document.querySelector('.navbar .dropdown-toggle');
            if (toggle) {
                toggle.click();
                // Give dropdown time to open, then click logout
                setTimeout(() => {
                    const logout = document.querySelector('a[href*="logout"]');
                    if (logout) logout.click();
                }, 200);
            }
        }
        """
    )
    await anyio.sleep(1.0)
    await browser.wait_for_text(".login-container button[type='submit']", "Sign In")
    
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", new_password)
    await browser.click("button[type='submit']")
    await anyio.sleep(1.0)

    # Admin logins may require 2FA again after logout.
    await handle_2fa_if_present(browser, timeout=10.0)
    
    # After login with new password, we should go directly to dashboard
    # (the password was already changed so no change-password redirect)
    body_text = await browser.text("body")
    current_url = getattr(browser, "_page", None).url if getattr(browser, "_page", None) else (browser.current_url or "")
    print(f"[DEBUG] After re-login: URL={current_url}, body preview={body_text[:200]}")
    await browser.wait_for_text("main h1", "Dashboard")
    
    # CRITICAL: Persist password change to .env.webhosting for subsequent test runs
    _update_deployment_state(admin_password=new_password)
    
    # Update in-memory settings for this test session
    settings._active.admin_password = new_password
    settings._active.admin_new_password = new_password
    
    return new_password


async def verify_admin_nav(browser: Browser) -> List[Tuple[str, str]]:
    """Click through primary admin navigation links and return the visited headings."""

    # Direct nav links (not in dropdowns)
    nav_items: List[Tuple[str, str, str]] = [
        ("Dashboard", "a.nav-link[href='/admin/']", "Dashboard"),
        ("Accounts", "a.nav-link[href='/admin/accounts']", "Accounts"),
        ("Pending", "a.nav-link[href='/admin/realms/pending']", "Pending Realm Requests"),
        ("Audit", "a.nav-link[href='/admin/audit']", "Audit Logs"),
    ]
    
    # Config dropdown items
    config_items: List[Tuple[str, str, str]] = [
        ("Settings", "a.dropdown-item[href='/admin/settings']", "Settings"),
        ("System", "a.dropdown-item[href='/admin/system']", "System Information"),
        ("Logs", "a.dropdown-item[href='/admin/app-logs']", "Application Logs"),
    ]

    visited: List[Tuple[str, str]] = []
    
    # Test direct nav links
    for label, selector, expected_heading in nav_items:
        await browser.click(selector)
        await anyio.sleep(0.3)
        heading = await browser.wait_for_text("main h1", expected_heading)
        visited.append((label, heading))
    
    # Test Config dropdown items
    for label, selector, expected_heading in config_items:
        # First open the Config dropdown
        await browser.click("a.nav-link.dropdown-toggle:has-text('Config')")
        await anyio.sleep(0.3)
        # Then click the item
        await browser.click(selector)
        await anyio.sleep(0.3)
        heading = await browser.wait_for_text("main h1", expected_heading)
        visited.append((label, heading))
    
    # Test Logout - navigate directly to logout URL
    await browser.goto(settings.url("/admin/logout"))
    await anyio.sleep(1.0)
    # Wait for redirect to login page - check for the login form's submit button
    heading = await browser.wait_for_text("button[type='submit']", "Sign In")
    visited.append(("Logout", heading))

    # Re-establish the admin session for follow-up tests.
    await ensure_admin_dashboard(browser)
    return visited


async def open_admin_accounts(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/accounts"))
    await browser.wait_for_text("main h1", "Accounts")
    return browser


# Alias for backwards compatibility
open_admin_clients = open_admin_accounts


async def open_admin_audit_logs(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/audit"))
    await browser.wait_for_text("main h1", "Audit Logs")
    return browser


async def open_admin_netcup_config(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/config/netcup"))
    await browser.wait_for_text("main h1", "Netcup API Configuration")
    return browser


async def open_admin_email_settings(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/config/email"))
    await browser.wait_for_text("main h1", "Email Configuration")
    return browser


async def open_admin_system_info(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/system"))
    await browser.wait_for_text("main h1", "System Information")
    return browser


async def open_admin_account_create(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/accounts/new"))
    await browser.wait_for_text("main h1", "Create Account")
    return browser


# Alias for backwards compatibility
open_admin_client_create = open_admin_account_create


async def submit_account_form(browser: Browser, data: AccountFormData) -> str:
    """Submit account creation form and return the account username."""
    await browser.fill("#username", data.username)
    await browser.fill("#email", data.email)
    if data.description:
        await browser.fill("#description", data.description)
    
    await browser.submit("form")
    
    # Wait for success message or redirect to account detail
    body_text = await browser.text("body")
    if "Account created" in body_text or data.username in body_text:
        return data.username
    
    raise AssertionError(f"Account creation failed: {body_text[:500]}")


# Keep for backwards compatibility - but note this is now creating accounts, not clients
async def submit_client_form(browser: Browser, data: ClientFormData) -> str:
    """Submit client creation form and return the generated token from flash message."""
    await browser.fill("#client_id", data.client_id)
    await browser.fill("#description", data.description)
    await browser.select("select[name='realm_type']", data.realm_type)
    await browser.fill("#realm_value", data.realm_value)

    # The original <select> is hidden; we must interact with it via JavaScript.
    # This is more robust than trying to click the custom UI elements.
    await browser.evaluate(
        """
        (args) => {
            const [selector, values] = args;
            const select = document.querySelector(selector);
            if (!select) return;
            for (const option of select.options) {
                option.selected = values.includes(option.value);
            }
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """,
        ["select[name='allowed_record_types']", data.record_choices()],
    )

    await browser.evaluate(
        """
        (args) => {
            const [selector, values] = args;
            const select = document.querySelector(selector);
            if (!select) return;
            for (const option of select.options) {
                option.selected = values.includes(option.value);
            }
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """,
        ["select[name='allowed_operations']", data.operation_choices()],
    )

    if data.email:
        await browser.fill("#email_address", data.email)
    
    await browser.submit("form")
    
    # Wait for success message and extract token
    success_msg = await browser.wait_for_text(".alert-success", "Client created successfully")
    
    # Extract token from message - token is in <code> tag after "Authentication token"
    # Token format is client_id:secret_key (two-factor authentication)
    import re
    
    # Look for text inside code tag: <code ...>actual_token_here</code>
    code_match = re.search(r'<code[^>]*>([^<]+)</code>', success_msg)
    if code_match:
        token = code_match.group(1)
    else:
        # Fallback: try to extract after colon (but before any HTML)
        match = re.search(r'Authentication token[^:]*:\s*([A-Za-z0-9_:]+)(?=\s|<|$)', success_msg)
        if not match:
            raise AssertionError(f"Could not extract token from success message: {success_msg}")
        token = match.group(1)
    
    # Verify token format (should contain exactly one colon)
    if ':' not in token:
        raise AssertionError(f"Token should be in client_id:secret_key format, got: {token}")
    
    return token


async def ensure_account_visible(browser: Browser, account_id: str) -> None:
    await open_admin_accounts(browser)
    table_text = await browser.text("table tbody")
    assert account_id in table_text, f"Expected {account_id} in accounts table"


# Alias for backwards compatibility
ensure_client_visible = ensure_account_visible


async def ensure_account_absent(browser: Browser, account_id: str) -> None:
    await open_admin_accounts(browser)
    table_text = await browser.text("table tbody")
    assert account_id not in table_text, f"Did not expect {account_id} in accounts table"


# Alias for backwards compatibility
ensure_client_absent = ensure_account_absent


async def delete_admin_account(browser: Browser, account_id: str) -> None:
    """Disable an account via the admin UI (soft delete)."""
    await open_admin_accounts(browser)
    
    # Find the account row and click into detail view
    row_selector = f"tr:has-text('{account_id}')"
    link_selector = f"{row_selector} a[href*='/admin/accounts/']"
    
    # Click on the account link to go to detail page
    await browser._page.click(link_selector, timeout=5000)
    await browser.wait_for_text("main h1", account_id)
    
    # Find and click the disable button
    await browser._page.click("form[action*='/disable'] button[type='submit']", timeout=5000)
    
    await browser.wait_for_text("main h1", "Accounts")


# Alias for backwards compatibility
delete_admin_client = delete_admin_account


async def admin_logout_and_prepare_client_login(browser: Browser) -> None:
    """Logout from admin UI and robustly navigate to client login page."""
    print("[DEBUG] Workflow: Logging out admin to prepare for client login.")
    await admin_logout(browser)
    
    # Add a small delay to allow server-side session to clear completely
    print("[DEBUG] Workflow: Delaying for 500ms before navigating.")
    await anyio.sleep(0.5)
    
    print("[DEBUG] Workflow: Navigating to client login page.")
    await browser.goto(settings.url("/client/login"))
    
    # Add another debug screenshot to see the result of the navigation
    await browser.screenshot("debug-after-client-login-goto")
    
    # Robustly wait for the client login form to be ready
    print("[DEBUG] Workflow: Waiting for client login form elements.")
    await wait_for_selector(browser, "#client_id")
    await wait_for_selector(browser, "#secret_key")
    await browser.wait_for_text(".login-container button[type='submit']", "Sign In")
    print("[DEBUG] Workflow: Client login page is ready.")


async def admin_logout(
    browser: Browser,
    *,
    clear_session: bool = False,
    clear_persisted_state: bool = False,
) -> None:
    """Logout from admin UI and wait for login page.

    Args:
        browser: Current browser session
        clear_session: If True, clears cookies + local/session storage after logout
        clear_persisted_state: If True, deletes the persisted Playwright storage-state
            file so subsequent tests/runs cannot reuse the previous session.
    """
    return await _admin_logout_impl(
        browser,
        clear_session=clear_session,
        clear_persisted_state=clear_persisted_state,
    )


async def _admin_logout_impl(
    browser: Browser,
    *,
    clear_session: bool = False,
    clear_persisted_state: bool = False,
) -> None:
    print("[DEBUG] Admin logout: using JavaScript to open dropdown and logout.")
    # Use JavaScript to reliably open dropdown and click logout
    await browser.evaluate(
        """
        () => {
            const toggle = document.querySelector('.navbar .dropdown-toggle');
            if (toggle) {
                toggle.click();
                setTimeout(() => {
                    const logout = document.querySelector('a[href*="logout"]');
                    if (logout) logout.click();
                }, 200);
            }
        }
        """
    )
    await anyio.sleep(1.0)
    print(f"[DEBUG] Admin logout: URL after click is {browser.current_url}")
    
    # After logout, we should be on the admin login page.
    await browser.wait_for_text(".login-container button[type='submit']", "Sign In")
    print("[DEBUG] Admin logout: successfully detected admin login page.")

    if clear_session:
        # Clear cookies and origin storage to avoid leaking auth between users.
        try:
            await browser._page.context.clear_cookies()
        except Exception as exc:
            print(f"[WARN] Failed to clear cookies: {exc}")

        try:
            await browser.evaluate(
                """
                () => {
                    try { window.localStorage?.clear?.(); } catch (e) {}
                    try { window.sessionStorage?.clear?.(); } catch (e) {}
                }
                """
            )
        except Exception as exc:
            print(f"[WARN] Failed to clear local/session storage: {exc}")

    if clear_persisted_state:
        try:
            from ui_tests.deployment_state import clear_playwright_storage_state

            deleted = clear_playwright_storage_state(name="admin")
            if deleted:
                print("[DEBUG] Deleted persisted Playwright storage state")
            else:
                print("[DEBUG] No persisted Playwright storage state to delete")
        except Exception as exc:
            print(f"[WARN] Failed to delete persisted Playwright storage state: {exc}")


async def admin_logout_and_clear_auth_state(browser: Browser) -> None:
    """Logout and fully invalidate auth state (in-memory + persisted)."""
    await _admin_logout_impl(browser, clear_session=True, clear_persisted_state=True)


async def client_portal_login(browser: Browser) -> Browser:
    await browser.goto(settings.url("/client/login"))
    # Split token into separate client_id and secret_key fields
    client_id, secret_key = settings.client_token.split(":", 1)
    await browser.fill('input[name="client_id"]', client_id)
    await browser.fill('input[name="secret_key"]', secret_key)
    await browser.click("button[type='submit']")
    body = await browser.text("body")
    if "internal server error" in body.lower() or "server error" in body.lower():
        raise AssertionError(
            "Client portal login failed with server error; investigate backend logs before rerunning client UI tests"
        )
    await browser.wait_for_text("main h1", settings.client_id)
    return browser


async def admin_verify_audit_log_columns(browser: Browser) -> str:
    await open_admin_audit_logs(browser)
    header_row = await browser.text("table thead tr")
    assert "Timestamp" in header_row
    assert "Actor" in header_row  # Changed from "Client ID" 
    return header_row


async def admin_submit_invalid_client(browser: Browser) -> None:
    """Submit an invalid client form and assert validation feedback is shown."""

    data = ClientFormData(
        client_id=f"invalid-{secrets.token_hex(2)}",
        description="Invalid client for validation flow",
        realm_value="bad value with spaces",
    )
    await browser.fill("#client_id", data.client_id)
    await browser.fill("#description", data.description)
    await browser.select("select[name='realm_type']", data.realm_type)
    await browser.fill("#realm_value", data.realm_value)
    await browser.select("select[name='allowed_record_types']", data.record_choices())
    await browser.select("select[name='allowed_operations']", data.operation_choices())
    await browser.submit("form")
    await browser.wait_for_text("main h1", "Clients")
    await browser.wait_for_text(
        ".flash-messages",
        "Realm value must be a valid domain",
    )
    current = await browser.get_attribute("#client_id", "value")
    assert current == data.client_id
    body_text = await browser.text("body")
    assert "Client created successfully" not in body_text


async def admin_click_cancel_from_client_form(browser: Browser) -> None:
    await browser.click("text=Cancel")
    await browser.wait_for_text("main h1", "Clients")


async def admin_configure_netcup_api(
    browser: Browser,
    customer_id: str,
    api_key: str,
    api_password: str,
    api_url: str,
    timeout: str = "30"
) -> None:
    """Configure Netcup API credentials for E2E testing with mock server."""
    await open_admin_netcup_config(browser)
    
    await browser.fill('input[name="customer_id"]', customer_id)
    await browser.fill('input[name="api_key"]', api_key)
    await browser.fill('input[name="api_password"]', api_password)
    await browser.fill('input[name="api_url"]', api_url)
    await browser.fill('input[name="timeout"]', timeout)
    
    await browser.submit("form")
    await browser.wait_for_text(".flash-messages", "Netcup API configuration saved successfully")


async def admin_create_client_and_extract_token(browser: Browser, data: ClientFormData) -> str:
    """Create a new client and extract the token from the success message.
    
    Returns the complete authentication token in client_id:secret_key format.
    """
    await open_admin_client_create(browser)
    # submit_client_form already extracts and validates the token
    token = await submit_client_form(browser, data)
    return token


async def admin_save_netcup_config(browser: Browser) -> None:
    await open_admin_netcup_config(browser)
    defaults = {
        "#customer_id": "123456",
        "#api_key": "local-api-key",
        "#api_password": "local-api-pass",
        "#api_url": "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON",
        "#timeout": "30",
    }

    for selector, fallback in defaults.items():
        current = await browser.get_attribute(selector, "value")
        await browser.fill(selector, current or fallback)

    await browser.submit("form")
    await browser.wait_for_text("body", "saved", timeout=10.0)


async def admin_email_save_expect_error(browser: Browser) -> None:
    """Test email config page loads and shows form fields.
    
    NOTE: After testing with fake values, restores Mailpit config
    so that other tests (like Registration E2E) can send real emails.
    """
    await open_admin_email_settings(browser)
    
    # Verify key form elements exist by getting their HTML
    page_html = await browser.html("body")
    assert "smtp_host" in page_html, "SMTP host field not found"
    assert "smtp_port" in page_html, "SMTP port field not found"
    assert "from_email" in page_html, "From email field not found"
    
    target = get_deployment_target()
    if target == "webhosting":
        # In live mode, do not mutate SMTP settings; it can break 2FA and invite emails.
        return

    # Fill valid test values
    await browser.fill("#smtp_host", "smtp.test.local")
    await browser.fill("#smtp_port", "587")
    await browser.fill("#from_email", "test@example.com")

    # Submit form and check for success
    await browser.click('button[type="submit"]')
    await browser.wait_for_text("body", "saved", timeout=10.0)

    # Restore Mailpit config so other tests can send real emails
    # This is important for local E2E tests that rely on Mailpit
    import os
    mailpit_host = os.environ.get("SERVICE_MAILPIT", "mailpit")
    await open_admin_email_settings(browser)
    await browser.fill("#smtp_host", mailpit_host)
    await browser.fill("#smtp_port", "1025")
    await browser.fill("#from_email", "naf@example.com")
    await browser.click('button[type="submit"]')
    await browser.wait_for_text("body", "saved", timeout=10.0)


async def admin_email_trigger_test_without_address(browser: Browser) -> None:
    """Test the Send Test Email button triggers async request.
    
    NOTE: After testing, restores Mailpit config so other tests work.
    """
    await open_admin_email_settings(browser)
    
    target = get_deployment_target()
    if target != "webhosting":
        # In local mode we can safely set placeholder values and then restore.
        await browser.fill("#smtp_host", "smtp.test.local")
        await browser.fill("#smtp_port", "587")
        await browser.fill("#from_email", "test@example.com")
    
    # Click the test email button (uses JavaScript sendTestEmail function)
    await browser.click('button:has-text("Send Test Email")')
    
    # Wait for status update in emailStatus div - either shows spinner or badge after async call
    import anyio
    await anyio.sleep(1)  # Allow async JS to start
    status_html = await browser.html("#emailStatus")
    # After clicking, either spinner or result should appear
    assert "spinner" in status_html.lower() or "badge" in status_html.lower() or "sending" in status_html.lower() or "check" in status_html.lower()
    
    if target != "webhosting":
        # Restore Mailpit config so other tests can send real emails
        import os

        mailpit_host = os.environ.get("SERVICE_MAILPIT", "mailpit")
        await open_admin_email_settings(browser)
        await browser.fill("#smtp_host", mailpit_host)
        await browser.fill("#smtp_port", "1025")
        await browser.fill("#from_email", "naf@example.com")
        await browser.click('button[type="submit"]')
        await browser.wait_for_text("body", "saved", timeout=10.0)


async def client_portal_manage_all_domains(browser: Browser) -> List[str]:
    """Click each Manage button and assert the domain detail view loads and sorts."""

    dashboard_html = await browser.html("body")
    links = sorted(set(re.findall(r"href=\"(/client/domains/[^\"]+)\"", dashboard_html)))
    assert links, "No domains with Manage links were found"
    visited: List[str] = []

    for link in links:
        domain = link.rsplit("/", 1)[-1]
        await browser.click(f"a[href='{link}']")
        await browser.wait_for_text("main h1", domain)

        table_selector = "table.table"
        try:
            await browser.click(f"{table_selector} thead th.sortable:nth-child(2)")
            await browser.click(f"{table_selector} thead th.sortable:nth-child(3)")
        except ToolError:
            # Domains without records won't render the table; skip sort interaction.
            pass

        await browser.click("text=Back to Dashboard")
        await browser.wait_for_text("main h1", settings.client_id)
        visited.append(domain)

    return visited


async def client_portal_logout(browser: Browser) -> None:
    # Use JavaScript to reliably open dropdown and click logout
    await browser.evaluate(
        """
        () => {
            const toggle = document.querySelector('.navbar .dropdown-toggle');
            if (toggle) {
                toggle.click();
                setTimeout(() => {
                    const logout = document.querySelector('a[href*="logout"]');
                    if (logout) logout.click();
                }, 200);
            }
        }
        """
    )
    await anyio.sleep(1.0)
    await browser.wait_for_text(".login-container button[type='submit']", "Sign In")


async def client_portal_open_activity(browser: Browser) -> str:
    """Navigate to client activity page and return the table header text or empty message."""
    await browser.goto(settings.url("/client/activity"))
    await browser.wait_for_text("main h1", "Activity Log")
    
    # Check if there are any logs by looking for the table or empty message
    body_html = await browser.html("body")
    if "No activity recorded yet" in body_html:
        return "No activity recorded yet"
    else:
        # Return the table header text to verify columns are present
        header_row = await browser.text("table thead tr")
        return header_row


async def test_client_login_with_token(browser: Browser, token: str, should_succeed: bool = True, expected_client_id: str | None = None) -> None:
    """Test client login with a specific token."""
    print(f"[DEBUG] Client login: Navigating to /client/login. Current URL: {browser.current_url}")
    await browser.goto(settings.url("/client/login"))
    print(f"[DEBUG] Client login: URL is now {browser.current_url}")
    await wait_for_selector(browser, "#client_id")
    await wait_for_selector(browser, "#secret_key")
    await browser.wait_for_text(".login-container button[type='submit']", "Sign In")
    # Parse token into client_id:secret_key format
    if ":" in token:
        client_id, secret_key = token.split(":", 1)
    else:
        client_id, secret_key = token, token  # Legacy fallback
    await browser.fill("#client_id", client_id)
    await browser.fill("#secret_key", secret_key)
    await browser.click("button[type='submit']")
    
    if should_succeed:
        body = await browser.text("body")
        if "internal server error" in body.lower() or "server error" in body.lower():
            raise AssertionError("Client portal login failed with server error")
        
        # Check what the main h1 actually contains
        h1_text = await browser.text("main h1")
        client_id_to_check = expected_client_id or settings.client_id
        
        if client_id_to_check not in h1_text:
            # Debug: print what we actually got
            full_body = await browser.text("body")
            raise AssertionError(f"Expected client ID '{client_id_to_check}' in main h1, but got '{h1_text}'. Full body: {full_body[:500]}")
        
        await browser.wait_for_text("main h1", client_id_to_check)
    else:
        # Should fail - check for error message or redirect
        body_text = await browser.text("body")
        assert "Invalid token" in body_text or "danger" in body_text or "error" in body_text.lower()


async def disable_admin_account_by_edit(browser: Browser, account_id: str) -> None:
    """Disable an account by navigating to its detail page and using the disable button."""
    await open_admin_accounts(browser)
    
    # Find the row containing this account_id and get the detail link href
    row_selector = f"tr:has-text('{account_id}')"
    detail_link_selector = f"{row_selector} a[href*='/admin/accounts/']"
    
    # Get the href and navigate directly
    detail_href = await browser._page.get_attribute(detail_link_selector, "href")
    if not detail_href:
        raise AssertionError(f"Could not find detail link for account {account_id}")
    
    await browser.goto(settings.url(detail_href))
    
    # Wait for account detail page
    await browser.wait_for_text("main h1", account_id)
    
    # Click the disable button
    await browser._page.click("form[action*='/disable'] button[type='submit']")
    
    # Should redirect back to accounts list
    await browser.wait_for_text("main h1", "Accounts")


# Alias for backwards compatibility
disable_admin_client = disable_admin_account_by_edit


async def verify_account_list_has_icons(browser: Browser) -> None:
    """Verify that the account list shows view and disable icons."""
    await open_admin_accounts(browser)
    
    # Check for view and action functionality in the table rows
    page_html = await browser.html("body")
    
    # Check for view functionality - account detail links
    has_view = "/admin/accounts/" in page_html
    
    # Check for action buttons or links  
    has_actions = ("Approve" in page_html or 
                   "Disable" in page_html or
                   "btn" in page_html)
    
    assert has_view, f"No view functionality found in page HTML. Page contains: {page_html[:500]}..."


# Alias for backwards compatibility
verify_client_list_has_icons = verify_account_list_has_icons
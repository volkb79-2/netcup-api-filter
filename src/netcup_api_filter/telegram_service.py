"""Telegram integration for netcup-api-filter.

This module is intentionally config-driven and designed to be testable.

Key concepts:
- Telegram can only message users who started a chat with the bot.
- We implement "Option A" linking: UI shows a deep-link with a one-time token,
  user clicks Start in Telegram, and the bot calls back into the NAF backend
  to finalize linking.

Environment variables (see .env.defaults):
- TELEGRAM_API_BASE_URL: Base URL for Telegram Bot API.
- TELEGRAM_BOT_TOKEN: Bot token from @BotFather.
- TELEGRAM_BOT_USERNAME: Bot username (without @) used for deep-links.
- TELEGRAM_REQUEST_TIMEOUT_SECONDS: HTTP timeout.
- TELEGRAM_NOTIFICATIONS_ENABLED: Global toggle for sending Telegram messages.

Security:
- Never log full bot tokens.
- Do not trust inbound Telegram updates directly here; inbound verification
  and linking is handled in the API blueprint.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass

import httpx

from .utils import parse_bool, sha256_hex

logger = logging.getLogger(__name__)

# Placeholder secret shipped in .env.defaults so local UI tests can exercise the
# linking flow. It is public (committed to the repo), so it must never authorize
# the callback on a real deployment — get_link_callback_secret() rejects it
# unless DEPLOYMENT_TARGET is local.
LINK_CALLBACK_PLACEHOLDER = "local-test-telegram-callback-secret-change-me"

# A single pooled HTTP client, created lazily, so each Telegram send reuses the
# TCP/TLS connection instead of paying a fresh handshake per message.
_client_lock = threading.Lock()
_http_client: httpx.Client | None = None


def _truthy(value: str | None) -> bool:
    return parse_bool(value, default=False)


@dataclass(frozen=True)
class TelegramConfig:
    api_base_url: str
    bot_token: str | None
    bot_username: str | None
    timeout_seconds: float
    notifications_enabled: bool


def get_telegram_config() -> TelegramConfig:
    api_base_url = (os.environ.get("TELEGRAM_API_BASE_URL") or "https://api.telegram.org").rstrip("/")
    bot_token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip() or None
    bot_username = (os.environ.get("TELEGRAM_BOT_USERNAME") or "").strip() or None

    timeout_raw = (os.environ.get("TELEGRAM_REQUEST_TIMEOUT_SECONDS") or "10").strip()
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError:
        timeout_seconds = 10.0

    notifications_enabled = _truthy(os.environ.get("TELEGRAM_NOTIFICATIONS_ENABLED"))

    return TelegramConfig(
        api_base_url=api_base_url,
        bot_token=bot_token,
        bot_username=bot_username,
        timeout_seconds=timeout_seconds,
        notifications_enabled=notifications_enabled,
    )


def get_link_callback_secret() -> str | None:
    """Return the bot->app callback shared secret, or None if unusable.

    The placeholder value from .env.defaults is treated as "not configured" on
    any non-local deployment so that copying the defaults into production can
    never leave the linking callback authenticated by a public, repo-committed
    secret.
    """
    secret = (os.environ.get("TELEGRAM_LINK_CALLBACK_SECRET") or "").strip()
    if not secret:
        return None
    if secret == LINK_CALLBACK_PLACEHOLDER:
        target = (os.environ.get("DEPLOYMENT_TARGET") or "").strip().lower()
        if target != "local":
            logger.error(
                "TELEGRAM_LINK_CALLBACK_SECRET is the public placeholder value; "
                "refusing to enable Telegram linking. Set a strong secret per deployment."
            )
            return None
    return secret


def is_telegram_configured_for_linking() -> bool:
    cfg = get_telegram_config()
    return bool(cfg.bot_username) and bool(get_link_callback_secret())


def is_telegram_configured_for_sending() -> bool:
    cfg = get_telegram_config()
    return cfg.notifications_enabled and bool(cfg.bot_token)


def build_start_link(*, link_token: str) -> str:
    cfg = get_telegram_config()
    if not cfg.bot_username:
        raise RuntimeError("TELEGRAM_BOT_USERNAME not configured")

    # Telegram deep-link start payload is delivered to the bot via /start.
    # Keep it URL-safe and bot-friendly.
    payload = f"link_{link_token}"
    return f"https://t.me/{cfg.bot_username}?start={payload}"


# sha256_hex is re-exported from utils so existing callers
# (api.telegram, api.account) keep importing it from here.
__all__ = [
    "TelegramConfig",
    "get_telegram_config",
    "get_link_callback_secret",
    "is_telegram_configured_for_linking",
    "is_telegram_configured_for_sending",
    "build_start_link",
    "sha256_hex",
    "send_telegram_message",
]


def _get_http_client(timeout_seconds: float) -> httpx.Client:
    """Return the shared httpx client, creating it on first use (thread-safe)."""
    global _http_client
    if _http_client is None:
        with _client_lock:
            if _http_client is None:
                _http_client = httpx.Client(timeout=timeout_seconds)
    return _http_client


def send_telegram_message(*, chat_id: str, text: str) -> bool:
    """Send a Telegram message.

    Returns True if the request succeeded (HTTP 200 + ok=true), False otherwise.

    This function is safe to call even when Telegram is disabled: it will
    no-op and return False.
    """

    cfg = get_telegram_config()
    if not cfg.notifications_enabled:
        logger.debug("Telegram notifications disabled")
        return False

    if not cfg.bot_token:
        logger.warning("Telegram notifications enabled, but TELEGRAM_BOT_TOKEN not set")
        return False

    url = f"{cfg.api_base_url}/bot{cfg.bot_token}/sendMessage"

    try:
        client = _get_http_client(cfg.timeout_seconds)
        resp = client.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=cfg.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        ok = bool(data.get("ok"))
        if not ok:
            logger.warning(f"Telegram sendMessage returned ok=false for chat_id={chat_id}")
        return ok
    except Exception as exc:
        logger.error(f"Telegram sendMessage failed for chat_id={chat_id}: {exc}")
        return False

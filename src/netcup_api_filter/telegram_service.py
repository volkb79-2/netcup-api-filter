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

import hashlib
import logging
import os
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


def is_telegram_configured_for_linking() -> bool:
    cfg = get_telegram_config()
    return bool(cfg.bot_username)


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


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
        with httpx.Client(timeout=cfg.timeout_seconds) as client:
            resp = client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
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

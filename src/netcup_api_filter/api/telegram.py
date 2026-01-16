"""Telegram callback endpoints.

These endpoints are called by an external Telegram bot service.

We intentionally do NOT accept Telegram updates directly in the NAF web app.
Instead, your bot (hosted separately) should:
1) Receive Telegram webhook updates from Telegram
2) Extract chat_id + the /start payload "link_<token>"
3) Call the NAF callback endpoint with a shared secret

This keeps Telegram-specific webhook validation and bot hosting concerns
separate from the NAF web app deployment.

See docs:
- docs/TELEGRAM_LINKING.md
- docs/TELEGRAM_BOT_SETUP.md
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from flask import Blueprint, jsonify, request

from ..database import db
from ..models import Account
from ..telegram_service import send_telegram_message, sha256_hex

logger = logging.getLogger(__name__)

telegram_bp = Blueprint("telegram", __name__, url_prefix="/api/telegram")


def _get_callback_secret() -> str | None:
    secret = (os.environ.get("TELEGRAM_LINK_CALLBACK_SECRET") or "").strip()
    return secret or None


@telegram_bp.route("/link", methods=["POST"])
def telegram_link_callback():
    """Finalize Telegram linking (bot -> app callback).

    Required:
    - Header: X-NAF-TELEGRAM-SECRET: matches TELEGRAM_LINK_CALLBACK_SECRET
    - JSON: {"token": "<raw_link_token>", "chat_id": "<digits>"}

    Returns JSON with status.
    """

    secret = _get_callback_secret()
    if not secret:
        return jsonify({"error": "Telegram linking not configured"}), 503

    provided = (request.headers.get("X-NAF-TELEGRAM-SECRET") or "").strip()
    if provided != secret:
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    chat_id = (payload.get("chat_id") or "").strip()

    if not token:
        return jsonify({"error": "Missing token"}), 400
    if not chat_id or not chat_id.isdigit():
        return jsonify({"error": "Invalid chat_id"}), 400

    token_hash = sha256_hex(token)
    account: Account | None = Account.query.filter_by(telegram_link_token_hash=token_hash).first()
    if not account:
        return jsonify({"error": "Invalid or unknown token"}), 404

    if not account.telegram_link_token_expires_at:
        return jsonify({"error": "Token not pending"}), 409

    if datetime.utcnow() > account.telegram_link_token_expires_at:
        return jsonify({"error": "Token expired"}), 410

    account.telegram_chat_id = chat_id
    account.telegram_enabled = 1
    account.telegram_linked_at = datetime.utcnow()

    # Consume token
    account.telegram_link_token_hash = None
    account.telegram_link_token_expires_at = None

    db.session.commit()

    # Best-effort confirmation message.
    send_telegram_message(
        chat_id=chat_id,
        text="✅ Netcup API Filter: Telegram successfully linked. You can now receive notifications here.",
    )

    logger.info(f"Telegram linked for account={account.username}")

    return jsonify({"status": "linked"}), 200

"""Shared redaction rules for browser and pwmcp diagnostics."""
from __future__ import annotations

import re
from typing import Any

REDACTED = "<redacted>"
SECRET_PARAM_WORDS = ("token", "code", "key", "secret", "password", "otp", "signature", "sig")
ONE_TIME_PATH_RE = re.compile(
    r"(/(?:verify|reset|reset-password|invite)/)[^/?#\s\"'<>]+", re.IGNORECASE
)
SECRET_QUERY_RE = re.compile(
    r"([?&;](?:[^=&#\s\"'<>]*?)(?:" + "|".join(SECRET_PARAM_WORDS)
    + r")(?:[^=&#\s\"'<>]*)=)[^&#\s\"'<>]+",
    re.IGNORECASE,
)
WS_URL_RE = re.compile(r"wss?://[^\s\"'<>]+", re.IGNORECASE)


def is_secret_param(name: object) -> bool:
    lowered = str(name).lower()
    return any(word in lowered for word in SECRET_PARAM_WORDS)


def redact_url_text(text: Any) -> Any:
    """Mask one-time path tokens and secret-named query values in text."""
    if not isinstance(text, str):
        return text
    text = ONE_TIME_PATH_RE.sub(lambda match: match.group(1) + REDACTED, text)
    return SECRET_QUERY_RE.sub(lambda match: match.group(1) + REDACTED, text)

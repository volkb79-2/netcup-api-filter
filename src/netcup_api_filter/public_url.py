"""Validation and lookup for the app's configured public origin."""
from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlsplit, urlunsplit

from .config_defaults import get_default


def host_is_valid(hostname: str, *, allow_ip: bool) -> bool:
    """Validate a URL or cookie hostname without resolving it over the network."""
    if not hostname or "%" in hostname or any(char.isspace() for char in hostname):
        return False

    try:
        ipaddress.ip_address(hostname)
        return allow_ip
    except ValueError:
        if ":" in hostname or "%" in hostname:
            return False

    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        return False

    if ascii_hostname.endswith("."):
        ascii_hostname = ascii_hostname[:-1]
    if not ascii_hostname or len(ascii_hostname) > 253:
        return False

    for label in ascii_hostname.split("."):
        if (
            not label
            or len(label) > 63
            or not label[0].isalnum()
            or not label[-1].isalnum()
            or any(not (char.isalnum() or char == "-") for char in label)
        ):
            return False
    return True


def parse_public_base_url(value: str) -> tuple[str, str]:
    """Return normalized scheme and authority for an absolute HTTP(S) origin."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError(
            "PUBLIC_BASE_URL must be an absolute http(s) origin with a valid host and optional port"
        ) from exc

    hostname = parsed.hostname
    if (
        value != value.strip()
        or any(char.isspace() for char in value)
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
        or parsed.scheme.lower() not in ("http", "https")
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or "?" in value
        or "#" in value
        or parsed.netloc.endswith(":")
        or (port is not None and not 1 <= port <= 65535)
        or not host_is_valid(hostname, allow_ip=True)
    ):
        raise RuntimeError(
            "PUBLIC_BASE_URL must be an absolute http(s) origin with host[:port], "
            "and no path, query, fragment, or credentials"
        )

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if parsed.netloc.startswith("[") and (address is None or address.version != 6):
        raise RuntimeError(
            "PUBLIC_BASE_URL must use brackets only around a valid IPv6 host"
        )

    if address is None:
        authority_host = hostname.encode("idna").decode("ascii").lower()
    else:
        authority_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    authority = f"{authority_host}:{port}" if port is not None else authority_host
    return parsed.scheme.lower(), authority


def get_configured_public_base_url() -> str:
    """Read and validate PUBLIC_BASE_URL outside app initialization when needed."""
    raw_value = os.environ.get("PUBLIC_BASE_URL", get_default("PUBLIC_BASE_URL"))
    if not raw_value:
        return ""
    scheme, authority = parse_public_base_url(raw_value)
    return urlunsplit((scheme, authority, "", "", ""))

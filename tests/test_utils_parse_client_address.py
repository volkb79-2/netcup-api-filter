"""Exact contract tests for the resolved-client-address parser in utils.py."""
from __future__ import annotations

import ipaddress

import pytest

from netcup_api_filter.utils import parse_client_address

IPV4_MAPPED_IPV6 = str(ipaddress.ip_address("::ffff:c000:201"))


def assert_parsed(value, expected: str | None) -> None:
    parsed = parse_client_address(value)
    actual = None if parsed is None else str(parsed)
    assert actual == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        pytest.param(
            "\t 192.0.2.1 \r\n",
            "192.0.2.1",
            id="plain-ipv4-surrounding-whitespace",
        ),
        pytest.param(
            "2001:0db8:0000:0000:0000:0000:0000:0017",
            "2001:db8::17",
            id="plain-expanded-ipv6-normalizes",
        ),
        pytest.param(
            "::ffff:c000:201",
            IPV4_MAPPED_IPV6,
            id="ipv4-mapped-ipv6",
        ),
        pytest.param("::1", "::1", id="ipv6-colon-literal"),
        pytest.param(
            " \t198.51.100.17:443\r\n",
            "198.51.100.17",
            id="ipv4-port-valid",
        ),
        pytest.param("198.51.100.18:1", "198.51.100.18", id="ipv4-port-lower-bound"),
        pytest.param(
            "198.51.100.19:65535",
            "198.51.100.19",
            id="ipv4-port-upper-bound",
        ),
        pytest.param(
            "198.51.100.20:00001",
            "198.51.100.20",
            id="ipv4-port-five-digits-in-range",
        ),
        pytest.param(
            "[2001:db8::17]",
            "2001:db8::17",
            id="bracketed-ipv6-without-port",
        ),
        pytest.param(
            " \t[2001:0db8::17]:443\r\n",
            "2001:db8::17",
            id="bracketed-ipv6-port-valid",
        ),
        pytest.param(
            "[2001:db8::18]:65535",
            "2001:db8::18",
            id="bracketed-ipv6-port-upper-bound",
        ),
        pytest.param(
            "2001:db8::17:443",
            "2001:db8::17:443",
            id="plain-ipv6-with-numeric-final-segment",
        ),
    ],
)
def test_parse_client_address_accepts_only_unambiguous_addresses(value, expected):
    assert_parsed(value, expected)


@pytest.mark.parametrize(
    "value,expected",
    [
        pytest.param(None, None, id="none-is-not-a-string"),
        pytest.param(b"192.0.2.1", None, id="bytes-is-not-a-string"),
        pytest.param(42, None, id="integer-is-not-a-string"),
        pytest.param("", None, id="empty-string"),
        pytest.param(" \t\r\n ", None, id="whitespace-only"),
        pytest.param("fe80::1%eth0", None, id="scoped-ipv6"),
        pytest.param("[fe80::1%eth0]:443", None, id="scoped-bracketed-ipv6"),
        pytest.param("198.51.100.17:0", None, id="ipv4-port-zero"),
        pytest.param("198.51.100.17:65536", None, id="ipv4-port-above-range"),
        pytest.param(
            "198.51.100.17:000001",
            None,
            id="ipv4-port-six-digits",
        ),
        pytest.param(
            "198.51.100.17:٤٤٣",
            None,
            id="ipv4-port-non-ascii-digits",
        ),
        pytest.param("198.51.100.17:", None, id="ipv4-port-empty"),
        pytest.param("198.51.100.17:+443", None, id="ipv4-port-leading-plus"),
        pytest.param("198.51.100.17:not-a-port", None, id="ipv4-port-not-numeric"),
        pytest.param("bad.host:80", None, id="ipv4-shape-host-not-an-ip"),
        pytest.param(
            "2001:db8::17:65536",
            None,
            id="unbracketed-ipv6-port-more-than-one-colon",
        ),
        pytest.param("[", None, id="bracket-without-closing-bracket"),
        pytest.param(
            "[2001:db8::17:443",
            None,
            id="bracketed-ipv6-without-closing-bracket",
        ),
        pytest.param(
            "[2001:db8::17]garbage",
            None,
            id="bracket-suffix-garbage",
        ),
        pytest.param(
            "[2001:db8::17]443",
            None,
            id="bracket-suffix-port-without-colon",
        ),
        pytest.param(
            "[2001:db8::17]:443garbage",
            None,
            id="bracket-suffix-port-garbage",
        ),
        pytest.param("[192.0.2.1]:443", None, id="bracketed-ipv4-version-mismatch"),
        pytest.param("[not-ip]", None, id="bracketed-host-not-an-ip"),
        pytest.param("[bad.host]:80", None, id="bracketed-host-not-ip-with-port"),
        pytest.param("[2001:db8::17]:0", None, id="bracketed-ipv6-port-zero"),
        pytest.param(
            "[2001:db8::17]:65536",
            None,
            id="bracketed-ipv6-port-above-range",
        ),
        pytest.param(
            "[2001:db8::17]:000001",
            None,
            id="bracketed-ipv6-port-six-digits",
        ),
        pytest.param(
            "[2001:db8::17]:٤٤٣",
            None,
            id="bracketed-ipv6-port-non-ascii-digits",
        ),
        pytest.param("[2001:db8::17]:", None, id="bracketed-ipv6-port-empty"),
        pytest.param(
            "[2001:db8::17]:+443",
            None,
            id="bracketed-ipv6-port-leading-plus",
        ),
    ],
)
def test_parse_client_address_rejects_ambiguous_or_malformed_shapes(value, expected):
    assert_parsed(value, expected)

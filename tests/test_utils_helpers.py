"""Additional tests for utils.py: token/credential generation, password
hashing, filesystem probe, IP/filename helpers, info helpers, build info.

`utils` is imported as a module (not names) so pytest does not collect
`test_filesystem_access` as a test.
"""
from __future__ import annotations

import json
import logging
import os
import re
import string
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from netcup_api_filter import utils

ALNUM = set(string.ascii_letters + string.digits)


# ---------------------------------------------------------------- parse_bool
@given(st.sampled_from(sorted(utils._TRUTHY_VALUES)), st.booleans(), st.booleans(),
       st.sampled_from(["", " ", "\t"]))
def test_parse_bool_truthy_any_case_and_padding(word, upper, default, pad):
    raw = pad + (word.upper() if upper else word) + pad
    assert utils.parse_bool(raw, default=default) is True


@given(st.sampled_from(sorted(utils._FALSY_VALUES)), st.booleans(), st.booleans())
def test_parse_bool_falsy_any_case(word, upper, default):
    assert utils.parse_bool(word.upper() if upper else word, default=default) is False


@given(st.text(max_size=20).filter(
    lambda s: s.strip().lower() not in utils._TRUTHY_VALUES | utils._FALSY_VALUES),
    st.booleans())
def test_parse_bool_unrecognised_returns_default(raw, default):
    assert utils.parse_bool(raw, default=default) is default


@given(st.booleans(), st.booleans())
def test_parse_bool_bool_passthrough_and_none(value, default):
    assert utils.parse_bool(value, default=default) is value
    assert utils.parse_bool(None, default=default) is default


def test_parse_bool_strict_mode_rejects_unknown_values():
    with pytest.raises(ValueError, match="Unrecognised boolean value"):
        utils.parse_bool("tru", strict=True)


# ----------------------------------------------------------------- sha256_hex
@given(st.text(max_size=200))
def test_sha256_hex_shape_and_determinism(s):
    h = utils.sha256_hex(s)
    assert re.fullmatch(r"[0-9a-f]{64}", h)
    assert h == utils.sha256_hex(s)


def test_sha256_hex_known_vector():
    assert utils.sha256_hex("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


# ------------------------------------------------------------- generate_token
@given(st.integers(1, 80), st.integers(0, 20))
def test_generate_token_length_in_bounds_and_alphabet(lo, extra):
    tok = utils.generate_token(lo, lo + extra)
    assert lo <= len(tok) <= lo + extra
    assert set(tok) <= ALNUM


def test_generate_token_defaults_and_uniqueness():
    toks = {utils.generate_token() for _ in range(20)}
    assert len(toks) == 20
    assert all(63 <= len(t) <= 65 for t in toks)


@pytest.mark.parametrize("lo,hi", [(0, 5), (5, 0), (-1, 5), (5, -1)])
def test_generate_token_rejects_non_positive(lo, hi):
    with pytest.raises(ValueError, match="positive"):
        utils.generate_token(lo, hi)


def test_generate_token_rejects_inverted_range():
    with pytest.raises(ValueError, match="cannot exceed"):
        utils.generate_token(10, 9)


@given(st.integers(1, 60), st.integers(1, 60))
def test_generate_client_credentials_contract(id_len, secret_len):
    cid, secret, full = utils.generate_client_credentials(id_len, secret_len)
    assert (len(cid), len(secret)) == (id_len, secret_len)
    assert full == f"{cid}:{secret}"
    assert full.split(":") == [cid, secret]  # alphabet never contains ':'


def test_generate_client_credentials_defaults():
    cid, secret, _ = utils.generate_client_credentials()
    assert (len(cid), len(secret)) == (20, 40)


# ------------------------------------------------------------------ passwords
@settings(deadline=None, max_examples=10)
@given(st.text(min_size=1, max_size=40).filter(lambda s: len(s.encode()) <= 72 and "\x00" not in s))
def test_hash_verify_round_trip(pw):
    hashed = utils.hash_password(pw, cost=4)
    assert hashed.startswith("$2") and hashed != pw
    assert utils.verify_password(pw, hashed) is True
    assert utils.verify_password(pw + "x", hashed) is False


def test_hash_password_is_salted_and_cost_encoded():
    a = utils.hash_password("same-pw", cost=4)
    b = utils.hash_password("same-pw", cost=4)
    assert a != b
    assert a.split("$")[2] == "04"


def test_verify_password_malformed_hash_returns_false_and_logs(caplog):
    with caplog.at_level(logging.ERROR, logger=utils.logger.name):
        assert utils.verify_password("pw", "not-a-bcrypt-hash") is False
    assert "Password verification error" in caplog.text


# ------------------------------------------------------ test_filesystem_access
def _by_name(results):
    return {r["name"]: r for r in results}


def test_fs_access_writable_and_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    res = _by_name(utils.test_filesystem_access())["Working Directory"]
    assert res["success"] and res["readable"] and res["writable"]
    assert res["message"] == "Readable ✓ | Writable ✓"
    assert res["error"] == ""
    assert not (tmp_path / ".write_test_netcup_filter").exists()  # probe cleaned up


def test_fs_access_readable_not_writable(tmp_path, monkeypatch):
    # A directory squatting on the probe filename makes open(..., 'w') fail
    # regardless of uid (root ignores chmod).
    (tmp_path / ".write_test_netcup_filter").mkdir()
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    res = _by_name(utils.test_filesystem_access())["Working Directory"]
    assert res["success"] is False and res["writable"] is False
    assert res["readable"] is True
    assert res["message"] == "Readable ✓ | Writable ✗"
    assert res["error"].startswith("Write test failed:")


def test_fs_access_missing_path_not_accessible(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path / "does-not-exist"))
    res = _by_name(utils.test_filesystem_access())["Working Directory"]
    assert res["success"] is False
    assert res["readable"] is False
    assert res["message"] == ""
    assert res["error"].startswith("Not accessible:")


def test_fs_access_writable_but_unreadable(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    real_access = os.access
    monkeypatch.setattr(
        os, "access",
        lambda p, m, *a, **k: False if str(p) == str(tmp_path) else real_access(p, m, *a, **k))
    res = _by_name(utils.test_filesystem_access())["Working Directory"]
    assert res["writable"] and not res["readable"]
    assert res["message"] == "Writable ✓"


def test_fs_access_readability_check_exception_is_swallowed(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    real_exists = os.path.exists

    def flaky(p):
        if str(p) == str(tmp_path):
            raise OSError("stat exploded")
        return real_exists(p)

    monkeypatch.setattr(os.path, "exists", flaky)
    res = _by_name(utils.test_filesystem_access())["Working Directory"]
    assert res["readable"] is False
    assert res["writable"] is True  # write probe is independent of the read check


def test_fs_access_home_included_or_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path))
    names = [r["name"] for r in utils.test_filesystem_access()]
    assert names == ["Working Directory", "/tmp Directory", "Home Directory"]
    monkeypatch.setattr(os.path, "expanduser", lambda p: "~")
    names = [r["name"] for r in utils.test_filesystem_access()]
    assert names == ["Working Directory", "/tmp Directory"]


# ------------------------------------------------------------- validate_ip_range
@pytest.mark.parametrize("value,expected", [("255.*.0.1", True), ("*.*.*.256", False), ("300.*.1.1", False)])
def test_validate_ip_range_wildcard_octet_bounds(value, expected):
    assert utils.validate_ip_range(value) is expected


@pytest.mark.parametrize("value,expected", [
    ("192.168.1.*", True), ("*.*.*.*", True), ("10.*.0.1", True),
    ("300.1.1.*", False),        # octet out of range
    ("1.2.3.*.5", False),        # too many octets
    ("1.2.*", False),            # too few
    ("1.2.3.4-5.6.7.8-9.9.9.9", False),   # three parts, no other form matches
    ("1.2.3.4-not-an-ip", False),
    ("1.2.3.4 - 1.2.3.9", True),
    ("fe80::*", True),           # basic IPv6 wildcard support
    ("::1", True),
    ("2001:db8::/32", True),
    ("10.0.0.0/33", False),
    ("", False), ("*", True),
])
def test_validate_ip_range_cases(value, expected):
    assert utils.validate_ip_range(value) is expected


@given(st.integers(256, 999))
def test_validate_ip_range_wildcard_octet_over_255_rejected(n):
    assert utils.validate_ip_range(f"1.2.3.{n}") is False
    assert utils.validate_ip_range(f"{n}.2.*.4") is False


# ------------------------------------------------------------ sanitize_filename
@given(st.text(max_size=60))
def test_sanitize_filename_contract(name):
    out = utils.sanitize_filename(name)
    assert "/" not in out
    assert not out.startswith(".")
    assert re.fullmatch(r"[\w\-\.]*", out)
    assert utils.sanitize_filename(out) == out  # idempotent


@pytest.mark.parametrize("raw,expected", [
    ("../../etc/passwd", "passwd"),
    (".htaccess", "_.htaccess"),
    ("a b$c.txt", "a_b_c.txt"),
])
def test_sanitize_filename_examples(raw, expected):
    assert utils.sanitize_filename(raw) == expected


# --------------------------------------------------------------- info helpers
def test_get_python_info_keys_match_runtime():
    info = utils.get_python_info()
    assert info["python_version"] == sys.version
    assert info["executable"] == sys.executable
    assert info["prefix"] == sys.prefix
    assert set(info) == {"python_version", "python_implementation", "platform",
                         "architecture", "executable", "prefix"}


def test_get_installed_libraries_reports_installed_and_missing(monkeypatch):
    import importlib.metadata as md

    def fake_version(name):
        if name == "flask":
            return "9.9.9"
        raise md.PackageNotFoundError(name)

    monkeypatch.setattr(md, "version", fake_version)
    libs = {lib["name"]: lib["version"] for lib in utils.get_installed_libraries()}
    assert libs["flask"] == "9.9.9"
    assert libs["pytest"] == "Not installed"
    assert len(libs) == 11


def test_get_current_directory_info(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    info = utils.get_current_directory_info()
    assert info["cwd"] == str(tmp_path)
    assert os.path.isfile(os.path.join(info["script_dir"], "utils.py"))
    assert info["home"] == os.path.expanduser("~")


# ------------------------------------------------------------------ build info
@pytest.fixture
def build_info(tmp_path, monkeypatch):
    """Isolate get_build_info: private module dir, no env override, cleared cache."""
    monkeypatch.setattr(utils, "__file__", str(tmp_path / "pkg" / "utils.py"))
    monkeypatch.delenv("NETCUP_BUILD_INFO_PATH", raising=False)
    utils.get_build_info.cache_clear()
    yield utils.get_build_info
    utils.get_build_info.cache_clear()


def _assert_fallback(info):
    assert info["source"] == "runtime-generated"
    assert info["git_commit"] == "local"
    assert info["built_at"].endswith("Z")


def test_build_info_fallback_when_no_file(build_info):
    _assert_fallback(build_info())


def test_build_info_env_path_wins(build_info, tmp_path, monkeypatch):
    p = tmp_path / "bi.json"
    p.write_text(json.dumps({"git_commit": "abc123"}))
    monkeypatch.setenv("NETCUP_BUILD_INFO_PATH", str(p))
    assert build_info() == {"git_commit": "abc123"}


def test_build_info_package_dir_file_used(build_info, tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "build_info.json").write_text('{"environment": "prod"}')
    assert build_info() == {"environment": "prod"}


def test_build_info_is_cached(build_info, tmp_path, monkeypatch):
    p = tmp_path / "bi.json"
    p.write_text('{"v": 1}')
    monkeypatch.setenv("NETCUP_BUILD_INFO_PATH", str(p))
    assert build_info() == {"v": 1}
    p.write_text('{"v": 2}')
    assert build_info() == {"v": 1}


def test_build_info_invalid_json_warns_then_falls_through(build_info, tmp_path, monkeypatch, caplog):
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    monkeypatch.setenv("NETCUP_BUILD_INFO_PATH", str(bad))
    with caplog.at_level(logging.WARNING, logger=utils.logger.name):
        info = build_info()
    _assert_fallback(info)
    assert "Failed to read build info" in caplog.text


def test_build_info_unreadable_path_warns(build_info, tmp_path, monkeypatch, caplog):
    # exists() is true for a directory but open() on it raises
    monkeypatch.setenv("NETCUP_BUILD_INFO_PATH", str(tmp_path))
    with caplog.at_level(logging.WARNING, logger=utils.logger.name):
        _assert_fallback(build_info())
    assert "Failed to read build info" in caplog.text


def test_build_info_non_dict_json_ignored(build_info, tmp_path, monkeypatch):
    p = tmp_path / "list.json"
    p.write_text("[1, 2]")
    monkeypatch.setenv("NETCUP_BUILD_INFO_PATH", str(p))
    _assert_fallback(build_info())


def test_build_info_bad_env_falls_back_to_package_file(build_info, tmp_path, monkeypatch):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "build_info.json").write_text('{"environment": "pkg"}')
    monkeypatch.setenv("NETCUP_BUILD_INFO_PATH", str(tmp_path / "missing.json"))
    assert build_info() == {"environment": "pkg"}

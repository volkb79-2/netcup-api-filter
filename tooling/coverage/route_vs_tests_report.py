#!/usr/bin/env python3
"""Generate a route-vs-tests coverage report.

Goal
- Inventory all Flask routes from app.url_map.
- Extract URL paths referenced by UI tests (ui_tests/tests/).
- Produce a gap report highlighting routes not referenced by tests.

Notes
- This script does NOT execute HTTP requests.
- It is safe to run locally and in CI.
- It aims to be robust against simple f-strings by matching path literals.

Config (env-driven)
- COVERAGE_INCLUDE_PREFIXES: comma-separated path prefixes to treat as app routes
  (default: /admin,/account,/api,/,/health)
- COVERAGE_OUT_JSON: optional path to write JSON output
- COVERAGE_OUT_MD: optional path to write Markdown output

Usage
  python3 tooling/coverage/route_vs_tests_report.py \
    --out-json tmp/route_coverage.json \
    --out-md docs/TEST_COVERAGE_ROUTE_DIFF.md

Merged from scripts/audit_routes_vs_ui_tests.py (2026-06):
- Added scanning of ui_tests/journeys/ in addition to ui_tests/tests/
- Added _related_files_for_missing_route() to suggest relevant test files
- Added area classification for "/" and "/health" as "public"
- Expanded path literal regex max-length from 200 to 400 chars (catches longer f-string paths)
- Added scratch-DB setup so route discovery doesn't clobber a real DB
- Added sys.path setup for repos with deploy-local vendor layout
- --out-json now writes the full payload; compact summary is also printed to stdout
- JSON output now includes "covered_prefix_by_area" and "missing_related_files"
- Kept --markdown-out as an alias for --out-md for backward compatibility
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PARAM_PATTERN = re.compile(r"<[^>]+>")


def _normalize_rule(rule: str) -> str:
    return PARAM_PATTERN.sub("<param>", rule)


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _area_for_rule(rule: str) -> str:
    """Classify a route rule into a named area."""
    if rule.startswith("/admin"):
        return "admin"
    if rule.startswith("/account"):
        return "account"
    if rule.startswith("/api"):
        return "api"
    if rule in ("/", "/health"):
        return "public"
    return "misc"


def _parent_prefix(path: str) -> str:
    """Return a parent-path prefix ending in '/'.

    Example: /account/register/resend -> /account/register/
    """
    if path in ("/", ""):
        return "/"
    parts = path.split("/")
    if len(parts) <= 2:
        return "/"
    return "/".join(parts[:-1]) + "/"


# ---------------------------------------------------------------------------
# Route loading
# ---------------------------------------------------------------------------

def _setup_environment(workspace_root: Path) -> None:
    """Configure sys.path and environment variables for Flask app import."""
    sys.path.insert(0, str(workspace_root))
    sys.path.insert(0, str(workspace_root / "src"))
    sys.path.insert(0, str(workspace_root / "deploy-local" / "src"))
    sys.path.insert(0, str(workspace_root / "deploy-local" / "vendor"))

    os.environ.setdefault("FLASK_ENV", "testing")
    # Not a production key; used only to satisfy Flask session machinery.
    os.environ.setdefault("SECRET_KEY", "route-discovery-key")

    # Use a fresh scratch DB so route discovery doesn't touch a real database.
    scratch_dir = workspace_root / "tmp"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    scratch_db = scratch_dir / "route_discovery_audit.db"
    if scratch_db.exists():
        scratch_db.unlink()
    os.environ.setdefault("NETCUP_FILTER_DB_PATH", str(scratch_db))


def _load_routes() -> List[Dict[str, Any]]:
    from ui_tests.route_discovery import discover_routes_from_app

    registry = discover_routes_from_app()
    routes: List[Dict[str, Any]] = []
    for r in registry.routes:
        routes.append(
            {
                "rule": r.rule,
                "endpoint": r.endpoint,
                "methods": sorted(r.methods),
                "blueprint": r.blueprint,
                "category": r.category,
                "auth_required": r.auth_required,
                "has_params": r.has_params,
            }
        )
    return routes


# ---------------------------------------------------------------------------
# Test-file scanning
# ---------------------------------------------------------------------------

# Allow '/' itself or paths up to 400 chars (merged: was 200 in tooling/, 400 in scripts/).
_LITERAL_PATH_RE = re.compile(r"(?P<q>['\"])(/(?:(?!\1).){0,400})\1")


def _iter_test_files(workspace_root: Path) -> Iterable[Path]:
    """Yield all Python test files from ui_tests/tests/.

    (The legacy ui_tests/journeys/ tree was removed in the testing-hardening
    plan — see docs/plans/testing-hardening/AUDIT.md; it was orphaned/superseded.)
    """
    for rel in [Path("ui_tests") / "tests"]:
        root = workspace_root / rel
        if not root.exists():
            continue
        yield from sorted(root.rglob("*.py"))


def _scan_test_paths(
    workspace_root: Path,
    include_prefixes: Tuple[str, ...],
) -> Tuple[Set[str], Dict[str, Set[str]]]:
    """Return (all_tested_paths, tested_paths_by_file)."""
    all_tested: Set[str] = set()
    by_file: Dict[str, Set[str]] = {}

    for py in _iter_test_files(workspace_root):
        text = py.read_text(encoding="utf-8")
        file_paths: Set[str] = set()
        for m in _LITERAL_PATH_RE.finditer(text):
            p = m.group(2)
            if not p.startswith("/") or p.startswith("//"):
                continue
            if include_prefixes and not any(
                p == pfx or p.startswith(pfx.rstrip("/") + "/")
                for pfx in include_prefixes
            ):
                continue
            file_paths.add(p)
        if file_paths:
            rel = str(py.relative_to(workspace_root))
            by_file[rel] = file_paths
            all_tested |= file_paths

    return all_tested, by_file


# ---------------------------------------------------------------------------
# Coverage diff
# ---------------------------------------------------------------------------

def _related_files_for_missing_route(
    rule: str,
    tested_paths_by_file: Dict[str, Set[str]],
    limit: int = 5,
) -> List[str]:
    """Suggest test files likely relevant to a missing route.

    Finds the closest parent-prefix (and area prefix) referenced by tests,
    so a developer knows where similar coverage lives.
    """
    static_prefix = rule.split("<", 1)[0]
    prefixes = [static_prefix, _parent_prefix(static_prefix)]

    area = _area_for_rule(rule)
    if area == "admin":
        prefixes.append("/admin/")
    elif area == "account":
        prefixes.append("/account/")
    elif area == "api":
        prefixes.append("/api/")

    scores: Dict[str, int] = {}
    for file_path, paths in tested_paths_by_file.items():
        score = sum(
            1 for p in paths
            for pfx in prefixes
            if pfx != "/" and p.startswith(pfx)
        )
        if score:
            scores[file_path] = score

    candidates: List[str] = []
    for fp, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0])):
        candidates.append(fp)
        if len(candidates) >= limit:
            break
    return candidates


def _coverage_diff(
    routes: List[Dict[str, Any]],
    tested_paths: Set[str],
    tested_paths_by_file: Dict[str, Set[str]],
) -> Dict[str, Any]:
    normalized_tested = {_normalize_rule(p) for p in tested_paths}

    covered_exact: Set[str] = set()
    covered_prefix: Set[str] = set()
    missing: Set[str] = set()

    for r in routes:
        rule = r["rule"]

        if rule in tested_paths or _normalize_rule(rule) in normalized_tested:
            covered_exact.add(rule)
            continue

        if r["has_params"]:
            static_prefix = rule.split("<", 1)[0]
            if any(tp.startswith(static_prefix) for tp in tested_paths):
                covered_prefix.add(rule)
            else:
                missing.add(rule)
        else:
            missing.add(rule)

    def _group_by_area(items: Iterable[str]) -> Dict[str, List[str]]:
        grouped: Dict[str, List[str]] = defaultdict(list)
        for it in sorted(set(items)):
            grouped[_area_for_rule(it)].append(it)
        return dict(grouped)

    return {
        "summary": {
            "total_routes": len(routes),
            "tested_literal_paths_found": len(tested_paths),
            "covered_exact_count": len(covered_exact),
            "covered_prefix_count": len(covered_prefix),
            "missing_count": len(missing),
        },
        "covered_exact": sorted(covered_exact),
        "covered_prefix_by_area": _group_by_area(covered_prefix),
        "missing_by_area": _group_by_area(missing),
        "missing_related_files": {
            rule: _related_files_for_missing_route(rule, tested_paths_by_file)
            for rule in sorted(missing)
        },
        "notes": {
            "covered_prefix_meaning": (
                "Parameterized routes where at least one test references the static prefix "
                "(e.g. /admin/accounts/), but no exact rule match exists."
            ),
            "missing_meaning": (
                "Routes not referenced by any string-literal paths in ui_tests "
                "(may still be covered via computed URLs/f-strings, but those usually "
                "include the same prefix and are caught by prefix coverage)."
            ),
        },
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _render_md(diff: Dict[str, Any]) -> str:
    s = diff["summary"]
    lines: List[str] = []
    lines.append("# Route vs UI Test Coverage Report")
    lines.append("")
    lines.append("This report is generated by `tooling/coverage/route_vs_tests_report.py`.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total routes discovered: **{s['total_routes']}**")
    lines.append(f"- Test path literals found: **{s['tested_literal_paths_found']}**")
    lines.append(f"- Covered (exact): **{s['covered_exact_count']}**")
    lines.append(f"- Covered (prefix for param routes): **{s['covered_prefix_count']}**")
    lines.append(f"- Missing (not referenced): **{s['missing_count']}**")
    lines.append("")

    lines.append("## Missing Routes (by area)")
    lines.append("")
    for area in ("admin", "account", "api", "public", "misc"):
        items = diff["missing_by_area"].get(area) or []
        if not items:
            continue
        lines.append(f"### {area} ({len(items)})")
        lines.append("")
        for rule in items:
            lines.append(f"- `{rule}`")
            related = diff.get("missing_related_files", {}).get(rule) or []
            if related:
                lines.append("  - Related tests:")
                for fp in related:
                    lines.append(f"    - `{fp}`")
        lines.append("")

    lines.append("## Prefix-Covered Param Routes (by area)")
    lines.append("")
    for area in ("admin", "account", "api", "public", "misc"):
        items = (diff.get("covered_prefix_by_area") or {}).get(area) or []
        if not items:
            continue
        lines.append(f"### {area} ({len(items)})")
        lines.append("")
        for rule in items:
            lines.append(f"- `{rule}`")
        lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- This is a *reference scan* (string literals in tests), not full behavioral coverage.")
    lines.append(
        "- Param routes (e.g. `/admin/accounts/<int:id>`) are treated as covered "
        "if any test references the static prefix."
    )
    lines.append(
        "- If a route is missing but is invoked via form POST without a literal path, "
        "add an explicit test reference or extend the scanner."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    workspace_root = Path(__file__).resolve().parents[2]

    parser = argparse.ArgumentParser(
        description="Generate a route-vs-UI-tests coverage gap report.",
    )
    parser.add_argument(
        "--workspace-root",
        default=str(workspace_root),
        help="Path to repo workspace root (default: two levels up from this script)",
    )
    parser.add_argument(
        "--out-json",
        default=_env("COVERAGE_OUT_JSON", ""),
        help="Write full JSON report to this path (optional; env: COVERAGE_OUT_JSON)",
    )
    # --out-md and --markdown-out are synonyms; --markdown-out preserved for back-compat.
    _md_group = parser.add_mutually_exclusive_group()
    _md_group.add_argument(
        "--out-md",
        default=_env("COVERAGE_OUT_MD", ""),
        help="Write Markdown report to this path (optional; env: COVERAGE_OUT_MD)",
    )
    _md_group.add_argument(
        "--markdown-out",
        default="",
        help="Alias for --out-md (back-compat with scripts/audit_routes_vs_ui_tests.py)",
    )
    args = parser.parse_args()

    workspace_root = Path(args.workspace_root).resolve()
    md_out = args.out_md or args.markdown_out

    include_prefixes = tuple(
        p.strip()
        for p in _env("COVERAGE_INCLUDE_PREFIXES", "/admin,/account,/api,/,/health").split(",")
        if p.strip()
    )

    _setup_environment(workspace_root)
    routes = _load_routes()
    tested_paths, tested_paths_by_file = _scan_test_paths(workspace_root, include_prefixes)
    diff = _coverage_diff(routes, tested_paths, tested_paths_by_file)

    payload = {
        "summary": diff["summary"],
        "missing_by_area": diff["missing_by_area"],
        "covered_prefix_by_area": diff["covered_prefix_by_area"],
        "covered_exact": diff["covered_exact"],
        "missing_related_files": diff["missing_related_files"],
        "notes": diff["notes"],
    }

    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if md_out:
        out_md = Path(md_out)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(_render_md(diff) + "\n", encoding="utf-8")

    # Always print a compact summary + full JSON to stdout for CLI use.
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

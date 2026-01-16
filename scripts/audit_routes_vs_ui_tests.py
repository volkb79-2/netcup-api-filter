#!/usr/bin/env python3
"""Audit Flask route coverage vs UI tests.

Purpose
- Enumerate *actual* Flask routes (via app.url_map) and compare them to URL
  strings referenced in ui_tests.
- Produce a concrete, reviewable list of:
  - Routes never referenced by tests
  - Parameterized routes only covered indirectly (prefix-only)
  - Route families with no journey/workflow coverage

Outputs
- JSON summary to stdout by default
- Optional Markdown report with --markdown-out

Notes
- This script is intentionally read-only.
- It sets FLASK_ENV=testing to avoid production-only constraints.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple


PARAM_PATTERN = re.compile(r"<[^>]+>")


def normalize_rule(rule: str) -> str:
    return PARAM_PATTERN.sub("<param>", rule)


def iter_test_files(workspace_root: Path) -> Iterable[Path]:
    # Include both classic tests and journey modules.
    for rel in [Path("ui_tests") / "tests", Path("ui_tests") / "journeys"]:
        root = workspace_root / rel
        if not root.exists():
            continue
        yield from root.rglob("*.py")


def extract_path_literals(py_text: str) -> List[str]:
    # Extract quoted strings starting with '/'.
    # This is intentionally simple; we rely on app.url_map for ground truth.
    # Allow '/' itself (zero chars after leading slash).
    path_re = re.compile(r"(?P<q>['\"])(/(?:(?!\1).){0,400})\1")
    out: List[str] = []
    for m in path_re.finditer(py_text):
        p = m.group(2)
        if p.startswith("/") and not p.startswith("//"):
            out.append(p)
    return out


def area_for_rule(rule: str) -> str:
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

    Example:
      /account/register/resend -> /account/register/
    """
    if path in ("/", ""):
        return "/"
    parts = path.split("/")
    if len(parts) <= 2:
        return "/"
    # Keep leading '' from split('/...')
    return "/".join(parts[:-1]) + "/"


def _related_files_for_missing_route(
    rule: str,
    tested_paths_by_file: Dict[str, Set[str]],
    limit: int = 5,
) -> List[str]:
    """Suggest test files likely relevant to a missing route.

    Missing routes have no direct literal references by definition.
    This helper finds the closest parent-prefix (and then area prefix)
    referenced by tests, so a developer knows where similar coverage lives.
    """
    candidates: List[str] = []

    # Prefer the static (pre-parameter) prefix, then fall back to parent path.
    static_prefix = rule.split("<", 1)[0]
    prefixes = [static_prefix, _parent_prefix(static_prefix)]

    area = area_for_rule(rule)
    if area == "admin":
        prefixes.append("/admin/")
    elif area == "account":
        prefixes.append("/account/")
    elif area == "api":
        prefixes.append("/api/")

    # Score files by number of referenced paths matching any prefix.
    scores: Dict[str, int] = {}
    for file_path, paths in tested_paths_by_file.items():
        score = 0
        for pfx in prefixes:
            if pfx == "/":
                continue
            score += sum(1 for p in paths if p.startswith(pfx))
        if score:
            scores[file_path] = score

    for fp, _score in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0])):
        candidates.append(fp)
        if len(candidates) >= limit:
            break

    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Path to repo workspace root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--markdown-out",
        default="",
        help="Write a Markdown report to this path (optional)",
    )
    args = parser.parse_args()

    workspace_root = Path(args.workspace_root).resolve()

    # Ensure imports work
    sys.path.insert(0, str(workspace_root))
    sys.path.insert(0, str(workspace_root / "src"))
    sys.path.insert(0, str(workspace_root / "deploy-local" / "src"))
    sys.path.insert(0, str(workspace_root / "deploy-local" / "vendor"))

    os.environ.setdefault("FLASK_ENV", "testing")
    # Not a production key; used only to satisfy Flask session machinery.
    os.environ.setdefault("SECRET_KEY", "ui-test-coverage-audit")

    # Force route discovery to use a fresh DB with current schema.
    scratch_dir = workspace_root / "tmp"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    scratch_db = scratch_dir / "route_discovery_audit.db"
    if scratch_db.exists():
        scratch_db.unlink()
    os.environ.setdefault("NETCUP_FILTER_DB_PATH", str(scratch_db))

    from ui_tests.route_discovery import discover_routes_from_app

    registry = discover_routes_from_app()

    # Route inventory
    routes: List[Dict[str, Any]] = []
    for r in registry.routes:
        routes.append(
            {
                "rule": r.rule,
                "endpoint": r.endpoint,
                "methods": sorted(r.methods),
                "blueprint": r.blueprint,
                "auth_required": r.auth_required,
                "has_params": r.has_params,
                "category": r.category,
            }
        )

    # Test references inventory
    tested_paths: Set[str] = set()
    tested_paths_by_file: Dict[str, Set[str]] = {}

    for py in iter_test_files(workspace_root):
        text = py.read_text(encoding="utf-8")
        paths = set(extract_path_literals(text))
        if not paths:
            continue
        rel = str(py.relative_to(workspace_root))
        tested_paths_by_file[rel] = paths
        tested_paths |= paths

    normalized_tested = set(normalize_rule(p) for p in tested_paths)

    covered_exact: Set[str] = set()
    covered_prefix: Set[str] = set()
    missing: Set[str] = set()

    for r in routes:
        rule = r["rule"]
        has_params = bool(r["has_params"])

        if rule in tested_paths or normalize_rule(rule) in normalized_tested:
            covered_exact.add(rule)
            continue

        if has_params:
            static_prefix = rule.split("<", 1)[0]
            if any(tp.startswith(static_prefix) for tp in tested_paths):
                covered_prefix.add(rule)
            else:
                missing.add(rule)
        else:
            missing.add(rule)

    def group_by_area(items: Iterable[str]) -> Dict[str, List[str]]:
        grouped: Dict[str, List[str]] = defaultdict(list)
        for it in sorted(set(items)):
            grouped[area_for_rule(it)].append(it)
        return dict(grouped)

    out = {
        "summary": {
            "total_routes": len(routes),
            "tested_literal_paths_found": len(tested_paths),
            "covered_exact_count": len(covered_exact),
            "covered_prefix_count": len(covered_prefix),
            "missing_count": len(missing),
        },
        "missing_by_area": group_by_area(missing),
        "covered_prefix_by_area": group_by_area(covered_prefix),
        "missing_related_files": {
            rule: _related_files_for_missing_route(rule, tested_paths_by_file)
            for rule in sorted(missing)
        },
        "notes": {
            "covered_prefix_meaning": "Parameterized routes where at least one test references the static prefix (e.g. /admin/accounts/), but no exact rule match exists.",
            "missing_meaning": "Routes that are not referenced by any string-literal paths in ui_tests (may still be covered via computed URLs/f-strings, but those usually include the same prefix and are caught by prefix coverage).",
        },
    }

    if args.markdown_out:
        md_path = Path(args.markdown_out)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md = []
        md.append("# UI/API Coverage Audit (Routes vs UI Tests)\n")
        md.append("This report is generated by `scripts/audit_routes_vs_ui_tests.py`.\n")
        md.append("## Summary\n")
        for k, v in out["summary"].items():
            md.append(f"- **{k}**: {v}\n")
        md.append("\n## Missing Routes (by area)\n")
        for area, rules in out["missing_by_area"].items():
            md.append(f"\n### {area} ({len(rules)})\n")
            for rule in rules:
                md.append(f"- `{rule}`\n")
                related = out.get("missing_related_files", {}).get(rule) or []
                if related:
                    md.append("  - Related tests:\n")
                    for fp in related:
                        md.append(f"    - `{fp}`\n")
        md.append("\n## Prefix-Covered Param Routes (by area)\n")
        for area, rules in out["covered_prefix_by_area"].items():
            md.append(f"\n### {area} ({len(rules)})\n")
            for rule in rules:
                md.append(f"- `{rule}`\n")
        md_path.write_text("".join(md), encoding="utf-8")

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

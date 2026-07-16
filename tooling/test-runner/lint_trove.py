#!/usr/bin/env python3
"""Validate nyxloom handoff frontmatter in this repo's trove.

WHY THIS EXISTS
---------------
`nyxloom lint` is the canonical linter, but the running nyxloomd container does not
mount this repo (it mounts only vbpub + dstdns), so it cannot reach our handoffs yet.
Until that mount + `nyxloom project add` land, this reproduces the checks that matter
so the trove is verifiable in our own gate:

  * frontmatter present and parseable
  * validates against the canonical handoff-frontmatter JSON schema
  * L1: filename stem MUST equal the frontmatter `id`
  * every oracle's `gate` and each top-level `gates` entry resolves to a
    `[gates.*]` id declared in nyxloom-trove/nyxloom.toml

It is a SUBSET, not a replacement: once nyxloomd mounts this repo, `nyxloom lint` is
authoritative and this becomes a pre-flight convenience.

The schema is vendored (schemas/handoff-frontmatter.schema.json) because the canonical
copy lives in the nyxloom checkout, which is not mounted into the gate container. The
vendored copy records the revision it was taken from; refresh it deliberately.

Usage:  lint_trove.py [trove_dir]      (default: nyxloom-trove)
Exit:   0 = clean, 1 = findings, 3 = setup error
"""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

try:
    import jsonschema
    import yaml
except ImportError as exc:  # pragma: no cover - environment guard
    print(f"FATAL: gate image missing a linter dep ({exc}). Rebuild the test-runner image.",
          file=sys.stderr)
    raise SystemExit(3)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "tooling" / "test-runner" / "schemas" / "handoff-frontmatter.schema.json"


def split_frontmatter(text: str) -> str | None:
    """Return the YAML frontmatter block, or None if absent/unterminated."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[3:end]


def declared_gates(trove: Path) -> set[str]:
    cfg = trove / "nyxloom.toml"
    if not cfg.is_file():
        return set()
    with cfg.open("rb") as fh:
        return set(tomllib.load(fh).get("gates", {}).keys())


def main(argv: list[str]) -> int:
    trove = REPO_ROOT / (argv[1] if len(argv) > 1 else "nyxloom-trove")
    if not trove.is_dir():
        print(f"FATAL: trove not found: {trove}", file=sys.stderr)
        return 3
    if not SCHEMA_PATH.is_file():
        print(f"FATAL: vendored schema not found: {SCHEMA_PATH}", file=sys.stderr)
        return 3

    schema = json.loads(SCHEMA_PATH.read_text())
    validator = jsonschema.Draft202012Validator(schema)
    gates = declared_gates(trove)

    handoffs = sorted((trove / "handoffs").glob("*.md"))
    if not handoffs:
        print(f"FATAL: no handoffs found under {trove / 'handoffs'}", file=sys.stderr)
        return 3

    findings: list[str] = []
    for path in handoffs:
        rel = path.relative_to(REPO_ROOT)
        raw = split_frontmatter(path.read_text())
        if raw is None:
            findings.append(f"{rel}: missing or unterminated YAML frontmatter")
            continue
        try:
            fm = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            findings.append(f"{rel}: frontmatter is not valid YAML: {exc}")
            continue
        if not isinstance(fm, dict):
            findings.append(f"{rel}: frontmatter is not a mapping")
            continue

        for err in sorted(validator.iter_errors(fm), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "(root)"
            findings.append(f"{rel}: schema: {loc}: {err.message}")

        # L1 — the filename stem must equal the frontmatter id.
        if fm.get("id") and path.stem != fm["id"]:
            findings.append(
                f"{rel}: L1: filename stem {path.stem!r} != frontmatter id {fm['id']!r}"
            )

        # Gate ids must resolve to a declared [gates.*] in nyxloom.toml.
        referenced = set(fm.get("gates") or [])
        for oracle in fm.get("oracles") or []:
            if isinstance(oracle, dict) and oracle.get("gate"):
                referenced.add(oracle["gate"])
        for gate in sorted(referenced - gates):
            findings.append(
                f"{rel}: gate {gate!r} is not declared in nyxloom-trove/nyxloom.toml [gates.*]"
            )

    if findings:
        for finding in findings:
            print(f"FAIL {finding}")
        print(f"\n{len(findings)} finding(s) across {len(handoffs)} handoff(s)", file=sys.stderr)
        return 1

    print(f"trove OK — {len(handoffs)} handoff(s) valid against the frontmatter schema "
          f"(gates declared: {', '.join(sorted(gates)) or 'none'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

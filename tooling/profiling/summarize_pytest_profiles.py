#!/usr/bin/env python3
"""Summarize per-test pytest cProfile artifacts.

Designed to work with profiles emitted by `ui_tests/conftest.py`.

Inputs:
- A directory containing `*.prof` files
- Optional `*.json` metadata files beside profiles (same basename)

Outputs:
- Prints a ranked list of tests and their top functions.

This is intentionally dependency-free (stdlib only).
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
import pstats
from typing import Any, Iterable


@dataclass(frozen=True)
class ProfileMeta:
    nodeid: str | None
    duration_s: float | None


@dataclass(frozen=True)
class ProfileSummary:
    prof_path: Path
    nodeid: str
    duration_s: float | None
    total_tt: float


def _read_meta(meta_path: Path) -> ProfileMeta:
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ProfileMeta(nodeid=None, duration_s=None)

    nodeid = payload.get("nodeid")
    duration_s_raw = payload.get("duration_s")

    duration_s: float | None
    try:
        duration_s = float(duration_s_raw) if duration_s_raw is not None else None
    except (TypeError, ValueError):
        duration_s = None

    return ProfileMeta(nodeid=str(nodeid) if nodeid else None, duration_s=duration_s)


def _guess_nodeid_from_filename(prof_path: Path) -> str:
    # Fallback: keep it readable even without metadata.
    return prof_path.stem


def _iter_profiles(profile_dir: Path) -> Iterable[ProfileSummary]:
    for prof_path in sorted(profile_dir.glob("*.prof")):
        meta_path = prof_path.with_suffix(".json")
        meta = _read_meta(meta_path) if meta_path.exists() else ProfileMeta(None, None)

        stats = pstats.Stats(str(prof_path))
        total_tt = float(getattr(stats, "total_tt", 0.0) or 0.0)

        nodeid = meta.nodeid or _guess_nodeid_from_filename(prof_path)
        yield ProfileSummary(
            prof_path=prof_path,
            nodeid=nodeid,
            duration_s=meta.duration_s,
            total_tt=total_tt,
        )


def _fmt_seconds(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}s"


def _print_top_functions(
    prof_path: Path,
    sort_key: str,
    limit: int,
) -> None:
    stats = pstats.Stats(str(prof_path))
    try:
        stats.sort_stats(sort_key)
    except Exception:
        stats.sort_stats("tottime")

    # Use a stream-like object to capture print_stats output.
    import io

    buf = io.StringIO()
    stats.stream = buf
    stats.print_stats(limit)
    text = buf.getvalue().rstrip()
    if not text:
        return

    for line in text.splitlines():
        print(f"    {line}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize pytest cProfile artifacts")
    parser.add_argument(
        "--profile-dir",
        default=os.environ.get("PYTEST_PROFILE_DIR", ""),
        help="Directory containing *.prof files (defaults to $PYTEST_PROFILE_DIR)",
    )
    parser.add_argument(
        "--top-tests",
        type=int,
        default=int(os.environ.get("PYTEST_PROFILE_SUMMARY_TOP_TESTS", "10")),
        help="How many slowest tests to show",
    )
    parser.add_argument(
        "--sort-tests-by",
        choices=["duration_s", "total_tt"],
        default=os.environ.get("PYTEST_PROFILE_SUMMARY_SORT", "duration_s"),
        help="How to rank tests (duration_s requires .json metadata)",
    )
    parser.add_argument(
        "--sort-functions",
        default=os.environ.get("PYTEST_PROFILE_SORT", "tottime"),
        help="pstats sort key for per-test function listing",
    )
    parser.add_argument(
        "--top-functions",
        type=int,
        default=int(os.environ.get("PYTEST_PROFILE_TOP", "30")),
        help="How many functions to show per test",
    )

    args = parser.parse_args(argv)

    profile_dir = Path(args.profile_dir).resolve() if args.profile_dir else None
    if profile_dir is None:
        raise SystemExit("--profile-dir is required (or set PYTEST_PROFILE_DIR)")
    if not profile_dir.exists() or not profile_dir.is_dir():
        raise SystemExit(f"Profile dir not found: {profile_dir}")

    summaries = list(_iter_profiles(profile_dir))
    if not summaries:
        print(f"No .prof files found in: {profile_dir}")
        return 0

    def sort_key(summary: ProfileSummary) -> tuple[Any, ...]:
        if args.sort_tests_by == "duration_s":
            # Prefer tests with duration_s, then fall back to total_tt.
            return (
                -(summary.duration_s if summary.duration_s is not None else -1.0),
                -summary.total_tt,
                summary.nodeid,
            )
        return (-summary.total_tt, summary.nodeid)

    summaries.sort(key=sort_key)

    print(f"Profile directory: {profile_dir}")
    print(
        f"Profiles: {len(summaries)} | sort_tests_by={args.sort_tests_by} | sort_functions={args.sort_functions}"
    )

    for i, summary in enumerate(summaries[: args.top_tests], start=1):
        print(
            f"\n#{i} {summary.nodeid}\n"
            f"  duration_s={_fmt_seconds(summary.duration_s)}  total_tt={_fmt_seconds(summary.total_tt)}\n"
            f"  file={summary.prof_path}"
        )
        _print_top_functions(summary.prof_path, sort_key=args.sort_functions, limit=args.top_functions)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

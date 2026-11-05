"""Certify that nyxloom's [gates.*] pointers name lanes run-gate.toml really declares.

A renamed lane must go red here, at test time, not die as `unknown lane` at dispatch.
Runs `run-gate validate-pointers` (RG-2); skips only where the run-gate CLI is not
installed in the runner (the runner images do not carry it; the cockpit does).
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("run-gate") is None, reason="run-gate CLI not installed in this environment")
def test_nyxloom_gate_pointers_resolve():
    result = subprocess.run(
        ["run-gate", "validate-pointers", "nyxloom-trove/nyxloom.toml"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

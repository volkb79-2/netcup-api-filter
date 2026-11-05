"""The gate wiring must agree with itself; every check here runs in the runner (no CLI needed).

* nyxloom's [gates.*] argv only point at lanes run-gate.toml declares (a renamed lane goes
  red here, not as `unknown lane` at dispatch time).
* every runner variant exists in all four places that must move together: cmru.toml
  (shipped Passenger variants), ciu defaults (runner services), run-gate.toml (exec
  environments + image tags) and docker-bake.hcl (release targets).
"""
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _toml(rel):
    with (ROOT / rel).open("rb") as handle:
        return tomllib.load(handle)


def test_nyxloom_gate_pointers_name_declared_lanes():
    lanes = set(_toml("run-gate.toml")["lanes"])
    gates = _toml("nyxloom-trove/nyxloom.toml")["gates"]
    assert gates, "no gates declared"
    for name, gate in gates.items():
        joined = " ".join(gate["argv"])
        match = re.search(r"run-gate --worktree \{worktree\} (\S+)", joined)
        assert match, f"gate {name!r} is not a canonical run-gate pointer: {joined}"
        assert match.group(1) in lanes, f"gate {name!r} points at undeclared lane {match.group(1)!r}"


def test_runner_variants_agree_across_cmru_ciu_run_gate_and_bake():
    ciu_text = (ROOT / "tooling/test-runner/ciu.defaults.toml.j2").read_text()
    ciu_variants = set(re.findall(r'^name = "(py\d+)"', ciu_text, re.M))
    cmru_variants = {v["name"] for v in _toml("cmru.toml")["project"]["naf"]["variants"]}
    envs = _toml("run-gate.toml")["environments"]
    bake_targets = set(re.findall(r'^target "(py\d+)"', (ROOT / "docker-bake.hcl").read_text(), re.M))

    assert ciu_variants, "no runner variants in ciu defaults"
    assert cmru_variants <= ciu_variants, "a shipped Passenger variant has no runner"
    assert ciu_variants == bake_targets, f"ciu {ciu_variants} != bake {bake_targets}"
    for name in ciu_variants:
        env = envs.get(f"test-runner-{name}")
        assert env is not None, f"run-gate.toml has no environment test-runner-{name}"
        assert env["image"].endswith(f"/test-runner:{name}"), env["image"]

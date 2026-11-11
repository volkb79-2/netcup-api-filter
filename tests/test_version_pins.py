"""Every third-party image used by naf's stacks and builds is a cmru version target.

`versions/oci-images.json` is the reviewed, committed fact written by
`cmru versions resolve`. The consumer defaults stay literal (the mechanism already used
by Mailpit and PowerDNS); this hermetic test keeps those literals, the target declarations,
and the record equal without querying a registry.
"""
import json
import re
import shlex
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = ROOT / "versions/oci-images.json"
CMRU_PATH = ROOT / "cmru.toml"
RESOLVE_COMMAND = "cmru versions resolve naf"

# Only examples that are explicitly not concrete third-party image consumers
# may be exempted. Runnable commands must use a managed record or an internal
# image that is built in the same documented workflow.
DOC_IMAGE_REFERENCE_EXCLUSIONS = {
    (Path("docs/DOCKER_NETWORKS.md"), "myapp"): (
        "illustrative Compose service name in a network-topology comparison; "
        "it is not an image a reader is instructed to run"
    ),
    (Path("docs/FAIL_FAST_PRINCIPLE.md"), "myapp:latest"): (
        "illustrative Compose service name in a fail-fast syntax example; "
        "the document is about environment validation, not a runnable naf image"
    ),
    (Path("docs/deprecated/FAIL_FAST_POLICY.md"), "myapp"): (
        "archived syntax example uses a placeholder, not a real image"
    ),
    (Path("docs/deprecated/FAIL_FAST_POLICY.md"), "myapp:latest"): (
        "archived syntax example uses a placeholder, not a real image"
    ),
    (Path("docs/deprecated/QUICK_START.md"), "netcup-api-filter"): (
        "naf's internal image built immediately above with docker build -t "
        "netcup-api-filter ."
    ),
}

EXPECTED_TARGETS = {
    "oci.mailpit": {
        "constraint": ">=1.20.0,<2.0.0",
        "image": "ghcr.io/axllent/mailpit",
        "tag": "v{version}",
    },
    "oci.powerdns-auth": {
        "constraint": ">=4.8.0,<4.9.0",
        "image": "docker.io/powerdns/pdns-auth-48",
        "tag": "{version}",
    },
    "oci.python311": {
        "constraint": ">=3.11.0,<3.12.0",
        "image": "docker.io/library/python",
        "tag": "{version}-slim-trixie",
        "selection": "semver",
        "dockerhub_credentials": True,
    },
    "oci.python314": {
        "constraint": ">=3.14.0,<3.15.0-0",
        "image": "docker.io/library/python",
        "tag": "{version}-slim-trixie",
        "selection": "semver",
        "dockerhub_credentials": True,
    },
}

# The literal defaults copied from the record. Python consumers must carry the
# exact age-windowed patch refs recorded for oci.python311 / oci.python314.
STACK_PINS = {
    "oci.mailpit": [
        ("tooling/mailpit/ciu.defaults.toml.j2", "image", "image_tag"),
    ],
    "oci.powerdns-auth": [
        ("tooling/backend-powerdns/ciu.defaults.toml.j2", "image", "image_tag"),
    ],
    "oci.python311": [
        ("tooling/geoip-mock/ciu.defaults.toml.j2", "image", "image_tag"),
        ("tooling/netcup-api-mock/ciu.defaults.toml.j2", "image", "tag"),
    ],
}

COMPOSE_CONTRACTS = {
    "tooling/app-local/ciu.compose.yml.j2": "app_local.image_name",
    "tooling/backend-powerdns/ciu.compose.yml.j2": "backend_powerdns.image",
    "tooling/geoip-mock/ciu.compose.yml.j2": "geoip_mock.image",
    "tooling/mailpit/ciu.compose.yml.j2": "mailpit.image",
    "tooling/netcup-api-mock/ciu.compose.yml.j2": "netcup_api_mock.image",
    "tooling/test-runner/ciu.compose.yml.j2": "test_runner.image_name",
}

# naf-owned images built by this repository. These are deliberately not
# third-party cmru targets: their source is the tracked Dockerfile and the
# compose contract above proves the consumer uses the local image name.
INTERNAL_IMAGE_DEFAULTS = {
    ROOT / "tooling/app-local/ciu.defaults.toml.j2",
    ROOT / "tooling/test-runner/ciu.defaults.toml.j2",
}

def _cmru():
    with CMRU_PATH.open("rb") as handle:
        return tomllib.load(handle)


def _record():
    document = json.loads(RECORD_PATH.read_text())
    assert document["generated_by"] == "cmru versions resolve", (
        "versions/oci-images.json is not the committed output of cmru versions resolve"
    )
    assert set(document) >= {"generated_by", "resolved_at", "schema_version", "targets"}, (
        "versions/oci-images.json is missing snapshot metadata"
    )
    assert document["schema_version"] == 1, (
        f"unexpected versions/oci-images.json schema: {document['schema_version']!r}"
    )
    return document


def _timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _value(text, key):
    match = re.search(rf'^{re.escape(key)}\s*=\s*"([^"]+)"', text, re.M)
    assert match, f"{key} not found"
    return match.group(1)


def _assert_resolved(record, target):
    assert target in record, (
        f"{target} has no committed resolution; the controller must run "
        f"`{RESOLVE_COMMAND}`, update the stack/build consumers to its exact patch "
        "tag, and commit cmru.toml + versions/oci-images.json before this drift "
        "test can pass"
    )
    return record[target]


def _consumer_image(record_target):
    image = record_target["image"].removeprefix("docker.io/")
    image = image.removeprefix("library/")
    return image


def _consumer_ref(record_target):
    image = _consumer_image(record_target)
    return f"{image}:{record_target['tag']}"


def _fenced_code_blocks(text):
    """Yield (language, content) for Markdown fences, including indented fences."""
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        opener = re.match(r"^\s*(`{3,}|~{3,})(\S*)\s*$", lines[index])
        if not opener:
            index += 1
            continue
        marker = opener.group(1)
        language = opener.group(2).lower()
        start = index + 1
        index += 1
        while index < len(lines):
            closer = re.match(r"^\s*(`{3,}|~{3,})\s*$", lines[index])
            if closer and closer.group(1).startswith(marker[0]) and len(closer.group(1)) >= len(marker):
                yield language, "\n".join(lines[start:index])
                index += 1
                break
            index += 1


_DOCKER_RUN_OPTIONS_WITH_VALUE = {
    "-a", "--attach", "--add-host", "--cap-add", "--cap-drop", "--cgroupns",
    "--cidfile", "--cpu-period", "--cpu-quota", "--cpu-shares", "--cpus",
    "--cpuset-cpus", "--cpuset-mems", "--device", "--device-cgroup-rule",
    "-e", "--env", "--env-file", "--entrypoint", "--gpus", "-h", "--hostname",
    "--ipc", "--label", "-l", "--link", "--log-driver", "--log-opt", "--mac-address",
    "-m", "--memory", "--memory-swap", "--mount", "--name", "--network",
    "--network-alias", "--platform", "-p", "--publish", "--pull", "--pid",
    "--restart", "--runtime", "--security-opt", "--shm-size", "--stop-signal",
    "--stop-timeout", "--sysctl", "--tmpfs", "-u", "--user", "--userns", "--uts",
    "-v", "--volume", "-w", "--workdir",
}

_DOCKER_RUN_FLAG_OPTIONS = {
    "-d", "--detach", "-i", "--interactive", "--init", "--no-healthcheck",
    "--privileged", "--read-only", "--rm", "-t", "--tty",
}


def _docker_run_image(line):
    """Return the image operand from a one-line docker-run command."""
    if not re.match(r"^(?:sudo\s+)?(?:\$\s+)?docker\s+run(?:\s|$)", line, re.I):
        return None
    try:
        tokens = shlex.split(line, comments=True)
    except ValueError as exc:
        raise AssertionError(f"cannot parse documented docker run command {line!r}: {exc}") from exc
    try:
        docker_index = tokens.index("docker")
    except ValueError:
        return None
    if docker_index + 1 >= len(tokens) or tokens[docker_index + 1] != "run":
        return None

    index = docker_index + 2
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if not token.startswith("-"):
            break
        option = token.split("=", 1)[0]
        index += 1
        if "=" not in token and option in _DOCKER_RUN_OPTIONS_WITH_VALUE:
            index += 1
        elif option not in _DOCKER_RUN_FLAG_OPTIONS and not token.startswith("--"):
            # Unknown short flags may still expect a value; skipping one keeps
            # the scanner conservative without rejecting documentation-only flags.
            index += 1
    return tokens[index] if index < len(tokens) else None


def _logical_command_lines(block):
    """Join shell continuation lines before looking for a docker run operand."""
    buffer = ""
    for line in block.splitlines():
        stripped = line.strip()
        if buffer:
            buffer += " " + stripped
        else:
            buffer = stripped
        if buffer.endswith("\\"):
            buffer = buffer[:-1].rstrip()
            continue
        yield buffer
        buffer = ""
    if buffer:
        yield buffer


def _documentation_image_references(path):
    relative = path.relative_to(ROOT)
    for language, block in _fenced_code_blocks(path.read_text()):
        for line in _logical_command_lines(block):
            image = _docker_run_image(line)
            if image:
                yield relative, image

            match = re.match(r"^\s*image:\s*(\S+)(?:\s+#.*)?$", line)
            if match:
                yield relative, match.group(1).strip("\"'")

            if language in {"dockerfile", "docker"}:
                match = re.match(r"^\s*FROM\s+(\S+)(?:\s+AS\s+\S+)?\s*$", line, re.I)
                if match:
                    yield relative, match.group(1)


def test_target_inventory_is_complete_and_uses_the_existing_cmru_grammar():
    targets = _cmru()["versions"]["targets"]
    assert set(targets) == set(EXPECTED_TARGETS), (
        "cmru.toml target inventory must cover every third-party image in naf's "
        f"stacks and builds; declared={sorted(targets)}"
    )
    for target_id, expected in EXPECTED_TARGETS.items():
        target = targets[target_id]
        assert target["constraint"] == expected["constraint"], target_id
        assert target["oci"]["image"] == expected["image"], target_id
        assert target["oci"]["tag"] == expected["tag"], target_id
        assert target["oci"]["tag"].count("{version}") == 1, (
            f"{target_id}: the cmru OCI tag template must contain exactly one version placeholder"
        )
        if expected.get("selection") == "semver":
            assert target["oci"].get("selection") == "semver", (
                f"{target_id}: Python must use SemVer selection over an exact patch-tag template"
            )
        if expected.get("dockerhub_credentials"):
            assert target["oci"]["username_env"] == "DOCKERHUB_USERNAME", target_id
            assert target["oci"]["password_env"] == "DOCKERHUB_TOKEN", target_id


def test_cmru_resolution_and_committed_oci_fact_are_the_same_snapshot():
    cmru = _cmru()
    targets = cmru["versions"]["targets"]
    snapshot = _record()
    record = snapshot["targets"]
    missing = [target for target in EXPECTED_TARGETS if "resolved" not in targets[target]]
    assert not missing, (
        f"unresolved targets {missing}; the controller must run `{RESOLVE_COMMAND}` "
        "and commit its cmru.toml + versions/oci-images.json output"
    )
    assert set(record) == set(EXPECTED_TARGETS), (
        f"record targets {sorted(record)} != declared targets {sorted(EXPECTED_TARGETS)}"
    )

    resolved_at = snapshot["resolved_at"]
    snapshot_time = _timestamp(resolved_at)
    age_window = timedelta(days=cmru["versions"]["age_window_days"])
    for target_id, decl in targets.items():
        resolved = decl["resolved"]
        source = resolved["sources"]["oci"]
        recorded = record[target_id]
        assert resolved["resolved_at"] == resolved_at, (
            f"{target_id}: cmru.toml resolved_at {resolved['resolved_at']!r} "
            f"!= versions/oci-images.json snapshot {resolved_at!r}"
        )
        assert _timestamp(resolved["age_cutoff"]) == snapshot_time - age_window, (
            f"{target_id}: age_cutoff {resolved['age_cutoff']!r} must equal "
            f"{resolved_at!r} minus versions.age_window_days={age_window.days}"
        )
        assert recorded["image"] == decl["oci"]["image"], target_id
        assert recorded["version"] == resolved["version"], target_id
        assert recorded["tag"] == source["tag"], target_id
        assert recorded["tag"] == decl["oci"]["tag"].format(version=resolved["version"]), (
            f"{target_id}: the committed tag must equal the target's rendered patch tag"
        )
        assert recorded["released_at"] == source["released_at"], target_id
        assert recorded["age_source"] == source["age_source"], target_id
        assert recorded["reason"] == resolved.get("provenance"), target_id
        if decl["oci"].get("selection") == "rolling":
            assert recorded.get("digest") == source.get("digest"), (
                f"{target_id}: a rolling tag without the recorded manifest digest is floating"
            )
            assert re.fullmatch(r"sha256:[0-9a-f]{64}", recorded.get("digest", "")), target_id

    dated_facts = sorted((ROOT / "versions").glob("oci-images-*.json"))
    assert dated_facts, (
        f"no dated versions fact found; the controller must run `{RESOLVE_COMMAND}` "
        "and commit versions/oci-images-YYYYMMDD.json"
    )
    dated_snapshot = json.loads(dated_facts[-1].read_text())
    assert dated_snapshot == snapshot, (
        f"{dated_facts[-1].relative_to(ROOT)} must be byte-for-byte-equivalent JSON "
        f"data to versions/oci-images.json; run `{RESOLVE_COMMAND}` if either file "
        "was changed independently"
    )


def test_stack_build_and_ci_defaults_equal_the_recorded_images():
    record = _record()["targets"]

    for target_id, pins in STACK_PINS.items():
        recorded = _assert_resolved(record, target_id)
        for relative, image_key, tag_key in pins:
            text = (ROOT / relative).read_text()
            image = _value(text, image_key)
            tag = _value(text, tag_key)
            expected_image = _consumer_image(recorded)
            assert image == expected_image, f"{relative}: image {image!r} != {expected_image!r}"
            assert tag == recorded["tag"], (
                f"{relative}: tag {tag!r} != recorded {recorded['tag']!r}; "
                f"run `{RESOLVE_COMMAND}` when the target is due"
            )
            assert "latest" not in tag, relative

    mailpit = _assert_resolved(record, "oci.mailpit")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    service_image = re.search(r"^\s+image:\s+(\S+)$", workflow, re.M)
    assert service_image, "CI has no Mailpit service image"
    assert service_image.group(1) == _consumer_ref(mailpit), (
        "the CI Mailpit service image must equal the committed oci.mailpit record"
    )

    powerdns_compose = (ROOT / "tooling/backend-powerdns/ciu.compose.yml.j2").read_text()
    assert powerdns_compose.count(
        "image: {{ backend_powerdns.image }}:{{ backend_powerdns.image_tag }}"
    ) == 2, "both PowerDNS services must use the committed oci.powerdns-auth pin"
    assert "alpine:" not in powerdns_compose, (
        "the PowerDNS init must not reintroduce a separate floating base image"
    )
    init_block = powerdns_compose.split("  {{ backend_powerdns.name }}:\n", 1)[0]
    assert 'user: "0:0"' in init_block
    assert 'entrypoint: ["/bin/sh", "-c"]' in init_block
    assert "apk add" not in init_block, (
        "the PowerDNS runtime image already provides sqlite3; the init must not use apk"
    )

    global_text = (ROOT / "ciu.global.defaults.toml.j2").read_text()
    runner_defaults = (ROOT / "tooling/test-runner/ciu.defaults.toml.j2").read_text()
    runner_compose = (ROOT / "tooling/test-runner/ciu.compose.yml.j2").read_text()
    bake = (ROOT / "docker-bake.hcl").read_text()
    for target_id, ciu_key, variant in (
        ("oci.python311", "python_base_image", "py311"),
        ("oci.python314", "python_base_image_secondary", "py314"),
    ):
        recorded = _assert_resolved(record, target_id)
        expected_ref = _consumer_ref(recorded)
        assert _value(global_text, ciu_key) == expected_ref, (
            f"ciu.global.defaults.toml.j2 {ciu_key} must equal {expected_ref}; "
            f"the controller must run `{RESOLVE_COMMAND}` and update it"
        )
        assert f'PYTHON_BASE_IMAGE = "{expected_ref}"' in bake, (
            f"docker-bake.hcl {variant} must use {expected_ref}"
        )
        assert re.search(
            rf'name = "{variant}".+?python_base_image = "{{{{ build\.{ciu_key} }}}}"',
            runner_defaults,
            re.S,
        ), f"runner variant {variant} must derive its base image from build.{ciu_key}"
    assert 'PYTHON_BASE_IMAGE: "{{ v.python_base_image }}"' in runner_compose
    for dockerfile in (ROOT / "Dockerfile.release", ROOT / "tooling/test-runner/Dockerfile"):
        bases = re.findall(r"^FROM\s+(\S+)$", dockerfile.read_text(), re.M)
        assert bases == ["${PYTHON_BASE_IMAGE}"], (
            f"{dockerfile}: FROM must consume the cmru-pinned base argument, got {bases}"
        )


def test_no_third_party_image_reference_is_unmanaged_or_floating():
    record = _record()["targets"]
    record_refs = {_consumer_ref(target) for target in record.values()}
    record_refs.update(
        f"{target['image']}:{target['tag']}"
        for target in record.values()
    )

    for relative, required_variable in COMPOSE_CONTRACTS.items():
        text = (ROOT / relative).read_text()
        image_lines = re.findall(r"^\s+image:\s*(\S.*)$", text, re.M)
        assert image_lines, f"{relative}: no image lines found"
        for image in image_lines:
            assert "latest" not in image, f"{relative}: floating image {image!r}"
            if required_variable in image:
                continue
            if image in record_refs:
                continue
            raise AssertionError(
                f"{relative}: unmanaged image {image!r}; add it to cmru.toml and "
                f"versions/oci-images.json via `{RESOLVE_COMMAND}`, or add an explicit "
                "internal-image contract"
            )

    stack_default_files = set((ROOT / "tooling").glob("*/ciu.defaults.toml.j2"))
    classified_defaults = {
        ROOT / relative
        for pins in STACK_PINS.values()
        for relative, _image_key, _tag_key in pins
    }
    for path in stack_default_files - classified_defaults:
        if path in INTERNAL_IMAGE_DEFAULTS:
            continue
        text = path.read_text()
        assert not re.search(r'^image(_tag)?\s*=\s*"', text, re.M), (
            f"{path}: image defaults must be classified and kept equal to a cmru record"
        )

    for dockerfile in (
        ROOT / "Dockerfile.release",
        ROOT / "tooling/test-runner/Dockerfile",
    ):
        for base in re.findall(r"^FROM\s+(\S+)$", dockerfile.read_text(), re.M):
            assert base == "${PYTHON_BASE_IMAGE}", f"{dockerfile}: unmanaged base {base!r}"
            assert "latest" not in base

    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    for image in re.findall(r"^\s+image:\s+(\S+)$", workflow, re.M):
        assert image in record_refs, f".github/workflows/ci.yml: unmanaged image {image!r}"

    bake = (ROOT / "docker-bake.hcl").read_text()
    base_args = re.findall(r'PYTHON_BASE_IMAGE = "(\S+)"', bake)
    expected_base_args = []
    for target_id in ("oci.python311", "oci.python314"):
        recorded = _assert_resolved(record, target_id)
        assert recorded["tag"] == f"{recorded['version']}-slim-trixie", (
            f"{target_id}: the committed fact must carry an exact patch tag, "
            f"not the floating series literal {recorded['tag']!r}"
        )
        expected_base_args.append(_consumer_ref(recorded))
    assert base_args == expected_base_args, (
        "docker-bake.hcl must declare exactly the two managed Python bases; "
        f"expected {expected_base_args}, got {base_args}"
    )
    assert not any("latest" in value for value in base_args)

    unmanaged_docs = []
    for path in sorted((ROOT / "docs").rglob("*.md")):
        for relative, image in _documentation_image_references(path):
            if image in record_refs:
                continue
            if (relative, image) in DOC_IMAGE_REFERENCE_EXCLUSIONS:
                continue
            unmanaged_docs.append(
                f"{relative}: {image!r} in a fenced executable image snippet"
            )
    assert not unmanaged_docs, (
        "documentation has unmanaged or floating third-party image references:\n"
        + "\n".join(unmanaged_docs)
        + f"\npin to a committed versions/oci-images.json reference, remove the "
        f"runnable snippet, or add a narrowly justified non-executable-prose "
        f"exclusion; dependencies are resolved with `{RESOLVE_COMMAND}`"
    )

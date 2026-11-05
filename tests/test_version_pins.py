"""Third-party service images are pinned to what `cmru versions resolve` recorded.

versions/oci-images.json is the reviewed, committed fact (age-window resolution); the ciu stack defaults
must carry exactly that tag, never a floating one. Update both together (resolve, then pin).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# cmru target id -> stack defaults file that runs the image
STACKS = {
    "oci.mailpit": "tooling/mailpit/ciu.defaults.toml.j2",
    "oci.powerdns-auth": "tooling/backend-powerdns/ciu.defaults.toml.j2",
}


def _record():
    return json.loads((ROOT / "versions" / "oci-images.json").read_text())["targets"]


def _value(text, key):
    match = re.search(rf'^{re.escape(key)}\s*=\s*"([^"]+)"', text, re.M)
    assert match, f"{key} not found"
    return match.group(1)


def test_every_resolved_service_target_has_a_stack():
    assert set(_record()) == set(STACKS), "a new cmru target needs a stack mapping (or the reverse)"


def test_stack_image_and_tag_equal_the_recorded_resolution():
    record = _record()
    for target, rel in STACKS.items():
        text = (ROOT / rel).read_text()
        image = _value(text, "image")
        tag = _value(text, "image_tag")
        recorded_image = record[target]["image"].removeprefix("docker.io/")
        assert image == recorded_image, f"{rel}: image {image!r} != recorded {recorded_image!r}"
        assert tag == record[target]["tag"], f"{rel}: tag {tag!r} != recorded {record[target]['tag']!r}"
        assert tag != "latest"

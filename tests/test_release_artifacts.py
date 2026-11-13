"""Cheap contracts for cmru's Passenger bundle configuration and naf stage helper."""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tomllib
import types
import zipfile
from contextlib import nullcontext
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load_stage_helper():
    spec = importlib.util.spec_from_file_location(
        "naf_passenger_bundle_stage", REPO / "tooling/passenger_bundle_stage.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bundle_config():
    with (REPO / "bundle.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_bundle_config_uses_cmru_parser_or_structural_contract():
    """Reverting cmru.toml to the hand-rolled builder leaves no valid bundle config."""
    config = _bundle_config()
    try:
        from cmru.bundle import parse_config
    except ImportError:
        # The tester image may not carry cmru's package. Keep this closed structural
        # check in that case; the canary's release runner uses cmru's installed parser.
        assert set(config) == {
            "project_root", "dist_dir", "bundle_dir", "wheel", "archive",
            "copy", "vendor", "stage", "exec", "manifest",
        }
        assert config["archive"] == {
            "name_template": "naf-v{version}-{variant}.tar.xz",
            "version_env": "NAF_VERSION",
            "format": "xztar",
        }
        assert config["wheel"] == {
            "enabled": False,
            "python_bin": "/opt/tester-venv/bin/python",
        }
        assert config["copy"] == {
            "files": [".env.defaults", "src/netcup_api_filter/passenger_wsgi.py"],
            "dirs": ["src", "scripts"],
        }
        assert config["vendor"] == {
            "requirements": ["requirements-runtime.txt"],
            "platforms": ["manylinux2014_x86_64", "any"],
            "dest": "vendor",
        }
        assert config["stage"]["argv"][:2] == [
            "/opt/tester-venv/bin/python", "tooling/passenger_bundle_stage.py",
        ]
        assert config["stage"]["argv"][-2:] == ["{bundle_dir}", "{python_version}"]
        assert config["exec"]["prefix"] == [
            "docker", "exec", "-e", "SOURCE_DATE_EPOCH", "-w", "{root}", "{container}",
        ]
        assert config["exec"]["env"] == {
            "root": "NAF_BUNDLE_RUNNER_ROOT",
            "container": "NAF_BUNDLE_RUNNER_CONTAINER",
        }
        assert config["manifest"] == {"name": "manifest.json"}
    else:
        parsed = parse_config(REPO / "bundle.toml")
        assert parsed.wheel_enabled is False
        assert parsed.wheel_python_bin == "/opt/tester-venv/bin/python"
        assert parsed.bundle_dir == REPO / "dist/app"
        assert parsed.archive_template == "naf-v{version}-{variant}.tar.xz"
        assert parsed.archive_format == "xztar"
        assert parsed.copy_files == [".env.defaults", "src/netcup_api_filter/passenger_wsgi.py"]
        assert parsed.copy_dirs == ["src", "scripts"]
        assert parsed.vendor.requirements == ["requirements-runtime.txt"]
        assert parsed.vendor.platforms == ["manylinux2014_x86_64", "any"]
        assert parsed.vendor.dest == "vendor"
        assert parsed.stage.argv[-2:] == ["{bundle_dir}", "{python_version}"]
        assert parsed.exec_prefix.prefix == [
            "docker", "exec", "-e", "SOURCE_DATE_EPOCH", "-w", "{root}", "{container}",
        ]
        assert parsed.exec_prefix.env == {
            "root": "NAF_BUNDLE_RUNNER_ROOT",
            "container": "NAF_BUNDLE_RUNNER_CONTAINER",
        }
        assert parsed.manifest_name == "manifest.json"


def test_bundle_copy_paths_and_retired_ignore_patterns_are_pinned_as_data():
    """Reverting the old builder's allowlist or copytree ignores changes release contents."""
    config = _bundle_config()
    helper = _load_stage_helper()
    assert config["copy"] == {
        "files": [".env.defaults", "src/netcup_api_filter/passenger_wsgi.py"],
        "dirs": ["src", "scripts"],
    }
    assert helper.LEGACY_COPY_IGNORE_PATTERNS == ("__pycache__", "*.pyc", "*,cover")
    assert config["manifest"]["name"] == "manifest.json"


def test_stage_expands_wheels_seeds_and_renders_defaults_with_fakes(tmp_path, monkeypatch):
    """Reverting the old builder's wheel extraction, DB seed, or defaults stage breaks this."""
    stage = _load_stage_helper()
    project_root = tmp_path / "project"
    bundle_dir = project_root / "dist" / "app"
    vendor_dir = bundle_dir / "vendor"
    project_root.mkdir()
    (project_root / ".env.defaults").write_text(
        "DEFAULT_ADMIN_PASSWORD=fixture-only\n", encoding="utf-8"
    )
    (bundle_dir / ".env.defaults").parent.mkdir(parents=True)
    shutil.copy2(project_root / ".env.defaults", bundle_dir / ".env.defaults")
    (bundle_dir / "src/netcup_api_filter/templates").mkdir(parents=True)
    (bundle_dir / "scripts").mkdir()
    vendor_dir.mkdir()

    (bundle_dir / "src/cache/__pycache__").mkdir(parents=True)
    (bundle_dir / "src/cache/__pycache__/stale.py").write_text("ignored", encoding="utf-8")
    (bundle_dir / "src/stale.pyc").write_bytes(b"ignored")
    (bundle_dir / "src/generated,cover").write_text("ignored", encoding="utf-8")
    (bundle_dir / "scripts/generated,cover").write_text("ignored", encoding="utf-8")
    wheel_path = vendor_dir / "sample-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as wheel:
        wheel.writestr("sampledep/__init__.py", "VALUE = 'wheel'\n")
        wheel.writestr("sample-1.0.dist-info/METADATA", "Name: sample\n")
        # The old copytree patterns never applied to extracted vendor contents.
        wheel.writestr("sampledep/generated,cover", "retained vendor data")

    events = []

    class FakeDB:
        def init_app(self, app):
            events.append(("init_app", app.config.copy()))

        def create_all(self):
            events.append(("create_all", Path.cwd()))

    class FakeFlask:
        def __init__(self, name, *, template_folder):
            self.config = {}
            self.template_folder = template_folder
            events.append(("flask", name, template_folder))

        def app_context(self):
            return nullcontext()

    def fake_seed(*, mock_email=None):
        events.append((
            "seed", mock_email, Path.cwd(), os.environ.get("DEPLOYMENT_TARGET"),
            os.environ.get("NETCUP_FILTER_DB_PATH"), tuple(sys.path[:3]),
        ))
        assert Path("vendor/sampledep/__init__.py").is_file()
        assert not list(Path("vendor").glob("*.dist-info"))
        assert Path("vendor/sampledep/generated,cover").is_file()
        Path("netcup_filter.db").write_bytes(b"fake seeded database")

    flask_module = types.ModuleType("flask")
    flask_module.Flask = FakeFlask
    package_module = types.ModuleType("netcup_api_filter")
    package_module.__path__ = []
    database_module = types.ModuleType("netcup_api_filter.database")
    database_module.db = FakeDB()
    bootstrap_module = types.ModuleType("netcup_api_filter.bootstrap")
    bootstrap_module.seed_shipped_database = fake_seed
    defaults_module = types.ModuleType("netcup_api_filter.config_defaults")
    defaults_module.SHIPPED_RUNTIME_OVERRIDES = {"TRUSTED_PROXY_HOPS": ("0", "fixture")}

    def fake_write_defaults(source, destination, *, overrides):
        events.append(("defaults", Path(source), Path(destination), overrides))
        assert Path(source) == project_root / ".env.defaults"
        assert not (Path(destination) / ".env.defaults").exists()
        (Path(destination) / "app-defaults.env").write_text(
            "TRUSTED_PROXY_HOPS=0\n", encoding="utf-8"
        )

    defaults_module.write_shipped_defaults = fake_write_defaults
    package_module.database = database_module
    package_module.bootstrap = bootstrap_module
    package_module.config_defaults = defaults_module
    monkeypatch.setitem(sys.modules, "flask", flask_module)
    monkeypatch.setitem(sys.modules, "netcup_api_filter", package_module)
    monkeypatch.setitem(sys.modules, "netcup_api_filter.database", database_module)
    monkeypatch.setitem(sys.modules, "netcup_api_filter.bootstrap", bootstrap_module)
    monkeypatch.setitem(sys.modules, "netcup_api_filter.config_defaults", defaults_module)
    monkeypatch.setattr(stage, "_runtime_python_version", lambda: "3.11")
    monkeypatch.setenv("DEPLOYMENT_TARGET", "restore-this-target")
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", "restore-this-db")
    monkeypatch.chdir(project_root)
    original_sys_path = list(sys.path)

    stage.stage_bundle(bundle_dir, "3.11")

    assert [event[0] for event in events] == ["flask", "init_app", "create_all", "seed", "defaults"]
    seed_event = next(event for event in events if event[0] == "seed")
    assert seed_event[1:5] == (
        None, bundle_dir.resolve(), "webhosting", str(bundle_dir.resolve() / "netcup_filter.db")
    )
    assert seed_event[5] == (
        str(bundle_dir.resolve() / "vendor"),
        str(bundle_dir.resolve() / "src"),
        str(bundle_dir.resolve()),
    )
    assert os.environ["DEPLOYMENT_TARGET"] == "restore-this-target"
    assert os.environ["NETCUP_FILTER_DB_PATH"] == "restore-this-db"
    assert Path.cwd() == project_root
    assert sys.path == original_sys_path
    assert not wheel_path.exists()
    assert not list(vendor_dir.glob("*.dist-info"))
    assert not (bundle_dir / "src/cache/__pycache__").exists()
    assert not (bundle_dir / "src/stale.pyc").exists()
    assert not (bundle_dir / "src/generated,cover").exists()
    assert not (bundle_dir / "scripts/generated,cover").exists()
    assert (bundle_dir / "netcup_filter.db").read_bytes() == b"fake seeded database"
    assert (bundle_dir / "app-defaults.env").read_text(encoding="utf-8") == "TRUSTED_PROXY_HOPS=0\n"
    assert not (bundle_dir / ".env.defaults").exists()


def test_stage_rejects_a_runner_with_the_wrong_interpreter_before_mutation(tmp_path, monkeypatch):
    """Reverting the old builder's interpreter check would let an ABI mismatch stage files."""
    stage = _load_stage_helper()
    bundle_dir = tmp_path / "dist/app"
    bundle_dir.mkdir(parents=True)
    monkeypatch.setattr(stage, "_runtime_python_version", lambda: "3.11")
    called = []
    with pytest.raises(RuntimeError, match="refusing to stage the 3.14 Passenger bundle"):
        stage.stage_bundle(
            bundle_dir,
            "3.14",
            seed=lambda _root: called.append("seed"),
            render_defaults=lambda _root: called.append("defaults"),
        )
    assert called == []
    assert list(bundle_dir.iterdir()) == []


def test_stage_rejects_an_empty_wheelhouse(tmp_path, monkeypatch):
    """Reverting the old builder's no-wheels failure would publish an unvendored bundle."""
    stage = _load_stage_helper()
    bundle_dir = tmp_path / "dist/app"
    (bundle_dir / "vendor").mkdir(parents=True)
    monkeypatch.setattr(stage, "_runtime_python_version", lambda: "3.11")
    called = []
    with pytest.raises(RuntimeError, match="cmru vendored no wheels"):
        stage.stage_bundle(
            bundle_dir,
            "3.11",
            seed=lambda _root: called.append("seed"),
            render_defaults=lambda _root: called.append("defaults"),
        )
    assert called == []

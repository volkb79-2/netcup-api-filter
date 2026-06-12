#!/usr/bin/env python3
"""Fail-fast bootstrap for the CI ``e2e-smoke`` job (T13).

Unlike ``build_deployment.py`` (which downloads/vendors deps and zips a package),
this script does the *minimum* needed to make a freshly-checked-out repo testable
by the Playwright ``ci_smoke`` subset over plain HTTP:

1. Create a deploy directory and make ``src/`` importable from it (the
   ``initialize_database`` helper expects ``<deploy_dir>/src/netcup_api_filter``
   for both package import and the Jinja template folder).
2. Call ``initialize_database(deploy_dir, is_local=True)`` to create + seed the
   SQLite DB (admin + demo accounts + Mailpit email config).
3. Call ``create_deployment_state(...)`` with the returned credentials and copy
   the resulting state JSON to the path given by ``--state-file`` (the workflow
   points ``DEPLOYMENT_STATE_FILE`` at it).

Everything is fail-fast: any missing precondition raises immediately with a
clear message; there are NO cross-environment fallbacks. The state file is the
single source of truth the UI tests read at import time, so this MUST succeed
before pytest is invoked.

Required env (validated below):
- ``SECRET_KEY``                   Flask secret (also used by the app at runtime).
- ``NETCUP_FILTER_DB_PATH``        Absolute DB path; its parent becomes the deploy dir.
- ``DEPLOYMENT_TARGET=local``      Selects local seeding behaviour.
- ``MOCK_SMTP_HOST`` / ``MOCK_SMTP_PORT``  Where the app sends 2FA/invite mail
                                   (Mailpit SMTP on the runner). ``seed_mock_email_config``
                                   reads these; defaults are container hostnames that
                                   do NOT resolve on a GitHub runner, so we require
                                   ``MOCK_SMTP_HOST`` explicitly.
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

# Make build_deployment importable (it lives in the repo root).
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [ci_bootstrap] %(message)s",
)
logger = logging.getLogger("ci_bootstrap_e2e")


def _require_env(name: str, *, expected: str | None = None) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(
            f"FATAL: required environment variable {name!r} is unset/empty. "
            f"The CI e2e-smoke job must export it before running this bootstrap."
        )
    if expected is not None and value != expected:
        raise SystemExit(
            f"FATAL: environment variable {name}={value!r} but this bootstrap "
            f"requires {name}={expected!r}."
        )
    return value


def _prepare_deploy_dir(db_path: Path) -> Path:
    """Create the deploy dir and link ``src/`` so the DB initializer can import the app.

    ``initialize_database`` resolves ``<deploy_dir>/src/netcup_api_filter`` for the
    package import AND the Jinja template folder, and writes the SQLite DB to
    ``<deploy_dir>/netcup_filter.db``. We therefore require the configured DB path
    to live directly inside the deploy dir and expose ``src`` there.
    """
    deploy_dir = db_path.parent
    deploy_dir.mkdir(parents=True, exist_ok=True)

    if db_path.name != "netcup_filter.db":
        raise SystemExit(
            f"FATAL: NETCUP_FILTER_DB_PATH must end in 'netcup_filter.db' "
            f"(initialize_database writes <deploy_dir>/netcup_filter.db), got: {db_path}"
        )

    repo_src = REPO_ROOT / "src"
    if not (repo_src / "netcup_api_filter").is_dir():
        raise SystemExit(
            f"FATAL: expected source package at {repo_src / 'netcup_api_filter'} "
            f"(run this from a full checkout)."
        )

    deploy_src = deploy_dir / "src"
    if deploy_src.resolve() == repo_src.resolve():
        # deploy_dir IS the repo root; nothing to link.
        return deploy_dir

    if deploy_src.exists() or deploy_src.is_symlink():
        # Idempotent: clear any stale link/dir from a previous run.
        if deploy_src.is_symlink() or deploy_src.is_file():
            deploy_src.unlink()
        else:
            shutil.rmtree(deploy_src)

    try:
        deploy_src.symlink_to(repo_src, target_is_directory=True)
        logger.info("Linked %s -> %s", deploy_src, repo_src)
    except OSError:
        # Symlinks may be unavailable on some filesystems; fall back to a copy.
        shutil.copytree(repo_src, deploy_src)
        logger.info("Copied %s -> %s (symlink unavailable)", repo_src, deploy_src)

    return deploy_dir


def _reseed_email_config(db_path: Path) -> None:
    """Re-seed the ``email_config`` Settings row using the env-provided SMTP host.

    Runs in a minimal Flask app context bound to the freshly-created DB and calls
    the same ``seed_mock_email_config`` helper used at build time. ``MOCK_SMTP_HOST``
    / ``MOCK_SMTP_PORT`` are taken from the current environment (validated in
    ``main``), so the stored config points at the runner's Mailpit SMTP.
    """
    src_path = REPO_ROOT / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    from flask import Flask

    from netcup_api_filter import database
    from netcup_api_filter.bootstrap.seeding import seed_mock_email_config

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    database.db.init_app(app)

    with app.app_context():
        seed_mock_email_config()

    logger.info(
        "Re-seeded email_config -> %s:%s",
        os.environ.get("MOCK_SMTP_HOST"),
        os.environ.get("MOCK_SMTP_PORT", "1025"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="CI e2e-smoke bootstrap (fail-fast)")
    parser.add_argument(
        "--state-file",
        required=True,
        help="Destination path for the deployment state JSON (UI tests read this).",
    )
    args = parser.parse_args()

    # ---- Validate environment (fail-fast, no fallbacks) --------------------
    _require_env("SECRET_KEY")
    _require_env("DEPLOYMENT_TARGET", expected="local")
    db_path = Path(_require_env("NETCUP_FILTER_DB_PATH")).resolve()
    # Mailpit SMTP target for app-sent mail. Defaults in seed_mock_email_config
    # are container hostnames; require explicit host so CI never silently points
    # the app at an unresolvable name.
    smtp_host = _require_env("MOCK_SMTP_HOST")
    smtp_port = os.environ.get("MOCK_SMTP_PORT", "1025")

    logger.info("Repo root:   %s", REPO_ROOT)
    logger.info("DB path:     %s", db_path)
    logger.info("State file:  %s", args.state_file)

    deploy_dir = _prepare_deploy_dir(db_path)
    logger.info("Deploy dir:  %s", deploy_dir)

    # Import after sys.path is set up.
    from build_deployment import create_deployment_state, initialize_database

    # ---- Initialize + seed the database ------------------------------------
    # is_local=True seeds the Mailpit email config (seed_mock_email_config reads
    # MOCK_SMTP_HOST/MOCK_SMTP_PORT) and demo accounts used by the smoke subset.
    logger.info("Initializing database (is_local=True)...")
    client_id, secret_key, all_demo_clients = initialize_database(
        str(deploy_dir), is_local=True, seed_demo=False
    )
    if not all_demo_clients:
        raise SystemExit(
            "FATAL: initialize_database returned no demo clients; the smoke subset "
            "needs a seeded primary client. Check seeding (DEFAULT_TEST_CLIENT_* env)."
        )
    logger.info(
        "Database seeded: primary client=%s, %d demo client(s)",
        client_id,
        len(all_demo_clients),
    )

    # ---- Correct the seeded Mailpit host -----------------------------------
    # initialize_database(is_local=True) sources .env.services and OVERRIDES
    # MOCK_SMTP_HOST with the container hostname (SERVICE_MAILPIT, e.g.
    # 'naf-dev-mailpit') before calling seed_mock_email_config(). That hostname
    # does NOT resolve on a GitHub runner, so the app would silently fail to
    # deliver 2FA/invite mail and the smoke tests that wait on email would time
    # out. Re-seed email_config with the host/port we were explicitly given,
    # restoring the env values first (initialize_database mutated os.environ).
    os.environ["MOCK_SMTP_HOST"] = smtp_host
    os.environ["MOCK_SMTP_PORT"] = smtp_port
    _reseed_email_config(db_path)

    # ---- Write the deployment state JSON -----------------------------------
    # create_deployment_state writes deployment_state_local.json into REPO_ROOT;
    # copy that to the requested --state-file location.
    create_deployment_state(
        str(deploy_dir), client_id, secret_key, all_demo_clients, target="local"
    )
    source_state = REPO_ROOT / "deployment_state_local.json"
    if not source_state.is_file():
        raise SystemExit(
            f"FATAL: expected state file was not produced at {source_state}."
        )

    dest = Path(args.state_file).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest != source_state.resolve():
        shutil.copy2(source_state, dest)
    logger.info("Deployment state written to %s", dest)

    # Sanity: the DB the tests verify against must exist.
    if not db_path.is_file():
        raise SystemExit(
            f"FATAL: database file not found at {db_path} after initialization."
        )

    logger.info("Bootstrap complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

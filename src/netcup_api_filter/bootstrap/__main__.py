"""``python -m netcup_api_filter.bootstrap init`` — run init_instance in a one-shot process.

This is what a ciu ``post_compose`` hook ``docker exec``-s INSIDE the running app
container (the hook never writes files into the container). It reads the same
configuration the app itself reads at start-up — ``NETCUP_FILTER_DB_PATH``,
``NETCUP_FILTER_APP_ROOT`` and the ``NAF_BOOTSTRAP_ADMIN_*`` variables, whose password
normally arrives as a ciu-generated secret file — and prints one machine-readable
result line. Passwords are never printed; only where they live.

Exit status: 0 on success, 2 on a configuration error (message on stderr).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m netcup_api_filter.bootstrap", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="idempotently initialize the database (init_instance)")
    init.add_argument(
        "--enforce-admin", action="store_true",
        help="create-or-UPDATE the configured bootstrap admin (password, email, active, lockout cleared)",
    )
    init.add_argument("--mock-smtp-host", help="LOCAL stacks only: Mailpit SMTP host")
    init.add_argument("--mock-smtp-port", type=int, help="LOCAL stacks only: Mailpit SMTP port")
    init.add_argument("--mock-from-email", help="LOCAL stacks only: sender address")
    init.add_argument("--mock-admin-email", help="LOCAL stacks only: admin notification recipient")
    return parser


def _mock_email(args: argparse.Namespace):
    from .instance import MockEmail

    values = (args.mock_smtp_host, args.mock_smtp_port, args.mock_from_email, args.mock_admin_email)
    if not any(v is not None for v in values):
        return None
    if not all(v is not None for v in values):
        raise ValueError(
            "--mock-smtp-host, --mock-smtp-port, --mock-from-email and --mock-admin-email go together"
        )
    return MockEmail(*values)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(), stream=sys.stderr)
    args = _build_parser().parse_args(argv)

    from flask import Flask

    from .. import database
    from .admin import BootstrapAdminError, configured_admin_spec
    from .instance import init_instance

    db_path = os.environ.get("NETCUP_FILTER_DB_PATH", "").strip()
    if not db_path:
        print("error: NETCUP_FILTER_DB_PATH is not set (the app's database path)", file=sys.stderr)
        return 2

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    database.db.init_app(app)
    try:
        with app.app_context():
            spec = configured_admin_spec(os.environ.get("NETCUP_FILTER_APP_ROOT"))
            if args.enforce_admin and spec is None:
                raise BootstrapAdminError("--enforce-admin needs a configured bootstrap admin")
            if not args.enforce_admin:
                # Same rule as app start (init_db): the configured admin is only a
                # first-boot input; never add a second admin to an initialized DB.
                from ..models import Account
                database.db.create_all()
                if Account.query.filter_by(is_admin=1).first() is not None:
                    spec = None
            report = init_instance(admin=spec, enforce_admin=args.enforce_admin, mock_email=_mock_email(args))
    except (BootstrapAdminError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({
        "admin_username": report.admin_username,
        "admin_action": report.admin_action,
        "admin_source": report.admin_source,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

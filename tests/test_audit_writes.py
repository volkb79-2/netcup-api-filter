"""Audit writes must actually land — the ActivityLog API was being misused.

Two verified bugs these tests lock down (see docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md §P0-4/§P0-5):

* `api/account.py` constructed `ActivityLog(details=...)` at six sites and queried
  `ActivityLog.details.like(...)` at a seventh. There is no `details` column — the
  human-readable field is `status_reason` — so those sites raised TypeError /
  AttributeError *after* the DNS mutation had already run. Users saw "Failed" for a
  change that succeeded.
* `api/admin.py` called `log_activity(...)`, a name it never defines or imports, so
  realm/token revoke committed the revoke and then 500'd with NameError — a destructive
  security action with no audit trail.

The tests assert the ROW and its column values, not merely that nothing raised: a
"no exception" test would have passed against a build that silently wrote nothing.
"""
import ast
import pathlib

import pytest

from netcup_api_filter.models import ActivityLog, db as _db

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "netcup_api_filter"


def _module_ast(relpath: str) -> ast.Module:
    return ast.parse((_SRC / relpath).read_text(), filename=relpath)


def _defined_or_imported_names(tree: ast.Module) -> set:
    """Every name bound at module level (def/class/import/assign)."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


class TestBlueprintsDoNotUsePhantomAuditAPI:
    """Static guards that FAIL on the pre-fix code.

    The behavioural tests below pin the model contract but pass either way, because
    exercising the portal DNS routes needs session auth + a live backend (the e2e
    gate). These two catch the actual defects at their call sites.
    """

    @pytest.mark.parametrize("relpath", ["api/account.py", "api/admin.py"])
    def test_no_activitylog_details_kwarg_or_attribute(self, relpath):
        """P0-4: ActivityLog(details=...) / ActivityLog.details.like(...)."""
        tree = _module_ast(relpath)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "ActivityLog":
                kwargs = {kw.arg for kw in node.keywords}
                assert "details" not in kwargs, (
                    f"{relpath}:{node.lineno} passes details= to ActivityLog; there is no "
                    f"such column (use status_reason=). This raises TypeError at runtime."
                )
                assert "source_ip" in kwargs, (
                    f"{relpath}:{node.lineno} omits source_ip, which is NOT NULL — "
                    f"the row would fail with an IntegrityError."
                )
            if isinstance(node, ast.Attribute) and node.attr == "details" \
                    and isinstance(node.value, ast.Name) and node.value.id == "ActivityLog":
                pytest.fail(
                    f"{relpath}:{node.lineno} reads ActivityLog.details; no such column "
                    f"(AttributeError at runtime). Query by token_id instead."
                )

    @pytest.mark.parametrize("relpath", ["api/account.py", "api/admin.py"])
    def test_no_calls_to_undefined_names_in_audit_paths(self, relpath):
        """P0-5: admin.py called log_activity(), which it never imports or defines."""
        tree = _module_ast(relpath)
        bound = _defined_or_imported_names(tree)
        called = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        import builtins
        undefined = called - bound - set(dir(builtins))
        assert not undefined, (
            f"{relpath} calls name(s) that are neither defined nor imported: "
            f"{sorted(undefined)} — NameError at runtime."
        )


class TestActivityLogContract:
    """The column set the call sites must target."""

    def test_activitylog_has_no_details_column(self):
        """`details` is the phantom that caused P0-4 — it must stay gone.

        If someone 'fixes' a future TypeError by ADDING a details column, the six
        call sites would start writing to a column nothing reads, and this test is
        the tripwire. status_reason is the real field.
        """
        columns = {c.name for c in ActivityLog.__table__.columns}
        assert "details" not in columns
        assert "status_reason" in columns

    def test_source_ip_is_not_nullable(self):
        """Why a details= -> status_reason= rename alone was not enough.

        source_ip is NOT NULL, and none of the six account.py sites set it, so a
        pure rename would have swapped TypeError for an IntegrityError.
        """
        assert ActivityLog.__table__.columns["source_ip"].nullable is False

    def test_construction_with_real_columns_persists(self, app, make_account):
        account = make_account("audit_contract_user")
        _db.session.add(ActivityLog(
            account_id=account.id,
            action="dns_create",
            source_ip="203.0.113.7",
            status="success",
            status_reason="vpn.example.com A",
        ))
        _db.session.commit()

        row = ActivityLog.query.filter_by(account_id=account.id).one()
        assert row.status_reason == "vpn.example.com A"
        assert row.source_ip == "203.0.113.7"

    def test_details_kwarg_is_rejected(self, app, make_account):
        """The exact failure the portal hit, pinned so it cannot silently return."""
        account = make_account("audit_details_user")
        with pytest.raises(TypeError):
            ActivityLog(
                account_id=account.id,
                action="dns_create",
                source_ip="203.0.113.7",
                status="success",
                details="this column does not exist",
            )


class TestRealmDetailStats:
    """The per-token stats query joins on token_id, not a LIKE into a phantom column."""

    def test_stats_query_by_token_id_counts_operations(self, app, make_account, make_realm, make_token):
        account = make_account("stats_user")
        realm = make_realm(account)
        token, _plain = make_token(realm)

        for operation, status in (("update", "success"), ("create", "success"), ("read", "denied")):
            _db.session.add(ActivityLog(
                account_id=account.id,
                token_id=token.id,
                action="api_call",
                operation=operation,
                source_ip="203.0.113.9",
                status=status,
            ))
        _db.session.commit()

        logs = ActivityLog.query.filter(ActivityLog.token_id.in_([token.id])).all()
        assert len(logs) == 3

        # 'updates' counts real recorded operations. The old filter matched Netcup API
        # method names ('updateDnsRecords', ...) that are never written as an action,
        # so this count was always 0 even once the crash was fixed.
        updates = sum(1 for log in logs if log.operation in ("update", "create", "delete"))
        successful = sum(1 for log in logs if log.status == "success")
        assert updates == 2
        assert successful == 2

    def test_activity_is_attributable_to_its_token(self, app, make_account, make_realm, make_token):
        """A second token's activity must not be counted against the first."""
        account = make_account("stats_two_token_user")
        realm = make_realm(account)
        token_a, _ = make_token(realm, name="token-a")
        token_b, _ = make_token(realm, name="token-b")

        _db.session.add(ActivityLog(
            account_id=account.id, token_id=token_a.id, action="api_call",
            operation="update", source_ip="203.0.113.1", status="success",
        ))
        _db.session.add(ActivityLog(
            account_id=account.id, token_id=token_b.id, action="api_call",
            operation="delete", source_ip="203.0.113.2", status="success",
        ))
        _db.session.commit()

        only_a = ActivityLog.query.filter(ActivityLog.token_id.in_([token_a.id])).all()
        assert len(only_a) == 1
        assert only_a[0].operation == "update"

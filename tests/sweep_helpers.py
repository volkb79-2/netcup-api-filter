"""Shared mechanics for deterministic Flask authorization and CSRF sweeps."""
from __future__ import annotations

from sqlalchemy import select


HTTP_SWEEP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def rule_methods(rule):
    """Return the HTTP methods relevant to these auth sweeps."""
    return tuple(method for method in HTTP_SWEEP_METHODS if method in rule.methods)


def build_rule_path(rule, values):
    """Build a route path, failing loudly when a new converter is unclassified."""
    missing = set(rule.arguments) - set(values)
    assert missing == set(), f"unclassified path variables for {rule.endpoint}: {sorted(missing)}"
    subdomain, path = rule.build({key: values[key] for key in rule.arguments}, append_unknown=False)
    assert subdomain in (None, ""), f"unexpected subdomain for {rule.endpoint}: {subdomain}"
    return path


def database_snapshot(db):
    """Capture every mapped table so denied requests cannot hide side effects."""
    snapshot = {}
    for table in db.metadata.sorted_tables:
        statement = select(table)
        ordering = tuple(table.primary_key.columns) or tuple(table.columns)
        if ordering:
            statement = statement.order_by(*ordering)
        rows = db.session.execute(statement).all()
        snapshot[table.name] = tuple(tuple(row) for row in rows)
    return snapshot


def sweep_ip(index):
    """Give each request its own address so app-level rate limits cannot mask a guard."""
    third, fourth = divmod(index, 254)
    return f"198.18.{third}.{fourth + 1}"


def sweep_form(csrf_token=None, **extra):
    """Form values that would be ordinary input if a request passed its guard."""
    data = {
        "reason": "authorization sweep",
        "token_name": "sweep-attempt",
        "service_name": "sweep-attempt",
        "display_name": "sweep-attempt",
        "hostname": "owner-a.foreign-sweep.example",
        "type": "A",
        "destination": "192.0.2.123",
        "username": "sweep-probe",
        "password": "not-a-credential",
        "email": "sweep-probe@example.invalid",
        "new_email": "sweep-probe@example.invalid",
        "action": "",
    }
    if csrf_token is not None:
        data["csrf_token"] = csrf_token
    data.update(extra)
    return data

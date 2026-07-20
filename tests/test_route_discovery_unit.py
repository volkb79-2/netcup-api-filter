"""route_discovery must FAIL LOUDLY, not fall back to a stale list (naf-P06 / §P1-F).

The old `discover_routes_from_app()` swallowed any app-import error, printed a warning
pytest hides, and returned a hardcoded ~21-route list — silently shrinking the flagship
route-smoke suite while it stayed green. These tests pin the new contract at the unit
level (the behavioural ui_tests half needs the e2e gate).

Scope note: this file is a deliberate addition beyond naf-P06's stated scope.touch, so
that O1 (loud failure) is provable under the `unit` gate rather than only via ui_tests
collection. Recorded in nyxloom-trove/reports/ORCHESTRATION-2026-07-20.md.
"""
import importlib

import pytest

import ui_tests.route_discovery as rd


def test_static_fallback_is_gone():
    """The silent fallback function must not exist — its presence is the hazard."""
    assert not hasattr(rd, "discover_routes_static"), (
        "discover_routes_static() still exists; a stale hardcoded list must not be able "
        "to silently substitute for live discovery."
    )


def test_discovery_raises_on_app_import_failure(monkeypatch):
    """When create_app() fails, discovery RAISES — it does not return a degraded list."""
    def _boom():
        raise RuntimeError("simulated app import failure")

    # create_app is imported inside the function from netcup_api_filter.app, so patch it
    # at the source module.
    import netcup_api_filter.app as app_module
    monkeypatch.setattr(app_module, "create_app", _boom)

    with pytest.raises(RuntimeError) as exc_info:
        rd.discover_routes_from_app()
    # The raised error must name the real cause, not mask it.
    assert "simulated app import failure" in repr(exc_info.value)


def test_discovery_succeeds_and_finds_many_routes():
    """On a healthy app, discovery returns a rich registry (the floor the suite relies on)."""
    registry = rd.discover_routes_from_app()
    admin = [r for r in registry.routes if r.category == "admin"]
    # Far above the old 21-route fallback; the real app has ~30 admin routes.
    assert len(admin) >= 15, f"only {len(admin)} admin routes discovered"
    # Sanity: real discovery includes parametrized routes the static list never had.
    assert any(r.has_params for r in registry.routes)

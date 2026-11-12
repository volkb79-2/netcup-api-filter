"""Unit tests for seed_delegated_zone_domain_root (D-007 app-side backend seed).

Covers the contract used by tooling/app-local/post_compose_seed_domain.py:
- empty zone => no-op (no rows created)
- non-empty zone => idempotently creates exactly one BackendService (powerdns,
  platform-owned, pointing at the INTERNAL PowerDNS API) and one
  ManagedDomainRoot bound to it, with the models' real required fields
  populated
- running the seed twice never creates a second row of either
- missing PowerDNS credentials (no explicit args, no env) raises loudly
  rather than inventing a value (D-007)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from netcup_api_filter.bootstrap.seeding import (
    DELEGATED_ZONE_BACKEND_SERVICE_NAME,
    seed_delegated_zone_domain_root,
)
from netcup_api_filter.models import (
    BackendProvider,
    BackendService,
    ManagedDomainRoot,
    OwnerTypeEnum,
    VisibilityEnum,
)

ZONE = "managed.vxxu.de"
API_URL = "http://naf-instance42-powerdns:8081"  # fixture identity, not a real container
API_KEY = "test-powerdns-api-key"


def test_empty_zone_is_a_noop(app, db):
    result = seed_delegated_zone_domain_root("", api_url=API_URL, api_key=API_KEY)
    assert result is None
    assert BackendService.query.filter_by(
        service_name=DELEGATED_ZONE_BACKEND_SERVICE_NAME
    ).first() is None
    assert ManagedDomainRoot.query.count() == 0


def test_none_zone_is_a_noop(app, db):
    # Defensive: callers pass config.get(...) results, which may be None.
    result = seed_delegated_zone_domain_root(None, api_url=API_URL, api_key=API_KEY)
    assert result is None
    assert BackendService.query.count() == 0


def test_seeds_backend_service_and_domain_root_with_required_fields(app, db):
    root = seed_delegated_zone_domain_root(ZONE, api_url=API_URL, api_key=API_KEY)

    assert root is not None
    assert root.root_domain == ZONE
    assert root.dns_zone == ZONE
    assert root.is_active is True
    assert root.visibility is not None
    assert root.visibility.visibility_code == VisibilityEnum.PRIVATE

    service = BackendService.query.filter_by(
        service_name=DELEGATED_ZONE_BACKEND_SERVICE_NAME
    ).first()
    assert service is not None
    assert root.backend_service_id == service.id

    # Provider must actually be PowerDNS (BackendProvider FK), not just named that.
    provider = BackendProvider.query.get(service.provider_id)
    assert provider is not None
    assert provider.provider_code == "powerdns"

    # Ownership: platform/system-owned, per the task ("a user/system owns it").
    assert service.owner_type is not None
    assert service.owner_type.owner_code == OwnerTypeEnum.PLATFORM
    assert service.owner_id is None
    assert service.is_active is True

    # Config must point at the INTERNAL PowerDNS API, not a public/proxy URL.
    config = service.get_config()
    assert config["api_url"] == API_URL
    assert config["api_key"] == API_KEY


def test_zone_with_trailing_dot_and_whitespace_is_normalized(app, db):
    root = seed_delegated_zone_domain_root("  managed.vxxu.de.  ", api_url=API_URL, api_key=API_KEY)
    assert root.root_domain == ZONE
    assert root.dns_zone == ZONE


def test_idempotent_run_twice_yields_one_row_each(app, db):
    first = seed_delegated_zone_domain_root(ZONE, api_url=API_URL, api_key=API_KEY)
    second = seed_delegated_zone_domain_root(ZONE, api_url=API_URL, api_key=API_KEY)

    assert first.id == second.id
    assert BackendService.query.filter_by(
        service_name=DELEGATED_ZONE_BACKEND_SERVICE_NAME
    ).count() == 1
    assert ManagedDomainRoot.query.filter_by(root_domain=ZONE).count() == 1


def test_idempotent_second_call_with_different_credentials_keeps_original_service(app, db):
    # Once created, the BackendService config is not silently overwritten by a
    # later re-run with different (e.g. rotated) credentials passed in —
    # get-or-create semantics, matching create_backend_service's own pattern.
    seed_delegated_zone_domain_root(ZONE, api_url=API_URL, api_key=API_KEY)
    seed_delegated_zone_domain_root(ZONE, api_url="http://other:9999", api_key="other-key")

    assert BackendService.query.filter_by(
        service_name=DELEGATED_ZONE_BACKEND_SERVICE_NAME
    ).count() == 1
    service = BackendService.query.filter_by(
        service_name=DELEGATED_ZONE_BACKEND_SERVICE_NAME
    ).first()
    assert service.get_config()["api_url"] == API_URL


def test_missing_credentials_raises_instead_of_inventing_values(app, db, monkeypatch):
    monkeypatch.delenv("POWERDNS_API_URL_INTERNAL", raising=False)
    monkeypatch.delenv("POWERDNS_API_KEY", raising=False)

    with pytest.raises(RuntimeError):
        seed_delegated_zone_domain_root(ZONE)

    assert BackendService.query.count() == 0


def test_credentials_fall_back_to_environment(app, db, monkeypatch):
    monkeypatch.setenv("POWERDNS_API_URL_INTERNAL", API_URL)
    monkeypatch.setenv("POWERDNS_API_KEY", API_KEY)

    root = seed_delegated_zone_domain_root(ZONE)

    assert root is not None
    service = BackendService.query.get(root.backend_service_id)
    assert service.get_config()["api_url"] == API_URL
    assert service.get_config()["api_key"] == API_KEY

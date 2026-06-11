"""Canonical DNS realm configuration templates.

This module is the single **code** source of truth for the pre-configured realm
templates surfaced in the admin and account portals (the "quick template"
wizards on the realm-create / realm-request forms).

The companion human-readable product document is the repo-root
``CLIENT_TEMPLATES.md``. That file is the narrative reference (use cases,
security notes, integration examples) for humans; **this module is the source of
truth consumed by code**. When the two disagree, reconcile the doc to match this
module (or update both together).

Each template is a plain ``dict`` with a stable, snake_case ``id``:

==========================  =============  =================================  ==============================
id                          realm_type     record_types                       operations
==========================  =============  =================================  ==============================
ddns_single_host            host           A, AAAA                             read, update
ddns_subdomain_delegation   subdomain      A, AAAA, CNAME                     read, create, update, delete
monitoring_readonly         host           A, AAAA, CNAME, NS, TXT, MX        read
letsencrypt_dns01           subdomain      TXT                                read, create, delete
full_dns_management         host           A, AAAA, CNAME, NS, TXT, MX, SRV   read, create, update, delete
cname_delegation            subdomain      CNAME                              read, create, update, delete
==========================  =============  =================================  ==============================

Schema of each entry:
    id            (str)  Stable snake_case identifier. Used as the dict key the
                         template-wizard JS indexes (``templates[id]``) and the
                         ``applyTemplate('<id>')`` / ``selectTemplate('<id>', ...)``
                         button hooks. Do not rename without updating templates.
    name          (str)  Human-readable display name.
    icon          (str)  Emoji icon shown in the picker.
    realm_type    (str)  One of ``host`` / ``subdomain`` / ``subdomain_only``.
    record_types  (list) Allowed DNS record types (e.g. ``["A", "AAAA"]``).
    operations    (list) Allowed operations from ``read`` / ``create`` /
                         ``update`` / ``delete``.
    description   (str)  Short one-line description for the picker card.

Public exports:
    REALM_TEMPLATES        list of the template dicts (ordered as in CLIENT_TEMPLATES.md).
    REALM_TEMPLATES_BY_ID  dict mapping ``id`` -> template dict.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Ordered to match CLIENT_TEMPLATES.md ("Template Reference" sections 1-6).
REALM_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "ddns_single_host",
        "name": "DDNS Single Host",
        "icon": "🏠",
        "realm_type": "host",
        "record_types": ["A", "AAAA"],
        "operations": ["read", "update"],
        "description": "Update IP address for a single hostname (home router, VPN endpoint)",
    },
    {
        "id": "ddns_subdomain_delegation",
        "name": "DDNS Subdomain Delegation",
        "icon": "🌐",
        "realm_type": "subdomain",
        "record_types": ["A", "AAAA", "CNAME"],
        "operations": ["read", "create", "update", "delete"],
        "description": "Manage a subdomain and all hosts under it (IoT fleet, K8s)",
    },
    {
        "id": "monitoring_readonly",
        "name": "Read-Only Monitoring",
        "icon": "👁️",
        "realm_type": "host",
        "record_types": ["A", "AAAA", "CNAME", "NS", "TXT", "MX"],
        "operations": ["read"],
        "description": "View-only access for monitoring and dashboards",
    },
    {
        "id": "letsencrypt_dns01",
        "name": "LetsEncrypt DNS-01",
        "icon": "🔒",
        "realm_type": "subdomain",
        "record_types": ["TXT"],
        "operations": ["read", "create", "delete"],
        "description": "ACME DNS-01 challenge for automated certificate issuance",
    },
    {
        "id": "full_dns_management",
        "name": "Full DNS Management",
        "icon": "⚙️",
        "realm_type": "host",
        "record_types": ["A", "AAAA", "CNAME", "NS", "TXT", "MX", "SRV"],
        "operations": ["read", "create", "update", "delete"],
        "description": "Complete DNS control for automation and IaC (CI/CD, Terraform)",
    },
    {
        "id": "cname_delegation",
        "name": "CNAME Delegation",
        "icon": "🔗",
        "realm_type": "subdomain",
        "record_types": ["CNAME"],
        "operations": ["read", "create", "update", "delete"],
        "description": "Delegate CNAME management for CDN/load balancer aliases",
    },
]

# Convenience lookup by id.
REALM_TEMPLATES_BY_ID: Dict[str, Dict[str, Any]] = {
    tpl["id"]: tpl for tpl in REALM_TEMPLATES
}

__all__ = ["REALM_TEMPLATES", "REALM_TEMPLATES_BY_ID"]

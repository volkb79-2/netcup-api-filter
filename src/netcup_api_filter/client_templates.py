"""Client configuration templates for common use cases."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class ClientTemplate:
    """Template for client configuration."""
    
    id: str
    name: str
    description: str
    icon: str
    realm_type: str
    record_types: List[str]
    operations: List[str]
    example_realm_value: str
    use_case_description: str
    recommended_for: List[str]


# Template definitions for common scenarios
CLIENT_TEMPLATES = [
    ClientTemplate(
        id="ddns_single_host",
        name="DDNS Single Host",
        description="Update IP address for a single hostname (e.g., home.example.com)",
        icon="🏠",
        realm_type="host",
        record_types=["A", "AAAA"],
        operations=["read", "update"],
        example_realm_value="home.example.com",
        use_case_description="Dynamic DNS for a single host that needs to update its IP address (e.g., home router, VPN endpoint)",
        recommended_for=[
            "Home network with dynamic IP",
            "VPN server with changing IP",
            "Single server/device DDNS",
        ]
    ),
    
    ClientTemplate(
        id="ddns_subdomain_zone",
        name="DDNS Subdomain Delegation",
        description="Full control over subdomain zone (e.g., *.dyn.example.com)",
        icon="🌐",
        realm_type="subdomain",
        record_types=["A", "AAAA", "CNAME"],
        operations=["read", "update", "create", "delete"],
        example_realm_value="dyn.example.com",
        use_case_description="Delegate entire subdomain for dynamic hosts (multiple devices can register under dyn.example.com)",
        recommended_for=[
            "Multiple dynamic hosts in subdomain",
            "IoT device fleet registration",
            "Kubernetes external-dns integration",
        ]
    ),
    
    ClientTemplate(
        id="monitoring_readonly",
        name="Read-Only Monitoring",
        description="View DNS records without modification rights",
        icon="👁️",
        realm_type="host",
        record_types=["A", "AAAA", "CNAME", "NS", "TXT", "MX"],
        operations=["read"],
        example_realm_value="example.com",
        use_case_description="Monitor DNS configuration without write access (auditing, compliance, dashboards)",
        recommended_for=[
            "Monitoring dashboards",
            "Compliance auditing",
            "DNS health checks",
        ]
    ),
    
    ClientTemplate(
        id="letsencrypt_dns01",
        name="LetsEncrypt DNS-01 Challenge",
        description="Create/delete TXT records for ACME DNS-01 validation",
        icon="🔒",
        realm_type="subdomain",
        record_types=["TXT"],
        operations=["read", "create", "delete"],
        example_realm_value="_acme-challenge.example.com",
        use_case_description="Automated certificate issuance via DNS-01 challenge (certbot, acme.sh, Traefik)",
        recommended_for=[
            "Certbot DNS-01 plugin",
            "Traefik ACME DNS challenge",
            "Automated wildcard certificates",
        ]
    ),
    
    ClientTemplate(
        id="full_management",
        name="Full DNS Management",
        description="Complete control over all record types and operations",
        icon="⚙️",
        realm_type="host",
        record_types=["A", "AAAA", "CNAME", "NS", "TXT", "MX", "SRV"],
        operations=["read", "update", "create", "delete"],
        example_realm_value="example.com",
        use_case_description="Full DNS management API for automation, CI/CD, or DNS provider integration",
        recommended_for=[
            "CI/CD deployment automation",
            "Infrastructure as Code (Terraform)",
            "Custom DNS management tools",
        ]
    ),
    
    ClientTemplate(
        id="cname_only",
        name="CNAME Delegation",
        description="Manage CNAME records only (alias delegation)",
        icon="🔗",
        realm_type="subdomain",
        record_types=["CNAME"],
        operations=["read", "update", "create", "delete"],
        example_realm_value="cdn.example.com",
        use_case_description="Delegate CNAME management for CDN/service provider integration",
        recommended_for=[
            "CDN provider integration (Cloudflare, Fastly)",
            "SaaS service CNAME delegation",
            "Load balancer alias management",
        ]
    ),
]


def get_template(template_id: str) -> ClientTemplate | None:
    """Get template by ID."""
    for template in CLIENT_TEMPLATES:
        if template.id == template_id:
            return template
    return None


def get_all_templates() -> List[ClientTemplate]:
    """Get all available templates."""
    return CLIENT_TEMPLATES


def get_templates_by_realm_type(realm_type: str) -> List[ClientTemplate]:
    """Get templates filtered by realm type."""
    return [t for t in CLIENT_TEMPLATES if t.realm_type == realm_type]


def apply_template_to_form(template: ClientTemplate) -> dict:
    """Convert template to form default values."""
    return {
        'realm_type': template.realm_type,
        'allowed_record_types': template.record_types,
        'allowed_operations': template.operations,
        # realm_value and client_id must be provided by user
    }

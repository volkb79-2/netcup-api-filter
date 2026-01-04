"""
API v2 Blueprints for Account → Realms → Tokens architecture.

Provides:
- account_bp: Account portal (login, registration, dashboard, settings)
- admin_bp: Admin portal (account/realm management, approvals)
- dns_api_bp: DNS proxy API with Bearer token auth
- ddns_protocols_bp: DDNS protocol endpoints (DynDNS2, No-IP)
"""
from .account import account_bp
from .admin import admin_bp
from .dns_api import dns_api_bp
from .ddns_protocols import ddns_protocols_bp

__all__ = ['account_bp', 'admin_bp', 'dns_api_bp', 'ddns_protocols_bp']

"""
DNS Backend Abstraction Layer.

This module provides a pluggable backend system for DNS providers.
Each backend implements the DNSBackend interface.

Supported providers:
- netcup: Netcup CCP API
- powerdns: PowerDNS Authoritative Server

Usage:
    from netcup_api_filter.backends import get_backend, get_backend_for_realm
    
    # Get backend by provider code and config
    backend = get_backend('netcup', {'customer_id': '...', 'api_key': '...'})
    
    # Get backend for a realm (auto-resolves from domain root or user backend)
    backend = get_backend_for_realm(realm)
"""

from .base import DNSBackend, BackendError
from .registry import get_backend, get_backend_for_realm, BACKEND_REGISTRY
from .netcup import NetcupBackend
from .powerdns import PowerDNSBackend

__all__ = [
    'DNSBackend',
    'BackendError',
    'get_backend',
    'get_backend_for_realm',
    'BACKEND_REGISTRY',
    'NetcupBackend',
    'PowerDNSBackend',
]

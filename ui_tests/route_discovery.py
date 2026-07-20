#!/usr/bin/env python3
"""
Route Discovery Module

Automatically discovers all Flask routes from the application and categorizes
them for testing and screenshot capture.

This module:
1. Imports the Flask app to access app.url_map
2. Categorizes routes by authentication requirements
3. Generates test/screenshot lists dynamically
4. Eliminates hardcoded route lists throughout the codebase
"""
import sys
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set
import re

# Add src to path for imports
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "deploy-local" / "src"))
sys.path.insert(0, str(REPO_ROOT / "deploy-local" / "vendor"))


@dataclass
class RouteInfo:
    """Information about a discovered route."""
    rule: str  # URL pattern like /admin/accounts/<int:id>
    endpoint: str  # Function name
    methods: Set[str]  # HTTP methods
    blueprint: Optional[str] = None  # Blueprint name if applicable
    auth_required: str = "unknown"  # none, admin, client, api
    has_params: bool = False  # Whether route has URL parameters
    
    @property
    def is_get(self) -> bool:
        return "GET" in self.methods
    
    @property
    def is_static(self) -> bool:
        """True if route has no URL parameters."""
        return not self.has_params
    
    @property
    def category(self) -> str:
        """Determine route category from URL pattern."""
        if self.rule.startswith("/admin"):
            return "admin"
        elif self.rule.startswith("/account"):
            # Historical naming: tests refer to the user portal as "client".
            # The actual app routes are under /account.
            return "client"
        elif self.rule.startswith("/api"):
            return "api"
        elif self.rule in ("/", "/health"):
            return "public"
        else:
            return "misc"


@dataclass
class RouteRegistry:
    """Registry of all discovered routes."""
    routes: List[RouteInfo] = field(default_factory=list)
    
    def add(self, route: RouteInfo):
        self.routes.append(route)
    
    def by_category(self, category: str) -> List[RouteInfo]:
        return [r for r in self.routes if r.category == category]
    
    def get_routes(self) -> List[RouteInfo]:
        return [r for r in self.routes if r.is_get]
    
    def static_routes(self) -> List[RouteInfo]:
        """Routes without URL parameters (can be visited directly)."""
        return [r for r in self.routes if r.is_static and r.is_get]
    
    def admin_pages(self) -> List[RouteInfo]:
        """Admin pages suitable for screenshots."""
        return [r for r in self.static_routes() if r.category == "admin"]
    
    def client_pages(self) -> List[RouteInfo]:
        """Client pages suitable for screenshots."""
        return [r for r in self.static_routes() if r.category == "client"]
    
    def public_pages(self) -> List[RouteInfo]:
        """Public pages (no auth required)."""
        return [r for r in self.static_routes() if r.category in ("public", "misc")]


def discover_routes_from_app() -> RouteRegistry:
    """Discover routes by importing the Flask app."""
    registry = RouteRegistry()
    
    try:
        # Set up minimal environment for import
        os.environ.setdefault("FLASK_ENV", "testing")
        os.environ.setdefault("SECRET_KEY", "route-discovery-key")

        # Route discovery must not depend on any existing on-disk database, which may
        # be an older schema. Use a dedicated scratch DB to guarantee schema matches
        # current models (init_db() calls create_all()).
        scratch_dir = REPO_ROOT / "tmp"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        scratch_db = scratch_dir / "route_discovery.db"
        if scratch_db.exists():
            scratch_db.unlink()
        os.environ.setdefault("NETCUP_FILTER_DB_PATH", str(scratch_db))
        
        from netcup_api_filter.app import create_app
        app = create_app()
        
        with app.app_context():
            for rule in app.url_map.iter_rules():
                # Skip static files
                if rule.endpoint == "static":
                    continue
                
                # Determine blueprint
                blueprint = None
                if "." in rule.endpoint:
                    blueprint = rule.endpoint.split(".")[0]
                
                # Check for URL parameters
                has_params = bool(re.search(r"<[^>]+>", rule.rule))
                
                # Determine auth requirements
                auth_required = "unknown"
                if rule.rule.startswith("/admin"):
                    auth_required = "admin"
                elif rule.rule.startswith("/account"):
                    # Keep historical label for compatibility with existing callers.
                    auth_required = "client"
                elif rule.rule.startswith("/api"):
                    auth_required = "api"
                elif rule.rule in ("/", "/health", "/login", "/register"):
                    auth_required = "none"
                
                route = RouteInfo(
                    rule=rule.rule,
                    endpoint=rule.endpoint,
                    methods=set(rule.methods) - {"OPTIONS", "HEAD"},
                    blueprint=blueprint,
                    auth_required=auth_required,
                    has_params=has_params,
                )
                registry.add(route)
                
    except Exception as e:
        # FAIL LOUDLY. The old behavior swallowed this exception, printed a warning
        # pytest hides, and returned a stale ~21-route hardcoded list — which silently
        # shrank route-smoke from ~86 to ~45 tests (and ci_smoke ~93 -> ~50) while the
        # suite stayed green, so new or broken routes got zero coverage. A route-smoke
        # run that cannot discover the real routes is not a weaker signal, it is NO
        # signal, and must abort rather than pretend. See naf-P06 / review §P1-F.
        raise RuntimeError(
            f"Route discovery could not import the Flask app: {e!r}. Refusing to fall "
            f"back to a stale static route list — fix the import (a common cause is an "
            f"unwritable tmp/route_discovery.db) rather than running a hollow suite."
        ) from e

    return registry


def get_screenshot_pages() -> Dict[str, List[str]]:
    """Get pages suitable for screenshot capture, organized by category."""
    registry = discover_routes_from_app()
    
    return {
        "public": [r.rule for r in registry.public_pages()],
        "admin": [r.rule for r in registry.admin_pages()],
        "client": [r.rule for r in registry.client_pages()],
    }


def get_test_routes() -> Dict[str, List[str]]:
    """Get all routes for testing, organized by category."""
    registry = discover_routes_from_app()
    
    return {
        "admin": [r.rule for r in registry.by_category("admin") if r.is_get],
        "client": [r.rule for r in registry.by_category("client") if r.is_get],
        "api": [r.rule for r in registry.by_category("api")],
        "public": [r.rule for r in registry.by_category("public") if r.is_get],
    }


if __name__ == "__main__":
    print("=== Route Discovery ===\n")
    
    registry = discover_routes_from_app()
    
    print(f"Total routes discovered: {len(registry.routes)}")
    print(f"GET routes: {len(registry.get_routes())}")
    print(f"Static routes (no params): {len(registry.static_routes())}")
    print()
    
    for category in ["public", "admin", "client", "api", "misc"]:
        routes = registry.by_category(category)
        print(f"\n=== {category.upper()} ({len(routes)} routes) ===")
        for r in sorted(routes, key=lambda x: x.rule):
            params = " (has params)" if r.has_params else ""
            methods = ",".join(sorted(r.methods))
            print(f"  [{methods}] {r.rule}{params}")
    
    print("\n=== Screenshot-Ready Pages ===")
    pages = get_screenshot_pages()
    for category, routes in pages.items():
        print(f"\n{category.upper()}:")
        for route in sorted(routes):
            print(f"  {route}")

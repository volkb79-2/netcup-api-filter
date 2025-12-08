"""GeoIP service for IP geolocation.

Uses MaxMind GeoIP2 Web Services API for production.
Falls back to mock server for local testing.

Documentation:
- https://dev.maxmind.com/geoip/geolocate-an-ip/web-services/
- https://pypi.org/project/geoip2/

Configuration:
- MAXMIND_ACCOUNT_ID: Account ID from MaxMind
- MAXMIND_LICENSE_KEY: License key from MaxMind
- MAXMIND_API_URL: Override API URL for mock server (optional)
"""
from __future__ import annotations

import os
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
import threading

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TTL_HOURS = int(os.environ.get("GEOIP_CACHE_HOURS", "24"))
CACHE_MAX_SIZE = int(os.environ.get("GEOIP_CACHE_SIZE", "1000"))


@dataclass
class GeoIPResult:
    """Result from GeoIP lookup."""
    
    ip: str
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None
    continent: Optional[str] = None
    subdivision: Optional[str] = None
    postal_code: Optional[str] = None
    error: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if result has location data."""
        return self.country_code is not None and self.country_code != "XX"
    
    @property
    def location_string(self) -> str:
        """Get human-readable location string."""
        parts = []
        if self.city:
            parts.append(self.city)
        if self.subdivision:
            parts.append(self.subdivision)
        if self.country_name:
            parts.append(self.country_name)
        
        if parts:
            return ", ".join(parts)
        elif self.country_code and self.country_code != "XX":
            return self.country_code
        else:
            return "Unknown"
    
    @property
    def flag_emoji(self) -> str:
        """Get flag emoji for country code."""
        if not self.country_code or self.country_code == "XX":
            return "🌍"
        
        # Convert country code to regional indicator symbols
        try:
            return "".join(chr(ord(c) + 127397) for c in self.country_code.upper())
        except Exception:
            return "🌍"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ip": self.ip,
            "country_code": self.country_code,
            "country_name": self.country_name,
            "city": self.city,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timezone": self.timezone,
            "continent": self.continent,
            "subdivision": self.subdivision,
            "postal_code": self.postal_code,
            "location": self.location_string,
            "flag": self.flag_emoji,
            "error": self.error
        }


class GeoIPCache:
    """Thread-safe TTL cache for GeoIP results."""
    
    def __init__(self, max_size: int = CACHE_MAX_SIZE, ttl_hours: int = CACHE_TTL_HOURS):
        self.max_size = max_size
        self.ttl = timedelta(hours=ttl_hours)
        self._cache: Dict[str, tuple[GeoIPResult, datetime]] = {}
        self._lock = threading.Lock()
    
    def get(self, ip: str) -> Optional[GeoIPResult]:
        """Get cached result if not expired."""
        with self._lock:
            if ip not in self._cache:
                return None
            
            result, cached_at = self._cache[ip]
            if datetime.utcnow() - cached_at > self.ttl:
                del self._cache[ip]
                return None
            
            return result
    
    def set(self, ip: str, result: GeoIPResult):
        """Cache a result."""
        with self._lock:
            # Evict old entries if at capacity
            if len(self._cache) >= self.max_size:
                # Remove oldest entry
                oldest_ip = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest_ip]
            
            self._cache[ip] = (result, datetime.utcnow())
    
    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()


# Global cache instance
_cache = GeoIPCache()


def _get_config() -> tuple[str, str, str]:
    """Get MaxMind configuration from environment.
    
    Returns:
        (account_id, license_key, api_url)
    """
    account_id = os.environ.get("MAXMIND_ACCOUNT_ID", "")
    license_key = os.environ.get("MAXMIND_LICENSE_KEY", "")
    api_url = os.environ.get("MAXMIND_API_URL", "https://geoip.maxmind.com")
    
    return account_id, license_key, api_url


def _is_private_ip(ip: str) -> bool:
    """Check if IP is private/reserved."""
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    
    try:
        first = int(parts[0])
        second = int(parts[1])
        
        # 10.0.0.0/8
        if first == 10:
            return True
        # 172.16.0.0/12
        if first == 172 and 16 <= second <= 31:
            return True
        # 192.168.0.0/16
        if first == 192 and second == 168:
            return True
        # 127.0.0.0/8 (loopback)
        if first == 127:
            return True
        # 169.254.0.0/16 (link-local)
        if first == 169 and second == 254:
            return True
        
        return False
    except ValueError:
        return False


def lookup(ip: str, use_cache: bool = True) -> GeoIPResult:
    """Look up geolocation for an IP address.
    
    Args:
        ip: IP address to look up
        use_cache: Whether to use cached results
        
    Returns:
        GeoIPResult with location data or error
    """
    # Check cache first
    if use_cache:
        cached = _cache.get(ip)
        if cached:
            logger.debug(f"GeoIP cache hit for {ip}")
            return cached
    
    # Skip private IPs
    if _is_private_ip(ip):
        result = GeoIPResult(
            ip=ip,
            error="Private IP address"
        )
        if use_cache:
            _cache.set(ip, result)
        return result
    
    # Get configuration
    account_id, license_key, api_url = _get_config()
    
    if not account_id or not license_key:
        logger.warning("MaxMind credentials not configured")
        return GeoIPResult(
            ip=ip,
            error="GeoIP not configured"
        )
    
    try:
        # Use geoip2 library if available
        try:
            import geoip2.webservice
            
            client = geoip2.webservice.Client(
                int(account_id),
                license_key,
                host=api_url.replace("https://", "").replace("http://", "")
            )
            
            response = client.city(ip)
            
            result = GeoIPResult(
                ip=ip,
                country_code=response.country.iso_code,
                country_name=response.country.name,
                city=response.city.name if response.city else None,
                latitude=response.location.latitude if response.location else None,
                longitude=response.location.longitude if response.location else None,
                timezone=response.location.time_zone if response.location else None,
                continent=response.continent.name if response.continent else None,
                subdivision=response.subdivisions.most_specific.name if response.subdivisions else None,
                postal_code=response.postal.code if response.postal else None
            )
            
            logger.debug(f"GeoIP lookup for {ip}: {result.location_string}")
            
            if use_cache:
                _cache.set(ip, result)
            
            return result
            
        except ImportError:
            # Fallback to direct HTTP if geoip2 not installed
            return _lookup_http(ip, account_id, license_key, api_url, use_cache)
            
    except Exception as e:
        logger.error(f"GeoIP lookup failed for {ip}: {e}")
        return GeoIPResult(
            ip=ip,
            error=str(e)
        )


def _lookup_http(
    ip: str,
    account_id: str,
    license_key: str,
    api_url: str,
    use_cache: bool
) -> GeoIPResult:
    """Fallback HTTP-based lookup without geoip2 library."""
    import base64
    
    try:
        import httpx
    except ImportError:
        import urllib.request
        import json
        
        # Build request
        url = f"{api_url}/geoip/v2.1/city/{ip}"
        credentials = base64.b64encode(f"{account_id}:{license_key}".encode()).decode()
        
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Basic {credentials}")
        req.add_header("Accept", "application/json")
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        return _parse_response(ip, data, use_cache)
    
    # Use httpx if available
    url = f"{api_url}/geoip/v2.1/city/{ip}"
    credentials = base64.b64encode(f"{account_id}:{license_key}".encode()).decode()
    
    with httpx.Client(timeout=10.0) as client:
        response = client.get(
            url,
            headers={
                "Authorization": f"Basic {credentials}",
                "Accept": "application/json"
            }
        )
        
        if response.status_code != 200:
            return GeoIPResult(
                ip=ip,
                error=f"API error: {response.status_code}"
            )
        
        data = response.json()
    
    return _parse_response(ip, data, use_cache)


def _parse_response(ip: str, data: Dict[str, Any], use_cache: bool) -> GeoIPResult:
    """Parse MaxMind API response into GeoIPResult."""
    result = GeoIPResult(
        ip=ip,
        country_code=data.get("country", {}).get("iso_code"),
        country_name=data.get("country", {}).get("names", {}).get("en"),
        city=data.get("city", {}).get("names", {}).get("en"),
        latitude=data.get("location", {}).get("latitude"),
        longitude=data.get("location", {}).get("longitude"),
        timezone=data.get("location", {}).get("time_zone"),
        continent=data.get("continent", {}).get("names", {}).get("en"),
        postal_code=data.get("postal", {}).get("code")
    )
    
    # Get subdivision (state/province)
    subdivisions = data.get("subdivisions", [])
    if subdivisions:
        result.subdivision = subdivisions[0].get("names", {}).get("en")
    
    if use_cache:
        _cache.set(ip, result)
    
    return result


def clear_cache():
    """Clear the GeoIP cache."""
    _cache.clear()
    logger.info("GeoIP cache cleared")


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    return {
        "size": len(_cache._cache),
        "max_size": _cache.max_size,
        "ttl_hours": CACHE_TTL_HOURS
    }


def get_geoip_status() -> Dict[str, Any]:
    """Get GeoIP service status for system info display.
    
    Returns dict with:
        - available: bool - whether GeoIP lookups will work
        - account_id: str - configured account ID (masked)
        - api_url: str - API endpoint being used
        - cache_stats: dict - cache statistics
        - has_geoip2: bool - whether geoip2 library is available
        - error: str - error message if not available
    """
    account_id = os.environ.get("MAXMIND_ACCOUNT_ID", "")
    license_key = os.environ.get("MAXMIND_LICENSE_KEY", "")
    api_url = os.environ.get("MAXMIND_API_URL", "https://geoip.maxmind.com")
    
    # Check if geoip2 library is available
    has_geoip2 = False
    try:
        import geoip2.webservice  # noqa: F401
        has_geoip2 = True
    except ImportError:
        pass
    
    status = {
        "available": bool(account_id and license_key),
        "account_id": account_id[:4] + "..." if len(account_id) > 4 else ("(not set)" if not account_id else account_id),
        "api_url": api_url,
        "cache_stats": get_cache_stats(),
        "has_geoip2": has_geoip2,
    }
    
    if not account_id:
        status["error"] = "MAXMIND_ACCOUNT_ID not configured"
    elif not license_key:
        status["error"] = "MAXMIND_LICENSE_KEY not configured"
    
    return status


# Convenience function for templates
def geoip_location(ip: str) -> str:
    """Get location string for an IP (for use in templates).
    
    Returns "Unknown" if lookup fails.
    """
    try:
        result = lookup(ip)
        return result.location_string
    except Exception:
        return "Unknown"

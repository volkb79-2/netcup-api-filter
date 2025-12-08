"""
Integrated Journey-Based Testing Framework

This package contains sequential journey tests that:
1. CREATE data they need (never skip due to missing data)
2. CAPTURE screenshots at each state transition
3. VALIDATE behavior through both UI and API
4. BUILD on prior journey state

Journey execution order is critical:
- J1: Fresh Deployment - establishes base state
- J2: Account Lifecycle - needs J1's fresh database
- J3: Realm & Token - needs J2's approved account
- J4: Error States - documents all error conditions

Run with:
    pytest ui_tests/tests/test_journey_master.py -v
"""

from typing import Any, Dict

# Shared journey state passed between tests
class JourneyState:
    """Mutable container for state shared across journey tests."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset to initial state."""
        self.admin_password: str | None = None
        self.admin_logged_in: bool = False
        
        # Account lifecycle state
        self.test_account_username: str | None = None
        self.test_account_email: str | None = None
        self.test_account_password: str | None = None
        self.test_account_id: int | None = None
        self.test_account_approved: bool = False
        
        # Realm state
        self.test_realm_value: str | None = None
        self.test_realm_id: int | None = None
        self.test_realm_approved: bool = False
        
        # Token state
        self.test_token_id: int | None = None
        self.test_token_value: str | None = None
        self.test_token_revoked: bool = False
        
        # Screenshot counter for ordering
        self.screenshot_counter: int = 0
        
        # Captured screenshots for summary
        self.screenshots: list[tuple[str, str]] = []
        
        # Dynamic attributes for journey-specific state
        self._extra: Dict[str, Any] = {}
    
    def set_extra(self, key: str, value: Any):
        """Set dynamic attribute."""
        self._extra[key] = value
    
    def get_extra(self, key: str, default: Any = None) -> Any:
        """Get dynamic attribute."""
        return self._extra.get(key, default)
    
    def next_screenshot_name(self, journey: str, name: str) -> str:
        """Generate sequential screenshot name."""
        self.screenshot_counter += 1
        return f"{journey}-{self.screenshot_counter:02d}-{name}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Export state for logging/debugging."""
        return {
            "admin_password": "***" if self.admin_password else None,
            "admin_logged_in": self.admin_logged_in,
            "test_account_username": self.test_account_username,
            "test_account_email": self.test_account_email,
            "test_account_id": self.test_account_id,
            "test_account_approved": self.test_account_approved,
            "test_realm_value": self.test_realm_value,
            "test_realm_id": self.test_realm_id,
            "test_realm_approved": self.test_realm_approved,
            "test_token_id": self.test_token_id,
            "test_token_revoked": self.test_token_revoked,
            "screenshot_count": len(self.screenshots),
        }


# Global journey state instance
journey_state = JourneyState()

"""
Journey-based testing for comprehensive UI/API validation.

This package contains ordered test journeys that:
1. Build on each other (data created in journey N is available in N+1)
2. Capture screenshots at every significant state
3. Verify both UI and API behavior
4. Test email flows via Mailpit integration

Journey Order:
    00 - Auth enforcement (all routes require proper auth)
    01 - Admin bootstrap (login, change password, empty states)
    02 - Account lifecycle (create, approve, detail)
    03 - Realm management (add realms, configure, tokens)
    04 - API usage (make API calls, verify audit logs)
    05 - Error scenarios (denied, invalid, rate limited)
    06 - Account portal (self-service features)
    07 - Config review (system settings, security)
    08 - Email verification (password reset, invite links via Mailpit)
"""

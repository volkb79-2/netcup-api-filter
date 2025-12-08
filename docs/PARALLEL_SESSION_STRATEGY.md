# Parallel Session Strategy

This document describes the session management architecture used in the Netcup API Filter test framework for handling multiple concurrent browser sessions.

## Overview

The test framework supports parallel browser sessions to enable realistic multi-user and multi-actor testing scenarios. This is essential for testing:
- Admin managing accounts while users interact
- Multiple users accessing the portal simultaneously
- Race condition detection in concurrent operations
- Session isolation verification

## Architecture

### Session Types

| Session Type | Purpose | Isolation |
|--------------|---------|-----------|
| **Admin Session** | Administrative operations, account management | Full (separate browser context) |
| **Account Session** | User-facing portal interactions | Full (separate browser context) |
| **API Client** | Direct API requests without UI | Stateless (no browser context) |
| **Anonymous Session** | Unauthenticated access testing | Minimal (shared for efficiency) |

### Browser Context Model

Each session gets its own Playwright `BrowserContext`, providing:
- Isolated cookies and storage
- Independent authentication state
- Separate viewport and settings
- No cross-session data leakage

```
Browser (Chromium)
├── Admin Context
│   ├── Cookies: admin_session_id=...
│   ├── Page: /admin/dashboard
│   └── State: logged in as admin
├── User1 Context
│   ├── Cookies: account_session_id=...
│   ├── Page: /account/dashboard
│   └── State: logged in as user1
└── User2 Context
    ├── Cookies: account_session_id=...
    ├── Page: /account/realms
    └── State: logged in as user2
```

## Implementation

### ParallelSessionManager Class

```python
from dataclasses import dataclass
from typing import Dict, Optional
from playwright.async_api import Browser, BrowserContext, Page

@dataclass
class SessionHandle:
    """Handle to a parallel browser session."""
    session_id: str
    context: BrowserContext
    page: Page
    role: str  # 'admin', 'account', 'anonymous'
    username: Optional[str] = None


class ParallelSessionManager:
    """Manages multiple parallel browser sessions for testing."""
    
    def __init__(self, browser: Browser):
        self.browser = browser
        self.sessions: Dict[str, SessionHandle] = {}
    
    async def create_session(self, role: str, session_id: Optional[str] = None) -> SessionHandle:
        """Create a new isolated browser session."""
        if session_id is None:
            session_id = f"{role}_{len(self.sessions)}"
        
        context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 720},
            locale='en-US',
        )
        page = await context.new_page()
        
        handle = SessionHandle(
            session_id=session_id,
            context=context,
            page=page,
            role=role,
        )
        self.sessions[session_id] = handle
        return handle
    
    async def get_session(self, session_id: str) -> Optional[SessionHandle]:
        """Get existing session by ID."""
        return self.sessions.get(session_id)
    
    async def close_session(self, session_id: str) -> None:
        """Close and remove a session."""
        if session_id in self.sessions:
            handle = self.sessions.pop(session_id)
            await handle.context.close()
    
    async def close_all(self) -> None:
        """Close all sessions."""
        for session_id in list(self.sessions.keys()):
            await self.close_session(session_id)
    
    async def admin_session(self) -> SessionHandle:
        """Get or create the admin session."""
        if 'admin' not in self.sessions:
            handle = await self.create_session('admin', 'admin')
            # Login as admin
            await self._login_admin(handle)
        return self.sessions['admin']
    
    async def account_session(self, username: str) -> SessionHandle:
        """Get or create a session for a specific account."""
        session_id = f"account_{username}"
        if session_id not in self.sessions:
            handle = await self.create_session('account', session_id)
            handle.username = username
            # Note: Caller must handle login
        return self.sessions[session_id]
    
    async def _login_admin(self, handle: SessionHandle) -> None:
        """Login to admin portal."""
        # Implementation uses ui_tests.workflows.admin_login
        pass
```

### pytest Fixture Integration

```python
@pytest_asyncio.fixture()
async def session_manager(playwright_client):
    """Create parallel session manager for the test."""
    manager = ParallelSessionManager(playwright_client.browser)
    yield manager
    await manager.close_all()


@pytest_asyncio.fixture()
async def admin_session(session_manager):
    """Get the admin session handle."""
    return await session_manager.admin_session()


@pytest_asyncio.fixture()
async def user_session(session_manager):
    """Get a user session handle for testing."""
    return await session_manager.account_session('testuser')
```

## Usage Patterns

### Basic Multi-Session Test

```python
@pytest.mark.asyncio
async def test_admin_approves_user_sees_update(session_manager):
    """Admin approval is immediately visible to user."""
    # Setup: Admin and user sessions
    admin = await session_manager.admin_session()
    user = await session_manager.create_session('account')
    
    # User registers (gets pending status)
    await user.page.goto('/account/register')
    # ... fill registration form ...
    
    # Admin approves the account
    await admin.page.goto('/admin/accounts/pending')
    await admin.page.click('button[data-action="approve"]')
    
    # User refreshes and sees approval
    await user.page.reload()
    assert await user.page.text_content('.status') == 'Active'
```

### Concurrent Operation Test

```python
@pytest.mark.asyncio
async def test_concurrent_token_creation(session_manager):
    """Multiple users creating tokens simultaneously."""
    import asyncio
    
    async def create_token(session_id: str):
        session = await session_manager.create_session('account', session_id)
        await session.page.goto('/account/tokens/new')
        await session.page.fill('#name', f'Token-{session_id}')
        await session.page.click('button[type="submit"]')
        return await session.page.text_content('.token-value')
    
    # Create 3 tokens concurrently
    tokens = await asyncio.gather(
        create_token('user1'),
        create_token('user2'),
        create_token('user3'),
    )
    
    # Verify all tokens are unique
    assert len(set(tokens)) == 3
```

### Session Isolation Verification

```python
@pytest.mark.asyncio
async def test_sessions_are_isolated(session_manager):
    """Verify sessions don't share authentication state."""
    admin = await session_manager.admin_session()
    anon = await session_manager.create_session('anonymous')
    
    # Admin can access dashboard
    await admin.page.goto('/admin/dashboard')
    assert '/admin/dashboard' in admin.page.url
    
    # Anonymous session cannot
    await anon.page.goto('/admin/dashboard')
    assert '/admin/login' in anon.page.url  # Redirected to login
```

## Best Practices

### 1. Session Lifecycle Management

```python
# Good: Use async context manager for cleanup
async with session_manager.temporary_session('account') as session:
    # ... test code ...
# Session automatically closed

# Bad: Creating sessions without cleanup
session = await session_manager.create_session('account')
# ... test crashes ...
# Session leaks!
```

### 2. Avoid Session State Assumptions

```python
# Good: Verify state before actions
async def approve_if_pending(admin_session, username):
    await admin_session.page.goto('/admin/accounts/pending')
    if await admin_session.page.is_visible(f'[data-username="{username}"]'):
        await admin_session.page.click(f'[data-username="{username}"] .approve-btn')

# Bad: Assume state based on previous test
async def approve_account(admin_session, username):
    await admin_session.page.click(f'[data-username="{username}"] .approve-btn')
    # Fails if account not pending!
```

### 3. Limit Concurrent Sessions

```python
# Good: Reasonable concurrency
MAX_PARALLEL_SESSIONS = 5
sessions = [await session_manager.create_session('account', f'user{i}') 
            for i in range(MAX_PARALLEL_SESSIONS)]

# Bad: Excessive parallelism
# Can exhaust browser resources and cause flaky tests
sessions = [await session_manager.create_session('account', f'user{i}') 
            for i in range(100)]
```

### 4. Screenshot on Failure

```python
@pytest.mark.asyncio
async def test_with_diagnostics(session_manager):
    """Test that captures state on failure."""
    admin = await session_manager.admin_session()
    
    try:
        # Test operations...
        await admin.page.click('#nonexistent')
    except Exception as e:
        # Capture diagnostic info
        await admin.page.screenshot(path=f'failure_{admin.session_id}.png')
        raise
```

## Configuration

Environment variables for parallel session behavior:

```bash
# Maximum concurrent browser contexts
PARALLEL_SESSION_MAX=10

# Default viewport size
PARALLEL_SESSION_VIEWPORT_WIDTH=1280
PARALLEL_SESSION_VIEWPORT_HEIGHT=720

# Session timeout (seconds)
PARALLEL_SESSION_TIMEOUT=300

# Enable verbose logging
PARALLEL_SESSION_DEBUG=true
```

## Testing Matrix

Parallel sessions enable comprehensive testing scenarios:

| Scenario | Sessions | Purpose |
|----------|----------|---------|
| Admin + User | 2 | Basic approval flow |
| Admin + 2 Users | 3 | Concurrent user operations |
| Multiple Admins | 2 | Admin coordination |
| User + API Client | 2 | UI/API consistency |
| Race conditions | 5+ | Stress testing |

## Related Documentation

- [TESTING_STRATEGY.md](TESTING_STRATEGY.md) - Overall testing approach
- [UI_TESTING_GUIDE.md](UI_TESTING_GUIDE.md) - UI test patterns
- [PLAYWRIGHT_MCP_SETUP.md](PLAYWRIGHT_MCP_SETUP.md) - Playwright configuration

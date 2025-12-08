"""
Parallel Session Manager for UI Testing.

Manages multiple isolated browser sessions for realistic multi-user
and multi-actor testing scenarios.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TypedDict
import logging

from playwright.async_api import Browser, BrowserContext, Page

logger = logging.getLogger(__name__)


class ViewportSize(TypedDict):
    """Viewport size specification."""
    width: int
    height: int


@dataclass
class SessionHandle:
    """Handle to a parallel browser session."""
    session_id: str
    context: BrowserContext
    page: Page
    role: str  # 'admin', 'account', 'anonymous'
    username: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __repr__(self) -> str:
        return f"SessionHandle(id={self.session_id}, role={self.role}, user={self.username})"


class ParallelSessionManager:
    """
    Manages multiple parallel browser sessions for testing.
    
    Each session gets its own Playwright BrowserContext, providing:
    - Isolated cookies and storage
    - Independent authentication state
    - Separate viewport and settings
    - No cross-session data leakage
    
    Usage:
        async with ParallelSessionManager(browser) as manager:
            admin = await manager.admin_session()
            user = await manager.account_session('testuser')
            
            # Admin and user can interact concurrently
            await admin.page.goto('/admin/dashboard')
            await user.page.goto('/account/dashboard')
    """
    
    DEFAULT_VIEWPORT: ViewportSize = {'width': 1280, 'height': 720}
    DEFAULT_LOCALE = 'en-US'
    
    def __init__(
        self,
        browser: Browser,
        base_url: Optional[str] = None,
        viewport: Optional[ViewportSize] = None,
        locale: str = DEFAULT_LOCALE,
    ):
        """
        Initialize the session manager.
        
        Args:
            browser: Playwright Browser instance
            base_url: Base URL for navigation (optional)
            viewport: Default viewport size (optional)
            locale: Browser locale setting
        """
        self.browser = browser
        self.base_url = base_url
        self.viewport: ViewportSize = viewport or self.DEFAULT_VIEWPORT
        self.locale = locale
        self.sessions: Dict[str, SessionHandle] = {}
        self._counter = 0
    
    async def __aenter__(self) -> 'ParallelSessionManager':
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - cleanup all sessions."""
        await self.close_all()
    
    async def create_session(
        self,
        role: str,
        session_id: Optional[str] = None,
        viewport: Optional[ViewportSize] = None,
    ) -> SessionHandle:
        """
        Create a new isolated browser session.
        
        Args:
            role: Session role ('admin', 'account', 'anonymous')
            session_id: Custom session ID (auto-generated if not provided)
            viewport: Custom viewport size (uses default if not provided)
            
        Returns:
            SessionHandle for the new session
        """
        if session_id is None:
            self._counter += 1
            session_id = f"{role}_{self._counter}"
        
        if session_id in self.sessions:
            raise ValueError(f"Session {session_id} already exists")
        
        vp: ViewportSize = viewport if viewport is not None else self.viewport
        context = await self.browser.new_context(
            viewport=vp,
            locale=self.locale,
            base_url=self.base_url,
        )
        page = await context.new_page()
        
        handle = SessionHandle(
            session_id=session_id,
            context=context,
            page=page,
            role=role,
        )
        self.sessions[session_id] = handle
        
        logger.debug(f"Created session: {handle}")
        return handle
    
    async def get_session(self, session_id: str) -> Optional[SessionHandle]:
        """Get existing session by ID."""
        return self.sessions.get(session_id)
    
    async def close_session(self, session_id: str) -> None:
        """Close and remove a session."""
        if session_id in self.sessions:
            handle = self.sessions.pop(session_id)
            try:
                await handle.context.close()
                logger.debug(f"Closed session: {handle}")
            except Exception as e:
                logger.warning(f"Error closing session {session_id}: {e}")
    
    async def close_all(self) -> None:
        """Close all sessions."""
        for session_id in list(self.sessions.keys()):
            await self.close_session(session_id)
    
    async def admin_session(
        self,
        login: bool = True,
        credentials: Optional[tuple[str, str]] = None,
    ) -> SessionHandle:
        """
        Get or create the admin session.
        
        Args:
            login: Whether to automatically login (default True)
            credentials: Optional (username, password) tuple
            
        Returns:
            SessionHandle for admin session
        """
        if 'admin' not in self.sessions:
            handle = await self.create_session('admin', 'admin')
            handle.username = 'admin'
            
            if login:
                await self._login_admin(handle, credentials)
        
        return self.sessions['admin']
    
    async def account_session(
        self,
        username: str,
        login: bool = False,
        password: Optional[str] = None,
    ) -> SessionHandle:
        """
        Get or create a session for a specific account.
        
        Args:
            username: Account username
            login: Whether to automatically login (default False)
            password: Account password (required if login=True)
            
        Returns:
            SessionHandle for account session
        """
        session_id = f"account_{username}"
        
        if session_id not in self.sessions:
            handle = await self.create_session('account', session_id)
            handle.username = username
            
            if login:
                if password is None:
                    raise ValueError("Password required for login")
                await self._login_account(handle, username, password)
        
        return self.sessions[session_id]
    
    async def anonymous_session(self) -> SessionHandle:
        """
        Get or create an anonymous (unauthenticated) session.
        
        Returns:
            SessionHandle for anonymous session
        """
        if 'anonymous' not in self.sessions:
            handle = await self.create_session('anonymous', 'anonymous')
        
        return self.sessions['anonymous']
    
    async def _login_admin(
        self,
        handle: SessionHandle,
        credentials: Optional[tuple[str, str]] = None,
    ) -> None:
        """
        Login to admin portal.
        
        Args:
            handle: Session handle
            credentials: Optional (username, password) tuple
        """
        from ui_tests.config import settings
        
        username, password = credentials or (settings.admin_username, settings.admin_password)
        
        page = handle.page
        await page.goto(settings.url('/admin/login'))
        await page.fill('#username', username)
        await page.fill('#password', password)
        await page.click('button[type="submit"]')
        
        # Wait for navigation away from login
        await page.wait_for_url('**/admin/**')
        
        # Handle forced password change if required
        if '/admin/change-password' in page.url:
            logger.info(f"Admin {username} requires password change")
            # Caller must handle password change
        
        logger.debug(f"Admin login complete: {username}")
    
    async def _login_account(
        self,
        handle: SessionHandle,
        username: str,
        password: str,
    ) -> None:
        """
        Login to account portal.
        
        Args:
            handle: Session handle
            username: Account username
            password: Account password
        """
        from ui_tests.config import settings
        
        page = handle.page
        await page.goto(settings.url('/account/login'))
        await page.fill('#username', username)
        await page.fill('#password', password)
        await page.click('button[type="submit"]')
        
        # Wait for 2FA page or dashboard
        await page.wait_for_url('**/account/**')
        
        logger.debug(f"Account login complete: {username}")
    
    @property
    def session_count(self) -> int:
        """Get number of active sessions."""
        return len(self.sessions)
    
    def list_sessions(self) -> list[str]:
        """Get list of active session IDs."""
        return list(self.sessions.keys())

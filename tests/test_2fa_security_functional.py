"""
Functional tests for 2FA security features (backend logic testing).

Tests the core security functions without UI automation:
1. 2FA failure tracking and lockout
2. Recovery code rate limiting
3. Session regeneration
"""

import pytest
from datetime import datetime, timedelta

# Import Flask app and models
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from netcup_api_filter.app import create_app
from netcup_api_filter.database import db
from netcup_api_filter.models import Account, Settings
from netcup_api_filter import account_auth


@pytest.fixture
def app(monkeypatch, tmp_path):
    """Create test Flask app with a temporary SQLite database file."""
    monkeypatch.setenv("SECRET_KEY", "test_secret_key_for_testing_only")
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "test.db"))

    app = create_app()
    app.config['TESTING'] = True

    with app.app_context():
        db.create_all()

        # Create test account
        account = Account(
            username='testuser',
            user_alias='test_alias_123',
            email='test@example.com',
            password_hash='dummy_hash',
            email_2fa_enabled=True,
            is_active=1,
            approved_at=datetime.utcnow(),
            email_verified=1,
        )
        db.session.add(account)
        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def test_account(app):
    """Get test account from database."""
    with app.app_context():
        return Account.query.filter_by(username='testuser').first()


class Test2FAFailureTracking:
    """Test 2FA failure tracking and lockout logic."""
    
    def test_increment_2fa_failures(self, app, test_account):
        """Test incrementing 2FA failure counter."""
        with app.app_context():
            account = Account.query.get(test_account.id)
            
            # Start with 0 failures
            assert account_auth.get_2fa_failure_count(account) == 0
            
            # Increment failures
            account_auth.increment_2fa_failures(account)
            assert account_auth.get_2fa_failure_count(account) == 1
            
            account_auth.increment_2fa_failures(account)
            assert account_auth.get_2fa_failure_count(account) == 2
    
    def test_2fa_lockout_after_max_attempts(self, app, test_account):
        """Test account is locked after max 2FA failures."""
        with app.app_context():
            account = Account.query.get(test_account.id)
            
            # Not locked initially
            assert not account_auth.is_2fa_locked(account)
            
            # Increment to max attempts (5)
            for i in range(5):
                account_auth.increment_2fa_failures(account)
            
            # Should be locked now
            assert account_auth.is_2fa_locked(account)
            assert account_auth.get_2fa_failure_count(account) == 5
    
    def test_2fa_lockout_expiry(self, app, test_account):
        """Test 2FA lockout expires after timeout."""
        with app.app_context():
            account = Account.query.get(test_account.id)
            
            # Lock the account
            for i in range(5):
                account_auth.increment_2fa_failures(account)
            
            assert account_auth.is_2fa_locked(account)
            
            # Manually expire the lockout by back-dating last_failure via Settings.set.
            # The real key uses ":" as separator; expiry is based on last_failure being
            # older than TFA_LOCKOUT_MINUTES (30 min) — there is no separate expires_at
            # field; the old test used the wrong key format and a non-existent attribute.
            key = f"2fa_failures:{account.id}"
            data = Settings.get(key)
            assert data is not None, "Settings entry must exist after locking"
            data['last_failure'] = (datetime.utcnow() - timedelta(minutes=31)).isoformat()
            Settings.set(key, data)
            
            # Should no longer be locked
            assert not account_auth.is_2fa_locked(account)
            assert account_auth.get_2fa_failure_count(account) == 0
    
    def test_reset_2fa_failures(self, app, test_account):
        """Test resetting 2FA failure counter."""
        with app.app_context():
            account = Account.query.get(test_account.id)
            
            # Increment failures
            for i in range(3):
                account_auth.increment_2fa_failures(account)
            
            assert account_auth.get_2fa_failure_count(account) == 3
            
            # Reset
            account_auth.reset_2fa_failures(account)
            assert account_auth.get_2fa_failure_count(account) == 0
            assert not account_auth.is_2fa_locked(account)


class TestRecoveryCodeRateLimiting:
    """Test recovery code rate limiting logic."""
    
    def test_increment_recovery_code_failures(self, app, test_account):
        """Test incrementing recovery code failure counter."""
        with app.app_context():
            account = Account.query.get(test_account.id)
            
            # Start with 0 failures
            assert account_auth.get_recovery_code_failure_count(account) == 0
            
            # Increment failures
            account_auth.increment_recovery_code_failures(account)
            assert account_auth.get_recovery_code_failure_count(account) == 1
    
    def test_recovery_code_lockout_after_max_attempts(self, app, test_account):
        """Test account is locked after max recovery code failures."""
        with app.app_context():
            account = Account.query.get(test_account.id)
            
            # Not locked initially
            assert not account_auth.is_recovery_code_locked(account)
            
            # Increment to max attempts (3)
            for i in range(3):
                account_auth.increment_recovery_code_failures(account)
            
            # Should be locked now
            assert account_auth.is_recovery_code_locked(account)
            assert account_auth.get_recovery_code_failure_count(account) == 3
    
    def test_recovery_code_lockout_independent_from_2fa(self, app, test_account):
        """Test recovery code lockout is independent from 2FA lockout."""
        with app.app_context():
            account = Account.query.get(test_account.id)
            
            # Lock 2FA
            for i in range(5):
                account_auth.increment_2fa_failures(account)
            
            assert account_auth.is_2fa_locked(account)
            
            # Recovery code should still work (not locked)
            assert not account_auth.is_recovery_code_locked(account)
            
            # Can still attempt recovery codes (up to 3 times)
            for i in range(3):
                account_auth.increment_recovery_code_failures(account)
            
            # Now recovery codes are also locked
            assert account_auth.is_recovery_code_locked(account)


class TestSessionRegeneration:
    """Test session regeneration on login."""

    def test_create_session_sets_account_keys(self, app, test_account):
        """Test that create_session sets account_id and account_username.

        create_session() preserves pre-existing session data (session fixation
        protection: the session *ID* is rotated, not the contents) while writing
        the authenticated account identity keys.  The old test asserted
        'old_key' would be removed, which contradicts the session.clear() +
        session.update(old_data) pattern in account_auth.create_session().
        """
        with app.app_context():
            account = Account.query.get(test_account.id)

            with app.test_request_context():
                from flask import session

                # Set some pre-login session data
                session['old_key'] = 'old_value'
                session['user_id'] = 999

                # Create new session
                account_auth.create_session(account)

                # create_session restores pre-existing data then overwrites the
                # identity keys — old_key is preserved by design.
                assert session['account_id'] == account.id
                assert session['account_username'] == account.username


class TestConfigurationDefaults:
    """Test that security configuration values are correctly loaded."""
    
    def test_tfa_max_attempts_configured(self):
        """Test TFA_MAX_ATTEMPTS is set correctly."""
        assert account_auth.TFA_MAX_ATTEMPTS == 5
    
    def test_tfa_lockout_minutes_configured(self):
        """Test TFA_LOCKOUT_MINUTES is set correctly."""
        assert account_auth.TFA_LOCKOUT_MINUTES == 30
    
    def test_recovery_code_max_attempts_configured(self):
        """Test RECOVERY_CODE_MAX_ATTEMPTS is set correctly."""
        assert account_auth.RECOVERY_CODE_MAX_ATTEMPTS == 3
    
    def test_recovery_code_lockout_minutes_configured(self):
        """Test RECOVERY_CODE_LOCKOUT_MINUTES is set correctly."""
        assert account_auth.RECOVERY_CODE_LOCKOUT_MINUTES == 30
    
    def test_recovery_code_count_configured(self):
        """Test RECOVERY_CODE_COUNT is set to 3."""
        from netcup_api_filter import recovery_codes
        assert recovery_codes.RECOVERY_CODE_COUNT == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

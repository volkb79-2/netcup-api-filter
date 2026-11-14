from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from ui_tests.tests.journeys import test_journey_master as master


def test_local_j2_invite_guard_uses_persistent_path_after_transient_flag_clears():
    # _accept_admin_invite clears invite_based_account; the path and login result survive it.
    state = SimpleNamespace(
        get_extra=lambda key: {
            "j2_path": "admin_invite",
            "invite_based_account": False,
            "j2_user_login_verified": False,
        }.get(key)
    )

    with pytest.raises(pytest.fail.Exception, match="did not reach and verify J2_07"):
        master._assert_local_j2_invite_login(state, "local")


def test_local_j2_invite_guard_accepts_a_verified_login():
    state = SimpleNamespace(
        get_extra=lambda key: {
            "j2_path": "admin_invite",
            "invite_based_account": False,
            "j2_user_login_verified": True,
        }.get(key)
    )

    master._assert_local_j2_invite_login(state, "local")


@pytest.mark.asyncio
async def test_j2_master_keeps_path_after_invite_acceptance_clears_transient_flag(monkeypatch):
    class FakeJourneyState:
        def __init__(self):
            self.extras = {}

        def set_extra(self, key, value):
            self.extras[key] = value

        def get_extra(self, key, default=None):
            return self.extras.get(key, default)

    state = FakeJourneyState()
    events = []

    class FakeJourney:
        async def test_J2_01_admin_invite_account_created(self, _browser):
            events.append("J2_01")

        async def test_J2_07_user_can_login(self, _browser, _mailpit):
            events.append("J2_07")
            assert state.get_extra("j2_path") == "admin_invite"
            state.set_extra("invite_based_account", False)

        async def test_J2_08_summary(self, _browser):
            events.append("J2_08")

    @asynccontextmanager
    async def fake_browser_session(_persona):
        yield object()

    from ui_tests.tests.journeys import j2_account_lifecycle
    import ui_tests.config as ui_config

    monkeypatch.setattr(master, "journey_state", state)
    monkeypatch.setattr(master, "browser_session", fake_browser_session)
    monkeypatch.setattr(j2_account_lifecycle, "TestJourney2AccountLifecycle", FakeJourney)
    monkeypatch.setattr(ui_config, "settings", SimpleNamespace(deployment_target="local"))

    with pytest.raises(pytest.fail.Exception, match="did not reach and verify J2_07"):
        await master.TestJourneyMaster().test_journey_2_account_lifecycle(object())

    assert events == ["J2_01", "J2_07"]
    assert state.get_extra("j2_path") == "admin_invite"

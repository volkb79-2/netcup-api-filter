from types import SimpleNamespace

import pytest
import ui_tests.config as ui_config

from ui_tests.tests.journeys import j3_comprehensive_states as j3
from ui_tests.tests.journeys.state_matrix import ACCOUNTS, TOKENS


class FakeAccountBrowser:
    current_url = "http://app.test/admin/accounts/41"

    async def goto(self, *_args, **_kwargs):
        return None

    async def wait_for_load_state(self, *_args, **_kwargs):
        return None

    async def wait_for_timeout(self, *_args, **_kwargs):
        return None

    async def fill(self, *_args, **_kwargs):
        return None

    async def click(self, *_args, **_kwargs):
        return None

    async def query_selector(self, selector):
        if selector in {"#createAccountForm", "#email, input[name='email']"}:
            return object()
        return None

    async def text(self, _selector):
        return "Account created. Invitation sent."


def _account_creator(monkeypatch, invite_message):
    class FakeMailpit:
        def wait_for_message(self, **_kwargs):
            return invite_message

    async def no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr(j3, "settings", SimpleNamespace(url=lambda path: f"http://app.test{path}"))
    monkeypatch.setattr(j3, "MailpitClient", FakeMailpit)
    monkeypatch.setattr(j3, "generate_suffix", lambda: "abc123")
    monkeypatch.setattr(j3, "new_password", lambda: "test-password")
    monkeypatch.setattr(j3, "capture", no_op)
    monkeypatch.setattr(j3.AccountCreator, "ensure_admin_logged_in", no_op)
    monkeypatch.setattr(j3.AccountCreator, "_accept_invite", no_op)
    return j3.AccountCreator(FakeAccountBrowser())


@pytest.mark.asyncio
async def test_j3_01_fails_when_account_creator_returns_empty_result(monkeypatch):
    class EmptyAccountCreator:
        def __init__(self, _browser):
            self.created_accounts = {}

        async def create_account(self, _spec):
            return {}

    monkeypatch.setattr(j3, "AccountCreator", EmptyAccountCreator)

    with pytest.raises(pytest.fail.Exception, match="did not fully create account"):
        await j3.TestJourney3ComprehensiveStates().test_J3_01_create_accounts(None)


@pytest.mark.parametrize(
    "invite_message",
    [
        None,
        SimpleNamespace(text="Invitation email with no URL", html="", to=[]),
    ],
    ids=["missing-email", "missing-link"],
)
@pytest.mark.asyncio
async def test_account_creation_fails_when_invite_email_or_link_is_missing(
    monkeypatch, invite_message
):
    creator = _account_creator(monkeypatch, invite_message)

    with pytest.raises(pytest.fail.Exception, match="invite"):
        await creator.create_account(ACCOUNTS[1])


@pytest.mark.asyncio
async def test_rejected_account_fails_when_reject_or_disable_control_is_missing(monkeypatch):
    creator = _account_creator(monkeypatch, None)

    with pytest.raises(pytest.fail.Exception, match="Reject or Disable control"):
        await creator._reject_account(41, "journey-user")


@pytest.mark.asyncio
async def test_account_creation_checks_actual_database_state(monkeypatch):
    invite = SimpleNamespace(
        text="Accept at http://app.test/account/invite/invite-token",
        html="",
        to=[SimpleNamespace(address="user@test.example.com")],
    )
    creator = _account_creator(monkeypatch, invite)
    monkeypatch.setattr(j3.verification, "db_available", lambda: True)
    monkeypatch.setattr(
        j3.verification,
        "get_account",
        lambda _username: {
            "is_active": 0,
            "email_verified": 1,
            "must_change_password": 0,
        },
    )

    with pytest.raises(pytest.fail.Exception, match="differs from the completed invite flow"):
        await creator.create_account(ACCOUNTS[1])


@pytest.mark.parametrize(
    "created_tokens",
    [
        {TOKENS[0].name: {"token_value": "captured"}},
        {
            spec.name: {"token_value": "" if index == 0 else "captured"}
            for index, spec in enumerate(TOKENS)
        },
    ],
    ids=["missing-token", "missing-one-time-value"],
)
@pytest.mark.asyncio
async def test_j3_03_fails_for_missing_token_or_uncaptured_value(monkeypatch, created_tokens):
    class IncompleteTokenCreator:
        def __init__(self, _browser, _realm_creator):
            self.created_tokens = created_tokens

        async def create_token(self, _spec):
            return None

    async def no_op(*_args, **_kwargs):
        return None

    realm_creator = SimpleNamespace(account_creator=SimpleNamespace())
    monkeypatch.setattr(ui_config, "settings", SimpleNamespace(deployment_target="local"))
    monkeypatch.setattr(j3.journey_state, "get_extra", lambda _key: realm_creator)
    monkeypatch.setattr(j3, "TokenCreator", IncompleteTokenCreator)
    monkeypatch.setattr(j3, "capture", no_op)

    with pytest.raises(pytest.fail.Exception, match="J3_03"):
        await j3.TestJourney3ComprehensiveStates().test_J3_03_create_tokens(None)

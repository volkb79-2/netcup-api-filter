"""The local e2e Mailpit fixture must fail loudly when its dependency is down."""
from __future__ import annotations

import pytest

import ui_tests.conftest as ui_conftest
import ui_tests.mailpit_client as mailpit_client


def test_mailpit_fixture_fails_instead_of_skipping_when_unreachable(monkeypatch):
    class UnreachableMailpit:
        def clear(self):
            raise ConnectionError("connection refused")

    monkeypatch.setattr(mailpit_client, "MailpitClient", UnreachableMailpit)
    fixture = ui_conftest.mailpit.__wrapped__()

    with pytest.raises(BaseException) as caught:
        next(fixture)
    assert type(caught.value).__name__ == "Failed"
    assert "MAILPIT_URL" in str(caught.value)

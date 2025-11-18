import types

from client_portal import _normalize_token_info


class DummyClient:
    def __init__(self):
        self.client_id = "dummy"
        self.description = "Dummy client"
        self.realm_type = "host"
        self.realm_value = "example.com"
        self.email_address = "dummy@example.com"
        self.email_notifications_enabled = 1

    def get_allowed_record_types(self):
        return ["A", "AAAA"]

    def get_allowed_operations(self):
        return ["read", "update"]

    def get_allowed_ip_ranges(self):
        return ["127.0.0.1"]


def test_normalize_token_info_converts_object_to_dict():
    token_info = DummyClient()

    normalized = _normalize_token_info(token_info)

    assert normalized["client_id"] == "dummy"
    assert normalized["realm_value"] == "example.com"
    assert normalized["allowed_record_types"] == ["A", "AAAA"]
    assert normalized["allowed_operations"] == ["read", "update"]
    assert normalized["allowed_origins"] == ["127.0.0.1"]
    assert normalized["email_notifications_enabled"] is True

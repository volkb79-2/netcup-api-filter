"""Round-trip tests proving the factory fixtures produce consistent data."""

from netcup_api_filter.models import verify_token_hash, TOKEN_PREFIX, USER_ALIAS_LENGTH


def test_token_round_trip(make_account, make_realm, make_token):
    """Plaintext re-hashes to stored hash; prefix slice matches stored prefix."""
    account = make_account(username="factory-user")
    realm = make_realm(account)
    token_obj, plain = make_token(realm)

    # Format: naf_<16-char alias>_<64-char random> = 85 chars
    assert plain.startswith(f"naf_{account.user_alias}_")
    assert len(plain) == 85

    assert verify_token_hash(plain, token_obj.token_hash)

    # Prefix is first 8 chars of the random suffix — use split to derive it
    # independently of the factory's slice constant.
    assert token_obj.token_prefix == plain.split("_", 2)[2][:8]


def test_make_account_defaults(make_account):
    account = make_account(username="accountx1")
    assert account.id is not None
    assert account.is_active == 1
    assert account.is_admin == 0
    assert account.email_verified == 1
    assert account.approved_at is not None
    assert len(account.user_alias) == USER_ALIAS_LENGTH


def test_make_realm_defaults(make_account, make_realm):
    account = make_account(username="realmuser1")
    realm = make_realm(account)
    assert realm.id is not None
    assert realm.status == "approved"
    assert "A" in realm.get_allowed_record_types()
    assert "read" in realm.get_allowed_operations()


def test_make_token_explicit_scope(make_account, make_realm, make_token):
    account = make_account(username="scopeuser1")
    realm = make_realm(account)
    token_obj, _ = make_token(realm, operations=("read",), record_types=("A",))
    assert token_obj.get_allowed_operations() == ["read"]
    assert token_obj.get_allowed_record_types() == ["A"]


def test_make_token_no_scope_inherits_realm(make_account, make_realm, make_token):
    """No token-level scope → get_allowed_* returns None (falls back to realm)."""
    account = make_account(username="inherituser1")
    realm = make_realm(account)
    token_obj, _ = make_token(realm)
    assert token_obj.get_allowed_operations() is None
    assert token_obj.get_allowed_record_types() is None

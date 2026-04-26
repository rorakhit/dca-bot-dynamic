from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def test_set_and_get_access_token(temp_plaid_store):
    import plaid_store
    plaid_store.set_access_token("access-sandbox-abc123")
    assert plaid_store.get_access_token() == "access-sandbox-abc123"


def test_get_access_token_returns_none_when_unset(temp_plaid_store):
    import plaid_store
    assert plaid_store.get_access_token() is None


def test_cursor_roundtrip(temp_plaid_store):
    import plaid_store
    assert plaid_store.get_cursor() is None
    plaid_store.set_cursor("cursor-xyz")
    assert plaid_store.get_cursor() == "cursor-xyz"


def test_paycheck_deduplication(temp_plaid_store):
    import plaid_store
    assert not plaid_store.is_paycheck_processed("txn_abc")
    plaid_store.mark_paycheck_processed("txn_abc")
    assert plaid_store.is_paycheck_processed("txn_abc")
    assert not plaid_store.is_paycheck_processed("txn_xyz")


def test_create_and_consume_action_token(temp_plaid_store):
    import plaid_store
    token = plaid_store.create_action_token("cancel", {"foo": "bar"}, ttl_seconds=300)
    entry = plaid_store.consume_action_token(token)
    assert entry["type"] == "cancel"
    assert entry["metadata"] == {"foo": "bar"}
    assert plaid_store.consume_action_token(token) is None


def test_get_action_token_nondestructive(temp_plaid_store):
    import plaid_store
    token = plaid_store.create_action_token("retry", {}, ttl_seconds=300)
    assert plaid_store.get_action_token(token) is not None
    assert plaid_store.get_action_token(token) is not None


def test_expired_token_returns_none(temp_plaid_store):
    import plaid_store
    token = plaid_store.create_action_token("skip", {}, ttl_seconds=300)
    data = plaid_store._load()
    data["action_tokens"][token]["expires_at"] = (
        datetime.now(ET) - timedelta(seconds=1)
    ).isoformat()
    plaid_store._save(data)
    assert plaid_store.consume_action_token(token) is None


def test_expire_action_tokens(temp_plaid_store):
    import plaid_store
    good = plaid_store.create_action_token("cancel", {}, ttl_seconds=300)
    bad = plaid_store.create_action_token("retry", {}, ttl_seconds=300)
    data = plaid_store._load()
    data["action_tokens"][bad]["expires_at"] = (
        datetime.now(ET) - timedelta(seconds=1)
    ).isoformat()
    plaid_store._save(data)
    plaid_store.expire_action_tokens()
    assert plaid_store.get_action_token(good) is not None
    assert plaid_store.get_action_token(bad) is None

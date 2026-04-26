# tests/conftest.py
import pytest


@pytest.fixture
def temp_plaid_store(tmp_path, monkeypatch):
    """Point plaid_store at a temp file so tests never touch the real store."""
    store_path = tmp_path / "plaid_store.json"
    import config
    monkeypatch.setattr(config, "PLAID_STORE_PATH", store_path)
    import plaid_store
    monkeypatch.setattr(plaid_store, "PLAID_STORE_PATH", store_path)
    return store_path

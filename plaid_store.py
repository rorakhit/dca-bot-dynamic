"""
plaid_store.py — Persistent JSON store for Plaid state.

Stores: Plaid access token, sync cursor, processed paycheck IDs, action tokens.
Same load/save pattern as approval.py / pending_approvals.json.
"""

import json
import secrets
from datetime import datetime, timedelta

from config import ET, PLAID_STORE_PATH, log

_DEFAULT: dict = {
    "access_token": None,
    "cursor": None,
    "processed_ids": [],
    "action_tokens": {},
}


def _load() -> dict:
    if not PLAID_STORE_PATH.exists():
        return dict(_DEFAULT)
    try:
        data = json.loads(PLAID_STORE_PATH.read_text())
        return {**_DEFAULT, **data}
    except (json.JSONDecodeError, OSError):
        log.warning("Could not read plaid_store.json — starting fresh")
        return dict(_DEFAULT)


def _save(data: dict):
    tmp = PLAID_STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(PLAID_STORE_PATH)


# ─────────────────────────────────────────────
# ACCESS TOKEN
# ─────────────────────────────────────────────

def set_access_token(token: str):
    data = _load()
    data["access_token"] = token
    _save(data)
    log.info("Plaid access token stored in plaid_store.json")


def get_access_token() -> str | None:
    return _load().get("access_token")


# ─────────────────────────────────────────────
# SYNC CURSOR
# ─────────────────────────────────────────────

def get_cursor() -> str | None:
    return _load().get("cursor")


def set_cursor(cursor: str):
    data = _load()
    data["cursor"] = cursor
    _save(data)


# ─────────────────────────────────────────────
# PROCESSED PAYCHECK IDS
# ─────────────────────────────────────────────

def is_paycheck_processed(transaction_id: str) -> bool:
    return transaction_id in _load().get("processed_ids", [])


def mark_paycheck_processed(transaction_id: str):
    data = _load()
    ids = data.get("processed_ids", [])
    if transaction_id not in ids:
        ids.append(transaction_id)
    data["processed_ids"] = ids[-100:]  # keep last 100, discard oldest
    _save(data)


# ─────────────────────────────────────────────
# ACTION TOKENS (cancel / retry / skip / force)
# ─────────────────────────────────────────────

def create_action_token(token_type: str, metadata: dict, ttl_seconds: int) -> str:
    """Create a single-use action token. Returns the token string."""
    token = secrets.token_urlsafe(32)
    data = _load()
    expires_at = (datetime.now(ET) + timedelta(seconds=ttl_seconds)).isoformat()
    data["action_tokens"][token] = {
        "type": token_type,
        "expires_at": expires_at,
        "metadata": metadata,
    }
    _save(data)
    return token


def get_action_token(token: str) -> dict | None:
    """Non-destructive check. Returns entry dict if valid and unexpired; None otherwise."""
    entry = _load().get("action_tokens", {}).get(token)
    if not entry:
        return None
    if datetime.now(ET) > datetime.fromisoformat(entry["expires_at"]):
        return None
    return entry


def consume_action_token(token: str) -> dict | None:
    """Remove and return the token entry if valid and unexpired; None otherwise."""
    data = _load()
    entry = data.get("action_tokens", {}).pop(token, None)
    if not entry:
        return None
    _save(data)
    if datetime.now(ET) > datetime.fromisoformat(entry["expires_at"]):
        return None
    return entry


def expire_action_tokens():
    """Remove all expired action tokens. Called by daily scheduler job."""
    data = _load()
    now = datetime.now(ET)
    before = len(data.get("action_tokens", {}))
    data["action_tokens"] = {
        t: v
        for t, v in data.get("action_tokens", {}).items()
        if now <= datetime.fromisoformat(v["expires_at"])
    }
    after = len(data["action_tokens"])
    _save(data)
    if before > after:
        log.info(f"Expired {before - after} Plaid action token(s)")

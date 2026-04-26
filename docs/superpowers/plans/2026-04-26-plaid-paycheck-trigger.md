# Plaid Paycheck-Triggered DCA Contributions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed 1st/16th DCA schedule with a Plaid-webhook-driven pipeline that detects a paycheck deposit, pulls $100 into Alpaca via ACH, and fires the existing DCA contribution cycle automatically.

**Architecture:** Plaid sends a `TRANSACTIONS` webhook when new transactions appear. The bot verifies the webhook JWT, syncs new transactions, and detects the paycheck by employer name + minimum amount. A FastAPI background task runs the pipeline: send cancel email → wait 5-min grace period → ACH pull → poll Alpaca for buying power → call `scheduled_contribution()` → approval email sent → user clicks Approve → orders execute. Action URLs (cancel, retry, skip, force) use single-use tokens following the existing `approve/deny` pattern.

**Tech Stack:** Python, FastAPI, APScheduler, `plaid-python`, `httpx`, `python-jose[cryptography]`, `alpaca-py`, Resend, Anthropic SDK

---

## File Map

**New files:**
- `plaid_store.py` — JSON-backed persistent store (access token, sync cursor, processed paycheck IDs, action tokens)
- `plaid_client.py` — Plaid SDK wrapper (link token, token exchange, transaction sync, webhook JWT verification, paycheck detection)
- `plaid_routes.py` — FastAPI router: all `/plaid/*` endpoints, email HTML, pipeline orchestration
- `tests/conftest.py` — pytest fixtures (temp paths, monkeypatching)
- `tests/test_plaid_store.py` — store unit tests
- `tests/test_paycheck_detection.py` — paycheck detection unit tests

**Modified files:**
- `requirements.txt` — add `plaid-python`, `httpx`, `python-jose[cryptography]`, `pytest`
- `config.py` — add Plaid env vars + 5 new constants + `PLAID_STORE_PATH`
- `broker.py` — add `get_ach_relationship_id()`, `initiate_ach_transfer()`, `poll_for_buying_power()`
- `scheduler_jobs.py` — add `expire_plaid_tokens()`, remove `contribution_reminder`
- `app.py` — mount `plaid_routes` router, remove 2 cron jobs, reschedule `expire_pending` to daily, add `expire_plaid_tokens` cron
- `routes.py` — fix `health()` to handle missing `scheduled_contribution` job

---

## Task 1: Add Dependencies and Pytest Setup

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Add dependencies to requirements.txt**

Replace the contents of `requirements.txt` with:

```
alpaca-py
anthropic
pytz
apscheduler
fastapi
matplotlib
numpy
resend
uvicorn
python-dotenv
plaid-python
httpx
python-jose[cryptography]
pytest
pytest-asyncio
```

- [ ] **Step 2: Create tests package**

```bash
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 3: Create tests/conftest.py**

```python
# tests/conftest.py
import pytest


@pytest.fixture
def temp_plaid_store(tmp_path, monkeypatch):
    """Point plaid_store at a temp file so tests never touch the real store."""
    store_path = tmp_path / "plaid_store.json"
    import config
    monkeypatch.setattr(config, "PLAID_STORE_PATH", store_path)
    # Re-import plaid_store so it picks up the patched path
    import importlib
    import plaid_store
    monkeypatch.setattr(plaid_store, "PLAID_STORE_PATH", store_path)
    return store_path
```

- [ ] **Step 4: Verify pytest runs (nothing to test yet)**

```bash
pytest tests/ -v
```

Expected: `no tests ran` (exit 0 or 5 — both fine)

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tests/
git commit -m "chore: add plaid-python, httpx, python-jose, pytest dependencies"
```

---

## Task 2: Config Additions

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Add Plaid env vars and constants**

In `config.py`, after the existing `resend.api_key = ...` line, add:

```python
# Plaid credentials (required)
PLAID_CLIENT_ID = os.environ["PLAID_CLIENT_ID"]
PLAID_SECRET = os.environ["PLAID_SECRET"]
PLAID_MANUAL_TRIGGER_TOKEN = os.environ["PLAID_MANUAL_TRIGGER_TOKEN"]

# Plaid runtime config (optional — sensible defaults)
PLAID_ENV = os.environ.get("PLAID_ENV", "production")
PAYCHECK_EMPLOYER_KEYWORD = os.environ.get("PAYCHECK_EMPLOYER_KEYWORD", "DATALIGN ADVISOR")
PAYCHECK_MIN_AMOUNT = float(os.environ.get("PAYCHECK_MIN_AMOUNT", "575.00"))
ACH_POLL_INTERVAL_SECONDS = int(os.environ.get("ACH_POLL_INTERVAL_SECONDS", "30"))
ACH_POLL_MAX_MINUTES = int(os.environ.get("ACH_POLL_MAX_MINUTES", "10"))
PAYCHECK_CANCEL_GRACE_SECONDS = int(os.environ.get("PAYCHECK_CANCEL_GRACE_SECONDS", "300"))
```

- [ ] **Step 2: Add PLAID_STORE_PATH**

In `config.py`, after the existing `PENDING_STORE_PATH = BASE_DIR / "pending_approvals.json"` line, add:

```python
PLAID_STORE_PATH = BASE_DIR / "plaid_store.json"
```

- [ ] **Step 3: Verify the app still boots**

```bash
# Set dummy env vars so config doesn't raise KeyError
PLAID_CLIENT_ID=x PLAID_SECRET=x PLAID_MANUAL_TRIGGER_TOKEN=x python -c "import config; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add config.py
git commit -m "feat: add Plaid config constants and PLAID_STORE_PATH"
```

---

## Task 3: plaid_store.py — Persistent Store

**Files:**
- Create: `plaid_store.py`
- Create: `tests/test_plaid_store.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_plaid_store.py
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

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
    # Already consumed — second call returns None
    assert plaid_store.consume_action_token(token) is None


def test_get_action_token_nondestructive(temp_plaid_store):
    import plaid_store
    token = plaid_store.create_action_token("retry", {}, ttl_seconds=300)
    assert plaid_store.get_action_token(token) is not None
    assert plaid_store.get_action_token(token) is not None  # still there


def test_expired_token_returns_none(temp_plaid_store):
    import plaid_store
    token = plaid_store.create_action_token("skip", {}, ttl_seconds=300)
    # Manually backdoor the expiry
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
    # Expire the bad one
    data = plaid_store._load()
    data["action_tokens"][bad]["expires_at"] = (
        datetime.now(ET) - timedelta(seconds=1)
    ).isoformat()
    plaid_store._save(data)
    plaid_store.expire_action_tokens()
    assert plaid_store.get_action_token(good) is not None
    assert plaid_store.get_action_token(bad) is None
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
PLAID_CLIENT_ID=x PLAID_SECRET=x PLAID_MANUAL_TRIGGER_TOKEN=x pytest tests/test_plaid_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'plaid_store'`

- [ ] **Step 3: Create plaid_store.py**

```python
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
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
PLAID_CLIENT_ID=x PLAID_SECRET=x PLAID_MANUAL_TRIGGER_TOKEN=x pytest tests/test_plaid_store.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add plaid_store.py tests/test_plaid_store.py tests/conftest.py tests/__init__.py
git commit -m "feat: add plaid_store — persistent store for Plaid state and action tokens"
```

---

## Task 4: plaid_client.py — Plaid SDK Wrapper + Paycheck Detection

**Files:**
- Create: `plaid_client.py`
- Create: `tests/test_paycheck_detection.py`

- [ ] **Step 1: Write failing paycheck detection tests**

```python
# tests/test_paycheck_detection.py
import pytest


# These tests import only is_paycheck — a pure function with no Plaid API calls.
# We monkeypatch the config constants used inside plaid_client.

@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    import config
    monkeypatch.setattr(config, "PAYCHECK_EMPLOYER_KEYWORD", "DATALIGN ADVISOR")
    monkeypatch.setattr(config, "PAYCHECK_MIN_AMOUNT", 575.00)


def test_detects_paycheck():
    from plaid_client import is_paycheck
    txn = {"transaction_id": "t1", "amount": -1575.00, "name": "DATALIGN ADVISOR PAYROLL"}
    assert is_paycheck(txn) is True


def test_rejects_amount_too_small():
    from plaid_client import is_paycheck
    txn = {"transaction_id": "t2", "amount": -100.00, "name": "DATALIGN ADVISOR PAYROLL"}
    assert is_paycheck(txn) is False


def test_rejects_debit_transaction():
    from plaid_client import is_paycheck
    # Positive amount = debit (money leaving account)
    txn = {"transaction_id": "t3", "amount": 1575.00, "name": "DATALIGN ADVISOR PAYROLL"}
    assert is_paycheck(txn) is False


def test_rejects_wrong_employer():
    from plaid_client import is_paycheck
    txn = {"transaction_id": "t4", "amount": -2000.00, "name": "SOME OTHER COMPANY PAYROLL"}
    assert is_paycheck(txn) is False


def test_case_insensitive_match():
    from plaid_client import is_paycheck
    txn = {"transaction_id": "t5", "amount": -900.00, "name": "datalign advisor direct dep"}
    assert is_paycheck(txn) is True


def test_exact_minimum_amount_qualifies():
    from plaid_client import is_paycheck
    txn = {"transaction_id": "t6", "amount": -575.00, "name": "DATALIGN ADVISOR PAYROLL"}
    assert is_paycheck(txn) is True


def test_just_below_minimum_rejected():
    from plaid_client import is_paycheck
    txn = {"transaction_id": "t7", "amount": -574.99, "name": "DATALIGN ADVISOR PAYROLL"}
    assert is_paycheck(txn) is False
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
PLAID_CLIENT_ID=x PLAID_SECRET=x PLAID_MANUAL_TRIGGER_TOKEN=x pytest tests/test_paycheck_detection.py -v
```

Expected: `ModuleNotFoundError: No module named 'plaid_client'`

- [ ] **Step 3: Install new dependencies**

```bash
pip install plaid-python httpx "python-jose[cryptography]" pytest pytest-asyncio
```

- [ ] **Step 4: Create plaid_client.py**

```python
"""
plaid_client.py — Plaid API wrapper for DCA Dynamic bot.

Handles: link token creation, public→access token exchange,
         transaction sync, webhook JWT verification, paycheck detection.
"""

import hashlib

import plaid
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.webhook_verification_key_get_request import WebhookVerificationKeyGetRequest
from jose import jwt, JWTError

from config import (
    PAYCHECK_EMPLOYER_KEYWORD,
    PAYCHECK_MIN_AMOUNT,
    PLAID_CLIENT_ID,
    PLAID_ENV,
    PLAID_SECRET,
    SERVER_BASE_URL,
    log,
)

# ─────────────────────────────────────────────
# CLIENT SETUP
# ─────────────────────────────────────────────

_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "development": plaid.Environment.Development,
    "production": plaid.Environment.Production,
}

_configuration = plaid.Configuration(
    host=_ENV_MAP.get(PLAID_ENV, plaid.Environment.Production),
    api_key={
        "clientId": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
    },
)
_api_client = plaid.ApiClient(_configuration)
plaid_client = plaid_api.PlaidApi(_api_client)


# ─────────────────────────────────────────────
# LINK FLOW
# ─────────────────────────────────────────────

def create_link_token() -> str:
    """Create a Plaid link_token to initialise the Link UI widget."""
    request = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="DCA Dynamic Bot",
        country_codes=[CountryCode("US")],
        language="en",
        webhook=f"{SERVER_BASE_URL}/plaid/webhook",
        user=LinkTokenCreateRequestUser(client_user_id="ro"),
    )
    response = plaid_client.link_token_create(request)
    return response["link_token"]


def exchange_public_token(public_token: str) -> str:
    """Exchange a one-time public_token (from Link widget) for a permanent access_token."""
    request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = plaid_client.item_public_token_exchange(request)
    return response["access_token"]


# ─────────────────────────────────────────────
# TRANSACTION SYNC
# ─────────────────────────────────────────────

def sync_transactions(access_token: str, cursor: str | None) -> tuple[list[dict], str]:
    """
    Fetch new/modified transactions since cursor using Plaid's incremental sync API.
    Returns (added_transactions, next_cursor).

    Plaid amount sign convention:
      Positive = debit (money leaving account, e.g. purchase)
      Negative = credit (money entering account, e.g. paycheck deposit)
    """
    request = TransactionsSyncRequest(
        access_token=access_token,
        cursor=cursor or "",
    )
    response = plaid_client.transactions_sync(request)
    added = [t.to_dict() for t in response["added"]]
    return added, response["next_cursor"]


# ─────────────────────────────────────────────
# PAYCHECK DETECTION
# ─────────────────────────────────────────────

def is_paycheck(transaction: dict) -> bool:
    """
    Returns True if the Plaid transaction looks like the user's paycheck.

    Requires all three:
    - amount is negative (credit — money entering the account)
    - abs(amount) >= PAYCHECK_MIN_AMOUNT (575.00)
    - transaction name contains PAYCHECK_EMPLOYER_KEYWORD (case-insensitive)
    """
    amount = transaction.get("amount", 0)
    name = transaction.get("name", "")
    return (
        amount < 0
        and abs(amount) >= PAYCHECK_MIN_AMOUNT
        and PAYCHECK_EMPLOYER_KEYWORD.lower() in name.lower()
    )


# ─────────────────────────────────────────────
# WEBHOOK VERIFICATION
# ─────────────────────────────────────────────

def verify_webhook(plaid_verification_header: str, raw_body: bytes) -> bool:
    """
    Verify the Plaid-Verification JWT against the raw request body.

    Steps:
    1. Decode JWT header (unverified) to get the key ID (kid)
    2. Fetch the verification key from Plaid's API using that kid
    3. Verify the JWT signature using ES256
    4. Compare the JWT's request_body_sha256 claim with SHA256(raw_body)

    Returns True only if all checks pass. Logs a warning and returns False on any failure.
    """
    if not plaid_verification_header:
        log.warning("Plaid webhook missing Plaid-Verification header")
        return False
    try:
        header = jwt.get_unverified_header(plaid_verification_header)
        kid = header.get("kid")
        if not kid:
            log.warning("Plaid webhook JWT missing kid")
            return False

        key_request = WebhookVerificationKeyGetRequest(key_id=kid)
        key_response = plaid_client.webhook_verification_key_get(key_request)
        key_data = key_response["key"].to_dict()

        claims = jwt.decode(
            plaid_verification_header,
            key_data,
            algorithms=["ES256"],
        )

        body_hash = hashlib.sha256(raw_body).hexdigest()
        return claims.get("request_body_sha256") == body_hash

    except JWTError as exc:
        log.warning(f"Plaid webhook JWT verification failed: {exc}")
        return False
    except Exception as exc:
        log.warning(f"Plaid webhook verification error: {exc}")
        return False
```

- [ ] **Step 5: Run paycheck detection tests — confirm they pass**

```bash
PLAID_CLIENT_ID=x PLAID_SECRET=x PLAID_MANUAL_TRIGGER_TOKEN=x pytest tests/test_paycheck_detection.py -v
```

Expected: all 7 tests PASS

- [ ] **Step 6: Commit**

```bash
git add plaid_client.py tests/test_paycheck_detection.py
git commit -m "feat: add plaid_client — Plaid wrapper, paycheck detection, webhook verification"
```

---

## Task 5: ACH Functions in broker.py

**Files:**
- Modify: `broker.py`

These functions are added at the bottom of `broker.py`, after the existing `execute_allocations` function. They use `httpx` for direct REST calls to Alpaca's ACH endpoints (alpaca-py's TradingClient does not expose ACH relationship or transfer endpoints).

- [ ] **Step 1: Add imports at the top of broker.py**

In `broker.py`, add to the existing imports block:

```python
import asyncio

import httpx
```

Also add `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` to the existing import from `config` if not already present. Check: the existing import block has:
```python
from config import (
    ALPACA_API_KEY,
    ALPACA_SECRET_KEY,
    ...
)
```
Both are already imported — no change needed.

- [ ] **Step 2: Add ACH functions at the bottom of broker.py**

```python
# ─────────────────────────────────────────────
# ACH TRANSFERS (direct REST — alpaca-py has no ACH wrappers)
# ─────────────────────────────────────────────

_ALPACA_BASE = "https://api.alpaca.markets"
_ALPACA_HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
}


def get_ach_relationship_id() -> str:
    """Return the ID of the first APPROVED ACH relationship on the live Alpaca account."""
    with httpx.Client() as client:
        resp = client.get(
            f"{_ALPACA_BASE}/v2/account/ach/relationships",
            headers=_ALPACA_HEADERS,
        )
    resp.raise_for_status()
    approved = [r for r in resp.json() if r.get("status") == "APPROVED"]
    if not approved:
        raise RuntimeError("No approved ACH relationships on Alpaca account")
    return approved[0]["id"]


def initiate_ach_transfer(relationship_id: str, amount: float) -> dict:
    """
    Pull `amount` USD from the linked bank into the live Alpaca account via ACH.
    Returns the transfer response dict from Alpaca.
    """
    with httpx.Client() as client:
        resp = client.post(
            f"{_ALPACA_BASE}/v2/account/ach/transfers",
            headers=_ALPACA_HEADERS,
            json={
                "transfer_type": "ach",
                "relationship_id": relationship_id,
                "amount": f"{amount:.2f}",
                "direction": "INCOMING",
            },
        )
    resp.raise_for_status()
    return resp.json()


async def poll_for_buying_power(
    required_amount: float,
    interval_seconds: int,
    max_minutes: int,
) -> bool:
    """
    Poll Alpaca account cash every `interval_seconds` until it increases by at least
    `required_amount` (1-cent tolerance). Returns True if available; False if timed out.

    Alpaca offers instant buying power up to $1,000 for linked accounts, so $100
    typically clears within seconds. Max wait: max_minutes * 60 seconds.
    """
    baseline = float(broker.get_account().cash)
    max_polls = (max_minutes * 60) // interval_seconds

    for _ in range(max_polls):
        await asyncio.sleep(interval_seconds)
        current_cash = float(broker.get_account().cash)
        if current_cash >= baseline + required_amount - 0.01:
            log.info(f"ACH buying power confirmed: ${current_cash:.2f} (baseline ${baseline:.2f})")
            return True

    log.warning(f"ACH poll timed out after {max_minutes} minutes (baseline ${baseline:.2f})")
    return False
```

- [ ] **Step 3: Verify broker.py imports cleanly**

```bash
PLAID_CLIENT_ID=x PLAID_SECRET=x PLAID_MANUAL_TRIGGER_TOKEN=x \
  ALPACA_API_KEY=x ALPACA_SECRET_KEY=x ANTHROPIC_API_KEY=x \
  NOTIFY_EMAIL=x RESEND_API_KEY=x \
  python -c "import broker; print('ok')"
```

Expected: `ok` (plus the existing `⚠️ LIVE TRADING MODE` warning)

- [ ] **Step 4: Commit**

```bash
git add broker.py
git commit -m "feat: add ACH transfer and buying-power polling to broker.py"
```

---

## Task 6: plaid_routes.py — Routes, Emails, and Pipeline

**Files:**
- Create: `plaid_routes.py`

This is the largest file. It contains all `/plaid/*` FastAPI routes, the three Plaid-specific email functions, and the async pipeline that runs in a background task.

- [ ] **Step 1: Create plaid_routes.py**

```python
"""
plaid_routes.py — Plaid webhook, Link setup, and paycheck pipeline routes.

Routes:
  GET  /plaid/link           — one-time Plaid Link setup page
  POST /plaid/callback       — receives public_token, stores access_token
  POST /plaid/webhook        — Plaid TRANSACTIONS webhook (main entry point)
  GET  /plaid/cancel/{token} — cancel paycheck cycle before ACH initiates
  GET  /plaid/retry/{token}  — retry after ACH buying-power timeout
  GET  /plaid/skip/{token}   — skip failed cycle (audit logged)
  GET  /plaid/force/{token}  — cancel stale approval and run fresh cycle
  GET  /plaid/trigger        — manual trigger (requires static secret token)
"""

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from approval import _save_pending, create_pending_approval, pending_approvals
from audit import write_audit_entry
from broker import (
    CONTRIBUTION_AMOUNT,
    get_ach_relationship_id,
    initiate_ach_transfer,
    poll_for_buying_power,
)
from config import (
    ACH_POLL_INTERVAL_SECONDS,
    ACH_POLL_MAX_MINUTES,
    CONTRIBUTION_AMOUNT,
    PAYCHECK_CANCEL_GRACE_SECONDS,
    PLAID_MANUAL_TRIGGER_TOKEN,
    SERVER_BASE_URL,
    log,
)
from email_service import _send_email, send_error_email
from plaid_client import (
    create_link_token,
    exchange_public_token,
    is_paycheck,
    sync_transactions,
    verify_webhook,
)
from plaid_store import (
    consume_action_token,
    create_action_token,
    get_access_token,
    get_action_token,
    get_cursor,
    is_paycheck_processed,
    mark_paycheck_processed,
    set_access_token,
    set_cursor,
)
from scheduler_jobs import scheduled_contribution

router = APIRouter(prefix="/plaid")


# ─────────────────────────────────────────────
# SHARED RESULT PAGE (same pattern as approval.py)
# ─────────────────────────────────────────────

def _result_page(title: str, body: str, color: str) -> str:
    icon = title.split()[0]
    heading = " ".join(title.split()[1:])
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="font-family:-apple-system,sans-serif;background:#f3f4f6;
             display:flex;align-items:center;justify-content:center;
             min-height:100vh;margin:0">
  <div style="background:white;border-radius:16px;padding:40px;
              max-width:400px;text-align:center;box-shadow:0 4px 12px rgba(0,0,0,0.1)">
    <div style="font-size:40px;margin-bottom:16px">{icon}</div>
    <h2 style="margin:0 0 12px;color:{color}">{heading}</h2>
    <div style="font-size:14px;color:#6b7280;line-height:1.6">{body}</div>
  </div>
</body></html>"""


# ─────────────────────────────────────────────
# PLAID EMAIL FUNCTIONS
# ─────────────────────────────────────────────

def _send_paycheck_detected_email(cancel_token: str, paycheck_amount: float):
    cancel_url = f"{SERVER_BASE_URL}/plaid/cancel/{cancel_token}"
    html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,sans-serif;padding:24px;color:#111827">
  <div style="max-width:520px;background:#ecfdf5;border:1px solid #6ee7b7;
              border-radius:12px;padding:24px">
    <h2 style="color:#059669;margin:0 0 12px">💰 Paycheck Detected — DCA Cycle Starting</h2>
    <p style="margin:0 0 8px">
      A deposit of <strong>${abs(paycheck_amount):.2f}</strong> from your employer was detected.
      We're pulling <strong>${CONTRIBUTION_AMOUNT:.0f}</strong> into your Alpaca account and
      will propose a DCA allocation shortly.
    </p>
    <p style="margin:8px 0">
      You have <strong>5 minutes</strong> to cancel before the transfer initiates.
    </p>
    <a href="{cancel_url}"
       style="display:inline-block;margin-top:12px;padding:12px 24px;
              background:#ef4444;color:white;border-radius:8px;font-weight:600;
              text-decoration:none">
      🚫 Cancel this cycle
    </a>
    <p style="font-size:12px;color:#6b7280;margin:16px 0 0">
      If you don't cancel, the ${CONTRIBUTION_AMOUNT:.0f} transfer will initiate automatically.
    </p>
  </div>
</body></html>"""
    _send_email("💰 Paycheck Detected — DCA Cycle Starting", html)
    log.info(f"Paycheck detected email sent — cancel token {cancel_token[:8]}…")


def _send_ach_timeout_email(retry_token: str, skip_token: str):
    retry_url = f"{SERVER_BASE_URL}/plaid/retry/{retry_token}"
    skip_url = f"{SERVER_BASE_URL}/plaid/skip/{skip_token}"
    html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,sans-serif;padding:24px;color:#111827">
  <div style="max-width:520px;background:#fff7ed;border:1px solid #fed7aa;
              border-radius:12px;padding:24px">
    <h2 style="color:#ea580c;margin:0 0 12px">⏳ ACH Transfer Timeout</h2>
    <p style="margin:0 0 8px">
      The ${CONTRIBUTION_AMOUNT:.0f} ACH transfer to Alpaca was initiated but buying power
      didn't appear within {ACH_POLL_MAX_MINUTES} minutes. The DCA cycle was not run.
    </p>
    <div style="display:flex;gap:12px;margin-top:16px">
      <a href="{retry_url}"
         style="flex:1;display:block;text-align:center;padding:12px;
                background:#3b82f6;color:white;border-radius:8px;
                font-weight:600;text-decoration:none">
        🔄 Retry
      </a>
      <a href="{skip_url}"
         style="flex:1;display:block;text-align:center;padding:12px;
                background:#f3f4f6;color:#374151;border-radius:8px;
                font-weight:600;text-decoration:none;border:1px solid #e5e7eb">
        ✗ Skip this cycle
      </a>
    </div>
  </div>
</body></html>"""
    _send_email("⏳ DCA Dynamic — ACH Transfer Timeout", html)
    log.info("ACH timeout email sent")


def _send_pending_conflict_email(force_token: str):
    force_url = f"{SERVER_BASE_URL}/plaid/force/{force_token}"
    html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,sans-serif;padding:24px;color:#111827">
  <div style="max-width:520px;background:#fef3c7;border:1px solid #fcd34d;
              border-radius:12px;padding:24px">
    <h2 style="color:#d97706;margin:0 0 12px">⚠️ Paycheck Detected — Approval Pending</h2>
    <p style="margin:0 0 8px">
      A new paycheck was detected, but a previous DCA approval is still pending.
      The ACH transfer was skipped to avoid a double cycle.
    </p>
    <p style="margin:8px 0">Cancel the old approval and run a fresh cycle now:</p>
    <a href="{force_url}"
       style="display:inline-block;margin-top:12px;padding:12px 24px;
              background:#f97316;color:white;border-radius:8px;font-weight:600;
              text-decoration:none">
      🔄 Cancel old approval &amp; run new cycle
    </a>
    <p style="font-size:12px;color:#6b7280;margin:16px 0 0">
      Or keep the old approval — no action needed.
    </p>
  </div>
</body></html>"""
    _send_email("⚠️ DCA Dynamic — Paycheck Detected (Approval Pending)", html)
    log.info("Pending conflict email sent")


# ─────────────────────────────────────────────
# PIPELINE ORCHESTRATION
# ─────────────────────────────────────────────

async def run_paycheck_pipeline(transaction_id: str, paycheck_amount: float):
    """
    Background task: cancel window → conflict check → ACH pull → poll → DCA cycle.
    Called from the webhook handler after a paycheck is confirmed.
    """
    # 1. Send detection email with cancel window
    cancel_token = create_action_token(
        "cancel",
        {"transaction_id": transaction_id},
        ttl_seconds=PAYCHECK_CANCEL_GRACE_SECONDS + 60,
    )
    _send_paycheck_detected_email(cancel_token, paycheck_amount)
    write_audit_entry("paycheck_detected", {
        "transaction_id": transaction_id,
        "amount": paycheck_amount,
        "cancel_token_prefix": cancel_token[:8],
    })

    # 2. Wait for cancel grace period
    await asyncio.sleep(PAYCHECK_CANCEL_GRACE_SECONDS)

    # 3. Check if user cancelled (token consumed by /plaid/cancel/{token})
    if get_action_token(cancel_token) is None:
        log.info(f"Paycheck cycle cancelled — txn {transaction_id[:8]}…")
        write_audit_entry("paycheck_cycle_cancelled", {"transaction_id": transaction_id})
        return

    # 4. Check for a stale pending approval (would cause a double cycle)
    if pending_approvals:
        force_token = create_action_token(
            "force",
            {"transaction_id": transaction_id, "paycheck_amount": paycheck_amount},
            ttl_seconds=86400,
        )
        _send_pending_conflict_email(force_token)
        write_audit_entry("paycheck_pending_conflict", {
            "transaction_id": transaction_id,
            "force_token_prefix": force_token[:8],
        })
        return

    # 5. Initiate ACH transfer
    try:
        relationship_id = get_ach_relationship_id()
        transfer = initiate_ach_transfer(relationship_id, CONTRIBUTION_AMOUNT)
        write_audit_entry("ach_transfer_initiated", {
            "relationship_id": relationship_id,
            "amount": CONTRIBUTION_AMOUNT,
            "transfer_id": transfer.get("id"),
        })
        log.info(f"ACH transfer initiated: ${CONTRIBUTION_AMOUNT:.2f} — id={transfer.get('id')}")
    except Exception as exc:
        log.exception(f"ACH transfer failed: {exc}")
        send_error_email("run_paycheck_pipeline / ACH transfer", exc)
        return

    # 6. Poll Alpaca until buying power is available
    available = await poll_for_buying_power(
        CONTRIBUTION_AMOUNT,
        ACH_POLL_INTERVAL_SECONDS,
        ACH_POLL_MAX_MINUTES,
    )
    if not available:
        retry_token = create_action_token(
            "retry", {"transaction_id": transaction_id}, ttl_seconds=86400
        )
        skip_token = create_action_token(
            "skip", {"transaction_id": transaction_id}, ttl_seconds=86400
        )
        _send_ach_timeout_email(retry_token, skip_token)
        write_audit_entry("ach_poll_timeout", {"transaction_id": transaction_id})
        return

    # 7. Fire the DCA cycle (same path as the old 1st/16th cron)
    log.info("Buying power confirmed — firing DCA contribution cycle")
    await scheduled_contribution()
    mark_paycheck_processed(transaction_id)


async def _retry_pipeline(transaction_id: str):
    """Re-poll and fire DCA cycle. Used by the retry email action."""
    available = await poll_for_buying_power(
        CONTRIBUTION_AMOUNT,
        ACH_POLL_INTERVAL_SECONDS,
        ACH_POLL_MAX_MINUTES,
    )
    if not available:
        retry_token = create_action_token(
            "retry", {"transaction_id": transaction_id}, ttl_seconds=86400
        )
        skip_token = create_action_token(
            "skip", {"transaction_id": transaction_id}, ttl_seconds=86400
        )
        _send_ach_timeout_email(retry_token, skip_token)
        return
    await scheduled_contribution()
    mark_paycheck_processed(transaction_id)


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@router.get("/link", response_class=HTMLResponse)
def plaid_link_page():
    """One-time Plaid Link setup page — run once to connect your bank account."""
    link_token = create_link_token()
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>DCA Dynamic — Plaid Setup</title>
<script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
</head>
<body style="font-family:-apple-system,sans-serif;display:flex;align-items:center;
             justify-content:center;min-height:100vh;margin:0;background:#f3f4f6">
  <div style="background:white;border-radius:16px;padding:40px;max-width:420px;
              text-align:center;box-shadow:0 4px 12px rgba(0,0,0,0.1)">
    <h1 style="margin:0 0 8px;font-size:24px">🏦 Connect Your Bank</h1>
    <p style="color:#6b7280;margin:0 0 24px;font-size:14px">
      One-time setup so DCA Dynamic can detect your paycheck automatically.
    </p>
    <button id="link-btn"
      style="background:#7c3aed;color:white;border:none;border-radius:8px;
             padding:14px 28px;font-size:16px;font-weight:600;cursor:pointer">
      Connect Bank Account
    </button>
  </div>
  <script>
    var handler = Plaid.create({{
      token: '{link_token}',
      onSuccess: function(public_token, metadata) {{
        fetch('/plaid/callback', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{public_token: public_token}}),
        }}).then(r => r.json()).then(function(d) {{
          document.body.innerHTML =
            '<div style="font-family:-apple-system,sans-serif;display:flex;' +
            'align-items:center;justify-content:center;min-height:100vh;margin:0">' +
            '<div style="text-align:center"><h1>✅ Bank Connected</h1>' +
            '<p style="color:#6b7280">Setup complete. DCA Dynamic will now detect' +
            ' your paycheck automatically.</p></div></div>';
        }});
      }},
      onExit: function(err) {{ if (err) console.error('Plaid Link error:', err); }},
    }});
    document.getElementById('link-btn').onclick = function() {{ handler.open(); }};
  </script>
</body></html>"""
    return HTMLResponse(html)


@router.post("/callback")
async def plaid_callback(request: Request):
    """Receives public_token from Plaid Link widget, exchanges for permanent access_token."""
    body = await request.json()
    public_token = body.get("public_token")
    if not public_token:
        raise HTTPException(status_code=400, detail="Missing public_token")
    access_token = exchange_public_token(public_token)
    set_access_token(access_token)
    write_audit_entry("plaid_linked", {})
    log.info("Plaid Link complete — access token stored")
    return {"status": "ok"}


@router.post("/webhook")
async def plaid_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Main entry point for Plaid TRANSACTIONS webhooks.
    Verifies JWT signature, syncs transactions, detects paycheck, starts pipeline.
    Returns 200 immediately; pipeline runs in background.
    """
    raw_body = await request.body()
    verification_header = request.headers.get("Plaid-Verification", "")

    if not verify_webhook(verification_header, raw_body):
        log.warning("Plaid webhook verification failed — rejecting")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(raw_body)
    webhook_type = payload.get("webhook_type")
    webhook_code = payload.get("webhook_code")

    if webhook_type != "TRANSACTIONS" or webhook_code != "SYNC_UPDATES_AVAILABLE":
        return {"status": "ignored", "webhook_type": webhook_type, "webhook_code": webhook_code}

    access_token = get_access_token()
    if not access_token:
        log.error("Plaid access token not configured — visit /plaid/link to set up")
        return JSONResponse(status_code=500, content={"status": "error", "detail": "access_token not set"})

    cursor = get_cursor()
    added, next_cursor = sync_transactions(access_token, cursor)
    set_cursor(next_cursor)

    for txn in added:
        txn_id = txn.get("transaction_id", "")
        if not is_paycheck(txn):
            continue
        if is_paycheck_processed(txn_id):
            log.info(f"Paycheck txn {txn_id[:8]}… already processed — skipping")
            continue
        log.info(f"Paycheck detected: {txn.get('name')} ${abs(txn.get('amount', 0)):.2f}")
        background_tasks.add_task(run_paycheck_pipeline, txn_id, txn.get("amount", 0))
        break  # process at most one paycheck per webhook event

    return {"status": "ok"}


@router.get("/cancel/{token}", response_class=HTMLResponse)
async def plaid_cancel(token: str):
    """Cancel a pending paycheck cycle before the ACH transfer initiates."""
    entry = consume_action_token(token)
    if not entry or entry["type"] != "cancel":
        return HTMLResponse(_result_page(
            "❌ Not Found", "This link has expired or already been used.", "#6b7280"
        ))
    write_audit_entry("paycheck_cycle_cancelled", {"token_prefix": token[:8]})
    log.info(f"Paycheck cycle cancelled via email link — {token[:8]}…")
    return HTMLResponse(_result_page(
        "🚫 Cycle Cancelled",
        "The DCA cycle was cancelled. No money will be transferred.",
        "#ef4444",
    ))


@router.get("/retry/{token}", response_class=HTMLResponse)
async def plaid_retry(token: str, background_tasks: BackgroundTasks):
    """Re-poll Alpaca buying power and retry the DCA cycle after an ACH timeout."""
    entry = consume_action_token(token)
    if not entry or entry["type"] != "retry":
        return HTMLResponse(_result_page(
            "❌ Not Found", "This link has expired or already been used.", "#6b7280"
        ))
    txn_id = entry["metadata"].get("transaction_id", "")
    background_tasks.add_task(_retry_pipeline, txn_id)
    write_audit_entry("ach_retry_requested", {"token_prefix": token[:8], "transaction_id": txn_id})
    return HTMLResponse(_result_page(
        "🔄 Retrying",
        "Checking buying power and retrying the DCA cycle. Approval email incoming.",
        "#3b82f6",
    ))


@router.get("/skip/{token}", response_class=HTMLResponse)
async def plaid_skip(token: str):
    """Skip a failed cycle. Marks transaction as processed so it won't retry."""
    entry = consume_action_token(token)
    if not entry or entry["type"] != "skip":
        return HTMLResponse(_result_page(
            "❌ Not Found", "This link has expired or already been used.", "#6b7280"
        ))
    txn_id = entry["metadata"].get("transaction_id", "")
    mark_paycheck_processed(txn_id)
    write_audit_entry("paycheck_cycle_skipped", {"token_prefix": token[:8], "transaction_id": txn_id})
    log.info(f"Paycheck cycle skipped — {txn_id[:8]}…")
    return HTMLResponse(_result_page(
        "✗ Cycle Skipped",
        "This DCA cycle was skipped. No orders were placed.",
        "#6b7280",
    ))


@router.get("/force/{token}", response_class=HTMLResponse)
async def plaid_force(token: str, background_tasks: BackgroundTasks):
    """Cancel stale pending approval and start a fresh paycheck pipeline."""
    entry = consume_action_token(token)
    if not entry or entry["type"] != "force":
        return HTMLResponse(_result_page(
            "❌ Not Found", "This link has expired or already been used.", "#6b7280"
        ))
    # Clear all stale pending approvals
    pending_approvals.clear()
    _save_pending(pending_approvals)
    write_audit_entry("pending_approvals_force_cleared", {"token_prefix": token[:8]})
    txn_id = entry["metadata"].get("transaction_id", "")
    paycheck_amount = entry["metadata"].get("paycheck_amount", 0.0)
    background_tasks.add_task(run_paycheck_pipeline, txn_id, paycheck_amount)
    return HTMLResponse(_result_page(
        "🔄 Running New Cycle",
        "Old approval cancelled. A fresh DCA cycle is starting — approval email incoming.",
        "#f97316",
    ))


@router.get("/trigger", response_class=HTMLResponse)
async def plaid_manual_trigger(token: str, background_tasks: BackgroundTasks):
    """
    Manual trigger: fire the DCA contribution cycle directly (no ACH pull).
    Use when you've funded Alpaca manually and Plaid missed the deposit.
    Requires PLAID_MANUAL_TRIGGER_TOKEN as the `token` query param.
    """
    if token != PLAID_MANUAL_TRIGGER_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    background_tasks.add_task(scheduled_contribution)
    write_audit_entry("manual_trigger", {})
    log.info("Manual DCA cycle triggered via /plaid/trigger")
    return HTMLResponse(_result_page(
        "🚀 DCA Cycle Started",
        "Manual trigger accepted. AI allocation proposal is on its way — approval email incoming.",
        "#10b981",
    ))
```

- [ ] **Step 2: Verify plaid_routes.py imports cleanly**

```bash
PLAID_CLIENT_ID=x PLAID_SECRET=x PLAID_MANUAL_TRIGGER_TOKEN=x \
  ALPACA_API_KEY=x ALPACA_SECRET_KEY=x ANTHROPIC_API_KEY=x \
  NOTIFY_EMAIL=x RESEND_API_KEY=x \
  python -c "import plaid_routes; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add plaid_routes.py
git commit -m "feat: add plaid_routes — webhook handler, email actions, paycheck pipeline"
```

---

## Task 7: scheduler_jobs.py — Add expire_plaid_tokens, Remove contribution_reminder

**Files:**
- Modify: `scheduler_jobs.py`

- [ ] **Step 1: Add expire_plaid_tokens function**

At the bottom of `scheduler_jobs.py`, add:

```python
# ─────────────────────────────────────────────
# EXPIRE PLAID TOKENS (daily 5pm ET)
# ─────────────────────────────────────────────

def expire_plaid_tokens():
    """Remove stale cancel/retry/skip/force tokens from plaid_store.json."""
    from plaid_store import expire_action_tokens
    expire_action_tokens()
```

- [ ] **Step 2: Remove contribution_reminder function**

Delete the entire `contribution_reminder` function and its section header from `scheduler_jobs.py`. It spans from the `# CONTRIBUTION REMINDER` comment through the `log.info("Contribution reminder email sent")` line.

- [ ] **Step 3: Verify scheduler_jobs.py imports cleanly**

```bash
PLAID_CLIENT_ID=x PLAID_SECRET=x PLAID_MANUAL_TRIGGER_TOKEN=x \
  ALPACA_API_KEY=x ALPACA_SECRET_KEY=x ANTHROPIC_API_KEY=x \
  NOTIFY_EMAIL=x RESEND_API_KEY=x \
  python -c "import scheduler_jobs; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add scheduler_jobs.py
git commit -m "feat: add expire_plaid_tokens scheduler job, remove contribution_reminder"
```

---

## Task 8: app.py — Wire Router, Reschedule Jobs

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Replace app.py entirely**

```python
"""
app.py — FastAPI app, lifespan, scheduler setup, entrypoint.

DCA Dynamic Bot — LIVE TRADING with AI-adjusted target weights.

Contribution flow (live):
  1. Plaid detects paycheck deposit in linked bank account
  2. POST /plaid/webhook fires → paycheck detected → background pipeline starts
  3. Detection email sent with 5-min cancel window
  4. $100 ACH pull initiated from linked bank → Alpaca
  5. Alpaca cash polled until buying power confirmed
  6. scheduled_contribution() called → Claude proposes dynamic allocation
  7. Approval email sent — orders execute only after user clicks Approve
  8. Stale approvals and Plaid action tokens expire daily at 5pm ET
"""

import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from config import ET, log
from plaid_routes import router as plaid_router
from routes import router
from scheduler_jobs import (
    dca_contribution_report,
    expire_pending,
    expire_plaid_tokens,
)

# ─────────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────────

scheduler = AsyncIOScheduler(timezone=ET)

# Expire unapproved order tokens: daily 5pm ET (decoupled from fixed contribution dates)
scheduler.add_job(
    expire_pending,
    "cron",
    hour=17,
    minute=0,
    id="expire_pending_approvals",
)

# Expire Plaid action tokens (cancel/retry/skip/force): daily 5pm ET
scheduler.add_job(
    expire_plaid_tokens,
    "cron",
    hour=17,
    minute=0,
    id="expire_plaid_tokens",
)

# Portfolio report: noon on 1st and 16th (snapshot, independent of contribution cadence)
scheduler.add_job(
    dca_contribution_report,
    "cron",
    day="1,16",
    hour=12,
    minute=0,
    id="dca_contribution_report",
)


# ─────────────────────────────────────────────
# LIFESPAN
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    log.info(
        "Scheduler started — LIVE TRADING. Jobs: "
        "expire_pending@17:00 daily, "
        "expire_plaid_tokens@17:00 daily, "
        "report@12:00 on 1st/16th. "
        "Contributions triggered by Plaid paycheck webhook."
    )
    yield
    scheduler.shutdown()


# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────

app = FastAPI(lifespan=lifespan, title="DCA Dynamic Bot")
app.include_router(router)
app.include_router(plaid_router)

# Inject scheduler into health endpoint via app state
app.state.scheduler = scheduler


from fastapi import Request

@app.get("/health")
def health_with_scheduler(request: Request):
    """Health check with scheduler info."""
    from routes import health
    return health(scheduler=request.app.state.scheduler)


# ─────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

- [ ] **Step 2: Verify the app starts**

```bash
PLAID_CLIENT_ID=x PLAID_SECRET=x PLAID_MANUAL_TRIGGER_TOKEN=x \
  ALPACA_API_KEY=x ALPACA_SECRET_KEY=x ANTHROPIC_API_KEY=x \
  NOTIFY_EMAIL=x RESEND_API_KEY=x \
  python -c "import app; print('ok')"
```

Expected: `ok` (plus live trading warning)

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: wire plaid_routes into app, replace fixed cron with event-driven jobs"
```

---

## Task 9: routes.py — Fix Health Endpoint

**Files:**
- Modify: `routes.py`

The `health()` function currently looks up `scheduler.get_job("scheduled_contribution")` which no longer exists. Replace it to show `"event_driven"` instead.

- [ ] **Step 1: Update the health function in routes.py**

Find this block in `routes.py` (around line 75–80):

```python
    # Find next contribution job run time
    next_run = None
    if scheduler:
        job = scheduler.get_job("scheduled_contribution")
        next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
```

Replace it with:

```python
    # Contributions are now event-driven (Plaid paycheck webhook)
    next_run = "event_driven"
```

- [ ] **Step 2: Verify routes.py imports cleanly**

```bash
PLAID_CLIENT_ID=x PLAID_SECRET=x PLAID_MANUAL_TRIGGER_TOKEN=x \
  ALPACA_API_KEY=x ALPACA_SECRET_KEY=x ANTHROPIC_API_KEY=x \
  NOTIFY_EMAIL=x RESEND_API_KEY=x \
  python -c "import routes; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Run all tests**

```bash
PLAID_CLIENT_ID=x PLAID_SECRET=x PLAID_MANUAL_TRIGGER_TOKEN=x \
  ALPACA_API_KEY=x ALPACA_SECRET_KEY=x ANTHROPIC_API_KEY=x \
  NOTIFY_EMAIL=x RESEND_API_KEY=x \
  pytest tests/ -v
```

Expected: all 15 tests PASS

- [ ] **Step 4: Commit**

```bash
git add routes.py
git commit -m "fix: update health endpoint — next_contribution is now event_driven"
```

---

## Task 10: Smoke Test Checklist (Manual)

Before deploying to Railway, run through this checklist locally with a real `.env` file (not dummy values).

- [ ] **Step 1: Start the server**

```bash
uvicorn app:app --reload --port 8000
```

- [ ] **Step 2: Visit the link page**

Open `http://localhost:8000/plaid/link` in a browser.
Expected: Bank connection page with "Connect Bank Account" button renders without error.

- [ ] **Step 3: Check health endpoint**

```bash
curl http://localhost:8000/health | python -m json.tool
```

Expected JSON includes `"next_contribution": "event_driven"` and `"status": "ok"`.

- [ ] **Step 4: Test manual trigger (dry run — no ACH)**

```bash
curl "http://localhost:8000/plaid/trigger?token=$PLAID_MANUAL_TRIGGER_TOKEN"
```

Expected: `"🚀 DCA Cycle Started"` result page rendered. Check logs — `scheduled_contribution()` should fire (it will fail without live Alpaca cash unless you have $100 in the account, which is expected).

- [ ] **Step 5: Simulate a cancel token flow**

```bash
# Grab a cancel token from plaid_store.json after a test pipeline run, or create one:
python -c "
import os; os.environ.update({'PLAID_CLIENT_ID':'x','PLAID_SECRET':'x','PLAID_MANUAL_TRIGGER_TOKEN':'x','ALPACA_API_KEY':'x','ALPACA_SECRET_KEY':'x','ANTHROPIC_API_KEY':'x','NOTIFY_EMAIL':'x','RESEND_API_KEY':'x'})
import plaid_store
t = plaid_store.create_action_token('cancel', {'transaction_id': 'test'}, 300)
print(t)
"
# Then curl:
curl "http://localhost:8000/plaid/cancel/<token>"
```

Expected: `"🚫 Cycle Cancelled"` page. Second click: `"❌ Not Found"` (token consumed).

- [ ] **Step 6: Deploy to Railway**

Add the new env vars in the Railway dashboard before deploying:
- `PLAID_CLIENT_ID` — from Plaid dashboard
- `PLAID_SECRET` — from Plaid dashboard
- `PLAID_ENV` — `production`
- `PLAID_MANUAL_TRIGGER_TOKEN` — any long random string (e.g. `openssl rand -hex 32`)

Then push:

```bash
git push origin main
```

- [ ] **Step 7: Complete Plaid Link (one-time)**

Visit `https://dca-bot-dynamic.up.railway.app/plaid/link`, complete the widget. Check Railway logs — should see `"Plaid Link complete — access token stored"`.

- [ ] **Step 8: Final commit**

```bash
git add docs/superpowers/plans/2026-04-26-plaid-paycheck-trigger.md
git commit -m "docs: add Plaid paycheck trigger implementation plan"
```

---

## Self-Review Notes

- `scheduled_contribution` is **kept** in `scheduler_jobs.py` (called by `plaid_routes.py`) — it just loses its cron registration in `app.py`
- `expire_pending` is **kept** in `scheduler_jobs.py` — rescheduled from 1st/16th 3:30pm to daily 5pm
- `contribution_reminder` is the **only** function deleted from `scheduler_jobs.py`
- Webhook body parsing uses `json.loads(raw_body)` not `await request.json()` — body stream already consumed by `await request.body()`
- `CONTRIBUTION_AMOUNT` is imported from `config.py` in `plaid_routes.py` — double-check the import line doesn't accidentally shadow with a `broker` import
- The `plaid_store.json` file persists across Railway restarts (Railway volumes or ephemeral FS depending on config) — if the FS is ephemeral and the file is lost, the user visits `/plaid/link` again to reconnect

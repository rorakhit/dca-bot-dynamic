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

    Returns True only if all checks pass. Logs a warning and returns False on failure.
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

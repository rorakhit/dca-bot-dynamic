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
    get_account_info,
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
    set_account_info,
    set_cursor,
)
from scheduler_jobs import scheduled_contribution

router = APIRouter(prefix="/plaid")


# ─────────────────────────────────────────────
# SHARED RESULT PAGE (same pattern as approval.py)
# ─────────────────────────────────────────────

def _result_page(title: str, body: str, color: str) -> str:
    parts = title.split(" ", 1)
    icon = parts[0]
    heading = parts[1] if len(parts) > 1 else ""
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
    localStorage.setItem('plaid_link_token', '{link_token}');
    var handler = Plaid.create({{
      token: '{link_token}',
      onSuccess: function(public_token, metadata) {{
        fetch('/plaid/callback', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{public_token: public_token}}),
        }}).then(r => r.json()).then(function(d) {{
          localStorage.removeItem('plaid_link_token');
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


@router.get("/oauth-return", response_class=HTMLResponse)
def plaid_oauth_return():
    """OAuth return page — Plaid redirects here after bank OAuth flow (Chase, SoFi, etc.)."""
    html = """<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>DCA Dynamic — Connecting...</title>
<script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
</head>
<body style="font-family:-apple-system,sans-serif;display:flex;align-items:center;
             justify-content:center;min-height:100vh;margin:0;background:#f3f4f6">
  <div style="background:white;border-radius:16px;padding:40px;max-width:420px;
              text-align:center;box-shadow:0 4px 12px rgba(0,0,0,0.1)">
    <h1 style="margin:0 0 8px;font-size:24px">⏳ Completing Connection...</h1>
    <p style="color:#6b7280;margin:0;font-size:14px">Finishing bank OAuth — please wait.</p>
  </div>
  <script>
    var token = localStorage.getItem('plaid_link_token');
    if (!token) {
      document.body.innerHTML =
        '<div style="font-family:-apple-system,sans-serif;display:flex;align-items:center;' +
        'justify-content:center;min-height:100vh;margin:0"><div style="text-align:center">' +
        '<h1>⚠️ Session Expired</h1>' +
        '<p><a href="/plaid/link">Start over</a></p></div></div>';
    } else {
      var handler = Plaid.create({
        token: token,
        receivedRedirectUri: window.location.href,
        onSuccess: function(public_token, metadata) {
          fetch('/plaid/callback', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({public_token: public_token}),
          }).then(r => r.json()).then(function() {
            localStorage.removeItem('plaid_link_token');
            document.body.innerHTML =
              '<div style="font-family:-apple-system,sans-serif;display:flex;' +
              'align-items:center;justify-content:center;min-height:100vh;margin:0">' +
              '<div style="text-align:center"><h1>✅ Bank Connected</h1>' +
              '<p style="color:#6b7280">Setup complete. DCA Dynamic will now detect' +
              ' your paycheck automatically.</p></div></div>';
          });
        },
        onExit: function(err) { if (err) console.error('Plaid OAuth return error:', err); },
      });
      handler.open();
    }
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
    try:
        institution_name, account_mask = get_account_info(access_token)
        set_account_info(institution_name, account_mask)
        log.info("Plaid account info stored: %s ••%s", institution_name, account_mask)
    except Exception as e:
        log.warning("Could not fetch Plaid account info (non-fatal): %s", e)
    write_audit_entry("plaid_linked", {})
    log.info("Plaid Link complete — access token stored")
    return {"status": "ok"}


@router.post("/refresh-account-info")
async def refresh_account_info():
    """Re-fetch institution name and account mask from Plaid and update the store."""
    access_token = get_access_token()
    if not access_token:
        raise HTTPException(status_code=400, detail="No Plaid account linked — visit /plaid/link first")
    institution_name, account_mask = get_account_info(access_token)
    set_account_info(institution_name, account_mask)
    log.info("Plaid account info refreshed: %s ••%s", institution_name, account_mask)
    return {"status": "ok", "institution": institution_name, "mask": account_mask}


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

    log.info(f"Plaid webhook received: type={webhook_type} code={webhook_code}")

    if webhook_type != "TRANSACTIONS" or webhook_code != "SYNC_UPDATES_AVAILABLE":
        return {"status": "ignored", "webhook_type": webhook_type, "webhook_code": webhook_code}

    access_token = get_access_token()
    if not access_token:
        log.error("Plaid access token not configured — visit /plaid/link to set up")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": "access_token not set"},
        )

    cursor = get_cursor()
    added, next_cursor = sync_transactions(access_token, cursor)
    set_cursor(next_cursor)

    log.info(f"Plaid sync: {len(added)} added transaction(s)")
    for txn in added:
        log.info(
            f"  txn: name={txn.get('name')!r} amount={txn.get('amount')} "
            f"date={txn.get('date')} id={txn.get('transaction_id', '')[:8]}…"
        )

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


@router.get("/trigger-full", response_class=HTMLResponse)
async def plaid_manual_trigger_full(token: str, background_tasks: BackgroundTasks):
    """
    Full pipeline trigger: ACH pull from bank → poll for buying power → DCA cycle.
    Use when your paycheck deposited but the Plaid webhook missed it.
    Requires PLAID_MANUAL_TRIGGER_TOKEN as the `token` query param.
    """
    if token != PLAID_MANUAL_TRIGGER_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    background_tasks.add_task(run_paycheck_pipeline, "manual_trigger_full", CONTRIBUTION_AMOUNT * -1)
    write_audit_entry("manual_trigger_full", {})
    log.info("Full paycheck pipeline triggered manually via /plaid/trigger-full")
    return HTMLResponse(_result_page(
        "🏦 Full Pipeline Started",
        f"ACH transfer of ${CONTRIBUTION_AMOUNT:.0f} initiating from your bank. "
        "Cancel email sent — you have 5 minutes to abort before the transfer goes through.",
        "#10b981",
    ))

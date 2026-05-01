"""
plaid_routes.py — Plaid webhook, Link setup, and paycheck pipeline routes.

Routes:
  GET  /plaid/link              — one-time Plaid Link setup page
  POST /plaid/callback          — receives public_token, stores access_token
  POST /plaid/webhook           — Plaid TRANSACTIONS webhook (main entry point)
  GET  /plaid/force/{token}     — cancel stale approval and run fresh cycle
  GET  /plaid/trigger           — manual DCA-only trigger (Alpaca already funded)
  GET  /plaid/trigger-full      — manual full trigger with optional ?schedule=HH:MM
  POST /plaid/refresh-account-info — re-fetch institution name and account mask
"""

import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from approval import _save_pending, create_pending_approval, pending_approvals
from audit import write_audit_entry
from config import (
    CONTRIBUTION_AMOUNT,
    ET,
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

def _send_paycheck_detected_email(paycheck_amount: float, trigger_url: str, contribution_amount: float | None = None):
    cycle_amount = contribution_amount if contribution_amount is not None else CONTRIBUTION_AMOUNT
    html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,sans-serif;padding:24px;color:#111827">
  <div style="max-width:520px;background:#ecfdf5;border:1px solid #6ee7b7;
              border-radius:12px;padding:24px">
    <h2 style="color:#059669;margin:0 0 12px">💰 Paycheck Detected</h2>
    <p style="margin:0 0 8px">
      A deposit of <strong>${abs(paycheck_amount):.2f}</strong> from your employer was detected.
    </p>
    <p style="margin:8px 0">
      Transfer <strong>${cycle_amount:.0f}</strong> into your Alpaca account, then tap
      the button below to run the DCA cycle.
    </p>
    <a href="{trigger_url}"
       style="display:inline-block;margin-top:16px;padding:14px 28px;
              background:#059669;color:white;border-radius:8px;font-weight:600;
              text-decoration:none;font-size:16px">
      🚀 Run DCA Cycle
    </a>
    <p style="font-size:12px;color:#6b7280;margin:16px 0 0">
      This link is valid for 24 hours. Only tap after funding your Alpaca account.
    </p>
  </div>
</body></html>"""
    _send_email("💰 Paycheck Detected — Fund Alpaca &amp; Run DCA", html)
    log.info("Paycheck detected email sent")


def _send_pending_conflict_email(force_token: str):
    force_url = f"{SERVER_BASE_URL}/plaid/force/{force_token}"
    html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,sans-serif;padding:24px;color:#111827">
  <div style="max-width:520px;background:#fef3c7;border:1px solid #fcd34d;
              border-radius:12px;padding:24px">
    <h2 style="color:#d97706;margin:0 0 12px">⚠️ Paycheck Detected — Approval Pending</h2>
    <p style="margin:0 0 8px">
      A new paycheck was detected, but a previous DCA approval is still pending.
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

async def run_paycheck_pipeline(transaction_id: str, paycheck_amount: float, contribution_amount: float | None = None):
    """
    Background task: detect paycheck → check for conflicts → email user to fund
    Alpaca and tap the DCA trigger link.

    contribution_amount overrides CONTRIBUTION_AMOUNT for this cycle if provided.
    """
    cycle_amount = contribution_amount if contribution_amount is not None else CONTRIBUTION_AMOUNT

    # Check for a stale pending approval (would cause a double cycle)
    if pending_approvals:
        force_token = create_action_token(
            "force",
            {"transaction_id": transaction_id, "paycheck_amount": paycheck_amount, "contribution_amount": cycle_amount},
            ttl_seconds=86400,
        )
        _send_pending_conflict_email(force_token)
        write_audit_entry("paycheck_pending_conflict", {
            "transaction_id": transaction_id,
            "force_token_prefix": force_token[:8],
        })
        return

    # Create a one-time trigger token valid for 24h, carrying the contribution amount
    trigger_token = create_action_token(
        "trigger",
        {"transaction_id": transaction_id, "contribution_amount": cycle_amount},
        ttl_seconds=86400,
    )
    trigger_url = f"{SERVER_BASE_URL}/plaid/trigger-once/{trigger_token}"

    _send_paycheck_detected_email(paycheck_amount, trigger_url, cycle_amount)
    write_audit_entry("paycheck_detected", {
        "transaction_id": transaction_id,
        "amount": paycheck_amount,
        "contribution_amount": cycle_amount,
        "trigger_token_prefix": trigger_token[:8],
    })
    log.info(f"Paycheck detected — awaiting manual Alpaca funding for txn {transaction_id[:8]}…")


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


@router.get("/trigger-once/{token}", response_class=HTMLResponse)
async def plaid_trigger_once(token: str, background_tasks: BackgroundTasks):
    """
    One-time DCA trigger sent in the paycheck detected email.
    Valid for 24h — fires scheduled_contribution() once Alpaca is funded.
    Contribution amount is embedded in the token metadata.
    """
    entry = consume_action_token(token)
    if not entry or entry["type"] != "trigger":
        return HTMLResponse(_result_page(
            "❌ Not Found", "This link has expired or already been used.", "#6b7280"
        ))
    txn_id = entry["metadata"].get("transaction_id", "")
    contribution_amount = entry["metadata"].get("contribution_amount", CONTRIBUTION_AMOUNT)
    mark_paycheck_processed(txn_id)
    background_tasks.add_task(scheduled_contribution, contribution_amount)
    write_audit_entry("paycheck_trigger_once_used", {
        "token_prefix": token[:8],
        "transaction_id": txn_id,
        "contribution_amount": contribution_amount,
    })
    log.info(f"Paycheck trigger-once used — txn {txn_id[:8]}… amount=${contribution_amount:.2f}")
    return HTMLResponse(_result_page(
        "🚀 DCA Cycle Started",
        f"Got it — allocating ${contribution_amount:.0f}. Approval email incoming.",
        "#10b981",
    ))


@router.get("/force/{token}", response_class=HTMLResponse)
async def plaid_force(token: str, background_tasks: BackgroundTasks):
    """Cancel stale pending approval and re-send paycheck detected email."""
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
        "Old approval cancelled. Paycheck detected email resent — check your inbox.",
        "#f97316",
    ))


@router.get("/trigger", response_class=HTMLResponse)
async def plaid_manual_trigger(token: str, background_tasks: BackgroundTasks, amount: Optional[float] = None):
    """
    Manual DCA trigger — fires the contribution cycle directly.
    Use after funding Alpaca manually.
    Requires PLAID_MANUAL_TRIGGER_TOKEN as the `token` query param.
    Optional: ?amount=200 to override the default $100 contribution.
    """
    if token != PLAID_MANUAL_TRIGGER_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    contribution_amount = amount if amount is not None else CONTRIBUTION_AMOUNT
    background_tasks.add_task(scheduled_contribution, contribution_amount)
    write_audit_entry("manual_trigger", {"contribution_amount": contribution_amount})
    log.info(f"Manual DCA cycle triggered via /plaid/trigger — ${contribution_amount:.2f}")
    return HTMLResponse(_result_page(
        "🚀 DCA Cycle Started",
        f"Manual trigger accepted — allocating ${contribution_amount:.0f}. Approval email incoming.",
        "#10b981",
    ))


@router.get("/trigger-full", response_class=HTMLResponse)
async def plaid_manual_trigger_full(
    request: Request,
    token: str,
    background_tasks: BackgroundTasks,
    schedule: Optional[str] = None,
    amount: Optional[float] = None,
):
    """
    Manual full pipeline trigger — sends paycheck detected email with DCA link.
    Use when your paycheck deposited but the Plaid webhook missed it.
    Requires PLAID_MANUAL_TRIGGER_TOKEN as the `token` query param.
    Optional: ?schedule=HH:MM (ET, 24h) to defer to a specific time.
    Optional: ?amount=200 to override the default $100 contribution.
    """
    if token != PLAID_MANUAL_TRIGGER_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

    contribution_amount = amount if amount is not None else CONTRIBUTION_AMOUNT

    if schedule:
        try:
            run_time_naive = datetime.strptime(schedule, "%H:%M")
            run_dt = datetime.now(ET).replace(
                hour=run_time_naive.hour,
                minute=run_time_naive.minute,
                second=0,
                microsecond=0,
            )
            if run_dt <= datetime.now(ET):
                run_dt += timedelta(days=1)
        except ValueError:
            return HTMLResponse(_result_page(
                "⚠️ Invalid Time",
                "Use HH:MM format in 24h ET, e.g. ?schedule=10:00 or ?schedule=14:30",
                "#d97706",
            ))

        scheduler = request.app.state.scheduler
        scheduler.add_job(
            run_paycheck_pipeline,
            "date",
            run_date=run_dt,
            args=["manual_trigger_full", contribution_amount * -1, contribution_amount],
            id="manual_trigger_full_scheduled",
            replace_existing=True,
        )
        write_audit_entry("manual_trigger_full_scheduled", {
            "scheduled_for": run_dt.isoformat(),
            "contribution_amount": contribution_amount,
        })
        log.info(f"Paycheck pipeline scheduled for {run_dt.strftime('%H:%M ET')} — ${contribution_amount:.2f}")
        return HTMLResponse(_result_page(
            "⏰ Pipeline Scheduled",
            f"Paycheck detected email will be sent at {run_dt.strftime('%-I:%M %p ET on %a %b %-d')} "
            f"for ${contribution_amount:.0f}.",
            "#10b981",
        ))

    background_tasks.add_task(run_paycheck_pipeline, "manual_trigger_full", contribution_amount * -1, contribution_amount)
    write_audit_entry("manual_trigger_full", {"contribution_amount": contribution_amount})
    log.info(f"Paycheck pipeline triggered manually via /plaid/trigger-full — ${contribution_amount:.2f}")
    return HTMLResponse(_result_page(
        "💰 Paycheck Email Sent",
        f"Check your inbox — fund your Alpaca account with ${contribution_amount:.0f} "
        "then tap the link in the email to run the DCA cycle.",
        "#10b981",
    ))

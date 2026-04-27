"""
routes.py — All FastAPI route handlers for the DCA Dynamic bot.

Endpoints:
  GET  /                — desktop dashboard
  GET  /dashboard       — mobile dashboard
  GET  /health          — server status (paper_trading: false, strategy: "dynamic")
  GET  /portfolio       — current holdings
  GET  /audit           — audit log
  GET  /pending         — view pending approvals
  GET  /approve/{token} — approve a pending allocation (executes orders)
  GET  /deny/{token}    — deny a pending allocation
  POST /contribute      — manual trigger (sends approval email unless dry_run=true)
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from ai import ask_ai_for_dynamic_allocation
from approval import (
    create_pending_approval,
    handle_approval,
    handle_denial,
    pending_approvals,
)
from audit import get_audit_history_summary, read_audit_log, write_audit_entry
from broker import (
    broker,
    fetch_market_data,
    get_portfolio_state,
    is_market_open,
    is_trading_day,
)
from config import BASE_TARGET_ALLOCATION, CONTRIBUTION_AMOUNT, ET, log
from dashboard import DASHBOARD_HTML, LANDING_HTML
from plaid_store import get_account_info as get_plaid_account_info

router = APIRouter()


# ─────────────────────────────────────────────
# DASHBOARD ENDPOINTS
# ─────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def landing_page():
    """Desktop-optimized portfolio dashboard."""
    return HTMLResponse(LANDING_HTML)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Mobile-friendly portfolio dashboard."""
    return HTMLResponse(DASHBOARD_HTML)


# ─────────────────────────────────────────────
# HEALTH ENDPOINT
# ─────────────────────────────────────────────

def health(scheduler=None):
    """
    Quick status check — live trading, dynamic strategy, pending approval count.
    """
    errors = []
    account_value = None

    try:
        account = broker.get_account()
        account_value = float(account.portfolio_value)
    except Exception as e:
        errors.append(f"Alpaca: {e}")

    # Contributions are now event-driven (Plaid paycheck webhook)
    next_run = "event_driven"

    plaid_institution, plaid_account_mask = get_plaid_account_info()

    return JSONResponse({
        "status": "ok" if not errors else "degraded",
        "errors": errors,
        "paper_trading": False,
        "strategy": "dynamic",
        "market_open": is_market_open(),
        "trading_day": is_trading_day(),
        "pending_approvals": len(pending_approvals),
        "next_contribution": next_run,
        "account_value_usd": account_value,
        "server_time_et": datetime.now(ET).isoformat(),
        "fund_lineup": list(BASE_TARGET_ALLOCATION.keys()),
        "plaid_institution": plaid_institution,
        "plaid_account_mask": plaid_account_mask,
    })


# ─────────────────────────────────────────────
# API ENDPOINTS
# ─────────────────────────────────────────────

@router.get("/portfolio")
def portfolio_snapshot():
    """Current holdings and allocation."""
    return get_portfolio_state()


@router.get("/audit")
def audit_log():
    """Return parsed audit log entries as JSON, newest first."""
    return read_audit_log()


# ─────────────────────────────────────────────
# PENDING APPROVALS
# ─────────────────────────────────────────────

@router.get("/pending")
def list_pending():
    """See what approvals are currently waiting."""
    return {k[:8]: v for k, v in pending_approvals.items()}


@router.get("/approve/{token}", response_class=HTMLResponse)
async def approve(token: str):
    """User clicks Approve in email -> orders execute immediately."""
    result = handle_approval(token)
    if result is None:
        raise HTTPException(status_code=404, detail="Token not found or already used.")
    return HTMLResponse(result)


@router.get("/deny/{token}", response_class=HTMLResponse)
async def deny(token: str):
    """User clicks Deny in email -> allocation discarded."""
    result = handle_denial(token)
    if result is None:
        raise HTTPException(status_code=404, detail="Token not found or already used.")
    return HTMLResponse(result)


# ─────────────────────────────────────────────
# MANUAL CONTRIBUTION
# ─────────────────────────────────────────────

@router.post("/contribute")
async def manual_contribution(amount: float = CONTRIBUTION_AMOUNT, dry_run: bool = True):
    """
    Manually trigger a contribution cycle.
      POST /contribute?amount=100&dry_run=true   — propose, return, no email, no orders
      POST /contribute?amount=100&dry_run=false  — propose, send approval email, wait for click

    Orders never execute without a user-approved email click — same gate as scheduled runs.
    """
    log.info(f"Manual contribution: ${amount:.2f} | dry_run={dry_run}")

    try:
        portfolio = get_portfolio_state()
        write_audit_entry("portfolio_snapshot", portfolio)

        # Fetch market data
        symbols = list(BASE_TARGET_ALLOCATION.keys())
        market_stats = fetch_market_data(symbols)

        # Audit history for AI context
        audit_history = get_audit_history_summary(max_entries=10)

        # Dynamic AI allocation
        dynamic_result = ask_ai_for_dynamic_allocation(
            portfolio, amount, market_stats, audit_history
        )
        write_audit_entry("dynamic_allocation_proposed", {
            "adjusted_targets": dynamic_result["adjusted_targets"],
            "weight_reasoning": dynamic_result["weight_reasoning"],
            "allocations": dynamic_result["allocations"],
            "allocation_reasoning": dynamic_result["allocation_reasoning"],
            "new_cash": amount,
        })

        if dry_run:
            log.info("Dry run — skipping approval email and orders")
            return {
                "status": "done",
                "dry_run": True,
                "dynamic": dynamic_result,
            }

        # Send approval email — orders execute only if user clicks Approve
        token = create_pending_approval(
            allocations=dynamic_result["allocations"],
            allocation_reasoning=dynamic_result["allocation_reasoning"],
            adjusted_targets=dynamic_result["adjusted_targets"],
            weight_reasoning=dynamic_result["weight_reasoning"],
            new_cash=amount,
        )

        return {
            "status": "pending_approval",
            "dry_run": False,
            "token_prefix": token[:8],
            "dynamic": dynamic_result,
        }

    except Exception as exc:
        log.exception(f"Manual contribution failed: {exc}")
        write_audit_entry("contribution_error", {"error": str(exc), "new_cash": amount})
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(exc)},
        )

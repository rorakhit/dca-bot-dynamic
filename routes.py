"""
routes.py — All FastAPI route handlers for the DCA Dynamic bot.

Endpoints:
  GET  /            — desktop dashboard
  GET  /dashboard   — mobile dashboard
  GET  /health      — server status (paper_trading: true, strategy: "dynamic")
  GET  /portfolio   — current holdings
  GET  /audit       — audit log
  GET  /comparison  — A/B strategy comparison data
  POST /contribute  — manual trigger
"""

from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from ai import compute_fixed_strategy_allocation
from audit import get_audit_history_summary, read_audit_log, write_audit_entry
from broker import (
    broker,
    execute_allocations,
    fetch_market_data,
    get_portfolio_state,
    is_market_open,
    is_trading_day,
)
from ai import ask_ai_for_dynamic_allocation
from config import BASE_TARGET_ALLOCATION, CONTRIBUTION_AMOUNT, ET, log
from dashboard import DASHBOARD_HTML, LANDING_HTML

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
    Quick status check with paper trading and dynamic strategy indicators.
    """
    errors = []
    account_value = None

    try:
        account = broker.get_account()
        account_value = float(account.portfolio_value)
    except Exception as e:
        errors.append(f"Alpaca: {e}")

    # Find next contribution job run time
    next_run = None
    if scheduler:
        job = scheduler.get_job("scheduled_contribution")
        next_run = job.next_run_time.isoformat() if job and job.next_run_time else None

    return JSONResponse({
        "status": "ok" if not errors else "degraded",
        "errors": errors,
        "paper_trading": True,
        "strategy": "dynamic",
        "market_open": is_market_open(),
        "trading_day": is_trading_day(),
        "next_contribution": next_run,
        "account_value_usd": account_value,
        "server_time_et": datetime.now(ET).isoformat(),
        "fund_lineup": list(BASE_TARGET_ALLOCATION.keys()),
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


@router.get("/comparison")
def strategy_comparison():
    """
    Return A/B strategy comparison data from the audit log.
    Pairs dynamic and fixed allocations by date for side-by-side comparison.
    """
    entries = read_audit_log()  # newest first

    # Collect dynamic and fixed entries, pair them by date
    dynamic_entries = [e for e in entries if e.get("event") == "dynamic_allocation_proposed"]
    fixed_entries = [e for e in entries if e.get("event") == "fixed_counterfactual_logged"]

    # Build lookup by date for fixed entries
    fixed_by_date = {}
    for e in fixed_entries:
        day = e.get("timestamp", "")[:10]
        if day not in fixed_by_date:
            fixed_by_date[day] = e

    comparison = []
    for dyn in dynamic_entries[:20]:  # last 20 cycles
        day = dyn.get("timestamp", "")[:10]
        fixed = fixed_by_date.get(day, {})

        comparison.append({
            "date": dyn.get("timestamp", ""),
            "dynamic_targets": dyn.get("adjusted_targets"),
            "dynamic_allocations": dyn.get("allocations"),
            "fixed_allocations": fixed.get("allocations"),
            "reasoning": dyn.get("weight_reasoning", ""),
        })

    return comparison


# ─────────────────────────────────────────────
# MANUAL CONTRIBUTION
# ─────────────────────────────────────────────

@router.post("/contribute")
async def manual_contribution(amount: float = CONTRIBUTION_AMOUNT, dry_run: bool = True):
    """
    Manually trigger a contribution cycle.
    POST /contribute?amount=100&dry_run=true
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

        # Fixed counterfactual
        fixed_result = compute_fixed_strategy_allocation(portfolio, amount)
        write_audit_entry("fixed_counterfactual_logged", {
            "allocations": fixed_result["allocations"],
            "reasoning": fixed_result["reasoning"],
            "target_allocation": fixed_result["target_allocation"],
            "new_cash": amount,
        })

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
            log.info("Dry run — skipping order execution")
            return {
                "status": "done",
                "dry_run": True,
                "dynamic": dynamic_result,
                "fixed": fixed_result,
            }

        # Execute dynamic allocation (paper trading)
        receipts = execute_allocations(dynamic_result["allocations"], dry_run=False)
        write_audit_entry("orders_placed", {
            "receipts": receipts,
            "strategy": "dynamic",
            "executed_by": "manual_trigger",
        })

        return {
            "status": "done",
            "dry_run": False,
            "dynamic": dynamic_result,
            "fixed": fixed_result,
            "receipts": receipts,
        }

    except Exception as exc:
        log.exception(f"Manual contribution failed: {exc}")
        write_audit_entry("contribution_error", {"error": str(exc), "new_cash": amount})
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(exc)},
        )

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

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ai import ask_ai_for_dynamic_allocation
from approval import (
    create_pending_approval,
    handle_approval,
    handle_denial,
    pending_approvals,
)
from audit import get_audit_history_summary, read_audit_log, write_audit_entry
from auth import COOKIE_NAME, DASHBOARD_SECRET, LOGIN_HTML, is_authenticated, require_auth
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
# AUTH ENDPOINTS
# ─────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    """Login page — redirects to dashboard if already authenticated."""
    if is_authenticated(request):
        return RedirectResponse(url="/dashboard-home", status_code=302)
    return HTMLResponse(LOGIN_HTML)


@router.post("/auth")
async def auth_login(request: Request):
    body = await request.json()
    if body.get("secret") != DASHBOARD_SECRET:
        return JSONResponse({"error": "Invalid secret"}, status_code=403)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        key=COOKIE_NAME,
        value=DASHBOARD_SECRET,
        httponly=True,
        samesite="strict",
        path="/",
        max_age=30 * 24 * 60 * 60,
    )
    return response


@router.get("/auth/logout")
def auth_logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


# ─────────────────────────────────────────────
# DASHBOARD ENDPOINTS (protected)
# ─────────────────────────────────────────────

@router.get("/dashboard-home", response_class=HTMLResponse)
def landing_page(request: Request):
    """Desktop-optimized portfolio dashboard."""
    redirect = require_auth(request)
    if redirect:
        return redirect
    return HTMLResponse(LANDING_HTML)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    """Mobile-friendly portfolio dashboard."""
    redirect = require_auth(request)
    if redirect:
        return redirect
    return HTMLResponse(DASHBOARD_HTML)


# ─────────────────────────────────────────────
# DEMO (public, fake data)
# ─────────────────────────────────────────────

DEMO_AUDIT = [
    {
        "event": "dynamic_allocation_proposed",
        "timestamp": "2026-04-30T14:02:11.443Z",
        "adjusted_targets": {"VTI": 0.52, "VXUS": 0.33, "AVUV": 0.10, "BND": 0.05},
        "weight_reasoning": "Tilting slightly toward VTI given continued US large-cap momentum. VXUS trimmed modestly — international volatility remains elevated. AVUV held at base; small-cap value factor showing early signs of mean reversion. BND unchanged, rates still restrictive.",
        "allocations": {"VTI": 52.00, "VXUS": 33.00, "AVUV": 10.00, "BND": 5.00},
        "allocation_reasoning": "Portfolio is underweight VTI by 1.8% and overweight VXUS by 2.1%. Full $100 directed toward closing both gaps — $52 to VTI, $33 to VXUS, $10 to AVUV to maintain factor exposure, $5 to BND.",
        "new_cash": 100.0,
    },
    {
        "event": "paycheck_detected",
        "timestamp": "2026-04-30T13:58:04.112Z",
        "amount": -2840.50,
        "contribution_amount": 100.0,
    },
    {
        "event": "dynamic_allocation_proposed",
        "timestamp": "2026-04-15T14:11:33.201Z",
        "adjusted_targets": {"VTI": 0.50, "VXUS": 0.35, "AVUV": 0.08, "BND": 0.07},
        "weight_reasoning": "Holding base weights on VTI and VXUS — no strong directional signal. Trimming AVUV slightly; small-cap value underperformed over the trailing quarter. Adding marginal allocation to BND as a volatility hedge.",
        "allocations": {"VTI": 50.00, "VXUS": 35.00, "AVUV": 8.00, "BND": 7.00},
        "allocation_reasoning": "Drift is minimal across all positions. Allocating proportionally to adjusted targets — $50 VTI, $35 VXUS, $8 AVUV, $7 BND.",
        "new_cash": 100.0,
    },
    {
        "event": "paycheck_detected",
        "timestamp": "2026-04-15T13:55:17.009Z",
        "amount": -2840.50,
        "contribution_amount": 100.0,
    },
    {
        "event": "portfolio_snapshot",
        "timestamp": "2026-04-15T14:10:55.883Z",
        "holdings": {
            "VTI":  {"market_value": 12480.22, "weight": 0.511, "unrealized_pl": 1840.10},
            "VXUS": {"market_value":  8421.85, "weight": 0.345, "unrealized_pl":  620.34},
            "AVUV": {"market_value":  2318.44, "weight": 0.095, "unrealized_pl":  218.90},
            "BND":  {"market_value":  1220.10, "weight": 0.050, "unrealized_pl":   12.44},
        },
    },
]

DEMO_PORTFOLIO = {
    "total_value": 24440.61,
    "cash": 0.00,
    "cost_basis": 21748.83,
    "unrealized_pl": 2691.78,
    "holdings": {
        "VTI":  {"market_value": 12880.44, "weight": 0.5270, "unrealized_pl": 2040.10, "qty": 51.2},
        "VXUS": {"market_value":  8521.85, "weight": 0.3487, "unrealized_pl":  720.34, "qty": 148.6},
        "AVUV": {"market_value":  2318.22, "weight": 0.0948, "unrealized_pl":  218.90, "qty": 29.1},
        "BND":  {"market_value":   720.10, "weight": 0.0295, "unrealized_pl":   12.44, "qty": 9.8},
    },
}

DEMO_HEALTH = {
    "status": "ok",
    "errors": [],
    "paper_trading": False,
    "strategy": "dynamic",
    "market_open": False,
    "trading_day": True,
    "pending_approvals": 0,
    "next_contribution": "event_driven",
    "account_value_usd": 24440.61,
    "server_time_et": "2026-04-30T14:05:00-04:00",
    "fund_lineup": ["VTI", "VXUS", "AVUV", "BND"],
    "plaid_institution": "SoFi",
    "plaid_account_mask": "5266",
}


@router.get("/demo", response_class=HTMLResponse)
def demo_dashboard():
    """Public demo dashboard with fake data — no auth required."""
    html = (
        LANDING_HTML
        .replace("fetch('/portfolio')", "fetch('/demo/portfolio')")
        .replace("fetch('/health')", "fetch('/demo/health')")
        .replace("fetch('/audit')", "fetch('/demo/audit')")
    )
    demo_banner = """<div style="position:fixed;top:0;left:0;right:0;z-index:999;
      background:rgba(245,158,11,0.12);border-bottom:1px solid rgba(245,158,11,0.25);
      padding:8px;text-align:center;font-family:-apple-system,sans-serif;
      font-size:12px;font-weight:600;letter-spacing:0.05em;color:#f59e0b">
      DEMO — simulated data only
    </div>"""
    html = html.replace("<body>", f"<body>{demo_banner}", 1)
    return HTMLResponse(html)


@router.get("/demo/portfolio")
def demo_portfolio():
    return JSONResponse(DEMO_PORTFOLIO)


@router.get("/demo/health")
def demo_health():
    return JSONResponse(DEMO_HEALTH)


@router.get("/demo/audit")
def demo_audit():
    return JSONResponse(DEMO_AUDIT)


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

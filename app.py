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
    poll_for_paycheck,
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

# Paycheck poll fallback: every 2 hours 8am–4pm ET, no-ops outside pay date windows
scheduler.add_job(
    poll_for_paycheck,
    "cron",
    hour="8,10,12,14,16",
    minute=0,
    id="poll_for_paycheck",
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
        "report@12:00 on 1st/16th, "
        "poll_for_paycheck@8/10/12/14/16 on pay windows. "
        "Contributions triggered by Plaid paycheck webhook + polling fallback."
    )
    yield
    scheduler.shutdown()


# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────

app = FastAPI(lifespan=lifespan, title="DCA Dynamic Bot")
app.include_router(router)
app.include_router(plaid_router)

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

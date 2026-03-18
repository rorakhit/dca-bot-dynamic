"""
app.py — FastAPI app, lifespan, scheduler setup, entrypoint.

DCA Dynamic Bot — Paper trading experiment with AI-adjusted target weights.
"""

import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from config import ET, log
from routes import router
from scheduler_jobs import (
    contribution_reminder,
    dca_contribution_report,
    scheduled_contribution,
)

# ─────────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────────

scheduler = AsyncIOScheduler(timezone=ET)

# Contribution: 10am ET on 1st and 16th (day after payday)
scheduler.add_job(
    scheduled_contribution,
    "cron",
    day="1,16",
    hour=10,
    minute=0,
    id="scheduled_contribution",
)

# Reminder: 9am on 15th and last day of month
scheduler.add_job(
    contribution_reminder,
    "cron",
    day="15,last",
    hour=9,
    minute=0,
    id="contribution_reminder",
)

# Report: noon on 1st and 16th
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
        "Scheduler started — jobs: "
        "contribution@10:00 on 1st/16th, "
        "reminder@09:00 on 15th/last, "
        "report@12:00 on 1st/16th"
    )
    yield
    scheduler.shutdown()


# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────

app = FastAPI(lifespan=lifespan, title="DCA Dynamic Bot")
app.include_router(router)

# Inject scheduler into health endpoint via app state
app.state.scheduler = scheduler


# Override health to pass scheduler
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

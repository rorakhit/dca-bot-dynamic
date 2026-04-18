"""
config.py — All configuration constants, environment variables, and paths.
"""

import logging
import logging.handlers
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import resend
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# LOAD CREDENTIALS FROM .env
# ─────────────────────────────────────────────

load_dotenv(Path(__file__).parent / ".env")

ALPACA_API_KEY = os.environ["ALPACA_API_KEY"]
ALPACA_SECRET_KEY = os.environ["ALPACA_SECRET_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTIFY_EMAIL = os.environ["NOTIFY_EMAIL"]
resend.api_key = os.environ["RESEND_API_KEY"]

# ─────────────────────────────────────────────
# CONFIG (non-secret)
# ─────────────────────────────────────────────

SERVER_BASE_URL = os.environ.get(
    "SERVER_BASE_URL", "https://dca-bot-dynamic.up.railway.app"
)
EMAIL_FROM = os.environ.get("EMAIL_FROM", "DCA Dynamic <onboarding@resend.dev>")

# How much to deploy each contribution cycle
CONTRIBUTION_AMOUNT = 100.00

# Base target portfolio weights — must sum to 1.0
BASE_TARGET_ALLOCATION = {
    "VTI": 0.50,   # Total US market
    "VXUS": 0.35,  # International
    "AVUV": 0.10,  # US small-cap value (factor tilt)
    "BND": 0.05,   # US aggregate bonds
}

# Weight bounds for dynamic adjustment (AI can adjust within these ranges)
WEIGHT_BOUNDS = {
    "VTI":  (0.40, 0.60),
    "VXUS": (0.25, 0.45),
    "AVUV": (0.00, 0.20),
    "BND":  (0.00, 0.15),
}

# Hard safety rails — never touched by AI
MAX_SINGLE_ORDER_USD = 10_000
MIN_ORDER_USD = 1.00

ET = ZoneInfo("America/New_York")

BASE_DIR = Path(__file__).parent
AUDIT_LOG_PATH = BASE_DIR / "audit_log.jsonl"
PENDING_STORE_PATH = BASE_DIR / "pending_approvals.json"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────
# LOGGING — rotating file + console
# ─────────────────────────────────────────────

def _setup_logging() -> logging.Logger:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "dca_bot.log", maxBytes=1_000_000, backupCount=5
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    logger = logging.getLogger("dca_bot")
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


log = _setup_logging()

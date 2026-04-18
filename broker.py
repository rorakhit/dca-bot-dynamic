"""
broker.py — Alpaca client, portfolio state, order execution, market data.

⚠️ LIVE TRADING — real money. Orders only execute after email approval.
"""

from datetime import date, datetime, timedelta

import numpy as np
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import GetCalendarRequest, MarketOrderRequest

from config import (
    ALPACA_API_KEY,
    ALPACA_SECRET_KEY,
    BASE_TARGET_ALLOCATION,
    ET,
    MAX_SINGLE_ORDER_USD,
    MIN_ORDER_USD,
    log,
)

# ─────────────────────────────────────────────
# CLIENTS — paper=False (LIVE). Orders gated by email approval.
# ─────────────────────────────────────────────

broker = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=False)
data_client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

log.warning("⚠️ LIVE TRADING MODE — orders require email approval")


# ─────────────────────────────────────────────
# MARKET HOURS & HOLIDAY DETECTION
# ─────────────────────────────────────────────

def is_trading_day(check_date: date | None = None) -> bool:
    """
    Returns True if NYSE is open on check_date (defaults to today).
    Uses Alpaca's calendar API so holidays are always correct.
    Falls back to weekday check if the API call fails.
    """
    if check_date is None:
        check_date = datetime.now(ET).date()

    try:
        calendars = broker.get_calendar(
            GetCalendarRequest(start=check_date, end=check_date)
        )
        return len(calendars) > 0
    except Exception as exc:
        log.warning(f"Calendar API failed ({exc}) — falling back to weekday check")
        return check_date.weekday() < 5  # Mon-Fri


def is_market_open() -> bool:
    """
    Returns True if NYSE is currently open (trading day + within hours).
    9:30am-4:00pm ET, holidays excluded.
    """
    now = datetime.now(ET)
    if not is_trading_day(now.date()):
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now < market_close


def approval_deadline() -> datetime:
    """3:30pm ET today — 30 min before close, last sensible time to approve."""
    return datetime.now(ET).replace(hour=15, minute=30, second=0, microsecond=0)


# ─────────────────────────────────────────────
# PORTFOLIO STATE
# ─────────────────────────────────────────────

def get_portfolio_state(target_allocation: dict | None = None) -> dict:
    """
    Fetch current holdings and cash from Alpaca.
    Optionally accepts a custom target_allocation to compute drift against.
    """
    if target_allocation is None:
        target_allocation = BASE_TARGET_ALLOCATION

    account = broker.get_account()
    positions = broker.get_all_positions()

    total_value = float(account.portfolio_value)
    cash = float(account.cash)

    holdings = {}
    for pos in positions:
        holdings[pos.symbol] = {
            "market_value": float(pos.market_value),
            "weight": float(pos.market_value) / total_value if total_value > 0 else 0,
            "unrealized_pl": float(pos.unrealized_pl),
        }

    drift = {
        symbol: round(holdings.get(symbol, {}).get("weight", 0) - target, 4)
        for symbol, target in target_allocation.items()
    }

    return {
        "total_value": total_value,
        "cash_available": cash,
        "holdings": holdings,
        "target_allocation": target_allocation,
        "drift_from_target": drift,
    }


# ─────────────────────────────────────────────
# ORDER EXECUTION
# ─────────────────────────────────────────────

def execute_allocations(allocations: dict, dry_run: bool = False) -> list[dict]:
    """Place notional market orders. dry_run=True logs only, no orders sent."""
    receipts = []

    for symbol, dollar_amount in allocations.items():
        if dollar_amount < MIN_ORDER_USD:
            log.info(f"Skipping {symbol} — ${dollar_amount:.2f} below minimum")
            continue

        dollar_amount = min(dollar_amount, MAX_SINGLE_ORDER_USD)

        if dry_run:
            log.info(f"[DRY RUN] Would buy ${dollar_amount:.2f} of {symbol}")
            receipts.append({"symbol": symbol, "amount": dollar_amount, "status": "dry_run"})
        else:
            order = broker.submit_order(MarketOrderRequest(
                symbol=symbol,
                notional=round(dollar_amount, 2),
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            ))
            log.info(f"Order placed: ${dollar_amount:.2f} of {symbol} — {order.id}")
            receipts.append({
                "symbol": symbol,
                "amount": dollar_amount,
                "order_id": str(order.id),
                "status": str(order.status),
            })

    return receipts


# ─────────────────────────────────────────────
# MARKET DATA — 3-month daily bars + analytics
# ─────────────────────────────────────────────

def fetch_market_data(symbols: list[str], lookback_days: int = 90) -> dict:
    """
    Fetch 3-month daily bars for a list of symbols and compute analytics:
      - total_return_3m: total return over the period
      - annualized_volatility: annualized std dev of daily returns
      - sharpe_approx: approximate Sharpe ratio (no risk-free rate)
      - recent_20d_return: return over the most recent 20 trading days
      - prior_40d_return: return over the 40 days before the recent 20
      - momentum_signal: "positive" if recent > prior, "negative" otherwise
    """
    end_date = datetime.now(ET)
    start_date = end_date - timedelta(days=lookback_days + 10)  # buffer for weekends

    try:
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Day,
            start=start_date.replace(tzinfo=None),
            end=end_date.replace(tzinfo=None),
        )
        bars = data_client.get_stock_bars(request)
    except Exception as exc:
        log.error(f"Failed to fetch market data: {exc}")
        return {}

    results = {}
    for symbol in symbols:
        try:
            symbol_bars = bars[symbol]
            if len(symbol_bars) < 20:
                log.warning(f"Not enough bars for {symbol} ({len(symbol_bars)})")
                continue

            closes = np.array([float(bar.close) for bar in symbol_bars])
            daily_returns = np.diff(closes) / closes[:-1]

            total_return_3m = (closes[-1] / closes[0]) - 1.0
            annualized_vol = float(np.std(daily_returns) * np.sqrt(252))
            mean_daily = float(np.mean(daily_returns))
            sharpe_approx = (mean_daily * 252) / annualized_vol if annualized_vol > 0 else 0.0

            # Momentum: recent 20 days vs prior 40 days
            recent_20d = closes[-20:]
            recent_20d_return = (recent_20d[-1] / recent_20d[0]) - 1.0

            if len(closes) >= 60:
                prior_40d = closes[-60:-20]
                prior_40d_return = (prior_40d[-1] / prior_40d[0]) - 1.0
            else:
                prior_start = max(0, len(closes) - 60)
                prior_40d = closes[prior_start:-20]
                prior_40d_return = (prior_40d[-1] / prior_40d[0]) - 1.0 if len(prior_40d) > 1 else 0.0

            momentum_signal = "positive" if recent_20d_return > prior_40d_return else "negative"

            results[symbol] = {
                "total_return_3m": round(total_return_3m, 4),
                "annualized_volatility": round(annualized_vol, 4),
                "sharpe_approx": round(sharpe_approx, 2),
                "recent_20d_return": round(recent_20d_return, 4),
                "prior_40d_return": round(prior_40d_return, 4),
                "momentum_signal": momentum_signal,
                "last_close": round(float(closes[-1]), 2),
                "bars_count": len(symbol_bars),
            }
        except Exception as exc:
            log.error(f"Error computing stats for {symbol}: {exc}")

    return results

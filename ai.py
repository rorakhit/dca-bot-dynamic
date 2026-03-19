"""
ai.py — Claude AI dynamic allocation engine + fixed-strategy counterfactual.
"""

import json
import time

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    BASE_TARGET_ALLOCATION,
    MIN_ORDER_USD,
    WEIGHT_BOUNDS,
    log,
)

ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ─────────────────────────────────────────────
# DYNAMIC AI ALLOCATION
# ─────────────────────────────────────────────

def ask_ai_for_dynamic_allocation(
    portfolio: dict,
    new_cash: float,
    market_stats: dict,
    audit_history: list[dict],
) -> dict:
    """
    Ask Claude Haiku to:
      1. Adjust target weights within bounds based on market data
      2. Allocate the contribution using the adjusted targets

    Returns:
      {
        "adjusted_targets": {"VTI": 0.48, ...},
        "weight_reasoning": "...",
        "allocations": {"VTI": 48.00, ...},
        "allocation_reasoning": "..."
      }

    Includes retry logic for 529 (API overloaded).
    """
    # Build a summary of recent audit history for context
    history_summary = ""
    if audit_history:
        history_summary = "\n\nRecent portfolio history (newest first):\n"
        for entry in audit_history[:5]:
            ts = entry.get("timestamp", "?")[:10]
            evt = entry.get("event", "?")
            if evt == "portfolio_snapshot":
                tv = entry.get("total_value", 0)
                drift = entry.get("drift_from_target", {})
                history_summary += f"  {ts} snapshot: value=${tv:.2f}, drift={json.dumps(drift)}\n"
            elif evt == "dynamic_allocation_proposed":
                targets = entry.get("adjusted_targets", {})
                history_summary += f"  {ts} dynamic: targets={json.dumps(targets)}\n"

    prompt = f"""You are a portfolio manager running a dollar-cost averaging experiment with dynamic target adjustment.

A new cash contribution of ${new_cash:.2f} has arrived. You need to:
1. Review market conditions and adjust portfolio target weights (within strict bounds)
2. Allocate the cash contribution to bring the portfolio toward those adjusted targets

Current portfolio state:
{json.dumps(portfolio, indent=2)}

Base target allocation (starting point):
{json.dumps(BASE_TARGET_ALLOCATION, indent=2)}

Weight bounds (your adjusted targets MUST stay within these ranges):
{json.dumps({sym: {"min": lo, "max": hi} for sym, (lo, hi) in WEIGHT_BOUNDS.items()}, indent=2)}

Market data (3-month lookback):
{json.dumps(market_stats, indent=2)}
{history_summary}
Rules:
- Adjusted targets MUST sum to exactly 1.0
- Each weight MUST be within its min/max bounds
- Only allocate to symbols in: {list(BASE_TARGET_ALLOCATION.keys())}
- Allocations must sum to exactly ${new_cash:.2f}
- Minimum order size is ${MIN_ORDER_USD}
- Be conservative with adjustments — small tilts, not large swings
- Consider momentum, volatility, and valuation signals
- If market data is missing or unclear, stay close to base targets

Respond ONLY with valid JSON — no markdown, no code fences:
{{
  "adjusted_targets": {{"SYMBOL": weight, ...}},
  "weight_reasoning": "1-2 sentences on why you adjusted targets",
  "allocations": {{"SYMBOL": dollar_amount, ...}},
  "allocation_reasoning": "1-2 sentences on how you allocated the cash"
}}"""

    for attempt in range(3):
        try:
            response = ai_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            break
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt < 2:
                wait = 10 * (attempt + 1)
                log.warning(f"Anthropic overloaded — retrying in {wait}s")
                time.sleep(wait)
            else:
                raise

    raw = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    result = json.loads(raw.strip())
    log.info(f"AI weight reasoning: {result.get('weight_reasoning', '')}")
    log.info(f"AI allocation reasoning: {result.get('allocation_reasoning', '')}")

    # Validate and clamp weights
    result = _validate_dynamic_response(result, new_cash)

    return result


def _validate_dynamic_response(result: dict, new_cash: float) -> dict:
    """
    Clamp adjusted_targets to weight bounds, re-normalize to sum to 1.0.
    Also ensure allocations sum to new_cash.
    """
    adjusted = result.get("adjusted_targets", {})

    # Ensure all symbols are present
    for sym in BASE_TARGET_ALLOCATION:
        if sym not in adjusted:
            adjusted[sym] = BASE_TARGET_ALLOCATION[sym]

    # Clamp to bounds
    for sym, (lo, hi) in WEIGHT_BOUNDS.items():
        if sym in adjusted:
            adjusted[sym] = max(lo, min(hi, float(adjusted[sym])))

    # Re-normalize to sum to 1.0
    total = sum(adjusted.values())
    if total > 0 and abs(total - 1.0) > 0.001:
        for sym in adjusted:
            adjusted[sym] = adjusted[sym] / total

    # Round to 4 decimal places
    for sym in adjusted:
        adjusted[sym] = round(adjusted[sym], 4)

    # Fix tiny rounding errors: adjust largest weight
    total = sum(adjusted.values())
    if abs(total - 1.0) > 0.0001:
        largest = max(adjusted, key=adjusted.get)
        adjusted[largest] = round(adjusted[largest] + (1.0 - total), 4)

    result["adjusted_targets"] = adjusted

    # Validate allocations sum to new_cash
    allocations = result.get("allocations", {})
    alloc_total = sum(float(v) for v in allocations.values())
    if abs(alloc_total - new_cash) > 0.01 and alloc_total > 0:
        # Scale allocations to match new_cash
        scale = new_cash / alloc_total
        for sym in allocations:
            allocations[sym] = round(float(allocations[sym]) * scale, 2)
    result["allocations"] = allocations

    return result


# ─────────────────────────────────────────────
# FIXED STRATEGY COUNTERFACTUAL (A/B baseline)
# ─────────────────────────────────────────────

def compute_fixed_strategy_allocation(portfolio: dict, new_cash: float) -> dict:
    """
    Deterministic fixed-target allocation for A/B counterfactual comparison.
    Always uses BASE_TARGET_ALLOCATION. Allocates to minimize drift.
    """
    total_value = portfolio.get("total_value", 0)
    holdings = portfolio.get("holdings", {})

    # After contribution, what should each asset be worth?
    new_total = total_value + new_cash
    allocations = {}

    for symbol, target in BASE_TARGET_ALLOCATION.items():
        current_value = holdings.get(symbol, {}).get("market_value", 0)
        ideal_value = new_total * target
        deficit = ideal_value - current_value

        # Only buy, never sell in DCA
        allocations[symbol] = max(0, deficit)

    # Scale allocations to exactly match new_cash
    alloc_total = sum(allocations.values())
    if alloc_total > 0:
        scale = new_cash / alloc_total
        for sym in allocations:
            allocations[sym] = round(allocations[sym] * scale, 2)
    else:
        # Fallback: allocate proportionally to targets
        for sym, target in BASE_TARGET_ALLOCATION.items():
            allocations[sym] = round(new_cash * target, 2)

    # Fix rounding to ensure exact sum
    diff = new_cash - sum(allocations.values())
    if abs(diff) > 0.001:
        largest = max(allocations, key=allocations.get)
        allocations[largest] = round(allocations[largest] + diff, 2)

    return {
        "strategy": "fixed",
        "target_allocation": BASE_TARGET_ALLOCATION,
        "allocations": allocations,
        "reasoning": f"Fixed DCA: allocate ${new_cash:.2f} to minimize drift from static targets "
                     f"(VTI {int(BASE_TARGET_ALLOCATION['VTI']*100)}%, "
                     f"VXUS {int(BASE_TARGET_ALLOCATION['VXUS']*100)}%, "
                     f"AVUV {int(BASE_TARGET_ALLOCATION['AVUV']*100)}%, "
                     f"BND {int(BASE_TARGET_ALLOCATION['BND']*100)}%).",
    }

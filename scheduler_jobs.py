"""
scheduler_jobs.py — All scheduled jobs for the DCA Dynamic bot.

Jobs:
  - scheduled_contribution: 10am ET on 1st/16th — fetch data, compute both strategies, send approval email
  - expire_pending: 3:30pm ET on 1st/16th — drop any approvals the user didn't act on
  - contribution_reminder: 9am on 15th/last — email reminder to fund account
  - dca_contribution_report: noon on 1st/16th — email report with both strategies

⚠️ LIVE TRADING — orders only execute after the user clicks Approve in the email.
"""

import base64
import io
import json
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

from ai import (
    ask_ai_for_dynamic_allocation,
    compute_fixed_strategy_allocation,
)
from approval import (
    _save_pending,
    create_pending_approval,
    pending_approvals,
)
from audit import get_audit_history_summary, read_audit_log, write_audit_entry
from broker import (
    broker,
    fetch_market_data,
    get_portfolio_state,
    is_trading_day,
)
from config import (
    BASE_TARGET_ALLOCATION,
    CONTRIBUTION_AMOUNT,
    ET,
    log,
)
from email_service import _send_email, send_error_email


# ─────────────────────────────────────────────
# SCHEDULED CONTRIBUTION (10am ET, 1st & 16th)
# ─────────────────────────────────────────────

async def scheduled_contribution():
    """
    Full contribution cycle (LIVE TRADING):
      1. Check if trading day
      2. Check cash balance >= CONTRIBUTION_AMOUNT
      3. Get portfolio state
      4. Fetch market data
      5. Get audit history
      6. Compute fixed counterfactual, log it
      7. Ask AI for dynamic allocation, validate, log it
      8. Send approval email — orders stay pending until user clicks Approve
    """
    today = datetime.now(ET).date()

    if not is_trading_day(today):
        log.info(f"Skipping contribution — {today} is a holiday or weekend")
        return

    try:
        account = broker.get_account()
        available_cash = float(account.cash)

        if available_cash < CONTRIBUTION_AMOUNT:
            log.info(f"Insufficient cash (${available_cash:.2f}) — skipping cycle")
            send_error_email(
                "scheduled_contribution",
                RuntimeError(f"Insufficient cash: ${available_cash:.2f} < ${CONTRIBUTION_AMOUNT:.2f}"),
            )
            return

        # Step 3: Portfolio state
        portfolio = get_portfolio_state()
        write_audit_entry("portfolio_snapshot", portfolio)

        # Step 4: Market data
        symbols = list(BASE_TARGET_ALLOCATION.keys())
        market_stats = fetch_market_data(symbols)
        write_audit_entry("market_data_fetched", {"stats": market_stats})

        # Step 5: Audit history for AI context
        audit_history = get_audit_history_summary(max_entries=10)

        # Step 6: Fixed counterfactual (A/B baseline)
        fixed_result = compute_fixed_strategy_allocation(portfolio, CONTRIBUTION_AMOUNT)
        write_audit_entry("fixed_counterfactual_logged", {
            "allocations": fixed_result["allocations"],
            "reasoning": fixed_result["reasoning"],
            "target_allocation": fixed_result["target_allocation"],
            "new_cash": CONTRIBUTION_AMOUNT,
        })
        log.info(f"Fixed strategy counterfactual: {fixed_result['allocations']}")

        # Step 7: Dynamic AI allocation
        dynamic_result = ask_ai_for_dynamic_allocation(
            portfolio, CONTRIBUTION_AMOUNT, market_stats, audit_history
        )
        write_audit_entry("dynamic_allocation_proposed", {
            "adjusted_targets": dynamic_result["adjusted_targets"],
            "weight_reasoning": dynamic_result["weight_reasoning"],
            "allocations": dynamic_result["allocations"],
            "allocation_reasoning": dynamic_result["allocation_reasoning"],
            "new_cash": CONTRIBUTION_AMOUNT,
        })
        log.info(f"Dynamic strategy: targets={dynamic_result['adjusted_targets']}, "
                 f"allocations={dynamic_result['allocations']}")

        # Step 8: Send approval email — nothing executes until user clicks Approve
        create_pending_approval(
            allocations=dynamic_result["allocations"],
            allocation_reasoning=dynamic_result["allocation_reasoning"],
            adjusted_targets=dynamic_result["adjusted_targets"],
            weight_reasoning=dynamic_result["weight_reasoning"],
            new_cash=CONTRIBUTION_AMOUNT,
        )
        log.info("Approval email sent — awaiting user click to execute orders")

    except Exception as exc:
        log.exception(f"scheduled_contribution failed: {exc}")
        write_audit_entry("contribution_error", {"error": str(exc), "new_cash": CONTRIBUTION_AMOUNT})
        send_error_email(f"scheduled_contribution(${CONTRIBUTION_AMOUNT:.2f})", exc)


# ─────────────────────────────────────────────
# EXPIRE PENDING APPROVALS (3:30pm ET, 1st & 16th)
# ─────────────────────────────────────────────

async def expire_pending():
    """Clean up any tokens the user didn't act on before 3:30pm ET."""
    expired = [
        t for t, v in pending_approvals.items()
        if datetime.now(ET) > datetime.fromisoformat(v["expires_at"])
    ]
    for token in expired:
        data = pending_approvals.pop(token)
        write_audit_entry("approval_expired", {
            "token_prefix": token[:8],
            "allocations": data["allocations"],
            "adjusted_targets": data.get("adjusted_targets", {}),
        })
        log.info(f"Approval expired — token {token[:8]}…")

    if expired:
        _save_pending(pending_approvals)


# ─────────────────────────────────────────────
# CONTRIBUTION REMINDER (9am, 15th & last day)
# ─────────────────────────────────────────────

def contribution_reminder():
    """Remind to fund Alpaca on the 15th and last day of the month."""
    today = datetime.now(ET).strftime("%B %d")
    html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,sans-serif;padding:24px;color:#111827">
  <div style="max-width:520px;background:#eff6ff;border:1px solid #bfdbfe;
              border-radius:12px;padding:24px">
    <h2 style="color:#2563eb;margin:0 0 12px">💰 DCA Dynamic Reminder — {today}</h2>
    <p style="margin:0 0 8px">
      Time to transfer <strong>${CONTRIBUTION_AMOUNT:.0f}</strong> into your Alpaca
      live account so the dynamic allocation bot can propose a buy on the next
      contribution day (1st or 16th).
    </p>
    <p style="font-size:13px;color:#6b7280;margin:12px 0 0">
      💵 Live trading — you'll get an approve/deny email before any orders execute.
    </p>
  </div>
</body></html>"""
    _send_email(f"💰 DCA Dynamic — Fund account (${CONTRIBUTION_AMOUNT:.0f})", html)
    log.info("Contribution reminder email sent")


# ─────────────────────────────────────────────
# CONTRIBUTION REPORT (noon, 1st & 16th)
# ─────────────────────────────────────────────

def dca_contribution_report():
    """Generate and email a portfolio report with both dynamic and fixed strategy results."""
    account = broker.get_account()
    positions = broker.get_all_positions()

    total = float(account.portfolio_value)
    cash = float(account.cash)

    holdings = {}
    for p in positions:
        holdings[p.symbol] = {
            "market_value": float(p.market_value),
            "weight": float(p.market_value) / total if total > 0 else 0,
            "unrealized_pl": float(p.unrealized_pl),
        }

    symbols = list(BASE_TARGET_ALLOCATION.keys())
    colors = ["#4f46e5", "#06b6d4", "#10b981", "#f59e0b"]
    drift = {s: round(holdings.get(s, {}).get("weight", 0) - t, 4) for s, t in BASE_TARGET_ALLOCATION.items()}
    total_pl = sum(h["unrealized_pl"] for h in holdings.values())

    def fig_to_b64(fig):
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=150, facecolor="white")
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()

    # Chart 1: Side-by-side donuts
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5))
    fig.patch.set_facecolor("white")
    current_weights = [holdings.get(s, {}).get("weight", 0) for s in symbols]
    target_weights = [BASE_TARGET_ALLOCATION[s] for s in symbols]

    def donut(ax, values, title, note=None):
        display = values if any(v > 0 for v in values) else target_weights
        wedges, texts, autotexts = ax.pie(
            display, labels=symbols, colors=colors, autopct="%1.0f%%",
            startangle=90, pctdistance=0.75,
            wedgeprops=dict(width=0.5, edgecolor="white", linewidth=2),
        )
        for t in texts:
            t.set_fontsize(11)
        for at in autotexts:
            at.set_fontsize(9)
            at.set_color("white")
            at.set_fontweight("bold")
        ax.set_title(title, fontsize=13, fontweight="bold", pad=15)
        if note:
            ax.text(0, -1.35, note, ha="center", fontsize=9, color="#9ca3af", style="italic")

    note = "No positions yet" if not any(v > 0 for v in current_weights) else None
    donut(ax1, current_weights, "Current Allocation", note)
    donut(ax2, target_weights, "Base Target Allocation")
    chart1 = fig_to_b64(fig)
    plt.close(fig)

    # Chart 2: Drift bar chart
    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor("white")
    drift_vals = [drift[s] * 100 for s in symbols]
    bar_colors = ["#ef4444" if d > 0.5 else "#3b82f6" if d < -0.5 else "#10b981" for d in drift_vals]
    bars = ax.barh(symbols, drift_vals, color=bar_colors, height=0.5, edgecolor="white")
    ax.axvline(0, color="#6b7280", linewidth=1.5, linestyle="--")
    ax.set_xlabel("Drift from Target (% points)", fontsize=11)
    ax.set_title("Portfolio Drift from Base Target", fontsize=13, fontweight="bold")
    ax.set_facecolor("#f9fafb")
    for bar, val in zip(bars, drift_vals):
        ha = "left" if val >= 0 else "right"
        offset = 0.3 if val >= 0 else -0.3
        ax.text(val + offset, bar.get_y() + bar.get_height() / 2,
                f"{val:+.1f}%", va="center", ha=ha, fontsize=10, fontweight="bold")
    legend = [mpatches.Patch(color="#ef4444", label="Overweight"),
              mpatches.Patch(color="#3b82f6", label="Underweight"),
              mpatches.Patch(color="#10b981", label="On target")]
    ax.legend(handles=legend, loc="lower right", fontsize=9)
    plt.tight_layout()
    chart2 = fig_to_b64(fig)
    plt.close(fig)

    # Read latest proposals from audit log
    entries = read_audit_log()  # newest first

    dynamic_reasoning = "No dynamic proposal found for this cycle."
    dynamic_allocations = {}
    dynamic_targets = {}
    for e in entries:
        if e.get("event") == "dynamic_allocation_proposed":
            dynamic_reasoning = e.get("allocation_reasoning", "")
            dynamic_allocations = e.get("allocations", {})
            dynamic_targets = e.get("adjusted_targets", {})
            break

    fixed_reasoning = "No fixed counterfactual found for this cycle."
    fixed_allocations = {}
    for e in entries:
        if e.get("event") == "fixed_counterfactual_logged":
            fixed_reasoning = e.get("reasoning", "")
            fixed_allocations = e.get("allocations", {})
            break

    # Build HTML email
    date_str = datetime.now(ET).strftime("%B %-d, %Y")
    pl_color = "#10b981" if total_pl >= 0 else "#ef4444"
    pl_sign = "+" if total_pl >= 0 else ""

    holdings_rows = ""
    for symbol in symbols:
        h = holdings.get(symbol, {})
        mv = h.get("market_value", 0)
        w = h.get("weight", 0) * 100
        upl = h.get("unrealized_pl", 0)
        d = drift[symbol] * 100
        pill = "red" if d > 0.5 else ("blue" if d < -0.5 else "green")
        upl_color = "#10b981" if upl >= 0 else "#ef4444"
        holdings_rows += f"""<tr>
          <td><strong>{symbol}</strong></td><td>${mv:,.2f}</td><td>{w:.1f}%</td>
          <td>{int(BASE_TARGET_ALLOCATION[symbol]*100)}%</td>
          <td><span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600;
            {'background:#fee2e2;color:#991b1b' if pill == 'red' else 'background:#dbeafe;color:#1e40af' if pill == 'blue' else 'background:#d1fae5;color:#065f46'}">{d:+.1f}%</span></td>
          <td style="color:{upl_color}">${upl:+,.2f}</td></tr>"""

    dynamic_alloc_rows = ""
    for sym, amt in dynamic_allocations.items():
        target_pct = dynamic_targets.get(sym, BASE_TARGET_ALLOCATION.get(sym, 0))
        dynamic_alloc_rows += f'<tr><td><strong>{sym}</strong></td><td>${float(amt):.2f}</td><td>{target_pct*100:.1f}%</td></tr>'

    fixed_alloc_rows = ""
    for sym, amt in fixed_allocations.items():
        fixed_alloc_rows += f'<tr><td><strong>{sym}</strong></td><td>${float(amt):.2f}</td></tr>'

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f3f4f6;margin:0;padding:20px;color:#111827}}
  .wrap{{max-width:680px;margin:0 auto}}
  .card{{background:white;border-radius:12px;padding:24px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.08)}}
  .header{{background:linear-gradient(135deg,#f97316,#7c3aed);color:white;border-radius:12px;padding:28px;margin-bottom:16px}}
  .header h1{{margin:0 0 4px;font-size:22px;font-weight:700}}
  .header p{{margin:0;opacity:.85;font-size:14px}}
  .stat-row{{display:flex;gap:12px}}
  .stat{{flex:1;background:#f9fafb;border-radius:8px;padding:16px;text-align:center}}
  .stat .value{{font-size:20px;font-weight:700;color:#111827}}
  .stat .label{{font-size:12px;color:#6b7280;margin-top:4px}}
  h2{{margin:0 0 16px;font-size:16px;color:#111827}}
  table{{width:100%;border-collapse:collapse;font-size:14px}}
  th{{background:#f9fafb;padding:10px 12px;text-align:left;color:#6b7280;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.05em}}
  td{{padding:10px 12px;border-bottom:1px solid #f3f4f6}}
  tr:last-child td{{border-bottom:none}}
  .ai-box{{background:#f5f3ff;border-left:4px solid #7c3aed;padding:16px;border-radius:0 8px 8px 0;font-size:14px;color:#374151;line-height:1.6;margin-bottom:16px}}
  .fixed-box{{background:#fff7ed;border-left:4px solid #f97316;padding:16px;border-radius:0 8px 8px 0;font-size:14px;color:#374151;line-height:1.6;margin-bottom:16px}}
  .footer{{text-align:center;font-size:12px;color:#9ca3af;margin-top:8px;padding-bottom:20px}}
  img{{max-width:100%;border-radius:8px;display:block}}
  .badge{{display:inline-block;padding:3px 10px;border-radius:99px;font-size:11px;font-weight:600}}
  .badge-live{{background:#dcfce7;color:#166534}}
  .badge-dynamic{{background:#ede9fe;color:#5b21b6}}
</style></head>
<body>
<div class="wrap">
  <div class="header">
    <h1>📊 DCA Dynamic Report</h1>
    <p>{date_str} &nbsp;·&nbsp; <span class="badge badge-live">Live</span> <span class="badge badge-dynamic">Dynamic</span></p>
  </div>
  <div class="card">
    <div class="stat-row">
      <div class="stat"><div class="value">${total:,.2f}</div><div class="label">Portfolio Value</div></div>
      <div class="stat"><div class="value">${cash:,.2f}</div><div class="label">Cash Available</div></div>
      <div class="stat"><div class="value" style="color:{pl_color}">{pl_sign}${total_pl:,.2f}</div><div class="label">Unrealized P&amp;L</div></div>
    </div>
  </div>
  <div class="card">
    <h2>Allocation Charts</h2>
    <img src="data:image/png;base64,{chart1}" alt="Allocation donut charts"/>
    <img src="data:image/png;base64,{chart2}" alt="Drift chart" style="margin-top:12px"/>
  </div>
  <div class="card">
    <h2>Holdings</h2>
    <table>
      <tr><th>Symbol</th><th>Value</th><th>Current</th><th>Target</th><th>Drift</th><th>P&amp;L</th></tr>
      {holdings_rows}
    </table>
  </div>
  <div class="card">
    <h2>🤖 Dynamic AI Allocation (Proposed — pending approval)</h2>
    <div class="ai-box">{dynamic_reasoning}</div>
    <table>
      <tr><th>Symbol</th><th>Allocated</th><th>Adj. Target</th></tr>
      {dynamic_alloc_rows}
    </table>
  </div>
  <div class="card">
    <h2>📊 Fixed Strategy Counterfactual</h2>
    <div class="fixed-box">{fixed_reasoning}</div>
    <table>
      <tr><th>Symbol</th><th>Would Have Allocated</th></tr>
      {fixed_alloc_rows}
    </table>
  </div>
  <div class="footer">DCA Dynamic &nbsp;·&nbsp; Live Trading &nbsp;·&nbsp; Runs 1st &amp; 16th</div>
</div>
</body></html>"""

    _send_email(f"📊 DCA Dynamic Report — {date_str}", html)
    log.info("DCA contribution report email sent")

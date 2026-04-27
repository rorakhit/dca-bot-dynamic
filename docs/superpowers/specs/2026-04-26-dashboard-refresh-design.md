# Dashboard Refresh — Design Spec
**Date:** 2026-04-26
**Status:** Approved

## Overview

Restyle both dashboard templates (`LANDING_HTML` and `DASHBOARD_HTML` in `dashboard.py`) to reflect the bot's level-up from scheduled DCA to Plaid-powered paycheck-triggered automated contributions. The refresh is a pure frontend pass — no new API endpoints, no backend changes, no new data sources beyond what's already available.

Design direction: **Wealth OS × Dark Horizon hybrid**. Professional structure with a warm amber/gold palette and Claude's reasoning promoted to a first-class panel.

---

## Visual Identity

**Palette**

| Token | Value | Usage |
|---|---|---|
| Amber primary | `#f59e0b` | Accent bars, active borders, chart gradient, pills |
| Amber secondary | `#d97706` | Bar gradient end, icon gradient |
| Amber deep | `#b45309` | Icon gradient, dark borders |
| Hero text | `#fef3c7` | Portfolio value, ticker labels |
| Body text | `#e2e8f0` | Unchanged |
| Muted | `#78716c` | Card titles, subtitles |
| Subtle muted | `#44403c` | Faintest text |
| Background | `#0a0805` | Body — slightly warmer than current `#0c0a1a` |
| Card background | `rgba(255,255,255,0.02)` | Neutral cards |
| Amber card background | `rgba(245,158,11,0.06)` | Hero portfolio card, Claude callout card |
| Green card background | `rgba(52,211,153,0.05)` | P&L positive card |

The purple/orange palette (`#818cf8`, `#a855f7`, `#f97316`) is retired. Amber replaces purple as the primary accent throughout.

**Brand icon**

Replace `⚡` with `◈`. Icon gradient: `linear-gradient(135deg, #f59e0b, #b45309)`.

**Typography**

No change — Inter stays. `🧪📈` emoji removed from brand name.

---

## Nav

- Brand name: `DCA DYNAMIC` (all-caps, `font-weight: 700`, `letter-spacing: 0.04em`)
- Brand subtitle below name: `Automated wealth engine` (muted `#78716c`, `font-size: 9px`)
- Status pills: amber styling for **Live** and **Plaid** pills (amber background + border); green for market status; muted for next-contribution date
- Pill order: `● Market open/closed` · `Live` · `Plaid` · `Next: <date>`
- Refresh button: unchanged behaviour, updated colour to match new neutral dark

---

## Hero Stats (4-card row)

Layout unchanged (4-column grid on desktop, 2×2 on mobile).

| Card | Change |
|---|---|
| Portfolio value | Amber glow: `rgba(245,158,11,0.06)` bg + `rgba(245,158,11,0.15)` border. Value in `#fef3c7`. |
| Invested | Neutral card. No change to layout. |
| Cash available | Neutral card. No change to layout. |
| Unrealised P&L | Green glow when positive. Add all-time percentage gain as `stat-sub` (e.g. `+8.2% all time`). Percentage calculated as `pl / (total_value - pl) * 100`. |

---

## New: Claude Reasoning Callout Panel

A new card inserted between the hero stats row and the charts row. Desktop: `2fr` of a `2fr 1fr` grid alongside the Plaid status panel. Mobile: full width, stacked above Plaid panel.

**Content:** The `allocation_reasoning` (or `reasoning`) field from the most recent `dynamic_allocation_proposed` audit entry, displayed as a styled italic blockquote. Below it: the date and `Dynamic strategy` label.

**Styling:**
- Background: `rgba(245,158,11,0.07)`, border: `rgba(245,158,11,0.18)`
- Card title: `Claude's last allocation rationale` (amber muted `#92400e`)
- Reasoning text: `#fcd34d`, italic, `font-size: 13px`, `line-height: 1.6`
- Footer: date + "Dynamic strategy" in `#78716c`

If no `dynamic_allocation_proposed` entry exists yet, show a placeholder: `"No allocation reasoning yet — appears after the first contribution cycle."` in muted style.

---

## New: Plaid Status Panel

Second panel in the `2fr 1fr` grid alongside the Claude callout. Desktop: `1fr`. Mobile: full width, below Claude callout.

**Content** (read from `/health` endpoint):
- Bank name + masked account number (e.g. `Chase ••4521`) when connected
- Status indicator dot + label:
  - Green dot + `<Bank> ••<mask> connected`
  - Amber dot + `Watching for deposit` (always shown when connected, below bank line)
  - Red dot + `No account linked` (when not connected)
- Next expected payday: formatted date from `health.next_contribution`

**Styling:** Neutral card. Bank name in `#fef3c7`. Status labels in `#94a3b8`. Next payday value in `#fef3c7`.

### Backend changes required

**`plaid_client.py` — new function `get_account_info(access_token)`:**
- Calls `/item/get` to retrieve `institution_id`
- Calls `/institutions/get_by_id` (with `country_codes=["US"]`) to retrieve `institution.name`
- Calls `/accounts/get` to retrieve the first account's `mask` (last 4 digits)
- Returns `{"institution_name": str, "account_mask": str}`

**`plaid_store.py` — two new fields:**
- Add `institution_name: str | None` (default `None`) to the store schema
- Add `account_mask: str | None` (default `None`) to the store schema
- Add `set_account_info(institution_name, account_mask)` setter
- Add `get_account_info()` getter returning `(institution_name, account_mask)`

**`plaid_routes.py` — call after token exchange:**
- After `set_access_token(access_token)` in `plaid_callback`, call `get_account_info(access_token)` from `plaid_client` and persist with `set_account_info(...)` from `plaid_store`
- Wrap in try/except — if it fails, log a warning and continue (non-fatal; the access token is already stored)

**`routes.py` — surface in `/health`:**
- Import `get_account_info` from `plaid_store`
- Add to health response: `"plaid_institution": institution_name or None`, `"plaid_account_mask": account_mask or None`

---

## Charts

**Portfolio value chart:** Gradient fill switches from indigo (`rgba(129,140,248,…)`) to amber (`rgba(245,158,11,0.25)` → `rgba(245,158,11,0)`). Line colour: `#f59e0b`.

**Allocation drift chart:** Line colours update to the new per-symbol palette:

| Symbol | New colour |
|---|---|
| VTI | `#f59e0b` (amber) |
| VXUS | `#34d399` (green, unchanged) |
| AVUV | `#60a5fa` (blue) |
| BND | `#f87171` (red, unchanged) |

**Target weight history chart:** Same symbol colour update as drift chart.

---

## Allocation Rows

Allocation bar colours update to match the new symbol palette (amber for VTI, etc.). Drift badge styling unchanged.

---

## Contribution History & Event Log

No structural changes. Text and colours update to match new palette — `#a78bfa` purple highlights on allocation amounts replaced with `#f59e0b` amber.

---

## Mobile Dashboard (`DASHBOARD_HTML`)

All palette and identity changes apply. Structural additions:

- Claude reasoning callout: full-width card inserted after the portfolio value card, before the allocation card.
- Plaid status panel: full-width card below the Claude callout.
- Both new cards use the same styling as desktop.
- Nav becomes a `<header>` with the new `◈` icon + "DCA DYNAMIC" text + "Automated wealth engine" subtitle. No room for subtitle on very small screens — hide below 360px.

---

## What Does Not Change

- All JS data-fetching logic (`loadAll`, `fetch('/portfolio')`, `fetch('/health')`, `fetch('/audit')`)
- Chart.js configuration (options, scales, responsive behaviour)
- Allocation rendering logic
- Contribution history and event log rendering logic
- `COLORS` constant keys (symbol → colour mapping updated but constant structure unchanged)
- `/portfolio`, `/audit` API contracts (`/health` gains two new optional fields)
- Auto-refresh interval (60s)
- `dashboard.py` file structure — both templates remain inline string constants

---

## Scope

Files touched:

| File | Change |
|---|---|
| `dashboard.py` | Full restyling of both templates + two new panels |
| `plaid_client.py` | New `get_account_info(access_token)` function |
| `plaid_store.py` | Two new fields + getter/setter for institution/mask |
| `plaid_routes.py` | Call `get_account_info` + `set_account_info` after token exchange |
| `routes.py` | Add `plaid_institution` + `plaid_account_mask` to `/health` response |

No changes to `app.py`, `scheduler_jobs.py`, `ai.py`, `broker.py`, `approval.py`, or `audit.py`.

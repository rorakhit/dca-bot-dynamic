# Plaid Paycheck-Triggered DCA Contributions

**Date:** 2026-04-26  
**Project:** dca-bot-dynamic  
**Status:** Approved

---

## Overview

Replace the fixed 1st/16th contribution schedule with a Plaid webhook-driven pipeline that detects the user's paycheck landing in their bank account, automatically pulls $100 into Alpaca via ACH, and fires the DCA contribution cycle. The approval gate (email → click approve → orders execute) is preserved.

---

## Architecture

```
Plaid webhook (TRANSACTIONS / SYNC_UPDATES_AVAILABLE)
  → POST /plaid/webhook
  → verify Plaid JWT signature
  → fetch new transactions via Plaid sync API
  → paycheck detection (employer keyword + min amount)
  → deduplicate (skip if transaction_id already processed)
  → send "paycheck detected" email with Cancel token
  → if not cancelled within grace period:
      → POST /v1/transfers (Alpaca ACH pull, $100)
      → poll GET /account until cash += $100 (up to 10 min, 30s intervals)
      → call scheduled_contribution() directly
      → approval email sent → user clicks Approve → orders execute
```

---

## New Components

### `plaid_client.py`
Thin wrapper around the `plaid-python` SDK. Responsibilities:
- Create `link_token` (for one-time Link flow setup)
- Exchange `public_token` → `access_token`
- Sync transactions (fetch new/modified since last cursor)
- Verify webhook JWT signatures
- Fetch webhook verification key

### `plaid_routes.py`
New FastAPI router mounted at `/plaid`. Routes:
- `GET /plaid/link` — serves the one-time Plaid Link setup page (HTML + Plaid Link JS)
- `POST /plaid/callback` — receives `public_token` from Link widget, exchanges for `access_token`, stores in env
- `POST /plaid/webhook` — receives Plaid transaction webhooks (main pipeline entry point)
- `GET /plaid/cancel/{token}` — cancel a detected paycheck cycle before ACH initiates
- `GET /plaid/retry/{token}` — retry ACH poll + DCA trigger after a timeout
- `GET /plaid/skip/{token}` — skip a failed cycle (audit logs it, no orders)
- `GET /plaid/force/{token}` — cancel stale pending approval and run a fresh cycle
- `GET /plaid/trigger` — manual trigger (token-protected, linked from dashboard)

### `plaid_store.py`
Small JSON-backed store (same pattern as `pending_approvals.json`) for:
- Last Plaid transaction sync cursor
- Set of processed paycheck `transaction_id`s (deduplication)
- Active action tokens (cancel, retry, skip, force) with expiry timestamps

---

## Configuration

### New env vars (Railway)
| Variable | Description |
|---|---|
| `PLAID_CLIENT_ID` | From Plaid developer dashboard |
| `PLAID_SECRET` | From Plaid developer dashboard |
| `PLAID_ENV` | `production` |
| `PLAID_ACCESS_TOKEN` | Written by bot after Link flow completes |
| `PLAID_MANUAL_TRIGGER_TOKEN` | Static secret token for `/plaid/trigger` |

### New config constants (`config.py`)
| Constant | Default | Description |
|---|---|---|
| `PAYCHECK_EMPLOYER_KEYWORD` | `"DATALIGN ADVISOR"` | Case-insensitive substring match on transaction name |
| `PAYCHECK_MIN_AMOUNT` | `575.00` | Minimum deposit amount to qualify as a paycheck |
| `ACH_POLL_INTERVAL_SECONDS` | `30` | How often to poll Alpaca cash balance |
| `ACH_POLL_MAX_MINUTES` | `10` | Timeout before sending failure email |
| `PAYCHECK_CANCEL_GRACE_SECONDS` | `300` | Window after detection email to cancel before ACH initiates (5 min) |

---

## One-Time Setup Flow

1. Add Plaid env vars to Railway (`PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV=production`)
2. Visit `https://dca-bot-dynamic.up.railway.app/plaid/link` in a browser
3. Complete the Plaid Link widget (log into your bank — Plaid handles credentials, bot never sees them)
4. Bot receives `public_token`, exchanges for `access_token`, stores as `PLAID_ACCESS_TOKEN` in Railway env
5. Webhook URL (`https://dca-bot-dynamic.up.railway.app/plaid/webhook`) is registered with Plaid during `link_token` creation — no separate Plaid dashboard config needed

---

## Paycheck Detection Logic

A transaction qualifies as a paycheck if all three conditions are true:
1. `transaction_type` is a credit (money incoming, not outgoing)
2. `amount` ≥ `PAYCHECK_MIN_AMOUNT` (575.00)
3. `name` contains `PAYCHECK_EMPLOYER_KEYWORD` (case-insensitive, e.g. `"DATALIGN ADVISOR"`)

If a matching transaction's `transaction_id` is already in the processed set, it is silently skipped.

---

## Email Actions

### Paycheck Detected Email (new)
Fires immediately when a paycheck is confirmed. Gives a 5-minute cancel window before ACH initiates.

**Actions:**
- `Cancel this cycle` → `GET /plaid/cancel/{token}` — aborts before any money moves

### ACH Timeout Email
Fires if Alpaca cash doesn't increase by $100 within 10 minutes.

**Actions:**
- `Retry` → `GET /plaid/retry/{token}` — re-polls cash balance and fires DCA cycle if funds now available
- `Skip this cycle` → `GET /plaid/skip/{token}` — records in audit log, no orders placed

### Pending Conflict Email
Fires if a paycheck is detected while a previous approval is still pending.

**Actions:**
- `Cancel old approval & run new cycle` → `GET /plaid/force/{token}` — expires stale token, kicks off fresh cycle
- `Keep old approval` — no action needed (informational link only, no-op)

### Manual Trigger
Available from the dashboard at `GET /plaid/trigger?token={PLAID_MANUAL_TRIGGER_TOKEN}`. Kicks off the full paycheck pipeline (ACH pull → DCA cycle) without waiting for Plaid. Useful for testing or if Plaid misses a deposit.

---

## Scheduler Changes

### Removed jobs
| Job | Reason |
|---|---|
| `scheduled_contribution` (1st/16th 10am) | Replaced by Plaid webhook trigger |
| `contribution_reminder` (15th/last day) | No longer needed — funding is automated |

### Kept jobs
| Job | Change | Reason |
|---|---|---|
| `dca_contribution_report` (noon 1st/16th) | None | Still useful for portfolio snapshot |
| `expire_pending` (1st/16th 3:30pm) | Rescheduled to daily 5pm ET | Still needed for order approve/deny tokens; decoupled from fixed dates |

### New jobs
| Job | Schedule | Purpose |
|---|---|---|
| `expire_plaid_tokens` | Daily 5pm ET | Clean up stale cancel/retry/skip/force tokens from Plaid pipeline |

---

## ACH Transfer Details

- Get existing ACH relationship: `GET /v1/ach/relationships` → use first active relationship ID
- Initiate pull: `POST /v1/transfers` with `direction=INCOMING`, `amount=100.00`, relationship ID
- Alpaca provides instant buying power up to $1,000 for linked accounts — $100 should be available within seconds
- Poll `GET /account` every 30s for up to 10 minutes; abort with error email if cash doesn't increase

---

## Deduplication & Safety

- Each processed paycheck `transaction_id` is stored in `plaid_store.json` — same transaction never triggers twice
- Cancel tokens expire after 5 minutes (grace period window)
- Retry/skip tokens expire after 24 hours
- Force tokens expire after 24 hours
- Manual trigger requires static secret token — not guessable from the URL alone
- Plaid webhook JWT verification is mandatory — unsigned requests are rejected with 401
- `MAX_SINGLE_ORDER_USD` and `MIN_ORDER_USD` safety rails in `config.py` are unchanged

---

## New Dependencies

```
plaid-python
```

---

## Files Modified

| File | Change |
|---|---|
| `requirements.txt` | Add `plaid-python` |
| `config.py` | Add Plaid env vars + new constants |
| `app.py` | Mount `plaid_routes` router; remove 3 scheduler jobs; add `expire_plaid_tokens` job |
| `scheduler_jobs.py` | Remove `scheduled_contribution`, `expire_pending`, `contribution_reminder`; add `expire_plaid_tokens` |

## Files Created

| File | Purpose |
|---|---|
| `plaid_client.py` | Plaid SDK wrapper |
| `plaid_routes.py` | All `/plaid/*` FastAPI routes |
| `plaid_store.py` | JSON-backed store for cursor, processed IDs, action tokens |

# DCA Bot Dynamic

A personal dollar-cost averaging bot that uses AI to dynamically adjust portfolio target weights each cycle based on 3-month market data, momentum, and volatility. Runs on **live trading** with an email approval gate — no orders execute until you click Approve.

**Live dashboard:** [dca-bot-dynamic.up.railway.app](https://dca-bot-dynamic.up.railway.app)

---

## How it works

1. **Plaid monitors your bank account** for your paycheck deposit (employer name + amount match + pay date window)
2. **Detection email sent** — includes a one-time link to trigger the DCA cycle once you've funded Alpaca
3. **You transfer funds** into your Alpaca account manually ($100 default, any amount supported)
4. **Tap the link in the email** — kicks off the AI allocation cycle
5. **Fetches live portfolio state** from Alpaca
6. **Pulls 3-month market data** — daily bars, returns, volatility, momentum for each holding
7. **Asks Claude to adjust target weights** (±10% from base) based on current market conditions
8. **Allocates the contribution** using the adjusted targets to minimise drift from your goals
9. **Sends an approval email** — orders are staged and wait for your click
10. **You approve** — orders execute as market orders; unacted approvals expire daily at 5pm ET

If Plaid misses the webhook, a polling fallback runs every 2 hours during market hours on pay date windows and catches it automatically.

---

## Base Portfolio

Four-fund portfolio with a small-cap value tilt:

| Symbol | Asset | Base Target | Dynamic Range |
|--------|-------|-------------|---------------|
| VTI | US Total Market | 50% | 40–60% |
| VXUS | International | 35% | 25–45% |
| AVUV | US Small-Cap Value | 10% | 0–20% |
| BND | US Aggregate Bonds | 5% | 0–15% |

Claude can shift weights up to ±10% each cycle based on momentum and risk signals. The approval email always shows the reasoning.

---

## Stack

- **Python / FastAPI** — API server and webhook handler
- **APScheduler** — cron jobs and deferred one-shot tasks
- **Plaid** — bank account monitoring and paycheck detection
- **Alpaca** — live brokerage (market orders)
- **Claude (Anthropic)** — dynamic allocation reasoning
- **Resend** — transactional email (approval, detection, reports)
- **Railway** — deployment with persistent volume for Plaid state

---

## Features

- **Paycheck-triggered** — Plaid detects your direct deposit automatically; polling fallback catches missed webhooks
- **Smart pay date detection** — matches the 15th and last day of the month, weekend-adjusted, ±2 day window
- **Dynamic target weights** — Claude adjusts allocations each cycle based on 3-month market data
- **Email approval gate** — no orders execute without your explicit click; proposals expire at 5pm ET
- **Configurable contribution amount** — override the default $100 via `?amount=` on any trigger endpoint
- **Desktop and mobile dashboards** — portfolio value, P&L, Claude's reasoning, Plaid connection status
- **Audit log** — every event (detection, allocation, approval, expiry) written to a structured log
- **Manual triggers** — `/plaid/trigger` and `/plaid/trigger-full` for when you want to run a cycle manually

---

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Desktop dashboard |
| `GET /dashboard` | Mobile dashboard |
| `GET /health` | Server status, Plaid connection, pending approvals |
| `GET /audit` | Full audit log as JSON |
| `GET /approve/{token}` | Approve a pending allocation (executes orders) |
| `GET /deny/{token}` | Deny a pending allocation |
| `POST /contribute` | Manually propose an allocation (`?amount=100&dry_run=true/false`) |
| `GET /plaid/link` | One-time Plaid bank auth setup |
| `GET /plaid/trigger` | Manual DCA cycle (Alpaca already funded) |
| `GET /plaid/trigger-full` | Manual full pipeline — sends detection email with trigger link |
| `GET /plaid/trigger-once/{token}` | One-time link from paycheck detection email |
| `GET /plaid/force/{token}` | Cancel stale approval and restart cycle |
| `POST /plaid/refresh-account-info` | Re-fetch institution name and account mask from Plaid |

---

## Setup

1. Clone the repo and copy `.env.example` to `.env` (or set Railway env vars directly)
2. Required env vars:

```
ALPACA_API_KEY
ALPACA_SECRET_KEY
ANTHROPIC_API_KEY
PLAID_CLIENT_ID
PLAID_SECRET
PLAID_MANUAL_TRIGGER_TOKEN   # any secret string you choose
RESEND_API_KEY
NOTIFY_EMAIL
SERVER_BASE_URL              # e.g. https://your-app.up.railway.app
PLAID_STORE_PATH             # e.g. /data/plaid_store.json (Railway volume)
```

3. Visit `/plaid/link` to connect your bank account (one-time)
4. The bot starts monitoring for paychecks automatically

---

## Disclaimer

Not financial advice. This bot trades real money on a live Alpaca account. Review every approval email carefully before clicking. All orders require explicit approval — nothing executes automatically.

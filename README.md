# DCA Bot Dynamic ⚡📈

A DCA bot that uses AI to dynamically adjust portfolio target weights each cycle based on 3-month market data, momentum, and volatility. Runs on **live trading** with an email approval gate — no orders execute until you click Approve.

**Live dashboard:** [dca-bot-dynamic.up.railway.app](https://dca-bot-dynamic.up.railway.app)

> **💵 Live trading.** Every proposed allocation sends an approval email. Orders only execute after you click the Approve link; unacted approvals expire daily at 5pm ET.

## How it works

1. **Plaid detects your paycheck** landing in your bank account (employer name + minimum amount match)
2. **Sends a confirmation email** with a 5-minute cancel window before any money moves
3. **Pulls $100 into Alpaca** via ACH from your linked bank account
4. **Waits for buying power** — polls Alpaca until funds are available (instant for linked accounts)
5. **Fetches portfolio state** from Alpaca (live account)
6. **Pulls 3-month market data** — daily bars, returns, volatility, momentum for each holding
7. **Asks Claude to adjust target weights** (±10% from base) based on market conditions
8. **Allocates the contribution** using the adjusted targets to minimise drift
9. **Sends approval email** — orders are held in a pending state until you click Approve
10. **Expires pending approvals** daily at 5pm ET if not acted on

## Base Portfolio

| Symbol | Base Target | Dynamic Range |
|--------|-------------|---------------|
| VTI | 50% | 40–60% |
| VXUS | 35% | 25–45% |
| AVUV | 10% | 0–20% |
| BND | 5% | 0–15% |

## Features

- **Paycheck-triggered** — Plaid detects your direct deposit and kicks off the cycle automatically
- **Automated funding** — $100 ACH pull from your linked bank, no manual transfers needed
- **Dynamic target weights** — Claude adjusts targets each cycle based on momentum and risk
- **Email approval gate** — no orders execute without your explicit click
- **Email action links** — cancel, retry, skip, or force-restart the cycle directly from your inbox
- **Market data analysis** — 3-month returns, volatility, Sharpe ratio, momentum signals
- **Desktop dashboard** at `/`
- **Mobile dashboard** at `/dashboard`
- **Expiry safeguard** — unacted proposals auto-expire daily at 5pm ET

## Plaid Setup (one-time)

1. Add `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV=production`, and `PLAID_MANUAL_TRIGGER_TOKEN` to Railway env vars
2. Visit `https://dca-bot-dynamic.up.railway.app/plaid/link` and complete the bank auth flow
3. The bot stores your `PLAID_ACCESS_TOKEN` automatically — no further setup needed

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Desktop dashboard |
| `GET /dashboard` | Mobile dashboard |
| `GET /portfolio` | Current holdings and allocation JSON |
| `GET /health` | Server status, pending approval count |
| `GET /audit` | Full audit log as JSON |
| `GET /pending` | Approval tokens currently awaiting a click |
| `GET /approve/{token}` | Approve a pending allocation (executes orders) |
| `GET /deny/{token}` | Deny a pending allocation |
| `POST /contribute?amount=100&dry_run=true` | Manually propose (no email, no orders) |
| `POST /contribute?amount=100&dry_run=false` | Manually propose + send approval email |
| `GET /plaid/link` | One-time Plaid bank auth setup page |
| `GET /plaid/trigger` | Manually trigger a full paycheck cycle (requires token) |
| `GET /plaid/cancel/{token}` | Cancel a detected paycheck before ACH initiates |
| `GET /plaid/retry/{token}` | Retry after an ACH timeout |
| `GET /plaid/skip/{token}` | Skip a failed cycle (audit logged) |
| `GET /plaid/force/{token}` | Cancel stale approval and run a fresh cycle |

## Disclaimer

Not financial advice. Trades real money — review every approval email carefully before clicking.

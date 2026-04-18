# DCA Bot Dynamic ⚡📈

A DCA bot that uses AI to dynamically adjust portfolio target weights each cycle based on 3-month market data, momentum, and volatility. Runs on **live trading** with an email approval gate — no orders execute until you click Approve.

**Live dashboard:** [dca-bot-dynamic.up.railway.app](https://dca-bot-dynamic.up.railway.app)

> **💵 Live trading.** Every proposed allocation sends an approval email. Orders only execute after you click the Approve link; unacted approvals expire at 3:30pm ET the same day.

## How it works

1. **Scheduler fires** at 10am ET on the 1st and 16th
2. **Fetches portfolio state** from Alpaca (live account)
3. **Pulls 3-month market data** — daily bars, returns, volatility, momentum for each holding
4. **Asks Claude to adjust target weights** (±10% from base) based on market conditions
5. **Allocates the contribution** using the adjusted targets to minimise drift
6. **Sends approval email** — orders are held in a pending state until you click Approve
7. **Expires pending approvals** at 3:30pm ET if not acted on, so stale proposals never execute

## Base Portfolio

| Symbol | Base Target | Dynamic Range |
|--------|-------------|---------------|
| VTI | 50% | 40–60% |
| VXUS | 35% | 25–45% |
| AVUV | 10% | 0–20% |
| BND | 5% | 0–15% |

## Features

- **Dynamic target weights** — Claude adjusts targets each cycle based on momentum and risk
- **Email approval gate** — no orders execute without your explicit click
- **Market data analysis** — 3-month returns, volatility, Sharpe ratio, momentum signals
- **Desktop dashboard** at `/`
- **Mobile dashboard** at `/dashboard`
- **Expiry safeguard** — unacted proposals auto-expire at 3:30pm ET

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

## Disclaimer

Not financial advice. Trades real money — review every approval email carefully before clicking.

# DCA Bot Dynamic ⚡🧪📈

An experimental variant of [dca-bot](https://github.com/rorakhit/dca-bot) that uses AI to dynamically adjust portfolio target weights based on 3-month market data, momentum, and volatility. Runs on **paper trading only** for safe experimentation.

**Live dashboard:** [dca-bot-dynamic.up.railway.app](https://dca-bot-dynamic.up.railway.app)

> **⚠️ Paper trading only.** This bot never touches real money. It runs alongside the fixed-target bot to compare strategies.

## How it works

1. **Scheduler fires** at 10am ET on the 1st and 16th
2. **Fetches portfolio state** from Alpaca (paper account)
3. **Pulls 3-month market data** — daily bars, returns, volatility, momentum for each holding
4. **Asks Claude to adjust target weights** (±10% from base) based on market conditions
5. **Allocates the contribution** using the adjusted targets to minimise drift
6. **Auto-executes** paper trades (no approval needed — it's not real money)
7. **Logs both strategies** — what the dynamic bot did AND what the fixed-target bot would have done

## A/B Comparison

Every cycle logs a counterfactual: the fixed-target allocation that the original bot would have made. Over time, you can compare performance between strategies via the dashboard or `/comparison` endpoint.

## Base Portfolio

| Symbol | Base Target | Dynamic Range |
|--------|-------------|---------------|
| VTI | 50% | 40–60% |
| VXUS | 35% | 25–45% |
| AVUV | 10% | 0–20% |
| BND | 5% | 0–15% |

## Features

- **Dynamic target weights** — Claude adjusts targets each cycle based on momentum and risk
- **A/B comparison logging** — every cycle logs both dynamic and fixed-target strategies
- **Market data analysis** — 3-month returns, volatility, Sharpe ratio, momentum signals
- **Desktop dashboard** with strategy comparison cards
- **Mobile dashboard** at `/dashboard`
- **Paper trading safety** — hardcoded to never use live credentials

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Desktop dashboard with strategy comparison |
| `GET /dashboard` | Mobile dashboard |
| `GET /portfolio` | Current holdings and allocation JSON |
| `GET /health` | Server status, paper trading confirmation |
| `GET /audit` | Full audit log as JSON |
| `GET /comparison` | A/B strategy comparison data |
| `POST /contribute?amount=100&dry_run=false` | Manually trigger a contribution |

## Disclaimer

This is an experiment. Paper trading only. Not financial advice.

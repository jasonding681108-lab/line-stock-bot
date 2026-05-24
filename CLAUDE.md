# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run web UI (port 8080)
python web_app.py

# Production (Heroku / Render)
gunicorn web_app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60
```

Copy `.env.example` to `.env` and fill in credentials before running.

## Architecture

| File | Purpose |
|------|---------|
| `web_app.py` | Flask app — serves `templates/index.html` + `/api/stock/<id>` + `/api/name/<id>` endpoints |
| `stock_data.py` | Data layer — all FinMind / TWSE fetching logic |
| `templates/index.html` | Single-page app with Chart.js charts and a localStorage-backed watchlist |

### Data flow (`stock_data.py`)

- `get_institutional(stock_id, days=45)` — fetches 三大法人買賣超 from FinMind (`TaiwanStockInstitutionalInvestorsBuySell`), aggregates by date into 外資 / 投信 / 自營 / 合計. Returns 45 days to cover month-start cumulative calculations.
- `get_margin(stock_id)` — tries FinMind first (`TaiwanStockMarginPurchaseShortSale`); falls back to parallel TWSE scraping (`_margin_twse_parallel`) if FinMind returns no data.
- `get_stock_name(stock_id)` — fetches company name from FinMind (`TaiwanStockInstitutionalInvestorsBuySell`, past 7 days) and returns the `stock_name` field; returns `''` on failure.

### API endpoints (`web_app.py`)

| Endpoint | Returns |
|----------|---------|
| `GET /api/stock/<id>` | `{stock_id, institutional, margin}` |
| `GET /api/name/<id>` | `{name}` — company name lookup used by watchlist add |

### Environment variables

| Variable | Required | Notes |
|----------|----------|-------|
| `FINMIND_TOKEN` | Optional | Free token from finmindtrade.com; improves rate limits |

### Web UI watchlist

The watchlist in `index.html` is entirely client-side — stored in `localStorage` under key `tw_stock_watchlist`.

**Version-based reset:** `WL_VERSION` (integer constant) and `tw_stock_watchlist_ver` (localStorage key) are used to detect stale data. When `DEFAULT_WATCHLIST` changes, bump `WL_VERSION` by 1 — all users will automatically receive the new defaults on next page load without needing to clear localStorage manually.

**Auto name lookup:** `addToWatchlist()` is async. If the user enters only a stock code (no name), it calls `/api/name/<code>` to fetch the company name before saving the chip.

### Institutional cumulative logic (frontend)

The 三大法人 table and chart display **cumulative** buy/sell totals, not daily values. The accumulation starts from the 1st of the month of the oldest displayed date (e.g., if the 20-day window starts on 4/20, the cumulative begins from 4/1). `monthStart` must be computed before `setResult()` is called — using it inside the template string before declaration causes a `ReferenceError`.

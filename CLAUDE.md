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
| `web_app.py` | Flask app — serves `templates/index.html` + `/api/stock/<id>` JSON endpoint |
| `stock_data.py` | Data layer — all FinMind / TWSE fetching logic |
| `templates/index.html` | Single-page app with Chart.js charts and a localStorage-backed watchlist |

### Data flow (`stock_data.py`)

- `get_institutional(stock_id, days=45)` — fetches 三大法人買賣超 from FinMind (`TaiwanStockInstitutionalInvestorsBuySell`), aggregates by date into 外資 / 投信 / 自營 / 合計. Returns 45 days to cover month-start cumulative calculations.
- `get_margin(stock_id)` — tries FinMind first (`TaiwanStockMarginPurchaseShortSale`); falls back to parallel TWSE scraping (`_margin_twse_parallel`) if FinMind returns no data.

### Environment variables

| Variable | Required | Notes |
|----------|----------|-------|
| `FINMIND_TOKEN` | Optional | Free token from finmindtrade.com; improves rate limits |

### Web UI watchlist

The watchlist in `index.html` is entirely client-side — stored in `localStorage` under key `tw_stock_watchlist`. Default list (6 preset stocks) is seeded at first load. No backend changes are needed to modify watchlist behaviour.

### Institutional cumulative logic (frontend)

The 三大法人 table and chart display **cumulative** buy/sell totals, not daily values. The accumulation starts from the 1st of the month of the oldest displayed date (e.g., if the 20-day window starts on 4/20, the cumulative begins from 4/1). `monthStart` must be computed before `setResult()` is called — using it inside the template string before declaration causes a `ReferenceError`.

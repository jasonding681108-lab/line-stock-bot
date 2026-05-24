"""
Data layer: fetch institutional buy/sell and margin balance from
FinMind (primary) with TWSE tables as fallback for margin data.
"""

import os
import requests
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

_FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}
_FINMIND = "https://api.finmindtrade.com/api/v4/data"
_TWSE = "https://www.twse.com.tw/rwd/zh"

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _past_trading_dates(n: int = 30) -> list[str]:
    """Return the last n weekdays as 'YYYY-MM-DD' strings, newest first."""
    dates, d = [], datetime.now()
    while len(dates) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            dates.append(d.strftime("%Y-%m-%d"))
    return dates



# ──────────────────────────────────────────────
# 法人買賣超 via FinMind
# ──────────────────────────────────────────────

def get_stock_name(stock_id: str) -> str:
    """Return the company name for stock_id, or '' if not found."""
    params = {
        "dataset": "TaiwanStockInfo",
        "data_id": stock_id,
        "token": _FINMIND_TOKEN,
    }
    try:
        r = requests.get(_FINMIND, params=params, timeout=8, headers=_HEADERS)
        r.raise_for_status()
        data = r.json().get("data", [])
        if data:
            return data[0].get("stock_name", "").strip()
    except Exception:
        pass
    return ""


def get_institutional(stock_id: str, days: int = 20) -> list[dict]:
    """
    Return up to `days` rows of institutional net buy/sell, newest first.
    Each row: {date, 外資, 投信, 自營, 合計}  (units: shares)
    """
    start = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    params = {
        "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
        "data_id": stock_id,
        "start_date": start,
        "token": _FINMIND_TOKEN,
    }
    try:
        r = requests.get(_FINMIND, params=params, timeout=15, headers=_HEADERS)
        r.raise_for_status()
        payload = r.json()
        if payload.get("status") != 200 or not payload.get("data"):
            return []
    except Exception:
        return []

    # Aggregate by date across investor types
    by_date: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in payload["data"]:
        date = row["date"]
        net = int(row.get("buy", 0)) - int(row.get("sell", 0))
        name = row.get("name", "")
        if name in ("Foreign_Investor", "Foreign_Dealer_Self"):
            by_date[date]["外資"] += net
        elif name == "Investment_Trust":
            by_date[date]["投信"] += net
        elif name in ("Dealer_self", "Dealer_Hedging"):
            by_date[date]["自營"] += net

    result = []
    for date in sorted(by_date, reverse=True)[:days]:
        d = by_date[date]
        total = d["外資"] + d["投信"] + d["自營"]
        result.append(
            {"date": date, "外資": d["外資"], "投信": d["投信"], "自營": d["自營"], "合計": total}
        )
    return result


# ──────────────────────────────────────────────
# 融資融券餘額  (FinMind → TWSE fallback)
# ──────────────────────────────────────────────

def get_margin(stock_id: str, days: int = 20) -> list[dict]:
    """
    Return up to `days` rows of margin balance, newest first.
    Each row: {date, 融資餘額, 融券餘額}  (units: shares/1000 = 張)
    """
    rows = _margin_finmind(stock_id, days)
    if rows:
        return rows
    return _margin_twse_parallel(stock_id, days)


def _margin_finmind(stock_id: str, days: int) -> list[dict]:
    start = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    params = {
        "dataset": "TaiwanStockMarginPurchaseShortSale",
        "data_id": stock_id,
        "start_date": start,
        "token": _FINMIND_TOKEN,
    }
    try:
        r = requests.get(_FINMIND, params=params, timeout=15, headers=_HEADERS)
        r.raise_for_status()
        payload = r.json()
        if payload.get("status") != 200 or not payload.get("data"):
            return []
        raw = sorted(payload["data"], key=lambda x: x["date"], reverse=True)[:days]
        return [
            {
                "date": row["date"],
                "融資餘額": row.get("MarginPurchaseTodayBalance", 0),
                "融券餘額": row.get("ShortSaleTodayBalance", 0),
            }
            for row in raw
        ]
    except Exception:
        return []


def _fetch_one_day_margin(twse_date: str, stock_id: str) -> dict | None:
    """Query TWSE MI_MARGN (no stockNo) for one day; return row for stock_id or None."""
    url = f"{_TWSE}/marginTrading/MI_MARGN"
    try:
        r = requests.get(
            url, params={"date": twse_date, "response": "json"},
            timeout=10, headers=_HEADERS
        )
        d = r.json()
        for table in d.get("tables", []):
            fields = table.get("fields", [])
            rows = table.get("data", [])
            if not rows:
                continue
            # Identify column positions dynamically
            code_idx = next((i for i, f in enumerate(fields) if "代號" in f or "代碼" in f), None)
            marg_idx = next((i for i, f in enumerate(fields) if "融資" in f and "餘額" in f), None)
            short_idx = next((i for i, f in enumerate(fields) if "融券" in f and "餘額" in f), None)
            if None in (code_idx, marg_idx, short_idx):
                continue
            for row in rows:
                if len(row) > max(code_idx, marg_idx, short_idx):
                    if row[code_idx].strip() == stock_id:
                        iso = f"{twse_date[:4]}-{twse_date[4:6]}-{twse_date[6:]}"
                        return {
                            "date": iso,
                            "融資餘額": row[marg_idx].strip(),
                            "融券餘額": row[short_idx].strip(),
                        }
    except Exception:
        pass
    return None


def _margin_twse_parallel(stock_id: str, days: int) -> list[dict]:
    """Parallel-fetch the last 30 trading days from TWSE; return up to `days` hits."""
    trading_dates = [d.replace("-", "") for d in _past_trading_dates(30)]
    results: list[dict] = []

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_one_day_margin, td, stock_id): td for td in trading_dates}
        for f in as_completed(futures):
            row = f.result()
            if row:
                results.append(row)

    results.sort(key=lambda x: x["date"], reverse=True)
    return results[:days]

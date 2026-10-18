"""Earnings dates (free, from Yahoo via yfinance).

A quarterly report can gap a stock 10-20% overnight, straight through a stop.
We warn when a quest's time window includes an earnings date, and let the
backtest measure whether those quests did worse.
Dates are cached in cache/earnings/ for a week.
"""
import json
import time
from datetime import date, timedelta

import pandas as pd

from swingquest.config import CACHE_DIR

CACHE = CACHE_DIR / "earnings"
WINDOW_DAYS = 15        # trading days in a quest


def earnings_dates(ticker: str, fetch=None, max_age_days: int = 7) -> list[str]:
    """Past and upcoming earnings dates (YYYY-MM-DD), newest last. [] if unknown."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{ticker}.json"
    if path.exists():
        cached = json.loads(path.read_text())
        if cached.get("fetched", "") >= (date.today() - timedelta(days=max_age_days)).isoformat():
            return cached["dates"]
    if fetch is None:
        import yfinance as yf
        fetch = lambda t: yf.Ticker(t).get_earnings_dates(limit=24)
    try:
        df = fetch(ticker)
        dates = sorted({pd.Timestamp(d).strftime("%Y-%m-%d") for d in (df.index if df is not None else [])})
    except Exception:
        dates = []
    path.write_text(json.dumps({"fetched": date.today().isoformat(), "dates": dates}))
    return dates


def cached_dates(ticker: str) -> list[str]:
    """Earnings dates from the cache only (no internet); [] if never fetched."""
    path = CACHE / f"{ticker}.json"
    return json.loads(path.read_text())["dates"] if path.exists() else []


def quest_window(signal_day: str, days: int = WINDOW_DAYS) -> tuple[str, str]:
    """Entry day (next trading day) to the last day of the time stop, weekdays only."""
    start = pd.Timestamp(signal_day) + pd.offsets.BDay(1)
    end = start + pd.offsets.BDay(days - 1)
    return f"{start:%Y-%m-%d}", f"{end:%Y-%m-%d}"


def in_window(dates: list[str], signal_day: str, days: int = WINDOW_DAYS) -> str | None:
    """The first earnings date inside the quest's window, or None."""
    start, end = quest_window(signal_day, days)
    return next((d for d in dates if start <= d <= end), None)


def annotate(rows: list[dict], statuses=("pick", "watch"), pause: float = 0.8, progress=print) -> list[dict]:
    """Adds earnings_in_window (True/False) to backtest rows of the given kinds."""
    todo = sorted({r["ticker"] for r in rows if r["status"] in statuses})
    found = {}
    for i, t in enumerate(todo, 1):
        cached = (CACHE / f"{t}.json").exists()
        found[t] = earnings_dates(t)
        if not cached:
            time.sleep(pause)  # be gentle with Yahoo
        if progress and i % 50 == 0:
            progress(f"  earnings dates: {i}/{len(todo)} stocks")
    for r in rows:
        if r["status"] in statuses:
            dates = found.get(r["ticker"]) or []
            r["earnings_in_window"] = (in_window(dates, r["signal_date"]) is not None) if dates else None
    return rows

"""The stock universe: S&P 500 + MidCap 400 + SmallCap 600 (US) and the
S&P/TSX Composite (Canada), from Wikipedia's public index lists, refreshed
weekly. Saved to data/universe/stocks.json so a failed download never
empties the universe."""
import json
from datetime import date, timedelta
from io import StringIO

import pandas as pd
import requests

from swingquest.config import ROOT

STOCKS_FILE = ROOT / "data" / "universe" / "stocks.json"
UA = {"User-Agent": "SwingQuest/1.0 (personal research project)"}
SOURCES = [
    ("S&P 500", "US", "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"),
    ("S&P 400", "US", "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"),
    ("S&P 600", "US", "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"),
    ("TSX Composite", "CA", "https://en.wikipedia.org/wiki/S%26P/TSX_Composite_Index"),
]
TICKER_COLS = ("Symbol", "Ticker symbol", "Ticker")


def yahoo_ticker(raw: str, country: str) -> str | None:
    t = str(raw).strip().upper().replace(" ", "")
    if not t or t == "NAN":
        return None
    t = t.replace(".", "-")                 # BRK.B -> BRK-B, BBD.B -> BBD-B
    return f"{t}.TO" if country == "CA" else t


def _members(html: str) -> pd.DataFrame | None:
    """The constituents table: has a ticker column and plenty of rows."""
    for tbl in pd.read_html(StringIO(html)):
        if isinstance(tbl.columns, pd.MultiIndex):
            continue
        col = next((c for c in TICKER_COLS if c in tbl.columns), None)
        if col and len(tbl) >= 150:
            return tbl.rename(columns={col: "_ticker"})
    return None


def fetch_lists(get=None) -> list[dict]:
    get = get or (lambda url: requests.get(url, headers=UA, timeout=30).text)
    stocks = {}
    for index, country, url in SOURCES:
        tbl = _members(get(url))
        if tbl is None:
            continue
        name_col = next((c for c in ("Security", "Company") if c in tbl.columns), None)
        sector_col = next((c for c in tbl.columns if str(c).startswith(("GICS Sector", "Sector"))), None)
        for _, row in tbl.iterrows():
            t = yahoo_ticker(row["_ticker"], country)
            if t and t not in stocks:
                stocks[t] = {"ticker": t, "name": str(row[name_col]) if name_col else t,
                             "sector": str(row[sector_col]) if sector_col else None,
                             "index": index, "country": country}
    return sorted(stocks.values(), key=lambda s: s["ticker"])


def load(refresh_days: int = 7, force: bool = False) -> list[dict]:
    """Saved list, refreshed when older than a week. Falls back to the saved
    list if Wikipedia can't be reached or returns something odd."""
    saved = json.loads(STOCKS_FILE.read_text(encoding="utf-8")) if STOCKS_FILE.exists() else None
    fresh_enough = saved and saved["updated"] >= (date.today() - timedelta(days=refresh_days)).isoformat()
    if saved and fresh_enough and not force:
        return saved["stocks"]
    try:
        stocks = fetch_lists()
    except Exception:
        stocks = []
    if len(stocks) < 1000 and saved:      # partial download: keep what we had
        return saved["stocks"]
    STOCKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STOCKS_FILE.write_text(json.dumps({"updated": date.today().isoformat(), "stocks": stocks}, indent=0),
                           encoding="utf-8", newline="\n")
    return stocks

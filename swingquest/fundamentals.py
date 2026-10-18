"""Company fundamentals, analyst views and earnings estimates (free, Yahoo).

Cached in data/universe/fundamentals.json. Each run refreshes only the
stalest slice (a few hundred stocks), so the whole universe is updated about
once a week without hammering Yahoo. Earnings-estimate revisions and
surprises (2 extra calls each) are fetched for the strongest candidates.
"""
import json
import time
from datetime import date, timedelta

from swingquest.config import ROOT

FILE = ROOT / "data" / "universe" / "fundamentals.json"
INFO_FIELDS = [
    "longName", "sector", "industry", "country", "currency", "marketCap", "currentPrice",
    "targetMeanPrice", "targetHighPrice", "targetLowPrice", "numberOfAnalystOpinions", "recommendationMean", "recommendationKey",
    "profitMargins", "operatingMargins", "returnOnEquity", "debtToEquity", "currentRatio", "revenueGrowth", "earningsGrowth",
    "freeCashflow", "forwardPE", "trailingPE", "priceToSalesTrailing12Months", "enterpriseToEbitda",
    "beta", "shortPercentOfFloat", "heldPercentInstitutions", "heldPercentInsiders", "dividendYield",
    "fiftyTwoWeekLow", "fiftyTwoWeekHigh", "averageDailyVolume3Month",
]


def load() -> dict:
    return json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else {}


def save(data: dict) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8", newline="\n")


def _stale_first(data: dict, tickers: list[str], key: str, max_age_days: int) -> list[str]:
    cutoff = (date.today() - timedelta(days=max_age_days)).isoformat()
    due = [t for t in tickers if data.get(t, {}).get(key, "") < cutoff]
    return sorted(due, key=lambda t: data.get(t, {}).get(key, ""))


def _yf_info(t):
    import yfinance as yf
    return yf.Ticker(t).info


def _yf_estimates(t):
    import yfinance as yf
    tk = yf.Ticker(t)
    return tk.eps_revisions, tk.earnings_history


def summarize_estimates(revisions, history) -> dict:
    """Net analyst EPS revisions (last 30 days) and the earnings-surprise record."""
    out = {}
    try:
        if revisions is not None and len(revisions):
            up = int(revisions["upLast30days"].fillna(0).sum())
            down = int(revisions["downLast30days"].fillna(0).sum())
            out.update({"rev_up_30d": up, "rev_down_30d": down, "rev_net_30d": up - down})
    except (KeyError, TypeError, ValueError):
        pass
    try:
        if history is not None and len(history):
            s = history["surprisePercent"].dropna().tail(4)
            if len(s):
                out.update({"surprise_avg": round(float(s.mean()), 4), "surprise_last": round(float(s.iloc[-1]), 4),
                            "beats_4q": int((s > 0).sum()), "quarters": int(len(s))})
    except (KeyError, TypeError, ValueError):
        pass
    return out


def refresh_info(tickers: list[str], budget: int = 350, max_age_days: int = 6, fetch=None,
                 pause: float = 0.35, progress=print) -> int:
    """Refresh the stalest `budget` stocks. Stops early if Yahoo starts refusing."""
    fetch = fetch or _yf_info
    data = load()
    todo = _stale_first(data, tickers, "info_at", max_age_days)[:budget]
    fails, done = 0, 0
    for i, t in enumerate(todo, 1):
        try:
            info = fetch(t) or {}
            if not info.get("currentPrice") and not info.get("regularMarketPrice") and not info.get("marketCap"):
                raise ValueError("empty")
            row = data.get(t, {})
            row.update({k: info.get(k) for k in INFO_FIELDS})
            row["currentPrice"] = info.get("currentPrice") or info.get("regularMarketPrice")
            row["info_at"] = date.today().isoformat()
            data[t] = row
            done += 1
            fails = 0
        except Exception:
            fails += 1
            data.setdefault(t, {})["info_at"] = date.today().isoformat()  # don't retry a dead ticker every run
            if fails >= 8:
                if progress:
                    progress("  Yahoo is refusing requests; stopping this batch early (will resume next run)")
                break
        if progress and i % 100 == 0:
            progress(f"  fundamentals: {i}/{len(todo)}")
            save(data)
        time.sleep(pause)
    save(data)
    return done


def refresh_estimates(tickers: list[str], budget: int = 150, max_age_days: int = 7, fetch=None,
                      pause: float = 0.5, progress=print) -> int:
    fetch = fetch or _yf_estimates
    data = load()
    todo = _stale_first(data, tickers, "est_at", max_age_days)[:budget]
    done = 0
    for i, t in enumerate(todo, 1):
        try:
            rev, hist = fetch(t)
            data.setdefault(t, {}).update(summarize_estimates(rev, hist))
            done += 1
        except Exception:
            pass
        data.setdefault(t, {})["est_at"] = date.today().isoformat()
        if progress and i % 50 == 0:
            progress(f"  estimates: {i}/{len(todo)}")
        time.sleep(pause)
    save(data)
    return done

"""Replays the live scanner through history.

For every past insider-buying "event" we do what the live scan would have
done: wait for the filing to be public, apply the universe rules, score it
with the SAME evaluate() function, and give it up to `trigger_days` for the
chart timing to turn Ready. Then we record what happened next.

An event starts with a purchase filing for a stock that had no event in
the previous 21 calendar days (so one cluster of buying = one signal).
"""
from datetime import date, timedelta

import pandas as pd

from swingquest import store
from swingquest.config import settings
from swingquest.prices.base import get_price_source
from swingquest.signals import scoring
from swingquest.signals.scan import evaluate
from swingquest.backtest.outcomes import measure
from swingquest.sectors import SECTOR_ETFS, etf_of, sector_of
from swingquest.universe import IssuerProfiles, exchange_map, is_us_listed, liquidity_check

EVENT_GAP_DAYS = 21
HISTORY_BARS = 300   # roughly what the live scan sees (~400 calendar days)


def build_events(buys: list[dict], gap_days: int = EVENT_GAP_DAYS) -> list[tuple[str, str]]:
    """[(ticker, first filing date)] with at most one event per gap window."""
    events, last_start = [], {}
    for b in sorted(buys, key=lambda b: (b["filed_date"], b["ticker"])):
        t, d = b["ticker"], b["filed_date"]
        prev = last_start.get(t)
        if prev is None or date.fromisoformat(d) - date.fromisoformat(prev) > timedelta(days=gap_days):
            events.append((t, d))
            last_start[t] = d
    return events


def price_matches_filing(df: pd.DataFrame, buy: dict) -> bool:
    """Catches tickers that now belong to a different company, and big
    splits: the insider's price should be near the market price that day."""
    past = df.loc[:pd.Timestamp(buy["trade_date"] or buy["filed_date"])]
    if past.empty:
        return False
    ratio = float(past["close"].iloc[-1]) / buy["avg_price"]
    return 0.6 <= ratio <= 1.67


def run_backtest(start: str, end: str, source=None, profiles=None, exchanges=None,
                 progress=print, trade_cfg: dict | None = None) -> dict:
    """`trade_cfg` lets an experiment try different stop/target rules
    without touching settings.yaml."""
    cfg = scoring.load_weights()
    rules, trade_cfg = cfg["rules"], {**settings()["trade"], **(trade_cfg or {})}
    hist_start = store.load_state().get("history_start")

    all_buys = store.load_buys((date.fromisoformat(start) - timedelta(days=440)).isoformat(), end)
    if rules.get("ignore_10b5_1_plans"):
        all_buys = [b for b in all_buys if not b.get("plan_10b5_1")]
    by_ticker: dict[str, list[dict]] = {}
    for b in sorted(all_buys, key=lambda b: b["filed_date"]):
        by_ticker.setdefault(b["ticker"], []).append(b)
    events = build_events([b for b in all_buys if start <= b["filed_date"] <= end])
    progress(f"{len(events)} insider-buying events from {start} to {end}")

    source = source or get_price_source()
    exchanges = exchange_map() if exchanges is None else exchanges
    profiles = profiles or IssuerProfiles()
    tickers = sorted({t for t, _ in events})
    price_start = date.fromisoformat(start) - timedelta(days=420)
    prices = source.history(tickers + ["SPY"] + list(SECTOR_ETFS.values()), price_start, date.today())
    spy = prices["SPY"]

    rows, skipped = [], {}

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    for n, (t, d) in enumerate(events, 1):
        if n % 1000 == 0:
            progress(f"  evaluated {n}/{len(events)} events")
        df = prices.get(t)
        if df is None:
            skip("no price data (often delisted)")
            continue
        day0 = pd.Timestamp(d)
        days = df.index[(df.index >= day0) & (df.index <= day0 + pd.Timedelta(days=rules["trigger_days"]))]
        if len(days) == 0:
            skip("no trading days after filing")
            continue
        first = by_ticker[t][[b["filed_date"] for b in by_ticker[t]].index(d)]
        if not price_matches_filing(df, first):
            skip("price doesn't match filing (ticker change or split)")
            continue
        if not is_us_listed(t, exchanges):
            skip("trades OTC")
            continue
        liq = liquidity_check(df, days[0])
        if not liq["ok"]:
            skip("too cheap or thinly traded")
            continue
        profile = profiles.get(first["issuer_cik"])
        if profile["is_fund"]:
            skip("a fund, not an operating company")
            continue

        sector = sector_of(profile.get("sic"))
        market = {"spy": spy, "etf": prices.get(etf_of(sector)), "sector": sector}  # cut at each day inside evaluate
        chosen = None
        for e in days:  # give timing up to trigger_days to turn Ready, like the live scan
            e_str = f"{e:%Y-%m-%d}"
            w_start = (e - pd.Timedelta(days=rules["window_days"])).strftime("%Y-%m-%d")
            window = [b for b in by_ticker[t] if w_start <= b["filed_date"] <= e_str]
            prior_start = (e - pd.Timedelta(days=rules["window_days"] + 400)).strftime("%Y-%m-%d")
            prior = [b for b in by_ticker[t] if prior_start <= b["filed_date"] < w_start]
            setup = evaluate(t, window, prior, hist_start, df.loc[:e].tail(HISTORY_BARS), cfg, trade_cfg, market)
            if setup is None:
                break
            if chosen is None or setup["status"] == "pick":
                chosen = (e, setup)
            if setup["status"] == "pick":
                break
        if chosen is None:
            skip("not enough price history")
            continue
        e, setup = chosen
        outcome = measure(df, spy, e, setup["indicators"]["atr"], setup["plan"]["entry_high"], trade_cfg)
        rows.append(_row(t, d, e, setup, outcome))

    progress(f"{len(rows)} signals evaluated; skipped: {skipped}")
    return {"start": start, "end": end, "events": len(events), "skipped": skipped, "rows": rows}


def _row(ticker, filed, signal_day, setup, outcome) -> dict:
    row = {
        "id": f"{ticker}-{signal_day:%Y-%m-%d}",
        "ticker": ticker,
        "filed_date": filed,
        "signal_date": f"{signal_day:%Y-%m-%d}",
        "status": setup["status"],
        "score": setup["score"],
        "timing": setup["timing"],
        "role": setup["factors"]["role"]["value"],
    }
    for name, f in setup["factors"].items():
        row[f"{name}_points"] = f["points"]
        row[f"{name}_frac"] = f.get("fraction")
    row["rs_3m"] = setup["factors"].get("relative_strength", {}).get("value")
    row["sector_rs"] = setup["factors"].get("sector_strength", {}).get("value")
    row["sector"] = setup.get("sector")
    row.update(outcome)
    return row

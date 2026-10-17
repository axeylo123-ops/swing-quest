"""The daily scan: insider buys -> scored setups -> docs/data/today.json.

`evaluate()` judges ONE stock on ONE day using only information available
then. The live scan and the backtest (Phase 3) both call it, so what we
test is exactly what we trade.
"""
import json
import math
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from swingquest import store
from swingquest.config import DATA_OUT_DIR, settings
from swingquest.prices.base import get_price_source
from swingquest.signals import plan, scoring, technicals
from swingquest.universe import IssuerProfiles, exchange_map, is_us_listed, liquidity_check

PRICE_LOOKBACK_DAYS = 400   # enough for a 52-week range plus moving averages
CHART_BARS = 90


def evaluate(ticker: str, window_buys: list[dict], prior_buys: list[dict],
             history_start: str | None, prices: pd.DataFrame, cfg: dict,
             trade_cfg: dict) -> dict | None:
    """Score one stock. `prices` must end on the decision day (no future bars)."""
    snap = technicals.snapshot(prices, trade_cfg["atr_period"])
    if snap is None or not window_buys:
        return None
    result = scoring.score(window_buys, prior_buys, history_start, snap, cfg)
    trade = plan.trade_plan(snap["close"], snap["atr"], trade_cfg)
    if trade is None:
        return None
    t = plan.timing(snap)
    min_score = cfg["rules"]["min_score"]
    status = ("pick" if result["score"] >= min_score and t["label"] == "Ready"
              else "watch" if result["score"] >= min_score else "below")
    return {
        "ticker": ticker,
        "company": window_buys[-1].get("issuer_name"),
        "status": status,
        "score": result["score"],
        "timing": t["label"],
        "timing_notes": t["notes"],
        "reasons": result["reasons"],
        "cautions": result["cautions"],
        "factors": {k: {"points": f["points"], "value": f["value"]} for k, f in result["factors"].items()},
        "plan": trade,
        "indicators": {k: round(v, 4) for k, v in snap.items()},
        "insiders": [{"name": b["owner_name"], "role": b["role"], "value": b["value"],
                      "avg_price": b["avg_price"], "trade_date": b["trade_date"],
                      "filed_date": b["filed_date"]} for b in window_buys],
    }


def chart_data(prices: pd.DataFrame) -> list[list]:
    """Compact OHLC + 20-day average for the dashboard chart."""
    tail = prices.assign(sma20=technicals.sma(prices["close"], 20)).tail(CHART_BARS)
    return [[d.strftime("%Y-%m-%d"), round(r.open, 2), round(r.high, 2), round(r.low, 2),
             round(r.close, 2), None if math.isnan(r.sma20) else round(r.sma20, 2)]
            for d, r in tail.iterrows()]


def market_weather(spy: pd.DataFrame | None, as_of) -> dict | None:
    """Is the overall market (SPY) above its 200-day average? Shown as a
    caution only: past quests in downtrends were too few to make it a rule."""
    if spy is None:
        return None
    past = spy.loc[:as_of]
    if len(past) < 200:
        return None
    close, sma200 = float(past["close"].iloc[-1]), float(past["close"].tail(200).mean())
    return {"trend": "up" if close > sma200 else "down", "spy_close": round(close, 2), "spy_sma200": round(sma200, 2)}


def history_start() -> str | None:
    """Earliest date our insider data reliably covers (set by the backfill)."""
    state = store.load_state()
    return state.get("history_start")


def run_scan(today: date | None = None, out_dir=DATA_OUT_DIR, source=None, exchanges=None,
             profiles=None) -> dict:
    cfg = scoring.load_weights()
    rules, trade_cfg = cfg["rules"], settings()["trade"]
    today = today or datetime.now(timezone.utc).date()
    window_start = today - timedelta(days=rules["window_days"])
    trigger_start = (today - timedelta(days=rules["trigger_days"])).isoformat()

    buys = store.load_buys(window_start.isoformat(), today.isoformat())
    if rules.get("ignore_10b5_1_plans"):
        buys = [b for b in buys if not b.get("plan_10b5_1")]
    by_ticker: dict[str, list[dict]] = {}
    for b in sorted(buys, key=lambda b: b["filed_date"]):
        by_ticker.setdefault(b["ticker"], []).append(b)
    triggered = sorted(t for t, bs in by_ticker.items() if bs[-1]["filed_date"] >= trigger_start)

    prior = store.load_buys((window_start - timedelta(days=400)).isoformat(),
                            (window_start - timedelta(days=1)).isoformat())
    source = source or get_price_source()
    exchanges = exchange_map() if exchanges is None else exchanges
    profiles = profiles or IssuerProfiles()
    price_data = source.history(triggered + ["SPY"], today - timedelta(days=PRICE_LOOKBACK_DAYS), today)
    as_of = price_data["SPY"].index[-1] if "SPY" in price_data else pd.Timestamp(today)

    picks, watch, skipped, evaluated = [], [], [], []
    for t in triggered:
        df = price_data.get(t)
        if df is None:
            skipped.append({"ticker": t, "reason": "no price data"})
            continue
        df = df.loc[:as_of]
        if not is_us_listed(t, exchanges):
            skipped.append({"ticker": t, "reason": "trades over-the-counter (OTC)"})
            continue
        liq = liquidity_check(df, as_of)
        if not liq["ok"]:
            skipped.append({"ticker": t, "reason": liq["reason"]})
            continue
        if profiles.get(by_ticker[t][-1]["issuer_cik"])["is_fund"]:
            skipped.append({"ticker": t, "reason": "a fund, not an operating company"})
            continue
        setup = evaluate(t, by_ticker[t], [p for p in prior if p["ticker"] == t],
                         history_start(), df, cfg, trade_cfg)
        if setup is None:
            skipped.append({"ticker": t, "reason": "not enough price history"})
            continue
        setup["id"] = f"{t}-{as_of:%Y-%m-%d}"
        evaluated.append(setup)  # every scored stock is logged for learning (see tracker.py)
        if setup["status"] == "below":
            skipped.append({"ticker": t, "reason": f"score {setup['score']} is below {rules['min_score']}"})
            continue
        setup["chart"] = chart_data(df)
        (picks if setup["status"] == "pick" else watch).append(setup)

    picks.sort(key=lambda s: -s["score"])
    watch.sort(key=lambda s: -s["score"])
    market = market_weather(price_data.get("SPY"), as_of)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": f"{as_of:%Y-%m-%d}",
        "status": "setups" if picks else "none",
        "message": f"{len(picks)} setup(s) today" if picks else "No setups today.",
        "picks": picks,
        "watchlist": watch,
        "summary": {
            "insider_buys_in_window": len(buys),
            "stocks_with_new_buys": len(triggered),
            "skipped": len(skipped),
            "watchlist": len(watch),
            "picks": len(picks),
        },
        "skipped": skipped,
        "rules": {"min_score": rules["min_score"], "weights": cfg["weights"]},
        "market": market,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "today.json").write_text(json.dumps(result, indent=1, allow_nan=False),
                                        encoding="utf-8", newline="\n")
    result["evaluated"] = evaluated  # not in today.json; the tracker logs these
    return result

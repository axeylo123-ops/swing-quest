"""The brain: scores every stock in the universe on six pillars plus a risk
penalty, blends them into one Conviction score (0-100), picks the top ideas,
and writes short, specific, analyst-style notes.

Pillars are ranked against the whole universe (0 = worst, 100 = best), so
"Quality 85" means better than 85% of the ~1,800 stocks we cover.
"""
import math
from datetime import date

import numpy as np
import pandas as pd

from swingquest import events
from swingquest.signals import plan, technicals
from swingquest.signals.scan import ret_over

PILLARS = ["upside", "analysts", "insiders", "quality", "momentum", "value"]
LABEL = {"value": ("expensive", "fair", "cheap")}


# ----------------------------------------------------------------- helpers
def _num(x):
    try:
        x = float(x)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def rank(values: dict, higher_better: bool = True) -> dict:
    """Percentile (0-100) of each value among the non-missing ones."""
    s = pd.Series({k: v for k, v in values.items() if v is not None})
    if s.empty:
        return {}
    r = (s if higher_better else -s).rank(pct=True) * 100
    return r.round(1).to_dict()


def _mean(xs, default=None):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else default


def _money(x, cur="USD"):
    if x is None:
        return "–"
    sign = "C$" if cur == "CAD" else "$"
    a = abs(x)
    if a >= 1e12: return f"{sign}{x / 1e12:.1f}T"
    if a >= 1e9: return f"{sign}{x / 1e9:.1f}B"
    if a >= 1e6: return f"{sign}{x / 1e6:.1f}M"
    if a >= 1e3: return f"{sign}{x / 1e3:.0f}K"
    return f"{sign}{x:.2f}"


def _pct(x, digits=0):
    return "–" if x is None else f"{x * 100:+.{digits}f}%"


def label(pillar: str, score: float | None) -> str:
    if score is None:
        return "n/a"
    words = LABEL.get(pillar, ("weak", "ok", "strong"))
    return words[2] if score >= 70 else words[1] if score >= 45 else words[0]


# ----------------------------------------------------------------- metrics
def stock_metrics(stock: dict, fund: dict, prices: pd.DataFrame | None, spy: pd.DataFrame | None,
                  trade_cfg: dict) -> dict | None:
    """Raw facts for one stock (price-based + fundamentals). None if too little price history."""
    if prices is None or len(prices) < 60:
        return None
    snap = technicals.snapshot(prices.tail(300), trade_cfg["atr_period"])
    if snap is None:
        return None
    day, close = prices.index[-1], float(prices["close"].iloc[-1])
    spy3 = ret_over(spy, day) if spy is not None else None
    r3, r6 = ret_over(prices, day), ret_over(prices, day, 126)
    target = _num(fund.get("targetMeanPrice"))
    high = _num(fund.get("fiftyTwoWeekHigh")) or snap["high52"]
    trade = plan.trade_plan(close, snap["atr"], trade_cfg)
    above200 = None if len(prices) < 200 else close > float(prices["close"].tail(200).mean())
    t = plan.trend_timing(snap, above200)
    adv = float((prices["close"] * prices["volume"]).tail(20).mean())
    return {
        "ticker": stock["ticker"], "name": fund.get("longName") or stock.get("name"), "country": stock.get("country", "US"),
        "sector": stock.get("sector") or fund.get("sector"), "industry": fund.get("industry"),
        "currency": fund.get("currency") or ("CAD" if stock.get("country") == "CA" else "USD"),
        "price": round(close, 2), "as_of": f"{day:%Y-%m-%d}", "adv": adv, "mcap": _num(fund.get("marketCap")),
        "analyst_upside": (target / close - 1) if target and close else None,
        "target": target, "target_high": _num(fund.get("targetHighPrice")),
        "n_analysts": _num(fund.get("numberOfAnalystOpinions")), "rec_mean": _num(fund.get("recommendationMean")),
        "rec_key": fund.get("recommendationKey"),
        "rev_net": _num(fund.get("rev_net_30d")), "rev_up": _num(fund.get("rev_up_30d")), "rev_down": _num(fund.get("rev_down_30d")),
        "surprise_avg": _num(fund.get("surprise_avg")), "beats": _num(fund.get("beats_4q")), "quarters": _num(fund.get("quarters")),
        "op_margin": _num(fund.get("operatingMargins")), "roe": _num(fund.get("returnOnEquity")),
        "de": _num(fund.get("debtToEquity")), "rev_growth": _num(fund.get("revenueGrowth")),
        "eps_growth": _num(fund.get("earningsGrowth")),
        "fcf_pos": None if _num(fund.get("freeCashflow")) is None else float(_num(fund.get("freeCashflow")) > 0),
        "fpe": _num(fund.get("forwardPE")), "ps": _num(fund.get("priceToSalesTrailing12Months")),
        "short_pct": _num(fund.get("shortPercentOfFloat")), "beta": _num(fund.get("beta")),
        "rs_3m": (r3 - spy3) if r3 is not None and spy3 is not None else None, "ret_6m": r6,
        "above50": close > snap["sma50"], "above200": above200,
        "room_to_high": (high / close - 1) if high else None,
        "atr_pct": snap["atr"] / close, "timing": t["label"], "timing_notes": t["notes"], "plan": trade,
        "swing_upside": (trade["target"] / close - 1) if trade else None,
    }


# ----------------------------------------------------------------- pillars
def score_universe(stocks: list[dict], cfg: dict, insider_scores: dict) -> list[dict]:
    """Adds pillars, penalty, Conviction and rank to each metrics dict."""
    by = {s["ticker"]: s for s in stocks}
    col = lambda k: {t: s.get(k) for t, s in by.items()}

    # Upside: analyst target upside (65%) + room to the 52-week high (35%)
    up_a, up_r = rank(col("analyst_upside")), rank(col("room_to_high"))
    # Analysts & earnings
    a_parts = [rank(col("rec_mean"), higher_better=False),
               rank({t: math.log1p(v) if v else None for t, v in col("n_analysts").items()}),
               rank(col("rev_net")), rank(col("surprise_avg")), rank(col("beats"))]
    # Quality
    q_parts = [rank(col("op_margin")), rank(col("roe")), rank(col("de"), higher_better=False),
               rank(col("rev_growth")), rank(col("eps_growth")), rank(col("fcf_pos"))]
    # Momentum
    m_parts = [rank(col("rs_3m")), rank(col("ret_6m"))]
    # Value: within each sector, lower forward P/E and price/sales are better
    v_fpe, v_ps = {}, {}
    for sector in {s.get("sector") for s in stocks}:
        members = [s for s in stocks if s.get("sector") == sector]
        v_fpe.update(rank({s["ticker"]: s["fpe"] for s in members if s["fpe"] and s["fpe"] > 0}, higher_better=False))
        v_ps.update(rank({s["ticker"]: s["ps"] for s in members if s["ps"] and s["ps"] > 0}, higher_better=False))
    # "very volatile" = top 15% of the universe AND moving at least 4% a day on average
    vol_cut = max(float(np.nanpercentile([s["atr_pct"] for s in stocks], 85)), 0.04) if stocks else 1

    w = cfg["pillars"]
    total_w = sum(w.values())
    for t, s in by.items():
        a = up_a.get(t)
        s["pillars"] = p = {
            "upside": (0.65 * a + 0.35 * up_r.get(t, 50)) if a is not None else 0.8 * up_r.get(t, 40),
            "analysts": 30 if not s["n_analysts"] else _mean([part.get(t) for part in a_parts], 40),
            "insiders": insider_scores.get(t, {}).get("score", 50),
            "quality": _mean([part.get(t) for part in q_parts], 40) if sum(part.get(t) is not None for part in q_parts) >= 3 else 40,
            "momentum": _mean([m_parts[0].get(t), m_parts[1].get(t), 50 * bool(s["above50"]) + 50 * bool(s["above200"])], 40),
            "value": _mean([v_fpe.get(t), v_ps.get(t)], 25),
        }
        flags, pen = [], 0
        if s["atr_pct"] >= vol_cut:
            pen += 5; flags.append(f"very volatile: moves about {s['atr_pct'] * 100:.1f}% a day")
        if s["mcap"] is not None and s["mcap"] < 3e8:
            pen += 6; flags.append(f"tiny company ({_money(s['mcap'], s['currency'])})")
        elif s["mcap"] is not None and s["mcap"] < 1e9:
            pen += 4; flags.append(f"small company ({_money(s['mcap'], s['currency'])})")
        if s["de"] is not None and s["de"] > 200:
            pen += 3; flags.append(f"heavy debt (debt is {s['de'] / 100:.1f}x equity)")
        if s["short_pct"] is not None and s["short_pct"] > 0.2:
            pen += 2; flags.append(f"{s['short_pct'] * 100:.0f}% of shares sold short")
        if not s["n_analysts"]:
            pen += 2; flags.append("no analyst coverage")
        if s.get("earnings_in_window"):
            pen += 3; flags.append(f"earnings on {s['earnings_in_window']}, inside the trade window")
        s["penalty"] = min(pen, cfg.get("risk_max_penalty", 15))
        s["flags"] = flags
        bonus = cfg.get("canada_bonus", 0) if s["country"] == "CA" else 0
        s["conviction"] = round(max(0, min(100, sum(w[k] * p[k] for k in PILLARS) / total_w - s["penalty"] + bonus)), 1)
        s["pillars"] = {k: round(v, 1) for k, v in p.items()}
    ordered = sorted(by.values(), key=lambda s: -s["conviction"])
    for i, s in enumerate(ordered, 1):
        s["rank"] = i
    return ordered


# ----------------------------------------------------------------- verdicts
def verdict(s: dict, rules: dict) -> tuple[str, str]:
    """(verdict, short reason) for a new buy."""
    best_up = max(x for x in (s["analyst_upside"] or -1, s["swing_upside"] or -1))
    if s["pillars"]["quality"] < rules["min_quality"]:
        return "Avoid", "weak business (quality in the bottom quarter)"
    if s["atr_pct"] > rules.get("max_daily_move", 1):
        return "Avoid", f"too volatile for a swing plan (moves {s['atr_pct'] * 100:.1f}% a day)"
    if s["penalty"] > rules["max_penalty"]:
        return "Avoid", "too risky: " + ", ".join(s["flags"][:2])
    if best_up < rules["min_upside"]:
        return "Limited upside", f"analysts see {_pct(s['analyst_upside'])}"
    if s["timing"] == "Wait":
        return "Watch", (s["timing_notes"][0].split(":")[0].lower() + ": wait") if s.get("timing_notes") else "wait for it to turn up"
    if s["timing"] == "Extended":
        return "Don't chase", "ran up too fast: wait for a pullback"
    if s["conviction"] < rules.get("min_conviction", 0):
        return "Neutral", f"passes the checks but ranks mid-pack (conviction {s['conviction']:.0f})"
    return "Buy candidate", "high conviction and passes every check"


def hold_verdict(s: dict) -> tuple[str, str]:
    """What to do if you already own it."""
    p = s["pillars"]
    if s["analyst_upside"] is not None and s["analyst_upside"] < 0.03 and s["n_analysts"]:
        return "Trim?", f"near the analyst target ({_money(s['target'], s['currency'])}, {_pct(s['analyst_upside'])})"
    if s["above200"] is False and (s["rs_3m"] or 0) < 0:
        return "Review", "trend broken: below its 200-day average and lagging the market"
    if s["conviction"] < 35:
        return "Review", "weak on most pillars"
    strong = [k for k in PILLARS if p[k] >= 70 and k != "insiders"] + (["insiders"] if p["insiders"] >= 70 else [])
    if s.get("verdict") == "Buy candidate":
        return "Add", "a top-ranked buy right now"
    return "Hold", ("strong " + " and ".join(strong[:2])) if strong else "nothing alarming"


# ----------------------------------------------------------------- notes
def note(s: dict, insider: dict | None) -> dict:
    """Short, specific lines a human analyst would write. Numbers, not adjectives."""
    cur, p, lines = s["currency"], s["pillars"], {}
    head = [s["ticker"], s["name"] or ""]
    if s["industry"]: head.append(s["industry"])
    if s["mcap"]: head.append(_money(s["mcap"], cur))
    lines["head"] = " · ".join(h for h in head if h)

    if s["n_analysts"] and s["target"]:
        rk = (s["rec_key"] or "").replace("_", " ")
        lines["upside"] = (f"{int(s['n_analysts'])} analysts{(' rate it ' + rk.title()) if rk and rk != 'none' else ''}, "
                           f"average target {_money(s['target'], cur)} ({_pct(s['analyst_upside'])})")
    else:
        lines["upside"] = "No analyst coverage"
    if s["plan"]:
        lines["upside"] += f" · swing target {_money(s['plan']['target'], cur)} ({_pct(s['swing_upside'])}) within 15 trading days"

    est = []
    if s["rev_up"] is not None:
        est.append(f"estimates: {int(s['rev_up'])} raised, {int(s['rev_down'] or 0)} cut in the last 30 days")
    if s["beats"] is not None and s["quarters"]:
        est.append(f"beat {int(s['beats'])} of the last {int(s['quarters'])} quarters (avg surprise {_pct(s['surprise_avg'])})")
    lines["earnings"] = "; ".join(est) if est else None

    if insider and insider.get("facts"):
        f = insider["facts"]
        others = f["insiders"] - 1
        since = ""
        if f.get("avg_price"):
            since = f", avg ${f['avg_price']:.2f} (now {_money(s['price'], cur)}, {_pct(s['price'] / f['avg_price'] - 1)})"
        lines["insiders"] = (f"{f['top_role']} {f['top_name'].title()}{f' + {others} other' + ('s' if others > 1 else '') if others else ''} "
                             f"bought {_money(f['dollars'])} in 60 days{since}")
    elif insider and insider.get("excluded"):
        lines["insiders"] = f"No genuine insider buying ({len(insider['excluded'])} plan or mismatched purchases ignored)"
    else:
        lines["insiders"] = "No insider buying in the last 60 days" if s["country"] == "US" else "Insider data not covered for Canadian listings"

    q = []
    if s["op_margin"] is not None: q.append(f"{s['op_margin'] * 100:.0f}% operating margin")
    if s["roe"] is not None: q.append(f"{s['roe'] * 100:.0f}% return on equity")
    if s["de"] is not None: q.append(f"debt {s['de'] / 100:.1f}x equity")
    if s["rev_growth"] is not None: q.append(f"revenue {_pct(s['rev_growth'])}")
    lines["quality"] = (label("quality", p["quality"]).capitalize() + ": " + ", ".join(q)) if q else "No fundamentals"

    mo = []
    if s["rs_3m"] is not None: mo.append(f"{_pct(s['rs_3m'])} vs the market over 3 months")
    mo.append("above" if s["above50"] else "below")
    mo[-1] += " its 50-day"
    if s["above200"] is not None: mo[-1] += " and " + ("above" if s["above200"] else "below") + " its 200-day average"
    lines["momentum"] = label("momentum", p["momentum"]).capitalize() + ": " + ", ".join(mo)

    lines["value"] = (label("value", p["value"]).capitalize() + ": " +
                      (f"{s['fpe']:.0f}x forward earnings" if s["fpe"] and s["fpe"] > 0 else "no forward earnings (loss-making or not covered)"))
    lines["risks"] = s["flags"] or ["nothing unusual"]
    return lines


# ----------------------------------------------------------------- pipeline
def build_board(stocks: list[dict], funds: dict, price_data: dict, insider_scores: dict, cfg: dict,
                trade_cfg: dict, earnings_lookup=None) -> dict:
    """Everything the dashboard needs: ranked universe, top ideas, watchlist."""
    spy = price_data.get("SPY")
    rules = cfg["ideas"]
    metrics = []
    for st in stocks:
        m = stock_metrics(st, funds.get(st["ticker"], {}), price_data.get(st["ticker"]), spy, trade_cfg)
        if m is None:
            continue
        min_adv = rules["min_dollar_volume_ca"] if m["country"] == "CA" else rules["min_dollar_volume_us"]
        if m["price"] < 2 or m["adv"] < min_adv:
            continue
        metrics.append(m)
    ranked = score_universe(metrics, cfg, insider_scores)

    # earnings check for the leaders (a few cached lookups), then re-score
    if earnings_lookup is not None:
        for s in ranked[:60]:
            dates = earnings_lookup(s["ticker"])
            hit = events.in_window(dates, s["as_of"]) if dates else None
            if hit:
                s["earnings_in_window"] = hit
        ranked = score_universe(metrics, cfg, insider_scores)

    for s in ranked:
        s["verdict"], s["why"] = verdict(s, rules)
        s["hold"], s["hold_why"] = hold_verdict(s)
    top, sectors = [], set()
    for s in ranked:                       # best buy candidates, one per sector
        if s["verdict"] == "Buy candidate" and s.get("sector") not in sectors:
            top.append(s); sectors.add(s.get("sector"))
        if len(top) >= rules["top_n"]:
            break
    # watchlist: the next best that are worth your attention (no Avoid / Limited upside)
    watch = [s for s in ranked if s not in top and s["verdict"] not in ("Avoid", "Limited upside")][: rules["watch_n"]]
    for s in top + watch:
        s["note"] = note(s, insider_scores.get(s["ticker"]))
    return {"ranked": ranked, "top": top, "watch": watch}

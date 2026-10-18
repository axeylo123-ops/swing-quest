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
SPLIT_GUARD = 0.35   # cached fundamentals priced >35% away from today's close = stale (e.g. a split)


def stock_metrics(stock: dict, fund: dict, prices: pd.DataFrame | None, spy: pd.DataFrame | None,
                  trade_cfg: dict) -> dict | None:
    """Raw facts for one stock (price-based + fundamentals). None if too little or stale price history."""
    if prices is None or len(prices) < 60:
        return None
    if spy is not None and len(spy) and (spy.index[-1] - prices.index[-1]).days > 5:
        return None                       # no fresh prices (halted, acquired, or a data gap)
    snap = technicals.snapshot(prices.tail(300), trade_cfg["atr_period"])
    if snap is None:
        return None
    day, close = prices.index[-1], float(prices["close"].iloc[-1])
    spy3 = ret_over(spy, day) if spy is not None else None
    r3, r6 = ret_over(prices, day), ret_over(prices, day, 126)
    # price-based Yahoo fields are only trusted if Yahoo's price matches ours (guards against splits)
    fprice = _num(fund.get("currentPrice"))
    fresh = fprice is not None and abs(close / fprice - 1) <= SPLIT_GUARD
    target = _num(fund.get("targetMeanPrice")) if fresh else None
    high = (_num(fund.get("fiftyTwoWeekHigh")) if fresh else None) or snap["high52"]
    trade = plan.level_plan(prices.tail(260), snap["atr"], trade_cfg["min_reward_risk"], trade_cfg["time_stop_days"])
    above200 = None if len(prices) < 200 else close > float(prices["close"].tail(200).mean())
    t = plan.trend_timing(snap, above200)
    adv = float((prices["close"] * prices["volume"]).tail(20).mean())
    de = _num(fund.get("debtToEquity"))
    n = _num(fund.get("numberOfAnalystOpinions"))
    up, down = _num(fund.get("rev_up_30d")), _num(fund.get("rev_down_30d"))

    def surprise(k):
        v = _num(fund.get(k))
        return None if v is None else max(-0.5, min(0.5, v))

    return {
        "ticker": stock["ticker"], "name": fund.get("longName") or stock.get("name"), "country": stock.get("country", "US"),
        "sector": stock.get("sector") or fund.get("sector"), "industry": fund.get("industry"),
        "currency": fund.get("currency") or ("CAD" if stock.get("country") == "CA" else "USD"),
        "price": round(close, 2), "as_of": f"{day:%Y-%m-%d}", "adv": adv, "mcap": _num(fund.get("marketCap")),
        "analyst_upside": (target / close - 1) if target and close else None,
        "target": target, "target_low": _num(fund.get("targetLowPrice")) if fresh else None,
        "target_high": _num(fund.get("targetHighPrice")) if fresh else None,
        "n_analysts": n, "rec_mean": _num(fund.get("recommendationMean")), "rec_key": fund.get("recommendationKey"),
        "rev_up": up, "rev_down": down, "rev_net": None if up is None else up - (down or 0),
        # revisions per analyst, so heavily covered mega-caps don't win on raw counts
        "rev_ratio": None if up is None else (up - (down or 0)) / max(n or 0, up + (down or 0), 1),
        "eps_trend": _num(fund.get("eps_trend_30d")),
        "surprise_avg": surprise("surprise_avg"), "surprise_last": surprise("surprise_last"),
        "beats": _num(fund.get("beats_4q")), "quarters": _num(fund.get("quarters")),
        "op_margin": _num(fund.get("operatingMargins")), "roe": _num(fund.get("returnOnEquity")),
        "de": de if de is not None and de >= 0 else None,       # negative = negative equity: treat as unknown
        "rev_growth": _num(fund.get("revenueGrowth")), "eps_growth": _num(fund.get("earningsGrowth")),
        "fcf_pos": None if _num(fund.get("freeCashflow")) is None else float(_num(fund.get("freeCashflow")) > 0),
        "fpe": _num(fund.get("forwardPE")), "ps": _num(fund.get("priceToSalesTrailing12Months")),
        "short_pct": _num(fund.get("shortPercentOfFloat")), "beta": _num(fund.get("beta")),
        "rs_3m": (r3 - spy3) if r3 is not None and spy3 is not None else None, "ret_6m": r6,
        "above50": close > snap["sma50"], "above200": above200,
        "room_to_high": (high / close - 1) if high else None,
        "near_high": (close / high) if high else None,          # 1.0 = at the 52-week high
        "atr_pct": snap["atr"] / close, "timing": t["label"], "timing_notes": t["notes"], "plan": trade,
        "swing_upside": (trade["target"] / close - 1) if trade else None,
        "atr": snap["atr"],
    }


# ----------------------------------------------------------------- pillars
UPSIDE_CAP = 0.40


def realistic_upside(s: dict) -> float | None:
    """Analyst upside you can lean on: trusted in proportion to how many
    analysts cover it (full trust at 6+), capped at +40% (bigger gaps are
    usually stale targets after a fall), and discounted when analysts
    disagree widely (high minus low target, relative to the average)."""
    up, n = s.get("analyst_upside"), s.get("n_analysts") or 0
    if up is None:
        return None
    cred = min(1.0, n / 6)
    capped = min(up, UPSIDE_CAP)
    if s.get("target_high") and s.get("target_low") and s.get("target"):
        disp = (s["target_high"] - s["target_low"]) / s["target"]
    else:
        disp = 0.5
    return cred * capped / (1 + max(0.0, disp))


def _group_rank(stocks, key_fn, value_key, min_size=8, higher_better=False):
    """Rank within peer groups (industry, then sector), falling back to the
    whole universe when a group is too small to compare fairly."""
    out, groups = {}, {}
    for s in stocks:
        v = s.get(value_key)
        if v and v > 0:
            groups.setdefault(key_fn(s), []).append(s)
    whole = rank({s["ticker"]: s[value_key] for s in stocks if s.get(value_key) and s[value_key] > 0}, higher_better)
    for g, members in groups.items():
        if g is None or len(members) < min_size:
            for m in members:
                out[m["ticker"]] = whole.get(m["ticker"])
        else:
            out.update(rank({m["ticker"]: m[value_key] for m in members}, higher_better))
    return out


def estimates_cut(s: dict) -> bool:
    """Analysts clearly turning negative: cuts outnumber raises 2:1 (3+ cuts),
    or the current-year EPS estimate fell more than 3% in 30 days."""
    down, up = s.get("rev_down") or 0, s.get("rev_up") or 0
    return (down >= 3 and down >= 2 * up) or (s.get("eps_trend") is not None and s["eps_trend"] < -0.03)


def score_universe(stocks: list[dict], cfg: dict, insider_scores: dict) -> list[dict]:
    """Adds pillars, penalty, Conviction and rank to each metrics dict."""
    by = {s["ticker"]: s for s in stocks}

    def col(k):
        return {t: s.get(k) for t, s in by.items()}

    # Upside: realistic analyst upside only (capped, coverage- and dispersion-adjusted)
    for st in stocks:
        st["upside_real"] = realistic_upside(st)
    up_a = rank(col("upside_real"))
    # Analysts & earnings: rating, coverage, revisions per analyst, estimate trend, surprises, beats
    a_parts = [rank(col("rec_mean"), higher_better=False),
               rank({t: math.log1p(v) if v else None for t, v in col("n_analysts").items()}),
               rank(col("rev_ratio")), rank(col("eps_trend")), rank(col("surprise_avg")), rank(col("beats"))]
    # Quality
    q_parts = [rank(col("op_margin")), rank(col("roe")), rank(col("de"), higher_better=False),
               rank(col("rev_growth")), rank(col("eps_growth")), rank(col("fcf_pos"))]
    # Momentum: relative strength, 6-month return, nearness to the 52-week high (stocks near highs tend to keep going)
    m_parts = [rank(col("rs_3m")), rank(col("ret_6m")), rank(col("near_high"))]

    # Value: within industry (or sector), lower forward P/E and price/sales are better
    def peer(s):
        return s.get("industry") or s.get("sector")
    v_fpe, v_ps = _group_rank(stocks, peer, "fpe"), _group_rank(stocks, peer, "ps")
    # "very volatile" = top 15% of the universe AND moving at least 4% a day on average
    vol_cut = max(float(np.nanpercentile([s["atr_pct"] for s in stocks], 85)), 0.04) if stocks else 1

    w = cfg["pillars"]
    total_w = sum(w.values())
    for t, s in by.items():
        a = up_a.get(t)
        trend = 50 * bool(s["above50"]) + (25 if s["above200"] is None else 50 * bool(s["above200"]))
        s["pillars"] = p = {
            "upside": a if a is not None else 20,
            "analysts": 30 if not s["n_analysts"] else _mean([part.get(t) for part in a_parts], 40),
            "insiders": insider_scores.get(t, {}).get("score", 50),
            "quality": _mean([part.get(t) for part in q_parts], 40) if sum(part.get(t) is not None for part in q_parts) >= 3 else 40,
            "momentum": _mean([m_parts[0].get(t), m_parts[1].get(t), m_parts[2].get(t), trend], 40),
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
        if estimates_cut(s):
            pen += 4; flags.append("analysts are cutting estimates")
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
    # with analyst coverage, the analysts' (realistic) upside must clear the bar; else the plan target
    up = s["upside_real"] if s["n_analysts"] and s.get("upside_real") is not None else s["swing_upside"]
    if s["pillars"]["quality"] < rules["min_quality"]:
        return "Avoid", "weak business (quality in the bottom quarter)"
    if s["atr_pct"] > rules.get("max_daily_move", 1):
        return "Avoid", f"too volatile for a swing plan (moves {s['atr_pct'] * 100:.1f}% a day)"
    if estimates_cut(s):
        return "Avoid", "analysts are cutting their estimates"
    if s["penalty"] > rules["max_penalty"]:
        return "Avoid", "too risky: " + ", ".join(s["flags"][:2])
    if up is None or up < rules["min_upside"]:
        return "Limited upside", f"realistic upside {_pct(up)}"
    if s["timing"] == "Wait":
        note0 = (s.get("timing_notes") or ["wait for it to turn up"])[0]
        return "Watch", note0.split(":")[0].lower() + ": wait"
    if s["timing"] == "Extended":
        return "Don't chase", "ran up too fast: wait for a pullback"
    if s["above200"] is False and (s["rs_3m"] or 0) < 0:
        return "Watch", "below its 200-day average and lagging the market: wait for strength"
    if s.get("earnings_in_window"):
        return "Watch", f"earnings on {s['earnings_in_window']}: wait for the report before buying"
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
def catalyst(s: dict) -> str | None:
    """What could move it soon: a fresh earnings beat with rising estimates
    (a known short-term edge), and when it reports next."""
    bits = []
    if s.get("surprise_last") is not None and s["surprise_last"] >= 0.05 and (s.get("rev_net") or 0) > 0:
        bits.append(f"beat last quarter by {_pct(s['surprise_last'])} and estimates are rising since")
    if s.get("next_earnings"):
        days = (date.fromisoformat(s["next_earnings"]) - date.fromisoformat(s["as_of"])).days
        if 0 <= days <= 60:
            bits.append(f"next earnings {s['next_earnings']} (in {days} days)")
    return "; ".join(bits).capitalize() if bits else None


def note(s: dict, insider: dict | None) -> dict:
    """Short, specific lines a human analyst would write. Numbers, not adjectives."""
    cur, p, lines = s["currency"], s["pillars"], {}
    head = [s["ticker"], s["name"] or ""]
    if s["industry"]: head.append(s["industry"])
    if s["mcap"]: head.append(_money(s["mcap"], cur))
    lines["head"] = " · ".join(h for h in head if h)

    if s["n_analysts"] and s["target"]:
        rk = (s["rec_key"] or "").replace("_", " ")
        rng = (f", range {_money(s['target_low'], cur)}–{_money(s['target_high'], cur)}"
               if s.get("target_low") and s.get("target_high") and s["n_analysts"] > 1 else "")
        lines["upside"] = (f"{int(s['n_analysts'])} analyst{'s' if s['n_analysts'] > 1 else ''}"
                           f"{(' rate it ' + rk.title()) if rk and rk != 'none' else ''}, "
                           f"average target {_money(s['target'], cur)} ({_pct(s['analyst_upside'])}{rng})")
    else:
        lines["upside"] = "No analyst coverage"
    if s["plan"]:
        lines["upside"] += (f" · plan target {_money(s['plan']['target'], cur)} ({_pct(s['swing_upside'])}, {s['plan'].get('target_basis', '')}) "
                            f"within {s['plan']['time_stop_days']} trading days")

    est = []
    if s["rev_up"] is not None:
        est.append(f"estimates: {int(s['rev_up'])} raised, {int(s['rev_down'] or 0)} cut in the last 30 days")
    if s["beats"] is not None and s["quarters"]:
        est.append(f"beat {int(s['beats'])} of the last {int(s['quarters'])} quarters (avg surprise {_pct(s['surprise_avg'])})")
    lines["earnings"] = "; ".join(est) if est else None
    lines["catalyst"] = catalyst(s)

    if insider and insider.get("facts"):
        f = insider["facts"]
        others = f["insiders"] - 1
        since = ""
        if f.get("avg_price"):
            since = f", avg ${f['avg_price']:.2f} (now {_money(s['price'], cur)}, {_pct(s['price'] / f['avg_price'] - 1)})"
        lines["insiders"] = (f"{f['top_role']} {(f.get('top_name') or 'an insider').title()}{f' + {others} other' + ('s' if others > 1 else '') if others else ''} "
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


# ----------------------------------------------------------------- high-upside lane
def high_upside(ranked: list[dict], price_data: dict, cfg: dict, exclude: set) -> list[dict]:
    """Realistic +50%+ candidates, not lottery tickets.
    Potential = the average target of 3+ analysts (a far-away 52-week high is
    NOT potential: it's usually where the stock fell from). Needs 2+ separate
    catalysts (genuine insider buying, rising estimates, a big beat, a
    breakout), price above its 50-day average, analysts not cutting, a real
    business (not tiny, growing or cash-generating) and sane volatility."""
    hu = cfg.get("high_upside", {})
    found = []
    for s in ranked:
        if s["ticker"] in exclude:
            continue
        pot = s["analyst_upside"] if (s["n_analysts"] or 0) >= 3 else None
        if pot is None or pot < hu.get("min_potential", 0.5):
            continue
        ready = s["timing"] == "Ready" and bool(s["above50"])
        if s["pillars"]["quality"] < hu.get("min_quality", 15) or s["atr_pct"] > hu.get("max_daily_move", 0.10):
            continue
        if estimates_cut(s) or (s["mcap"] is not None and s["mcap"] < 3e8):
            continue
        if not ((s["rev_growth"] or 0) > 0 or s["fcf_pos"]):       # shrinking AND burning cash = junk
            continue
        cats = []
        if s["pillars"]["insiders"] >= 65: cats.append("genuine insider buying")
        if (s["rev_net"] or 0) >= 2: cats.append("analysts raising estimates")
        if (s["surprise_last"] or 0) >= 0.10: cats.append(f"beat last quarter by {_pct(s['surprise_last'])}")
        if (s["rs_3m"] or 0) >= 0.10 and s["above200"]: cats.append("breaking out vs the market")
        if len(cats) < hu.get("min_catalysts", 2):
            continue
        df = price_data.get(s["ticker"])
        if df is None:
            continue
        p = plan.level_plan(df.loc[:s["as_of"]].tail(260), s["atr"], 2.0, hu.get("time_stop_days", 30),
                            hu.get("stop_atr", 3.0), target_hint=s.get("target"))
        if not p:
            continue
        pick = dict(s)
        pick.update({
            "potential": round(pot, 4), "catalysts": cats, "plan": p, "swing_upside": p["target"] / s["price"] - 1,
            "hu_ready": ready,
            "verdict": "High-upside" if ready else "High-upside: wait",
            "why": ("catalysts: " + ", ".join(cats)) if ready else
                   ((s.get("timing_notes") or ["not turned up yet"])[0].split(":")[0] + ": wait for it to turn up and clear its 50-day average"),
            "hu_score": round(0.45 * s["pillars"]["upside"] + 0.20 * s["pillars"]["momentum"]
                              + 0.20 * max(s["pillars"]["insiders"], s["pillars"]["analysts"])
                              + 0.15 * s["pillars"]["quality"] - s["penalty"] / 2, 1),
        })
        found.append(pick)
    found.sort(key=lambda x: -x["hu_score"])

    def pick(items):
        out, sectors = [], set()
        for s in items:                     # one per sector
            if s.get("sector") not in sectors:
                out.append(s); sectors.add(s.get("sector"))
            if len(out) >= hu.get("n", 3):
                break
        return out
    # ready to buy now, and the best ones still waiting for their chart to turn up
    return pick([s for s in found if s["hu_ready"]]), pick([s for s in found if not s["hu_ready"]])


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

    def earnings(s, days=15):
        dates = earnings_lookup(s["ticker"]) if earnings_lookup else []
        s["next_earnings"] = next((d for d in dates if d > s["as_of"]), None)
        hit = events.in_window(dates, s["as_of"], days) if dates else None
        if hit:
            s["earnings_in_window"] = hit
        checked.add(s["ticker"])

    def select(ranked):
        for s in ranked:
            s["verdict"], s["why"] = verdict(s, rules)
            s["hold"], s["hold_why"] = hold_verdict(s)
        top, sectors = [], set()
        for s in ranked:                       # best buy candidates, one per sector
            if s["verdict"] == "Buy candidate" and s.get("sector") not in sectors:
                top.append(s); sectors.add(s.get("sector"))
            if len(top) >= rules["top_n"]:
                break
        # watchlist: the next best worth your attention (no Avoid / Limited upside), max 2 per industry
        watch, per = [], {}
        for s in ranked:
            if s in top or s["verdict"] in ("Avoid", "Limited upside"):
                continue
            key = s.get("industry") or s.get("sector")
            if per.get(key, 0) >= rules.get("watch_per_industry", 2):
                continue
            watch.append(s); per[key] = per.get(key, 0) + 1
            if len(watch) >= rules["watch_n"]:
                break
        return top, watch

    # earnings dates for the leaders, then for anything selected that wasn't checked yet
    # (a report inside the window can change the verdict, so re-score and re-select until stable)
    checked = set()
    if earnings_lookup is not None:
        for s in ranked[:60]:
            earnings(s)
        ranked = score_universe(metrics, cfg, insider_scores)
    top, watch = select(ranked)
    for _ in range(6):
        if earnings_lookup is None:
            break
        new = [s for s in top + watch if s["ticker"] not in checked]
        if not new:
            break
        for s in new:
            earnings(s)
        ranked = score_universe(metrics, cfg, insider_scores)
        top, watch = select(ranked)
    high, high_wait = high_upside(ranked, price_data, cfg, {s["ticker"] for s in top})
    for s in high + high_wait:
        earnings(s, s["plan"]["time_stop_days"])
        if s.get("earnings_in_window"):
            s["flags"] = s["flags"] + [f"earnings on {s['earnings_in_window']}, inside the trade window"]
    for s in top + watch + high + high_wait:
        s["note"] = note(s, insider_scores.get(s["ticker"]))
    return {"ranked": ranked, "top": top, "watch": watch, "high": high, "high_wait": high_wait}

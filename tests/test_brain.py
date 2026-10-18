"""Phase 9: universe, fundamentals cache, clean insider signal, the brain."""
import pandas as pd
import pytest

from swingquest import brain, fundamentals, insider_signal, stocklist

CFG = {"pillars": {"upside": 25, "analysts": 15, "insiders": 15, "quality": 15, "momentum": 15, "value": 10},
       "risk_max_penalty": 15, "canada_bonus": 3,
       "ideas": {"top_n": 3, "watch_n": 12, "min_upside": 0.08, "min_quality": 25, "max_penalty": 9,
                 "min_dollar_volume_us": 1e7, "min_dollar_volume_ca": 3e6}}


# ---------------- universe ----------------

def test_yahoo_tickers():
    assert stocklist.yahoo_ticker("BRK.B", "US") == "BRK-B"
    assert stocklist.yahoo_ticker("BBD.B", "CA") == "BBD-B.TO"
    assert stocklist.yahoo_ticker("RY", "CA") == "RY.TO"
    assert stocklist.yahoo_ticker("nan", "US") is None


def test_members_table_picks_constituents_not_changes():
    html = """<table><tr><th>Date</th><th>Added</th></tr>""" + "".join(f"<tr><td>d</td><td>X{i}</td></tr>" for i in range(200)) + """</table>
    <table><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th></tr>""" + "".join(
        f"<tr><td>T{i}</td><td>Co {i}</td><td>Energy</td></tr>" for i in range(160)) + "</table>"
    tbl = stocklist._members(html)
    assert tbl is not None and len(tbl) == 160 and "_ticker" in tbl.columns


# ---------------- fundamentals ----------------

def test_estimate_summary():
    rev = pd.DataFrame({"upLast30days": [1, 0, 2, 1], "downLast30days": [0, 1, 0, 1]})
    hist = pd.DataFrame({"surprisePercent": [0.05, -0.02, 0.10, 0.08]})
    s = fundamentals.summarize_estimates(rev, hist)
    assert s["rev_up_30d"] == 4 and s["rev_down_30d"] == 2 and s["rev_net_30d"] == 2
    assert s["beats_4q"] == 3 and s["surprise_last"] == 0.08


def test_refresh_stops_when_yahoo_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentals, "FILE", tmp_path / "f.json")
    calls = []
    def fetch(t):
        calls.append(t)
        raise RuntimeError("429")
    done = fundamentals.refresh_info([f"T{i}" for i in range(30)], budget=30, fetch=fetch, pause=0, progress=None)
    assert done == 0 and len(calls) == 8          # gave up after 8 refusals in a row


def test_refresh_saves_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentals, "FILE", tmp_path / "f.json")
    fundamentals.refresh_info(["AAA"], fetch=lambda t: {"currentPrice": 10, "targetMeanPrice": 12, "junk": 1}, pause=0, progress=None)
    row = fundamentals.load()["AAA"]
    assert row["targetMeanPrice"] == 12 and "junk" not in row and row["info_at"]


# ---------------- clean insider signal ----------------

def buy(owner, value=175_000.0, price=220.0, filed="2026-10-13", role="Director", plan=False):
    return {"owner_cik": owner, "owner_name": f"P{owner}", "role": role, "value": value, "avg_price": price,
            "shares": value / price, "filed_date": filed, "trade_date": filed, "plan_10b5_1": plan,
            "pct_of_holdings": 0.1, "holdings_before": 100}


def closes(price):
    return pd.DataFrame({"close": [price] * 5}, index=pd.bdate_range("2026-10-08", periods=5))


def test_identical_same_day_buys_are_a_plan_not_conviction():
    p = insider_signal.pillar([buy(str(i)) for i in range(5)], closes(220))
    assert p["score"] == 50 and len(p["excluded"]) == 5 and "plan" in p["excluded"][0]["why"]


def test_price_mismatch_is_excluded():
    p = insider_signal.pillar([buy("1", price=3.3)], closes(79.0))
    assert p["score"] == 50 and "vs market" in p["excluded"][0]["why"]


def test_genuine_ceo_cluster_scores_high():
    bs = [buy("1", 2_000_000, role="CEO"), buy("2", 300_000, filed="2026-10-12"), buy("3", 150_000, filed="2026-10-09")]
    p = insider_signal.pillar(bs, closes(221))
    assert p["score"] >= 80 and p["facts"]["insiders"] == 3 and p["facts"]["top_role"] == "CEO"


def test_10b5_1_plans_ignored():
    assert insider_signal.pillar([buy("1", plan=True)], closes(220))["score"] == 50


# ---------------- the brain ----------------

def test_rank_percentiles():
    r = brain.rank({"a": 1, "b": 2, "c": 3, "d": None})
    assert r["c"] == 100 and r["a"] < r["b"] < r["c"] and "d" not in r
    assert brain.rank({"a": 1, "b": 2}, higher_better=False)["a"] == 100


def metric(t, **kw):
    m = {"ticker": t, "name": t, "country": "US", "sector": "Tech", "industry": "Software", "currency": "USD", "price": 50.0,
         "as_of": "2026-10-16", "adv": 5e7, "mcap": 5e9, "analyst_upside": 0.2, "target": 60.0, "target_high": 70.0,
         "n_analysts": 10, "rec_mean": 2.0, "rec_key": "buy", "rev_net": 1, "rev_up": 2, "rev_down": 1, "surprise_avg": 0.05,
         "beats": 3, "quarters": 4, "op_margin": 0.2, "roe": 0.15, "de": 50, "rev_growth": 0.1, "eps_growth": 0.1,
         "fcf_pos": 1.0, "fpe": 20, "ps": 3, "short_pct": 0.02, "beta": 1.0, "rs_3m": 0.05, "ret_6m": 0.1, "above50": True,
         "above200": True, "room_to_high": 0.1, "atr_pct": 0.02, "timing": "Ready", "timing_notes": [], "swing_upside": 0.12,
         "plan": {"target": 56.0, "stop": 47.0, "entry_low": 49.5, "entry_high": 51.0, "time_stop_days": 15}}
    m.update(kw)
    return m


def test_better_stock_gets_higher_conviction_and_canada_bonus():
    good = metric("GOOD", analyst_upside=0.4, op_margin=0.35, rs_3m=0.2)
    meh = metric("MEH", analyst_upside=0.02, op_margin=0.02, rs_3m=-0.2, above50=False, above200=False)
    ca = metric("MEH.TO", analyst_upside=0.02, op_margin=0.02, rs_3m=-0.2, above50=False, above200=False, country="CA")
    ranked = brain.score_universe([good, meh, ca], CFG, {})
    by = {s["ticker"]: s for s in ranked}
    assert ranked[0]["ticker"] == "GOOD" and by["GOOD"]["rank"] == 1
    assert by["MEH.TO"]["conviction"] == pytest.approx(by["MEH"]["conviction"] + 3, abs=0.2)
    assert set(by["GOOD"]["pillars"]) == set(brain.PILLARS)


def test_risk_penalty_and_flags():
    tiny = metric("TINY", mcap=2e8, de=300, short_pct=0.3, n_analysts=None)
    t = [x for x in brain.score_universe([tiny, metric("OK")], CFG, {}) if x["ticker"] == "TINY"][0]
    assert t["penalty"] == 13 and any("tiny" in f for f in t["flags"]) and any("debt" in f for f in t["flags"])


@pytest.mark.parametrize("kw,expected", [
    ({}, "Buy candidate"), ({"timing": "Wait"}, "Watch"), ({"timing": "Extended"}, "Don't chase"),
    ({"analyst_upside": 0.01, "swing_upside": 0.05}, "Limited upside"),
])
def test_verdicts(kw, expected):
    s = brain.score_universe([metric("X", **kw), metric("Y"), metric("Z")], CFG, {})
    x = [r for r in s if r["ticker"] == "X"][0]
    assert brain.verdict(x, CFG["ideas"])[0] == expected


def test_hold_verdicts():
    s = brain.score_universe([metric("A"), metric("B", analyst_upside=0.01), metric("C", above200=False, rs_3m=-0.4, ret_6m=-0.4)], CFG, {})
    by = {r["ticker"]: r for r in s}
    for r in s:
        r["verdict"] = brain.verdict(r, CFG["ideas"])[0]
    assert brain.hold_verdict(by["B"])[0] == "Trim?"
    assert brain.hold_verdict(by["C"])[0] == "Review"


def test_note_is_specific():
    s = brain.score_universe([metric("A"), metric("B")], CFG, {})[0]
    n = brain.note(s, {"facts": {"insiders": 2, "dollars": 1.2e6, "top_role": "CEO", "top_name": "JANE DOE", "avg_price": 45.0}})
    assert "10 analysts" in n["upside"] and "+20%" in n["upside"]
    assert "CEO Jane Doe + 1 other bought $1.2M" in n["insiders"] and "(now $50.00, +11%)" in n["insiders"]
    assert "operating margin" in n["quality"] and "20x forward earnings" in n["value"]


# ---------------- live idea tracking ----------------

def idea(t, as_of="2026-10-16", conv=80):
    return {"ticker": t, "as_of": as_of, "conviction": conv, "rank": 1, "verdict": "Buy candidate", "timing": "Ready",
            "country": "US", "sector": "Tech", "pillars": {k: 60.0 for k in brain.PILLARS},
            "plan": {"reference": 100.0, "stop": 96.0, "entry_low": 99.5, "entry_high": 101.0, "target": 111.0, "time_stop_days": 15}}


def test_board_log_once_per_stock_and_upgrade(monkeypatch):
    from swingquest import board_track
    rows, added = board_track.log({"top": [idea("AAA")], "watch": [idea("BBB")]}, rows=[])
    assert added == 2 and {r["kind"] for r in rows} == {"top", "watch"}
    assert rows[0]["atr"] == pytest.approx(2.0) and rows[0]["upside_frac"] == 0.6
    rows, added = board_track.log({"top": [idea("AAA", "2026-10-19"), idea("BBB", "2026-10-19")], "watch": []}, rows=rows)
    assert added == 0
    assert [r["kind"] for r in rows if r["ticker"] == "BBB"] == ["top"]        # watched stock became a top idea
    rows, added = board_track.log({"top": [idea("AAA", "2026-11-20")], "watch": []}, rows=rows)
    assert added == 1                                                         # new event after 21 days


# ---------------- momentum-aware timing ----------------

def tsnap(close=100, sma20=101, sma50=95, rsi=55, atr=2):
    return {"close": close, "sma20": sma20, "sma50": sma50, "rsi": rsi, "atr": atr}


def test_pullback_in_uptrend_is_ready_not_wait():
    from swingquest.signals import plan
    t = plan.trend_timing(tsnap(close=100, sma20=101), above200=True)
    assert t["label"] == "Ready" and "pulling back" in t["notes"][0]


def test_downtrend_waits_until_it_turns_up():
    from swingquest.signals import plan
    assert plan.trend_timing(tsnap(close=90, sma20=92), above200=False)["label"] == "Wait"
    assert plan.trend_timing(tsnap(close=93, sma20=92), above200=False)["label"] == "Ready"


def test_overextended_is_dont_chase():
    from swingquest.signals import plan
    assert plan.trend_timing(tsnap(close=110, sma20=100), above200=True)["label"] == "Extended"


def test_mid_pack_is_neutral_not_buy():
    rules = {**CFG["ideas"], "min_conviction": 99}
    s = brain.score_universe([metric("X"), metric("Y")], CFG, {})[0]
    assert brain.verdict(s, rules)[0] == "Neutral"


def test_sharp_drop_is_not_a_pullback():
    from swingquest.signals import plan
    t = plan.trend_timing(tsnap(close=90, sma20=100, atr=3), above200=True)
    assert t["label"] == "Wait" and "Sharp drop" in t["notes"][0]


def test_too_volatile_is_avoid():
    rules = {**CFG["ideas"], "max_daily_move": 0.06}
    s = [x for x in brain.score_universe([metric("X", atr_pct=0.09), metric("Y")], CFG, {}) if x["ticker"] == "X"][0]
    assert brain.verdict(s, rules)[0] == "Avoid"

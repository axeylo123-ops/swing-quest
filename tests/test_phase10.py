"""Phase 10: review fixes (bad data, grading, estimate cuts, upside realism, high-upside lane)."""
import math

import numpy as np
import pandas as pd

from swingquest import brain, tracker
from swingquest.prices.yfinance_source import is_missing_error, is_throttle_error, normalize
from swingquest.signals.scan import ret_over
from tests.test_brain import CFG, metric


def test_broken_price_rows_are_dropped():
    raw = pd.DataFrame({"Open": [10, 0, 11, np.nan], "High": [11, 1, 12, 12], "Low": [9, 0, 10, 10],
                        "Close": [10, 0.5, 11.5, 11], "Volume": [100, 100, 100, 100]},
                       index=pd.date_range("2026-10-01", periods=4))
    df = normalize(raw)
    assert list(df["close"]) == [10, 11.5]


def test_ret_over_never_returns_infinity():
    df = pd.DataFrame({"close": [0.0] + [1.0] * 70}, index=pd.date_range("2026-01-01", periods=71))
    assert ret_over(df, df.index[-1], 70) is None


def test_only_explicit_errors_mark_a_ticker_missing():
    assert is_missing_error("possibly delisted; no price data found")
    assert not is_missing_error("Read timed out")
    assert is_throttle_error("Too Many Requests. Rate limited.")


def test_finished_trades_keep_grading_until_15_day_return_is_known():
    assert tracker.needs_grading({"exit_reason": "open"})
    assert tracker.needs_grading({"exit_reason": "target", "entry_date": "2026-10-01", "ret_15": None})
    assert not tracker.needs_grading({"exit_reason": "target", "entry_date": "2026-10-01", "ret_15": 0.1})
    assert not tracker.needs_grading({"exit_reason": "skipped", "entry_date": None})


def test_realistic_upside_discounts_thin_coverage_disagreement_and_huge_gaps():
    solid = brain.realistic_upside({"analyst_upside": 0.30, "n_analysts": 12, "target": 65, "target_low": 60, "target_high": 70})
    thin = brain.realistic_upside({"analyst_upside": 0.30, "n_analysts": 2, "target": 65, "target_low": 60, "target_high": 70})
    split = brain.realistic_upside({"analyst_upside": 0.30, "n_analysts": 12, "target": 65, "target_low": 30, "target_high": 100})
    huge = brain.realistic_upside({"analyst_upside": 1.50, "n_analysts": 12, "target": 65, "target_low": 60, "target_high": 70})
    assert solid > split and solid > thin
    assert huge <= brain.UPSIDE_CAP


def test_estimate_cuts_are_avoid():
    s = brain.score_universe([metric("X", rev_up=0, rev_down=5), metric("Y"), metric("Z")], CFG, {})
    x = [r for r in s if r["ticker"] == "X"][0]
    assert "analysts are cutting estimates" in x["flags"]
    assert brain.verdict(x, CFG["ideas"])[0] == "Avoid"


def test_earnings_inside_window_waits_for_report():
    s = brain.score_universe([metric("X", earnings_in_window="2026-10-22"), metric("Y"), metric("Z")], CFG, {})
    x = [r for r in s if r["ticker"] == "X"][0]
    v, why = brain.verdict(x, CFG["ideas"])
    assert v == "Watch" and "report" in why


def _prices(n=260, start=40.0):
    close = start + np.linspace(0, 10, n) + np.sin(np.arange(n) / 4)
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close, "volume": 1e6},
                        index=pd.bdate_range("2025-10-01", periods=n))


def test_high_upside_needs_analyst_potential_and_two_catalysts():
    cfg = {**CFG, "high_upside": {"n": 3, "min_potential": 0.5, "min_catalysts": 2, "min_quality": 0,
                                  "max_daily_move": 0.1, "stop_atr": 3.0, "time_stop_days": 30}}
    df = _prices()
    day = f"{df.index[-1]:%Y-%m-%d}"
    common = dict(as_of=day, price=float(df["close"].iloc[-1]), atr=1.0, n_analysts=8, target=80.0)
    good = metric("GOOD", analyst_upside=0.7, rev_net=3, surprise_last=0.2, **common)
    one_cat = metric("ONE", analyst_upside=0.7, rev_net=3, surprise_last=0.0, sector="Energy", **common)
    room_only = metric("ROOM", analyst_upside=0.1, room_to_high=1.5, rev_net=3, surprise_last=0.2, sector="Banks", **common)
    waiting = metric("WAIT", analyst_upside=0.7, rev_net=3, surprise_last=0.2, timing="Wait", sector="Retail", **common)
    ranked = brain.score_universe([good, one_cat, room_only, waiting], cfg, {})
    data = {t: df for t in ("GOOD", "ONE", "ROOM", "WAIT")}
    ready, wait = brain.high_upside(ranked, data, cfg, set())
    assert [s["ticker"] for s in ready] == ["GOOD"]
    assert [s["ticker"] for s in wait] == ["WAIT"] and wait[0]["verdict"] == "High-upside: wait"
    assert math.isclose(ready[0]["potential"], 0.7)

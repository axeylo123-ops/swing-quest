"""Tests for the backtest math. Each case is small enough to check by hand."""
import pandas as pd
import pytest

from swingquest.backtest import outcomes, scorecard
from swingquest.backtest.engine import build_events, price_matches_filing

TRADE = {"atr_period": 14, "stop_atr_multiple": 2.0, "min_reward_risk": 2.0, "time_stop_days": 15}


def bars(rows, start="2026-01-05"):
    """rows = [(open, high, low, close), ...] on consecutive weekdays."""
    idx = pd.bdate_range(start, periods=len(rows))
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).assign(volume=1e6)


FLAT = (100, 101, 99, 100)


# ---------- simulate_trade: entry 100, stop 96, target 108 ----------

def test_target_hit():
    b = bars([FLAT, (101, 103, 100, 102), (103, 109, 102, 108)] + [FLAT] * 12)
    r = outcomes.simulate_trade(b, 100, 96, 108, 15)
    assert r["exit_reason"] == "target" and r["days_held"] == 3
    assert r["trade_return"] == pytest.approx(0.08) and r["r_multiple"] == pytest.approx(2.0)


def test_stop_hit():
    b = bars([FLAT, (99, 99, 95, 96)] + [FLAT] * 13)
    r = outcomes.simulate_trade(b, 100, 96, 108, 15)
    assert r["exit_reason"] == "stop" and r["r_multiple"] == pytest.approx(-1.0)


def test_same_day_stop_and_target_counts_as_stop():
    b = bars([FLAT, (100, 110, 94, 100)] + [FLAT] * 13)
    assert outcomes.simulate_trade(b, 100, 96, 108, 15)["exit_reason"] == "stop"


def test_gap_down_through_stop_exits_at_worse_open():
    b = bars([FLAT, (90, 92, 89, 91)] + [FLAT] * 13)
    r = outcomes.simulate_trade(b, 100, 96, 108, 15)
    assert r["exit_price"] == 90 and r["r_multiple"] == pytest.approx(-2.5)


def test_gap_up_through_target_exits_at_better_open():
    b = bars([FLAT, (112, 113, 111, 112)] + [FLAT] * 13)
    r = outcomes.simulate_trade(b, 100, 96, 108, 15)
    assert r["exit_price"] == 112 and r["exit_reason"] == "target"


def test_time_stop_exits_at_day_15_close():
    b = bars([FLAT] * 14 + [(100, 101, 99, 103)] + [FLAT] * 5)
    r = outcomes.simulate_trade(b, 100, 96, 108, 15)
    assert r["exit_reason"] == "time" and r["days_held"] == 15
    assert r["trade_return"] == pytest.approx(0.03)


def test_not_enough_days_yet_is_open():
    r = outcomes.simulate_trade(bars([FLAT] * 5), 100, 96, 108, 15)
    assert r["exit_reason"] == "open" and r["trade_return"] is None


# ---------- forward returns vs SPY ----------

def test_forward_returns_vs_spy():
    stock = bars([FLAT, (100, 101, 99, 100)] + [(0, 0, 0, 0)] * 3 + [(0, 0, 0, 110)] + [FLAT] * 10)
    spy = bars([FLAT, (200, 201, 199, 200)] + [FLAT] * 3 + [(0, 0, 0, 204)] + [FLAT] * 10)
    r = outcomes.forward_returns(stock, spy, entry_i=1)  # buy day 1 open at 100
    assert r["ret_5"] == pytest.approx(0.10)      # day 5 close 110
    assert r["spy_5"] == pytest.approx(0.02)      # 200 -> 204
    assert r["excess_5"] == pytest.approx(0.08)
    assert r["ret_15"] is not None and r["ret_15"] == pytest.approx(0.0)


# ---------- measure: entry rules ----------

def test_measure_buys_next_open_and_sizes_stop_from_atr():
    df = bars([FLAT, (100, 101, 99, 100)] + [FLAT] * 20)
    m = outcomes.measure(df, df, df.index[0], atr=2.0, entry_high=101, trade_cfg=TRADE)
    assert m["entry_date"] == f"{df.index[1]:%Y-%m-%d}" and m["entry"] == 100
    assert m["stop"] == 96 and m["target"] == 108 and m["taken"]


def test_measure_skips_gap_above_entry_zone():
    df = bars([FLAT, (105, 106, 104, 105)] + [FLAT] * 20)
    m = outcomes.measure(df, df, df.index[0], atr=2.0, entry_high=101, trade_cfg=TRADE)
    assert m["taken"] is False and "above the entry zone" in m["skip_reason"]
    assert m["ret_5"] is not None  # forward returns still recorded for analysis


# ---------- events and data checks ----------

def test_one_event_per_cluster():
    buys = [{"ticker": "A", "filed_date": d} for d in ("2026-01-02", "2026-01-10", "2026-01-20", "2026-02-15")]
    assert build_events(buys) == [("A", "2026-01-02"), ("A", "2026-02-15")]


def test_price_must_match_filing():
    df = bars([FLAT] * 3)
    assert price_matches_filing(df, {"trade_date": "2026-01-06", "filed_date": "2026-01-07", "avg_price": 98})
    assert not price_matches_filing(df, {"trade_date": "2026-01-06", "filed_date": "2026-01-07", "avg_price": 30})


# ---------- scorecard ----------

def row(score=70, status="pick", excess=0.02, ret=0.03, trade=0.05, reason="target", taken=True, **pts):
    r = {"score": score, "status": status, "timing": "Ready", "role": "CEO", "signal_date": "2025-01-02",
         "ret_5": ret, "ret_10": ret, "ret_15": ret, "excess_15": excess, "taken": taken,
         "trade_return": trade, "r_multiple": None if trade is None else trade / 0.04,
         "exit_reason": reason}
    for f in scorecard.FACTORS:
        r[f"{f}_points"] = pts.get(f, 0)
    return r


def test_small_groups_are_flagged():
    s = scorecard.stats([row()] * 29)
    assert s["n"] == 29 and not s["enough_data"] and s["label"] == "not enough data"
    assert scorecard.stats([row()] * 30)["enough_data"]


def test_stats_math():
    rows = [row(trade=0.08, reason="target", excess=0.05)] * 3 + [row(trade=-0.04, reason="stop", excess=-0.01)]
    s = scorecard.stats(rows)
    assert s["win_rate"] == 0.75 and s["target_first"] == 0.75 and s["stop_first"] == 0.25
    assert s["avg_trade_return"] == pytest.approx(0.05)
    assert s["beat_spy_rate"] == 0.75
    assert s["avg_excess_15"] == pytest.approx(0.035)


def test_open_signals_are_not_counted():
    s = scorecard.stats([row(), {**row(), "ret_15": None, "exit_reason": "open"}])
    assert s["n"] == 1


def test_skipped_trades_count_for_returns_not_trades():
    s = scorecard.stats([row(), row(taken=False, reason="skipped", trade=None)])
    assert s["n"] == 2 and s["n_trades"] == 1


WEIGHTS = {"cluster": 25, "role": 20, "dollar_size": 15, "stake_increase": 15, "first_buy": 10, "price_context": 15}


def test_factor_edge_strong_vs_weak():
    # cluster strong = at least half of its 25-point weight
    rows = [row(excess=0.05, cluster=25)] * 2 + [row(excess=0.03, cluster=15)] + [row(excess=0.01, cluster=0)] * 3
    f = scorecard.factor_table(rows, WEIGHTS)["cluster"]
    assert f["with"]["n"] == 3 and f["without"]["n"] == 3
    assert f["edge_excess_15"] == pytest.approx((0.05 * 2 + 0.03) / 3 - 0.01, abs=1e-4)  # stored rounded
    assert f["enough_data"] is False


def test_role_factor_can_be_judged():
    rows = [row(role=20)] * 2 + [row(role=4)] * 2   # CEO = 20 pts, "Other" = 4 pts
    f = scorecard.factor_table(rows, WEIGHTS)["role"]
    assert f["with"]["n"] == 2 and f["without"]["n"] == 2


def test_score_buckets():
    assert scorecard.bucket_of(39) == "0-39" and scorecard.bucket_of(60) == "60-79"
    assert scorecard.bucket_of(100) == "80-100"

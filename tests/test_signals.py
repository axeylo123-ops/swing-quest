"""Tests for indicators, scoring factors, timing and the trade plan."""
import numpy as np
import pandas as pd
import pytest

from tests.helpers import FIXED_CFG
from swingquest.signals import plan, scoring, technicals

CFG = FIXED_CFG  # fixed test config (see tests/helpers.py)
TRADE = {"atr_period": 14, "stop_atr_multiple": 2.0, "min_reward_risk": 2.0, "time_stop_days": 15}


def buy(owner="1", role="Director", value=100_000, pct=0.1, filed="2026-10-14", before=1000):
    return {"owner_cik": owner, "owner_name": f"Insider {owner}", "role": role, "value": value,
            "pct_of_holdings": pct, "holdings_before": before, "filed_date": filed,
            "trade_date": filed, "avg_price": 10.0, "issuer_name": "Example Inc", "ticker": "ABCD"}


# ---------- indicators ----------

def test_sma():
    assert technicals.sma(pd.Series([1, 2, 3, 4]), 2).tolist()[1:] == [1.5, 2.5, 3.5]


def test_rsi_extremes_and_middle():
    up = pd.Series(np.arange(1, 40, dtype=float))
    assert technicals.rsi(up).iloc[-1] == pytest.approx(100)
    assert technicals.rsi(up[::-1].reset_index(drop=True)).iloc[-1] == pytest.approx(0)
    zigzag = pd.Series([10 + (i % 2) for i in range(60)], dtype=float)
    assert technicals.rsi(zigzag).iloc[-1] == pytest.approx(50, abs=5)


def test_atr_of_steady_two_dollar_range():
    df = pd.DataFrame({"high": [12.0] * 30, "low": [10.0] * 30, "close": [11.0] * 30})
    assert technicals.atr(df).iloc[-1] == pytest.approx(2.0)


# ---------- scoring factors ----------

def test_cluster_counts_distinct_people_not_filings():
    assert scoring.cluster([buy("1"), buy("1")])["value"] == 1
    assert scoring.cluster([buy("1"), buy("2")])["fraction"] == 0.6
    assert scoring.cluster([buy("1"), buy("2"), buy("3")])["fraction"] == 1.0


def test_role_uses_most_senior_buyer():
    r = scoring.role([buy(role="10% Owner"), buy(role="CEO")], CFG["role_points"])
    assert r["value"] == "CEO" and r["fraction"] == 1.0


@pytest.mark.parametrize("value,frac", [(50_000, 0), (100_000, 0.3), (300_000, 0.6),
                                        (600_000, 0.8), (2_000_000, 1.0)])
def test_dollar_size_steps(value, frac):
    assert scoring.dollar_size([buy(value=value)])["fraction"] == frac


def test_stake_increase():
    assert scoring.stake_increase([buy(pct=0.35)])["fraction"] == 0.75
    assert scoring.stake_increase([buy(pct=0.6)])["fraction"] == 1.0
    assert scoring.stake_increase([buy(pct=None, before=0)])["fraction"] == 0.7  # new position
    assert scoring.stake_increase([buy(pct=None, before=None)])["fraction"] == 0.0  # unknown


def test_first_buy_needs_a_year_of_history():
    f = scoring.first_buy([buy()], [], history_start="2026-06-01")
    assert f["known"] is False and f["fraction"] == 0 and f["caution"]


def test_first_buy_true_and_false():
    assert scoring.first_buy([buy()], [], "2023-01-01")["fraction"] == 1.0
    earlier = buy(filed="2026-03-01")
    assert scoring.first_buy([buy()], [earlier], "2023-01-01")["fraction"] == 0.0
    long_ago = buy(filed="2025-01-01")
    assert scoring.first_buy([buy()], [long_ago], "2023-01-01")["fraction"] == 1.0


def test_price_context():
    assert scoring.price_context({"range_position": 0.05})["fraction"] == 1.0
    assert scoring.price_context({"range_position": 0.9})["fraction"] == 0.0


def test_weights_add_to_100_and_max_score_is_100():
    assert sum(CFG["weights"].values()) == 100
    buys = [buy("1", "CEO", 2e6, 0.6), buy("2"), buy("3")]
    r = scoring.score(buys, [], "2020-01-01", {"range_position": 0.0}, CFG)
    assert r["score"] == 100
    assert len(r["reasons"]) == 6


def test_weak_setup_scores_low():
    r = scoring.score([buy(role="Other", value=20_000, pct=0.01)], [], None,
                      {"range_position": 0.9}, CFG)
    assert r["score"] < CFG["rules"]["min_score"]


# ---------- timing and trade plan ----------

def snap(close=100, sma20=98, sma50=95, rsi=55, atr=2, vol=1.0):
    return {"close": close, "sma20": sma20, "sma50": sma50, "rsi": rsi, "atr": atr, "volume_ratio": vol}


def test_timing_labels():
    assert plan.timing(snap())["label"] == "Ready"
    assert plan.timing(snap(close=96))["label"] == "Wait"
    assert plan.timing(snap(rsi=75))["label"] == "Extended"
    assert plan.timing(snap(close=103, sma20=98))["label"] == "Extended"  # > 2 ATR above


def test_trade_plan_math():
    p = plan.trade_plan(100, 2, TRADE)
    assert p["stop"] == 96                 # 100 - 2 x 2
    assert p["entry_high"] == 101          # 100 + 0.5 x 2
    assert p["target"] == 111              # 101 + 2 x (101 - 96)
    assert p["reward_risk_worst"] == pytest.approx(2.0)
    assert p["reward_risk"] >= 2.0
    assert p["time_stop_days"] == 15


def test_trade_plan_rejects_impossible_stop():
    assert plan.trade_plan(3, 2, TRADE) is None  # stop would be below $0

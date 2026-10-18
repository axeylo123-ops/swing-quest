"""Tests for live signal tracking and the weekly health report."""
import copy
from datetime import date

import pandas as pd
import pytest

from tests.helpers import FIXED_CFG
from swingquest import health, tracker
from swingquest.prices.base import PriceSource
from swingquest.signals.scoring import FACTORS, load_weights

CFG = FIXED_CFG  # fixed test config (see tests/helpers.py)


def setup(ticker="ABCD", status="pick", score=72, timing="Ready", filed="2026-10-14"):
    return {
        "ticker": ticker, "company": "Example Inc", "status": status, "score": score, "timing": timing,
        "factors": {f: {"points": 5.0, "value": None} for f in FACTORS} | {"role": {"points": 20.0, "value": "CEO"}},
        "plan": {"entry_high": 101.0, "stop": 96.0, "target": 111.0, "time_stop_days": 15},
        "indicators": {"atr": 2.0},
        "insiders": [{"filed_date": filed, "role": "CEO"}],
    }


# ---------------- logging ----------------

def test_one_signal_per_event():
    rows, added = tracker.log_signals([setup()], "2026-10-14", rows=[], trigger_days=5)
    rows, added2 = tracker.log_signals([setup()], "2026-10-15", rows=rows, trigger_days=5)
    assert added == 1 and added2 == 0 and len(rows) == 1


def test_new_event_after_gap():
    rows, _ = tracker.log_signals([setup()], "2026-09-01", rows=[], trigger_days=5)
    rows, added = tracker.log_signals([setup()], "2026-10-14", rows=rows, trigger_days=5)
    assert added == 1 and len(rows) == 2


def test_rumor_upgrades_to_quest_within_trigger_window():
    rows, _ = tracker.log_signals([setup(status="watch", timing="Wait")], "2026-10-12", rows=[], trigger_days=5)
    rows, _ = tracker.log_signals([setup(status="pick")], "2026-10-14", rows=rows, trigger_days=5)
    assert len(rows) == 1 and rows[0]["status"] == "pick" and rows[0]["signal_date"] == "2026-10-14"


def test_row_keeps_plan_and_factor_points():
    r = tracker.to_row(setup(), "2026-10-14")
    assert r["id"] == "ABCD-2026-10-14" and r["role"] == "CEO" and r["role_points"] == 20.0
    assert r["plan"]["entry_high"] == 101.0 and r["atr"] == 2.0 and r["exit_reason"] is None


# ---------------- grading ----------------

class FakeSource(PriceSource):
    def __init__(self, frames): self.frames = frames
    def history(self, tickers, start, end): return {t: self.frames[t] for t in tickers if t in self.frames}


def bars(rows, start="2026-10-14"):
    idx = pd.bdate_range(start, periods=len(rows))
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).assign(volume=1e6)


def test_grading_uses_backtest_rules():
    flat = (100, 101, 99, 100)
    # signal 10-14; buy 10-15 open at 100 -> stop 96, target 108; target hit on day 3
    stock = bars([flat, flat, (101, 103, 100, 102), (103, 109, 102, 108)] + [flat] * 15)
    rows = [tracker.to_row(setup(), "2026-10-14")]
    rows = tracker.update_outcomes(rows, source=FakeSource({"ABCD": stock, "SPY": bars([flat] * 19)}), today=date(2026, 11, 10))
    r = rows[0]
    assert r["entry"] == 100 and r["exit_reason"] == "target" and r["trade_return"] == pytest.approx(0.08)


def test_unfinished_trade_stays_open_with_current_return():
    flat = (100, 101, 99, 100)
    stock = bars([flat, flat, (100, 102, 99, 102)])
    rows = tracker.update_outcomes([tracker.to_row(setup(), "2026-10-14")],
                                   source=FakeSource({"ABCD": stock, "SPY": bars([flat] * 3)}), today=date(2026, 10, 16))
    r = rows[0]
    assert r["exit_reason"] == "open" and r["return_now"] == pytest.approx(0.02)
    view = tracker.dashboard_view(rows)
    assert len(view["open"]) == 1 and view["closed"] == []


def test_dashboard_shows_only_quests():
    rows = [tracker.to_row(setup(status="below", score=40), "2026-10-14")]
    assert tracker.dashboard_view(rows)["open"] == []


# ---------------- health report ----------------

def past(score_pts, timing="Ready", excess=0.01, date_="2025-01-02", role="CEO"):
    r = {"signal_date": date_, "timing": timing, "role": role, "status": "pick", "score": 0,
         "ret_5": excess, "ret_10": excess, "ret_15": excess, "excess_15": excess, "taken": True,
         "trade_return": excess, "r_multiple": excess / 0.04, "exit_reason": "time"}
    for f in FACTORS:
        r[f"{f}_points"] = score_pts.get(f, 0)
    return r


def test_normalize_adds_to_100():
    assert sum(health.normalize({"a": 30, "b": 20, "c": 15, "d": 15, "e": 15, "f": 10}).values()) == 100


def test_rescore_with_same_settings_keeps_score():
    pts = {"cluster": 25, "role": 20, "dollar_size": 15, "stake_increase": 7.5, "first_buy": 0, "price_context": 0}
    r = health.rescore(past(pts), CFG, CFG)
    assert r["score"] == round(25 + 20 * CFG["role_points"]["CEO"] + 15 + 7.5)
    assert r["status"] == ("pick" if r["score"] >= CFG["rules"]["min_score"] else "below")


def test_rescore_new_weights():
    new = copy.deepcopy(CFG)
    new["weights"] = {f: 0 for f in FACTORS} | {"cluster": 100}
    r = health.rescore(past({"cluster": 25}), CFG, new)  # full cluster points -> 100
    assert r["score"] == 100


@pytest.mark.parametrize("edge,enough,expected", [(0.01, True, "helping"), (-0.01, True, "hurting"),
                                                  (0.001, True, "unclear"), (0.05, False, "not enough data")])
def test_verdicts(edge, enough, expected):
    assert health.verdict({"edge_excess_15": edge, "enough_data": enough}) == expected


def test_report_never_touches_real_weights(tmp_path, monkeypatch):
    monkeypatch.setattr(health, "HEALTH_FILE", tmp_path / "health.json")
    monkeypatch.setattr(health, "PROPOSED_FILE", tmp_path / "weights_proposed.yaml")
    real = (health.CONFIG_DIR / "weights.yaml").read_text()
    rows = [past({"cluster": 25, "role": 20, "dollar_size": 15}, excess=0.02, date_=f"2025-{m:02d}-0{d}")
            for m in range(1, 13) for d in range(1, 8)]
    report, proposed = health.build_report(rows, [], today=date(2026, 10, 14))
    health.write_report(report, proposed)
    assert (health.CONFIG_DIR / "weights.yaml").read_text() == real
    assert "NOTHING here is used" in (tmp_path / "weights_proposed.yaml").read_text()
    assert report["week"] == "2026-10-12"


def test_threshold_respects_quests_per_month():
    rows = [past({"cluster": 25, "role": 20, "dollar_size": 15, "first_buy": s}, excess=0.01 + s / 1000,
                 date_=f"202{4 + (i % 2)}-{(i % 12) + 1:02d}-1{i % 9}") for i, s in enumerate([0, 10] * 150)]
    m, st = health.best_threshold(rows, CFG, CFG, target=4)
    assert st is None or st["per_month"] <= 4 * 1.25

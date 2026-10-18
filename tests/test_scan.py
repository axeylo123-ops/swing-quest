"""End-to-end scan on made-up data (no internet needed)."""
import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from swingquest import store
from swingquest.prices.base import PriceSource
from swingquest.signals import scan

TODAY = date(2026, 10, 16)


@pytest.fixture(autouse=True)
def fixed_rules(monkeypatch):
    """Tests use their own rules, so changing your config never breaks them."""
    from swingquest import universe
    from swingquest.signals import scoring
    real_settings, real_weights = universe.settings(), scoring.load_weights()
    monkeypatch.setattr(universe, "settings", lambda: {**real_settings, "universe": {
        "min_price": 5.0, "max_price": None, "min_avg_dollar_volume": 10_000_000}})
    monkeypatch.setattr(scan.scoring, "load_weights", lambda: {**real_weights, "rules": {**real_weights["rules"], "min_score": 60}})
    monkeypatch.setattr(scan.events, "earnings_dates", lambda ticker, fetch=None: ["2026-10-27"])  # no internet in tests


def test_radar_lists_near_misses_with_reasons():
    def s(t, score, status, timing):
        return {"ticker": t, "company": t, "score": score, "status": status, "timing": timing, "reasons": ["r1", "r2"],
                "context": [], "indicators": {"close": 10.0}, "insiders": [{"name": "A", "value": 1e5}]}
    ev = [s("PICK", 90, "pick", "Ready"), s("WAIT", 70, "watch", "Wait"), s("LOW", 50, "below", "Ready"),
          s("HOT", 66, "watch", "Extended"), s("NOISE", 20, "below", "Ready")]
    r = scan.radar_list(ev, min_score=60)
    assert [x["ticker"] for x in r] == ["WAIT", "HOT", "LOW"]          # quests and noise excluded, best first
    assert "blocked" in r[0]["why_not"] and "chase" in r[1]["why_not"] and "needs 60" in r[2]["why_not"]


def test_earnings_inside_window_adds_warning(monkeypatch, tmp_path):
    r = run(monkeypatch, tmp_path, strong_cluster(), {"SPY": bars(), "ABCD": bars()})
    p = r["picks"][0]
    assert p["earnings"]["in_window"] and p["cautions"][0].startswith("Earnings expected 2026-10-27")


def bars(noisy=True):
    """A year-long slide from $60 to $30, then a gentle turn up to ~$34."""
    down = np.linspace(60, 30, 260)
    up = np.linspace(30, 34, 41)[1:]
    trend = np.concatenate([down, up])
    close = trend + (0.5 * (-1) ** np.arange(len(trend)) if noisy else 0)
    idx = pd.bdate_range(end=pd.Timestamp(TODAY), periods=len(trend))
    return pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5,
                         "close": close, "volume": 1_000_000.0}, index=idx)


class FakeSource(PriceSource):
    def __init__(self, frames):
        self.frames = frames

    def history(self, tickers, start, end):
        return {t: self.frames[t] for t in tickers if t in self.frames}


def strong_cluster():
    base = {"ticker": "ABCD", "issuer_cik": "123", "issuer_name": "Example Inc", "avg_price": 33.0,
            "pct_of_holdings": 0.5, "holdings_before": 10000, "plan_10b5_1": False}
    return [
        {**base, "owner_cik": "1", "owner_name": "A", "role": "CEO", "value": 900_000,
         "filed_date": "2026-10-01", "trade_date": "2026-09-30"},
        {**base, "owner_cik": "2", "owner_name": "B", "role": "Director", "value": 400_000,
         "filed_date": "2026-10-08", "trade_date": "2026-10-07"},
        {**base, "owner_cik": "3", "owner_name": "C", "role": "CFO", "value": 200_000,
         "filed_date": "2026-10-15", "trade_date": "2026-10-14"},
    ]


class FakeProfiles:
    def __init__(self, is_fund=False):
        self.is_fund = is_fund

    def get(self, cik):
        return {"sic": "" if self.is_fund else "2080", "is_fund": self.is_fund}


def run(monkeypatch, tmp_path, buys, frames, is_fund=False):
    monkeypatch.setattr(store, "load_buys", lambda start=None, end=None: [
        b for b in buys if (not start or b["filed_date"] >= start) and (not end or b["filed_date"] <= end)])
    monkeypatch.setattr(store, "load_state", lambda: {})
    return scan.run_scan(TODAY, out_dir=tmp_path, source=FakeSource(frames), exchanges={},
                         profiles=FakeProfiles(is_fund))


def test_funds_are_skipped(monkeypatch, tmp_path):
    r = run(monkeypatch, tmp_path, strong_cluster(), {"SPY": bars(), "ABCD": bars()}, is_fund=True)
    assert r["picks"] == [] and "fund" in r["skipped"][0]["reason"]


def test_no_buys_means_no_setups_today(monkeypatch, tmp_path):
    r = run(monkeypatch, tmp_path, [], {"SPY": bars()})
    assert r["status"] == "none" and r["message"] == "No setups today."
    assert json.loads((tmp_path / "today.json").read_text())["message"] == "No setups today."


def test_strong_cluster_with_turning_chart_is_a_pick(monkeypatch, tmp_path):
    r = run(monkeypatch, tmp_path, strong_cluster(), {"SPY": bars(), "ABCD": bars()})
    assert r["status"] == "setups", r["skipped"]
    p = r["picks"][0]
    assert p["ticker"] == "ABCD" and p["timing"] == "Ready"
    assert p["score"] >= 60
    assert p["plan"]["reward_risk_worst"] >= 2.0
    assert len(p["chart"]) == scan.CHART_BARS
    assert any("3 different insiders" in reason for reason in p["reasons"])


def test_overheated_chart_goes_to_watchlist(monkeypatch, tmp_path):
    r = run(monkeypatch, tmp_path, strong_cluster(), {"SPY": bars(), "ABCD": bars(noisy=False)})
    assert r["status"] == "none"
    assert r["watchlist"][0]["timing"] == "Extended"


def test_old_buys_without_a_fresh_one_do_not_trigger(monkeypatch, tmp_path):
    old = [b for b in strong_cluster() if b["filed_date"] < "2026-10-10"]
    r = run(monkeypatch, tmp_path, old, {"SPY": bars(), "ABCD": bars()})
    assert r["summary"]["stocks_with_new_buys"] == 0


def test_illiquid_stock_is_skipped_with_reason(monkeypatch, tmp_path):
    thin = bars().assign(volume=1000.0)
    r = run(monkeypatch, tmp_path, strong_cluster(), {"SPY": bars(), "ABCD": thin})
    assert r["picks"] == [] and "traded per day" in r["skipped"][0]["reason"]


def test_scan_ignores_future_prices(monkeypatch, tmp_path):
    frames = {"SPY": bars(), "ABCD": bars()}
    future = pd.DataFrame({"open": 999.0, "high": 999.0, "low": 999.0, "close": 999.0, "volume": 1e9},
                          index=[pd.Timestamp("2026-10-19")])
    frames["ABCD"] = pd.concat([frames["ABCD"], future])
    r = run(monkeypatch, tmp_path, strong_cluster(), frames)
    assert r["picks"][0]["indicators"]["close"] < 100

"""Phase 8: sector strength, relative strength, earnings windows."""
import pandas as pd
import pytest

from tests.helpers import FIXED_CFG
from swingquest import events, health, sectors
from swingquest.backtest import scorecard
from swingquest.signals import scan, scoring

CFG = FIXED_CFG  # fixed test config (see tests/helpers.py)


@pytest.mark.parametrize("sic,sector", [("2834", "Health Care"), ("1311", "Energy"), ("7372", "Technology"),
                                        ("6022", "Financials"), ("6798", "Real Estate"), ("4911", "Utilities"),
                                        ("3711", "Consumer Discretionary"), ("", None), (None, None)])
def test_sector_from_sic(sic, sector):
    assert sectors.sector_of(sic) == sector


def test_sector_etf():
    assert sectors.etf_of("Energy") == "XLE" and sectors.etf_of(None) is None


def closes(values, start="2026-01-01"):
    idx = pd.bdate_range(start, periods=len(values))
    return pd.DataFrame({"close": values}, index=idx)


def test_relative_and_sector_strength_vs_spy():
    n = 70
    stock = closes([10.0] * (n - 64) + [10.0] + [10.0] * 62 + [12.0])   # +20% over 63 days
    spy = closes([100.0] * (n - 64) + [100.0] + [100.0] * 62 + [105.0])  # +5%
    etf = closes([50.0] * (n - 64) + [50.0] + [50.0] * 62 + [51.0])      # +2%
    s = scan.strength(stock, {"spy": spy, "etf": etf, "sector": "Energy"})
    assert s["rs_3m"] == pytest.approx(0.15) and s["sector_rs"] == pytest.approx(-0.03) and s["sector"] == "Energy"


def test_strength_needs_enough_history():
    assert scan.ret_over(closes([1.0] * 30), pd.Timestamp("2026-02-10")) is None


def test_observed_factors_never_change_the_score():
    buys = [{"owner_cik": "1", "role": "CEO", "value": 2e6, "pct_of_holdings": 0.6, "holdings_before": 10, "filed_date": "2026-10-14"}]
    snap = {"range_position": 0.0, "rs_3m": 0.2, "sector_rs": 0.05, "sector": "Energy"}
    with_ctx = scoring.score(buys, [], None, snap, CFG)
    without = scoring.score(buys, [], None, {"range_position": 0.0}, CFG)
    assert with_ctx["score"] == without["score"]                       # weight 0: observed only
    assert any("Beating the market" in c for c in with_ctx["context"])
    assert any("Energy" in c for c in with_ctx["context"])
    assert with_ctx["factors"]["relative_strength"]["fraction"] == 1.0


def test_quest_window_and_earnings_hit():
    start, end = events.quest_window("2026-10-16")        # Friday signal -> Monday entry
    assert start == "2026-10-19" and end == "2026-11-06"
    assert events.in_window(["2026-08-01", "2026-11-04"], "2026-10-16") == "2026-11-04"
    assert events.in_window(["2026-11-18"], "2026-10-16") is None


def test_earnings_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "CACHE", tmp_path)
    calls = []
    def fetch(t):
        calls.append(t)
        return pd.DataFrame(index=pd.to_datetime(["2026-11-04 16:00", "2026-08-01 08:00"]))
    assert events.earnings_dates("ABC", fetch=fetch) == ["2026-08-01", "2026-11-04"]
    events.earnings_dates("ABC", fetch=fetch)
    assert calls == ["ABC"]


def test_strength_judged_by_fraction_even_at_weight_zero():
    r = {"relative_strength_frac": 0.7, "relative_strength_points": 0}
    assert scorecard.is_strong(r, "relative_strength", 0) is True
    assert scorecard.is_strong({"relative_strength_points": 0}, "relative_strength", 0) is None  # old row: unknown


def test_rescore_uses_fraction_for_new_weights():
    row = {"role": "CEO", "timing": "Ready", **{f"{f}_frac": 0 for f in scoring.FACTORS}, "relative_strength_frac": 1.0}
    new = {**CFG, "weights": {f: 0 for f in scoring.FACTORS} | {"relative_strength": 100}}
    assert health.rescore(row, CFG, new)["score"] == 100

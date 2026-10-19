"""Phase 11: paper trading. The browser engine (docs/js/paper.js) must grade
trades exactly like the Python grader, and the bot must publish prices for
every stock that was on a list."""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingquest import paper
from swingquest.backtest.outcomes import measure_plan

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def _df(closes, lows=None, highs=None, opens=None):
    idx = pd.bdate_range("2026-09-01", periods=len(closes))
    c = np.array(closes, float)
    return pd.DataFrame({"open": opens if opens is not None else c, "high": highs if highs is not None else c * 1.01,
                         "low": lows if lows is not None else c * 0.99, "close": c, "volume": 1e6}, index=idx)


def _js(bars, plan, fill, opts):
    script = ("import { simulate } from " + json.dumps((ROOT / "docs/js/paper.js").as_uri()) + ";"
              f"console.log(JSON.stringify(simulate({json.dumps(bars)}, {json.dumps(plan)}, {json.dumps(fill)}, {json.dumps(opts)})));")
    out = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


CASES = {
    "target": _df([100, 100, 102, 104, 106, 112, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125]),
    "stop": _df([100, 100, 99, 97, 95, 93, 92, 91, 90, 90, 90, 90, 90, 90, 90, 90, 90]),
    "time": _df([100] * 20),
    "gap_down": _df([100, 100, 100, 100], opens=[100, 100, 100, 90], lows=[99, 99, 99, 89]),
    "above_zone": _df([100, 100, 104, 104], opens=[100, 100, 104, 104]),
}


@pytest.mark.skipif(NODE is None, reason="node not installed")
@pytest.mark.parametrize("name", list(CASES))
def test_browser_engine_matches_python_grader(name):
    df = CASES[name]
    spy = _df([400] * len(df))
    plan = {"entry_low": 99.0, "entry_high": 101.0, "stop": 96.0, "target": 110.0, "time_stop_days": 15, "reference": 100.0}
    day = df.index[0]
    py = measure_plan(df, spy, day, plan)
    bars = [[f"{d:%Y-%m-%d}", r.open, r.high, r.low, r.close] for d, r in df.iterrows()]
    js = _js(bars, plan, f"{df.index[1]:%Y-%m-%d}", {"strict": True})
    if py["exit_reason"] == "skipped":
        assert js["status"] == "skipped"
    elif py["exit_reason"] == "open":
        assert js["status"] == "open"
    else:
        assert js["status"] == "closed" and js["reason"] == py["exit_reason"]
        assert js["exitDate"] == py["exit_date"] and js["days"] == py["days_held"]
        assert js["exitPrice"] == pytest.approx(py["exit_price"]) and js["ret"] == pytest.approx(py["trade_return"], abs=1e-4)


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_your_orders_fill_even_above_the_zone_and_can_be_sold():
    df = CASES["time"]
    bars = [[f"{d:%Y-%m-%d}", 104.0, 105.0, 103.0, 104.0] for d in df.index]
    plan = {"entry_low": 99.0, "entry_high": 101.0, "stop": 96.0, "target": 120.0, "time_stop_days": 15}
    mine = _js(bars, plan, bars[1][0], {})
    assert mine["status"] == "closed" and mine["aboveZone"] is True
    sold = _js(bars, plan, bars[1][0], {"closeOn": bars[3][0]})
    assert sold["reason"] == "sold" and sold["exitDate"] == bars[3][0] and sold["days"] == 3


def test_list_history_and_price_feed(tmp_path, monkeypatch):
    monkeypatch.setattr(paper, "HISTORY_FILE", tmp_path / "hist.json")
    monkeypatch.setattr(paper, "PAPER_FILE", tmp_path / "paper.json")
    df = _df(list(np.linspace(50, 60, 40)))
    today = f"{df.index[-1]:%Y-%m-%d}"
    board = {"ranked": [{"as_of": today}], "top": [{"ticker": "AAA"}], "high_wait": [{"ticker": "BBB"}], "watch": []}
    rows = [{"id": "AAA-x", "ticker": "AAA", "kind": "top", "signal_date": today, "conviction": 70,
             "plan": {"entry_low": 59, "entry_high": 61, "stop": 55, "target": 70, "time_stop_days": 15, "reference": 60}}]
    out = paper.publish(board, rows, {"AAA": df, "BBB": df, "SPY": df}, today=today)
    data = json.loads((tmp_path / "paper.json").read_text())
    assert out["tickers"] == 3 and set(data["bars"]) == {"AAA", "BBB", "SPY"}
    assert data["bars"]["AAA"][-1][0] == today and len(data["bars"]["AAA"][0]) == 5
    assert [p["id"] for p in data["system"]] == ["AAA-x"]
    # a stock that falls off the lists keeps its feed while it's inside the window
    later = paper.update_history({"top": []}, json.loads((tmp_path / "hist.json").read_text()), today)
    assert "BBB" in later

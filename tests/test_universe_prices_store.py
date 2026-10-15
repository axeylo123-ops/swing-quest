import numpy as np
import pandas as pd
import pytest

from swingquest import store
from swingquest.prices.yfinance_source import normalize
from swingquest.tickers import clean_ticker
from swingquest.universe import is_us_listed, liquidity_check


def bars(n=30, close=20.0, volume=1_000_000, start="2026-09-01"):
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": volume}, index=idx)


def test_liquid_stock_passes():
    df = bars(close=20, volume=1_000_000)  # $20M per day
    assert liquidity_check(df, df.index[-1], 5, 10e6)["ok"]


def test_cheap_or_thin_stock_fails():
    assert not liquidity_check(bars(close=4, volume=10_000_000), "2026-12-31", 5, 10e6)["ok"]
    assert not liquidity_check(bars(close=20, volume=100_000), "2026-12-31", 5, 10e6)["ok"]


def test_liquidity_never_peeks_at_future_bars():
    df = bars(n=40, close=20, volume=100_000)  # thin...
    df.iloc[30:, df.columns.get_loc("volume")] = 50_000_000  # ...until day 30
    assert not liquidity_check(df, df.index[25], 5, 10e6)["ok"]


def test_short_history_fails():
    assert not liquidity_check(bars(n=10), "2026-12-31", 5, 10e6)["ok"]


def test_otc_is_excluded_unknown_is_allowed():
    ex = {"AAA": "Nasdaq", "BBB": "OTC"}
    assert is_us_listed("AAA", ex) and not is_us_listed("BBB", ex) and is_us_listed("ZZZ", ex)


@pytest.mark.parametrize("raw,expected", [
    ("abcd", "ABCD"), ("NYSE: BRK.B", "BRK-B"), ("ABC, ABCW", "ABC"),
    ("None", None), ("N/A", None), ("", None), (None, None), ("TOOLONGX", None),
])
def test_clean_ticker(raw, expected):
    assert clean_ticker(raw) == expected


def test_normalize_yfinance_frame():
    idx = pd.date_range("2026-10-01", periods=3, tz="America/New_York")
    raw = pd.DataFrame({"Open": [1, 2, 3], "High": [1, 2, 3], "Low": [1, 2, 3],
                        "Close": [1, np.nan, 3], "Volume": [10, 20, 30]}, index=idx)
    df = normalize(raw)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 2 and df.index.tz is None


def test_store_merges_without_duplicates(tmp_path):
    rec = {"accession": "a1", "filed_date": "2026-10-14", "ticker": "ABCD"}
    assert store.save_buys([rec], base=tmp_path) == 1
    assert store.save_buys([rec, {**rec, "accession": "a2"}], base=tmp_path) == 1
    assert len(store.load_buys(base=tmp_path)) == 2
    assert store.load_buys("2026-10-15", base=tmp_path) == []

import numpy as np
import pandas as pd
import pytest

from swingquest import store
from swingquest.prices.yfinance_source import normalize
from swingquest.tickers import clean_ticker
from swingquest.universe import IssuerProfiles, is_us_listed, liquidity_check


class FakeClient:
    def __init__(self, responses):
        self.responses, self.calls = responses, 0

    def get_json(self, url):
        self.calls += 1
        cik = int(url.split("CIK")[1].split(".")[0])
        return self.responses[cik]


def test_issuer_profiles_spot_funds_and_cache(tmp_path):
    client = FakeClient({
        1: {"sic": "2080", "sicDescription": "Beverages", "filings": {"recent": {"form": ["10-K"]}}},
        2: {"sic": "", "filings": {"recent": {"form": ["N-CSR"]}}},
    })
    p = IssuerProfiles(client, cache_path=tmp_path / "p.json")
    assert p.get("0000000001")["is_fund"] is False
    assert p.get("2")["is_fund"] is True
    p.get("1")
    assert client.calls == 2  # second lookup came from the cache
    assert IssuerProfiles(client, cache_path=tmp_path / "p.json").get("2")["is_fund"]


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


def test_max_price_ceiling(monkeypatch):
    from swingquest import universe
    monkeypatch.setattr(universe, "settings", lambda: {"universe": {"min_price": 2, "max_price": 30, "min_avg_dollar_volume": 1}})
    assert not liquidity_check(bars(close=40), "2026-12-31")["ok"]
    assert liquidity_check(bars(close=25), "2026-12-31")["ok"]


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


def test_throttled_tickers_are_retried_not_marked_missing(tmp_path, monkeypatch):
    from datetime import date
    from swingquest.prices import yfinance_source as ys
    monkeypatch.setattr(ys, "CACHE", tmp_path)
    monkeypatch.setattr(ys, "META", tmp_path / "_meta.json")
    monkeypatch.setattr(ys.time, "sleep", lambda s: None)
    idx = pd.date_range("2026-10-01", periods=3)
    good = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1.0}, index=idx)
    calls = []

    def fake_fetch(tickers, start, end):
        calls.append(list(tickers))
        if len(calls) == 1:  # first try: AAA works, BBB throttled, OLD delisted
            raw = pd.concat({"AAA": good}, axis=1)
            return raw, {"BBB": "YFRateLimitError('Too Many Requests')", "OLD": "possibly delisted"}
        return pd.concat({"BBB": good}, axis=1), {}

    monkeypatch.setattr(ys.YFinanceSource, "_fetch", staticmethod(fake_fetch))
    src = ys.YFinanceSource()
    got = src.history(["AAA", "BBB", "OLD"], date(2026, 10, 1), date(2026, 10, 3))
    assert set(got) == {"AAA", "BBB"}
    assert calls[1] == ["BBB"]                      # only the throttled one was retried
    assert "missing" in src.meta["OLD"] and "missing" not in src.meta["BBB"]


def test_yfinance_error_lines_are_parsed():
    import logging
    from swingquest.prices.yfinance_source import _ErrorCatcher, is_throttle_error
    c = _ErrorCatcher()
    for msg in ["['ZI', 'SPY']: YFRateLimitError('Too Many Requests. Rate limited.')",
                "['OLD']: possibly delisted; no timezone found", "\n2 Failed downloads:"]:
        c.emit(logging.LogRecord("yfinance", logging.ERROR, "", 0, msg, None, None))
    assert is_throttle_error(c.errors["SPY"]) and is_throttle_error(c.errors["ZI"])
    assert not is_throttle_error(c.errors["OLD"])
    assert len(c.errors) == 3


def test_store_merges_without_duplicates(tmp_path):
    rec = {"accession": "a1", "filed_date": "2026-10-14", "ticker": "ABCD"}
    assert store.save_buys([rec], base=tmp_path) == 1
    assert store.save_buys([rec, {**rec, "accession": "a2"}], base=tmp_path) == 1
    assert len(store.load_buys(base=tmp_path)) == 2
    assert store.load_buys("2026-10-15", base=tmp_path) == []

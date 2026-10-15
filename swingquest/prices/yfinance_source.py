"""Free daily prices from Yahoo Finance via the yfinance library.

yfinance is unofficial: it can be slow, rate-limited, or briefly broken,
and it has no data for companies that were later delisted. Results are
cached on disk (cache/prices/) so we don't re-download the same bars.
"""
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from swingquest.config import CACHE_DIR
from swingquest.prices.base import COLUMNS, PriceSource

CACHE = CACHE_DIR / "prices"
BATCH = 50


def normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """yfinance columns ('Open', 'Close'...) -> our standard shape."""
    df = raw.rename(columns=str.lower)
    df = df[[c for c in COLUMNS if c in df.columns]].dropna(subset=["close"])
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "date"
    return df.sort_index()


class YFinanceSource(PriceSource):
    name = "yfinance"

    def history(self, tickers, start, end):
        CACHE.mkdir(parents=True, exist_ok=True)
        out, missing = {}, []
        for t in dict.fromkeys(tickers):  # de-duplicate, keep order
            cached = self._load(t)
            if cached is not None and cached.index[0] <= pd.Timestamp(start) + pd.Timedelta(days=5) \
                    and cached.index[-1] >= self._last_expected_day(end):
                out[t] = cached
            else:
                missing.append(t)
        for i in range(0, len(missing), BATCH):
            out.update(self._download(missing[i:i + BATCH], start, end))
        s, e = pd.Timestamp(start), pd.Timestamp(end)
        return {t: df.loc[s:e] for t, df in out.items() if not df.loc[s:e].empty}

    def _download(self, tickers, start, end):
        raw = yf.download(tickers, start=start, end=end + timedelta(days=1), auto_adjust=True,
                          group_by="ticker", progress=False, threads=True)
        result = {}
        for t in tickers:
            try:
                part = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            except KeyError:
                continue
            df = normalize(part)
            if not df.empty:
                df.to_pickle(CACHE / f"{t}.pkl")
                result[t] = df
        return result

    @staticmethod
    def _load(ticker):
        path = CACHE / f"{ticker}.pkl"
        return pd.read_pickle(path) if path.exists() else None

    @staticmethod
    def _last_expected_day(end: date) -> pd.Timestamp:
        """The most recent weekday on or before `end` (ignores holidays, so a
        holiday just causes one harmless re-download)."""
        d = pd.Timestamp(end)
        while d.weekday() >= 5:
            d -= pd.Timedelta(days=1)
        today = pd.Timestamp.today().normalize()
        # Today's bar only exists after the close; don't demand it.
        return min(d, today - pd.Timedelta(days=1)) if d >= today else d

"""Free daily prices from Yahoo Finance via the yfinance library.

yfinance is unofficial: it can be slow, rate-limited, or briefly broken,
and it has no data for companies that were later delisted. Results are
cached on disk (cache/prices/) so we don't re-download the same bars,
and tickers Yahoo doesn't know are remembered for a week.
"""
import ast
import json
import logging
import re
import time
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from swingquest.config import CACHE_DIR
from swingquest.prices.base import COLUMNS, PriceSource

CACHE = CACHE_DIR / "prices"
META = CACHE / "_meta.json"   # {ticker: {"start": ..., "through": ...} or {"missing": date}}
BATCH = 25


def normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """yfinance columns ('Open', 'Close'...) -> our standard shape."""
    df = raw.rename(columns=str.lower)
    df = df[[c for c in COLUMNS if c in df.columns]].dropna(subset=["close"])
    ohlc = [c for c in ("open", "high", "low", "close") if c in df.columns]
    df = df[df[ohlc].notna().all(axis=1) & (df[ohlc] > 0).all(axis=1)]   # broken bars break every calc
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "date"
    return df.sort_index()


class _ErrorCatcher(logging.Handler):
    """Collects yfinance's "['A', 'B']: reason" error lines into {ticker: reason}."""

    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.errors: dict[str, str] = {}

    def emit(self, record):
        msg = record.getMessage().strip()
        m = re.match(r"^(\[.*?\]):\s*(.*)$", msg, re.S)
        if not m:
            return
        try:
            syms = ast.literal_eval(m.group(1))
        except (ValueError, SyntaxError):
            return
        for s in syms:
            self.errors[str(s).upper()] = m.group(2)


def is_throttle_error(message: str) -> bool:
    m = message.lower()
    return "too many requests" in m or "rate limit" in m or "ratelimit" in m


def is_missing_error(message: str) -> bool:
    m = message.lower()
    return any(k in m for k in ("delisted", "not found", "no data found", "no timezone found", "no price data"))


def last_expected_day(end: date, today: date | None = None) -> str:
    """The latest weekday whose bar should exist (today's only after the close;
    holidays just cause one harmless re-download)."""
    today = today or date.today()
    d = min(end, today - timedelta(days=1)) if end >= today else end
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


class YFinanceSource(PriceSource):
    name = "yfinance"

    def __init__(self, progress=None):
        self.progress = progress
        CACHE.mkdir(parents=True, exist_ok=True)
        self.meta = json.loads(META.read_text()) if META.exists() else {}

    def history(self, tickers, start, end):
        need_through = last_expected_day(end)
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        out, missing = {}, []
        for t in dict.fromkeys(tickers):
            m = self.meta.get(t, {})
            if m.get("missing", "") >= week_ago:
                continue  # Yahoo had nothing recently; don't ask again yet
            if m.get("start", "9999") <= start.isoformat() and m.get("through", "") >= need_through:
                path = CACHE / f"{t}.pkl"
                if path.exists():
                    out[t] = pd.read_pickle(path)
                    continue
            missing.append(t)
        # never shrink a ticker's cached history: download from the earliest start asked for
        dl_start = min([start] + [date.fromisoformat(self.meta[t]["start"])
                                  for t in missing if "start" in self.meta.get(t, {})])
        for i in range(0, len(missing), BATCH):
            out.update(self._download(missing[i:i + BATCH], dl_start, end, need_through))
            if self.progress:
                self.progress(f"  prices: {min(i + BATCH, len(missing))}/{len(missing)} downloaded")
            if i + BATCH < len(missing):
                time.sleep(3)  # be gentle with Yahoo
        META.write_text(json.dumps(self.meta))
        s, e = pd.Timestamp(start), pd.Timestamp(end)
        return {t: df.loc[s:e] for t, df in out.items() if not df.loc[s:e].empty}

    def _download(self, tickers, start, end, through):
        """Downloads a batch. Yahoo says *why* a ticker failed: "possibly
        delisted" means really missing; "Too Many Requests" means we're being
        throttled, so we wait and retry those, and never mark them missing."""
        result, todo = {}, list(tickers)
        for attempt in range(4):
            raw, errors = self._fetch(todo, start, end)
            throttled = []
            for t in todo:
                df = self._extract(raw, t)
                if not df.empty:
                    df.to_pickle(CACHE / f"{t}.pkl")
                    self.meta[t] = {"start": start.isoformat(), "through": through}
                    result[t] = df
                elif is_missing_error(errors.get(t, "")):
                    self.meta[t] = {"missing": date.today().isoformat()}
                else:
                    throttled.append(t)      # throttled or unknown failure: retry, never mark missing
            if not throttled:
                break
            todo = throttled
            time.sleep(60 * (attempt + 1))  # 1, 2, 3 minutes
        return result

    @staticmethod
    def _fetch(tickers, start, end):
        """Returns (data, {ticker: error message}). yfinance only reports
        failures in its log, as "['A', 'B']: reason", so we listen to it."""
        catcher = _ErrorCatcher()
        log = logging.getLogger("yfinance")
        log.addHandler(catcher)
        try:
            raw = yf.download(tickers, start=start, end=end + timedelta(days=1), auto_adjust=True,
                              group_by="ticker", progress=False, threads=4)
        except Exception as e:  # whole request failed: treat every ticker as throttled
            return pd.DataFrame(), {t: f"Too Many Requests ({e})" for t in tickers}
        finally:
            log.removeHandler(catcher)
        return raw, catcher.errors

    @staticmethod
    def _extract(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
        try:
            part = raw[ticker] if isinstance(raw.columns, pd.MultiIndex) else raw
            return normalize(part)
        except KeyError:
            return pd.DataFrame()

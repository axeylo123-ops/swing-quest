"""The price "plug". Every price source must look like this.

To switch to a paid data API later, write one new class with a
`history()` method that returns the same shape, then change
`prices.source` in config/settings.yaml. Nothing else needs to change.
"""
from abc import ABC, abstractmethod
from datetime import date

import pandas as pd

COLUMNS = ["open", "high", "low", "close", "volume"]


class PriceSource(ABC):
    name = "base"

    @abstractmethod
    def history(self, tickers: list[str], start: date, end: date) -> dict[str, pd.DataFrame]:
        """Daily bars for each ticker, from start to end (inclusive).

        Returns {ticker: DataFrame} with a sorted DatetimeIndex (one row per
        trading day) and lowercase columns open/high/low/close/volume, adjusted
        for splits and dividends. Tickers with no data are simply left out.
        """


def get_price_source(name: str | None = None) -> PriceSource:
    from swingquest import config
    name = name or config.settings().get("prices", {}).get("source", "yfinance")
    if name == "yfinance":
        from swingquest.prices.yfinance_source import YFinanceSource
        return YFinanceSource()
    raise ValueError(f"Unknown price source: {name}")

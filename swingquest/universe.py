"""Which stocks are allowed at all: listed in the US, price > $5, and
enough trading that you can get in and out easily (> $10M a day)."""
import json
from datetime import date

import pandas as pd

from swingquest.config import CACHE_DIR, settings

TICKER_LIST_URL = "https://www.sec.gov/files/company_tickers_exchange.json"


def liquidity_check(prices: pd.DataFrame, as_of, min_price: float | None = None,
                    min_dollar_volume: float | None = None, window: int = 20) -> dict:
    """Uses only bars up to `as_of`, so a backtest never peeks at the future."""
    u = settings()["universe"]
    min_price = u["min_price"] if min_price is None else min_price
    min_dollar_volume = u["min_avg_dollar_volume"] if min_dollar_volume is None else min_dollar_volume
    past = prices.loc[:pd.Timestamp(as_of)].tail(window)
    if len(past) < window:
        return {"ok": False, "reason": "not enough price history"}
    price = float(past["close"].iloc[-1])
    adv = float((past["close"] * past["volume"]).mean())
    if price <= min_price:
        return {"ok": False, "reason": f"price ${price:.2f} is under ${min_price:.0f}",
                "price": price, "avg_dollar_volume": adv}
    if adv <= min_dollar_volume:
        return {"ok": False, "reason": f"only ${adv / 1e6:.1f}M traded per day",
                "price": price, "avg_dollar_volume": adv}
    return {"ok": True, "price": price, "avg_dollar_volume": adv}


def exchange_map(client=None, refresh: bool = False) -> dict[str, str | None]:
    """Ticker -> exchange from the SEC's list, cached for the day."""
    path = CACHE_DIR / f"exchanges_{date.today():%Y%m%d}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    if client is None:
        from swingquest.sec.client import SecClient
        client = SecClient()
    data = client.get_json(TICKER_LIST_URL)
    i_t, i_x = data["fields"].index("ticker"), data["fields"].index("exchange")
    result = {row[i_t]: row[i_x] for row in data["data"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result))
    return result


def is_us_listed(ticker: str, exchanges: dict) -> bool:
    """False only when the SEC says it trades OTC (or elsewhere). Unknown
    tickers (e.g. later delisted, in old backtest data) are allowed and must
    pass the price and volume test instead."""
    return exchanges.get(ticker) != "OTC"

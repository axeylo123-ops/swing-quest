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
    max_price = u.get("max_price")
    if max_price and price > max_price:
        return {"ok": False, "reason": f"price ${price:.2f} is above your ${max_price:.0f} limit",
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


PROFILE_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
PROFILE_CACHE = CACHE_DIR / "issuer_profiles.json"
FUND_FORMS = {"N-CSR", "N-CSRS", "N-2", "N-PORT"}


class IssuerProfiles:
    """Looks up what kind of company an issuer is (SEC industry code).

    Closed-end funds, interval funds and similar file Form 4s too, but they
    are not operating companies. They have no industry (SIC) code and file
    fund reports (N-CSR), which is how we spot them. Answers are cached on
    disk because they almost never change.
    """

    def __init__(self, client=None, cache_path=PROFILE_CACHE):
        self.client = client
        self.cache_path = cache_path
        self.cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    def get(self, cik: str) -> dict:
        key = str(int(cik))
        if key not in self.cache:
            if self.client is None:
                from swingquest.sec.client import SecClient
                self.client = SecClient()
            j = self.client.get_json(PROFILE_URL.format(cik=int(cik)))
            forms = set(j.get("filings", {}).get("recent", {}).get("form", [])[:300])
            sic = (j.get("sic") or "").strip()
            self.cache[key] = {
                "sic": sic,
                "industry": j.get("sicDescription") or "",
                "is_fund": sic in ("", "0000") or bool(forms & FUND_FORMS),
            }
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache))
        return self.cache[key]


def is_us_listed(ticker: str, exchanges: dict) -> bool:
    """False only when the SEC says it trades OTC (or elsewhere). Unknown
    tickers (e.g. later delisted, in old backtest data) are allowed and must
    pass the price and volume test instead."""
    return exchanges.get(ticker) != "OTC"

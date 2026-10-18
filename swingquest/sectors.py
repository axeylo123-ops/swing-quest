"""Which sector a company is in (from its SEC industry code, "SIC"), and the
sector fund (ETF) we compare it with. Approximate but good enough to ask
"is this stock's industry beating the market right now?"."""

SECTOR_ETFS = {
    "Technology": "XLK", "Financials": "XLF", "Energy": "XLE", "Health Care": "XLV",
    "Industrials": "XLI", "Consumer Discretionary": "XLY", "Consumer Staples": "XLP",
    "Utilities": "XLU", "Materials": "XLB", "Real Estate": "XLRE", "Communication": "XLC",
}

# (first SIC, last SIC, sector). Checked in order: specific ranges come first.
_RANGES = [
    (2830, 2836, "Health Care"), (2840, 2844, "Consumer Staples"), (3570, 3579, "Technology"),
    (3600, 3699, "Technology"), (3710, 3716, "Consumer Discretionary"), (3840, 3851, "Health Care"),
    (3800, 3899, "Technology"), (5122, 5122, "Health Care"), (5140, 5149, "Consumer Staples"),
    (5400, 5499, "Consumer Staples"), (5912, 5912, "Consumer Staples"), (6500, 6599, "Real Estate"),
    (6798, 6798, "Real Estate"), (7370, 7379, "Technology"), (7800, 7999, "Communication"),
    (8000, 8099, "Health Care"),
    (100, 999, "Consumer Staples"), (1000, 1099, "Materials"), (1200, 1299, "Energy"), (1300, 1399, "Energy"),
    (1400, 1499, "Materials"), (1500, 1799, "Industrials"), (2000, 2199, "Consumer Staples"),
    (2200, 2399, "Consumer Discretionary"), (2400, 2499, "Materials"), (2500, 2599, "Consumer Discretionary"),
    (2600, 2699, "Materials"), (2700, 2799, "Communication"), (2800, 2899, "Materials"), (2900, 2999, "Energy"),
    (3000, 3099, "Materials"), (3100, 3199, "Consumer Discretionary"), (3200, 3399, "Materials"),
    (3400, 3599, "Industrials"), (3700, 3799, "Industrials"), (3900, 3999, "Consumer Discretionary"),
    (4000, 4799, "Industrials"), (4800, 4899, "Communication"), (4900, 4999, "Utilities"),
    (5000, 5199, "Industrials"), (5200, 5999, "Consumer Discretionary"), (6000, 6799, "Financials"),
    (7000, 7099, "Consumer Discretionary"), (7200, 7399, "Industrials"), (7500, 7699, "Consumer Discretionary"),
    (8100, 8999, "Industrials"),
]


def sector_of(sic) -> str | None:
    try:
        code = int(str(sic).strip())
    except (TypeError, ValueError):
        return None
    for lo, hi, name in _RANGES:
        if lo <= code <= hi:
            return name
    return None


def etf_of(sector: str | None) -> str | None:
    return SECTOR_ETFS.get(sector) if sector else None

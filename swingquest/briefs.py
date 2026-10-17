"""Short plain-English briefs on YOUR holdings (US and Canadian):
analyst rating and price target, trend, 52-week position, dividend, and
recent insider buying where we have it (US only: Canada's SEDI has no
free data feed).

Privacy: your symbols are saved to data/private/holdings.txt and the
briefs to docs/data/private/briefs.json. Both folders are git-ignored, so
nothing about your holdings is ever committed or published. The briefs show
up in the Treasury when you view the dashboard on your own PC.
"""
import json
import time
from datetime import date, datetime, timedelta, timezone

from swingquest import store
from swingquest.config import DATA_OUT_DIR, ROOT

HOLDINGS_FILE = ROOT / "data" / "private" / "holdings.txt"
BRIEFS_FILE = DATA_OUT_DIR / "private" / "briefs.json"
CANADIAN_SUFFIXES = (".TO", ".V", ".VN", ".CN", ".NE")
RATING_WORDS = {"strong_buy": "Strong buy", "buy": "Buy", "hold": "Hold", "underperform": "Underperform",
                "sell": "Sell", "strong_sell": "Strong sell"}


def yahoo_symbol(sym: str) -> str:
    """Questrade -> Yahoo: TSX Venture '.VN' is '.V' on Yahoo; US class shares use '-'."""
    s = sym.strip().upper()
    if s.endswith(".VN"):
        return s[:-3] + ".V"
    return s


def is_canadian(sym: str) -> bool:
    return sym.upper().endswith(CANADIAN_SUFFIXES)


def rating_word(info: dict) -> str | None:
    key = (info.get("recommendationKey") or "").lower()
    if key in RATING_WORDS:
        return RATING_WORDS[key]
    mean = info.get("recommendationMean")
    if mean is None:
        return None
    return "Strong buy" if mean <= 1.5 else "Buy" if mean <= 2.5 else "Hold" if mean <= 3.5 else "Sell"


def insider_summary(sym: str, buys: list[dict] | None = None, today: date | None = None) -> dict:
    """Open-market insider buying in the last 90 days (from our SEC data)."""
    if is_canadian(sym):
        return {"covered": False}
    today = today or date.today()
    start = (today - timedelta(days=90)).isoformat()
    buys = store.load_buys(start, today.isoformat()) if buys is None else buys
    mine = [b for b in buys if b["ticker"] == sym.upper() and b["filed_date"] >= start]
    return {"covered": True, "count": len(mine), "people": len({b["owner_cik"] for b in mine}),
            "value": round(sum(b["value"] for b in mine), 2)}


def _money(x: float, cur: str) -> str:
    sign = "C$" if cur == "CAD" else "$"
    if x >= 1e6:
        return f"{sign}{x / 1e6:.1f}M"
    return f"{sign}{x:,.0f}" if x >= 1000 else f"{sign}{x:,.2f}"


def sentence(sym: str, info: dict, ins: dict) -> dict:
    """Two plain sentences plus the numbers behind them."""
    cur = info.get("currency") or ("CAD" if is_canadian(sym) else "USD")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    name = info.get("longName") or info.get("shortName") or sym
    parts = []
    if price:
        lo, hi = info.get("fiftyTwoWeekLow"), info.get("fiftyTwoWeekHigh")
        where = f", {round((price - lo) / (hi - lo) * 100)}% of the way up its 52-week range" if lo and hi and hi > lo else ""
        f50, f200 = info.get("fiftyDayAverage"), info.get("twoHundredDayAverage")
        if f50 and f200:
            trend = ("in an uptrend (above its 50- and 200-day averages)" if price > f50 and price > f200
                     else "in a downtrend (below its 50- and 200-day averages)" if price < f50 and price < f200
                     else "in a mixed trend (between its 50- and 200-day averages)")
        else:
            trend = "trend unknown"
        sector = f" ({info['sector']})" if info.get("sector") else ""
        parts.append(f"{name}{sector} trades at {_money(price, cur)}{where}, {trend}.")
    else:
        parts.append(f"{name}: no current price data on Yahoo.")

    second = []
    n, target, rating = info.get("numberOfAnalystOpinions"), info.get("targetMeanPrice"), rating_word(info)
    upside = (target / price - 1) if target and price else None
    if n and target:
        second.append(f"{n} analyst{'s' if n != 1 else ''} rate it {rating or 'without a published rating'}, "
                      f"average target {_money(target, cur)} ({upside * 100:+.0f}%)")
    else:
        second.append("No analyst coverage on Yahoo")
    if not ins.get("covered"):
        second.append("Canadian insider trades aren't covered (no free SEDI feed)")
    elif ins["count"]:
        second.append(f"insiders bought {_money(ins['value'], 'USD')} in the last 90 days "
                      f"({ins['people']} {'person' if ins['people'] == 1 else 'people'})")
    else:
        second.append("no insider buying on file in the last 90 days")
    dy = info.get("dividendYield")
    if dy:
        second.append(f"dividend yield {dy:.1f}%")
    parts.append("; ".join(second) + ".")
    return {"text": " ".join(parts), "name": name, "currency": cur, "price": price, "rating": rating,
            "analysts": n, "target": target, "upside": round(upside, 4) if upside is not None else None,
            "insiders": ins}


def build_briefs(symbols: list[str], fetch_info=None, pause: float = 0.6) -> dict:
    import yfinance as yf
    fetch_info = fetch_info or (lambda s: yf.Ticker(s).info)
    buys = store.load_buys((date.today() - timedelta(days=90)).isoformat())
    out = {}
    for sym in dict.fromkeys(s.strip().upper() for s in symbols if s.strip()):
        try:
            info = fetch_info(yahoo_symbol(sym)) or {}
        except Exception:
            info = {}
        out[sym] = sentence(sym, info, insider_summary(sym, buys))
        time.sleep(pause)  # be gentle with Yahoo
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "briefs": out}


def save_holdings(symbols: list[str]) -> None:
    HOLDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    HOLDINGS_FILE.write_text("\n".join(symbols) + "\n", encoding="utf-8")


def load_holdings() -> list[str]:
    if not HOLDINGS_FILE.exists():
        return []
    return [s.strip() for s in HOLDINGS_FILE.read_text(encoding="utf-8").splitlines() if s.strip()]


def write_briefs(result: dict) -> None:
    BRIEFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    BRIEFS_FILE.write_text(json.dumps(result, indent=1), encoding="utf-8", newline="\n")

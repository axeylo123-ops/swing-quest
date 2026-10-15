"""Cleans up ticker symbols as typed by insiders on their filings."""
import re

_VALID = re.compile(r"^[A-Z]{1,5}(-[A-Z]{1,2})?$")
_JUNK = {"NONE", "NA", "N/A", "NOTICKER", "NOT", "NULL"}


def clean_ticker(raw: str | None) -> str | None:
    """'nyse: brk.b' -> 'BRK-B'. Returns None if it isn't a usable symbol.

    Filers type tickers by hand, so we see things like 'ABC, ABCW',
    'NASDAQ:XYZ' or 'None'. We keep the first plausible symbol and use the
    dash style for share classes (BRK-B), which yfinance and the SEC both use.
    """
    if not raw:
        return None
    t = raw.strip().upper()
    if t in _JUNK:
        return None
    if ":" in t:
        t = t.split(":", 1)[1]
    t = re.split(r"[,;/\s]+", t.strip())[0]
    t = t.replace(".", "-")
    if t in _JUNK or not _VALID.match(t):
        return None
    return t

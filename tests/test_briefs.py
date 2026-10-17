"""Tests for holding briefs (no internet: Yahoo data is faked)."""
from datetime import date

from swingquest import briefs

INFO = {"longName": "Example Corp", "sector": "Energy", "currency": "USD", "currentPrice": 10.0,
        "fiftyTwoWeekLow": 5.0, "fiftyTwoWeekHigh": 15.0, "fiftyDayAverage": 9.0, "twoHundredDayAverage": 8.0,
        "targetMeanPrice": 12.0, "numberOfAnalystOpinions": 7, "recommendationKey": "buy", "dividendYield": 2.5}


def test_questrade_to_yahoo_symbols():
    assert briefs.yahoo_symbol("abc.vn") == "ABC.V"
    assert briefs.yahoo_symbol("SHOP.TO") == "SHOP.TO"
    assert briefs.is_canadian("DML.TO") and briefs.is_canadian("XYZ.VN") and not briefs.is_canadian("PEP")


def test_brief_sentence_has_trend_analysts_insiders_dividend():
    b = briefs.sentence("EXC", INFO, {"covered": True, "count": 2, "people": 2, "value": 1_500_000})
    t = b["text"]
    assert "50% of the way up its 52-week range" in t and "uptrend" in t
    assert "7 analysts rate it Buy" in t and "+20%" in t
    assert "insiders bought $1.5M" in t and "dividend yield 2.5%" in t
    assert b["upside"] == 0.2


def test_canadian_brief_says_insiders_not_covered():
    info = {**INFO, "currency": "CAD"}
    b = briefs.sentence("XYZ.TO", info, briefs.insider_summary("XYZ.TO", buys=[]))
    assert "C$10.00" in b["text"] and "aren't covered" in b["text"]


def test_missing_analysts_and_price():
    b = briefs.sentence("NONE", {"longName": "Tiny Co"}, {"covered": True, "count": 0, "people": 0, "value": 0})
    assert "no current price data" in b["text"] and "No analyst coverage" in b["text"]
    assert "no insider buying" in b["text"]


def test_rating_from_mean_when_key_missing():
    assert briefs.rating_word({"recommendationKey": "none", "recommendationMean": 1.4}) == "Strong buy"
    assert briefs.rating_word({"recommendationMean": 3.0}) == "Hold"
    assert briefs.rating_word({}) is None


def test_insider_summary_counts_last_90_days_only():
    buys = [{"ticker": "EXC", "filed_date": "2026-10-01", "owner_cik": "1", "value": 100.0},
            {"ticker": "EXC", "filed_date": "2026-09-15", "owner_cik": "2", "value": 50.0},
            {"ticker": "EXC", "filed_date": "2026-05-01", "owner_cik": "3", "value": 999.0},
            {"ticker": "OTHER", "filed_date": "2026-10-01", "owner_cik": "4", "value": 7.0}]
    s = briefs.insider_summary("EXC", buys, today=date(2026, 10, 17))
    assert s == {"covered": True, "count": 2, "people": 2, "value": 150.0}


def test_build_briefs_survives_yahoo_errors():
    def fetch(sym):
        if sym == "BAD":
            raise RuntimeError("Yahoo hiccup")
        return INFO
    out = briefs.build_briefs(["EXC", "BAD", "exc"], fetch_info=fetch, pause=0)
    assert set(out["briefs"]) == {"EXC", "BAD"}
    assert "No analyst coverage" in out["briefs"]["BAD"]["text"]

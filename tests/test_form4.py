from pathlib import Path

import pytest

from swingquest.sec import form4

XML = (Path(__file__).parent / "fixtures" / "form4_ceo_buy.xml").read_text()


def record():
    return form4.purchase_record(form4.parse_form4(XML), "0000999001-26-000001", "2026-10-09")


def test_only_common_stock_purchases_are_counted():
    r = record()
    # P lines on common stock: 1000 @ 10.00, 500 @ 10.60, 2000 @ 10.20.
    # Ignored: the sale (S), option exercise (M), and preferred-stock purchase.
    assert r["shares"] == 3500
    assert r["value"] == pytest.approx(10000 + 5300 + 20400)
    assert r["avg_price"] == pytest.approx(35700 / 3500)


def test_size_vs_existing_holdings():
    # Direct account: 11500 after - 1500 bought = 10000 before.
    # Trust account:   7000 after - 2000 bought =  5000 before.
    r = record()
    assert r["holdings_before"] == 15000
    assert r["pct_of_holdings"] == pytest.approx(3500 / 15000, abs=1e-4)


def test_identity_role_and_ticker():
    r = record()
    assert r["ticker"] == "ABCD"
    assert r["role"] == "CEO"
    assert r["trade_date"] == "2026-10-08"
    assert r["plan_10b5_1"] is False


def test_grant_only_filing_gives_no_record():
    doc = form4.parse_form4(XML)
    for ln in doc["lines"]:
        ln["code"] = "A"  # pretend every line is a stock grant
    assert form4.purchase_record(doc, "x", "2026-10-09") is None


def test_amendments_are_skipped():
    doc = form4.parse_form4(XML)
    doc["document_type"] = "4/A"
    assert form4.purchase_record(doc, "x", "2026-10-09") is None


@pytest.mark.parametrize("owner,expected", [
    ({"officer_title": "Chief Executive Officer"}, "CEO"),
    ({"officer_title": "EVP & CFO"}, "CFO"),
    ({"officer_title": "COO", "is_officer": True}, "Officer"),
    ({"is_director": True}, "Director"),
    ({"is_ten_pct": True}, "10% Owner"),
    ({}, "Other"),
])
def test_classify_role(owner, expected):
    assert form4.classify_role(owner) == expected


def test_best_role_picks_most_senior():
    owners = [{"is_ten_pct": True}, {"is_director": True}]
    assert form4.best_role(owners) == "Director"


def test_submission_wrapper():
    txt = ("<SEC-HEADER>\n<ACCEPTANCE-DATETIME>20261014172448\n</SEC-HEADER>"
           "<XML>\n" + XML + "\n</XML>")
    assert form4.accepted_timestamp(txt) == "2026-10-14T17:24:48"
    assert "<ownershipDocument>" in form4.extract_xml(txt)

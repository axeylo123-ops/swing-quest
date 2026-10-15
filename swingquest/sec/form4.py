"""Reads Form 4 filings and keeps only real open-market purchases.

A Form 4 is what an insider files within 2 business days of trading their
company's stock. Each trade line has a code; we only want code "P"
(open-market or private purchase), with "A" (acquired) and a real price.
Option exercises (M), grants (A), sales (S), gifts (G) etc. are ignored.

The work is split in two so the SEC bulk datasets (Phase 3) can reuse it:
  parse_form4()      XML text -> a plain "document" dict
  purchase_record()  document  -> one purchase record (or None)
"""
import re
import xml.etree.ElementTree as ET

from swingquest.tickers import clean_ticker

ROLE_ORDER = ["CEO", "CFO", "Director", "Officer", "10% Owner", "Other"]
_NON_COMMON = re.compile(r"prefer|note|warrant|debenture|right|unit|option|bond", re.I)


def extract_xml(submission_txt: str) -> str | None:
    """A full SEC submission (.txt) wraps the Form 4 XML in <XML> tags."""
    for block in re.findall(r"<XML>(.*?)</XML>", submission_txt, re.S):
        if "<ownershipDocument" in block:
            return block.strip()
    return None


def accepted_timestamp(submission_txt: str) -> str | None:
    """'<ACCEPTANCE-DATETIME>20261014172448' -> '2026-10-14T17:24:48' (ET)."""
    m = re.search(r"<ACCEPTANCE-DATETIME>(\d{14})", submission_txt)
    if not m:
        return None
    s = m.group(1)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:{s[12:14]}"


def _text(el, path: str) -> str | None:
    """Form 4 puts most values in <x><value>...</value></x>; some are bare."""
    node = el.find(path)
    if node is None:
        return None
    inner = node.find("value")
    txt = (inner.text if inner is not None else node.text) or ""
    txt = txt.strip()
    return txt or None


def _num(el, path: str) -> float | None:
    try:
        return float(_text(el, path))
    except (TypeError, ValueError):
        return None


def _flag(el, path: str) -> bool:
    return (_text(el, path) or "").lower() in ("1", "true")


def parse_form4(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    owners = []
    for ro in root.findall("reportingOwner"):
        owners.append({
            "cik": _text(ro, "reportingOwnerId/rptOwnerCik"),
            "name": _text(ro, "reportingOwnerId/rptOwnerName"),
            "is_director": _flag(ro, "reportingOwnerRelationship/isDirector"),
            "is_officer": _flag(ro, "reportingOwnerRelationship/isOfficer"),
            "is_ten_pct": _flag(ro, "reportingOwnerRelationship/isTenPercentOwner"),
            "officer_title": _text(ro, "reportingOwnerRelationship/officerTitle"),
        })
    lines = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        lines.append({
            "title": _text(tx, "securityTitle") or "",
            "date": _text(tx, "transactionDate"),
            "code": _text(tx, "transactionCoding/transactionCode"),
            "shares": _num(tx, "transactionAmounts/transactionShares"),
            "price": _num(tx, "transactionAmounts/transactionPricePerShare"),
            "acq_disp": _text(tx, "transactionAmounts/transactionAcquiredDisposedCode"),
            "shares_after": _num(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction"),
            "ownership": (_text(tx, "ownershipNature/directOrIndirectOwnership") or "D")
                         + "|" + (_text(tx, "ownershipNature/natureOfOwnership") or ""),
        })
    return {
        "document_type": _text(root, "documentType"),
        "issuer_cik": _text(root, "issuer/issuerCik"),
        "issuer_name": _text(root, "issuer/issuerName"),
        "ticker_raw": _text(root, "issuer/issuerTradingSymbol"),
        "plan_10b5_1": _flag(root, "aff10b5One"),
        "owners": owners,
        "lines": lines,
    }


def classify_role(owner: dict) -> str:
    title = (owner.get("officer_title") or "").lower()
    if re.search(r"\bceo\b|chief executive|principal executive", title):
        return "CEO"
    if re.search(r"\bcfo\b|chief financial|principal financial", title):
        return "CFO"
    if owner.get("is_director"):
        return "Director"
    if owner.get("is_officer"):
        return "Officer"
    if owner.get("is_ten_pct"):
        return "10% Owner"
    return "Other"


def best_role(owners: list[dict]) -> str:
    roles = [classify_role(o) for o in owners] or ["Other"]
    return min(roles, key=ROLE_ORDER.index)


def is_purchase_line(line: dict) -> bool:
    return (line["code"] == "P" and line["acq_disp"] == "A"
            and (line["shares"] or 0) > 0 and (line["price"] or 0) > 0
            and not _NON_COMMON.search(line["title"]))


def purchase_record(doc: dict, accession: str, filed_date: str,
                    accepted: str | None = None, source: str = "live") -> dict | None:
    """Combines all purchase lines in one filing into a single record."""
    if doc["document_type"] != "4":
        return None
    buys = [ln for ln in doc["lines"] if is_purchase_line(ln)]
    ticker = clean_ticker(doc["ticker_raw"])
    if not buys or not ticker:
        return None

    shares = sum(ln["shares"] for ln in buys)
    value = sum(ln["shares"] * ln["price"] for ln in buys)

    # Holdings before the purchase, per ownership account (direct, a trust...):
    # the last line's "shares after" minus what was bought in that account.
    holdings_before, known = 0.0, True
    for acct in {ln["ownership"] for ln in buys}:
        acct_lines = [ln for ln in buys if ln["ownership"] == acct]
        after = acct_lines[-1]["shares_after"]
        if after is None:
            known = False
            continue
        holdings_before += max(after - sum(ln["shares"] for ln in acct_lines), 0.0)
    pct = (shares / holdings_before) if known and holdings_before > 0 else None

    primary = doc["owners"][0] if doc["owners"] else {}
    dates = sorted(ln["date"][:10] for ln in buys if ln["date"])
    return {
        "accession": accession,
        "filed_date": filed_date,
        "accepted": accepted,
        "ticker": ticker,
        "issuer_cik": doc["issuer_cik"],
        "issuer_name": doc["issuer_name"],
        "owner_cik": primary.get("cik"),
        "owner_name": primary.get("name"),
        "owner_ciks": [o["cik"] for o in doc["owners"]],
        "role": best_role(doc["owners"]),
        "officer_title": next((o["officer_title"] for o in doc["owners"] if o["officer_title"]), None),
        "plan_10b5_1": doc["plan_10b5_1"],
        "trade_date": dates[0] if dates else None,
        "shares": shares,
        "avg_price": round(value / shares, 4),
        "value": round(value, 2),
        "holdings_before": holdings_before if known else None,
        "pct_of_holdings": round(pct, 4) if pct is not None else None,  # None = new or unknown
        "source": source,
    }

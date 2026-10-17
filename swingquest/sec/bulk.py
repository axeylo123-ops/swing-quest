"""Backfill from the SEC's quarterly "Insider Transactions Data Sets".

Each quarter is one ~10 MB zip of tab-separated tables (every Form 3/4/5
filed that quarter). Far fewer requests than downloading filings one by
one. We rebuild the same "document" shape that form4.parse_form4() makes,
so purchase_record() treats bulk and live data identically.
"""
import csv
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from swingquest import store
from swingquest.config import CACHE_DIR
from swingquest.sec import feed, form4
from swingquest.sec.fetch import _process

BULK_URL = ("https://www.sec.gov/files/structureddata/data/"
            "insider-transactions-data-sets/{q}_form345.zip")
BULK_DIR = CACHE_DIR / "bulk"


def quarters(first: str, last: str) -> list[str]:
    """quarters('2022q4', '2023q2') -> ['2022q4', '2023q1', '2023q2']"""
    y, q = int(first[:4]), int(first[-1])
    out = []
    while f"{y}q{q}" <= last:
        out.append(f"{y}q{q}")
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)
    return out


def quarter_start(q: str) -> str:
    return date(int(q[:4]), 3 * (int(q[-1]) - 1) + 1, 1).isoformat()


def download_quarter(client, q: str) -> Path:
    BULK_DIR.mkdir(parents=True, exist_ok=True)
    path = BULK_DIR / f"{q}_form345.zip"
    if not path.exists():
        path.write_bytes(client.get(BULK_URL.format(q=q)).content)
    return path


def _table(z: zipfile.ZipFile, name: str) -> pd.DataFrame:
    return pd.read_csv(z.open(name), sep="\t", dtype=str, quoting=csv.QUOTE_NONE,
                       keep_default_na=False)


def _num(x: str) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def records_from_zip(path: Path) -> list[dict]:
    z = zipfile.ZipFile(path)
    trans = _table(z, "NONDERIV_TRANS.tsv")
    trans = trans[trans["TRANS_CODE"] == "P"]
    wanted = set(trans["ACCESSION_NUMBER"])
    subs = _table(z, "SUBMISSION.tsv")
    subs = subs[subs["ACCESSION_NUMBER"].isin(wanted)]
    owners = _table(z, "REPORTINGOWNER.tsv")
    owners = owners[owners["ACCESSION_NUMBER"].isin(wanted)]

    owners_by_acc = {acc: g for acc, g in owners.groupby("ACCESSION_NUMBER", sort=False)}
    trans["SK"] = trans["NONDERIV_TRANS_SK"].astype(int)
    trans_by_acc = {acc: g.sort_values("SK") for acc, g in trans.groupby("ACCESSION_NUMBER")}

    records = []
    for s in subs.itertuples(index=False):
        acc = s.ACCESSION_NUMBER
        doc = {
            "document_type": s.DOCUMENT_TYPE,
            "issuer_cik": s.ISSUERCIK,
            "issuer_name": s.ISSUERNAME,
            "ticker_raw": s.ISSUERTRADINGSYMBOL,
            # the 10b5-1 plan flag only exists in filings from April 2023 on
            "plan_10b5_1": getattr(s, "AFF10B5ONE", "").lower() in ("1", "true"),
            "owners": [{
                "cik": o.RPTOWNERCIK,
                "name": o.RPTOWNERNAME,
                "is_director": "Director" in o.RPTOWNER_RELATIONSHIP,
                "is_officer": "Officer" in o.RPTOWNER_RELATIONSHIP,
                "is_ten_pct": "TenPercentOwner" in o.RPTOWNER_RELATIONSHIP,
                "officer_title": o.RPTOWNER_TITLE or None,
            } for o in owners_by_acc.get(acc, pd.DataFrame()).itertuples(index=False)],
            "lines": [{
                "title": t.SECURITY_TITLE,
                "date": _bulk_date(t.TRANS_DATE),
                "code": t.TRANS_CODE,
                "shares": _num(t.TRANS_SHARES),
                "price": _num(t.TRANS_PRICEPERSHARE),
                "acq_disp": t.TRANS_ACQUIRED_DISP_CD,
                "shares_after": _num(t.SHRS_OWND_FOLWNG_TRANS),
                "ownership": (t.DIRECT_INDIRECT_OWNERSHIP or "D") + "|" + t.NATURE_OF_OWNERSHIP,
            } for t in trans_by_acc[acc].itertuples(index=False)],
        }
        rec = form4.purchase_record(doc, acc, _bulk_date(s.FILING_DATE), source="bulk")
        if rec:
            records.append(rec)
    return records


def _bulk_date(s: str) -> str | None:
    """'31-MAR-2026' -> '2026-03-31'"""
    try:
        return datetime.strptime(s, "%d-%b-%Y").date().isoformat()
    except (TypeError, ValueError):
        return None


def backfill_bulk(client, first: str, last: str, progress=print) -> dict:
    total = 0
    for q in quarters(first, last):
        recs = records_from_zip(download_quarter(client, q))
        new = store.save_buys(recs)
        total += len(recs)
        progress(f"  {q}: {len(recs)} purchases ({new} new)")
    state = store.load_state()
    start = quarter_start(first)
    if state.get("history_start") is None or start < state["history_start"]:
        state["history_start"] = start
    state["bulk_through"] = max(state.get("bulk_through", ""), last)
    store.save_state(state)
    return {"quarters": len(quarters(first, last)), "purchases": total}


def backfill_days(client, start: date, end: date, progress=print) -> dict:
    """Gap-fill day by day from the nightly index. Resumable: finished days
    are remembered in data/state.json, so you can stop and re-run."""
    state = store.load_state()
    done = set(state.get("filled_days", []))
    d, total = start, 0
    while d <= end:
        if d.weekday() < 5 and d.isoformat() not in done:
            try:
                text = client.get_text(feed.daily_index_url(d))
            except Exception as e:  # 404 = market holiday, no index that day
                if "404" not in str(e) and "403" not in str(e):
                    raise
                text = ""
            refs = feed.parse_daily_index(text)
            recs = _process(client, refs)
            store.save_buys(recs)
            total += len(recs)
            done.add(d.isoformat())
            state["filled_days"] = sorted(done)
            store.save_state(state)
            progress(f"  {d}: {len(refs)} filings, {len(recs)} purchases")
        d += timedelta(days=1)
    return {"purchases": total}

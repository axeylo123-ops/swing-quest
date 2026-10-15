"""Downloads Form 4 filings and turns them into purchase records."""
from datetime import date, datetime, timedelta, timezone

from swingquest import store
from swingquest.sec import feed, form4


def fetch_record(client, ref: feed.FilingRef) -> dict | None:
    txt = client.get_text(ref.txt_url)
    xml = form4.extract_xml(txt)
    if not xml:
        return None
    try:
        doc = form4.parse_form4(xml)
    except Exception:  # a handful of filings have broken XML; skip them
        return None
    return form4.purchase_record(doc, ref.accession, ref.filed_date,
                                 accepted=form4.accepted_timestamp(txt) or ref.accepted)


def _process(client, refs, progress=None) -> list[dict]:
    records = []
    for i, ref in enumerate(refs, 1):
        try:
            rec = fetch_record(client, ref)
        except Exception as e:  # one bad filing shouldn't stop the run
            print(f"  ! skipped {ref.accession}: {e}")
            continue
        if rec:
            records.append(rec)
        if progress and i % 100 == 0:
            progress(i, len(refs), len(records))
    return records


def fetch_latest(client, lookback_hours: float = 36, progress=print) -> dict:
    """Reads new filings from the live feed since the last run.

    The cursor (newest filing time seen) is saved in data/state.json, so each
    run only downloads what's new. A 2-hour overlap guards against gaps.
    """
    state = store.load_state()
    now = datetime.now(timezone.utc)
    if "feed_cursor" in state:
        since = datetime.fromisoformat(state["feed_cursor"]) - timedelta(hours=2)
    else:
        since = now - timedelta(hours=lookback_hours)
    seen: dict = state.get("recent_accessions", {})  # accession -> filed date

    refs = [r for r in feed.fetch_feed_since(client, since) if r.accession not in seen]
    report = lambda i, n, k: progress(f"  read {i}/{n} filings, {k} purchases so far")
    records = _process(client, refs, report)
    new = store.save_buys(records)

    if refs:
        newest = max(datetime.fromisoformat(r.accepted) for r in refs if r.accepted)
        state["feed_cursor"] = max(newest, since + timedelta(hours=2)).isoformat()
    # remember the last few days of accessions so the overlap isn't re-downloaded
    seen.update({r.accession: r.filed_date for r in refs})
    cutoff = (now - timedelta(days=5)).date().isoformat()
    state["recent_accessions"] = {a: d for a, d in seen.items() if d >= cutoff}
    state["last_fetch_utc"] = now.isoformat(timespec="seconds")
    store.save_state(state)
    return {"filings_read": len(refs), "purchases": len(records), "new_purchases": new}


def fetch_day(client, day: date, progress=print) -> dict:
    """Reads every Form 4 from one day's nightly index (gap-filling)."""
    refs = feed.parse_daily_index(client.get_text(feed.daily_index_url(day)))
    report = lambda i, n, k: progress(f"  read {i}/{n} filings, {k} purchases so far")
    records = _process(client, refs, report)
    new = store.save_buys(records)
    return {"filings_read": len(refs), "purchases": len(records), "new_purchases": new}

"""Finds Form 4 filings to read.

Two sources:
- The real-time "latest filings" feed: updated within minutes, reaches back
  a few days. Used for the daily scans.
- The nightly daily index (published ~10 pm ET): the complete list for one
  day. Used to fill gaps if a scan was missed.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime
from html import unescape

ARCHIVE = "https://www.sec.gov/Archives/"
FEED_URL = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4"
            "&company=&dateb=&owner=include&start={start}&count=100&output=atom")
DAILY_INDEX_URL = ARCHIVE + "edgar/daily-index/{y}/QTR{q}/form.{ymd}.idx"
PAGE_SIZE = 100


@dataclass(frozen=True)
class FilingRef:
    accession: str          # unique filing ID, e.g. 0001225028-26-000006
    cik: str                # a CIK the filing is stored under (issuer or owner)
    filed_date: str         # YYYY-MM-DD
    accepted: str | None = None  # ISO timestamp when the SEC published it

    @property
    def txt_url(self) -> str:
        return f"{ARCHIVE}edgar/data/{int(self.cik)}/{self.accession}.txt"


def parse_feed(atom_text: str) -> list[FilingRef]:
    refs = []
    for entry in re.findall(r"<entry>(.*?)</entry>", atom_text, re.S):
        form = re.search(r'term="([^"]+)"', entry)
        if not form or form.group(1) != "4":
            continue  # skip amendments (4/A) and anything else
        acc = re.search(r"accession-number=([\d-]+)", entry)
        cik = re.search(r"/edgar/data/(\d+)/", entry)
        filed = re.search(r"Filed:</b>\s*(\d{4}-\d{2}-\d{2})", unescape(entry))
        updated = re.search(r"<updated>(.*?)</updated>", entry)
        if acc and cik and filed:
            refs.append(FilingRef(acc.group(1), cik.group(1), filed.group(1),
                                  updated.group(1) if updated else None))
    return refs


def fetch_feed_since(client, since: datetime, max_pages: int = 80) -> list[FilingRef]:
    """Pages back through the live feed until filings are older than `since`."""
    seen, out = set(), []
    for page in range(max_pages):
        refs = parse_feed(client.get_text(FEED_URL.format(start=page * PAGE_SIZE)))
        if not refs:
            break
        reached_old = False
        for r in refs:
            if r.accepted and datetime.fromisoformat(r.accepted) < since:
                reached_old = True
                continue
            if r.accession not in seen:
                seen.add(r.accession)
                out.append(r)
        if reached_old:
            break
    return out


def daily_index_url(d: date) -> str:
    return DAILY_INDEX_URL.format(y=d.year, q=(d.month - 1) // 3 + 1, ymd=d.strftime("%Y%m%d"))


def parse_daily_index(text: str) -> list[FilingRef]:
    """Reads the fixed-width form.YYYYMMDD.idx file, keeping only Form 4s."""
    refs, seen = [], set()
    for line in text.splitlines():
        tokens = line.split()
        if len(tokens) < 4 or tokens[0] != "4" or not tokens[-1].startswith("edgar/"):
            continue
        path, ymd, cik = tokens[-1], tokens[-2], tokens[-3]
        acc = path.rsplit("/", 1)[-1].removesuffix(".txt")
        if acc in seen:
            continue
        seen.add(acc)
        refs.append(FilingRef(acc, cik, f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"))
    return refs

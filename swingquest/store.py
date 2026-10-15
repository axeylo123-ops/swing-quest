"""Saves and loads insider purchase records.

Records live in data/insider_buys/YYYY-MM.json (one file per month of
filing date), keyed by accession number so re-running never duplicates.
Small, readable files that are easy to commit and diff.
"""
import json
from pathlib import Path

from swingquest.config import ROOT

BUYS_DIR = ROOT / "data" / "insider_buys"
STATE_FILE = ROOT / "data" / "state.json"


def _month_file(month: str, base: Path) -> Path:
    return base / f"{month}.json"


def save_buys(records: list[dict], base: Path = BUYS_DIR) -> int:
    """Merges records into the monthly files. Returns how many were new."""
    base.mkdir(parents=True, exist_ok=True)
    by_month: dict[str, list[dict]] = {}
    for r in records:
        by_month.setdefault(r["filed_date"][:7], []).append(r)
    new = 0
    for month, recs in by_month.items():
        path = _month_file(month, base)
        existing = {r["accession"]: r for r in _read(path)}
        for r in recs:
            new += r["accession"] not in existing
            existing[r["accession"]] = r
        rows = sorted(existing.values(), key=lambda r: (r["filed_date"], r["ticker"], r["accession"]))
        path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return new


def load_buys(start: str | None = None, end: str | None = None, base: Path = BUYS_DIR) -> list[dict]:
    """All records with start <= filed_date <= end (YYYY-MM-DD strings)."""
    out = []
    for path in sorted(base.glob("*.json")):
        month = path.stem
        if (start and month < start[:7]) or (end and month > end[:7]):
            continue
        out.extend(r for r in _read(path)
                   if (not start or r["filed_date"] >= start) and (not end or r["filed_date"] <= end))
    return out


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_state(path: Path = STATE_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_state(state: dict, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")

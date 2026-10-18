"""Live track record of the ranking system.

Each day the top ideas and the watchlist are logged (once per stock per
21 days) with their Conviction, pillars and trade plan, then graded with
the same trade rules as the backtest. Writes docs/data/record.json for the
Record tab, and keeps pillar scores so we can learn which pillars work.
"""
import json
from datetime import date, datetime, timezone

from swingquest import tracker
from swingquest.backtest import scorecard
from swingquest.config import DATA_OUT_DIR, ROOT, settings

LOG_FILE = ROOT / "data" / "signals" / "board_log.json"
RECORD_FILE = DATA_OUT_DIR / "record.json"
GAP_DAYS = 21


def load() -> list[dict]:
    return json.loads(LOG_FILE.read_text(encoding="utf-8")) if LOG_FILE.exists() else []


def to_row(s: dict, kind: str) -> dict | None:
    pl = s.get("plan")
    if not pl:
        return None
    atr = (pl["reference"] - pl["stop"]) / settings()["trade"]["stop_atr_multiple"]
    return {
        "id": f"{s['ticker']}-{s['as_of']}", "ticker": s["ticker"], "signal_date": s["as_of"], "kind": kind,
        "status": "pick" if kind == "top" else "watch", "conviction": s["conviction"], "rank": s["rank"],
        "verdict": s["verdict"], "timing": s["timing"], "country": s["country"], "sector": s.get("sector"),
        **{f"{k}_frac": round(v / 100, 3) for k, v in s["pillars"].items()},
        "plan": pl, "atr": atr, "exit_reason": None,
    }


def log(board: dict, rows: list[dict] | None = None) -> tuple[list[dict], int]:
    rows = list(load() if rows is None else rows)
    latest = {}
    for r in rows:
        if r["ticker"] not in latest or r["signal_date"] > latest[r["ticker"]]["signal_date"]:
            latest[r["ticker"]] = r
    added = 0
    for kind, items in (("top", board["top"]), ("watch", board["watch"])):
        for s in items:
            prev = latest.get(s["ticker"])
            if prev and (date.fromisoformat(s["as_of"]) - date.fromisoformat(prev["signal_date"])).days <= GAP_DAYS:
                if kind == "top" and prev["kind"] != "top" and prev.get("entry_date") is None:
                    new = to_row(s, kind)          # a watched stock became a top idea before entry
                    if new:
                        rows[rows.index(prev)] = new
                        latest[s["ticker"]] = new
                continue
            new = to_row(s, kind)
            if new:
                rows.append(new)
                latest[s["ticker"]] = new
                added += 1
    return rows, added


def save(rows: list[dict]) -> None:
    tracker.save_log(rows, LOG_FILE)


def write_record(rows: list[dict]) -> dict:
    top = [r for r in rows if r["kind"] == "top"]
    open_rows = [r for r in top if r.get("exit_reason") not in tracker.FINAL]
    keep = ["ticker", "signal_date", "entry_date", "entry", "conviction", "return_now", "exit_reason", "trade_return", "excess_15"]
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "started": min((r["signal_date"] for r in rows), default=None),
        "summary": scorecard.stats(top),
        "watch_summary": scorecard.stats([r for r in rows if r["kind"] == "watch"]),
        "open": [{k: r.get(k) for k in keep} for r in sorted(open_rows, key=lambda r: r["signal_date"], reverse=True)],
        "closed": [{k: r.get(k) for k in keep} for r in sorted((r for r in top if r.get("exit_reason") in tracker.FINAL),
                                                              key=lambda r: r.get("exit_date") or "", reverse=True)[:30]],
        "logged": len(rows),
    }
    RECORD_FILE.parent.mkdir(parents=True, exist_ok=True)
    RECORD_FILE.write_text(json.dumps(out, indent=1, allow_nan=False), encoding="utf-8", newline="\n")
    return out


def run(board: dict) -> dict:
    rows, added = log(board)
    rows = tracker.update_outcomes(rows)
    save(rows)
    rec = write_record(rows)
    return {"added": added, "open": len(rec["open"]), "logged": rec["logged"]}

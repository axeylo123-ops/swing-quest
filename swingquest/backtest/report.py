"""Writes the scorecard files the dashboard reads.

data/backtest/rows.json   every backtest signal and its outcome (one per line)
docs/data/scorecard.json  the summarized scorecard (backtest + live)
"""
import json
from datetime import datetime, timezone

from swingquest.backtest import scorecard
from swingquest.config import DATA_OUT_DIR, ROOT
from swingquest.signals.scoring import load_weights

ROWS_FILE = ROOT / "data" / "backtest" / "rows.json"
META_FILE = ROOT / "data" / "backtest" / "meta.json"
SCORECARD_FILE = DATA_OUT_DIR / "scorecard.json"
NOTES = [
    "Prices come from yfinance, which has no data for many delisted companies, so failed "
    "companies drop out and results are probably somewhat better than reality (survivorship bias).",
    "Groups with fewer than 30 finished signals are marked 'not enough data'.",
    "A factor counts as 'strong' when it earned at least half of its weight.",
]


def write_lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[\n" + ",\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n]\n",
                    encoding="utf-8", newline="\n")


def save_backtest(rows: list[dict], meta: dict) -> dict:
    write_lines(ROWS_FILE, rows)
    META_FILE.write_text(json.dumps(meta, indent=1), encoding="utf-8", newline="\n")
    return write_scorecard()


HISTORY_FILE = DATA_OUT_DIR / "history.json"
HISTORY_FIELDS = ["signal_date", "score", "status", "timing", "role", "cluster_points",
                  "excess_15", "ret_15", "taken", "trade_return", "exit_reason", "source", "entry",
                  "rs_3m", "sector_rs", "sector", "earnings_in_window"]


def write_history(rows: list[dict], live_rows: list[dict] | None = None) -> None:
    """Compact table of every FINISHED signal for the dashboard's interactive
    explorer ("Ask the Oracle") and the "quests like this" track record."""
    out = []
    for source, rs in (("backtest", rows), ("live", live_rows or [])):
        for r in scorecard.finished(rs):
            r = {**r, "source": source}
            out.append([r.get(f) for f in HISTORY_FIELDS])
    out.sort(key=lambda x: x[0])
    HISTORY_FILE.write_text(json.dumps({"fields": HISTORY_FIELDS, "rows": out}, separators=(",", ":")),
                            encoding="utf-8", newline="\n")


def write_scorecard(live_rows: list[dict] | None = None) -> dict:
    """Rebuilds scorecard.json from the saved backtest rows (+ live rows if any)."""
    weights = load_weights()["weights"]
    rows = json.loads(ROWS_FILE.read_text(encoding="utf-8")) if ROWS_FILE.exists() else []
    meta = json.loads(META_FILE.read_text(encoding="utf-8")) if META_FILE.exists() else {}
    card = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "backtest": {**meta, **scorecard.build(rows, weights)} if rows else None,
        "live": scorecard.build(live_rows, weights) if live_rows else None,
        "notes": NOTES,
    }
    DATA_OUT_DIR.mkdir(parents=True, exist_ok=True)
    SCORECARD_FILE.write_text(json.dumps(card, indent=1), encoding="utf-8", newline="\n")
    write_history(rows, live_rows)
    return card

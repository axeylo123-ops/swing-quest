"""Live signal log: every signal the daily scan scores is recorded once and
graded automatically, using exactly the same trade rules as the backtest.

data/signals/live.json   every live signal (quests, rumors and below-score
                         ones, so the weekly report can learn from all of them)
docs/data/live.json      what the dashboard shows: open quests and results
"""
import json
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from swingquest.backtest.engine import EVENT_GAP_DAYS, _row
from swingquest.backtest.outcomes import measure
from swingquest.backtest import scorecard
from swingquest.config import DATA_OUT_DIR, ROOT, settings
from swingquest.prices.base import get_price_source
from swingquest.signals.scoring import load_weights

LOG_FILE = ROOT / "data" / "signals" / "live.json"
OUT_FILE = DATA_OUT_DIR / "live.json"
FINAL = {"target", "stop", "time", "skipped"}


def load_log(path=LOG_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def save_log(rows: list[dict], path=LOG_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: (r["signal_date"], r["ticker"]))
    path.write_text("[\n" + ",\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n]\n",
                    encoding="utf-8", newline="\n")


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def to_row(setup: dict, as_of: str) -> dict:
    filed = max(b["filed_date"] for b in setup["insiders"])
    row = _row(setup["ticker"], filed, pd.Timestamp(as_of), setup, {})
    row.update({
        "company": setup.get("company"),
        "plan": setup["plan"],
        "atr": setup["indicators"]["atr"],
        "exit_reason": None,
    })
    return row


def log_signals(evaluated: list[dict], as_of: str, rows: list[dict] | None = None,
                trigger_days: int | None = None) -> tuple[list[dict], int]:
    """Adds today's scored setups. One signal per stock per buying event
    (21 days), like the backtest. A rumor that turns into a quest within the
    trigger window is upgraded to a quest. Returns (rows, number added)."""
    rows = list(load_log() if rows is None else rows)
    trigger_days = trigger_days or load_weights()["rules"]["trigger_days"]
    latest = {}
    for r in rows:
        if r["ticker"] not in latest or r["signal_date"] > latest[r["ticker"]]["signal_date"]:
            latest[r["ticker"]] = r
    added = 0
    for s in evaluated:
        new = to_row(s, as_of)
        prev = latest.get(s["ticker"])
        if prev and _days(prev["signal_date"], as_of) <= EVENT_GAP_DAYS:
            not_started = prev.get("entry_date") is None
            if (s["status"] == "pick" and prev["status"] != "pick" and not_started
                    and _days(prev["signal_date"], as_of) <= trigger_days):
                rows[rows.index(prev)] = new
                latest[s["ticker"]] = new
            continue
        rows.append(new)
        latest[s["ticker"]] = new
        added += 1
    return rows, added


def update_outcomes(rows: list[dict], source=None, today: date | None = None) -> list[dict]:
    """Grades every unfinished signal with the latest prices."""
    todo = [r for r in rows if r.get("exit_reason") not in FINAL]
    if not todo:
        return rows
    trade_cfg = settings()["trade"]
    today = today or datetime.now(timezone.utc).date()
    start = date.fromisoformat(min(r["signal_date"] for r in todo)) - timedelta(days=10)
    source = source or get_price_source()
    prices = source.history(sorted({r["ticker"] for r in todo}) + ["SPY"], start, today)
    spy = prices.get("SPY")
    for r in todo:
        df, day = prices.get(r["ticker"]), pd.Timestamp(r["signal_date"])
        if df is None or spy is None or day not in df.index:
            continue
        out = measure(df, spy, day, r["atr"], r["plan"]["entry_high"], trade_cfg)
        r.update(out)
        last = df.iloc[-1]
        r["last_close"] = round(float(last["close"]), 4)
        r["last_date"] = f"{df.index[-1]:%Y-%m-%d}"
        if r.get("entry"):
            r["return_now"] = round(r["last_close"] / r["entry"] - 1, 5)
    return rows


def dashboard_view(rows: list[dict]) -> dict:
    """Open quests (picks you could be holding) and recent results."""
    quests = [r for r in rows if r["status"] == "pick"]
    open_q = [r for r in quests if r.get("exit_reason") not in FINAL]
    closed = sorted((r for r in quests if r.get("exit_reason") in FINAL),
                    key=lambda r: r.get("exit_date") or r["signal_date"], reverse=True)
    keep = ["id", "ticker", "company", "score", "signal_date", "entry_date", "entry", "stop", "target",
            "plan", "last_close", "last_date", "return_now", "days_held", "exit_reason", "exit_date",
            "exit_price", "trade_return", "excess_15", "taken", "skip_reason"]
    pick = lambda r: {k: r.get(k) for k in keep}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "open": [pick(r) for r in open_q],
        "closed": [pick(r) for r in closed[:30]],
        "summary": scorecard.stats(quests),
        "logged_signals": len(rows),
    }


def write_dashboard(rows: list[dict]) -> dict:
    view = dashboard_view(rows)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(view, indent=1), encoding="utf-8", newline="\n")
    return view

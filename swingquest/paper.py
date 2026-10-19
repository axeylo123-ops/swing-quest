"""Price feed for paper trading (the Paper tab's bubbles).

Your paper trades live only in your browser, so the bot never knows which
stocks you bought. Instead it publishes daily bars for EVERY stock that was on
any list (top ideas, high-upside, waiting, watchlist) in the last 120 days,
and your browser grades your trades from those, with the same rules the
Record uses. It also publishes the system's own picks so they can be shown as
bubbles beside yours.

data/signals/list_history.json   {ticker: {"first": date, "last": date}} seen on a list
docs/data/paper.json             {"as_of", "bars": {ticker: [[date, o, h, l, c], ...]}, "system": [...]}
"""
import json
import math
from datetime import date, timedelta

from swingquest.config import DATA_OUT_DIR, ROOT

HISTORY_FILE = ROOT / "data" / "signals" / "list_history.json"
PAPER_FILE = DATA_OUT_DIR / "paper.json"
WINDOW_DAYS = 120
LISTS = ("top", "high", "high_wait", "watch")


def update_history(board: dict, history: dict, today: str) -> dict:
    """Remembers when each stock was first and last on a list (restarting after it falls out of the window)."""
    cutoff = (date.fromisoformat(today) - timedelta(days=WINDOW_DAYS)).isoformat()
    out = {t: v for t, v in history.items() if v["last"] >= cutoff}
    for kind in LISTS:
        for s in board.get(kind, []):
            t = s["ticker"]
            out[t] = {"first": out[t]["first"] if t in out else today, "last": today}
    return out


def _bar(day, row) -> list | None:
    vals = [float(row[k]) for k in ("open", "high", "low", "close")]
    if not all(math.isfinite(v) and v > 0 for v in vals):
        return None
    return [f"{day:%Y-%m-%d}"] + [round(v, 4) for v in vals]


def bars_for(history: dict, price_data: dict, start_pad_days: int = 7) -> dict:
    """Daily bars per ticker from a week before it first appeared, up to the latest close."""
    out = {}
    for t, v in sorted(history.items()):
        df = price_data.get(t)
        if df is None or df.empty:
            continue
        start = date.fromisoformat(v["first"]) - timedelta(days=start_pad_days)
        part = df.loc[str(start):]
        rows = [b for b in (_bar(d, r) for d, r in part.iterrows()) if b]
        if rows:
            out[t] = rows
    return out


def system_picks(rows: list[dict], cutoff: str) -> list[dict]:
    """The system's own top and high-upside picks, as $100 paper trades."""
    keep = ("id", "ticker", "kind", "signal_date", "conviction", "plan", "reason",
            "entry_date", "entry", "exit_reason", "exit_date", "exit_price", "trade_return", "taken", "skip_reason")
    out = []
    for r in rows:
        if r.get("kind") in ("top", "high") and r["signal_date"] >= cutoff:
            p = r["plan"]
            out.append({k: r.get(k) for k in keep} | {"plan": {k: p.get(k) for k in
                       ("entry_low", "entry_high", "stop", "target", "time_stop_days", "reference")}})
    return sorted(out, key=lambda r: r["signal_date"])


def publish(board: dict, rows: list[dict], price_data: dict | None, today: str | None = None, source=None) -> dict:
    """Updates the list history and writes docs/data/paper.json."""
    today = today or (board["ranked"][0]["as_of"] if board.get("ranked") else date.today().isoformat())
    history = json.loads(HISTORY_FILE.read_text(encoding="utf-8")) if HISTORY_FILE.exists() else {}
    history = update_history(board, history, today)
    for r in rows:                                   # logged picks count as "seen" too (covers older lists)
        if r["signal_date"] >= (date.fromisoformat(today) - timedelta(days=WINDOW_DAYS)).isoformat():
            h = history.setdefault(r["ticker"], {"first": r["signal_date"], "last": r["signal_date"]})
            h["first"], h["last"] = min(h["first"], r["signal_date"]), max(h["last"], r["signal_date"])
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=0, sort_keys=True), encoding="utf-8", newline="\n")

    prices = dict(price_data or {})
    need = [t for t in list(history) + ["SPY"] if t not in prices]
    if need:                                          # stocks that dropped out of today's universe
        from swingquest.prices.base import get_price_source
        start = date.fromisoformat(min(v["first"] for v in history.values()) if history else today) - timedelta(days=10)
        try:
            prices.update((source or get_price_source()).history(need, start, date.fromisoformat(today)))
        except Exception:
            pass
    cutoff = (date.fromisoformat(today) - timedelta(days=WINDOW_DAYS)).isoformat()
    bars = bars_for({**history, "SPY": {"first": min([v["first"] for v in history.values()] or [today])}}, prices)
    out = {"as_of": today, "window_days": WINDOW_DAYS, "bars": bars, "system": system_picks(rows, cutoff)}
    PAPER_FILE.parent.mkdir(parents=True, exist_ok=True)
    PAPER_FILE.write_text(json.dumps(out, separators=(",", ":"), allow_nan=False), encoding="utf-8", newline="\n")
    return {"tickers": len(bars), "system": len(out["system"])}

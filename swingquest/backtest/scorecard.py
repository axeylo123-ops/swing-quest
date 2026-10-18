"""Turns signal outcomes into an honest scorecard.

Two kinds of numbers:
- Forward returns (all finished signals): did the stock beat SPY over
  5/10/15 trading days, whether or not a trade was taken?
- Trade results (signals where the trade rules let us in): win rate,
  average return, average R (profit measured in units of risk), and how
  often the target vs the stop was hit first.

Any group with fewer than 30 finished signals is flagged "not enough data".
"""
from statistics import mean

from swingquest.signals.scoring import FACTORS

MIN_SAMPLES = 30
BUCKETS = [(0, 39, "0-39"), (40, 59, "40-59"), (60, 79, "60-79"), (80, 100, "80-100")]


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(mean(xs), 5) if xs else None


def _rate(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(1 for x in xs if x) / len(xs), 4) if xs else None


def finished(rows: list[dict]) -> list[dict]:
    """Signals whose 15-day window is over (open trades don't count yet)."""
    return [r for r in rows if r.get("ret_15") is not None and r.get("exit_reason") != "open"]


def stats(rows: list[dict]) -> dict:
    done = finished(rows)
    trades = [r for r in done if r.get("taken")]
    n = len(done)
    return {
        "n": n,
        "n_trades": len(trades),
        "enough_data": n >= MIN_SAMPLES,
        "label": None if n >= MIN_SAMPLES else "not enough data",
        # forward returns, all finished signals
        "avg_ret_5": _avg(r["ret_5"] for r in done),
        "avg_ret_10": _avg(r["ret_10"] for r in done),
        "avg_ret_15": _avg(r["ret_15"] for r in done),
        "avg_excess_15": _avg(r["excess_15"] for r in done),
        "beat_spy_rate": _rate(None if r["excess_15"] is None else r["excess_15"] > 0 for r in done),
        # trade results
        "win_rate": _rate(r["trade_return"] > 0 for r in trades),
        "avg_trade_return": _avg(r["trade_return"] for r in trades),
        "avg_r": _avg(r["r_multiple"] for r in trades),
        "target_first": _rate(r["exit_reason"] == "target" for r in trades),
        "stop_first": _rate(r["exit_reason"] == "stop" for r in trades),
        "time_exit": _rate(r["exit_reason"] == "time" for r in trades),
    }


def bucket_of(score: int) -> str:
    return next(label for lo, hi, label in BUCKETS if lo <= score <= hi)


def group(rows, key) -> dict:
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(key(r), []).append(r)
    return {k: stats(v) for k, v in sorted(groups.items())}


def is_strong(row: dict, factor: str, weight: float) -> bool | None:
    """Did this factor earn at least half of its possible points? Uses the
    stored fraction when present (works even for weight-0 'observed' factors);
    None = can't tell (older rows without that factor)."""
    frac = row.get(f"{factor}_frac")
    if frac is not None:
        return frac >= 0.5
    if weight <= 0 or f"{factor}_points" not in row:
        return None
    return (row.get(f"{factor}_points") or 0) >= weight / 2


def factor_table(rows: list[dict], weights: dict) -> dict:
    """For each factor: signals where it was STRONG (earned at least half its
    weight) vs WEAK. 'edge' = difference in average 15-day return vs SPY
    (strong minus weak). Half-weight works for every factor, including role,
    where everyone earns at least a few points."""
    out = {}
    for f in FACTORS:
        flags = [(r, is_strong(r, f, weights.get(f, 0))) for r in rows]
        with_f = stats([r for r, s in flags if s is True])
        without = stats([r for r, s in flags if s is False])
        edge = None
        if with_f["avg_excess_15"] is not None and without["avg_excess_15"] is not None:
            edge = round(with_f["avg_excess_15"] - without["avg_excess_15"], 5)
        out[f] = {"with": with_f, "without": without, "edge_excess_15": edge,
                  "enough_data": with_f["enough_data"] and without["enough_data"]}
    return out


def monthly(rows: list[dict]) -> list[dict]:
    """Picks per month and their average trade return (for a simple chart)."""
    by: dict[str, list] = {}
    for r in finished(rows):
        if r["status"] == "pick" and r.get("taken"):
            by.setdefault(r["signal_date"][:7], []).append(r)
    return [{"month": m, "n": len(v), "avg_trade_return": _avg(x["trade_return"] for x in v)}
            for m, v in sorted(by.items())]


def build(rows: list[dict], weights: dict) -> dict:
    """The full scorecard for one set of signals (backtest or live)."""
    done = finished(rows)
    dates = sorted(r["signal_date"] for r in done)
    mid = dates[len(dates) // 2] if dates else None
    return {
        "picks": stats([r for r in rows if r["status"] == "pick"]),
        "all_signals": stats(rows),
        "by_status": group(rows, lambda r: r["status"]),
        "by_score_bucket": group(rows, lambda r: bucket_of(r["score"])),
        "by_timing": group(rows, lambda r: r["timing"]),
        "by_role": group(rows, lambda r: r["role"]),
        "by_factor": factor_table(rows, weights),
        # same numbers for the older and newer half: big differences = luck or a changing market
        "by_period": group(rows, lambda r: "older half" if mid and r["signal_date"] < mid else "newer half"),
        "monthly_picks": monthly(rows),
        "open_signals": len([r for r in rows if r.get("exit_reason") == "open"]),
    }

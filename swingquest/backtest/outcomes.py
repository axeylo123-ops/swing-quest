"""What happened after a signal. Pure math, no downloads, fully tested.

Day numbering: the signal is judged after the close on the signal day.
We buy at the NEXT day's open; that is "day 1". The 15-day time stop
sells at the close of day 15.

Conservative rules (so the backtest doesn't flatter itself):
- if the stock opens above the entry zone, the trade is skipped (no chasing)
- if stop and target are both touched on the same day, assume the stop hit first
- if the price gaps through the stop overnight, we get the (worse) opening price
"""
import pandas as pd

HORIZONS = (5, 10, 15)


def simulate_trade(bars: pd.DataFrame, entry: float, stop: float, target: float,
                   max_days: int) -> dict:
    """Walks forward day by day from the entry day (bars.iloc[0])."""
    for k in range(min(max_days, len(bars))):
        bar = bars.iloc[k]
        if k > 0:  # overnight gaps (day 1 open IS our entry)
            if bar["open"] <= stop:
                return _exit(bars, k, bar["open"], "stop", entry, stop)
            if bar["open"] >= target:
                return _exit(bars, k, bar["open"], "target", entry, stop)
        if bar["low"] <= stop:
            return _exit(bars, k, stop, "stop", entry, stop)
        if bar["high"] >= target:
            return _exit(bars, k, target, "target", entry, stop)
    if len(bars) < max_days:
        return {"exit_reason": "open", "exit_date": None, "exit_price": None,
                "days_held": len(bars), "trade_return": None, "r_multiple": None}
    return _exit(bars, max_days - 1, bars.iloc[max_days - 1]["close"], "time", entry, stop)


def _exit(bars, k, price, reason, entry, stop):
    return {
        "exit_reason": reason,
        "exit_date": f"{bars.index[k]:%Y-%m-%d}",
        "exit_price": round(float(price), 4),
        "days_held": k + 1,
        "trade_return": round(float(price) / entry - 1, 5),
        "r_multiple": round((float(price) - entry) / (entry - stop), 3),
    }


def forward_returns(df: pd.DataFrame, spy: pd.DataFrame, entry_i: int) -> dict:
    """Stock and SPY returns from day-1 open to the close of day 5/10/15."""
    entry = float(df["open"].iloc[entry_i])
    entry_date = df.index[entry_i]
    spy_open = float(spy["open"].loc[entry_date]) if entry_date in spy.index else None
    out = {}
    for h in HORIZONS:
        j = entry_i + h - 1
        r = s = None
        if j < len(df):
            r = float(df["close"].iloc[j]) / entry - 1
            d = df.index[j]
            if spy_open and d in spy.index:
                s = float(spy["close"].loc[d]) / spy_open - 1
        out[f"ret_{h}"] = None if r is None else round(r, 5)
        out[f"spy_{h}"] = None if s is None else round(s, 5)
        out[f"excess_{h}"] = None if r is None or s is None else round(r - s, 5)
    return out


def measure(df: pd.DataFrame, spy: pd.DataFrame, signal_day: pd.Timestamp, atr: float,
            entry_high: float, trade_cfg: dict) -> dict:
    """Everything that happened after one signal."""
    i = df.index.get_loc(signal_day)
    entry_i = i + 1
    if entry_i >= len(df):
        return {"exit_reason": "open", "taken": False, "skip_reason": "no next-day price yet"}
    entry = float(df["open"].iloc[entry_i])
    stop = entry - trade_cfg["stop_atr_multiple"] * atr
    target = entry + trade_cfg["min_reward_risk"] * (entry - stop)
    result = {"entry_date": f"{df.index[entry_i]:%Y-%m-%d}", "entry": round(entry, 4),
              "stop": round(stop, 4), "target": round(target, 4)}
    result.update(forward_returns(df, spy, entry_i))
    if entry > entry_high:
        result.update({"taken": False, "skip_reason": "opened above the entry zone",
                       "exit_reason": "skipped"})
        return result
    if stop <= 0:
        result.update({"taken": False, "skip_reason": "stop below $0", "exit_reason": "skipped"})
        return result
    result["taken"] = True
    result.update(simulate_trade(df.iloc[entry_i:], entry, stop, target, trade_cfg["time_stop_days"]))
    return result


def measure_plan(df: pd.DataFrame, spy: pd.DataFrame, signal_day: pd.Timestamp, plan: dict) -> dict:
    """Grades a trade using the plan's own stop and target levels (chart-based
    plans), buying at the next open if it's inside the buy zone."""
    i = df.index.get_loc(signal_day)
    entry_i = i + 1
    if entry_i >= len(df):
        return {"exit_reason": "open", "taken": False, "skip_reason": "no next-day price yet"}
    entry = float(df["open"].iloc[entry_i])
    stop, target = plan["stop"], plan["target"]
    result = {"entry_date": f"{df.index[entry_i]:%Y-%m-%d}", "entry": round(entry, 4), "stop": stop, "target": target}
    result.update(forward_returns(df, spy, entry_i))
    if entry > plan["entry_high"]:
        result.update({"taken": False, "skip_reason": "opened above the buy zone", "exit_reason": "skipped"})
        return result
    if entry <= stop:
        result.update({"taken": False, "skip_reason": "opened below the stop", "exit_reason": "skipped"})
        return result
    result["taken"] = True
    result.update(simulate_trade(df.iloc[entry_i:], entry, stop, target, plan["time_stop_days"]))
    return result

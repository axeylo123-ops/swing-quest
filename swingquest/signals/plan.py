"""Timing label and trade plan.

Timing (from the chart, not part of the score):
  Ready    - price has turned up (above its 20-day average) and isn't overheated
  Wait     - still falling (below its 20-day average): let it turn first
  Extended - already ran up fast (RSI > 70 or far above the 20-day): don't chase

Trade plan:
  entry zone: from 0.25 ATR below to 0.5 ATR above the reference price
  stop:       reference - 2 x ATR
  target:     set so that even buying at the TOP of the entry zone gives
              reward >= 2 x risk
  time stop:  exit after 15 trading days if neither stop nor target is hit
"""


def timing(snap: dict) -> dict:
    close, sma20, sma50, rsi, atr = (snap[k] for k in ("close", "sma20", "sma50", "rsi", "atr"))
    notes = []
    if rsi > 70 or close > sma20 + 2 * atr:
        label = "Extended"
        notes.append("Price has run up fast; wait for a pullback instead of chasing")
    elif close < sma20:
        label = "Wait"
        notes.append("Still below its 20-day average; wait for the price to turn up")
    else:
        label = "Ready"
        notes.append("Price is back above its 20-day average")
    notes.append("Above its 50-day average (longer trend up)" if close > sma50
                 else "Below its 50-day average (longer trend still down)")
    notes.append(f"RSI {rsi:.0f}" + (" (overbought)" if rsi > 70 else " (oversold)" if rsi < 30 else ""))
    if snap["volume_ratio"] >= 1.5:
        notes.append(f"Volume {snap['volume_ratio']:.1f}x normal")
    return {"label": label, "notes": notes}


def trend_timing(snap: dict, above200: bool | None) -> dict:
    """Timing for the whole-market ranking (momentum aware):
    - uptrend (above the 200-day): Ready, including pullbacks to the 20/50-day,
      which are often the best entries; Extended only if it ran up too fast
    - downtrend: Ready only once it has turned back above the 20-day; else Wait
    """
    close, sma20, sma50, rsi, atr = (snap[k] for k in ("close", "sma20", "sma50", "rsi", "atr"))
    notes = []
    if rsi > 75 or close > sma20 + 2.5 * atr:
        label = "Extended"
        notes.append("Ran up fast: wait for a pullback instead of chasing")
    elif close < sma20 - 2 * atr:
        label = "Wait"
        notes.append("Sharp drop: more than 2 average daily moves below its 20-day average, let it settle")
    elif above200 or (above200 is None and close > sma50):
        label = "Ready"
        notes.append("Uptrend, pulling back toward its 20-day average: a typical entry" if close < sma20
                     else "Uptrend, above its 20-day average")
    elif close > sma20 and rsi >= 40:
        label = "Ready"
        notes.append("Below its 200-day average but turning up (back above its 20-day)")
    else:
        label = "Wait"
        notes.append("Downtrend: below its 200-day and 20-day averages, wait for it to turn up")
    notes.append(f"RSI {rsi:.0f}" + (" (overbought)" if rsi > 70 else " (oversold)" if rsi < 30 else ""))
    return {"label": label, "notes": notes}


def level_plan(prices, atr: float, min_rr: float = 2.0, time_stop_days: int = 15,
               max_stop_atr: float = 3.0, target_hint: float | None = None) -> dict | None:
    """A trade plan built on real chart levels, the way a trader would:
    - stop just under the nearest support that's at least 1 ATR below the price
      (10-day low, 20-day low or the 50-day average), never more than
      `max_stop_atr` ATRs away
    - target at the next resistance above (60-day or 52-week high, or an
      analyst target passed as `target_hint`), but always at least `min_rr`
      times the risk, even if you buy at the top of the zone
    """
    close = float(prices["close"].iloc[-1])
    if atr <= 0 or close <= 0:
        return None
    lows, highs = prices["low"], prices["high"]
    supports = {
        "the 10-day low": float(lows.tail(10).min()),
        "the 20-day low": float(lows.tail(20).min()),
        "the 50-day average": float(prices["close"].tail(50).mean()),
    }
    usable = {k: v for k, v in supports.items() if close - max_stop_atr * atr <= v <= close - atr}
    if usable:
        basis, level = max(usable.items(), key=lambda kv: kv[1])   # nearest solid support
        stop, stop_basis = level - 0.25 * atr, f"just under {basis}"
    else:
        stop, stop_basis = close - 2 * atr, "2 average daily moves below"
    if stop <= 0:
        return None
    entry_high = close + 0.5 * atr
    floor_target = entry_high + min_rr * (entry_high - stop)
    resist = {"the 60-day high": float(highs.tail(60).max()), "the 52-week high": float(highs.tail(252).max())}
    if target_hint:
        resist["the analyst average target"] = float(target_hint)
    above = {k: v for k, v in resist.items() if v >= floor_target}
    if above:
        tb, target = min(above.items(), key=lambda kv: kv[1])          # first level that still pays 2:1
        target_basis = f"at {tb}"
    else:
        target, target_basis = floor_target, f"{min_rr:.0f}x the risk"
    risk = close - stop
    return {
        "reference": round(close, 2), "entry_low": round(close - 0.25 * atr, 2), "entry_high": round(entry_high, 2),
        "stop": round(stop, 2), "target": round(target, 2), "risk_pct": round(risk / close, 4),
        "reward_risk": round((target - close) / risk, 2),
        "reward_risk_worst": round((target - entry_high) / (entry_high - stop), 2),
        "time_stop_days": time_stop_days, "stop_basis": stop_basis, "target_basis": target_basis,
    }


def trade_plan(reference: float, atr: float, trade_cfg: dict) -> dict | None:
    stop = reference - trade_cfg["stop_atr_multiple"] * atr
    if stop <= 0 or atr <= 0:
        return None
    entry_high = reference + 0.5 * atr
    target = entry_high + trade_cfg["min_reward_risk"] * (entry_high - stop)
    risk = reference - stop
    return {
        "reference": round(reference, 2),
        "entry_low": round(reference - 0.25 * atr, 2),
        "entry_high": round(entry_high, 2),
        "stop": round(stop, 2),
        "target": round(target, 2),
        "risk_pct": round(risk / reference, 4),
        "reward_risk": round((target - reference) / risk, 2),           # buying at reference
        "reward_risk_worst": round((target - entry_high) / (entry_high - stop), 2),  # top of zone
        "time_stop_days": trade_cfg["time_stop_days"],
    }

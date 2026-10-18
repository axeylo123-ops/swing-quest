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

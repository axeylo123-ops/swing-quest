"""Chart indicators, used for timing only (not for the score).

- SMA: simple moving average, the average close of the last N days.
- RSI: 0-100 "momentum" gauge. Above 70 = overbought, below 30 = oversold.
- ATR: Average True Range, how much the stock typically moves in a day.
  We size stops with it so a volatile stock gets a wider stop.
"""
import pandas as pd


def sma(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI (the standard version charting sites show)."""
    change = close.diff()
    gain = change.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0).where(gain.notna())


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    true_range = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def snapshot(df: pd.DataFrame, atr_period: int = 14) -> dict | None:
    """All indicator values on the last bar of `df`. None if too little history."""
    if len(df) < 60:
        return None
    close = df["close"]
    year = df.tail(252)
    last = df.iloc[-1]
    avg_volume = float(df["volume"].tail(21).iloc[:-1].mean())
    low52, high52 = float(year["low"].min()), float(year["high"].max())
    return {
        "close": float(last["close"]),
        "sma20": float(sma(close, 20).iloc[-1]),
        "sma50": float(sma(close, 50).iloc[-1]),
        "rsi": float(rsi(close).iloc[-1]),
        "atr": float(atr(df, atr_period).iloc[-1]),
        "volume_ratio": float(last["volume"]) / avg_volume if avg_volume > 0 else 0.0,
        "low52": low52,
        "high52": high52,
        # 0 = at the 52-week low, 1 = at the 52-week high
        "range_position": (float(last["close"]) - low52) / (high52 - low52) if high52 > low52 else 0.5,
    }

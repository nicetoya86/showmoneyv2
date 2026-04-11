from __future__ import annotations

import numpy as np
import pandas as pd


def sma(arr: np.ndarray, window: int) -> np.ndarray:
    if window <= 0:
        raise ValueError("window must be > 0")
    s = pd.Series(arr, dtype="float64")
    return s.rolling(window).mean().to_numpy(dtype="float64")


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int = 14) -> np.ndarray:
    """
    Average True Range (ATR) using Wilder-style true range, simple rolling mean for simplicity.
    Returns array aligned to input length (leading values may be NaN).
    """
    if not (len(high) == len(low) == len(close)):
        raise ValueError("high/low/close lengths must match")
    h = pd.Series(high, dtype="float64")
    l = pd.Series(low, dtype="float64")
    c = pd.Series(close, dtype="float64")
    prev_close = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev_close).abs(), (l - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(window).mean().to_numpy(dtype="float64")


def max_drawdown(equity: np.ndarray) -> float:
    """
    Max drawdown for an equity curve array.
    """
    eq = np.asarray(equity, dtype="float64")
    if eq.size == 0:
        return 0.0
    peaks = np.maximum.accumulate(eq)
    dd = (eq - peaks) / np.where(peaks == 0, np.nan, peaks)
    return float(np.nanmin(dd))


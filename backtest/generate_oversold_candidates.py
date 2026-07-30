"""
Phase B of sub-project 3 (swing-algo enhancement): a new candidate-generation pattern,
parallel to evaluate_candidate()'s A/B/C/D patterns, admitting oversold-recovery setups that
evaluate_candidate() structurally excludes via its `rsi14 < 40` hard filter
(backtest/swing_signal_engine.py:117). See
docs/superpowers/specs/2026-07-30-swing-algo-oversold-bounce-design.md for the full design.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import rsi14 as calc_rsi14
from .indicators import sma


def _is_oversold_bounce(df: pd.DataFrame, idx: int) -> bool:
    """All five conditions from the design doc's "Entry Rule" section, AND'd together."""
    close = df["close"].to_numpy(dtype="float64")
    high = df["high"].to_numpy(dtype="float64")

    if idx < 70 or idx >= len(close):
        return False

    rsi_now = calc_rsi14(close, idx)
    rsi_prev = calc_rsi14(close, idx - 1)
    if not (np.isfinite(rsi_now) and np.isfinite(rsi_prev)):
        return False
    if not (rsi_now >= 40 and rsi_prev < 40):
        return False

    recent_rsi = [calc_rsi14(close, i) for i in range(idx - 5, idx)]
    if not all(np.isfinite(r) for r in recent_rsi):
        return False
    if min(recent_rsi) > 35:
        return False

    sma60 = sma(close, 60)
    if not np.isfinite(sma60[idx]) or close[idx] <= sma60[idx]:
        return False

    high20 = float(np.max(high[idx - 20: idx + 1]))
    if high20 <= 0 or (close[idx] / high20 - 1.0) > -0.08:
        return False

    if close[idx] <= high[idx - 1]:
        return False

    return True

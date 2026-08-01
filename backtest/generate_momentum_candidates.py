"""
Sub-project 5: a new candidate-generation pattern, "F모멘텀" (momentum-continuation), parallel
to evaluate_candidate()'s A/B/C/D patterns and Phase B's E반등. Bets on continuation of an
already-established uptrend (relative-strength leadership + new high + trend alignment) rather
than reversal off oversold conditions. See
docs/superpowers/specs/2026-08-01-swing-algo-momentum-continuation-design.md for the full design.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .indicators import sma

HOLD_DAYS = 10
RS_LOOKBACK = 60
RS_TOP_FRAC = 0.10
NEW_HIGH_LOOKBACK = 60


def compute_trailing_return(df: pd.DataFrame, idx: int, lookback: int = RS_LOOKBACK) -> float:
    """close[idx]/close[idx-lookback] - 1. NaN if idx < lookback or the base price isn't
    positive/finite."""
    close = df["close"].to_numpy(dtype="float64")
    if idx < lookback:
        return float("nan")
    base = close[idx - lookback]
    if not np.isfinite(base) or base <= 0:
        return float("nan")
    return float(close[idx] / base - 1.0)


def build_universe_return_lookup(
    per_ticker_ohlcv: Dict[str, pd.DataFrame],
    *,
    lookback: int = RS_LOOKBACK,
    top_frac: float = RS_TOP_FRAC,
) -> Dict[str, float]:
    """date (ISO string) -> the value at the (1 - top_frac) quantile of that day's
    cross-sectional distribution of trailing-lookback-day returns across every ticker with a
    valid return that date. A date with zero contributing tickers is simply absent from the
    result -- _is_momentum_continuation fails closed when a date's threshold is missing."""
    by_date: Dict[str, List[float]] = {}
    for df in per_ticker_ohlcv.values():
        for i, day in enumerate(df["timestamp_utc"]):
            r = compute_trailing_return(df, i, lookback=lookback)
            if not np.isfinite(r):
                continue
            date_key = pd.Timestamp(day).date().isoformat()
            by_date.setdefault(date_key, []).append(r)

    return {
        date_key: float(np.quantile(returns, 1.0 - top_frac))
        for date_key, returns in by_date.items()
    }


def _is_momentum_continuation(df: pd.DataFrame, idx: int, *, rs_threshold: Optional[float]) -> bool:
    """All three momentum-continuation conditions from the design doc's "Entry Rule" section,
    AND'd together. rs_threshold is that day's cutoff from build_universe_return_lookup (or
    None if the date had no universe sample -- fails closed)."""
    if rs_threshold is None:
        return False
    if idx < NEW_HIGH_LOOKBACK:
        return False

    close = df["close"].to_numpy(dtype="float64")
    high = df["high"].to_numpy(dtype="float64")

    own_return = compute_trailing_return(df, idx, lookback=RS_LOOKBACK)
    if not np.isfinite(own_return) or own_return < rs_threshold:
        return False

    high60 = float(np.max(high[idx - NEW_HIGH_LOOKBACK: idx]))
    if close[idx] < high60:
        return False

    sma50 = sma(close, 50)
    sma200 = sma(close, 200)
    if not (np.isfinite(sma50[idx]) and np.isfinite(sma200[idx])):
        return False
    if not (close[idx] > sma50[idx] > sma200[idx]):
        return False

    return True

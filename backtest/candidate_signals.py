"""
Sub-project 3 Phase A: three additive signal "tags" computed per (ticker, date) from data
already available as of the close of the candidate's signal day (idx) -- no use of entry_idx
(idx+1) or later, no lookahead. See
docs/superpowers/specs/2026-07-28-swing-algo-new-signal-filters-design.md for the full design,
including the trader-review corrections these formulas already reflect (weekly-SMA trend metric,
pre-event volatility window, minimum-sample sector gate).
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .indicators import atr as calc_atr
from .run_swing_v2_backtest import _iso_week_key


def compute_trend_alignment(df: pd.DataFrame, idx: int, *, weeks: int = 10) -> bool:
    """True if the last fully-completed ISO week's close is above the weeks-week weekly SMA.
    The week containing idx itself is always excluded, even if idx is that week's last bar --
    a deliberately conservative no-lookahead rule."""
    history = df.iloc[: idx + 1]
    if history.empty:
        return False

    iso_weeks = history["timestamp_utc"].apply(lambda d: _iso_week_key(pd.Timestamp(d)))
    current_week = iso_weeks.iloc[-1]
    completed_mask = iso_weeks != current_week
    if not completed_mask.any():
        return False

    completed = history.loc[completed_mask].copy()
    completed["_iso_week"] = iso_weeks[completed_mask]
    weekly_closes = completed.groupby("_iso_week")["close"].last()
    if len(weekly_closes) < weeks:
        return False

    last_close = float(weekly_closes.iloc[-1])
    sma_val = float(weekly_closes.iloc[-weeks:].mean())
    return last_close > sma_val


def compute_vol_contraction(
    df: pd.DataFrame,
    idx: int,
    *,
    lookback: int = 60,
    exclude_recent: int = 10,
    percentile: float = 0.2,
) -> bool:
    """True if ATR/price at idx-exclude_recent (the most recent point in the pre-event window)
    is at or below the percentile-th percentile of that ratio over idx-lookback..idx-exclude_recent.
    The most recent exclude_recent bars are deliberately excluded: the existing A/C/D candidate
    patterns require a volume/price expansion to have already fired as of idx, so including those
    bars would contradict the very definition of the candidates this is applied to."""
    window_start = idx - lookback
    window_end = idx - exclude_recent
    if window_start < 0 or window_end < window_start:
        return False

    history = df.iloc[: idx + 1]
    high = history["high"].to_numpy(dtype="float64")
    low = history["low"].to_numpy(dtype="float64")
    close = history["close"].to_numpy(dtype="float64")
    atr_vals = calc_atr(high, low, close, 14)
    ratio = atr_vals / close

    window = ratio[window_start: window_end + 1]
    window = window[~np.isnan(window)]
    if len(window) < 20:
        return False

    current = ratio[window_end]
    if np.isnan(current):
        return False

    threshold = float(np.quantile(window, percentile))
    return bool(current <= threshold)

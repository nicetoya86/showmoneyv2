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

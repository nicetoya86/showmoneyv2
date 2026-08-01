"""
Sub-project 4 (Phase C) Stage 2: additive signal tags computed on the Stage-1 v3
(2-day-confirmed) oversold-bounce ("E반등") candidate pool -- items 1 (volume confirm), 2
(sector strength, reused unmodified from candidate_signals.py) and 4 (support confluence)
from the trader review. Also builds the per-candidate ATR-pct lookup Stage 3's
atr_stop_grid_search.py consumes. All computations use data available as of the candidate's
trigger day (idx) -- no lookahead. See
docs/superpowers/specs/2026-08-01-swing-algo-oversold-bounce-hitrate-design.md.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .candidate_signals import build_sector_returns_by_date, compute_sector_strength
from .generate_signal_candidates import CachedCandidate
from .indicators import atr as calc_atr

VOLUME_CONFIRM_RVOL_MIN = 1.5
SUPPORT_PIVOT_WINDOW = 3
SUPPORT_LOOKBACK = 40
SUPPORT_TOLERANCE = 0.03


def compute_volume_confirm(df: pd.DataFrame, idx: int) -> bool:
    """Item 1: trigger-day rvol >= 1.5, using the same rvol formula as
    swing_signal_engine.py's evaluate_candidate() (trailing 20-day average volume,
    excluding idx itself)."""
    vol = df["volume"].to_numpy(dtype="float64")
    vol_window = vol[max(0, idx - 20): idx]
    vol20_avg = float(vol_window.sum() / max(1, min(20, idx))) if len(vol_window) else 0.0
    if vol20_avg <= 0:
        return False
    rvol = vol[idx] / vol20_avg
    return bool(rvol >= VOLUME_CONFIRM_RVOL_MIN)


def compute_support_confluence(df: pd.DataFrame, idx: int) -> bool:
    """Item 4: True if idx's close is within SUPPORT_TOLERANCE of any pivot low (a close
    strictly lower than SUPPORT_PIVOT_WINDOW bars on both sides) found in the trailing
    SUPPORT_LOOKBACK bars. Distinct from swing_signal_engine.py's B-pattern support concept
    (proximity to a trailing AVERAGE price) -- this looks for an actual local low."""
    close = df["close"].to_numpy(dtype="float64")
    start = max(0, idx - SUPPORT_LOOKBACK)
    end = idx - SUPPORT_PIVOT_WINDOW
    if end < start + SUPPORT_PIVOT_WINDOW:
        return False
    current = close[idx]
    for p in range(start + SUPPORT_PIVOT_WINDOW, end + 1):
        left = close[p - SUPPORT_PIVOT_WINDOW: p]
        right = close[p + 1: p + 1 + SUPPORT_PIVOT_WINDOW]
        if len(left) < SUPPORT_PIVOT_WINDOW or len(right) < SUPPORT_PIVOT_WINDOW:
            continue
        if bool(close[p] < left.min() and close[p] < right.min()):
            if abs(current / close[p] - 1.0) <= SUPPORT_TOLERANCE:
                return True
    return False


def compute_atr_pct(df: pd.DataFrame, idx: int) -> float:
    """ATR14 / close at idx, for Stage 3's ATR-based target/stop -- no lookahead, uses only
    history up to and including idx (same convention as candidate_signals.py's
    compute_vol_contraction)."""
    history = df.iloc[: idx + 1]
    high = history["high"].to_numpy(dtype="float64")
    low = history["low"].to_numpy(dtype="float64")
    close = history["close"].to_numpy(dtype="float64")
    atr_vals = calc_atr(high, low, close, 14)
    atr_val = atr_vals[idx]
    if not np.isfinite(atr_val) or close[idx] <= 0:
        return float("nan")
    return float(atr_val / close[idx])


def tag_candidates_oversold(
    candidates: List[CachedCandidate],
    per_ticker_ohlcv: Dict[str, pd.DataFrame],
    sector_map: Dict[str, str],
) -> Dict[Tuple[str, str], Dict[str, bool]]:
    """(ticker, date) -> {volume_confirm, sector_strong, support_confluence}. Fails closed
    (all False) for a candidate whose ticker/date can't be located in per_ticker_ohlcv,
    matching tag_candidates()'s convention in candidate_signals.py."""
    sector_returns_by_date = build_sector_returns_by_date(sector_map, per_ticker_ohlcv)
    closed = {"volume_confirm": False, "sector_strong": False, "support_confluence": False}

    tags: Dict[Tuple[str, str], Dict[str, bool]] = {}
    for c in candidates:
        df = per_ticker_ohlcv.get(c.ticker)
        if df is None:
            tags[(c.ticker, c.date)] = dict(closed)
            continue
        idxs = df.index[df["timestamp_utc"] == pd.Timestamp(c.date)].tolist()
        if not idxs:
            tags[(c.ticker, c.date)] = dict(closed)
            continue
        idx = int(idxs[0])
        date_key = pd.Timestamp(c.date).date().isoformat()
        tags[(c.ticker, c.date)] = {
            "volume_confirm": compute_volume_confirm(df, idx),
            "sector_strong": compute_sector_strength(sector_returns_by_date, sector_map, c.code, date_key),
            "support_confluence": compute_support_confluence(df, idx),
        }
    return tags


def build_atr_pct_lookup(
    candidates: List[CachedCandidate],
    per_ticker_ohlcv: Dict[str, pd.DataFrame],
) -> Dict[Tuple[str, str], float]:
    """(ticker, date) -> atr_pct, for Stage 3's atr_stop_grid_search.py. Omits a candidate
    (rather than storing NaN) if its ticker/date can't be located or its atr_pct is not
    finite -- atr_stop_grid_search.py treats a missing key as "skip this candidate"."""
    lookup: Dict[Tuple[str, str], float] = {}
    for c in candidates:
        df = per_ticker_ohlcv.get(c.ticker)
        if df is None:
            continue
        idxs = df.index[df["timestamp_utc"] == pd.Timestamp(c.date)].tolist()
        if not idxs:
            continue
        idx = int(idxs[0])
        atr_pct = compute_atr_pct(df, idx)
        if np.isfinite(atr_pct):
            lookup[(c.ticker, c.date)] = atr_pct
    return lookup

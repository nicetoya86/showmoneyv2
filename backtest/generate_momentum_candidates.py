"""
Sub-project 5: a new candidate-generation pattern, "F모멘텀" (momentum-continuation), parallel
to evaluate_candidate()'s A/B/C/D patterns and Phase B's E반등. Bets on continuation of an
already-established uptrend (relative-strength leadership + new high + trend alignment) rather
than reversal off oversold conditions. See
docs/superpowers/specs/2026-08-01-swing-algo-momentum-continuation-design.md for the full design.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

from .dart_history import fetch_disclosures_for_date
from .generate_signal_candidates import CachedCandidate, _code_of
from .indicators import sma
from .krx_supply_history import fetch_supply_for_date
from .swing_signal_engine import MIN_PRICE, MIN_TURNOVER_ALGO, NEGATIVE_DART_RE
from .yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart

DART_API_KEY = "34a9b090d2a7b1ee689a240fef68667d36b389e7"  # matches production (already public in this repo)

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


def _passes_base_filters(
    df: pd.DataFrame, idx: int, *, supply: Dict[str, float], dart_items: List[str]
) -> bool:
    """Liquidity/quality gates matching evaluate_candidate()'s base filters
    (backtest/swing_signal_engine.py lines 112-121) in content -- a fresh local
    implementation, not an import, since generate_oversold_candidates.py's own copy of this
    logic is module-private (leading underscore) and not meant to be imported cross-module,
    per this line's established convention (see atr_stop_grid_search.py's _window_df for the
    same reasoning)."""
    close = df["close"].to_numpy(dtype="float64")
    vol = df["volume"].to_numpy(dtype="float64")
    current_price = float(close[idx])
    if current_price < MIN_PRICE:
        return False
    turnover = current_price * (vol[idx] if np.isfinite(vol[idx]) else 0.0)
    if turnover < MIN_TURNOVER_ALGO:
        return False
    if dart_items and re.search(NEGATIVE_DART_RE, " ".join(dart_items)):
        return False
    if supply.get("frgn", 0) < -1_000_000_000 or supply.get("org", 0) < -1_000_000_000:
        return False
    vol_window = vol[max(0, idx - 20): idx]
    vol20_avg = float(vol_window.sum() / max(1, min(20, idx))) if len(vol_window) else 0.0
    rvol = (vol[idx] / vol20_avg) if vol20_avg > 0 else 0.0
    if rvol < 1.0:
        return False
    return True


def scan_momentum_candidates(
    tickers: List[str],
    *,
    start: str,
    end: str,
    dart_api_key: str = DART_API_KEY,
) -> Tuple[List[CachedCandidate], List[Dict[str, str]]]:
    per_ticker: Dict[str, pd.DataFrame] = {}
    skipped_tickers: List[Dict[str, str]] = []
    for t in tickers:
        try:
            data = fetch_yahoo_chart(YahooFetchSpec(ticker=t, range="5y", interval="1d"))
            df, _ = chart_to_ohlcv_daily(data)
            df = df.sort_values("timestamp_utc").reset_index(drop=True)
            per_ticker[t] = df
        except (requests.exceptions.RequestException, ValueError) as e:
            print(f"WARNING: skipping ticker {t} - fetch failed: {e}")
            skipped_tickers.append({"ticker": t, "error": str(e)})
            continue

    rs_lookup = build_universe_return_lookup(per_ticker)

    start_ts = pd.to_datetime(start, utc=True)
    end_ts = pd.to_datetime(end, utc=True)
    all_days = sorted({d for df in per_ticker.values() for d in df["timestamp_utc"].tolist()})
    all_days = [d for d in all_days if start_ts <= d <= end_ts]

    candidates: List[CachedCandidate] = []
    for day in all_days:
        trd_dd = day.strftime("%Y%m%d")
        date_key = pd.Timestamp(day).date().isoformat()
        rs_threshold = rs_lookup.get(date_key)
        supply_map = fetch_supply_for_date(trd_dd)
        dart_map = fetch_disclosures_for_date(trd_dd, api_key=dart_api_key)

        for t, df in per_ticker.items():
            idxs = df.index[df["timestamp_utc"] == day].tolist()
            if not idxs:
                continue
            idx = int(idxs[0])
            entry_idx = idx + 1
            if entry_idx >= len(df):
                continue
            code = _code_of(t)
            if not _passes_base_filters(
                df, idx, supply=supply_map.get(code, {}), dart_items=dart_map.get(code, [])
            ):
                continue
            if not _is_momentum_continuation(df, idx, rs_threshold=rs_threshold):
                continue
            window = df.iloc[entry_idx: entry_idx + HOLD_DAYS]
            candidates.append(CachedCandidate(
                ticker=t, code=code, date=day.isoformat(),
                entry=float(df["close"].to_numpy(dtype="float64")[idx]),
                pattern_type="F모멘텀", score=110, rank_score=110, grade="매수", hold_days=HOLD_DAYS,
                window_open=window["open"].astype(float).tolist(),
                window_high=window["high"].astype(float).tolist(),
                window_low=window["low"].astype(float).tolist(),
                window_close=window["close"].astype(float).tolist(),
            ))
    return candidates, skipped_tickers


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--end", default="2026-01-01")
    ap.add_argument("--out", default="backtest_momentum_candidates.json")
    args = ap.parse_args()

    tickers = [
        x.strip() for x in Path(args.tickers).read_text(encoding="utf-8").splitlines()
        if x.strip() and not x.startswith("#")
    ]
    candidates, skipped = scan_momentum_candidates(tickers, start=args.start, end=args.end)

    out = {
        "params": {"start": args.start, "end": args.end, "tickers": len(tickers)},
        "skipped_tickers": skipped,
        "candidates": [asdict(c) for c in candidates],
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out}: {len(candidates)} candidates, {len(skipped)} skipped tickers")


if __name__ == "__main__":
    main()

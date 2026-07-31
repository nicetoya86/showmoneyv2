"""
Phase B of sub-project 3 (swing-algo enhancement): a new candidate-generation pattern,
parallel to evaluate_candidate()'s A/B/C/D patterns, admitting oversold-recovery setups that
evaluate_candidate() structurally excludes via its `rsi14 < 40` hard filter
(backtest/swing_signal_engine.py:117). See
docs/superpowers/specs/2026-07-30-swing-algo-oversold-bounce-design.md for the full design.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import requests

from .dart_history import fetch_disclosures_for_date
from .generate_signal_candidates import CachedCandidate, _code_of
from .indicators import rsi14 as calc_rsi14
from .indicators import sma
from .krx_supply_history import fetch_supply_for_date
from .swing_signal_engine import MIN_PRICE, MIN_TURNOVER_ALGO, NEGATIVE_DART_RE
from .yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart

DART_API_KEY = "34a9b090d2a7b1ee689a240fef68667d36b389e7"  # matches production (already public in this repo)
HOLD_DAYS = 5


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


def _passes_base_filters(
    df: pd.DataFrame, idx: int, *, supply: Dict[str, float], dart_items: List[str]
) -> bool:
    """Liquidity/quality gates reused unmodified from evaluate_candidate()'s base filters
    (backtest/swing_signal_engine.py lines 112-121) — not directionally specific, so kept as-is
    rather than redefined, per the design doc."""
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
    return True


def scan_oversold_candidates(
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

    start_ts = pd.to_datetime(start, utc=True)
    end_ts = pd.to_datetime(end, utc=True)
    all_days = sorted({d for df in per_ticker.values() for d in df["timestamp_utc"].tolist()})
    all_days = [d for d in all_days if start_ts <= d <= end_ts]

    candidates: List[CachedCandidate] = []
    for day in all_days:
        trd_dd = day.strftime("%Y%m%d")
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
            if not _is_oversold_bounce(df, idx):
                continue
            window = df.iloc[entry_idx: entry_idx + HOLD_DAYS]
            candidates.append(CachedCandidate(
                ticker=t, code=code, date=day.isoformat(),
                entry=float(df["close"].to_numpy(dtype="float64")[idx]),
                pattern_type="E반등", score=110, rank_score=110, grade="매수", hold_days=HOLD_DAYS,
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
    ap.add_argument("--out", default="backtest_oversold_candidates.json")
    args = ap.parse_args()

    tickers = [
        x.strip() for x in Path(args.tickers).read_text(encoding="utf-8").splitlines()
        if x.strip() and not x.startswith("#")
    ]
    candidates, skipped = scan_oversold_candidates(tickers, start=args.start, end=args.end)

    out = {
        "params": {"start": args.start, "end": args.end, "tickers": len(tickers)},
        "skipped_tickers": skipped,
        "candidates": [asdict(c) for c in candidates],
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out}: {len(candidates)} candidates, {len(skipped)} skipped tickers")


if __name__ == "__main__":
    main()

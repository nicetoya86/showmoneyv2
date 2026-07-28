"""
Phase 1 of the target/stop retuning sub-project: re-runs the existing, unmodified
evaluate_candidate() over the full ticker universe and caches every qualifying candidate
together with its forward OHLC price path, so Phase 2 (backtest/target_stop_grid_search.py)
can evaluate arbitrary target/stop/threshold combinations without re-fetching data or
re-running candidate generation.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
import requests

from .dart_history import fetch_disclosures_for_date
from .krx_supply_history import fetch_supply_for_date
from .swing_signal_engine import evaluate_candidate
from .yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart

DART_API_KEY = "34a9b090d2a7b1ee689a240fef68667d36b389e7"  # matches production (already public in this repo)
MAX_WINDOW_DAYS = 5  # max(_hold_days(...)) across all grade/pattern combinations (swing_signal_engine.py)


def _code_of(ticker: str) -> str:
    return ticker[:-3] if ticker.endswith(".KS") or ticker.endswith(".KQ") else ticker


@dataclass
class CachedCandidate:
    ticker: str
    code: str
    date: str
    entry: float
    pattern_type: str
    score: int
    rank_score: int
    grade: str
    hold_days: int
    window_open: List[float]
    window_high: List[float]
    window_low: List[float]
    window_close: List[float]


def generate_candidates(
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
            cand = evaluate_candidate(
                df, idx,
                supply=supply_map.get(code, {}),
                dart_items=dart_map.get(code, []),
                day_of_week=int(day.isoweekday() % 7),
            )
            if cand is None:
                continue
            window = df.iloc[entry_idx: entry_idx + MAX_WINDOW_DAYS]
            candidates.append(CachedCandidate(
                ticker=t, code=code, date=day.isoformat(), entry=cand.entry,
                pattern_type=cand.pattern_type, score=cand.score, rank_score=cand.rank_score,
                grade=cand.grade, hold_days=cand.hold_days,
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
    ap.add_argument("--out", default="backtest_candidates_with_paths.json")
    args = ap.parse_args()

    tickers = [
        x.strip() for x in Path(args.tickers).read_text(encoding="utf-8").splitlines()
        if x.strip() and not x.startswith("#")
    ]
    candidates, skipped = generate_candidates(tickers, start=args.start, end=args.end)

    out = {
        "params": {"start": args.start, "end": args.end, "tickers": len(tickers)},
        "skipped_tickers": skipped,
        "candidates": [asdict(c) for c in candidates],
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out}: {len(candidates)} candidates, {len(skipped)} skipped tickers")


if __name__ == "__main__":
    main()

# swing-algo-momentum-continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the "F모멘텀" (momentum-continuation) candidate-generation engine per the design
doc — a new pattern betting on continuation of an established uptrend (relative-strength
leadership + new high + trend alignment) — and backtest it through the existing, unmodified grid
search with the same rigor as every prior sub-project in this line.

**Architecture:** New module `backtest/generate_momentum_candidates.py`. Task 1 builds the three
pure signal functions (including the first cross-sectional, universe-wide computation in this
line). Task 2 builds the scan/orchestration layer and CLI, mirroring
`backtest/generate_oversold_candidates.py`'s structure. Tasks 3-4 are execution-only (run the scan,
run the grid search). Task 5 writes the honest results analysis.

**Tech Stack:** Python, pandas/numpy, pytest. No new dependencies.

## Global Constraints

- `backtest/target_stop_grid_search.py` is **not modified** — reused exactly as every prior
  sub-project has used it.
- Decision-gate bar: `hit_rate >= 0.90` (`MIN_HIT_RATE`) AND `trades_per_week >= 5.0`
  (`MIN_TRADES_PER_WEEK`) AND `cagr_15slot > 0`, on **both** train (`2022-01-01`..`2024-06-30`) and
  test (`2024-07-01`..`2026-01-01`) splits. `n_trades >= 50` reliability gate on both splits before
  any pass/fail conclusion (three-way outcome: target-met / target-not-met-but-reliable /
  underpowered) — report honestly, never soften.
- `HOLD_DAYS = 10`, `RS_LOOKBACK = 60`, `RS_TOP_FRAC = 0.10`, `NEW_HIGH_LOOKBACK = 60`, SMA
  alignment periods `50`/`200` — all fixed per the design doc, not swept.
- Single-day trigger: `entry = close[idx]`, `entry_idx = idx + 1` (no multi-day confirmation, no
  shift — unlike E반등's later 2-day-confirmed variant).
- New-high condition excludes the trigger day itself: `close[idx] >= max(high[idx-60..idx-1])`,
  never `high[idx-60..idx]` (which would include today's own high and make the condition nearly
  unsatisfiable, since `high[idx] >= close[idx]` always in real OHLC data).
- Reused data files (already committed, do not re-fetch): `backtest/tickers_operating.txt` (959
  tickers), `backtest_regime_lookup.json` (required by `run_grid_search`'s `regime_lookup` param,
  even though this plan doesn't sweep `regime_gate` specifically — the parameter is mandatory).
- No lookahead: every computation at trigger day `idx` uses data through and including `idx` only.

---

### Task 1: Signal functions — relative strength, new high, trend alignment

**Files:**
- Create: `backtest/generate_momentum_candidates.py`
- Test: `backtest/tests/test_generate_momentum_candidates.py`

**Interfaces:**
- Consumes: `backtest.indicators.sma` (existing, unmodified).
- Produces: `compute_trailing_return(df, idx, lookback=60) -> float`,
  `build_universe_return_lookup(per_ticker_ohlcv, *, lookback=60, top_frac=0.10) -> Dict[str, float]`
  (date ISO string -> RS cutoff), `_is_momentum_continuation(df, idx, *, rs_threshold) -> bool` —
  Task 2 consumes all three plus adds `_passes_base_filters`/`scan_momentum_candidates` to the same
  file.

- [ ] **Step 1: Write the failing tests**

Create `backtest/tests/test_generate_momentum_candidates.py`:

```python
import numpy as np
import pandas as pd

from backtest import generate_momentum_candidates as mod


def test_compute_trailing_return_value_pinned():
    n = 65
    close = np.full(n, 100.0)
    close[64] = 130.0
    df = pd.DataFrame({"close": close})
    result = mod.compute_trailing_return(df, 64, lookback=60)
    assert abs(result - 0.3) < 1e-9


def test_compute_trailing_return_nan_when_idx_below_lookback():
    n = 60
    df = pd.DataFrame({"close": np.full(n, 100.0)})
    assert np.isnan(mod.compute_trailing_return(df, 59, lookback=60))


def _flat_with_final_bump(n, flat_level, final_close, dates):
    close = np.full(n, flat_level)
    close[-1] = final_close
    return pd.DataFrame({"timestamp_utc": dates, "close": close})


def test_build_universe_return_lookup_value_pinned():
    n = 65
    dates = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    returns = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10]
    per_ticker = {
        f"T{i}.KS": _flat_with_final_bump(n, 100.0, 100.0 * (1 + r), dates)
        for i, r in enumerate(returns)
    }

    lookup = mod.build_universe_return_lookup(per_ticker, lookback=60, top_frac=0.10)

    last_date_key = dates[-1].date().isoformat()
    assert abs(lookup[last_date_key] - 0.091) < 1e-9
    # every ticker is flat (return 0.0) on days 60-63 -- a separate, correctly-zero cutoff
    mid_date_key = dates[60].date().isoformat()
    assert abs(lookup[mid_date_key] - 0.0) < 1e-9


def test_build_universe_return_lookup_excludes_dates_with_no_valid_return():
    n = 65
    dates = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    per_ticker = {"T0.KS": _flat_with_final_bump(n, 100.0, 105.0, dates)}
    lookup = mod.build_universe_return_lookup(per_ticker, lookback=60, top_frac=0.10)
    day59_key = dates[59].date().isoformat()
    assert day59_key not in lookup  # idx=59 < lookback=60 everywhere -- no valid return that day


def _build_momentum_df(n, closes, highs=None):
    closes = np.asarray(closes, dtype="float64")
    highs = np.asarray(highs, dtype="float64") if highs is not None else closes * 1.001
    return pd.DataFrame({
        "timestamp_utc": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
        "open": closes, "high": highs, "low": closes * 0.999, "close": closes,
        "volume": np.full(n, 2_000_000_000.0),
    })


def test_is_momentum_continuation_true_when_all_conditions_hold():
    n = 210
    close = np.linspace(100, 400, n)
    df = _build_momentum_df(n, close)
    idx = n - 1
    assert mod._is_momentum_continuation(df, idx, rs_threshold=0.05) is True


def test_is_momentum_continuation_false_when_rs_threshold_none():
    n = 210
    close = np.linspace(100, 400, n)
    df = _build_momentum_df(n, close)
    assert mod._is_momentum_continuation(df, n - 1, rs_threshold=None) is False


def test_is_momentum_continuation_false_when_return_below_threshold():
    n = 210
    close = np.linspace(100, 400, n)
    df = _build_momentum_df(n, close)
    # own trailing-60d return here is ~0.274 -- an impossibly high threshold forces a miss
    assert mod._is_momentum_continuation(df, n - 1, rs_threshold=999.0) is False


def test_is_momentum_continuation_false_when_not_at_new_high():
    n = 210
    close = np.linspace(100, 400, n)
    high = close * 1.001
    idx = n - 1
    # a spike 5 bars before idx that exceeds the final close -- the prior-60-day high wins
    close = close.copy()
    high = high.copy()
    close[idx - 5] = close[idx] * 1.05
    high[idx - 5] = close[idx - 5] * 1.001
    df = _build_momentum_df(n, close, highs=high)
    assert mod._is_momentum_continuation(df, idx, rs_threshold=0.05) is False


def test_is_momentum_continuation_false_when_trend_not_aligned():
    # long steep decline (drags sma200 high), then a flat base, then a small tick-up that is a
    # new high vs the flat base (last 60 bars) but still far below the sma50/sma200 built from
    # the earlier decline -- isolates the trend-alignment condition specifically
    close = np.concatenate([
        np.linspace(1000, 200, 100),
        np.full(109, 150.0),
        [155.0],
    ])
    df = _build_momentum_df(len(close), close)
    idx = len(close) - 1
    assert mod._is_momentum_continuation(df, idx, rs_threshold=0.01) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_generate_momentum_candidates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.generate_momentum_candidates'`

- [ ] **Step 3: Implement the three signal functions**

Create `backtest/generate_momentum_candidates.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_generate_momentum_candidates.py -v`
Expected: all pass (9 tests)

- [ ] **Step 5: Run the full test suite (regression gate)**

Run: `python -m pytest backtest/tests -v`
Expected: all pass (136 before this task + 9 new = 145)

- [ ] **Step 6: Commit**

```bash
git add backtest/generate_momentum_candidates.py backtest/tests/test_generate_momentum_candidates.py
git commit -m "feat(backtest): relative-strength/new-high/trend-alignment signals for momentum-continuation (sub-project 5)"
```

---

### Task 2: Base filters + scan orchestration + CLI

**Files:**
- Modify: `backtest/generate_momentum_candidates.py` (adds to the file Task 1 created)
- Test: `backtest/tests/test_generate_momentum_candidates.py` (adds to the file Task 1 created)

**Interfaces:**
- Consumes: `backtest.generate_signal_candidates.CachedCandidate` / `_code_of` (existing,
  unmodified), `backtest.swing_signal_engine.MIN_PRICE` / `MIN_TURNOVER_ALGO` / `NEGATIVE_DART_RE`
  (existing, unmodified), `backtest.dart_history.fetch_disclosures_for_date`,
  `backtest.krx_supply_history.fetch_supply_for_date`, `backtest.yahoo_cache.YahooFetchSpec` /
  `chart_to_ohlcv_daily` / `fetch_yahoo_chart` (all existing, unmodified), plus Task 1's
  `build_universe_return_lookup` / `_is_momentum_continuation`.
- Produces: `_passes_base_filters(df, idx, *, supply, dart_items) -> bool`,
  `scan_momentum_candidates(tickers, *, start, end, dart_api_key=DART_API_KEY) -> Tuple[List[CachedCandidate], List[Dict]]`,
  a `main()` CLI — Task 3 invokes this module as `python -m backtest.generate_momentum_candidates`.

- [ ] **Step 1: Write the failing tests**

Add to `backtest/tests/test_generate_momentum_candidates.py`:

```python
def test_scan_momentum_candidates_caches_window_and_fields(monkeypatch):
    ticker = "000001.KS"
    df = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08",
             "2024-01-09", "2024-01-10", "2024-01-11", "2024-01-12", "2024-01-15",
             "2024-01-16", "2024-01-17"],
            utc=True,
        ),
        "open":   [100.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0],
        "high":   [101.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0],
        "low":    [99.0,  99.0,  100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0],
        "close":  [100.0, 100.0, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5, 108.5, 109.5, 110.5],
        "volume": [1_000_000.0] * 12,
    })

    monkeypatch.setattr(mod, "fetch_yahoo_chart", lambda spec: {"_fake_for": spec.ticker})
    monkeypatch.setattr(mod, "chart_to_ohlcv_daily", lambda data: (df.copy(), None))
    monkeypatch.setattr(mod, "fetch_supply_for_date", lambda trd_dd: {})
    monkeypatch.setattr(mod, "fetch_disclosures_for_date", lambda trd_dd, api_key: {})
    monkeypatch.setattr(mod, "_passes_base_filters", lambda df, idx, *, supply, dart_items: True)
    monkeypatch.setattr(mod, "_is_momentum_continuation", lambda df, idx, *, rs_threshold: idx == 1)

    candidates, skipped = mod.scan_momentum_candidates([ticker], start="2024-01-01", end="2024-01-18")

    assert skipped == []
    assert len(candidates) == 1
    c = candidates[0]
    assert c.ticker == ticker
    assert c.code == "000001"
    assert c.date == "2024-01-03T00:00:00+00:00"  # trigger day itself, idx=1 -- no shift
    assert c.entry == 100.0  # close[idx=1], not close[idx+1]
    assert c.pattern_type == "F모멘텀"
    assert c.score == 110
    assert c.rank_score == 110
    assert c.grade == "매수"
    assert c.hold_days == 10
    # entry_idx = idx(1) + 1 = 2; window is df.iloc[2:12] (HOLD_DAYS=10 rows, all exist)
    assert c.window_open == [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0]
    assert c.window_high == [102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0]
    assert c.window_low == [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
    assert c.window_close == [101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5, 108.5, 109.5, 110.5]


def test_scan_momentum_candidates_skips_fetch_failure(monkeypatch):
    import requests

    def raise_fetch(spec):
        raise requests.exceptions.RequestException("boom")

    monkeypatch.setattr(mod, "fetch_yahoo_chart", raise_fetch)

    candidates, skipped = mod.scan_momentum_candidates(
        ["999999.KS"], start="2024-01-01", end="2024-01-10"
    )
    assert candidates == []
    assert skipped == [{"ticker": "999999.KS", "error": "boom"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_generate_momentum_candidates.py -k scan_momentum -v`
Expected: FAIL with `AttributeError: module 'backtest.generate_momentum_candidates' has no
attribute 'scan_momentum_candidates'`

- [ ] **Step 3: Add imports, `_passes_base_filters`, `scan_momentum_candidates`, and `main()`**

In `backtest/generate_momentum_candidates.py`, replace the top import block (everything before
`HOLD_DAYS = 10`) with:

```python
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
```

Then append, after `_is_momentum_continuation`'s closing `return True`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_generate_momentum_candidates.py -v`
Expected: all pass (11 tests: 9 from Task 1 + 2 new)

- [ ] **Step 5: Run the full test suite (regression gate)**

Run: `python -m pytest backtest/tests -v`
Expected: all pass (136 before Task 1 + 11 new = 147)

- [ ] **Step 6: Commit**

```bash
git add backtest/generate_momentum_candidates.py backtest/tests/test_generate_momentum_candidates.py
git commit -m "feat(backtest): momentum-continuation candidate scan + CLI (sub-project 5)"
```

---

### Task 3: Run the candidate scan

**Files:** none created except the output JSON — this is an execution-only task.

- [ ] **Step 1: Run the scan over the 959-ticker operating universe**

```bash
python -m backtest.generate_momentum_candidates --tickers backtest/tickers_operating.txt --start 2022-01-01 --end 2026-01-01 --out backtest_momentum_candidates.json
```

Expected: prints `wrote backtest_momentum_candidates.json: N candidates, M skipped tickers`. The
same handful of tickers that 404'd against Yahoo in every prior sub-project's scan are expected to
404 again (not a new issue). Record the actual `N` and `M` — this pattern's frequency is
structurally unknown in advance (it has never been run before in this codebase), so do not assume
any particular count; report whatever comes out honestly in Task 5.

- [ ] **Step 2: Commit the candidate cache**

```bash
git add backtest_momentum_candidates.json
git commit -m "data(backtest): momentum-continuation candidate scan, 959-ticker universe (sub-project 5)"
```

---

### Task 4: Run the grid search

**Files:** none created except the output JSON — this is an execution-only task.

- [ ] **Step 1: Run the existing, unmodified grid search on the momentum candidate pool**

```bash
python -c "
import json
from backtest.generate_signal_candidates import CachedCandidate
from backtest.target_stop_grid_search import run_grid_search

d = json.load(open('backtest_momentum_candidates.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]
regime_lookup = json.load(open('backtest_regime_lookup.json', encoding='utf-8'))

result = run_grid_search(
    candidates, regime_lookup=regime_lookup,
    train_start='2022-01-01', train_end='2024-06-30',
    test_start='2024-07-01', test_end='2026-01-01',
)
json.dump(result, open('backtest_momentum_grid_search_results.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('status:', result['selection']['status'])
print('train n_trades:', result['selection']['config']['n_trades'] if result['selection']['config'] else None)
print('test n_trades:', result['test_result']['n_trades'], 'test hit_rate:', result['test_result']['hit_rate'])
"
```

Expected: no exception. Record the actual `status`/`n_trades`/`hit_rate` honestly in Task 5 —
this is the first empirical result for this hypothesis, so there is no prior expectation to match
or contradict.

- [ ] **Step 2: Commit the grid search results**

```bash
git add backtest_momentum_grid_search_results.json
git commit -m "data(backtest): momentum-continuation grid search results (sub-project 5)"
```

---

### Task 5: Write the results analysis document

**Files:**
- Create: `docs/03-analysis/swing-algo-momentum-continuation.analysis.md`

- [ ] **Step 1: Assemble the honest summary**

Using the real numbers from `backtest_momentum_candidates.json` (Task 3) and
`backtest_momentum_grid_search_results.json` (Task 4), write
`docs/03-analysis/swing-algo-momentum-continuation.analysis.md` with these sections (no bracket
placeholders — every number must be the actual value read from these JSON files):

- **Header** matching the convention of `docs/03-analysis/swing-algo-oversold-bounce-hitrate.analysis.md`
  (Analysis Type, Project, Feature, Design Doc / Implementation Plan links, Prior work, Date).
- **Method summary**: restate the entry rule (RS leadership top 10%, new high vs. prior 60 days,
  SMA50>SMA200 trend alignment, `hold_days=10`), linking to the design doc rather than
  re-deriving it.
- **Candidate count and skipped tickers**: the raw scan result from Task 3.
- **Train vs. test result table**: same format as every prior sub-project's Section 2 (`n_trades`,
  reliable/unreliable `n_trades >= 50` column, `hit_rate`, `trades_per_week`, `avg_pnl`,
  `cagr_15slot`, for train and test).
- **Decision-gate verdict**: using the three-way framework (target-met / target-not-met-but-reliable
  / underpowered), state plainly which outcome this result falls into on each split.
- **Limitations**: restate the design doc's Section 7 limitations (single hand-specified rule not
  swept, single train/test split, cross-sectional computation cost, `hold_days=10` not swept)
  rather than re-deriving them.
- **Next step recommendation**: given the actual result, state plainly whether momentum-continuation
  should be pursued further (e.g., a hit-rate-improvement follow-up analogous to sub-project 4, if
  this result is promising-but-underpowered) or whether this hypothesis should also be closed and
  the research line should pivot to low-volatility-accumulation (the other hypothesis named in the
  original Phase B design doc) or elsewhere — a concrete recommendation, not an open question.

No production code (`src/swing-scanner.src.js`) has been changed by this sub-project — as with
every prior sub-project, that remains a separate, later decision, and the document must state this
explicitly.

- [ ] **Step 2: Commit the analysis document**

```bash
git add docs/03-analysis/swing-algo-momentum-continuation.analysis.md
git commit -m "docs: results analysis for swing algo sub-project 5 (momentum-continuation)"
```

---

## Self-Review Notes

- **Spec coverage**: Task 1 covers the design doc's three signal functions (§3's
  `compute_trailing_return`, `build_universe_return_lookup`, `_is_momentum_continuation`). Task 2
  covers `_passes_base_filters` and `scan_momentum_candidates` (§3's remaining components) plus the
  CLI. Tasks 3-4 cover §4's data flow. Task 5 covers §7's required analysis-document content.
- **Placeholder scan**: no TBD/TODO. All numeric fixtures (0.3, 0.091, the all-true/RS-fail/
  new-high-fail/trend-fail cases) were verified by executing the draft implementation against them
  before being written into this plan — including catching and fixing two bugs in the original
  design doc (entry/entry_idx formula copied from E반등's 2-day-confirmed variant instead of the
  single-day-trigger case; new-high window including `idx` itself, which made the condition nearly
  unsatisfiable) — both corrected in the committed design doc before this plan was written.
- **Type consistency**: `_is_momentum_continuation`'s `rs_threshold` parameter type
  (`Optional[float]`) and `None`-means-fail-closed semantics are used identically across Task 1's
  implementation, Task 1's tests, and Task 2's `scan_momentum_candidates` (`rs_lookup.get(date_key)`
  naturally returns `None` for a missing key, no special-casing needed). `CachedCandidate`'s field
  names match `generate_signal_candidates.py` and every prior sub-project's usage identically.

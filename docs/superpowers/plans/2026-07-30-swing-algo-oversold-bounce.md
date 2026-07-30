# Swing Algorithm Enhancement — Sub-project 3 Phase B: Oversold-Bounce Candidate Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new, independent candidate-generation pattern ("E반등", oversold-bounce) that admits
stocks the current A/B/C/D pattern engine structurally excludes (`rsi14 < 40` hard filter), backtest
it with the same rigor as every prior sub-project, and report an honest decision-gate verdict.

**Architecture:** A new standalone scanner script (`backtest/generate_oversold_candidates.py`)
re-reads already-cached OHLCV/DART/supply data, applies a five-condition entry rule to emit
`CachedCandidate` records (reusing the existing dataclass unmodified), then feeds them through
`backtest/target_stop_grid_search.py`'s existing grid-search pipeline with **zero code changes**
to that module. A final analysis document reports the train/test decision-gate verdict.

**Tech Stack:** Python, pandas, numpy — same as all prior sub-projects in this line. No new
dependencies.

## Global Constraints

- No changes to `evaluate_candidate()`, `backtest/swing_signal_engine.py`,
  `backtest/target_stop_grid_search.py`, or `src/swing-scanner.src.js` — everything in this phase is
  additive-only new files.
- Universe: `backtest/tickers_operating.txt` (959 tickers) — same file as prior sub-projects.
- Scan date range: `2022-01-01`..`2026-01-01`. Grid-search train/test split:
  `train_start=2022-01-01`, `train_end=2024-06-30`, `test_start=2024-07-01`, `test_end=2026-01-01` —
  identical to sub-projects 2 and 3 Phase A.
- Reuse already-cached data only: `cache/yahoo/*.json` (per-ticker OHLCV), `backtest/cache/dart`,
  `backtest/cache/krx_supply`, `backtest_regime_lookup.json` — no new network fetch is expected for
  any ticker already fetched by a prior sub-project.
- `CachedCandidate` fixed fields for every emitted candidate (per the design doc, not grid-searched):
  `pattern_type="E반등"`, `score=110`, `rank_score=110`, `grade="매수"`, `hold_days=5`.
- Decision-gate bar (same as sub-projects 2 and 3 Phase A): `hit_rate >= 0.90` AND
  `trades_per_week >= 5.0` AND `cagr_15slot > 0`, on **both** train and test, with the selected
  train config's `n_trades >= 50` reliability rule.
- Design doc: `docs/superpowers/specs/2026-07-30-swing-algo-oversold-bounce-design.md` — the
  authoritative source for the five entry-rule conditions and their rationale.

---

### Task 1: Entry-rule predicate — `_is_oversold_bounce`

**Files:**
- Create: `backtest/generate_oversold_candidates.py`
- Test: `backtest/tests/test_generate_oversold_candidates.py`

**Interfaces:**
- Produces: `_is_oversold_bounce(df: pd.DataFrame, idx: int) -> bool` — `df` has columns
  `open/high/low/close/volume`, sorted ascending by date. Returns `True` only if all five design-doc
  conditions hold at `idx`.
- Consumes: `backtest.indicators.rsi14` (as `calc_rsi14`), `backtest.indicators.sma` (both
  unmodified, already used elsewhere in this codebase).

- [ ] **Step 1: Write the failing tests**

Create `backtest/tests/test_generate_oversold_candidates.py`:

```python
import numpy as np
import pandas as pd

from backtest import generate_oversold_candidates as mod


def _build_df(flat_n, flat_level, rally_days, rally_step, decline_days, decline_step, bounce_close):
    """Builds a synthetic OHLCV DataFrame: flat history -> rally -> decline -> one bounce day
    (the last row, returned as `idx`). All price paths below were verified against the real
    backtest.indicators.rsi14/sma functions before being written into this test."""
    closes = [float(flat_level)] * flat_n
    for i in range(1, rally_days + 1):
        closes.append(flat_level + i * rally_step)
    last = closes[-1]
    for i in range(1, decline_days + 1):
        closes.append(last - i * decline_step)
    closes.append(bounce_close)
    close = np.array(closes, dtype="float64")
    high = close * 1.01
    low = close * 0.99
    openp = np.concatenate([[close[0]], close[:-1]])
    df = pd.DataFrame({
        "open": openp, "high": high, "low": low, "close": close,
        "volume": np.full(len(close), 2_000_000_000.0),
    })
    return df, len(close) - 1


def test_is_oversold_bounce_all_conditions_true():
    df, idx = _build_df(48, 950, 16, 15, 18, 13, 1067.2639)
    assert mod._is_oversold_bounce(df, idx) is True


def test_is_oversold_bounce_false_when_no_rsi_crossup():
    # RSI never crosses back up through 40 (bounce too small)
    df, idx = _build_df(45, 900, 18, 25, 22, 11, 1122.3227)
    assert mod._is_oversold_bounce(df, idx) is False


def test_is_oversold_bounce_false_when_no_oversold_depth():
    # RSI crosses up through 40, but never dipped to <=35 in the prior 5 bars
    df, idx = _build_df(38, 900, 19, 30, 18, 15, 1272.0)
    assert mod._is_oversold_bounce(df, idx) is False


def test_is_oversold_bounce_false_when_pullback_too_shallow():
    # only ~5% off the 20-day high, short of the required 8%
    df, idx = _build_df(49, 1100, 15, 10, 25, 9, 1148.0)
    assert mod._is_oversold_bounce(df, idx) is False


def test_is_oversold_bounce_false_when_below_sma60():
    # bounce day's close is still below the 60-day SMA (no uptrend context)
    df, idx = _build_df(49, 1000, 7, 25, 19, 15, 996.8)
    assert mod._is_oversold_bounce(df, idx) is False


def test_is_oversold_bounce_false_when_not_above_prior_day_high():
    # same price path as the all-true case, but the prior day had a long upper wick
    # (high raised well above the bounce day's close) so the breakout confirmation fails
    df, idx = _build_df(48, 950, 16, 15, 18, 13, 1067.2639)
    df.loc[idx - 1, "high"] = 1117.2639
    assert mod._is_oversold_bounce(df, idx) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_generate_oversold_candidates.py -v`
Expected: all 6 tests FAIL with `ModuleNotFoundError` or `AttributeError` (module/function does not
exist yet).

- [ ] **Step 3: Write the minimal implementation**

Create `backtest/generate_oversold_candidates.py` (this step only — the rest of the module is added
in Task 2):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_generate_oversold_candidates.py -v`
Expected: all 6 tests PASS. If any of the five negative-case tests unexpectedly passes/fails,
do not hand-adjust the assertion — the fixture numbers were verified against the real
`rsi14`/`sma` functions before being written here, so a mismatch means the implementation in Step 3
diverges from the design doc's Entry Rule, not the fixture.

- [ ] **Step 5: Commit**

```bash
git add backtest/generate_oversold_candidates.py backtest/tests/test_generate_oversold_candidates.py
git commit -m "feat(backtest): oversold-bounce entry-rule predicate (sub-project 3 Phase B)"
```

---

### Task 2: Candidate scanner — `scan_oversold_candidates` + base filters + CLI

**Files:**
- Modify: `backtest/generate_oversold_candidates.py`
- Test: `backtest/tests/test_generate_oversold_candidates.py`

**Interfaces:**
- Consumes: `_is_oversold_bounce(df, idx) -> bool` (Task 1). `backtest.generate_signal_candidates.CachedCandidate`
  (dataclass, unmodified) and `backtest.generate_signal_candidates._code_of` (unmodified).
  `backtest.swing_signal_engine.MIN_PRICE`, `MIN_TURNOVER_ALGO`, `NEGATIVE_DART_RE` (unmodified
  constants). `backtest.yahoo_cache.YahooFetchSpec/chart_to_ohlcv_daily/fetch_yahoo_chart`,
  `backtest.dart_history.fetch_disclosures_for_date`, `backtest.krx_supply_history.fetch_supply_for_date`
  (all unmodified).
- Produces: `scan_oversold_candidates(tickers: List[str], *, start: str, end: str, dart_api_key: str = DART_API_KEY) -> Tuple[List[CachedCandidate], List[Dict[str, str]]]`
  — same `(candidates, skipped_tickers)` shape as `generate_signal_candidates.generate_candidates`.
  `main()` — CLI entry point, writes a JSON file with the same `{params, skipped_tickers, candidates}`
  shape as `generate_signal_candidates.py`'s CLI.

- [ ] **Step 1: Write the failing tests**

Append to `backtest/tests/test_generate_oversold_candidates.py`:

```python
def test_scan_oversold_candidates_caches_window_and_fields(monkeypatch):
    ticker = "000001.KS"
    df = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08",
             "2024-01-09", "2024-01-10", "2024-01-11"],
            utc=True,
        ),
        "open":   [100.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
        "high":   [101.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
        "low":    [99.0,  99.0,  100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        "close":  [100.0, 100.0, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5],
        "volume": [1_000_000.0] * 8,
    })

    monkeypatch.setattr(mod, "fetch_yahoo_chart", lambda spec: {"_fake_for": spec.ticker})
    monkeypatch.setattr(mod, "chart_to_ohlcv_daily", lambda data: (df.copy(), None))
    monkeypatch.setattr(mod, "fetch_supply_for_date", lambda trd_dd: {})
    monkeypatch.setattr(mod, "fetch_disclosures_for_date", lambda trd_dd, api_key: {})
    monkeypatch.setattr(mod, "_passes_base_filters", lambda df, idx, *, supply, dart_items: True)
    monkeypatch.setattr(mod, "_is_oversold_bounce", lambda df, idx: idx == 1)

    candidates, skipped = mod.scan_oversold_candidates([ticker], start="2024-01-01", end="2024-01-12")

    assert skipped == []
    assert len(candidates) == 1
    c = candidates[0]
    assert c.ticker == ticker
    assert c.code == "000001"
    assert c.date == "2024-01-03T00:00:00+00:00"
    assert c.entry == 101.5
    assert c.pattern_type == "E반등"
    assert c.score == 110
    assert c.rank_score == 110
    assert c.grade == "매수"
    assert c.hold_days == 5
    # entry_idx = idx(1) + 1 = 2; window is df.iloc[2:7] (HOLD_DAYS=5 rows, all exist)
    assert c.window_open == [101.0, 102.0, 103.0, 104.0, 105.0]
    assert c.window_high == [102.0, 103.0, 104.0, 105.0, 106.0]
    assert c.window_low == [100.0, 101.0, 102.0, 103.0, 104.0]
    assert c.window_close == [101.5, 102.5, 103.5, 104.5, 105.5]


def test_scan_oversold_candidates_skips_fetch_failure(monkeypatch):
    import requests

    def raise_fetch(spec):
        raise requests.exceptions.RequestException("boom")

    monkeypatch.setattr(mod, "fetch_yahoo_chart", raise_fetch)

    candidates, skipped = mod.scan_oversold_candidates(
        ["999999.KS"], start="2024-01-01", end="2024-01-10"
    )
    assert candidates == []
    assert skipped == [{"ticker": "999999.KS", "error": "boom"}]
```

No new top-level imports are needed in the test file — `pd` and `mod` are already imported by
Task 1's tests in the same file; `requests` is imported locally inside
`test_scan_oversold_candidates_skips_fetch_failure` (matching `test_generate_signal_candidates.py`'s
existing convention).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_generate_oversold_candidates.py -v`
Expected: the two new tests FAIL with `AttributeError: module 'backtest.generate_oversold_candidates' has no attribute 'scan_oversold_candidates'` (or `_passes_base_filters`). The Task 1 tests still PASS.

- [ ] **Step 3: Write the minimal implementation**

Replace the full contents of `backtest/generate_oversold_candidates.py` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_generate_oversold_candidates.py -v`
Expected: all 8 tests PASS (6 from Task 1, 2 from this task).

- [ ] **Step 5: Run the full backtest test suite to confirm no regressions**

Run: `python -m pytest backtest/tests/ -v`
Expected: all tests pass, including every pre-existing test file — this task only added a new file
and imported (never modified) `CachedCandidate`, `_code_of`, `MIN_PRICE`, `MIN_TURNOVER_ALGO`,
`NEGATIVE_DART_RE`.

- [ ] **Step 6: Commit**

```bash
git add backtest/generate_oversold_candidates.py backtest/tests/test_generate_oversold_candidates.py
git commit -m "feat(backtest): oversold-bounce candidate scanner + CLI (sub-project 3 Phase B)"
```

---

### Task 3: Run the real scan over the operating universe

**Files:** none created except the output JSON — this is an execution-only task.

- [ ] **Step 1: Run the scanner over all 959 operating tickers**

Run (re-reads all already-fetched tickers from `yahoo_cache`'s disk cache — cache hits, no new
network fetch expected; low minutes, comparable to prior sub-projects' re-scan runs):

```bash
python -m backtest.generate_oversold_candidates --tickers backtest/tickers_operating.txt --start 2022-01-01 --end 2026-01-01 --out backtest_oversold_candidates.json
```

Expected: no exception; prints a candidate count. Per the design doc's Limitations section, this
count may be small (the five-condition rule is more restrictive than any single A/B/C/D pattern
condition) — a small count here is expected and must not be treated as a bug; it becomes the
`n_trades`-reliability question Task 5's analysis document must address honestly.

- [ ] **Step 2: Commit the artifact for reproducibility**

```bash
git add backtest_oversold_candidates.json
git commit -m "data(backtest): oversold-bounce candidate scan, 959-ticker operating universe (sub-project 3 Phase B)"
```

---

### Task 4: Run the grid search

**Files:** none created except the output JSON — this is an execution-only task.

- [ ] **Step 1: Load candidates and run the existing grid search unmodified**

Run:

```bash
python -c "
import json
from backtest.generate_signal_candidates import CachedCandidate
from backtest.target_stop_grid_search import run_grid_search

d = json.load(open('backtest_oversold_candidates.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]
regime_lookup = json.load(open('backtest_regime_lookup.json', encoding='utf-8'))

result = run_grid_search(
    candidates, regime_lookup=regime_lookup,
    train_start='2022-01-01', train_end='2024-06-30',
    test_start='2024-07-01', test_end='2026-01-01',
)
json.dump(result, open('backtest_oversold_grid_search_results.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

sel = result['selection']
cfg = sel['config']
test = result['test_result']
print('candidates:', len(candidates))
print('train status:', sel['status'], 'train n_trades:', cfg['n_trades'], 'train hit_rate:', cfg['hit_rate'], 'train cagr_15slot:', cfg['cagr_15slot'])
print('test n_trades:', test['n_trades'], 'test hit_rate:', test['hit_rate'], 'test cagr_15slot:', test['cagr_15slot'])
"
```

Expected: no exception. If `len(candidates)` is 0, stop and investigate before proceeding to Task 5
(a truly empty pool is a data/logic problem to diagnose, not a result to report) — any non-zero
count, however small, should proceed to Task 5 as-is.

- [ ] **Step 2: Commit the raw result for reproducibility**

```bash
git add backtest_oversold_grid_search_results.json
git commit -m "data(backtest): oversold-bounce grid search results, train 2022-2024H1 / test 2024H2-2026 (sub-project 3 Phase B)"
```

---

### Task 5: Write the results analysis document

**Files:**
- Create: `docs/03-analysis/swing-algo-oversold-bounce.analysis.md`

- [ ] **Step 1: Write the analysis document**

Create `docs/03-analysis/swing-algo-oversold-bounce.analysis.md` with these sections, using the real
numbers from Task 4's Step 1 output (no bracket placeholders left in the committed file):

- **Header** matching the convention of `docs/03-analysis/swing-algo-new-signal-filters.analysis.md`
  (Analysis Type, Project, Feature, Design Doc / Implementation Plan links, Date).
- **Method summary**: restate the five entry-rule conditions and their trader-review rationale
  (RSI depth, pullback depth, breakout confirmation), linking to the design doc rather than
  re-deriving it. State the raw candidate count from Task 3.
- **Train vs. test result table**: `hit_rate`, `trades_per_week`, `avg_pnl`, `cagr_15slot`,
  `n_trades` for both train and test, plus an explicit **reliable / unreliable** column
  (`n_trades >= 50` per the design doc's reliability rule).
- **Decision-gate verdict**: state plainly whether the selected train config reaches
  `hit_rate >= 90%`, `trades_per_week >= 5`, and `cagr_15slot > 0` **on both train and test**, AND
  is statistically reliable (`n_trades >= 50` on both). Per the design doc's Limitations section,
  explicitly distinguish three possible outcomes, not two:
  1. **Target met and reliable** — recommend this configuration (a separate, later deployment
     decision) and state that sub-project 3 ends here.
  2. **Target not met, but reliable (n_trades >= 50 on both train and test)** — a genuine negative
     result for this specific five-condition rule; report the best-available numbers plainly (same
     honesty standard as every prior sub-project) and recommend scoping the momentum-continuation
     or low-volatility-accumulation hypotheses next, per the design doc's "Explicitly out of scope"
     note.
  3. **Underpowered (n_trades < 50 on train or test)** — report this as inconclusive, not negative;
     state the exact `n_trades` figure and do not draw a pass/fail conclusion from it. Per the
     design doc, name which specific threshold (RSI depth 35, pullback depth 8%, or the prior-day-
     high breakout) is the most likely candidate to loosen first if this outcome occurs, with
     rationale for that specific choice over the other two.
- **Limitations**: carry forward from the design doc — single hand-specified rule (not
  grid-searched), single train/test split, inherited sub-project 1/2 limitations (flat-percentage
  target/stop, orderbook checks not modeled, flat-fee assumption).
- **Next step recommendation**: explicitly state that no production code
  (`src/swing-scanner.src.js`) has been changed, and that any further work (deployment, or scoping
  a follow-up hypothesis) is a separate decision pending the user's review of these results.

- [ ] **Step 2: Commit**

```bash
git add docs/03-analysis/swing-algo-oversold-bounce.analysis.md
git commit -m "docs: oversold-bounce candidate engine results for swing algo enhancement sub-project 3 Phase B"
```

---

## Self-Review Notes

- **Spec coverage:** every in-scope item from
  `docs/superpowers/specs/2026-07-30-swing-algo-oversold-bounce-design.md` maps to a task — the
  five-condition entry rule (Task 1), the reused base filters and CachedCandidate emission (Task 2),
  the real scan run (Task 3), the unmodified grid-search run (Task 4), and the decision-gate
  write-up including the three-way outcome distinction from the Limitations section (Task 5).
- **Placeholder scan:** no task contains "TBD"/"TODO"/unfilled brackets; Task 5's document content
  is described precisely (which table, which columns, which three-way verdict rule) without being
  filled in here, matching sub-project 3 Phase A's Task 9 pattern (real values only exist after
  Tasks 3/4 run).
- **Type consistency:** `CachedCandidate` (imported unmodified from `generate_signal_candidates.py`)
  is used identically across Tasks 2 and 4 (constructed in Task 2, round-tripped through JSON via
  `asdict`/`CachedCandidate(**c)` in Task 3/4, exactly matching sub-project 3 Phase A's Task 8
  round-trip convention). `_is_oversold_bounce(df, idx) -> bool` and
  `_passes_base_filters(df, idx, *, supply, dart_items) -> bool` are defined in Task 1/2 and used
  with identical signatures in `scan_oversold_candidates` and in both tests' `monkeypatch.setattr`
  calls.
- **Numeric-fixture verification:** all six `_is_oversold_bounce` test fixtures (Task 1) were
  computed and verified against the actual `backtest.indicators.rsi14`/`sma` functions before being
  written into this plan (not hand-derived), so Step 4's "run to verify" is a confirmation, not a
  trial-and-error search.
- **Global-constraint check:** "no changes to `evaluate_candidate()`/`swing_signal_engine.py`/
  `target_stop_grid_search.py`/`src/swing-scanner.src.js`" is verified directly by Task 2's Step 5
  full-suite regression run (any accidental modification would show up as an unrelated test file
  changing behavior) and by Task 4 calling `run_grid_search` with no new parameters, exactly as it
  already exists. The fixed `CachedCandidate` field values (`score=110`, etc.) are hardcoded once in
  Task 2's implementation and asserted directly in Task 2's test, so a future edit changing them
  would be caught immediately.
- **Scope check:** single cohesive phase (one new pattern, reusing sub-project 1/2's exit-simulation
  pipeline unmodified), matching the design doc's Phase B boundary. The momentum-continuation and
  low-volatility-accumulation hypotheses are explicitly out of scope here, per the design doc.

# swing-algo-oversold-bounce-hitrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply all 5 trader-diagnosed hit-rate levers to the oversold-bounce ("E반등") pattern
from swing-algo sub-project 3 Phase B, executed in dependency order (item 3 first, producing a
new v3 candidate pool; items 1/2/4 as additive tags swept against that pool; item 5 as a new
ATR-based target/stop grid search), reporting each stage's effect honestly per this project's
established no-softening convention.

**Architecture:** Stage 1 modifies `backtest/generate_oversold_candidates.py`'s entry rule to
require 2-day RSI confirmation (item 3), producing `backtest_oversold_candidates_v3.json`. Stage 2
adds a new `backtest/oversold_candidate_signals.py` module computing 3 boolean tags (items 1, 2,
4) plus an ATR-pct lookup on the v3 pool, then sweeps all 7 non-empty tag subsets through
`target_stop_grid_search.py`'s existing, **unmodified** `run_grid_search`/`required_tags`
mechanism. Stage 3 adds a new `backtest/atr_stop_grid_search.py` (item 5) that reuses the same
simulation primitives (`simulate_exit`, `apply_toss_liveprice`, `apply_round_trip_cost`,
`simulate_portfolio`, `cagr_and_mdd`) but computes target/stop from ATR instead of a flat
percentage.

**Tech Stack:** Python, pandas/numpy, pytest. No new dependencies.

## Global Constraints

- `target_stop_grid_search.py` is **not modified** in this plan — every prior sub-project's design
  treats it as locked, already-reviewed code.
- Decision-gate bar (from design doc, reused from every prior sub-project): `hit_rate >= 0.90`
  (`MIN_HIT_RATE` in `target_stop_grid_search.py`) AND `trades_per_week >= 5.0`
  (`MIN_TRADES_PER_WEEK`) AND `cagr_15slot > 0`, on **both** train (`2022-01-01`..`2024-06-30`)
  and test (`2024-07-01`..`2026-01-01`) splits.
- Statistical-reliability gate: `n_trades >= 50` on **both** splits before any pass/fail
  conclusion is drawn (three-way outcome: target-met / target-not-met-but-reliable /
  underpowered) — report honestly, never silently switch to soft scoring to dodge this.
- `HOLD_DAYS = 5` (existing E반등 convention, unchanged).
- Item 1 threshold: `rvol >= 1.5` on the trigger day.
- Item 4 pivot-low definition: a close strictly lower than the 3 bars on each side
  (`SUPPORT_PIVOT_WINDOW = 3`), searched over the trailing 40 bars (`SUPPORT_LOOKBACK = 40`),
  proximity tolerance `SUPPORT_TOLERANCE = 0.03` (±3%).
- Item 5 grid: `target_mult=[1.0, 1.5, 2.0, 3.0]`, `stop_mult=[0.5, 1.0, 1.5, 2.0]` (16 cells).
- Reused data files (already committed, do not re-fetch): `backtest/tickers_operating.txt` (959
  tickers), `backtest_sector_map.json`, `backtest_regime_lookup.json`.
- Every new function must have no lookahead: computations at candidate trigger day `idx` may use
  data through and including `idx`, never `idx+1` or later (except item 3's own confirmation
  check, which is exactly the point of that item).

---

### Task 1: 2-day RSI confirmation (item 3) — entry-rule change producing the v3 pool

**Files:**
- Modify: `backtest/generate_oversold_candidates.py`
- Test: `backtest/tests/test_generate_oversold_candidates.py`

**Interfaces:**
- Consumes: `backtest.indicators.rsi14` (existing), `_is_oversold_bounce(df, idx) -> bool`
  (existing, unchanged), `_passes_base_filters(df, idx, *, supply, dart_items) -> bool` (existing,
  unchanged).
- Produces: `_confirms_next_day(df: pd.DataFrame, idx: int) -> bool` — new. `idx` here is the
  *provisional* trigger day (the day `_is_oversold_bounce` fired on); returns whether RSI is still
  `>= 40` at `idx + 1`. `scan_oversold_candidates` now creates candidates dated at `idx + 1` (not
  `idx`), with `entry_idx = idx + 2` for the window — later tasks must use this new indexing when
  reasoning about v3 candidate dates.

- [ ] **Step 1: Write the failing tests for `_confirms_next_day`**

Add to `backtest/tests/test_generate_oversold_candidates.py`, after the existing
`_build_df` helper:

```python
def _build_df_confirm(flat_n, flat_level, rally_days, rally_step, decline_days, decline_step,
                       bounce_close, confirm_close):
    """Extends _build_df's fixture with one more day (the 2-day-confirmation day) appended
    after the bounce day. idx (returned) still points at the bounce day, unchanged."""
    df, idx = _build_df(flat_n, flat_level, rally_days, rally_step, decline_days, decline_step,
                         bounce_close)
    new_row = pd.DataFrame({
        "open": [float(df["close"].iloc[-1])],
        "high": [confirm_close * 1.01],
        "low": [confirm_close * 0.99],
        "close": [confirm_close],
        "volume": [2_000_000_000.0],
    })
    df = pd.concat([df, new_row], ignore_index=True)
    return df, idx


def test_confirms_next_day_true_when_rsi_still_above_40():
    # bounce day's RSI (idx) is 54.56; confirm day holds flat -> RSI at idx+1 stays 54.73 (>=40)
    df, idx = _build_df_confirm(48, 950, 16, 15, 18, 13, 1067.2639, confirm_close=1067.2639)
    assert mod._confirms_next_day(df, idx) is True


def test_confirms_next_day_false_when_rsi_drops_back_below_40():
    # confirm day drops sharply -> RSI at idx+1 falls to 38.54 (<40), a whipsaw the 2-day
    # confirmation is designed to catch
    df, idx = _build_df_confirm(48, 950, 16, 15, 18, 13, 1067.2639, confirm_close=960.0)
    assert mod._confirms_next_day(df, idx) is False


def test_confirms_next_day_false_when_no_next_day_data():
    # idx is the last row of the DataFrame -- there is no idx+1 to check
    df, idx = _build_df(48, 950, 16, 15, 18, 13, 1067.2639)
    assert mod._confirms_next_day(df, idx) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_generate_oversold_candidates.py -k confirms_next_day -v`
Expected: FAIL with `AttributeError: module 'backtest.generate_oversold_candidates' has no
attribute '_confirms_next_day'`

- [ ] **Step 3: Implement `_confirms_next_day`**

In `backtest/generate_oversold_candidates.py`, add immediately after `_is_oversold_bounce`
(after its `return True` at line 65):

```python
def _confirms_next_day(df: pd.DataFrame, idx: int) -> bool:
    """Item 3 (2-day confirmation): the RSI cross-up _is_oversold_bounce confirmed at idx
    must still hold (rsi14 >= 40) one bar later, at idx+1 -- guards against a single-day
    whipsaw back below 40 that a bare same-day cross-up cannot distinguish from a real
    reversal."""
    close = df["close"].to_numpy(dtype="float64")
    if idx + 1 >= len(close):
        return False
    rsi_next = calc_rsi14(close, idx + 1)
    if not np.isfinite(rsi_next):
        return False
    return rsi_next >= 40
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_generate_oversold_candidates.py -k confirms_next_day -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write the failing test for the updated `scan_oversold_candidates` indexing**

Replace the existing `test_scan_oversold_candidates_caches_window_and_fields` test (it currently
monkeypatches only `_is_oversold_bounce`; it must also monkeypatch `_confirms_next_day` and expect
the shifted date/entry/window) with:

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
    # provisional bounce fires at idx=1; confirmation also fires at idx=1 -> trigger_idx=2,
    # entry_idx=3
    monkeypatch.setattr(mod, "_is_oversold_bounce", lambda df, idx: idx == 1)
    monkeypatch.setattr(mod, "_confirms_next_day", lambda df, idx: idx == 1)

    candidates, skipped = mod.scan_oversold_candidates([ticker], start="2024-01-01", end="2024-01-12")

    assert skipped == []
    assert len(candidates) == 1
    c = candidates[0]
    assert c.ticker == ticker
    assert c.code == "000001"
    assert c.date == "2024-01-04T00:00:00+00:00"  # trigger_idx=2, one day later than Phase B
    assert c.entry == 101.5  # close[2]
    assert c.pattern_type == "E반등"
    assert c.score == 110
    assert c.rank_score == 110
    assert c.grade == "매수"
    assert c.hold_days == 5
    # entry_idx = trigger_idx(2) + 1 = 3; window is df.iloc[3:8] (HOLD_DAYS=5 rows, all exist)
    assert c.window_open == [102.0, 103.0, 104.0, 105.0, 106.0]
    assert c.window_high == [103.0, 104.0, 105.0, 106.0, 107.0]
    assert c.window_low == [101.0, 102.0, 103.0, 104.0, 105.0]
    assert c.window_close == [102.5, 103.5, 104.5, 105.5, 106.5]
```

- [ ] **Step 6: Run test to verify it fails**

Run: `python -m pytest backtest/tests/test_generate_oversold_candidates.py -k caches_window_and_fields -v`
Expected: FAIL — old code produces `c.date == "2024-01-03T00:00:00+00:00"` and `c.entry == 100.0`
(Phase B's un-shifted indexing).

- [ ] **Step 7: Update `scan_oversold_candidates`'s loop body**

In `backtest/generate_oversold_candidates.py`, replace the inner `for t, df in per_ticker.items():`
loop body (lines 120-144) with:

```python
        for t, df in per_ticker.items():
            idxs = df.index[df["timestamp_utc"] == day].tolist()
            if not idxs:
                continue
            idx = int(idxs[0])
            if idx + 2 >= len(df):
                continue
            code = _code_of(t)
            if not _passes_base_filters(
                df, idx, supply=supply_map.get(code, {}), dart_items=dart_map.get(code, [])
            ):
                continue
            if not _is_oversold_bounce(df, idx):
                continue
            if not _confirms_next_day(df, idx):
                continue
            trigger_idx = idx + 1
            entry_idx = trigger_idx + 1
            window = df.iloc[entry_idx: entry_idx + HOLD_DAYS]
            candidates.append(CachedCandidate(
                ticker=t, code=code, date=df["timestamp_utc"].iloc[trigger_idx].isoformat(),
                entry=float(df["close"].to_numpy(dtype="float64")[trigger_idx]),
                pattern_type="E반등", score=110, rank_score=110, grade="매수", hold_days=HOLD_DAYS,
                window_open=window["open"].astype(float).tolist(),
                window_high=window["high"].astype(float).tolist(),
                window_low=window["low"].astype(float).tolist(),
                window_close=window["close"].astype(float).tolist(),
            ))
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_generate_oversold_candidates.py -v`
Expected: all pass (11 tests: the 3 new `_confirms_next_day` tests + 8 existing, with
`test_scan_oversold_candidates_caches_window_and_fields` updated)

- [ ] **Step 9: Run the full test suite (regression gate)**

Run: `python -m pytest backtest/tests -v`
Expected: all pass (was 116 before this task; +3 new = 119)

- [ ] **Step 10: Commit**

```bash
git add backtest/generate_oversold_candidates.py backtest/tests/test_generate_oversold_candidates.py
git commit -m "feat(backtest): 2-day RSI confirmation for oversold-bounce entry rule (sub-project 4 item 3)"
```

---

### Task 2: Run the v3 candidate scan

**Files:** none created except the output JSON — this is an execution-only task.

- [ ] **Step 1: Run the scan over the 959-ticker operating universe**

```bash
python -m backtest.generate_oversold_candidates --tickers backtest/tickers_operating.txt --start 2022-01-01 --end 2026-01-01 --out backtest_oversold_candidates_v3.json
```

Expected: prints `wrote backtest_oversold_candidates_v3.json: N candidates, M skipped tickers`
(the same 4 tickers from Phase B's `skipped_tickers` are expected to 404 again — not a bug). `N`
is expected to be **lower** than v2's 127 (the 2-day confirmation is strictly more restrictive) —
record the actual number for the analysis document, do not adjust the rule to hit a target count.

- [ ] **Step 2: Commit the v3 candidate cache**

```bash
git add backtest_oversold_candidates_v3.json
git commit -m "data(backtest): oversold-bounce v3 candidate scan, 2-day RSI confirmation (sub-project 4 Stage 1)"
```

---

### Task 3: Volume confirm, sector strength, support confluence tags + ATR-pct lookup (items 1, 2, 4)

**Files:**
- Create: `backtest/oversold_candidate_signals.py`
- Test: `backtest/tests/test_oversold_candidate_signals.py`

**Interfaces:**
- Consumes: `backtest.candidate_signals.build_sector_returns_by_date` (existing, unmodified),
  `backtest.candidate_signals.compute_sector_strength` (existing, unmodified),
  `backtest.indicators.atr` (existing), `backtest.generate_signal_candidates.CachedCandidate`
  (existing).
- Produces: `compute_volume_confirm(df, idx) -> bool`, `compute_support_confluence(df, idx) -> bool`,
  `compute_atr_pct(df, idx) -> float`, `tag_candidates_oversold(candidates, per_ticker_ohlcv,
  sector_map) -> Dict[Tuple[str, str], Dict[str, bool]]` (keys: `volume_confirm`,
  `sector_strong`, `support_confluence`), `build_atr_pct_lookup(candidates, per_ticker_ohlcv) ->
  Dict[Tuple[str, str], float]` — Task 4 and Task 6 both consume these.

- [ ] **Step 1: Write the failing tests**

Create `backtest/tests/test_oversold_candidate_signals.py`:

```python
import numpy as np
import pandas as pd

from backtest import oversold_candidate_signals as mod
from backtest.generate_signal_candidates import CachedCandidate


def _make_df(close, high=None, low=None, volume=None):
    close = np.asarray(close, dtype="float64")
    n = len(close)
    return pd.DataFrame({
        "timestamp_utc": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
        "open": close,
        "high": high if high is not None else close * 1.01,
        "low": low if low is not None else close * 0.99,
        "close": close,
        "volume": volume if volume is not None else np.full(n, 1_000_000.0),
    })


def test_compute_volume_confirm_true_at_or_above_threshold():
    volume = np.full(26, 1_000_000.0)
    volume[25] = 2_000_000.0  # rvol = 2.0 >= 1.5
    df = _make_df(np.full(26, 100.0), volume=volume)
    assert mod.compute_volume_confirm(df, 25) is True


def test_compute_volume_confirm_false_below_threshold():
    volume = np.full(26, 1_000_000.0)  # rvol = 1.0 < 1.5
    df = _make_df(np.full(26, 100.0), volume=volume)
    assert mod.compute_volume_confirm(df, 25) is False


def test_compute_support_confluence_true_near_pivot_low():
    # descend 1000->900 over 30 bars, then ascend to 920 (2.2% above the 900 pivot low)
    desc = np.linspace(1000, 900, 30)
    asc = np.linspace(905, 920, 15)
    close = np.concatenate([desc, asc])
    idx = len(close) - 1
    df = _make_df(close)
    assert mod.compute_support_confluence(df, idx) is True


def test_compute_support_confluence_false_far_from_pivot_low():
    desc = np.linspace(1000, 900, 30)
    asc = np.linspace(905, 970, 15)  # 7.8% above the 900 pivot low -- outside 3% tolerance
    close = np.concatenate([desc, asc])
    idx = len(close) - 1
    df = _make_df(close)
    assert mod.compute_support_confluence(df, idx) is False


def test_compute_support_confluence_false_when_no_interior_pivot():
    # pure monotonic ascent -- no local low strictly lower than both neighborhoods
    close = np.linspace(900, 950, 45)
    idx = len(close) - 1
    df = _make_df(close)
    assert mod.compute_support_confluence(df, idx) is False


def test_compute_atr_pct_value_pinned():
    n = 20
    df = _make_df(np.full(n, 100.0), high=np.full(n, 101.0), low=np.full(n, 99.0))
    idx = n - 1
    atr_pct = mod.compute_atr_pct(df, idx)
    assert abs(atr_pct - 0.02) < 1e-9


def test_compute_atr_pct_nan_when_insufficient_history():
    df = _make_df(np.full(5, 100.0), high=np.full(5, 101.0), low=np.full(5, 99.0))
    assert np.isnan(mod.compute_atr_pct(df, 2))


def _candidate(ticker, code, date, entry=100.0):
    return CachedCandidate(
        ticker=ticker, code=code, date=date, entry=entry,
        pattern_type="E반등", score=110, rank_score=110, grade="매수", hold_days=5,
        window_open=[entry] * 5, window_high=[entry] * 5,
        window_low=[entry] * 5, window_close=[entry] * 5,
    )


def test_tag_candidates_oversold_maps_each_candidate():
    n = 26
    close = np.full(n, 100.0)
    volume = np.full(n, 1_000_000.0)
    volume[25] = 2_000_000.0
    df = _make_df(close, volume=volume)
    date = df["timestamp_utc"].iloc[25].isoformat()
    candidate = _candidate("000001.KS", "000001", date)

    tags = mod.tag_candidates_oversold([candidate], {"000001.KS": df}, sector_map={})
    key = ("000001.KS", date)
    assert key in tags
    assert tags[key]["volume_confirm"] is True
    assert tags[key]["sector_strong"] is False  # empty sector_map fails closed
    assert tags[key]["support_confluence"] is False  # flat price series has no pivot low


def test_tag_candidates_oversold_fails_closed_when_ticker_unknown():
    candidate = _candidate("999999.KS", "999999", "2024-01-26T00:00:00+00:00")
    tags = mod.tag_candidates_oversold([candidate], {}, sector_map={})
    key = ("999999.KS", "2024-01-26T00:00:00+00:00")
    assert tags[key] == {"volume_confirm": False, "sector_strong": False, "support_confluence": False}


def test_build_atr_pct_lookup_includes_only_locatable_candidates():
    n = 20
    df = _make_df(np.full(n, 100.0), high=np.full(n, 101.0), low=np.full(n, 99.0))
    date = df["timestamp_utc"].iloc[19].isoformat()
    found = _candidate("000001.KS", "000001", date)
    missing = _candidate("999999.KS", "999999", "2024-01-26T00:00:00+00:00")

    lookup = mod.build_atr_pct_lookup([found, missing], {"000001.KS": df})
    assert ("000001.KS", date) in lookup
    assert abs(lookup[("000001.KS", date)] - 0.02) < 1e-9
    assert ("999999.KS", "2024-01-26T00:00:00+00:00") not in lookup
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_oversold_candidate_signals.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.oversold_candidate_signals'`

- [ ] **Step 3: Implement `backtest/oversold_candidate_signals.py`**

```python
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
    return rvol >= VOLUME_CONFIRM_RVOL_MIN


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
        if close[p] < left.min() and close[p] < right.min():
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_oversold_candidate_signals.py -v`
Expected: all pass (11 tests)

- [ ] **Step 5: Run the full test suite (regression gate)**

Run: `python -m pytest backtest/tests -v`
Expected: all pass (119 before this task + 11 new = 130)

- [ ] **Step 6: Commit**

```bash
git add backtest/oversold_candidate_signals.py backtest/tests/test_oversold_candidate_signals.py
git commit -m "feat(backtest): volume/support/ATR-pct signals for oversold-bounce v3 pool (sub-project 4 items 1, 4, 5-prep)"
```

---

### Task 4: Tag the v3 pool and build the ATR-pct lookup

**Files:** none created except the output JSONs — this is an execution-only task.

- [ ] **Step 1: Tag every v3 candidate and build the ATR-pct lookup**

Run (reads v3 candidates + reuses the already-committed `backtest_sector_map.json`; re-reads
each ticker's OHLCV from `yahoo_cache`'s disk cache -- cache hits expected, no new network fetch):

```bash
python -c "
import json
from backtest.yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart
from backtest.generate_signal_candidates import CachedCandidate
from backtest.oversold_candidate_signals import build_atr_pct_lookup, tag_candidates_oversold

d = json.load(open('backtest_oversold_candidates_v3.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]
tickers = sorted({c.ticker for c in candidates})

per_ticker_ohlcv = {}
for t in tickers:
    data = fetch_yahoo_chart(YahooFetchSpec(ticker=t, range='5y', interval='1d'))
    df, _ = chart_to_ohlcv_daily(data)
    per_ticker_ohlcv[t] = df.sort_values('timestamp_utc').reset_index(drop=True)

sector_map = json.load(open('backtest_sector_map.json', encoding='utf-8'))
tags = tag_candidates_oversold(candidates, per_ticker_ohlcv, sector_map)
out_tags = {f'{tk}|{dt}': v for (tk, dt), v in tags.items()}
json.dump(out_tags, open('backtest_oversold_v3_tags.json', 'w', encoding='utf-8'), ensure_ascii=False)

atr_lookup = build_atr_pct_lookup(candidates, per_ticker_ohlcv)
out_atr = {f'{tk}|{dt}': v for (tk, dt), v in atr_lookup.items()}
json.dump(out_atr, open('backtest_oversold_v3_atr_lookup.json', 'w', encoding='utf-8'), ensure_ascii=False)

n = len(tags)
n_vol = sum(1 for v in tags.values() if v['volume_confirm'])
n_sector = sum(1 for v in tags.values() if v['sector_strong'])
n_support = sum(1 for v in tags.values() if v['support_confluence'])
print(f'tagged {n} candidates: volume_confirm={n_vol}, sector_strong={n_sector}, support_confluence={n_support}')
print(f'atr_pct lookup: {len(atr_lookup)}/{n} candidates')
"
```

Expected: no exception; `tagged` count equals the v3 candidate count from Task 2. Report the
actual `volume_confirm`/`sector_strong`/`support_confluence` counts honestly in the analysis
document (Task 8) even if one or more is degenerate (0 or all) — with only tens to low hundreds
of v3 candidates (much smaller than Phase A's 21,587), a degenerate count is plausible and not
automatically a bug the way it was in Phase A; investigate only if it looks like an implementation
error (e.g. an exception was swallowed), not merely because the count is extreme.

- [ ] **Step 2: Commit the tag and ATR-pct lookup artifacts**

```bash
git add backtest_oversold_v3_tags.json backtest_oversold_v3_atr_lookup.json
git commit -m "data(backtest): volume/sector/support tags + ATR-pct lookup for oversold-bounce v3 pool"
```

---

### Task 5: Run the 7-subset tag sweep (items 1, 2, 4) through the unmodified grid search

**Files:** none created except the output JSON — this is an execution-only task.

- [ ] **Step 1: Run all 7 non-empty tag subsets**

```bash
python -c "
import itertools
import json

from backtest.generate_signal_candidates import CachedCandidate
from backtest.target_stop_grid_search import run_grid_search

d = json.load(open('backtest_oversold_candidates_v3.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]
regime_lookup = json.load(open('backtest_regime_lookup.json', encoding='utf-8'))
raw_tags = json.load(open('backtest_oversold_v3_tags.json', encoding='utf-8'))
tags_lookup = {tuple(k.split('|', 1)): v for k, v in raw_tags.items()}

TAG_NAMES = ['volume_confirm', 'sector_strong', 'support_confluence']
subsets = []
for r in range(1, 4):
    subsets.extend(itertools.combinations(TAG_NAMES, r))

results = {}
for subset in subsets:
    key = '+'.join(subset)
    r = run_grid_search(
        candidates, regime_lookup=regime_lookup,
        train_start='2022-01-01', train_end='2024-06-30',
        test_start='2024-07-01', test_end='2026-01-01',
        required_tags=frozenset(subset), tags_lookup=tags_lookup,
    )
    results[key] = {'tags': list(subset), **r}
    print(key, 'status:', r['selection']['status'], 'train n_trades:', r['selection']['config']['n_trades'] if r['selection']['config'] else None, 'test n_trades:', r['test_result']['n_trades'])

json.dump(results, open('backtest_oversold_v3_tagsweep_results.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('wrote backtest_oversold_v3_tagsweep_results.json:', len(results), 'subsets')
"
```

Expected: exactly 7 subsets printed and written (3 singles, 3 pairs, 1 triple; the empty/`∅`
subset is Task 2's own v3 pool run with no tag filter at all, not part of this sweep -- report it
separately in Task 8 from `backtest_oversold_candidates_v3.json` directly run through
`run_grid_search` with `required_tags=frozenset()`). No exceptions. `n_trades` may legitimately be
very small (single digits) for some subsets given the v3 pool is already much smaller than Phase
B's 127 -- this is expected, not a bug; do not treat a subset producing 0 trades as an error.

- [ ] **Step 2: Also run the untagged (∅) v3-pool baseline for the same comparison**

```bash
python -c "
import json
from backtest.generate_signal_candidates import CachedCandidate
from backtest.target_stop_grid_search import run_grid_search

d = json.load(open('backtest_oversold_candidates_v3.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]
regime_lookup = json.load(open('backtest_regime_lookup.json', encoding='utf-8'))

r = run_grid_search(
    candidates, regime_lookup=regime_lookup,
    train_start='2022-01-01', train_end='2024-06-30',
    test_start='2024-07-01', test_end='2026-01-01',
)
json.dump(r, open('backtest_oversold_v3_none_results.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('none: status:', r['selection']['status'], 'test n_trades:', r['test_result']['n_trades'])
"
```

- [ ] **Step 3: Commit the sweep results**

```bash
git add backtest_oversold_v3_tagsweep_results.json backtest_oversold_v3_none_results.json
git commit -m "data(backtest): oversold-bounce v3 tag-subset sweep results (sub-project 4 items 1, 2, 4)"
```

---

### Task 6: ATR-based target/stop grid search (item 5)

**Files:**
- Create: `backtest/atr_stop_grid_search.py`
- Test: `backtest/tests/test_atr_stop_grid_search.py`

**Interfaces:**
- Consumes: `backtest.generate_signal_candidates.CachedCandidate` (existing),
  `backtest.simulate_exits.simulate_exit` (existing, unmodified),
  `backtest.toss_liveprice.apply_toss_liveprice` (existing, unmodified),
  `backtest.transaction_costs.apply_round_trip_cost` (existing, unmodified),
  `backtest.analyze_portfolio_return.simulate_portfolio` / `cagr_and_mdd` (existing, unmodified),
  `backtest.run_swing_v2_backtest._iso_week_key` / `apply_daily_selection` (existing, unmodified),
  `backtest.target_stop_grid_search.MIN_HIT_RATE` / `MIN_TRADES_PER_WEEK` (existing constants,
  imported not duplicated). Does **not** import `target_stop_grid_search._window_df` (a private
  helper) -- duplicates the small caching helper locally instead, to avoid a hidden dependency on
  another module's internal symbol.
- Produces: `run_one_atr_config(candidates, *, target_mult, stop_mult, atr_lookup, start, end) ->
  Dict`, `build_atr_grid() -> List[Dict]`, `select_best_atr_config(train_results) -> Dict`,
  `run_atr_grid_search(candidates, *, atr_lookup, train_start, train_end, test_start, test_end) ->
  Dict` — Task 7 consumes `run_atr_grid_search`.

- [ ] **Step 1: Write the failing tests**

Create `backtest/tests/test_atr_stop_grid_search.py`:

```python
from backtest.atr_stop_grid_search import (
    build_atr_grid,
    run_atr_grid_search,
    run_one_atr_config,
    select_best_atr_config,
)
from backtest.generate_signal_candidates import CachedCandidate


def _make_candidate(code, date, entry=100.0, hold_days=3, window=None):
    if window is None:
        window = {
            "open": [entry] * hold_days, "high": [entry] * hold_days,
            "low": [entry] * hold_days, "close": [entry] * hold_days,
        }
    return CachedCandidate(
        ticker=f"{code}.KS", code=code, date=date, entry=entry,
        pattern_type="E반등", score=110, rank_score=110, grade="매수",
        hold_days=hold_days,
        window_open=window["open"], window_high=window["high"],
        window_low=window["low"], window_close=window["close"],
    )


def test_atr_target_stop_value_pinned_hit_rate_and_pnl():
    day = "2024-01-02T00:00:00+00:00"
    # entry=100, atr_pct=0.02, target_mult=1.5 -> target=100*(1+1.5*0.02)=103
    # stop_mult=1.0 -> stop=100*(1-1*0.02)=98
    # window day0: high=104(>=103 target), low=99(>98 stop) -> hits target
    hit = _make_candidate(
        "000001", day, hold_days=3,
        window={
            "open": [100.0, 100.0, 100.0], "high": [104.0, 104.0, 104.0],
            "low": [99.0, 99.0, 99.0], "close": [103.5, 103.5, 103.5],
        },
    )
    atr_lookup = {("000001.KS", day): 0.02}
    result = run_one_atr_config(
        [hit], target_mult=1.5, stop_mult=1.0, atr_lookup=atr_lookup,
        start="2024-01-01", end="2024-01-08",  # exactly 7 days = 1.0 week
    )
    assert result["n_trades"] == 1
    assert result["hit_rate"] == 1.0
    assert result["trades_per_week"] == 1.0
    assert abs(result["avg_pnl"] - (0.03 - 0.002)) < 1e-9


def test_missing_atr_lookup_skips_candidate():
    day = "2024-01-02T00:00:00+00:00"
    c = _make_candidate("000001", day)
    result = run_one_atr_config(
        [c], target_mult=1.5, stop_mult=1.0, atr_lookup={},
        start="2024-01-01", end="2024-01-05",
    )
    assert result["n_trades"] == 0


def test_no_trades_returns_zeroed_result():
    result = run_one_atr_config(
        [], target_mult=1.5, stop_mult=1.0, atr_lookup={},
        start="2024-01-01", end="2024-01-08",
    )
    assert result["n_trades"] == 0
    assert result["hit_rate"] == 0.0
    assert result["trades_per_week"] == 0.0


def test_build_atr_grid_size():
    grid = build_atr_grid()
    assert len(grid) == 4 * 4  # target_mult x stop_mult == 16
    assert all(cell["target_mult"] >= 1.0 for cell in grid)


def test_select_best_atr_config_prefers_highest_cagr_among_qualifying():
    results = [
        {"target_mult": 1.0, "stop_mult": 0.5, "hit_rate": 0.92, "trades_per_week": 6,
         "cagr_15slot": 0.10, "avg_pnl": 0.01, "n_trades": 100},
        {"target_mult": 1.5, "stop_mult": 0.5, "hit_rate": 0.91, "trades_per_week": 6,
         "cagr_15slot": 0.20, "avg_pnl": 0.01, "n_trades": 100},
        {"target_mult": 3.0, "stop_mult": 2.0, "hit_rate": 0.85, "trades_per_week": 6,
         "cagr_15slot": 0.50, "avg_pnl": 0.01, "n_trades": 100},  # hit_rate < 0.90 -> excluded
    ]
    sel = select_best_atr_config(results)
    assert sel["status"] == "target_met"
    assert sel["config"]["target_mult"] == 1.5


def test_select_best_atr_config_fallback_when_none_qualify():
    results = [
        {"target_mult": 1.0, "stop_mult": 2.0, "hit_rate": 0.70, "trades_per_week": 6,
         "cagr_15slot": 0.05, "avg_pnl": 0.005, "n_trades": 100},
        {"target_mult": 2.0, "stop_mult": 1.0, "hit_rate": 0.80, "trades_per_week": 6,
         "cagr_15slot": 0.02, "avg_pnl": 0.004, "n_trades": 50},
        {"target_mult": 3.0, "stop_mult": 0.5, "hit_rate": 0.95, "trades_per_week": 2,
         "cagr_15slot": 0.30, "avg_pnl": 0.02, "n_trades": 10},  # fails freq floor
    ]
    sel = select_best_atr_config(results)
    assert sel["status"] == "target_not_met"
    assert sel["config"]["hit_rate"] == 0.80
    assert len(sel["fallback_top5"]) == 2
    assert sel["fallback_best_cagr"]["hit_rate"] == 0.95


def test_run_atr_grid_search_train_test_split():
    def make(code, date, entry=100.0):
        return CachedCandidate(
            ticker=f"{code}.KS", code=code, date=date, entry=entry,
            pattern_type="E반등", score=110, rank_score=110, grade="매수",
            hold_days=3,
            window_open=[entry, entry, entry], window_high=[entry * 1.05] * 3,
            window_low=[entry * 0.97] * 3, window_close=[entry] * 3,
        )

    train_day = "2024-06-30T00:00:00+00:00"
    test_day = "2024-07-01T00:00:00+00:00"
    train_c = make("000001", train_day)
    test_c = make("000002", test_day)
    atr_lookup = {("000001.KS", train_day): 0.02, ("000002.KS", test_day): 0.02}

    result = run_atr_grid_search(
        [train_c, test_c], atr_lookup=atr_lookup,
        train_start="2024-01-01", train_end="2024-06-30",
        test_start="2024-07-01", test_end="2024-12-31",
    )
    assert len(result["train_results"]) == 16
    assert result["test_result"]["n_trades"] in (0, 1)
    assert "selection" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_atr_stop_grid_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.atr_stop_grid_search'`

- [ ] **Step 3: Implement `backtest/atr_stop_grid_search.py`**

```python
"""
Sub-project 4 (Phase C) Stage 3: item 5, an ATR-based/volatility-adjusted target and stop in
place of target_stop_grid_search.py's flat target_pct/stop_pct -- that file stays unmodified
(off-limits per every prior sub-project's design docs). Reuses the same TOSS-LIVEPRICE,
exit-simulation, transaction-cost, and portfolio-CAGR primitives, replacing only how
target/stop are derived from entry. See
docs/superpowers/specs/2026-08-01-swing-algo-oversold-bounce-hitrate-design.md.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd

from .analyze_portfolio_return import cagr_and_mdd, simulate_portfolio
from .generate_signal_candidates import CachedCandidate
from .run_swing_v2_backtest import _iso_week_key, apply_daily_selection
from .simulate_exits import simulate_exit
from .target_stop_grid_search import MIN_HIT_RATE, MIN_TRADES_PER_WEEK
from .toss_liveprice import apply_toss_liveprice
from .transaction_costs import apply_round_trip_cost


def _window_df(c: CachedCandidate) -> pd.DataFrame:
    """Lazily builds and caches the small per-candidate OHLC DataFrame simulate_exit needs.
    A local duplicate of target_stop_grid_search.py's identical private helper -- kept
    separate rather than imported, since that file's leading-underscore helpers are not
    meant to be a cross-module interface."""
    cached = getattr(c, "_atr_window_df_cache", None)
    if cached is None:
        cached = pd.DataFrame({
            "open": c.window_open, "high": c.window_high,
            "low": c.window_low, "close": c.window_close,
        })
        c._atr_window_df_cache = cached
    return cached


def run_one_atr_config(
    candidates: List[CachedCandidate],
    *,
    target_mult: float,
    stop_mult: float,
    atr_lookup: Dict[Tuple[str, str], float],
    start: str,
    end: str,
) -> Dict[str, Any]:
    start_ts = pd.to_datetime(start, utc=True)
    end_ts = pd.to_datetime(end, utc=True)
    weeks = max((end_ts - start_ts).days / 7.0, 1e-9)

    by_day: Dict[pd.Timestamp, List[CachedCandidate]] = {}
    for c in candidates:
        by_day.setdefault(pd.Timestamp(c.date), []).append(c)

    week_state: Dict[str, Any] = {"key": None, "count": 0, "codes": set()}
    trades: List[Dict[str, Any]] = []
    for day in sorted(by_day.keys()):
        week_key = _iso_week_key(day)
        if week_key != week_state["key"]:
            week_state = {"key": week_key, "count": 0, "codes": set()}

        filtered = [(c.code, c) for c in by_day[day]]
        selected = apply_daily_selection(filtered, week_state)
        for code, c in selected:
            atr_pct = atr_lookup.get((c.ticker, c.date))
            if atr_pct is None:
                continue
            new_target = c.entry * (1 + target_mult * atr_pct)
            new_stop = c.entry * (1 - stop_mult * atr_pct)
            next_day_open = c.window_open[0] if c.window_open else c.entry
            toss = apply_toss_liveprice(c.entry, new_target, new_stop, next_day_open)
            if toss.status in ("blocked_chasing", "blocked_stopped_out"):
                continue
            df = _window_df(c)
            if df.empty:
                continue
            sim = simulate_exit(
                df, 0, entry=toss.entry, stop=toss.stop, target=toss.target, hold_days=c.hold_days,
            )
            gross_pnl = (float(sim["exit_price"]) - toss.entry) / toss.entry
            pnl = apply_round_trip_cost(gross_pnl)
            trades.append({
                "date": c.date, "ticker": c.ticker, "code": code,
                "pnl": pnl, "result": sim["result"],
            })

    n_trades = len(trades)
    base = {"target_mult": target_mult, "stop_mult": stop_mult}
    if n_trades == 0:
        return {
            **base, "n_trades": 0, "hit_rate": 0.0, "trades_per_week": 0.0,
            "avg_pnl": 0.0, "cagr_15slot": float("nan"), "mdd_15slot": 0.0,
        }

    hit_rate = sum(1 for t in trades if t["result"] == "target") / n_trades
    avg_pnl = sum(t["pnl"] for t in trades) / n_trades
    trades_sorted = sorted(trades, key=lambda t: (t["date"], t["ticker"]))
    curve = simulate_portfolio(trades_sorted, 15)
    _, mdd, _, cagr = cagr_and_mdd(curve, trades_sorted[0]["date"], trades_sorted[-1]["date"])

    return {
        **base, "n_trades": n_trades, "hit_rate": hit_rate,
        "trades_per_week": n_trades / weeks, "avg_pnl": avg_pnl,
        "cagr_15slot": cagr, "mdd_15slot": mdd,
    }


GRID_TARGET_MULT = [1.0, 1.5, 2.0, 3.0]
GRID_STOP_MULT = [0.5, 1.0, 1.5, 2.0]


def build_atr_grid() -> List[Dict[str, float]]:
    return [
        {"target_mult": tm, "stop_mult": sm}
        for tm in GRID_TARGET_MULT
        for sm in GRID_STOP_MULT
    ]


def select_best_atr_config(train_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    qualifying = [
        r for r in train_results
        if r["hit_rate"] >= MIN_HIT_RATE and r["trades_per_week"] >= MIN_TRADES_PER_WEEK
    ]
    if qualifying:
        best = max(qualifying, key=lambda r: r["cagr_15slot"])
        return {"status": "target_met", "config": best, "fallback_top5": [], "fallback_best_cagr": None}

    freq_ok = [r for r in train_results if r["trades_per_week"] >= MIN_TRADES_PER_WEEK]
    fallback_sorted = sorted(freq_ok, key=lambda r: (r["hit_rate"], r["cagr_15slot"]), reverse=True)
    best_cagr_overall = max(train_results, key=lambda r: r["cagr_15slot"]) if train_results else None
    chosen = fallback_sorted[0] if fallback_sorted else best_cagr_overall
    return {
        "status": "target_not_met",
        "config": chosen,
        "fallback_top5": fallback_sorted[:5],
        "fallback_best_cagr": best_cagr_overall,
    }


def run_atr_grid_search(
    candidates: List[CachedCandidate],
    *,
    atr_lookup: Dict[Tuple[str, str], float],
    train_start: str,
    train_end: str,
    test_start: str,
    test_end: str,
) -> Dict[str, Any]:
    train_start_ts = pd.to_datetime(train_start, utc=True)
    train_end_ts = pd.to_datetime(train_end, utc=True)
    test_start_ts = pd.to_datetime(test_start, utc=True)
    test_end_ts = pd.to_datetime(test_end, utc=True)
    train_candidates = [c for c in candidates if train_start_ts <= pd.Timestamp(c.date) <= train_end_ts]
    test_candidates = [c for c in candidates if test_start_ts <= pd.Timestamp(c.date) <= test_end_ts]

    grid = build_atr_grid()
    train_results = [
        run_one_atr_config(
            train_candidates, atr_lookup=atr_lookup, start=train_start, end=train_end, **cell
        )
        for cell in grid
    ]
    selection = select_best_atr_config(train_results)
    chosen = selection["config"]
    test_result = run_one_atr_config(
        test_candidates, atr_lookup=atr_lookup, start=test_start, end=test_end,
        target_mult=chosen["target_mult"], stop_mult=chosen["stop_mult"],
    )
    return {"train_results": train_results, "selection": selection, "test_result": test_result}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_atr_stop_grid_search.py -v`
Expected: all pass (7 tests)

- [ ] **Step 5: Run the full test suite (regression gate)**

Run: `python -m pytest backtest/tests -v`
Expected: all pass (130 before this task + 7 new = 137)

- [ ] **Step 6: Commit**

```bash
git add backtest/atr_stop_grid_search.py backtest/tests/test_atr_stop_grid_search.py
git commit -m "feat(backtest): ATR-based target/stop grid search for oversold-bounce (sub-project 4 item 5)"
```

---

### Task 7: Run the ATR grid search

**Files:** none created except the output JSON — this is an execution-only task.

- [ ] **Step 1: Decide which Stage 2 pool to apply item 5 to**

Read `backtest_oversold_v3_tagsweep_results.json` and `backtest_oversold_v3_none_results.json`
(both from Task 5). Pick whichever of the 8 (7 tagged + untagged) pools has the **largest test
`n_trades`** while still being a genuine Stage 2 output (this maximizes the chance of clearing the
`n_trades >= 50` reliability bar for item 5's own grid search, and is the most defensible,
least-cherry-picked selection rule available). If multiple pools tie on test `n_trades`, prefer
the untagged (∅) pool, since it carries the fewest additional free parameters. Record which pool
was chosen and why in the analysis document (Task 8) — this choice is itself a reported decision,
not a hidden implementation detail.

- [ ] **Step 2: Run the ATR grid search on the chosen pool**

```bash
python -c "
import json
from backtest.generate_signal_candidates import CachedCandidate
from backtest.atr_stop_grid_search import run_atr_grid_search

d = json.load(open('backtest_oversold_candidates_v3.json', encoding='utf-8'))
all_candidates = {(c['ticker'], c['date']): CachedCandidate(**c) for c in d['candidates']}

raw_atr = json.load(open('backtest_oversold_v3_atr_lookup.json', encoding='utf-8'))
atr_lookup = {tuple(k.split('|', 1)): v for k, v in raw_atr.items()}

# CHOSEN_TAGS: set this to [] for the untagged pool, or e.g. ['volume_confirm'] for a tagged
# pool, per Step 1's decision. If a tagged pool was chosen, also filter candidates by
# backtest_oversold_v3_tags.json the same way target_stop_grid_search.run_one_config does.
CHOSEN_TAGS = []
if CHOSEN_TAGS:
    raw_tags = json.load(open('backtest_oversold_v3_tags.json', encoding='utf-8'))
    tags_lookup = {tuple(k.split('|', 1)): v for k, v in raw_tags.items()}
    candidates = [
        c for (tk, dt), c in all_candidates.items()
        if all(tags_lookup.get((tk, dt), {}).get(tag, False) for tag in CHOSEN_TAGS)
    ]
else:
    candidates = list(all_candidates.values())

result = run_atr_grid_search(
    candidates, atr_lookup=atr_lookup,
    train_start='2022-01-01', train_end='2024-06-30',
    test_start='2024-07-01', test_end='2026-01-01',
)
json.dump(result, open('backtest_oversold_atr_grid_results.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('status:', result['selection']['status'])
print('train n_trades:', result['selection']['config']['n_trades'] if result['selection']['config'] else None)
print('test n_trades:', result['test_result']['n_trades'], 'test hit_rate:', result['test_result']['hit_rate'])
"
```

Before running, edit the `CHOSEN_TAGS` line in the command above to match Step 1's decision.
Expected: no exception. Record the resulting `n_trades`/`hit_rate`/`cagr_15slot` for train and
test honestly in Task 8, regardless of whether the reliability or decision-gate bars are cleared.

- [ ] **Step 3: Commit the ATR grid search results**

```bash
git add backtest_oversold_atr_grid_results.json
git commit -m "data(backtest): ATR-based target/stop grid search results for oversold-bounce (sub-project 4 item 5)"
```

---

### Task 8: Write the results analysis document

**Files:**
- Create: `docs/03-analysis/swing-algo-oversold-bounce-hitrate.analysis.md`

- [ ] **Step 1: Assemble the honest, stage-by-stage summary**

Using the real numbers from `backtest_oversold_candidates_v2.json` (Phase B baseline),
`backtest_oversold_candidates_v3.json` (Task 2), `backtest_oversold_v3_none_results.json` and
`backtest_oversold_v3_tagsweep_results.json` (Task 5), and `backtest_oversold_atr_grid_results.json`
(Task 7), write `docs/03-analysis/swing-algo-oversold-bounce-hitrate.analysis.md` with these
sections (no bracket placeholders left in the committed file — every number must be the actual
value read from these JSON files):

- **Header** matching the convention of `docs/03-analysis/swing-algo-oversold-bounce.analysis.md`
  (Analysis Type, Project, Feature, Design Doc / Implementation Plan links, Prior work, Date).
- **Method summary**: restate the 5 items and the 3→1,2,4→5 execution-order rationale, linking to
  the design doc rather than re-deriving it.
- **Stage 1 result (item 3)**: v2 (127 candidates) vs. v3 candidate count — report the raw count
  change plainly (expected to shrink, per the design doc's explicit expectation), and, run the v3
  pool with no tags through `run_grid_search` (this is exactly
  `backtest_oversold_v3_none_results.json`) to give a train/test table in the same format as
  Phase B's Section 2, so Stage 1's effect in isolation is visible before any tags are layered on.
- **Stage 2 result (items 1, 2, 4)**: a table of all 8 pools (∅ + 7 tag subsets) — each row
  showing train and test `hit_rate`, `trades_per_week`, `avg_pnl`, `cagr_15slot`, `n_trades`, and
  an explicit **reliable/unreliable** (`n_trades >= 50`) column for both splits. Any subset with
  `n_trades < 50` on either split must be labeled unreliable regardless of how good its hit_rate
  looks — same rule as Phase A/B.
- **Stage 3 result (item 5)**: which pool was chosen (per Task 7 Step 1) and why, then the 16-cell
  ATR grid's selected train config and test result, same table format.
- **Decision-gate verdict**: state plainly whether **any reliable** result across all of Stage
  1/2/3 reaches `hit_rate >= 90%`, `trades_per_week >= 5`, and `cagr_15slot > 0` **on both train
  and test**. If yes: recommend that specific stage/subset/config explicitly. If no (the likely
  outcome given Phase B's baseline and the sample-size trajectory): use the same three-way
  framework as Phase B (target-met / target-not-met-but-reliable / underpowered) rather than
  collapsing to a single verdict, and be explicit about which stages were underpowered vs.
  genuinely target-not-met.
- **Limitations**: restate the design doc's Section 7 limitations (parameter proliferation, the
  40-day/±3%/1.5-rvol/ATR-grid values being first-cut judgment calls not swept, persistent
  sample-size risk) rather than re-deriving them; note whether the sample-size risk materialized
  as anticipated.
- **Next step recommendation**: given the actual results, state plainly whether this line of the
  E반등 hypothesis (with all 5 levers applied) should be considered complete (regardless of
  whether the joint bar was cleared), or whether a further, explicitly-labeled follow-up is
  warranted — do not leave this open-ended without a concrete recommendation.

No production code (`src/swing-scanner.src.js`) has been changed by this sub-project — as with
every prior sub-project, that remains a separate, later decision, and the document must state this
explicitly.

- [ ] **Step 2: Commit the analysis document**

```bash
git add docs/03-analysis/swing-algo-oversold-bounce-hitrate.analysis.md
git commit -m "docs: results analysis for swing algo sub-project 4 (oversold-bounce hit-rate levers 1-5)"
```

---

## Self-Review Notes

- **Spec coverage**: Task 1-2 cover item 3 (Stage 1, design doc §Architecture Stage 1). Task 3-5
  cover items 1/2/4 (Stage 2). Task 6-7 cover item 5 (Stage 3). Task 8 covers the design doc's
  data-flow endpoint and limitations section. All 5 items and all 3 stages from the design doc
  have a task.
- **Placeholder scan**: no TBD/TODO; Task 7's `CHOSEN_TAGS` is a real decision point resolved by
  Task 7 Step 1's stated rule (largest test `n_trades`, tie-break to the untagged pool), not an
  unresolved placeholder — the plan states exactly how to fill it in, not "decide later".
  Task 8's Executive-Summary-style sections require real numbers, explicitly disallowing bracket
  placeholders.
- **Type consistency**: `tag_candidates_oversold`'s returned dict keys (`volume_confirm`,
  `sector_strong`, `support_confluence`) match exactly across Task 3's implementation, Task 3's
  tests, Task 4's execution script, and Task 5's `TAG_NAMES` list. `run_one_atr_config`/
  `build_atr_grid`/`select_best_atr_config`/`run_atr_grid_search`'s signatures match between Task
  6's implementation, its tests, and Task 7's execution script (`target_mult`, `stop_mult`,
  `atr_lookup` used consistently throughout). `CachedCandidate`'s field names (`ticker`, `code`,
  `date`, `entry`, `pattern_type`, `score`, `rank_score`, `grade`, `hold_days`, `window_open`,
  `window_high`, `window_low`, `window_close`) are used identically to `generate_signal_candidates.py`
  and every prior sub-project's usage.

# Swing Algorithm New Signal Filters (Sub-project 3 Phase A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether three additive signals — weekly-trend alignment, sector relative
strength, and volatility contraction — can isolate a profitable, ≥90%-hit-rate, ≥5/week subset
from the existing (unmodified) candidate pool, before considering a new candidate-generation
engine.

**Architecture:** Two new modules (`backtest/krx_sector_snapshot.py` for a one-time sector
classification fetch, `backtest/candidate_signals.py` for the three tag-computation functions)
plus a minimal, additive extension to `backtest/target_stop_grid_search.py` (an optional tag
filter, defaulting to sub-project 2's exact existing behavior). The existing 432-cell grid is then
re-run once per each of 8 tag subsets against the already-cached 21,587 candidates.

**Tech Stack:** Python 3.11, pandas, numpy, requests, pytest (all already used in `backtest/`). No
new dependencies.

## Global Constraints

- Do not modify `backtest/swing_signal_engine.py`, `backtest/toss_liveprice.py`,
  `backtest/simulate_exits.py`, `backtest/transaction_costs.py`,
  `backtest/market_regime_history.py`, `backtest/analyze_portfolio_return.py`,
  `backtest/generate_signal_candidates.py`, or `backtest/run_swing_v2_backtest.py`'s existing
  functions (only `target_stop_grid_search.py` is modified, additively) — all already-reviewed and
  reused as-is.
- `run_one_config`/`run_grid_search`'s new `required_tags`/`tags_lookup` parameters MUST default
  to `frozenset()`/`None` and reproduce sub-project 2's existing behavior byte-for-byte in that
  case — verified by re-running sub-project 2's existing 10 tests unchanged (regression gate).
- Trend alignment: weekly close vs. a **10-week** weekly SMA (not week-over-week close
  comparison — too noisy, rejected during design review).
- Volatility contraction: ATR/price percentile computed over `idx-60..idx-10`, **excluding the
  most recent 10 bars** (the trigger-event window) — including them would contradict the existing
  A/C/D patterns' own "event already fired" definition.
- Sector strength: a sector's trailing-20-day return is only used if **≥5 tickers** in the cached
  universe belong to it; below that, the signal is `False` (fail-closed), never "unknown defaults
  to True."
- All three tag functions must use only data available as of the close of day `idx` (the
  candidate's signal day) — no use of `entry_idx` (`idx+1`) or later. No lookahead.
- Sector classification is a **single static snapshot** (one KRX fetch, applied across the whole
  2022-2026 window) — not point-in-time history. Document this as a limitation.
- When reporting results (Task 9), any tag subset's selected/qualifying configuration with train
  `n_trades < 50` must be flagged as **statistically unreliable regardless of its hit_rate** and
  excluded from any "target met" claim.
- Every numeric/logic piece ships with a value-pinning unit test — no test that only asserts "runs
  without error."
- No changes to `src/swing-scanner.src.js` in this plan.

---

## File Structure Overview

| File | Status | Responsibility |
|---|---|---|
| `backtest/krx_sector_snapshot.py` | Create | One-time KRX sector-classification snapshot fetch |
| `backtest/candidate_signals.py` | Create | Trend/volatility/sector tag computation + orchestration |
| `backtest/target_stop_grid_search.py` | Modify | Add optional `required_tags`/`tags_lookup` filter |
| `backtest_sector_map.json` | Create (data) | Phase A output — code → sector_code snapshot |
| `backtest_candidate_tags.json` | Create (data) | Phase A output — `(ticker,date)` → `{tag: bool}` |
| `backtest_signal_filter_results.json` | Create (data) | 8-subset grid search results |
| `docs/03-analysis/swing-algo-new-signal-filters.analysis.md` | Create | Results write-up + decision gate |

---

### Task 1: KRX sector-classification snapshot

**Files:**
- Create: `backtest/krx_sector_snapshot.py`
- Test: `backtest/tests/test_krx_sector_snapshot.py`

**Interfaces:**
- Produces: `fetch_sector_snapshot(trd_dd: str, *, cache_dir: Path = Path("backtest/cache/krx_sector"), min_sleep_s: float = 0.2) -> Dict[str, str]` (stock code → 6-char sector code). Consumed by Task 5 (`tag_candidates`) and Task 7 (real run).

- [ ] **Step 1: Write the failing tests**

Create `backtest/tests/test_krx_sector_snapshot.py`:

```python
import json

from backtest.krx_sector_snapshot import fetch_sector_snapshot


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_sector_snapshot_parses_code_and_truncates_sector_to_6_chars(monkeypatch, tmp_path):
    payload = {
        "output": [
            {"ISU_SRT_CD": "000001", "IDX_IND_NM": "ABCDEFGHIJ"},
            {"ISU_SRT_CD": "000002", "SECT_TP_NM": "XYZW12"},
            {"ISU_SRT_CD": "", "IDX_IND_NM": "IGNORED_NO_CODE"},
        ]
    }
    monkeypatch.setattr(
        "backtest.krx_sector_snapshot.requests.post",
        lambda *a, **k: _FakeResp(payload),
    )
    result = fetch_sector_snapshot("20240102", cache_dir=tmp_path, min_sleep_s=0)
    assert result == {"000001": "ABCDEF", "000002": "XYZW12"}


def test_fetch_sector_snapshot_returns_empty_dict_on_request_failure(monkeypatch, tmp_path):
    def raise_error(*a, **k):
        raise Exception("boom")

    monkeypatch.setattr("backtest.krx_sector_snapshot.requests.post", raise_error)
    result = fetch_sector_snapshot("20240102", cache_dir=tmp_path, min_sleep_s=0)
    assert result == {}


def test_fetch_sector_snapshot_uses_disk_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "20240102.json"
    cache_path.write_text(json.dumps({"000009": "CACHED"}), encoding="utf-8")

    def fail_if_called(*a, **k):
        raise AssertionError("should not hit network when cache exists")

    monkeypatch.setattr("backtest.krx_sector_snapshot.requests.post", fail_if_called)
    result = fetch_sector_snapshot("20240102", cache_dir=tmp_path, min_sleep_s=0)
    assert result == {"000009": "CACHED"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_krx_sector_snapshot.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.krx_sector_snapshot'`

- [ ] **Step 3: Implement**

Create `backtest/krx_sector_snapshot.py`:

```python
"""
One-time KRX stock-code -> sector-classification snapshot, used by
backtest/candidate_signals.py's sector-relative-strength signal. Mirrors
backtest/krx_supply_history.py's request/cache/error-handling style exactly, and mirrors the
sector-code parsing already dead-code in production (src/swing-scanner.src.js:1017-1019:
`IDX_IND_NM || SECT_TP_NM`, first 6 characters).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict

import requests

_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://data.krx.co.kr",
    "Referer": "https://data.krx.co.kr/",
    "User-Agent": "Mozilla/5.0",
}


def fetch_sector_snapshot(
    trd_dd: str,
    *,
    cache_dir: Path = Path("backtest/cache/krx_sector"),
    min_sleep_s: float = 0.2,
) -> Dict[str, str]:
    """Stock code -> 6-char sector code, for one KRX trading day (market-wide, 1 call)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{trd_dd}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass

    try:
        body = f"bld=dbms/MDC/STAT/standard/MDCSTAT01501&mktId=ALL&trdDd={trd_dd}&share=1&money=1&csvxls_isNo=false"
        resp = requests.post(_URL, headers=_HEADERS, data=body, timeout=20)
        resp.raise_for_status()
        resp_data = resp.json() or {}
        rows = resp_data.get("output")
        if rows is None:
            rows = resp_data.get("OutBlock_1")
        if rows is None:
            rows = []

        result: Dict[str, str] = {}
        for row in rows:
            code = str(row.get("ISU_SRT_CD") or "").strip()
            if not code:
                continue
            sector = str(row.get("IDX_IND_NM") or row.get("SECT_TP_NM") or "").strip()[:6]
            if sector:
                result[code] = sector

        try:
            cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        if min_sleep_s > 0:
            time.sleep(min_sleep_s)
        return result
    except Exception:
        return {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_krx_sector_snapshot.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/krx_sector_snapshot.py backtest/tests/test_krx_sector_snapshot.py
git commit -m "feat(backtest): KRX sector-classification snapshot for sector-strength signal"
```

---

### Task 2: `candidate_signals.py` — weekly-trend alignment

**Files:**
- Create: `backtest/candidate_signals.py`
- Test: `backtest/tests/test_candidate_signals.py`

**Interfaces:**
- Consumes: `_iso_week_key` (`backtest/run_swing_v2_backtest.py`, unmodified).
- Produces: `compute_trend_alignment(df: pd.DataFrame, idx: int, *, weeks: int = 10) -> bool`.
  Consumed by Task 5 (`tag_candidates`).

- [ ] **Step 1: Write the failing tests**

Create `backtest/tests/test_candidate_signals.py`:

```python
import pandas as pd

from backtest.candidate_signals import compute_trend_alignment


def _ohlcv_df(dates, opens, highs, lows, closes):
    return pd.DataFrame({
        "timestamp_utc": dates,
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": [1_000_000.0] * len(closes),
    })


def _flat_ohlcv_df(dates, closes):
    return _ohlcv_df(dates, closes, closes, closes, closes)


def test_trend_alignment_true_for_steady_uptrend():
    dates = pd.bdate_range("2024-01-01", periods=65, tz="UTC")  # 13 weeks of business days
    closes = [100.0 + i for i in range(65)]
    df = _flat_ohlcv_df(dates, closes)
    assert compute_trend_alignment(df, len(df) - 1) is True


def test_trend_alignment_false_for_steady_downtrend():
    dates = pd.bdate_range("2024-01-01", periods=65, tz="UTC")
    closes = [200.0 - i for i in range(65)]
    df = _flat_ohlcv_df(dates, closes)
    assert compute_trend_alignment(df, len(df) - 1) is False


def test_trend_alignment_false_with_fewer_than_10_completed_weeks():
    dates = pd.bdate_range("2024-01-01", periods=20, tz="UTC")  # only 4 weeks of business days
    closes = [100.0 + i for i in range(20)]
    df = _flat_ohlcv_df(dates, closes)
    assert compute_trend_alignment(df, len(df) - 1) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_candidate_signals.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.candidate_signals'`

- [ ] **Step 3: Implement**

Create `backtest/candidate_signals.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_candidate_signals.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/candidate_signals.py backtest/tests/test_candidate_signals.py
git commit -m "feat(backtest): weekly-trend-alignment signal (10-week SMA)"
```

---

### Task 3: `candidate_signals.py` — volatility contraction

**Files:**
- Modify: `backtest/candidate_signals.py`
- Test: `backtest/tests/test_candidate_signals.py`

**Interfaces:**
- Consumes: `atr` (`backtest/indicators.py`, unmodified).
- Produces: `compute_vol_contraction(df: pd.DataFrame, idx: int, *, lookback: int = 60, exclude_recent: int = 10, percentile: float = 0.2) -> bool`. Consumed by Task 5.

- [ ] **Step 1: Write the failing tests**

Add to `backtest/tests/test_candidate_signals.py`:

```python
from backtest.candidate_signals import compute_vol_contraction


def test_vol_contraction_true_when_tight_before_an_excluded_recent_breakout():
    dates = pd.bdate_range("2024-01-01", periods=80, tz="UTC")
    closes = [100.0] * 80
    # Tight range (high-low = 1.0) for bars 0..69 (covers the idx-60..idx-10 window);
    # a sharp breakout range (20.0) for the excluded most-recent 10 bars (70..79).
    highs = [100.5] * 70 + [110.0] * 10
    lows = [99.5] * 70 + [90.0] * 10
    df = _ohlcv_df(dates, closes, highs, lows, closes)
    assert compute_vol_contraction(df, len(df) - 1) is True


def test_vol_contraction_false_when_range_expands_into_the_pre_event_window():
    dates = pd.bdate_range("2024-01-01", periods=80, tz="UTC")
    closes = [100.0] * 80
    # Range grows monotonically across the whole series, including inside the pre-event
    # window itself -- the most recent pre-event point is near the window's max, not its
    # bottom 20th percentile.
    highs = [100.0 + 0.15 * i for i in range(80)]
    lows = [100.0 - 0.15 * i for i in range(80)]
    df = _ohlcv_df(dates, closes, highs, lows, closes)
    assert compute_vol_contraction(df, len(df) - 1) is False


def test_vol_contraction_false_with_insufficient_history():
    dates = pd.bdate_range("2024-01-01", periods=25, tz="UTC")
    closes = [100.0] * 25
    df = _flat_ohlcv_df(dates, closes)
    assert compute_vol_contraction(df, len(df) - 1) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_candidate_signals.py -v -k vol_contraction`
Expected: FAIL with `ImportError` (`compute_vol_contraction` not defined yet)

- [ ] **Step 3: Implement**

Append to `backtest/candidate_signals.py` (add `from .indicators import atr as calc_atr` to the
existing import block at the top of the file):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_candidate_signals.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/candidate_signals.py backtest/tests/test_candidate_signals.py
git commit -m "feat(backtest): pre-event volatility-contraction signal"
```

---

### Task 4: `candidate_signals.py` — sector relative strength

**Files:**
- Modify: `backtest/candidate_signals.py`
- Test: `backtest/tests/test_candidate_signals.py`

**Interfaces:**
- Produces: `build_sector_returns_by_date(sector_map: Dict[str,str], per_ticker_ohlcv: Dict[str, pd.DataFrame], *, lookback: int = 20, min_sector_size: int = 5) -> Dict[str, Dict[str, float]]`
  and `compute_sector_strength(sector_returns_by_date: Dict[str, Dict[str, float]], sector_map: Dict[str,str], code: str, date_key: str, *, top_frac: float = 0.3) -> bool`. Both consumed by
  Task 5.

- [ ] **Step 1: Write the failing tests**

Add to `backtest/tests/test_candidate_signals.py`:

```python
from backtest.candidate_signals import build_sector_returns_by_date, compute_sector_strength


def test_build_sector_returns_by_date_requires_min_sector_size():
    dates = pd.bdate_range("2024-01-01", periods=25, tz="UTC")
    date_strs = list(dates)

    sector_map = {}
    per_ticker_ohlcv = {}
    # Sector AAAAAA: 5 tickers, all flat then +10% in the last 5 bars -> qualifies.
    for i in range(5):
        code = f"AAA{i}"
        closes = [100.0] * 20 + [110.0] * 5
        per_ticker_ohlcv[f"{code}.KS"] = _flat_ohlcv_df(date_strs, closes)
        sector_map[code] = "AAAAAA"
    # Sector ZZZZZZ: only 2 tickers -> below min_sector_size, must not appear.
    for i in range(2):
        code = f"ZZZ{i}"
        closes = [100.0] * 20 + [90.0] * 5
        per_ticker_ohlcv[f"{code}.KS"] = _flat_ohlcv_df(date_strs, closes)
        sector_map[code] = "ZZZZZZ"

    result = build_sector_returns_by_date(sector_map, per_ticker_ohlcv, lookback=20, min_sector_size=5)
    last_date_key = dates[-1].date().isoformat()
    assert "AAAAAA" in result[last_date_key]
    assert abs(result[last_date_key]["AAAAAA"] - 0.10) < 1e-9
    assert "ZZZZZZ" not in result[last_date_key]


def test_compute_sector_strength_ranks_against_other_sectors():
    sector_returns_by_date = {
        "2024-01-30": {
            "S1": 0.20, "S2": 0.15, "S3": 0.10, "S4": 0.05, "S5": 0.02,
            "S6": 0.00, "S7": -0.02, "S8": -0.05, "S9": -0.08, "S10": -0.10,
        }
    }
    sector_map = {"CODE_TOP": "S3", "CODE_MID": "S4"}
    assert compute_sector_strength(
        sector_returns_by_date, sector_map, "CODE_TOP", "2024-01-30", top_frac=0.3,
    ) is True
    assert compute_sector_strength(
        sector_returns_by_date, sector_map, "CODE_MID", "2024-01-30", top_frac=0.3,
    ) is False


def test_compute_sector_strength_false_when_unmapped_or_below_min_sample():
    assert compute_sector_strength({}, {}, "ANY_CODE", "2024-01-30") is False
    sector_returns_by_date = {"2024-01-30": {"S1": 0.20}}
    # CODE's sector ("S9") isn't present that date -- either unmapped upstream or filtered
    # out by build_sector_returns_by_date's min_sector_size gate.
    assert compute_sector_strength(sector_returns_by_date, {"CODE": "S9"}, "CODE", "2024-01-30") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_candidate_signals.py -v -k sector`
Expected: FAIL with `ImportError` (`build_sector_returns_by_date`/`compute_sector_strength` not defined yet)

- [ ] **Step 3: Implement**

Append to `backtest/candidate_signals.py`:

```python
def build_sector_returns_by_date(
    sector_map: Dict[str, str],
    per_ticker_ohlcv: Dict[str, pd.DataFrame],
    *,
    lookback: int = 20,
    min_sector_size: int = 5,
) -> Dict[str, Dict[str, float]]:
    """date (ISO string) -> {sector_code: equal-weighted trailing-lookback-day return}, including
    only sectors with >= min_sector_size tickers contributing a valid return that date."""
    by_date_sector: Dict[str, Dict[str, List[float]]] = {}
    for ticker, df in per_ticker_ohlcv.items():
        code = ticker[:-3] if ticker.endswith(".KS") or ticker.endswith(".KQ") else ticker
        sector = sector_map.get(code)
        if not sector:
            continue
        close = df["close"].astype(float)
        ret = close / close.shift(lookback) - 1.0
        for date_val, r in zip(df["timestamp_utc"], ret):
            if pd.isna(r):
                continue
            date_key = pd.Timestamp(date_val).date().isoformat()
            by_date_sector.setdefault(date_key, {}).setdefault(sector, []).append(float(r))

    result: Dict[str, Dict[str, float]] = {}
    for date_key, sectors in by_date_sector.items():
        qualifying = {
            sector: sum(vals) / len(vals)
            for sector, vals in sectors.items()
            if len(vals) >= min_sector_size
        }
        if qualifying:
            result[date_key] = qualifying
    return result


def compute_sector_strength(
    sector_returns_by_date: Dict[str, Dict[str, float]],
    sector_map: Dict[str, str],
    code: str,
    date_key: str,
    *,
    top_frac: float = 0.3,
) -> bool:
    """True if code's sector's trailing return ranks in the top top_frac of all sectors with
    enough sample size that date. Fails closed (False) if code is unmapped or its sector didn't
    meet build_sector_returns_by_date's minimum sample size that date."""
    sector = sector_map.get(code)
    if not sector:
        return False
    sectors_today = sector_returns_by_date.get(date_key)
    if not sectors_today or sector not in sectors_today:
        return False
    ranked = sorted(sectors_today.values(), reverse=True)
    cutoff_idx = max(0, int(len(ranked) * top_frac) - 1)
    threshold = ranked[cutoff_idx]
    return sectors_today[sector] >= threshold
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_candidate_signals.py -v`
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/candidate_signals.py backtest/tests/test_candidate_signals.py
git commit -m "feat(backtest): sector-relative-strength signal with minimum-sample gate"
```

---

### Task 5: `candidate_signals.py` — `tag_candidates` orchestrator

**Files:**
- Modify: `backtest/candidate_signals.py`
- Test: `backtest/tests/test_candidate_signals.py`

**Interfaces:**
- Consumes: `compute_trend_alignment`, `compute_vol_contraction`, `build_sector_returns_by_date`,
  `compute_sector_strength` (Tasks 2-4); `CachedCandidate` (`backtest/generate_signal_candidates.py`, unmodified).
- Produces: `tag_candidates(candidates: List[CachedCandidate], per_ticker_ohlcv: Dict[str, pd.DataFrame], sector_map: Dict[str,str]) -> Dict[Tuple[str,str], Dict[str,bool]]`. Consumed by Task 7 (real run).

- [ ] **Step 1: Write the failing test**

Add to `backtest/tests/test_candidate_signals.py`:

```python
from backtest.candidate_signals import tag_candidates
from backtest.generate_signal_candidates import CachedCandidate


def test_tag_candidates_keys_by_ticker_and_date_and_fails_closed_when_untradeable():
    dates = pd.bdate_range("2024-01-01", periods=65, tz="UTC")
    closes = [100.0 + i for i in range(65)]
    df = _flat_ohlcv_df(dates, closes)
    candidate_date = dates[-1].isoformat()

    candidate = CachedCandidate(
        ticker="000001.KS", code="000001", date=candidate_date, entry=164.0,
        pattern_type="C촉매", score=100, rank_score=100, grade="매수", hold_days=3,
        window_open=[164.0], window_high=[165.0], window_low=[163.0], window_close=[164.0],
    )
    missing_df_candidate = CachedCandidate(
        ticker="999999.KQ", code="999999", date=candidate_date, entry=100.0,
        pattern_type="C촉매", score=100, rank_score=100, grade="매수", hold_days=3,
        window_open=[100.0], window_high=[101.0], window_low=[99.0], window_close=[100.0],
    )

    tags = tag_candidates(
        [candidate, missing_df_candidate],
        per_ticker_ohlcv={"000001.KS": df},
        sector_map={},
    )

    assert set(tags[("000001.KS", candidate_date)].keys()) == {
        "trend_aligned", "vol_contraction", "sector_strong",
    }
    assert tags[("999999.KQ", candidate_date)] == {
        "trend_aligned": False, "vol_contraction": False, "sector_strong": False,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backtest/tests/test_candidate_signals.py -v -k tag_candidates`
Expected: FAIL with `ImportError` (`tag_candidates` not defined yet)

- [ ] **Step 3: Implement**

Append to `backtest/candidate_signals.py` (add
`from .generate_signal_candidates import CachedCandidate` to the existing import block):

```python
def tag_candidates(
    candidates: List[CachedCandidate],
    per_ticker_ohlcv: Dict[str, pd.DataFrame],
    sector_map: Dict[str, str],
) -> Dict[Tuple[str, str], Dict[str, bool]]:
    """(ticker, date) -> {trend_aligned, vol_contraction, sector_strong}. Fails closed (all False)
    for a candidate whose ticker/date can't be located in per_ticker_ohlcv, rather than raising --
    matches this codebase's existing fail-closed conventions (TOSS blocking, sector min-sample)."""
    sector_returns_by_date = build_sector_returns_by_date(sector_map, per_ticker_ohlcv)
    closed = {"trend_aligned": False, "vol_contraction": False, "sector_strong": False}

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
            "trend_aligned": compute_trend_alignment(df, idx),
            "vol_contraction": compute_vol_contraction(df, idx),
            "sector_strong": compute_sector_strength(sector_returns_by_date, sector_map, c.code, date_key),
        }
    return tags
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_candidate_signals.py -v`
Expected: `11 passed`

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest backtest/tests -v`
Expected: all tests pass (89 from prior sessions + 3 + 11 = 103 total; exact count isn't
load-bearing, zero failures is).

- [ ] **Step 6: Commit**

```bash
git add backtest/candidate_signals.py backtest/tests/test_candidate_signals.py
git commit -m "feat(backtest): tag_candidates orchestrator, fail-closed on missing data"
```

---

### Task 6: Extend `target_stop_grid_search.py` with an optional tag filter

**Files:**
- Modify: `backtest/target_stop_grid_search.py` (the `run_one_config` signature/body around
  the current lines 40-98, and the `run_grid_search` signature/body around the current lines
  169-199 — exact line numbers will have shifted after Tasks 1-5's edits to other files, but this
  file itself is unchanged until this task)
- Test: `backtest/tests/test_target_stop_grid_search.py`

**Interfaces:**
- Consumes: nothing new (same imports as today).
- Produces: `run_one_config(..., required_tags: FrozenSet[str] = frozenset(), tags_lookup: Optional[Dict[Tuple[str,str], Dict[str,bool]]] = None)` and `run_grid_search(..., required_tags: FrozenSet[str] = frozenset(), tags_lookup: Optional[Dict] = None)`, both passing the new
  parameters through unchanged in every other respect. Consumed by Task 8 (real run).

- [ ] **Step 1: Write the failing tests**

Add to `backtest/tests/test_target_stop_grid_search.py`:

```python
def test_required_tags_filters_out_untagged_candidates():
    day = "2024-01-02T00:00:00+00:00"
    tagged = _make_candidate("000001", day, score=95)
    untagged = _make_candidate("000002", day, score=95)
    tags_lookup = {
        ("000001.KS", day): {"trend_aligned": True},
        ("000002.KS", day): {"trend_aligned": False},
    }
    result = run_one_config(
        [tagged, untagged], target_pct=0.03, stop_pct=0.02, min_score=60,
        regime_gate=False, exclude_d_box=False, regime_lookup={},
        start="2024-01-01", end="2024-01-05",
        required_tags=frozenset({"trend_aligned"}), tags_lookup=tags_lookup,
    )
    assert result["n_trades"] == 1


def test_required_tags_empty_reproduces_unfiltered_behavior():
    day = "2024-01-02T00:00:00+00:00"
    a = _make_candidate("000001", day, score=95)
    b = _make_candidate("000002", day, score=95)
    result = run_one_config(
        [a, b], target_pct=0.03, stop_pct=0.02, min_score=60,
        regime_gate=False, exclude_d_box=False, regime_lookup={},
        start="2024-01-01", end="2024-01-05",
    )
    assert result["n_trades"] == 2


def test_run_grid_search_passes_required_tags_through():
    def make(code, date, score=100, entry=100.0):
        return CachedCandidate(
            ticker=f"{code}.KS", code=code, date=date, entry=entry,
            pattern_type="C촉매", score=score, rank_score=score, grade="매수",
            hold_days=3,
            window_open=[entry, entry, entry], window_high=[entry * 1.05] * 3,
            window_low=[entry * 0.97] * 3, window_close=[entry] * 3,
        )

    day = "2024-06-30T00:00:00+00:00"
    tagged = make("000001", day)
    untagged = make("000002", day)
    tags_lookup = {
        ("000001.KS", day): {"trend_aligned": True},
        ("000002.KS", day): {"trend_aligned": False},
    }
    result = run_grid_search(
        [tagged, untagged], regime_lookup={},
        train_start="2024-01-01", train_end="2024-06-30",
        test_start="2024-07-01", test_end="2024-12-31",
        required_tags=frozenset({"trend_aligned"}), tags_lookup=tags_lookup,
    )
    assert all(r["n_trades"] <= 1 for r in result["train_results"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_target_stop_grid_search.py -v -k required_tags`
Expected: FAIL with `TypeError: run_one_config() got an unexpected keyword argument 'required_tags'`

- [ ] **Step 3: Implement**

In `backtest/target_stop_grid_search.py`, change the typing import line from:

```python
from typing import Any, Dict, List
```

to:

```python
from typing import Any, Dict, FrozenSet, List, Optional, Tuple
```

Change the `run_one_config` signature from:

```python
def run_one_config(
    candidates: List[CachedCandidate],
    *,
    target_pct: float,
    stop_pct: float,
    min_score: int,
    regime_gate: bool,
    exclude_d_box: bool,
    regime_lookup: Dict[str, int],
    start: str,
    end: str,
) -> Dict[str, Any]:
```

to:

```python
def run_one_config(
    candidates: List[CachedCandidate],
    *,
    target_pct: float,
    stop_pct: float,
    min_score: int,
    regime_gate: bool,
    exclude_d_box: bool,
    regime_lookup: Dict[str, int],
    start: str,
    end: str,
    required_tags: FrozenSet[str] = frozenset(),
    tags_lookup: Optional[Dict[Tuple[str, str], Dict[str, bool]]] = None,
) -> Dict[str, Any]:
    tags_lookup = tags_lookup or {}
```

Change the per-day filter loop from:

```python
        filtered = []
        for c in by_day[day]:
            if c.score < min_score:
                continue
            if exclude_d_box and c.pattern_type == "D박스":
                continue
            if regime_gate:
                level = regime_lookup.get(day.date().isoformat(), 0)
                if level >= 2 and c.grade != "강매":
                    continue
            filtered.append((c.code, c))
```

to:

```python
        filtered = []
        for c in by_day[day]:
            if c.score < min_score:
                continue
            if exclude_d_box and c.pattern_type == "D박스":
                continue
            if regime_gate:
                level = regime_lookup.get(day.date().isoformat(), 0)
                if level >= 2 and c.grade != "강매":
                    continue
            if required_tags:
                candidate_tags = tags_lookup.get((c.ticker, c.date), {})
                if not all(candidate_tags.get(tag, False) for tag in required_tags):
                    continue
            filtered.append((c.code, c))
```

Change the `run_grid_search` signature from:

```python
def run_grid_search(
    candidates: List[CachedCandidate],
    *,
    regime_lookup: Dict[str, int],
    train_start: str,
    train_end: str,
    test_start: str,
    test_end: str,
) -> Dict[str, Any]:
```

to:

```python
def run_grid_search(
    candidates: List[CachedCandidate],
    *,
    regime_lookup: Dict[str, int],
    train_start: str,
    train_end: str,
    test_start: str,
    test_end: str,
    required_tags: FrozenSet[str] = frozenset(),
    tags_lookup: Optional[Dict[Tuple[str, str], Dict[str, bool]]] = None,
) -> Dict[str, Any]:
```

And change its body from:

```python
    grid = build_grid()
    train_results = [
        run_one_config(
            train_candidates, regime_lookup=regime_lookup, start=train_start, end=train_end, **cell
        )
        for cell in grid
    ]
    selection = select_best_config(train_results)
    chosen = selection["config"]
    test_result = run_one_config(
        test_candidates, regime_lookup=regime_lookup, start=test_start, end=test_end,
        target_pct=chosen["target_pct"], stop_pct=chosen["stop_pct"], min_score=chosen["min_score"],
        regime_gate=chosen["regime_gate"], exclude_d_box=chosen["exclude_d_box"],
    )
    return {"train_results": train_results, "selection": selection, "test_result": test_result}
```

to:

```python
    grid = build_grid()
    train_results = [
        run_one_config(
            train_candidates, regime_lookup=regime_lookup, start=train_start, end=train_end,
            required_tags=required_tags, tags_lookup=tags_lookup, **cell
        )
        for cell in grid
    ]
    selection = select_best_config(train_results)
    chosen = selection["config"]
    test_result = run_one_config(
        test_candidates, regime_lookup=regime_lookup, start=test_start, end=test_end,
        target_pct=chosen["target_pct"], stop_pct=chosen["stop_pct"], min_score=chosen["min_score"],
        regime_gate=chosen["regime_gate"], exclude_d_box=chosen["exclude_d_box"],
        required_tags=required_tags, tags_lookup=tags_lookup,
    )
    return {"train_results": train_results, "selection": selection, "test_result": test_result}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_target_stop_grid_search.py -v`
Expected: all tests pass (10 from sub-project 2 + 3 new = 13 total)

- [ ] **Step 5: Run the full test suite (regression gate)**

Run: `python -m pytest backtest/tests -v`
Expected: all tests pass (103 from Task 5 + 3 new = 106 total). Sub-project 2's original 10
`test_target_stop_grid_search.py` tests passing unchanged is the regression proof that
`required_tags=frozenset()` reproduces the old behavior exactly.

- [ ] **Step 6: Commit**

```bash
git add backtest/target_stop_grid_search.py backtest/tests/test_target_stop_grid_search.py
git commit -m "feat(backtest): optional tag filter for grid search, defaults preserve sub-project 2 behavior"
```

---

### Task 7: Run the sector snapshot + tag all cached candidates

**Files:** none created except the output JSONs — this is an execution-only task.

- [ ] **Step 1: Fetch the sector snapshot**

Run:
```bash
python -c "
import json
from backtest.krx_sector_snapshot import fetch_sector_snapshot

d = json.load(open('backtest_candidates_with_paths.json', encoding='utf-8'))
latest_date = max(c['date'] for c in d['candidates'])
trd_dd = latest_date[:10].replace('-', '')
sector_map = fetch_sector_snapshot(trd_dd)
json.dump(sector_map, open('backtest_sector_map.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('wrote backtest_sector_map.json:', len(sector_map), 'codes, snapshot date', trd_dd)
"
```
Expected: no exception; prints a code count in the low thousands (KRX's full listed universe,
not just our 959-ticker operating subset — `MDCSTAT01501` returns every listed name).

- [ ] **Step 2: Tag every cached candidate**

Run (re-reads all 955 already-fetched tickers from `yahoo_cache`'s disk cache — cache hits, no
new network fetch expected; low minutes):
```bash
python -c "
import json
from backtest.yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart
from backtest.generate_signal_candidates import CachedCandidate
from backtest.candidate_signals import tag_candidates

d = json.load(open('backtest_candidates_with_paths.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]
tickers = sorted({c.ticker for c in candidates})

per_ticker_ohlcv = {}
for t in tickers:
    data = fetch_yahoo_chart(YahooFetchSpec(ticker=t, range='5y', interval='1d'))
    df, _ = chart_to_ohlcv_daily(data)
    per_ticker_ohlcv[t] = df.sort_values('timestamp_utc').reset_index(drop=True)

sector_map = json.load(open('backtest_sector_map.json', encoding='utf-8'))
tags = tag_candidates(candidates, per_ticker_ohlcv, sector_map)

out = {f'{tk}|{dt}': v for (tk, dt), v in tags.items()}
json.dump(out, open('backtest_candidate_tags.json', 'w', encoding='utf-8'), ensure_ascii=False)

n = len(tags)
n_trend = sum(1 for v in tags.values() if v['trend_aligned'])
n_vol = sum(1 for v in tags.values() if v['vol_contraction'])
n_sector = sum(1 for v in tags.values() if v['sector_strong'])
print(f'tagged {n} candidates: trend_aligned={n_trend}, vol_contraction={n_vol}, sector_strong={n_sector}')
"
```
Expected: no exception; `tagged` count equals 21,587 (the full cached candidate count). Each of
`trend_aligned`/`vol_contraction`/`sector_strong` must be strictly between 0 and 21,587 (not
degenerate all-True or all-False) — if any one of the three is exactly 0 or exactly 21,587, stop
and investigate rather than proceeding (same discipline as sub-project 1/2's sanity checks; a
degenerate count means the signal isn't discriminating at all, most likely a bug).

- [ ] **Step 3: Commit the artifacts for reproducibility**

```bash
git add backtest_sector_map.json backtest_candidate_tags.json
git commit -m "data(backtest): KRX sector snapshot + trend/volatility/sector tags for all 21,587 cached candidates"
```

---

### Task 8: Run the 8-subset grid search

**Files:** none created except the output JSON — this is an execution-only task.

- [ ] **Step 1: Run all 8 tag subsets**

Run (the `∅` subset reuses sub-project 2's already-committed `backtest_grid_search_results.json`
directly rather than re-running its 432 cells; the other 7 each run the existing 432-cell grid —
expect low tens of minutes total, comparable to sub-project 2's single ~80-second run times 7):

```bash
python -c "
import itertools
import json

from backtest.generate_signal_candidates import CachedCandidate
from backtest.target_stop_grid_search import run_grid_search

d = json.load(open('backtest_candidates_with_paths.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]
regime_lookup = json.load(open('backtest_regime_lookup.json', encoding='utf-8'))
raw_tags = json.load(open('backtest_candidate_tags.json', encoding='utf-8'))
tags_lookup = {tuple(k.split('|', 1)): v for k, v in raw_tags.items()}
prior = json.load(open('backtest_grid_search_results.json', encoding='utf-8'))

TAG_NAMES = ['trend_aligned', 'vol_contraction', 'sector_strong']
subsets = []
for r in range(4):
    subsets.extend(itertools.combinations(TAG_NAMES, r))

results = {}
for subset in subsets:
    key = '+'.join(subset) if subset else 'none'
    if not subset:
        results[key] = {
            'tags': [], 'train_results': prior['train_results'],
            'selection': prior['selection'], 'test_result': prior['test_result'],
        }
        print(key, '(reused from sub-project 2): status', prior['selection']['status'])
        continue
    r = run_grid_search(
        candidates, regime_lookup=regime_lookup,
        train_start='2022-01-01', train_end='2024-06-30',
        test_start='2024-07-01', test_end='2026-01-01',
        required_tags=frozenset(subset), tags_lookup=tags_lookup,
    )
    results[key] = {'tags': list(subset), **r}
    print(key, 'status:', r['selection']['status'], 'test n_trades:', r['test_result']['n_trades'])

json.dump(results, open('backtest_signal_filter_results.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('wrote backtest_signal_filter_results.json:', len(results), 'subsets')
"
```

Expected: exactly 8 subsets printed and written (`none`, 3 singles, 3 pairs, 1 triple); no
exceptions; no NaN in any subset's selected-config or test-result `avg_pnl`/`cagr_15slot` unless
that subset genuinely produced 0 trades in that split (same rule as sub-project 1/2: a `nan` there
means stop and investigate, not proceed).

- [ ] **Step 2: Commit the raw result for reproducibility**

```bash
git add backtest_signal_filter_results.json
git commit -m "data(backtest): 8-subset (trend/sector/volatility) grid search results, train 2022-2024H1 / test 2024H2-2026"
```

---

### Task 9: Write the results analysis document

**Files:**
- Create: `docs/03-analysis/swing-algo-new-signal-filters.analysis.md`

- [ ] **Step 1: Summarize the 8-subset results**

Run:
```bash
python -c "
import json
d = json.load(open('backtest_signal_filter_results.json', encoding='utf-8'))
for key, r in d.items():
    sel = r['selection']
    cfg = sel['config']
    test = r['test_result']
    reliable = cfg['n_trades'] >= 50
    print(f\"{key}: status={sel['status']} train_hit_rate={cfg['hit_rate']:.4f} \"
          f\"train_n={cfg['n_trades']} train_cagr={cfg['cagr_15slot']:.4f} \"
          f\"test_hit_rate={test['hit_rate']:.4f} test_n={test['n_trades']} \"
          f\"test_cagr={test['cagr_15slot']:.4f} reliable(n>=50)={reliable}\")
"
```

- [ ] **Step 2: Write the analysis document**

Create `docs/03-analysis/swing-algo-new-signal-filters.analysis.md` with these sections, using the
real numbers from Step 1 (no bracket placeholders left in the committed file):

- **Header** matching the convention of `docs/03-analysis/swing-algo-target-stop-retuning.analysis.md`
  (Analysis Type, Project, Feature, Design Doc / Implementation Plan links, Date).
- **Method summary**: restate the 3 signals, the trader-review corrections applied to each
  (weekly-SMA trend, pre-event volatility window, min-sample sector gate), and the 8-subset x
  432-cell sweep, linking to the design doc rather than re-deriving it.
- **Per-subset train vs. test table**: all 8 subsets, each row showing `hit_rate`,
  `trades_per_week`, `avg_pnl`, `cagr_15slot` for train and test side by side, plus the train
  `n_trades` and an explicit **reliable / unreliable** column (`n_trades >= 50` per the plan's
  Global Constraints statistical-reliability rule). Any subset with `n_trades < 50` must be
  labeled unreliable in this table regardless of how good its hit_rate looks.
- **Decision-gate verdict**: state plainly whether **any reliable** subset reaches
  `hit_rate >= 90%`, `trades_per_week >= 5`, and `cagr_15slot > 0` **on both train and test**. If
  yes: recommend that subset+config explicitly, and state that sub-project 3 ends here (no Phase B
  needed). If no: report this as plainly as sub-project 2's conclusion, and explicitly recommend
  scoping **Phase B** (a new candidate-generation engine) as the next sub-project, per the design
  doc's roadmap — do not soften this conclusion or retroactively loosen the 90%/5-per-week/
  positive-return bar to manufacture a "success."
- **Best available subset regardless of the joint target**: if no subset meets the full joint bar,
  report which reliable subset came closest (highest test `hit_rate` among subsets with
  `trades_per_week >= 5` and `n_trades >= 50`), with its exact numbers, the same way sub-project
  2's analysis reported its best-available fallback.
- **Limitations**: carry forward from the design doc — static sector-classification snapshot,
  equal-weighted universe-limited sector returns, discrete tag-subset sweep (not a continuous
  search), and the added data-snooping exposure from testing 8 subsets x 432 cells against a
  single train/test split (mitigated, not eliminated, by the `n_trades >= 50` reliability rule).
- **Next step recommendation**: explicitly state that no production code
  (`src/swing-scanner.src.js`) has been changed, and that any further work (deployment, or scoping
  Phase B) is a separate decision pending the user's review of these results.

- [ ] **Step 3: Commit**

```bash
git add docs/03-analysis/swing-algo-new-signal-filters.analysis.md
git commit -m "docs: new-signal-filter (trend/sector/volatility) results for swing algo enhancement sub-project 3 Phase A"
```

---

## Self-Review Notes

- **Spec coverage:** every in-scope item from
  `docs/superpowers/specs/2026-07-28-swing-algo-new-signal-filters-design.md` maps to a task —
  sector snapshot (Task 1), trend/volatility/sector signals individually (Tasks 2-4), the tagging
  orchestrator (Task 5), the additive grid-search extension with its byte-identical-default
  regression requirement (Task 6), the two real runs (Tasks 7-8), and the decision-gate write-up
  (Task 9). All four trader-review revisions from the design doc (weekly-SMA metric, pre-event
  volatility window, min-sample sector gate, `n_trades >= 50` reliability rule) appear as explicit
  Global Constraints and are implemented in Tasks 2, 3, 4, and 9 respectively, not left as
  background context only.
- **Placeholder scan:** no task contains "TBD"/"TODO"/unfilled brackets; Task 9's document content
  is described precisely (which table, which columns, which verdict rule) without being filled in
  here, matching sub-project 1/2's Task 6 pattern (real values only exist after Tasks 7/8 run).
- **Type consistency:** `CachedCandidate` (Task 1 of sub-project 2, reused unmodified) is used
  identically across Tasks 5, 7, 8. `tag_candidates`'s return type
  (`Dict[Tuple[str,str], Dict[str,bool]]`, keys `(ticker, date)`) is used identically by Task 6's
  `tags_lookup` parameter and Task 7/8's JSON round-trip (`f'{tk}|{dt}'` / `k.split('|', 1)`,
  consistent both directions). The three tag names (`trend_aligned`, `vol_contraction`,
  `sector_strong`) are spelled identically in Tasks 2-5, 6's tests, and 7-9.
- **Global-constraint check:** the `required_tags=frozenset()` default-preserves-old-behavior
  requirement is directly tested (Task 6, `test_required_tags_empty_reproduces_unfiltered_behavior`)
  and additionally verified by the full-suite regression run in Task 6 Step 5. The
  `n_trades >= 50` reliability rule is stated in Global Constraints and again in Task 9's Step 2
  instructions, so an implementer reading only one section still sees it. The min-sector-size=5
  gate is enforced in `build_sector_returns_by_date` itself (Task 4), not left to the caller, and
  is verified by `test_build_sector_returns_by_date_requires_min_sector_size`.
- **Scope check:** single cohesive phase (additive filters over the existing candidate pool),
  matching the sub-project 3 Phase A boundary drawn during brainstorming. Phase B (new
  candidate-generation engine) is explicitly out of scope and conditional on this phase's result,
  to be scoped as a separate design if triggered.

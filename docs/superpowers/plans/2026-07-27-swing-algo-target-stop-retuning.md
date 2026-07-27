# Swing Algorithm Target/Stop & Threshold Retuning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-derive the swing algorithm's target price, stop-loss, minimum score, regime gate, and
D박스-pattern inclusion via a grid search with a chronological train/test split, to find (or
honestly report the absence of) a configuration reaching ≥90% target-hit rate, ≥5 recommendations
per week, and a positive expected return — without changing candidate generation (scoring/pattern
logic) itself.

**Architecture:** Two new, independent modules. Phase 1 (`backtest/generate_signal_candidates.py`)
re-runs the existing, unmodified `evaluate_candidate()` over the 959-ticker/2022-2026 universe and
caches every qualifying candidate together with its forward OHLC price path (so any target/stop
choice can be evaluated later without re-fetching or re-scoring). Phase 2
(`backtest/target_stop_grid_search.py`) grid-searches target_pct/stop_pct/min_score/regime_gate/
exclude_d_box combinations against that cache, reusing sub-project 1's `apply_toss_liveprice`,
`simulate_exit`, `apply_round_trip_cost`, and `analyze_portfolio_return`'s portfolio-CAGR
simulation completely unmodified. Selection happens only on a training split; the chosen
configuration is evaluated exactly once on a held-out test split.

**Tech Stack:** Python 3.11, pandas, numpy, pytest (all already used in `backtest/`). No new
dependencies.

## Global Constraints

- Do not modify `backtest/swing_signal_engine.py`, `backtest/toss_liveprice.py`,
  `backtest/simulate_exits.py`, `backtest/transaction_costs.py`,
  `backtest/market_regime_history.py`, or `backtest/analyze_portfolio_return.py` — all
  already-reviewed and reused as-is via their existing function signatures.
- Target/stop are **flat percentages**, not ATR-scaled — `target_pct`/`stop_pct` apply uniformly
  to every candidate in a grid cell, computed as `entry * (1 ± pct)`. This is a deliberate
  simplification versus production's ATR-scaled formula (see design doc, "Explicitly out of
  scope").
- `target_pct` grid floor is `0.03` (3%) — never search below this per the user's explicit
  requirement.
- The ≥5 recommendations/week frequency floor is a **hard constraint** agreed with the user, not
  a soft preference — the fallback selection logic in Task 3 must not silently drop it.
- **`hit_rate` means `(result == "target").mean()`** — the fraction of trades whose exit was a
  target touch, NOT `(pnl > 0).mean()`. These are different metrics: a trade that times out with a
  small positive PnL counts toward the existing `win_rate` stat in `run_swing_v2_backtest.py` but
  NOT toward this plan's `hit_rate`. Do not conflate them — the user's "90%" requirement is
  specifically about reaching the target price.
- Train split: `2022-01-01`..`2024-06-30`. Test split: `2024-07-01`..`2026-01-01`. Grid search and
  configuration selection (Task 3's `select_best_config`) run **only** on the train split. The
  selected configuration is evaluated on the test split exactly once, with no re-selection
  afterward.
- No changes to `src/swing-scanner.src.js` in this plan — this plan stops at a backtested
  recommendation in an analysis document; production deployment is a separate, later decision.
- Every numeric/logic piece ships with a value-pinning unit test — no test that only asserts "runs
  without error."

---

## File Structure Overview

| File | Status | Responsibility |
|---|---|---|
| `backtest/generate_signal_candidates.py` | Create | Phase 1: candidate + forward-OHLC-path caching |
| `backtest/target_stop_grid_search.py` | Create | Phase 2: grid search, train/test evaluation, selection |
| `backtest_candidates_with_paths.json` | Create (data) | Phase 1 output — cached candidates |
| `backtest_grid_search_results.json` | Create (data) | Phase 2 output — full grid + selection + test result |
| `docs/03-analysis/swing-algo-target-stop-retuning.analysis.md` | Create | Results write-up |

---

### Task 1: Phase 1 — candidate + forward-path caching

**Files:**
- Create: `backtest/generate_signal_candidates.py`
- Test: `backtest/tests/test_generate_signal_candidates.py`

**Interfaces:**
- Consumes: `evaluate_candidate` (`backtest/swing_signal_engine.py`, unmodified),
  `fetch_yahoo_chart`/`chart_to_ohlcv_daily` (`backtest/yahoo_cache.py`, unmodified),
  `fetch_supply_for_date` (`backtest/krx_supply_history.py`, unmodified),
  `fetch_disclosures_for_date` (`backtest/dart_history.py`, unmodified).
- Produces: `CachedCandidate` dataclass (`ticker, code, date, entry, pattern_type, score,
  rank_score, grade, hold_days, window_open, window_high, window_low, window_close` — all JSON
  primitives) and `generate_candidates(tickers, *, start, end, dart_api_key=DART_API_KEY) ->
  Tuple[List[CachedCandidate], List[Dict[str, str]]]`. Consumed by Task 2/3 (grid search) and
  Task 4 (real run).

- [ ] **Step 1: Write the failing test**

Create `backtest/tests/test_generate_signal_candidates.py`:

```python
import pandas as pd

from backtest import generate_signal_candidates as mod


def test_generate_candidates_caches_window_and_fields(monkeypatch):
    ticker = "000001.KS"
    df = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"],
            utc=True,
        ),
        "open":   [100.0, 100.0, 101.0, 102.0, 103.0, 104.0],
        "high":   [101.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        "low":    [99.0,  99.0,  100.0, 101.0, 102.0, 103.0],
        "close":  [100.0, 100.0, 101.5, 102.5, 103.5, 104.5],
        "volume": [1_000_000.0] * 6,
    })

    monkeypatch.setattr(mod, "fetch_yahoo_chart", lambda spec: {"_fake_for": spec.ticker})
    monkeypatch.setattr(mod, "chart_to_ohlcv_daily", lambda data: (df.copy(), None))
    monkeypatch.setattr(mod, "fetch_supply_for_date", lambda trd_dd: {})
    monkeypatch.setattr(mod, "fetch_disclosures_for_date", lambda trd_dd, api_key: {})

    from backtest.swing_signal_engine import SwingCandidate

    def fake_evaluate_candidate(df_arg, idx, *, supply, dart_items, day_of_week):
        if idx != 1:
            return None
        return SwingCandidate(
            pattern_type="D박스", score=100, rank_score=100, grade="매수",
            entry=100.0, target=110.0, stop=90.0, hold_days=3, signals=[],
        )

    monkeypatch.setattr(mod, "evaluate_candidate", fake_evaluate_candidate)

    candidates, skipped = mod.generate_candidates([ticker], start="2024-01-01", end="2024-01-10")

    assert skipped == []
    assert len(candidates) == 1
    c = candidates[0]
    assert c.ticker == ticker
    assert c.code == "000001"
    assert c.date == "2024-01-03T00:00:00+00:00"
    assert c.entry == 100.0
    assert c.pattern_type == "D박스"
    assert c.score == 100
    assert c.grade == "매수"
    assert c.hold_days == 3
    # entry_idx = idx(1) + 1 = 2; window is df.iloc[2:7], but only rows 2..5 exist (4 rows)
    assert c.window_open == [101.0, 102.0, 103.0, 104.0]
    assert c.window_high == [102.0, 103.0, 104.0, 105.0]
    assert c.window_low == [100.0, 101.0, 102.0, 103.0]
    assert c.window_close == [101.5, 102.5, 103.5, 104.5]


def test_generate_candidates_skips_fetch_failure(monkeypatch):
    import requests

    def raise_fetch(spec):
        raise requests.exceptions.RequestException("boom")

    monkeypatch.setattr(mod, "fetch_yahoo_chart", raise_fetch)

    candidates, skipped = mod.generate_candidates(
        ["999999.KS"], start="2024-01-01", end="2024-01-10"
    )
    assert candidates == []
    assert skipped == [{"ticker": "999999.KS", "error": "boom"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_generate_signal_candidates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.generate_signal_candidates'`

- [ ] **Step 3: Implement**

Create `backtest/generate_signal_candidates.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_generate_signal_candidates.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/generate_signal_candidates.py backtest/tests/test_generate_signal_candidates.py
git commit -m "feat(backtest): Phase 1 candidate + forward-price-path caching for target/stop retuning"
```

---

### Task 2: Phase 2 core — single grid-cell evaluator (`run_one_config`)

**Files:**
- Create: `backtest/target_stop_grid_search.py`
- Test: `backtest/tests/test_target_stop_grid_search.py`

**Interfaces:**
- Consumes: `CachedCandidate` (Task 1), `apply_daily_selection`/`_iso_week_key`
  (`backtest/run_swing_v2_backtest.py`, unmodified), `apply_toss_liveprice`
  (`backtest/toss_liveprice.py`, unmodified), `simulate_exit` (`backtest/simulate_exits.py`,
  unmodified), `apply_round_trip_cost` (`backtest/transaction_costs.py`, unmodified),
  `simulate_portfolio`/`cagr_and_mdd` (`backtest/analyze_portfolio_return.py`, unmodified).
- Produces: `run_one_config(candidates, *, target_pct, stop_pct, min_score, regime_gate,
  exclude_d_box, regime_lookup, start, end) -> Dict[str, Any]` returning `{target_pct, stop_pct,
  min_score, regime_gate, exclude_d_box, n_trades, hit_rate, trades_per_week, avg_pnl,
  cagr_15slot, mdd_15slot}`. Consumed by Task 3 (grid sweep and selection).

**Note on `candidates` argument:** the caller (Task 3's `run_grid_search`) is expected to have
already filtered `candidates` to `[start, end]` — `run_one_config` does NOT re-filter by date
itself (only uses `start`/`end` to compute the `trades_per_week` denominator). This avoids
re-scanning the full candidate pool on every one of the ~432 grid cells.

- [ ] **Step 1: Write the failing tests**

Create `backtest/tests/test_target_stop_grid_search.py`:

```python
from backtest.generate_signal_candidates import CachedCandidate
from backtest.target_stop_grid_search import run_one_config


def _make_candidate(
    code, date, score, pattern_type="C촉매", grade="매수", entry=100.0, hold_days=3, window=None
):
    if window is None:
        window = {
            "open": [entry] * hold_days, "high": [entry] * hold_days,
            "low": [entry] * hold_days, "close": [entry] * hold_days,
        }
    return CachedCandidate(
        ticker=f"{code}.KS", code=code, date=date, entry=entry,
        pattern_type=pattern_type, score=score, rank_score=score, grade=grade,
        hold_days=hold_days,
        window_open=window["open"], window_high=window["high"],
        window_low=window["low"], window_close=window["close"],
    )


def test_min_score_excludes_below_threshold():
    low = _make_candidate("000001", "2024-01-02T00:00:00+00:00", score=70)
    high = _make_candidate("000002", "2024-01-02T00:00:00+00:00", score=95)
    result = run_one_config(
        [low, high], target_pct=0.03, stop_pct=0.02, min_score=90,
        regime_gate=False, exclude_d_box=False, regime_lookup={},
        start="2024-01-01", end="2024-01-05",
    )
    assert result["n_trades"] == 1


def test_regime_gate_excludes_non_strong_grade_in_bear_regime():
    day = "2024-01-02T00:00:00+00:00"
    normal = _make_candidate("000001", day, score=95, grade="매수")
    strong = _make_candidate("000002", day, score=120, grade="강매")
    result = run_one_config(
        [normal, strong], target_pct=0.03, stop_pct=0.02, min_score=60,
        regime_gate=True, exclude_d_box=False,
        regime_lookup={"2024-01-02": 2},
        start="2024-01-01", end="2024-01-05",
    )
    assert result["n_trades"] == 1  # only the 강매 candidate survives the bear-regime gate


def test_regime_gate_off_keeps_both_candidates():
    day = "2024-01-02T00:00:00+00:00"
    normal = _make_candidate("000001", day, score=95, grade="매수")
    strong = _make_candidate("000002", day, score=120, grade="강매")
    result = run_one_config(
        [normal, strong], target_pct=0.03, stop_pct=0.02, min_score=60,
        regime_gate=False, exclude_d_box=False,
        regime_lookup={"2024-01-02": 2},
        start="2024-01-01", end="2024-01-05",
    )
    assert result["n_trades"] == 2


def test_exclude_d_box_removes_d_box_candidates():
    day = "2024-01-02T00:00:00+00:00"
    dbox = _make_candidate("000001", day, score=95, pattern_type="D박스")
    other = _make_candidate("000002", day, score=95, pattern_type="C촉매")
    result = run_one_config(
        [dbox, other], target_pct=0.03, stop_pct=0.02, min_score=60,
        regime_gate=False, exclude_d_box=True, regime_lookup={},
        start="2024-01-01", end="2024-01-05",
    )
    assert result["n_trades"] == 1


def test_hit_rate_trades_per_week_and_pnl_value_pinned():
    day = "2024-01-02T00:00:00+00:00"
    # entry=100 -> target_pct=0.03 => target=103; stop_pct=0.02 => stop=98
    # window: day0 high=104 (>=target), low=99 (>stop) -> hits target on day 0
    hit = _make_candidate(
        "000001", day, score=100, hold_days=3, entry=100.0,
        window={
            "open": [100.0, 100.0, 100.0], "high": [104.0, 104.0, 104.0],
            "low": [99.0, 99.0, 99.0], "close": [103.5, 103.5, 103.5],
        },
    )
    result = run_one_config(
        [hit], target_pct=0.03, stop_pct=0.02, min_score=60,
        regime_gate=False, exclude_d_box=False, regime_lookup={},
        start="2024-01-01", end="2024-01-08",  # exactly 7 days = 1.0 week
    )
    assert result["n_trades"] == 1
    assert result["hit_rate"] == 1.0
    assert result["trades_per_week"] == 1.0
    assert abs(result["avg_pnl"] - (0.03 - 0.002)) < 1e-9  # net of default 0.2% round-trip cost


def test_no_trades_returns_zeroed_result():
    result = run_one_config(
        [], target_pct=0.03, stop_pct=0.02, min_score=60,
        regime_gate=False, exclude_d_box=False, regime_lookup={},
        start="2024-01-01", end="2024-01-08",
    )
    assert result["n_trades"] == 0
    assert result["hit_rate"] == 0.0
    assert result["trades_per_week"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_target_stop_grid_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.target_stop_grid_search'`

- [ ] **Step 3: Implement**

Create `backtest/target_stop_grid_search.py`:

```python
"""
Phase 2 of the target/stop retuning sub-project: grid-searches target_pct/stop_pct/min_score/
regime_gate/exclude_d_box combinations against Phase 1's cached candidates
(backtest/generate_signal_candidates.py), reusing sub-project 1's TOSS-LIVEPRICE, exit-simulation,
transaction-cost, and portfolio-CAGR functions unmodified. See
docs/superpowers/specs/2026-07-27-swing-algo-target-stop-retuning-design.md for the full design.

hit_rate here means (result == "target").mean() -- the fraction of trades that actually touched
the target price -- which is NOT the same metric as run_swing_v2_backtest.py's win_rate stat
((pnl > 0).mean()). Do not conflate the two.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from .analyze_portfolio_return import cagr_and_mdd, simulate_portfolio
from .generate_signal_candidates import CachedCandidate
from .run_swing_v2_backtest import _iso_week_key, apply_daily_selection
from .simulate_exits import simulate_exit
from .toss_liveprice import apply_toss_liveprice
from .transaction_costs import apply_round_trip_cost


def _window_df(c: CachedCandidate) -> pd.DataFrame:
    """Lazily builds and caches the small per-candidate OHLC DataFrame simulate_exit needs.
    Cached on the CachedCandidate instance itself so repeated grid cells (which all reuse the
    same candidate objects) don't rebuild it ~432 times per candidate."""
    cached = getattr(c, "_window_df_cache", None)
    if cached is None:
        cached = pd.DataFrame({
            "open": c.window_open, "high": c.window_high,
            "low": c.window_low, "close": c.window_close,
        })
        c._window_df_cache = cached
    return cached


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

        selected = apply_daily_selection(filtered, week_state)
        for code, c in selected:
            new_target = c.entry * (1 + target_pct)
            new_stop = c.entry * (1 - stop_pct)
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
    base = {
        "target_pct": target_pct, "stop_pct": stop_pct, "min_score": min_score,
        "regime_gate": regime_gate, "exclude_d_box": exclude_d_box,
    }
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_target_stop_grid_search.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/target_stop_grid_search.py backtest/tests/test_target_stop_grid_search.py
git commit -m "feat(backtest): single-config evaluator (run_one_config) for target/stop grid search"
```

---

### Task 3: Grid definition, selection rule, and train/test orchestration

**Files:**
- Modify: `backtest/target_stop_grid_search.py`
- Test: `backtest/tests/test_target_stop_grid_search.py`

**Interfaces:**
- Consumes: `run_one_config` (Task 2).
- Produces: `build_grid() -> List[Dict[str, Any]]` (432 grid cells), `select_best_config(
  train_results: List[Dict]) -> Dict[str, Any]` (returns `{status: "target_met"|"target_not_met",
  config, fallback_top5, fallback_best_cagr}`), `run_grid_search(candidates, *, regime_lookup,
  train_start, train_end, test_start, test_end) -> Dict[str, Any]` (returns `{train_results,
  selection, test_result}`). Consumed by Task 5 (the real run).

- [ ] **Step 1: Write the failing tests**

Add to `backtest/tests/test_target_stop_grid_search.py`:

```python
from backtest.target_stop_grid_search import build_grid, run_grid_search, select_best_config


def test_build_grid_size():
    grid = build_grid()
    assert len(grid) == 6 * 6 * 3 * 2 * 2  # target_pct x stop_pct x min_score x regime x d_box == 432
    assert all(cell["target_pct"] >= 0.03 for cell in grid)  # 3% floor, never searched below


def test_select_best_config_prefers_highest_cagr_among_qualifying():
    results = [
        {"target_pct": 0.03, "stop_pct": 0.02, "min_score": 60, "regime_gate": False,
         "exclude_d_box": False, "hit_rate": 0.92, "trades_per_week": 6, "cagr_15slot": 0.10,
         "avg_pnl": 0.01, "n_trades": 100},
        {"target_pct": 0.04, "stop_pct": 0.02, "min_score": 60, "regime_gate": False,
         "exclude_d_box": False, "hit_rate": 0.91, "trades_per_week": 6, "cagr_15slot": 0.20,
         "avg_pnl": 0.01, "n_trades": 100},
        {"target_pct": 0.05, "stop_pct": 0.02, "min_score": 60, "regime_gate": False,
         "exclude_d_box": False, "hit_rate": 0.85, "trades_per_week": 6, "cagr_15slot": 0.50,
         "avg_pnl": 0.01, "n_trades": 100},  # hit_rate < 0.90 -> does not qualify
    ]
    sel = select_best_config(results)
    assert sel["status"] == "target_met"
    assert sel["config"]["target_pct"] == 0.04  # highest cagr among the two qualifying rows


def test_select_best_config_fallback_when_none_qualify():
    results = [
        {"target_pct": 0.03, "stop_pct": 0.04, "min_score": 60, "regime_gate": False,
         "exclude_d_box": False, "hit_rate": 0.70, "trades_per_week": 6, "cagr_15slot": 0.05,
         "avg_pnl": 0.005, "n_trades": 100},
        {"target_pct": 0.05, "stop_pct": 0.02, "min_score": 90, "regime_gate": True,
         "exclude_d_box": True, "hit_rate": 0.80, "trades_per_week": 6, "cagr_15slot": 0.02,
         "avg_pnl": 0.004, "n_trades": 50},
        {"target_pct": 0.10, "stop_pct": 0.01, "min_score": 110, "regime_gate": False,
         "exclude_d_box": False, "hit_rate": 0.95, "trades_per_week": 2, "cagr_15slot": 0.30,
         "avg_pnl": 0.02, "n_trades": 10},  # highest hit_rate AND cagr, but fails freq floor
    ]
    sel = select_best_config(results)
    assert sel["status"] == "target_not_met"
    # only rows 1 & 2 satisfy trades_per_week >= 5; row 2 has the higher hit_rate (0.80 > 0.70)
    assert sel["config"]["hit_rate"] == 0.80
    assert len(sel["fallback_top5"]) == 2
    # best cagr regardless of frequency floor is still surfaced separately
    assert sel["fallback_best_cagr"]["hit_rate"] == 0.95


def test_run_grid_search_train_test_split_and_selection(monkeypatch):
    from backtest.generate_signal_candidates import CachedCandidate

    def make(code, date, score=100, entry=100.0):
        return CachedCandidate(
            ticker=f"{code}.KS", code=code, date=date, entry=entry,
            pattern_type="C촉매", score=score, rank_score=score, grade="매수",
            hold_days=3,
            window_open=[entry, entry, entry], window_high=[entry * 1.05] * 3,
            window_low=[entry * 0.97] * 3, window_close=[entry] * 3,
        )

    train_candidates = [make("000001", "2024-06-30T00:00:00+00:00")]
    test_candidates = [make("000002", "2024-07-01T00:00:00+00:00")]

    result = run_grid_search(
        train_candidates + test_candidates,
        regime_lookup={},
        train_start="2024-01-01", train_end="2024-06-30",
        test_start="2024-07-01", test_end="2024-12-31",
    )
    assert len(result["train_results"]) == 432
    # the 2024-06-30 candidate is train-only, the 2024-07-01 candidate is test-only
    assert result["test_result"]["n_trades"] in (0, 1)
    assert "selection" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_target_stop_grid_search.py -v -k "grid or select_best or run_grid_search"`
Expected: FAIL — `ImportError` (no `build_grid`/`select_best_config`/`run_grid_search` yet).

- [ ] **Step 3: Implement**

Append to `backtest/target_stop_grid_search.py`:

```python
GRID_TARGET_PCT = [0.03, 0.04, 0.05, 0.06, 0.08, 0.10]
GRID_STOP_PCT = [0.01, 0.015, 0.02, 0.025, 0.03, 0.04]
GRID_MIN_SCORE = [60, 90, 110]
GRID_REGIME_GATE = [False, True]
GRID_EXCLUDE_D_BOX = [False, True]

MIN_HIT_RATE = 0.90
MIN_TRADES_PER_WEEK = 5.0


def build_grid() -> List[Dict[str, Any]]:
    return [
        {
            "target_pct": tp, "stop_pct": sp, "min_score": ms,
            "regime_gate": rg, "exclude_d_box": ed,
        }
        for tp in GRID_TARGET_PCT
        for sp in GRID_STOP_PCT
        for ms in GRID_MIN_SCORE
        for rg in GRID_REGIME_GATE
        for ed in GRID_EXCLUDE_D_BOX
    ]


def select_best_config(train_results: List[Dict[str, Any]]) -> Dict[str, Any]:
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


def run_grid_search(
    candidates: List[CachedCandidate],
    *,
    regime_lookup: Dict[str, int],
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_target_stop_grid_search.py -v`
Expected: all tests pass (6 from Task 2 + 4 new = 10 total).

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest backtest/tests -v`
Expected: all tests pass (74 from prior sessions + 2 from Task 1 + 10 from Task 2/3 = 86 total;
exact count isn't load-bearing, zero failures is).

- [ ] **Step 6: Commit**

```bash
git add backtest/target_stop_grid_search.py backtest/tests/test_target_stop_grid_search.py
git commit -m "feat(backtest): grid definition, train-only selection rule, and train/test orchestration"
```

---

### Task 4: Run Phase 1 over the full universe

**Files:** none created except the output JSON — this is an execution-only task.

- [ ] **Step 1: Kick off candidate generation in the background**

Run (background — comparable cost to sub-project 1's Task 5 full run since it re-executes
`evaluate_candidate` over the same 959-ticker/2022-2026 space; expect on the order of 1-3+ hours):

```bash
python -m backtest.generate_signal_candidates --tickers backtest/tickers_operating.txt --start 2022-01-01 --end 2026-01-01 --out backtest_candidates_with_paths.json
```

Expected: eventually prints `wrote backtest_candidates_with_paths.json: N candidates, M skipped
tickers` where `M` matches sub-project 1's 4 skipped tickers (same delisted/unfetchable tickers)
and `N` is substantially larger than sub-project 1's 2,832 pre-block candidate count (Phase 1 here
caches every `evaluate_candidate` pass, before any daily/weekly selection cap is applied).

- [ ] **Step 2: Sanity-check the output**

Run:
```bash
python -c "
import json
d = json.load(open('backtest_candidates_with_paths.json', encoding='utf-8'))
print('candidates:', len(d['candidates']))
print('skipped:', len(d['skipped_tickers']))
print('sample:', d['candidates'][0] if d['candidates'] else None)
"
```
Expected: `candidates` > 0 with no exception; `skipped` == 4 (matching sub-project 1); sample
record has all `CachedCandidate` fields populated and non-null.

- [ ] **Step 3: Commit the raw result for reproducibility**

```bash
git add backtest_candidates_with_paths.json
git commit -m "data(backtest): cached signal candidates + forward price paths, 959 tickers 2022-01-01..2026-01-01"
```

---

### Task 5: Run Phase 2 — grid search with train/test split

**Files:** none created except the output JSON — this is an execution-only task.

- [ ] **Step 1: Build the regime lookup**

Run:
```bash
python -c "
import json
from backtest.market_regime_history import compute_regime_series
df = compute_regime_series('2022-01-01', '2026-01-01')
lookup = {d.isoformat(): int(level) for d, level in df['regime_level'].items()}
json.dump(lookup, open('backtest_regime_lookup.json', 'w', encoding='utf-8'))
print('wrote backtest_regime_lookup.json:', len(lookup), 'days')
"
```
Expected: prints a day count roughly matching the number of KOSPI/KOSDAQ trading days in the
range (a few hundred to ~1000). This is the first real invocation of
`market_regime_history.compute_regime_series` in this codebase (previously computed but never
called anywhere) — if it raises a network/fetch error for `%5EKS11`/`%5EKQ11`/`%5EIXIC`/`%5EVIX`,
that is a pre-existing gap in this module's own fetch resilience, not something this plan
introduces; stop and report rather than silently working around it.

- [ ] **Step 2: Run the grid search**

Run (background — 432 grid cells over the cached train-split candidates; expect low minutes to
tens of minutes given the `_window_df` per-candidate caching in Task 2, not hours):

```bash
python -c "
import json
from backtest.generate_signal_candidates import CachedCandidate
from backtest.target_stop_grid_search import run_grid_search

d = json.load(open('backtest_candidates_with_paths.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]
regime_lookup = json.load(open('backtest_regime_lookup.json', encoding='utf-8'))

result = run_grid_search(
    candidates, regime_lookup=regime_lookup,
    train_start='2022-01-01', train_end='2024-06-30',
    test_start='2024-07-01', test_end='2026-01-01',
)
json.dump(result, open('backtest_grid_search_results.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('selection status:', result['selection']['status'])
print('selected config:', result['selection']['config'])
print('test result:', result['test_result'])
"
```

Expected: no exceptions, no NaN in the selected config's or test result's `avg_pnl`/`cagr_15slot`
(a `nan` there means 0 trades in that split for the chosen config — stop and investigate rather
than proceeding, same rule as sub-project 1's Task 5 sanity check). Prints the selection status
(`target_met` or `target_not_met`) plainly.

- [ ] **Step 3: Commit the raw result for reproducibility**

```bash
git add backtest_regime_lookup.json backtest_grid_search_results.json
git commit -m "data(backtest): target/stop grid search results, train 2022-2024H1 / test 2024H2-2026"
```

---

### Task 6: Write the results analysis document

**Files:**
- Create: `docs/03-analysis/swing-algo-target-stop-retuning.analysis.md`

- [ ] **Step 1: Summarize the grid search results**

Run:
```bash
python -c "
import json
d = json.load(open('backtest_grid_search_results.json', encoding='utf-8'))
sel = d['selection']
print('status:', sel['status'])
print('selected config:', sel['config'])
print('test result:', d['test_result'])
if sel['status'] == 'target_not_met':
    print('fallback_top5:', sel['fallback_top5'])
    print('fallback_best_cagr:', sel['fallback_best_cagr'])
top10_train = sorted(d['train_results'], key=lambda r: r['cagr_15slot'], reverse=True)[:10]
for r in top10_train:
    print(r)
"
```

- [ ] **Step 2: Write the analysis document**

Create `docs/03-analysis/swing-algo-target-stop-retuning.analysis.md` with these sections, using
the real numbers from Step 1 (no bracket placeholders left in the committed file):

- **Header** matching the convention of `docs/03-analysis/backtest.analysis.md` (Analysis Type,
  Project, Feature, Design Doc / Implementation Plan links, Date).
- **Method summary**: one paragraph restating the grid axes, train/test split dates, and the
  selection rule (90% hit-rate + 5/week frequency floor, maximize CAGR among qualifying; explicit
  fallback otherwise) — link to the design doc rather than re-deriving it.
- **Result**: state plainly whether `selection.status` was `target_met` or `target_not_met`. Show
  the selected configuration's exact `target_pct`/`stop_pct`/`min_score`/`regime_gate`/
  `exclude_d_box`, and a table comparing **train** vs. **test** `hit_rate`/`trades_per_week`/
  `avg_pnl`/`cagr_15slot` side by side — a large gap between train and test numbers is itself a
  finding (evidence of overfitting) and must be called out explicitly, not omitted.
- **Top-10 train configs table** (from Step 1), for transparency about the shape of the search
  space even if a single config was selected.
- **If `target_not_met`**: report `fallback_top5` and `fallback_best_cagr` plainly, and state
  the honest conclusion — e.g., "no configuration in this grid jointly reached 90% hit-rate and
  5/week frequency with a positive return; the best available trade-off was X" — without
  softening it. Recommend the conditional sub-project 3 (new signals) as the next step per the
  design doc's roadmap.
- **Limitations**: flat-percentage (not ATR-scaled) target/stop is a simplification; single
  train/test split (not walk-forward/k-fold) means the test-period estimate, while genuinely
  held-out, is still a single draw; grid is discrete (the true optimum may lie between grid
  points).
- **Next step recommendation**: explicitly state that no production code
  (`src/swing-scanner.src.js`) has been changed, and that deployment is a separate decision
  pending the user's review of these results.

- [ ] **Step 3: Commit**

```bash
git add docs/03-analysis/swing-algo-target-stop-retuning.analysis.md
git commit -m "docs: target/stop grid search results for swing algo enhancement sub-project 2"
```

---

## Self-Review Notes

- **Spec coverage:** every in-scope item from
  `docs/superpowers/specs/2026-07-27-swing-algo-target-stop-retuning-design.md` maps to a task —
  candidate+path caching (Task 1), single-config evaluation reusing sub-project 1's pure
  functions (Task 2), grid definition/selection/train-test orchestration (Task 3), the real
  Phase 1 run (Task 4), the real Phase 2 run including the regime lookup (Task 5), and the
  results write-up (Task 6).
- **Placeholder scan:** no task contains "TBD"/"TODO"/unfilled brackets; Task 6's document
  content is described precisely (which numbers, which comparisons) without being filled in here,
  matching the pattern of sub-project 1's Task 6 (its real values only exist after Task 4/5 run).
- **Type consistency:** `CachedCandidate`'s fields (Task 1) are used identically in Task 2/3's
  tests and implementation. `run_one_config`'s return dict keys (`hit_rate`, `trades_per_week`,
  `avg_pnl`, `cagr_15slot`, `mdd_15slot`, plus the 5 grid-parameter keys) are used identically by
  `select_best_config` and `run_grid_search` in Task 3, and by Task 6's summary script.
- **Global-constraint check:** `hit_rate`'s definition (`result == "target"`, distinct from the
  existing `win_rate` stat) is stated in the Global Constraints section and again in Task 2's
  module docstring, so an implementer reading only one task still sees it. The 3% target floor is
  the grid's minimum value (`GRID_TARGET_PCT[0] = 0.03`), verified by
  `test_build_grid_size`'s floor assertion. The 5/week frequency floor is enforced identically in
  `select_best_config`'s primary qualification path and its fallback path (never silently
  dropped), verified by both `select_best_config` tests.
- **Scope check:** single cohesive subsystem (target/stop/threshold retuning via grid search),
  matching the sub-project boundary drawn during brainstorming. New signals (sub-project 3) are
  explicitly out of scope and conditional on this sub-project's result.

# swing-algo-partial-exit-simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backtest the exit mechanism production actually promises users (30%@+2% / 30%@+4% /
remaining 40% on ATR-trailing-stop-or-timeout) and report how it changes the -26.03%/yr headline
CAGR figure that's currently built on a simpler binary target/stop/timeout model — honestly,
whichever direction it moves.

**Architecture:** A new sibling function `simulate_exit_partial()` in `backtest/simulate_exits.py`
implements the exit state machine (existing `simulate_exit()` untouched). `backtest/run_swing_v2_backtest.py`'s
`backtest_swing_v2()` gets an `exit_model` parameter (default `"binary"`, preserving exact current
behavior) that switches to the new function when set to `"partial"`, computing `atr_pct` inline
from data already in scope. Re-run against the same 959-ticker/4-year universe as the existing
-26.03%/yr figure, reuse `backtest/analyze_portfolio_return.py` unmodified for portfolio stats,
write a comparison analysis document.

**Tech Stack:** Python, pandas, numpy, pytest. No new dependencies.

## Global Constraints

- **No modifications to `src/swing-scanner.src.js`** — this sub-project backtests what production
  already promises users, it does not change that promise.
- **`backtest/simulate_exits.py`'s existing `simulate_exit()` is not modified** — every prior
  sub-project's cached results that call it must stay reproducible.
- **`backtest/analyze_portfolio_return.py` is not modified** — it's already schema-compatible
  (reads only `trade["date"]`/`trade["pnl"]`), reuse its functions with a different file path
  instead of editing it.
- **`backtest_swing_v2()`'s default `exit_model="binary"` path must remain byte-identical to its
  current behavior.** This is load-bearing: `backtest_out_swing_v2_realistic.json` and every
  figure derived from it (the -26.03%/yr headline) depend on this exact path never changing.
- Same-bar tie-break convention (from `docs/superpowers/specs/2026-08-02-swing-algo-partial-exit-simulation-design.md`
  Section 4): whenever a single day's OHLC range could plausibly trigger more than one outcome,
  resolve to the worse-for-the-trader outcome. Pre-trigger phase: check `stop` breach before the
  +2% trigger. Runner phase: check trailing-stop breach (using the running high as of the
  *previous* day's close) before checking the +4% partial, and before folding the current day's
  high into the running high.
- Exit state machine (design doc Section 3, confirmed with the user): before +2% is ever touched,
  only `stop` is active (100% of position). First touch of `entry*1.02` sells 30% at that price.
  From then on, whichever comes first for the remaining 70% between a +4% partial (another 30% of
  the *original* position, at `entry*1.04`) and a trailing-stop breach
  (`running_high * (1 - trailingPct)`, `trailingPct = clamp(atr_pct, 0.01, 0.03)`) determines the
  next event; if trailing breaches before +4% ever triggers, the entire remaining 70% exits at
  once. The final 40% (after a +4% partial has fired) exits on trailing-breach-or-timeout,
  whichever is first.
- No bracket placeholders or invented numbers in the final analysis document (Task 5) — every
  number must trace to `backtest_out_swing_v2_partial_exit.json`, Task 4's captured portfolio-stats
  output, or `docs/03-analysis/swing-algorithm-profitability-review.analysis.md` cited by name.
- Work directly on `main`, no feature branch — matches this research line's established
  convention.

---

### Task 1: `simulate_exit_partial()` — the exit state machine, TDD

**Files:**
- Modify: `backtest/simulate_exits.py` (add a new function; `simulate_exit()` untouched)
- Create: `backtest/tests/test_simulate_exit_partial.py`

**Interfaces:**
- Produces: `simulate_exit_partial(df: pd.DataFrame, entry_idx: int, *, entry: float, stop: float,
  atr_pct: float, hold_days: int) -> Dict[str, Any]`, returning
  `{"exit_price": float, "result": str, "days_held": int, "tranches": List[Dict[str, Any]]}`.
  `result` is one of: `"pretrigger_stop"`, `"pretrigger_timeout"`, `"trail"`,
  `"target4_then_trail"`, `"target4_then_timeout"`, `"trigger_then_timeout"`. Each tranche dict is
  `{"day_idx": int, "weight": float, "price": float, "reason": str}` with weights summing to
  `1.0`. Task 2 consumes this function and its exact return-key names.

- [ ] **Step 1: Write the failing tests**

Create `backtest/tests/test_simulate_exit_partial.py`:

```python
import pytest
import pandas as pd

from backtest.simulate_exits import simulate_exit_partial


def _df(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def test_pretrigger_stop_before_2pct_ever_touched():
    df = _df([
        [100, 101, 99, 100],   # day0: no stop (low=99 > stop=95), no trigger (high=101 < 102)
        [100, 100, 94, 95],    # day1: low=94 <= stop(95) -> full stop-out
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=95.0, atr_pct=0.02, hold_days=5)
    assert r["result"] == "pretrigger_stop"
    assert r["exit_price"] == pytest.approx(95.0)
    assert r["days_held"] == 1
    assert r["tranches"] == [{"day_idx": 1, "weight": 1.0, "price": 95.0, "reason": "stop"}]


def test_pretrigger_timeout_never_triggers():
    df = _df([
        [100, 101, 99, 100],   # day0: no stop, no trigger
        [100, 101, 99, 99],    # day1: no stop, no trigger
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=90.0, atr_pct=0.02, hold_days=2)
    assert r["result"] == "pretrigger_timeout"
    assert r["exit_price"] == pytest.approx(99.0)
    assert r["days_held"] == 1
    assert r["tranches"] == [{"day_idx": 1, "weight": 1.0, "price": 99.0, "reason": "timeout"}]


def test_trigger_then_trailing_stop_before_4pct():
    df = _df([
        [100, 103, 99, 102],     # day0: high=103 >= trigger(102) -> 30% @ 102, running_high=103
        [102, 103.5, 100, 101],  # day1: trailing_level=103*0.98=100.94; low=100 <= 100.94 -> trail
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=90.0, atr_pct=0.02, hold_days=5)
    assert r["result"] == "trail"
    assert r["exit_price"] == pytest.approx(0.30 * 102.0 + 0.70 * 100.94)
    assert r["days_held"] == 1
    assert r["tranches"] == [
        {"day_idx": 0, "weight": 0.30, "price": 102.0, "reason": "trigger_2pct"},
        {"day_idx": 1, "weight": 0.70, "price": pytest.approx(100.94), "reason": "trail"},
    ]


def test_trigger_then_4pct_then_trailing_stop():
    df = _df([
        [100, 103, 99, 102],      # day0: trigger @102, running_high=103
        [102, 105, 101, 104],     # day1: trailing_level=103*0.98=100.94, low=101 no breach;
                                   #       high=105 >= 104 -> 30% @104, running_high=max(103,105)=105
        [104, 103, 102, 102.5],   # day2: trailing_level=105*0.98=102.9, low=102 <= 102.9 -> trail
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=90.0, atr_pct=0.02, hold_days=5)
    assert r["result"] == "target4_then_trail"
    expected_price = 0.30 * 102.0 + 0.30 * 104.0 + 0.40 * 102.9
    assert r["exit_price"] == pytest.approx(expected_price)
    assert r["days_held"] == 2
    pnl_pct = (r["exit_price"] - 100.0) / 100.0
    hand_computed_pnl_pct = 0.30 * 0.02 + 0.30 * 0.04 + 0.40 * 0.029
    assert pnl_pct == pytest.approx(hand_computed_pnl_pct)


def test_trigger_then_4pct_then_timeout():
    df = _df([
        [100, 103, 99, 102],     # day0: trigger @102, running_high=103
        [102, 105, 101, 104],    # day1: no trail breach (low=101>100.94); +4% @104, running_high=105
        [104, 103, 103, 103.2],  # day2 (=end, hold_days=3): trailing_level=105*0.98=102.9,
                                  #       low=103 > 102.9 -> no breach -> timeout at this close
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=90.0, atr_pct=0.02, hold_days=3)
    assert r["result"] == "target4_then_timeout"
    expected_price = 0.30 * 102.0 + 0.30 * 104.0 + 0.40 * 103.2
    assert r["exit_price"] == pytest.approx(expected_price)
    assert r["days_held"] == 2
    assert r["tranches"][-1] == {"day_idx": 2, "weight": pytest.approx(0.40), "price": 103.2, "reason": "timeout"}


def test_trigger_then_timeout_never_hits_4pct_or_trail():
    df = _df([
        [100, 103, 99, 102],       # day0: trigger @102, running_high=103
        [102, 103, 101, 102.5],    # day1: trailing_level=100.94, low=101 no breach; high=103<104 no +4%
        [102.5, 103.5, 101, 102.8],# day2 (=end, hold_days=3): trailing_level=100.94 (unchanged since
                                    #       running_high stayed 103 through day1's check), low=101 no breach;
                                    #       high=103.5<104 no +4% -> timeout at this close
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=90.0, atr_pct=0.02, hold_days=3)
    assert r["result"] == "trigger_then_timeout"
    expected_price = 0.30 * 102.0 + 0.70 * 102.8
    assert r["exit_price"] == pytest.approx(expected_price)
    assert r["days_held"] == 2
    assert r["tranches"] == [
        {"day_idx": 0, "weight": 0.30, "price": 102.0, "reason": "trigger_2pct"},
        {"day_idx": 2, "weight": pytest.approx(0.70), "price": 102.8, "reason": "timeout"},
    ]


def test_same_bar_tie_break_pretrigger_resolves_to_stop():
    df = _df([
        [100, 103, 94, 98],  # day0: high=103 >= trigger(102) AND low=94 <= stop(95) -- both true
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=95.0, atr_pct=0.02, hold_days=5)
    assert r["result"] == "pretrigger_stop"
    assert r["exit_price"] == pytest.approx(95.0)
    assert r["days_held"] == 0


def test_same_bar_tie_break_runner_resolves_to_trail_not_4pct():
    df = _df([
        [100, 103, 99, 102],   # day0: trigger @102, running_high=103
        [102, 105, 100, 101],  # day1: trailing_level=103*0.98=100.94; low=100<=100.94 (breach) AND
                                #       high=105>=104 (would-be +4%) -- both true, trail must win
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=90.0, atr_pct=0.02, hold_days=5)
    assert r["result"] == "trail"  # NOT target4_then_trail -- +4% must never have fired
    assert r["exit_price"] == pytest.approx(0.30 * 102.0 + 0.70 * 100.94)
    assert len(r["tranches"]) == 2
    assert r["tranches"][1]["reason"] == "trail"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backtest/tests/test_simulate_exit_partial.py -v`
Expected: FAIL — `ImportError: cannot import name 'simulate_exit_partial'` (function doesn't exist yet).

- [ ] **Step 3: Implement `simulate_exit_partial()`**

Add to `backtest/simulate_exits.py` (below the existing `simulate_exit()`, which stays unchanged):

```python
def _finalize_partial(
    tranches: List[Dict[str, Any]], entry: float, days_held: int, result: str
) -> Dict[str, Any]:
    total_weight = sum(t["weight"] for t in tranches)
    exit_price = (
        sum(t["weight"] * t["price"] for t in tranches) / total_weight
        if total_weight > 0 else entry
    )
    return {"exit_price": exit_price, "result": result, "days_held": days_held, "tranches": tranches}


def simulate_exit_partial(
    df: pd.DataFrame,
    entry_idx: int,
    *,
    entry: float,
    stop: float,
    atr_pct: float,
    hold_days: int,
) -> Dict[str, Any]:
    """3-tranche partial-exit + trailing-stop model matching src/swing-scanner.src.js's Telegram
    message (lines 1782-1811): 30% @ +2%, 30% @ +4%, remaining 40% on trailing-stop-breach or
    hold_days timeout (whichever first). Trailing width = clamp(atr_pct, 1%, 3%) of entry.
    See docs/superpowers/specs/2026-08-02-swing-algo-partial-exit-simulation-design.md
    Sections 3-4 for the full state machine and same-bar tie-break convention this implements.

    Same-bar tie-break: whenever a day could plausibly trigger more than one outcome, the
    worse-for-the-trader outcome is checked first (stop before the +2% trigger pre-trigger;
    trailing-stop breach before the +4% partial in the runner phase). The running high used for
    a day's trailing-stop check is as of the *previous* day's close -- the current day's own high
    only feeds into the running high used for the *next* day's check.

    Returns exit_price as the position-weighted average fill price across whichever tranches
    executed (weights sum to 1.0) -- downstream pnl math ((exit_price - entry) / entry) is
    unchanged from simulate_exit()'s contract, since
    pnl_pct = sum(weight_i * (price_i/entry - 1)) = (sum(weight_i * price_i))/entry - 1
    algebraically.
    """
    trailing_pct = max(0.01, min(atr_pct, 0.03))
    trigger_price = entry * 1.02
    target4_price = entry * 1.04

    end = min(len(df) - 1, entry_idx + hold_days - 1)

    tranches: List[Dict[str, Any]] = []
    triggered = False
    target4_taken = False
    running_high = 0.0
    remaining_weight = 1.0

    for i in range(entry_idx, end + 1):
        hi = float(df.iloc[i]["high"])
        lo = float(df.iloc[i]["low"])

        if not triggered:
            if lo <= stop:
                tranches.append({"day_idx": i, "weight": remaining_weight, "price": stop, "reason": "stop"})
                return _finalize_partial(tranches, entry, i - entry_idx, "pretrigger_stop")
            if hi >= trigger_price:
                tranches.append({"day_idx": i, "weight": 0.30, "price": trigger_price, "reason": "trigger_2pct"})
                remaining_weight -= 0.30
                triggered = True
                running_high = max(trigger_price, hi)
            continue

        trailing_level = running_high * (1 - trailing_pct)
        if lo <= trailing_level:
            tranches.append({"day_idx": i, "weight": remaining_weight, "price": trailing_level, "reason": "trail"})
            result = "target4_then_trail" if target4_taken else "trail"
            return _finalize_partial(tranches, entry, i - entry_idx, result)
        if not target4_taken and hi >= target4_price:
            tranches.append({"day_idx": i, "weight": 0.30, "price": target4_price, "reason": "target4"})
            remaining_weight -= 0.30
            target4_taken = True
        running_high = max(running_high, hi)

    exit_close = float(df.iloc[end]["close"])
    tranches.append({"day_idx": end, "weight": remaining_weight, "price": exit_close, "reason": "timeout"})
    if not triggered:
        result = "pretrigger_timeout"
    elif target4_taken:
        result = "target4_then_timeout"
    else:
        result = "trigger_then_timeout"
    return _finalize_partial(tranches, entry, end - entry_idx, result)
```

Also update the module's imports at the top of `backtest/simulate_exits.py` — `List` needs to be
importable alongside the existing `Any, Dict`:

```python
from typing import Any, Dict, List
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backtest/tests/test_simulate_exit_partial.py -v`
Expected: PASS (all 8 tests green).

- [ ] **Step 5: Run the full existing test suite to confirm no regressions**

Run: `pytest backtest/tests/test_simulate_exits.py -v`
Expected: PASS (unchanged — `simulate_exit()` itself was not touched).

- [ ] **Step 6: Commit**

```bash
git add backtest/simulate_exits.py backtest/tests/test_simulate_exit_partial.py
git commit -m "feat(backtest): add simulate_exit_partial() — 3-tranche exit + trailing stop"
```

---

### Task 2: Wire `exit_model` into `backtest_swing_v2()` and the CLI

**Files:**
- Modify: `backtest/run_swing_v2_backtest.py`
- Create: `backtest/tests/test_run_swing_v2_backtest_exit_model.py`

**Interfaces:**
- Consumes: `simulate_exit_partial()` from Task 1 (exact signature above).
- Produces: `backtest_swing_v2(tickers, *, start, end, dart_api_key=..., exit_model="binary")` —
  the new `exit_model` keyword argument, default `"binary"`. Task 3 invokes this via the module's
  `main()`/CLI, not by calling `backtest_swing_v2()` directly.

- [ ] **Step 1: Write the failing tests**

Create `backtest/tests/test_run_swing_v2_backtest_exit_model.py`. This follows the exact
monkeypatch/fixture pattern already established in
`backtest/tests/test_run_swing_v2_backtest.py::test_backtest_swing_v2_records_toss_status_and_net_pnl`
(monkeypatches `fetch_yahoo_chart`, `chart_to_ohlcv_daily`, `fetch_supply_for_date`,
`fetch_disclosures_for_date`, and `evaluate_candidate` on the `run_swing_v2_backtest` module with a
synthetic per-ticker OHLC DataFrame, then calls `mod.backtest_swing_v2([ticker], start=..., end=...)`
directly and asserts on the returned `(df_trades, stats)`):

```python
import inspect

import pandas as pd

from backtest.run_swing_v2_backtest import backtest_swing_v2


def test_exit_model_defaults_to_binary():
    sig = inspect.signature(backtest_swing_v2)
    assert sig.parameters["exit_model"].default == "binary"


def test_partial_exit_model_produces_tranches_field(monkeypatch):
    from backtest import run_swing_v2_backtest as mod

    ticker = "000003.KS"
    # idx1 (2024-01-03) is the signal day (entry=100.0, close). entry_idx=2 (2024-01-04):
    # high=103 clears the +2% trigger (102) -> 30% tranche. idx3 (2024-01-05): high=104
    # clears +4% (104) -> another 30% tranche, low=101 does not breach the trailing level
    # (103*0.98=100.94). idx4 (2024-01-06, the last day in the hold_days=3 window: entry_idx=2
    # + hold_days=3 - 1 = 4): low=102 does not breach the trailing level (104*0.98=101.92) ->
    # remaining 40% times out at this day's close. Neither target(110) nor stop(90) is ever
    # touched across idx 2-4, so the binary model on this same fixture also times out (at the
    # last day's close) -- both models produce exactly one trade, with result "timeout"/
    # "target4_then_timeout" respectively, which is what this test distinguishes.
    df = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-06"], utc=True
        ),
        "open":  [100.0, 100.0, 101.0, 102.0, 103.5],
        "high":  [101.0, 101.0, 103.0, 104.0, 103.0],
        "low":   [99.0,  99.0,  100.0, 101.0, 102.0],
        "close": [100.0, 100.0, 102.0, 103.5, 103.3],
        "volume": [1_000_000.0] * 5,
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

    df_trades_binary, stats_binary = mod.backtest_swing_v2(
        [ticker], start="2024-01-01", end="2024-01-07",
    )
    assert stats_binary["trades"] == 1
    assert "tranches" not in df_trades_binary.columns
    assert df_trades_binary.iloc[0]["result"] in {"target", "stop", "timeout"}

    df_trades_partial, stats_partial = mod.backtest_swing_v2(
        [ticker], start="2024-01-01", end="2024-01-07", exit_model="partial",
    )
    assert stats_partial["trades"] == 1
    row_partial = df_trades_partial.iloc[0]
    assert row_partial["result"] in {
        "pretrigger_stop", "pretrigger_timeout", "trail",
        "target4_then_trail", "target4_then_timeout", "trigger_then_timeout",
    }
    assert isinstance(row_partial["tranches"], list) and len(row_partial["tranches"]) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backtest/tests/test_run_swing_v2_backtest_exit_model.py -v`
Expected: FAIL — `test_exit_model_defaults_to_binary` fails with `KeyError: 'exit_model'` (parameter
doesn't exist yet); `test_partial_exit_model_produces_tranches_field` fails with `TypeError:
backtest_swing_v2() got an unexpected keyword argument 'exit_model'`.

- [ ] **Step 3: Implement the wiring**

In `backtest/run_swing_v2_backtest.py`, update the imports:

```python
from .indicators import atr as calc_atr, max_drawdown
from .simulate_exits import simulate_exit, simulate_exit_partial
```

Change the `backtest_swing_v2()` signature (currently `tickers, *, start, end,
dart_api_key=DART_API_KEY`) to add the new parameter:

```python
def backtest_swing_v2(
    tickers: List[str],
    *,
    start: str,
    end: str,
    dart_api_key: str = DART_API_KEY,
    exit_model: str = "binary",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
```

Replace the existing exit-simulation call site (currently):

```python
            sim = simulate_exit(
                df, entry_idx,
                entry=toss.entry, stop=toss.stop, target=toss.target, hold_days=cand.hold_days,
            )
```

with:

```python
            if exit_model == "partial":
                high_arr = df["high"].to_numpy(dtype="float64")
                low_arr = df["low"].to_numpy(dtype="float64")
                close_arr = df["close"].to_numpy(dtype="float64")
                atr_abs = calc_atr(high_arr, low_arr, close_arr, 14)[idx - 1] if idx >= 1 else float("nan")
                if not np.isfinite(atr_abs) or atr_abs <= 0:
                    atr_abs = float(np.nanmean(high_arr[max(0, idx - 14):idx] - low_arr[max(0, idx - 14):idx]))
                atr_pct = atr_abs / toss.entry if toss.entry > 0 else 0.0
                sim = simulate_exit_partial(
                    df, entry_idx,
                    entry=toss.entry, stop=toss.stop, atr_pct=atr_pct, hold_days=cand.hold_days,
                )
            else:
                sim = simulate_exit(
                    df, entry_idx,
                    entry=toss.entry, stop=toss.stop, target=toss.target, hold_days=cand.hold_days,
                )
```

This must go in the same place the original `sim = simulate_exit(...)` call was, inside the
`for code, cand in selected:` loop, so `df` (the ticker's full history, already in scope as
`per_ticker[ticker]`) and `idx` (the signal-day index, already computed a few lines above as
`int(df.index[df["timestamp_utc"] == day][0])`) are both already available — do not refetch or
recompute either.

Update the trade-record dict a few lines below (currently ends `"toss_status": toss.status,`) to
also carry the new fields when present, so partial-exit trades are auditable in the committed
JSON:

```python
            trades.append({
                "date": day.isoformat(), "ticker": ticker, "code": code,
                "pattern_type": cand.pattern_type, "grade": cand.grade,
                "score": cand.score, "rank_score": cand.rank_score,
                "entry": toss.entry, "stop": toss.stop, "target": toss.target,
                "exit_price": float(sim["exit_price"]), "result": sim["result"],
                "days_held": sim["days_held"], "pnl": pnl,
                "gross_pnl": gross_pnl, "toss_status": toss.status,
                **({"tranches": sim["tranches"]} if "tranches" in sim else {}),
            })
```

Finally, add the CLI flag in `main()`:

```python
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-01-01")
    ap.add_argument("--out", default="backtest_out_swing_v2.json")
    ap.add_argument("--exit-model", default="binary", choices=["binary", "partial"])
    args = ap.parse_args()

    tickers = _load_tickers(Path(args.tickers))
    df_trades, stats = backtest_swing_v2(
        tickers, start=args.start, end=args.end, exit_model=args.exit_model,
    )

    out = {
        "params": {
            "start": args.start, "end": args.end, "tickers": len(tickers),
            "exit_model": args.exit_model,
        },
        "stats": stats,
        "trades": df_trades.to_dict(orient="records") if not df_trades.empty else [],
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backtest/tests/test_run_swing_v2_backtest_exit_model.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full existing backtest test suite to confirm the binary path is unchanged**

Run: `pytest backtest/tests/test_run_swing_v2_backtest.py -v`
Expected: PASS, unchanged — this is the regression guard for the Global Constraint that
`exit_model="binary"` stays byte-identical to current behavior.

- [ ] **Step 6: Commit**

```bash
git add backtest/run_swing_v2_backtest.py backtest/tests/test_run_swing_v2_backtest_exit_model.py
git commit -m "feat(backtest): wire exit_model flag into backtest_swing_v2 and CLI"
```

---

### Task 3: Run the real partial-exit backtest

**Files:** none created except the output JSON — this is an execution-only task.

**Interfaces:**
- Consumes: `backtest_swing_v2(..., exit_model="partial")` (Task 2), `backtest/tickers_operating.txt`
  (already committed, 959 tickers), local caches under `cache/yahoo/`,
  `backtest/cache/krx_supply/`, `backtest/cache/dart/` (already populated from the prior
  `backtest_out_swing_v2_realistic.json` run over the identical universe/date-range).

- [ ] **Step 1: Run the backtest**

```bash
python -m backtest.run_swing_v2_backtest --tickers backtest/tickers_operating.txt --start 2022-01-01 --end 2026-01-01 --exit-model partial --out backtest_out_swing_v2_partial_exit.json
```

Expected: completes without exception, prints `wrote backtest_out_swing_v2_partial_exit.json`
followed by the stats JSON. This should run substantially from local cache (no fresh Yahoo/KRX/DART
network fetches expected for tickers/dates already covered by the prior
`backtest_out_swing_v2_realistic.json` run) — if you observe live network calls happening (slow,
or errors), note this in your report but do not treat cache misses as a blocker; a `HTTP 400` from
the KRX supply endpoint specifically is a known, already-documented sandbox limitation from prior
sub-projects, not a new bug to chase.

- [ ] **Step 2: Sanity-check trade count against the existing binary-model run**

```bash
python -c "
import json
a = json.load(open('backtest_out_swing_v2_realistic.json', encoding='utf-8'))
b = json.load(open('backtest_out_swing_v2_partial_exit.json', encoding='utf-8'))
print('binary trades:', a['stats']['trades'])
print('partial trades:', b['stats']['trades'])
print('binary win_rate:', a['stats']['win_rate'], 'avg_pnl:', a['stats']['avg_pnl'])
print('partial win_rate:', b['stats']['win_rate'], 'avg_pnl:', b['stats']['avg_pnl'])
"
```

Expected: trade counts very close or identical (candidate generation and TOSS-blocking logic are
unchanged between the two runs — only the exit simulation differs, and the exit model does not
affect which candidates get selected in the first place). A large divergence (more than a handful
of trades) means something in the wiring is affecting candidate selection and must be investigated
before proceeding to Task 4 — report this as a concern rather than pushing through.

- [ ] **Step 3: Commit**

```bash
git add backtest_out_swing_v2_partial_exit.json
git commit -m "data(backtest): run partial-exit/trailing-stop backtest over 959-ticker universe (sub-project 8)"
```

---

### Task 4: Portfolio-level stats for the partial-exit run

**Files:** none created — this task's output is captured in the task report for Task 5 to cite.

**Interfaces:**
- Consumes: `backtest_out_swing_v2_partial_exit.json` (Task 3), `backtest/analyze_portfolio_return.py`'s
  existing `load_trades`, `simulate_portfolio`, `cagr_and_mdd` functions (all unmodified, imported
  and called with the new file's path — do not edit that file).

- [ ] **Step 1: Compute and print the full portfolio-stats table**

```bash
python -c "
from backtest.analyze_portfolio_return import load_trades, simulate_portfolio, cagr_and_mdd

trades_sorted, stats, params = load_trades(path='backtest_out_swing_v2_partial_exit.json')
start_date = trades_sorted[0]['date']
end_date = trades_sorted[-1]['date']

print(f'Trades: {len(trades_sorted)}  |  Span: {start_date[:10]} -> {end_date[:10]}')
print(f\"Per-trade avg net pnl: {stats['avg_pnl']*100:.3f}%  |  win_rate: {stats['win_rate']*100:.2f}%\")
print()
print(f\"{'N slots':>8} | {'final equity':>14} | {'total return':>13} | {'years':>6} | {'CAGR':>9} | {'MDD':>9}\")
print('-' * 78)
for n in (5, 10, 15, 20, 30, 50, 100, 200):
    curve = simulate_portfolio(trades_sorted, n)
    final_equity, max_dd, years, cagr = cagr_and_mdd(curve, start_date, end_date)
    marker = '  <- MAX_WEEKLY_SENDS-grounded' if n == 15 else ''
    print(
        f'{n:>8} | {final_equity:>14.4f} | {(final_equity-1)*100:>12.2f}% | '
        f'{years:>6.2f} | {cagr*100:>8.2f}% | {max_dd*100:>8.2f}%{marker}'
    )
"
```

Expected: no exception, a full table for N=5/10/15/20/30/50/100/200. **Copy the exact printed
output verbatim into your task report** — Task 5 must cite these exact numbers, not re-derive or
round them differently.

- [ ] **Step 2: Compute the `result` tag frequency breakdown**

```bash
python -c "
import json
from collections import Counter

b = json.load(open('backtest_out_swing_v2_partial_exit.json', encoding='utf-8'))
counts = Counter(t['result'] for t in b['trades'])
total = len(b['trades'])
for tag, n in counts.most_common():
    print(f'{tag}: {n} ({n/total*100:.1f}%)')
print('total:', total)
"
```

Expected: a breakdown across the six possible `result` tags. **Copy this output verbatim into your
task report too** — Task 5's "how often does the trailing mechanism actually fire" section cites
this exactly.

This task produces no commits — it's a read-only analysis step. Report both printed tables in full
in your task report file.

---

### Task 5: Final analysis document

**Files:**
- Create: `docs/03-analysis/swing-algo-partial-exit-simulation.analysis.md`

- [ ] **Step 1: Assemble the honest, fully-cited comparison**

Using the real numbers from `backtest_out_swing_v2_partial_exit.json`, Task 4's two captured
outputs, and `docs/03-analysis/swing-algorithm-profitability-review.analysis.md`'s existing
"Entry-model comparison" and "Portfolio-level expected annual return" sections (cite exact figures
from there — do not re-derive), write
`docs/03-analysis/swing-algo-partial-exit-simulation.analysis.md` with these sections (no bracket
placeholders):

- **Header** matching this research line's convention (Analysis Type, Project, Feature, Design Doc
  = `docs/superpowers/specs/2026-08-02-swing-algo-partial-exit-simulation-design.md`,
  Implementation Plan = `docs/superpowers/plans/2026-08-02-swing-algo-partial-exit-simulation.md`,
  Prior work citing `swing-algorithm-profitability-review.analysis.md` by name, Date `2026-08-02`).
- **Method summary**: restate that this sub-project adds one new function
  (`simulate_exit_partial()`) and one new parameter (`exit_model`) to the existing Line A pipeline,
  changes nothing about candidate generation, `apply_daily_selection`, or `apply_toss_liveprice`,
  and re-runs the identical 959-ticker/2022-2026 universe the -26.03%/yr figure came from. State
  the exit state machine in one paragraph (30%@+2%/30%@+4%/40% on trail-or-timeout) and link to
  the design doc for the full state machine and same-bar tie-break convention rather than
  restating every detail.
- **Binary vs. partial comparison table**: side by side, from the two committed JSON files' `stats`
  blocks — `trades`, `win_rate`, `avg_pnl` (net). Then a second table, portfolio-level, N=15
  primary (citing the existing -26.03%/yr / -70.00% MDD figures from the profitability-review doc
  for the binary side, and Task 4's captured N=15 row for the partial side), N=5/10/20/30/50/100/200
  as sensitivity for both.
- **Result-tag breakdown**: from Task 4's second captured output — what fraction of trades never
  even reach +2% (`pretrigger_stop` + `pretrigger_timeout`), what fraction ride the trailing stop
  after triggering (`trail` + `target4_then_trail`), what fraction reach the +4% partial at all
  (`target4_then_trail` + `target4_then_timeout`), what fraction time out without ever using the
  trailing mechanism (`trigger_then_timeout`). This is new, previously unmeasured information about
  how often production's promised exit discipline actually engages.
- **Honest trader-perspective verdict**: does the real exit mechanism make the headline number
  better, worse, or a wash? If worse or a wash, say plainly that this shifts more of the blame for
  the -26%/yr result onto the entry signal itself (the *pattern selection* is what's broken, not
  merely a too-simple exit assumption) — do not soften this if the numbers say it. If better,
  quantify by exactly how much and state plainly whether it's enough to flip the -26%/yr
  conclusion to a positive one, or just makes a negative number less negative (be specific about
  which). No hedging into vagueness either way — this repo's standing convention for this research
  line requires a specific, honest read.
- **Limitations**: restate the design doc's Section 10 limitations verbatim in substance (daily-bar
  same-day-ordering assumption as the largest source of uncertainty, flat non-per-fill transaction
  cost, inherited Line A pipeline limitations, single run/no walk-forward, does not extend to Line
  B/sub-projects 2-7c).
- **Final recommendation**: state plainly whether this finding changes the recommended next step
  from the honest trader-perspective gap review that opened this priority list (priority-3 items:
  re-fit scoring weights against real data, isolate B지지선) — e.g. if the exit mechanism turns out
  to be a wash or negative, that reinforces re-fitting the score weights as the higher-leverage
  next step over further exit-mechanism tuning.

State explicitly that no production code (`src/swing-scanner.src.js`) was changed by this
sub-project.

- [ ] **Step 2: Commit the analysis document**

```bash
git add docs/03-analysis/swing-algo-partial-exit-simulation.analysis.md
git commit -m "docs: final analysis for swing algo sub-project 8 (partial-exit/trailing-stop simulation)"
```

---

## Self-Review Notes

- **Spec coverage**: Task 1 covers design doc Section 5 (function contract) and Section 9
  (all 8 required test cases, including both same-bar tie-break cases and the weighted-average
  arithmetic check). Task 2 covers Section 6 (wiring, `atr_pct` computation matching
  `swing_signal_engine.py`'s exact formula, CLI flag) plus its own reproducibility regression test
  for the Global Constraint that the binary default path cannot change. Task 3 covers Section 7's
  data flow (re-run against the existing universe/date-range, relying on already-populated local
  caches). Task 4 covers the portfolio-stats half of Section 7's data flow, reusing
  `analyze_portfolio_return.py` unmodified per Section 6's explicit intent. Task 5 covers the
  analysis-document requirement implied by Section 1's goal statement and restates Section 10's
  limitations.
- **Placeholder scan**: none found — Task 2's test now has a complete, hand-traced fixture
  (verified arithmetic: entry=100, trigger=102, target4=104, atr_pct falls back to
  `high[0]-low[0]=2.0` since the 5-row fixture is too short for a real ATR(14) window, giving
  `trailing_pct=0.02`; trailing levels 103*0.98=100.94 and 104*0.98=101.92 both checked against
  the fixture's actual lows to confirm no accidental early exit) rather than a placeholder. Every
  step in this plan has complete, runnable code.
- **Type consistency**: `simulate_exit_partial()`'s return keys (`exit_price`, `result`,
  `days_held`, `tranches`) match between Task 1's implementation and Task 2's consumption
  (`sim["tranches"]`, `sim["result"]`, `sim["days_held"]`, `sim["exit_price"]`) and Task 5's
  analysis instructions (`t["result"]` for the Counter breakdown). `atr_pct` is computed
  identically in Task 2's wiring as `swing_signal_engine.py`'s internal computation (same
  `calc_atr(...)[idx-1]` lookup, same NaN/zero fallback), divided by `toss.entry` per the design
  doc's Section 6 specification. The six `result` tag strings are identical across Task 1's
  docstring, Task 2's test assertions, and Task 5's breakdown instructions.

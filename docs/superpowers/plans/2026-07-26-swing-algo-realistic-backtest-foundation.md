# Swing Algorithm Realistic Backtest Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the backtest's unrealistic entry-price model with a faithful reconstruction of production's `TOSS-LIVEPRICE` block/rebase logic, add transaction-cost modeling, fix a confirmed off-by-one exposure bug, and re-run the backtest over the full 959-ticker universe and a longer date range to produce a trustworthy baseline edge measurement — with no changes to scoring, patterns, or the regime gate (that's a later, separate plan).

**Architecture:** Two new, independent, pure-function modules (`backtest/toss_liveprice.py`, `backtest/transaction_costs.py`) are wired into the existing, already-reviewed `backtest_swing_v2()` loop in `backtest/run_swing_v2_backtest.py` as a post-processing step between candidate generation and exit simulation. `backtest/simulate_exits.py` gets a one-line fix for an off-by-one bug. No changes to `backtest/swing_signal_engine.py` (candidate generation stays exactly as-is — entry/target/stop are still computed from the signal-day close; only what happens *after* that stays the same).

**Tech Stack:** Python 3.11, pandas, numpy, pytest (all already used in `backtest/`). No new dependencies.

## Global Constraints

- Do not modify `backtest/swing_signal_engine.py`, `backtest/krx_supply_history.py`, `backtest/dart_history.py`, `backtest/market_regime_history.py`, `backtest/indicators.py`, `backtest/analyze_swing_v2_results.py`, `backtest/strategy_rules.py`, or `backtest/run_backtest_swing.py` — all already reviewed and out of scope for this plan.
- `TOSS_GAP_REBASE_THRESHOLD` must be exactly `0.02` (2%), copied verbatim from `src/swing-scanner.src.js:1569`. The block conditions (`next_day_open >= target` → blocked_chasing; `next_day_open <= stop` → blocked_stopped_out) must use `>=`/`<=` exactly as production does (`src/swing-scanner.src.js:1668-1669`), not strict `>`/`<`.
- Transaction cost default is `0.002` (0.2% round-trip), documented in its docstring as an approximation of Korean sell-side 증권거래세 + brokerage commission both ways — NOT a verified current regulatory figure. Must be a keyword-overridable parameter, not a hardcoded literal baked into call sites.
- `simulate_exit`'s `hold_days` parameter must mean exactly `hold_days` trading days held, counting the entry day itself as day 1 (matching production's "최대 N거래일" semantics) — not `hold_days + 1`.
- No changes to scoring weights, pattern thresholds, the regime gate, or any new trading signal. No ML/statistical modeling. Both are out of scope for this plan (tracked as separate future plans).
- Every numeric/logic port must ship with a unit test that pins down the exact expected value — no test that only asserts "runs without error."
- New trade-dict fields (`gross_pnl`, `toss_status`) are additive only — existing consumers (`backtest/analyze_swing_v2_results.py`) access trades by specific dict key and must continue to work unmodified.

---

## File Structure Overview

| File | Status | Responsibility |
|---|---|---|
| `backtest/simulate_exits.py` | Modify | Fix off-by-one: exactly `hold_days` bars, not `hold_days + 1` |
| `backtest/toss_liveprice.py` | Create | Faithful `TOSS-LIVEPRICE` block/rebase reconstruction (pure function) |
| `backtest/transaction_costs.py` | Create | Round-trip cost deduction (pure function) |
| `backtest/run_swing_v2_backtest.py` | Modify | Wire both new functions into the per-day trade loop |
| `backtest_out_swing_v2_realistic.json` | Create (data) | Output of the re-run over the expanded universe/period |
| `docs/03-analysis/swing-algorithm-profitability-review.analysis.md` | Modify | Add three-way comparison table (naive / crude next-day-open / TOSS+fee-aware) |

---

### Task 1: Fix `simulate_exits.py`'s off-by-one exposure bug

**Files:**
- Modify: `backtest/simulate_exits.py`
- Test: `backtest/tests/test_simulate_exits.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `simulate_exit(...)` — same signature and return shape as before (`{exit_idx, exit_price, result, days_held}`), only the number of bars walked when timing out changes. Consumed by Task 4.

- [ ] **Step 1: Update the failing test for the new hold_days semantics**

Replace the existing `test_timeout_exits_at_close_of_last_holding_day` test in `backtest/tests/test_simulate_exits.py` with:

```python
def test_timeout_exits_at_close_of_entry_day_when_hold_days_is_one():
    df = _df([
        [100, 101, 99, 100],
        [100, 105, 99, 103],
        [103, 106, 102, 104],
    ])
    r = simulate_exit(df, 1, entry=100.0, stop=50.0, target=200.0, hold_days=1)
    assert r["result"] == "timeout"
    assert r["exit_price"] == 103.0  # close of entry_idx itself — hold_days=1 counts the entry day
    assert r["days_held"] == 0
```

Leave every other test in the file unchanged (`test_hits_target_first`, `test_hits_stop_first`,
`test_both_hit_same_day_is_conservative_stop`, `test_timeout_clamps_to_last_row_when_data_runs_out`)
— none of them depend on the exact hold_days boundary, they all exit before reaching it.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest backtest/tests/test_simulate_exits.py::test_timeout_exits_at_close_of_entry_day_when_hold_days_is_one -v`
Expected: FAIL — with the current code, `hold_days=1` walks 2 bars (entry_idx and entry_idx+1), so `exit_price` would be `104.0` (close of index 2) and `days_held` would be `1`, not the asserted `103.0`/`0`.

- [ ] **Step 3: Fix the off-by-one**

In `backtest/simulate_exits.py`, change line 18 from:

```python
    end = min(len(df) - 1, entry_idx + hold_days)
```

to:

```python
    end = min(len(df) - 1, entry_idx + hold_days - 1)
```

Update the docstring on line 17 from:

```python
    """Day-by-day forward walk from entry_idx: exits on first target/stop touch, else at hold_days timeout."""
```

to:

```python
    """Day-by-day forward walk from entry_idx: exits on first target/stop touch, else at
    hold_days timeout. hold_days counts the entry day itself as day 1 (matches production's
    "최대 N거래일" semantics) — hold_days=1 means only entry_idx is held."""
```

- [ ] **Step 4: Run all simulate_exits tests to verify they pass**

Run: `python -m pytest backtest/tests/test_simulate_exits.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/simulate_exits.py backtest/tests/test_simulate_exits.py
git commit -m "fix(backtest): simulate_exit holds exactly hold_days bars, not hold_days+1"
```

---

### Task 2: Faithful `TOSS-LIVEPRICE` reconstruction

**Files:**
- Create: `backtest/toss_liveprice.py`
- Test: `backtest/tests/test_toss_liveprice.py`

**Interfaces:**
- Consumes: nothing (pure function over plain floats)
- Produces: `TossOutcome` dataclass (`status: str`, `entry: float`, `target: float`, `stop: float`) and `apply_toss_liveprice(entry, target, stop, next_day_open, *, gap_rebase_threshold=0.02) -> TossOutcome`. Consumed by Task 4.

**Reference (production, `src/swing-scanner.src.js:1652-1710`):** `TOSS_GAP_REBASE_THRESHOLD = 0.02` (line 1569). Decision order: (1) `livePrice >= c.target` → `chasingRisk`, blocks the send (line 1668). (2) else `livePrice <= c.stop` → `alreadyStoppedOut`, blocks the send (line 1669). (3) else, only if not blocked, `Math.abs(gapPct) >= TOSS_GAP_REBASE_THRESHOLD` → rebase: `targetPct = c.target / c.entry - 1`, `stopPct = 1 - c.stop / c.entry`, then `c.entry = livePrice; c.target = livePrice * (1 + targetPct); c.stop = livePrice * (1 - stopPct)` (lines 1687-1697). (4) else, no change at all — small gaps are not rebased in production either. This backtest has no intraday data, so `next_day_open` is used as the only available proxy for the real 09:10 `livePrice` — document this as an explicit approximation in the module docstring.

- [ ] **Step 1: Write the failing tests**

Create `backtest/tests/test_toss_liveprice.py`:

```python
from backtest.toss_liveprice import apply_toss_liveprice


def test_small_gap_is_left_as_is():
    # gap = (101 - 100) / 100 = 1%, below the 2% threshold -> no change at all
    r = apply_toss_liveprice(entry=100.0, target=110.0, stop=90.0, next_day_open=101.0)
    assert r.status == "as_is"
    assert r.entry == 100.0
    assert r.target == 110.0
    assert r.stop == 90.0


def test_gap_exactly_at_threshold_rebases():
    # gap = (102 - 100) / 100 = exactly 2% -> production uses >=, so this rebases
    r = apply_toss_liveprice(entry=100.0, target=110.0, stop=90.0, next_day_open=102.0)
    assert r.status == "rebased"
    assert r.entry == 102.0
    # original target_pct = 10%, stop_pct = 10% -> preserved on the new entry
    assert abs(r.target - 112.2) < 1e-9
    assert abs(r.stop - 91.8) < 1e-9


def test_gap_just_below_threshold_is_as_is():
    # gap = (101.9 - 100) / 100 = 1.9%, below 2% -> no rebase
    r = apply_toss_liveprice(entry=100.0, target=110.0, stop=90.0, next_day_open=101.9)
    assert r.status == "as_is"
    assert r.entry == 100.0


def test_downward_gap_beyond_threshold_rebases():
    # gap = (97 - 100) / 100 = -3%, |gap| >= 2% -> rebase (direction-agnostic)
    r = apply_toss_liveprice(entry=100.0, target=110.0, stop=90.0, next_day_open=97.0)
    assert r.status == "rebased"
    assert r.entry == 97.0
    assert abs(r.target - 106.7) < 1e-9
    assert abs(r.stop - 87.3) < 1e-9


def test_open_at_or_above_target_blocks_as_chasing():
    r = apply_toss_liveprice(entry=100.0, target=110.0, stop=90.0, next_day_open=110.0)
    assert r.status == "blocked_chasing"


def test_open_at_or_below_stop_blocks_as_stopped_out():
    r = apply_toss_liveprice(entry=100.0, target=110.0, stop=90.0, next_day_open=90.0)
    assert r.status == "blocked_stopped_out"


def test_chasing_block_takes_priority_over_stopped_out():
    # degenerate/impossible-in-practice inputs where target <= stop: chasing check runs first
    r = apply_toss_liveprice(entry=100.0, target=90.0, stop=95.0, next_day_open=90.0)
    assert r.status == "blocked_chasing"


def test_custom_gap_rebase_threshold():
    # with a wider 5% threshold, a 2% gap should NOT rebase
    r = apply_toss_liveprice(
        entry=100.0, target=110.0, stop=90.0, next_day_open=102.0, gap_rebase_threshold=0.05
    )
    assert r.status == "as_is"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_toss_liveprice.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.toss_liveprice'`

- [ ] **Step 3: Implement**

Create `backtest/toss_liveprice.py`:

```python
"""
Faithful daily-bar reconstruction of production's TOSS-LIVEPRICE logic
(src/swing-scanner.src.js:1652-1710, added 2026-07-19).

Production computes an entry/target/stop from the prior day's close, but the actual
send happens at 09:10 using a real-time live price. If the live price already reached
target/stop by send time, the send is blocked outright; if the gap between the prior
close and the live price exceeds TOSS_GAP_REBASE_THRESHOLD, entry/target/stop are
rebased onto the live price (preserving the original target/stop distances as
percentages). Below that threshold, production does NOT rebase — the original
close-based entry stands.

NOT MODELED (approximation, documented): this backtest has no intraday tick/orderbook
data, so `next_day_open` is used as the only available proxy for the real 09:10 live
price. This is a simplification, not an exact reproduction — the true 09:10 price can
differ from the day's opening print.

NOT MODELED (out of scope): production's separate ask/bid-ratio block
(TOSS_ASK_BID_BLOCK_RATIO) and pattern-C weak-buy-ratio block (TOSS_WEAK_BUY_RATIO_C)
require real-time orderbook/trade-tape data with no historical equivalent; only the
live-price block/rebase behavior (which needs just a price, not orderbook depth) is
reconstructed here.
"""
from __future__ import annotations

from dataclasses import dataclass

TOSS_GAP_REBASE_THRESHOLD = 0.02


@dataclass(frozen=True)
class TossOutcome:
    status: str  # "as_is" | "rebased" | "blocked_chasing" | "blocked_stopped_out"
    entry: float
    target: float
    stop: float


def apply_toss_liveprice(
    entry: float,
    target: float,
    stop: float,
    next_day_open: float,
    *,
    gap_rebase_threshold: float = TOSS_GAP_REBASE_THRESHOLD,
) -> TossOutcome:
    """Port of the TOSS-LIVEPRICE block/rebase decision, using next_day_open as the
    live-price proxy. See module docstring for the approximation this implies."""
    if next_day_open >= target:
        return TossOutcome(status="blocked_chasing", entry=entry, target=target, stop=stop)
    if next_day_open <= stop:
        return TossOutcome(status="blocked_stopped_out", entry=entry, target=target, stop=stop)

    gap_pct = (next_day_open - entry) / entry
    if abs(gap_pct) >= gap_rebase_threshold:
        target_pct = target / entry - 1
        stop_pct = 1 - stop / entry
        new_entry = next_day_open
        return TossOutcome(
            status="rebased",
            entry=new_entry,
            target=new_entry * (1 + target_pct),
            stop=new_entry * (1 - stop_pct),
        )

    return TossOutcome(status="as_is", entry=entry, target=target, stop=stop)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_toss_liveprice.py -v`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/toss_liveprice.py backtest/tests/test_toss_liveprice.py
git commit -m "feat(backtest): faithful TOSS-LIVEPRICE block/rebase reconstruction"
```

---

### Task 3: Transaction cost modeling

**Files:**
- Create: `backtest/transaction_costs.py`
- Test: `backtest/tests/test_transaction_costs.py`

**Interfaces:**
- Consumes: nothing
- Produces: `DEFAULT_ROUND_TRIP_COST_PCT: float` and `apply_round_trip_cost(pnl, *, cost_pct=DEFAULT_ROUND_TRIP_COST_PCT) -> float`. Consumed by Task 4.

- [ ] **Step 1: Write the failing tests**

Create `backtest/tests/test_transaction_costs.py`:

```python
from backtest.transaction_costs import DEFAULT_ROUND_TRIP_COST_PCT, apply_round_trip_cost


def test_default_cost_is_subtracted():
    result = apply_round_trip_cost(0.05)
    assert abs(result - (0.05 - DEFAULT_ROUND_TRIP_COST_PCT)) < 1e-12


def test_default_cost_pct_is_twenty_bps():
    assert DEFAULT_ROUND_TRIP_COST_PCT == 0.002


def test_custom_cost_pct_overrides_default():
    result = apply_round_trip_cost(0.05, cost_pct=0.001)
    assert abs(result - 0.049) < 1e-12


def test_cost_can_flip_a_small_positive_pnl_negative():
    result = apply_round_trip_cost(0.001, cost_pct=0.002)
    assert result < 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_transaction_costs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.transaction_costs'`

- [ ] **Step 3: Implement**

Create `backtest/transaction_costs.py`:

```python
"""
Transaction cost modeling for backtest PnL.

DEFAULT_ROUND_TRIP_COST_PCT (0.2%) is an APPROXIMATION of a Korean round-trip retail
equity trade (sell-side 증권거래세 / securities transaction tax, plus brokerage
commission both ways) — it is not sourced from a verified, current regulatory or
broker-specific rate table. Confirm and adjust the actual figure before using this for
real capital-allocation decisions.
"""
from __future__ import annotations

DEFAULT_ROUND_TRIP_COST_PCT = 0.002


def apply_round_trip_cost(pnl: float, *, cost_pct: float = DEFAULT_ROUND_TRIP_COST_PCT) -> float:
    """Returns pnl minus an approximate round-trip trading cost, both expressed as
    fractions (e.g. 0.05 = 5%, 0.002 = 0.2%)."""
    return pnl - cost_pct
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_transaction_costs.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backtest/transaction_costs.py backtest/tests/test_transaction_costs.py
git commit -m "feat(backtest): round-trip transaction cost modeling"
```

---

### Task 4: Wire TOSS-LIVEPRICE and transaction costs into the backtest loop

**Files:**
- Modify: `backtest/run_swing_v2_backtest.py`
- Test: `backtest/tests/test_run_swing_v2_backtest.py`

**Interfaces:**
- Consumes: `toss_liveprice.apply_toss_liveprice` (Task 2), `transaction_costs.apply_round_trip_cost` (Task 3), `simulate_exits.simulate_exit` (Task 1's fixed version — no interface change, same signature)
- Produces: `backtest_swing_v2(...)`'s trade dicts now additionally include `"gross_pnl": float` (pre-cost) and `"toss_status": str` (`"as_is"`/`"rebased"`) per trade; `pnl` is now net-of-cost. The stats dict additionally includes `"blocked_by_toss": List[Dict[str, str]]` (same shape as the existing `skipped_tickers`: `{"date": ..., "ticker": ..., "code": ..., "reason": "blocked_chasing"|"blocked_stopped_out"}`). No other keys change. Consumed by Task 5 (the real re-run) and by `analyze_swing_v2_results.py` (unmodified — reads `pattern_type`/`score`/`grade`/`pnl`/`date`, all still present).

**Reference:** the existing per-trade loop is `backtest/run_swing_v2_backtest.py:114-133` (as of commit `bbd8889`); the existing empty-trades branch is lines 136-139; the existing non-empty stats dict is lines 150-158.

- [ ] **Step 1: Write the failing test**

Add to `backtest/tests/test_run_swing_v2_backtest.py` (this file already exists with tests for `apply_daily_selection` and other backtest-loop behavior — add these as new test functions, keep existing ones untouched):

```python
def test_backtest_swing_v2_blocks_trade_on_chasing_risk(monkeypatch):
    import pandas as pd
    from backtest import run_swing_v2_backtest as mod

    ticker = "000001.KS"
    # 3 daily bars: signal day (idx 1), next day (idx 2) whose OPEN already blows past
    # a synthetic candidate's target -> must be blocked, not simulated/recorded.
    df = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04"], utc=True
        ),
        "open": [100.0, 200.0, 200.0],
        "high": [101.0, 205.0, 205.0],
        "low": [99.0, 195.0, 195.0],
        "close": [100.0, 200.0, 200.0],
        "volume": [1_000_000.0, 1_000_000.0, 1_000_000.0],
    })

    monkeypatch.setattr(
        mod, "fetch_yahoo_chart", lambda spec: {"_fake_for": spec.ticker}
    )
    monkeypatch.setattr(
        mod, "chart_to_ohlcv_daily", lambda data: (df.copy(), None)
    )
    monkeypatch.setattr(mod, "fetch_supply_for_date", lambda trd_dd: {})
    monkeypatch.setattr(mod, "fetch_disclosures_for_date", lambda trd_dd, api_key: {})

    from backtest.swing_signal_engine import SwingCandidate

    def fake_evaluate_candidate(df_arg, idx, *, supply, dart_items, day_of_week):
        if idx != 1:
            return None
        # entry=100 (signal day close), target=110 -> next day's open (200) blows past it
        return SwingCandidate(
            pattern_type="D박스", score=100, rank_score=100, grade="매수",
            entry=100.0, target=110.0, stop=90.0, hold_days=3, signals=[],
        )

    monkeypatch.setattr(mod, "evaluate_candidate", fake_evaluate_candidate)

    df_trades, stats = mod.backtest_swing_v2([ticker], start="2024-01-01", end="2024-01-05")

    assert df_trades.empty or ticker not in df_trades.get("ticker", pd.Series(dtype=str)).values
    assert stats.get("blocked_by_toss") or stats.get("reason") == "no_trades"
    if "blocked_by_toss" in stats:
        assert stats["blocked_by_toss"][0]["reason"] == "blocked_chasing"


def test_backtest_swing_v2_records_toss_status_and_net_pnl(monkeypatch):
    import pandas as pd
    from backtest import run_swing_v2_backtest as mod

    ticker = "000002.KS"
    # signal day close=100 (idx 1), next day open=101 (idx 2, 1% gap -> as_is, no rebase),
    # then a bar that hits the target so the trade resolves deterministically.
    df = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04"], utc=True
        ),
        "open": [100.0, 101.0, 101.0],
        "high": [101.0, 102.0, 115.0],
        "low": [99.0, 100.0, 100.0],
        "close": [100.0, 101.0, 112.0],
        "volume": [1_000_000.0, 1_000_000.0, 1_000_000.0],
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

    df_trades, stats = mod.backtest_swing_v2([ticker], start="2024-01-01", end="2024-01-05")

    assert stats["trades"] == 1
    row = df_trades.iloc[0]
    assert row["toss_status"] == "as_is"
    assert row["result"] == "target"
    assert abs(row["gross_pnl"] - 0.10) < 1e-9  # (110 - 100) / 100
    assert abs(row["pnl"] - (0.10 - 0.002)) < 1e-9  # net of default 0.2% cost
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_run_swing_v2_backtest.py -v -k "toss_status or chasing_risk"`
Expected: FAIL — `AttributeError` (no `toss_status`/`blocked_by_toss`/etc. yet) or `AssertionError` on the pnl values, since none of the new wiring exists yet.

- [ ] **Step 3: Implement the wiring**

In `backtest/run_swing_v2_backtest.py`, add the two new imports near the top (after the existing `from .simulate_exits import simulate_exit` line):

```python
from .simulate_exits import simulate_exit
from .toss_liveprice import apply_toss_liveprice
from .transaction_costs import apply_round_trip_cost
```

Initialize a `blocked_by_toss` list alongside the existing `week_state`/`code_to_ticker` initialization (right after the `code_to_ticker = {_code_of(t): t for t in tickers}` line):

```python
    blocked_by_toss: List[Dict[str, str]] = []
```

Replace the per-trade loop body (currently `run_swing_v2_backtest.py:115-133`) — the `for code, cand in selected:` block — with:

```python
        for code, cand in selected:
            ticker = code_to_ticker[code]
            df = per_ticker[ticker]
            entry_idx = int(df.index[df["timestamp_utc"] == day][0]) + 1
            if entry_idx >= len(df):
                continue
            next_day_open = float(df.iloc[entry_idx]["open"])
            toss = apply_toss_liveprice(cand.entry, cand.target, cand.stop, next_day_open)
            if toss.status in ("blocked_chasing", "blocked_stopped_out"):
                blocked_by_toss.append({
                    "date": day.isoformat(), "ticker": ticker, "code": code, "reason": toss.status,
                })
                continue
            sim = simulate_exit(
                df, entry_idx,
                entry=toss.entry, stop=toss.stop, target=toss.target, hold_days=cand.hold_days,
            )
            gross_pnl = (float(sim["exit_price"]) - toss.entry) / toss.entry
            pnl = apply_round_trip_cost(gross_pnl)
            trades.append({
                "date": day.isoformat(), "ticker": ticker, "code": code,
                "pattern_type": cand.pattern_type, "grade": cand.grade,
                "score": cand.score, "rank_score": cand.rank_score,
                "entry": toss.entry, "stop": toss.stop, "target": toss.target,
                "exit_price": float(sim["exit_price"]), "result": sim["result"],
                "days_held": sim["days_held"], "pnl": pnl,
                "gross_pnl": gross_pnl, "toss_status": toss.status,
            })
```

Replace the empty-trades branch (currently `run_swing_v2_backtest.py:136-139`):

```python
    if df_trades.empty:
        if skipped_tickers:
            return df_trades, {"reason": "no_trades", "skipped_tickers": skipped_tickers}
        return df_trades, {"reason": "no_trades"}
```

with:

```python
    if df_trades.empty:
        empty_stats: Dict[str, Any] = {"reason": "no_trades"}
        if skipped_tickers:
            empty_stats["skipped_tickers"] = skipped_tickers
        if blocked_by_toss:
            empty_stats["blocked_by_toss"] = blocked_by_toss
        return df_trades, empty_stats
```

And add `"blocked_by_toss": blocked_by_toss,` as a new key in the final (non-empty) `stats` dict (currently `run_swing_v2_backtest.py:150-158`), right after the existing `"skipped_tickers": skipped_tickers,` line.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_run_swing_v2_backtest.py -v`
Expected: all tests pass, including the two new ones (existing tests for `apply_daily_selection` etc. are untouched and must still pass).

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest backtest/tests -v`
Expected: all tests pass (60 previous + this plan's Tasks 1-4 additions — 1 renamed/updated + 8 new in Task 2 + 4 new in Task 3 + 2 new in Task 4 = 74 total; exact count isn't load-bearing, zero failures is).

- [ ] **Step 6: Commit**

```bash
git add backtest/run_swing_v2_backtest.py backtest/tests/test_run_swing_v2_backtest.py
git commit -m "feat(backtest): wire TOSS-LIVEPRICE blocking/rebasing and transaction costs into the trade loop"
```

---

### Task 5: Run the real backtest over the expanded universe and date range

**Files:** none created except the output JSON — this is an execution-only task.

- [ ] **Step 1: Confirm the ticker universe file**

Run: `wc -l backtest/tickers_operating.txt`
Expected: `959` (already built, no action needed if this matches)

- [ ] **Step 2: Kick off the backtest run in the background**

Run (background — this covers ~5x more tickers and 2x the date range of the prior 200-ticker/2-year run, which itself took considerable wall-clock time; expect this to take substantially longer — plausibly 1-3+ hours given the per-day KRX/DART calls now iterate over more trading days and the per-ticker candidate evaluation loop now covers ~959 tickers):

```bash
python -m backtest.run_swing_v2_backtest --tickers backtest/tickers_operating.txt --start 2022-01-01 --end 2026-01-01 --out backtest_out_swing_v2_realistic.json
```

Expected: eventually prints `wrote backtest_out_swing_v2_realistic.json` followed by a JSON stats block including `trades`, `win_rate`, `avg_pnl`, `median_pnl`, `mdd`, `equity_end`, `skipped_tickers`, `blocked_by_toss`.

- [ ] **Step 3: Sanity-check the output**

Run:
```bash
python -c "
import json
d = json.load(open('backtest_out_swing_v2_realistic.json', encoding='utf-8'))
print(d['stats'])
print('sample trade:', d['trades'][0] if d['trades'] else None)
print('skipped tickers:', len(d['stats'].get('skipped_tickers', [])))
print('blocked by toss:', len(d['stats'].get('blocked_by_toss', [])))
"
```
Expected: `trades` count should be roughly proportional to the prior 1,202-trade/200-ticker/2-year run scaled up (expect low thousands to tens of thousands given ~5x tickers and 2x period — exact figure not load-bearing, but 0 trades or any NaN in `avg_pnl`/`mdd` means stop and debug rather than proceeding, per the same rule as the original Task 8). `blocked_by_toss` should be a non-trivial but not overwhelming fraction of pre-block candidates (a handful of percent, not the majority) — if `blocked_by_toss` is empty/zero across a run this size, that's a strong signal the wiring in Task 4 isn't actually being exercised and needs investigation before proceeding.

- [ ] **Step 4: Commit the raw result for reproducibility**

```bash
git add backtest_out_swing_v2_realistic.json
git commit -m "data(backtest): realistic (TOSS-aware, fee-aware) swing v2 backtest output, 959 tickers 2022-01-01..2026-01-01"
```

---

### Task 6: Update the profitability report with a three-way comparison

**Files:**
- Modify: `docs/03-analysis/swing-algorithm-profitability-review.analysis.md`

- [ ] **Step 1: Compute summary stats for the new run**

Run:
```bash
python -c "
import json
d = json.load(open('backtest_out_swing_v2_realistic.json', encoding='utf-8'))
s = d['stats']
print('trades:', s['trades'])
print('win_rate:', round(s['win_rate']*100, 2))
print('avg_pnl (net of fees):', round(s['avg_pnl']*100, 3))
print('median_pnl:', round(s['median_pnl']*100, 2))
print('mdd:', round(s['mdd']*100, 2))
print('equity_end:', round(s['equity_end'], 2))
print('blocked_by_toss count:', len(s.get('blocked_by_toss', [])))
print('skipped_tickers count:', len(s.get('skipped_tickers', [])))
"
```

- [ ] **Step 2: Add a three-way comparison section**

In `docs/03-analysis/swing-algorithm-profitability-review.analysis.md`, immediately after the
existing "Entry-fill model books the overnight gap as free profit" Limitations bullet (added in
the prior session's final-review fix), add a new subsection under **Empirical Backtest Results**
titled `### Entry-model comparison: naive vs. crude approximation vs. TOSS-aware + fee-aware`
with a table using the real numbers from Step 1, structured as:

```markdown
| Entry model | Universe | Trades | Win rate | Avg PnL (net where noted) |
|---|---|---|---|---|
| Signal-day close (naive, original committed baseline) | 200 tickers, 2y | 1,202 | 40.68% | +0.886% (gross) |
| Crude next-day-open approximation (same-session sensitivity check) | 200 tickers, 2y | 1,202 | 39.68% | +0.142% (gross) |
| TOSS-LIVEPRICE-aware + fee-aware (this sub-project) | 959 tickers, 4y | [from Step 1] | [from Step 1] | [from Step 1] (net of ~0.2% round-trip cost) |
```

Fill in every `[from Step 1]` placeholder with the real numbers — do not leave any bracket in
the committed file. Write one paragraph interpreting the comparison: does the TOSS-aware/fee-aware
number land closer to the naive or the crude-approximation figure, and is it positive or negative
net of costs? State this plainly without over- or under-selling it (same standard applied to the
prior session's entry-fill correction).

- [ ] **Step 3: Commit**

```bash
git add docs/03-analysis/swing-algorithm-profitability-review.analysis.md
git commit -m "docs: add TOSS-aware + fee-aware backtest comparison to profitability review"
```

---

## Self-Review Notes

- **Spec coverage:** every in-scope item from `docs/superpowers/specs/2026-07-26-swing-algo-realistic-backtest-foundation-design.md` maps to a task — TOSS-LIVEPRICE reconstruction (Task 2), transaction costs (Task 3), hold_days off-by-one (Task 1), wiring (Task 4), universe/date-range expansion (Task 5), comparison report (Task 6).
- **Placeholder scan:** Task 6's table contains `[from Step 1]` placeholders by design — they don't exist until Task 5's real run completes, exactly like Task 11 in the prior plan; Step 2 explicitly requires filling every one in before committing. No other task contains a placeholder.
- **Type consistency:** `TossOutcome`'s fields (`status, entry, target, stop`) are used identically in Task 2's tests and Task 4's wiring code. `apply_round_trip_cost`'s `cost_pct` keyword name matches between Task 3's definition and Task 4's (implicit, default-only) usage. The new trade-dict keys (`gross_pnl`, `toss_status`) are introduced once in Task 4 and consumed nowhere else in this plan (Task 6 only reads aggregate `stats`, not individual trades) — no drift risk within this plan.
- **Scope check:** single cohesive subsystem (backtest realism), matching the sub-project boundary drawn during brainstorming. Sub-projects 2 (rule re-tuning) and 3 (ML) are explicitly out of scope and will get their own plans after this one's results are in hand.

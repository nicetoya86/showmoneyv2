# Swing Algorithm Enhancement — Sub-project 1: Realistic Backtest Foundation

## Context and Goal

**Overall goal (out of scope for this document, tracked as future sub-projects):** enhance the
production swing-trading algorithm (`src/swing-scanner.src.js`) toward a target of 50%+ annual
returns. Only reachable, if at all, by materially increasing the algorithm's real per-trade edge
— not by adding leverage or larger position sizes (explicitly ruled out).

**Why this comes first:** the most recent backtest (`docs/03-analysis/swing-algorithm-profitability-review.analysis.md`)
found that the previously-reported +0.89% average per-trade edge was mostly an artifact of an
unrealistic entry-price assumption (booking the overnight gap to next-day open as free profit).
A cruder same-session correction estimated a more realistic +0.14% avg PnL / 39.68% win rate, but
that correction was itself a simplification (always re-price at next-day open) — it does not
reflect what production's own `TOSS-LIVEPRICE` logic (src/swing-scanner.src.js:1652-1710) actually
does with a gap. It also didn't model transaction costs, and it ran over too small a sample
(200 tickers × 2 years = 1,202 trades) to reliably re-derive ~22 hand-tuned scoring weights in a
later phase.

Before spending effort improving the algorithm's edge, we need a **trustworthy measurement** of
what edge it actually has today. That is the sole deliverable of this sub-project.

## Roadmap (for context — only item 1 is designed/built here)

1. **[This document] Realistic backtest foundation** — faithful TOSS-LIVEPRICE entry-price
   modeling, transaction costs, and an expanded universe/date range for statistical adequacy.
2. **Rule-based re-tuning** (separate future spec, designed after seeing this sub-project's
   results) — remove the 60-89 losing score tier, re-examine the D박스 pattern, restore the dead
   regime gate, add new backtestable signals (weekly-trend alignment, sector/theme relative
   strength, volatility-contraction patterns), re-derive score weights statistically from the
   expanded dataset.
3. **Statistical/ML model** (separate future spec) — logistic regression or gradient-boosted
   classifier trained on the expanded dataset with a strict train/test time split, compared
   against the rule-based result from (2).

## Scope of This Sub-project

**In scope:**
- A faithful, daily-bar-appropriate reconstruction of `TOSS-LIVEPRICE`'s block/rebase behavior,
  applied as a post-processing step over the existing (unmodified) signal-generation logic.
- Transaction cost modeling (round-trip fee/tax).
- A fix for a confirmed off-by-one exposure bug (`hold_days + 1` bars simulated instead of
  `hold_days`).
- Expanding the backtest universe from 200 to the full 959-ticker operating universe
  (`backtest/tickers_operating.txt`, already built) and the date range from 2 to ~4 years
  (2022-01-01 → 2026-01-01), reusing already-fetched 5-year Yahoo history.
- Re-running the backtest (still using **today's existing, un-retuned** scoring/pattern logic —
  no algorithm changes yet) over the expanded universe/period with the above fixes, and reporting
  the resulting numbers alongside the prior (naive) figures for comparison.

**Explicitly out of scope (deferred to sub-project 2):**
- Any change to scoring weights, pattern thresholds, the regime gate, or new signals.
- Any ML/statistical modeling.

## Architecture

The existing, already-reviewed modules (`swing_signal_engine.py`, `run_swing_v2_backtest.py`,
`simulate_exits.py`, etc.) are not modified in their core candidate-generation or exit-simulation
logic. Two new, independent, pure-function modules are inserted as a post-processing layer between
candidate generation and the existing exit simulator:

```
[existing, unmodified] evaluate_candidate()
        → SwingCandidate(entry=signal-day close, target, stop, ...)
                ↓
[NEW] backtest/toss_liveprice.py : apply_toss_liveprice(candidate, next_day_open)
        → TossOutcome(status: "as_is" | "rebased" | "blocked_chasing" | "blocked_stopped_out",
                       entry, target, stop)
                ↓  (only "as_is"/"rebased" candidates proceed; "blocked_*" candidates are
                     recorded as blocked and do not enter the exit simulator)
[existing, unmodified] simulate_exit()
                ↓
[NEW] backtest/transaction_costs.py : apply_round_trip_cost(pnl) → net_pnl
```

This keeps the fidelity-critical, already-reviewed engine untouched, and makes the new behavior
independently unit-testable as small, pure functions.

## Components

### `backtest/toss_liveprice.py` (new)

**Produces:** `apply_toss_liveprice(entry: float, target: float, stop: float, next_day_open: float, *, gap_rebase_threshold: float = 0.02) -> TossOutcome`

Reconstructs `src/swing-scanner.src.js:1652-1710`'s decision using `next_day_open` as the only
available proxy for the real 09:10 live price (no intraday data exists in this daily-bar
backtest — documented as an explicit approximation, same as the existing regime-history
module's documented simplifications):

1. If `next_day_open >= target` → `blocked_chasing` (production would refuse to send this).
2. Else if `next_day_open <= stop` → `blocked_stopped_out` (setup already invalidated).
3. Else if `abs(next_day_open - entry) / entry >= gap_rebase_threshold` (2%, matching
   `TOSS_GAP_REBASE_THRESHOLD` verbatim) → `rebased`: recompute `entry = next_day_open`,
   preserving the original `target_pct`/`stop_pct` distances (exactly mirroring the JS: `targetPct
   = c.target / c.entry - 1`, `stopPct = 1 - c.stop / c.entry`, then reapplied to the new entry).
4. Else → `as_is`: entry/target/stop unchanged (small gaps are not rebased in production either —
   this is the one case where the existing, "naive" entry model is already production-faithful).

Blocked candidates are excluded from the trade list entirely (mirroring "발송 자체가 안 됨" in
production) but their count and blocking reason are recorded in the run's output stats, the same
way `skipped_tickers` is already recorded, so the report can state how many trades were removed
by this gate and why.

### `backtest/transaction_costs.py` (new)

**Produces:** `apply_round_trip_cost(pnl: float, *, cost_pct: float = 0.002) -> float`

Simple `pnl - cost_pct`. `cost_pct` defaults to 0.2% (documented in the docstring as an
approximation of Korean sell-side 증권거래세 + brokerage commission both ways — the exact figure
depends on broker/account type and should be confirmed/adjusted by whoever consumes this for real
trading decisions; it is not sourced from a verified current regulatory table).

### `backtest/simulate_exits.py` (existing, one-line fix)

Fix the confirmed off-by-one: the exit loop currently walks `hold_days + 1` bars
(`range(entry_idx, entry_idx + hold_days + 1)`); change to walk exactly `hold_days` bars,
matching production's "최대 N거래일" (counts the entry day itself). Add a regression test pinning
the corrected bar count.

### `backtest/run_swing_v2_backtest.py` (existing, wiring change only)

Wire the two new functions into the existing per-day loop: after `evaluate_candidate` produces a
candidate and before `simulate_exit`, look up the candidate's ticker's next trading day's open
(already available in the per-ticker DataFrame already loaded for exit simulation — no new data
fetch needed) and call `apply_toss_liveprice`. Blocked candidates never reach `simulate_exit`.
After `simulate_exit` returns a raw pnl, pass it through `apply_round_trip_cost` before recording
the trade. No other change to this file's existing, already-reviewed selection-cap logic.

**[Reconciled post-implementation]** The actual wiring places the TOSS check *after*
`apply_daily_selection` (inside the `for code, cand in selected:` loop), not before it as this
paragraph originally said — this matches what Task 4 of the implementation plan specified, but
this design paragraph was never updated to match. The practical effect: a TOSS-blocked candidate
still consumes its weekly-send-quota slot in this backtest, whereas production only books the
slot on a successful send (`src/swing-scanner.src.js:1825`), so production would refill that slot
with the next-ranked candidate and this backtest does not. Measured impact and full analysis:
`docs/03-analysis/swing-algorithm-profitability-review.analysis.md`, "TOSS-blocked candidates
consume this backtest's weekly send quota; production's do not" (~109 of 2,686 trades, ≈4%).
Moving the check before selection to close this gap is deferred to sub-project 2, since it
changes which candidates are selected per week and thus overlaps with that sub-project's planned
re-tuning work rather than being a pure fidelity fix.

### Universe/date-range expansion

`backtest/tickers_operating.txt` (959 tickers, already built) replaces
`tickers_operating_200.txt` as the default input. Date range changes from
`2024-01-01..2026-01-01` to `2022-01-01..2026-01-01`, both within the already-fetched 5-year
Yahoo history — no new fetch-range parameter needed, only the `--start`/`--end` CLI args to the
existing orchestration script change. This is a data-volume change only; no code changes required
beyond what's already resilient (per-ticker fetch failures are already handled from the prior
session's hardening work, and delisted/newly-listed tickers over a wider universe are exactly the
failure mode that hardening already covers).

## Error Handling

No new failure modes are introduced beyond what's already handled: `apply_toss_liveprice` and
`apply_round_trip_cost` are pure functions over already-validated numeric inputs (no I/O, no
exceptions expected). The larger universe increases the *frequency* of already-handled cases
(delisted tickers, thin/short history) but not their *nature* — the existing per-ticker
try/except resilience (added in a prior fix round) already covers this.

## Testing

- `backtest/toss_liveprice.py`: one test per branch (`as_is`, `rebased` with correct
  entry/target/stop recomputation, `blocked_chasing`, `blocked_stopped_out`), plus a boundary test
  at exactly the 2% threshold.
- `backtest/transaction_costs.py`: a single direct test of the subtraction.
- `backtest/simulate_exits.py`: update/add a test pinning exactly `hold_days` bars simulated
  (not `hold_days + 1`).
- Integration: re-run the real backtest over the expanded universe/period and sanity-check the
  output the same way Task 8 did previously (trade count in a sane range, win rate in [0,1], no
  NaN, blocked-trade counts reported). Update
  `docs/03-analysis/swing-algorithm-profitability-review.analysis.md` (or a new dated report) with
  a three-way comparison table: **naive (+0.886%, current committed baseline)** vs **crude
  next-day-open approximation (+0.14%, this session's earlier sensitivity check)** vs **TOSS-aware
  + fee-aware + expanded-universe (this sub-project's final number)**.

## Out of Scope / Explicit Non-Goals

- No scoring/pattern/regime changes (sub-project 2).
- No ML (sub-project 3).
- No claim about whether 50%/year is achievable — this sub-project only produces a trustworthy
  baseline number; whether that baseline, once improved by sub-projects 2-3, can plausibly reach
  50%/year is an open question this document does not answer.

# Swing Algorithm Enhancement — Sub-project 2: Target/Stop & Threshold Retuning for High Hit-Rate

## Context and Goal

**Where sub-project 1 left off:** the realistic (TOSS-LIVEPRICE-aware, fee-aware) backtest over the
full 959-ticker universe (2022-01-01..2026-01-01) found the current, un-retuned algorithm has a
**negative** expected edge: -0.478% avg PnL/trade, 32.17% hit rate, and roughly -26%/year expected
return under a realistic 15-concurrent-slot portfolio model (`docs/03-analysis/swing-algorithm-profitability-review.analysis.md`,
"Portfolio-level expected annual return" section).

**This sub-project's goal, as clarified with the user:** re-derive the algorithm's target-price,
stop-loss, minimum-score, and regime-gate parameters so that, if achievable, **at least 90% of
recommended trades reach a minimum +3% profit target**, while keeping **at least ~5 recommendations
per week** and an overall **positive expected return**. "90%" refers to hit-rate (fraction of trades
that reach the profit target before stopping out or timing out), not annualized return.

**Explicit, agreed expectation-setting:** hit-rate and reward-to-risk are structurally in tension —
a smaller, easier-to-reach target mechanically raises hit-rate but shrinks the per-win payoff, and a
wider stop reduces stop-outs but increases the loss when one does occur. This sub-project is a
**search for the best available trade-off**, not a guarantee that a config satisfying all three
constraints (90% hit-rate, ≥5/week, positive return) simultaneously exists. If no such config is
found on the training data, that negative result will be reported plainly, not papered over by
loosening the constraints after the fact.

## Roadmap Context (from sub-project 1's design doc)

1. ~~Realistic backtest foundation~~ (sub-project 1, done — commit `ed07c9b`)
2. **[This document] Target/stop/threshold retuning for hit-rate** — reuses the existing,
   unmodified candidate-generation pipeline (scoring/pattern logic untouched); re-derives only the
   target price, stop-loss, minimum score, regime gate, and D박스 inclusion via a grid search with a
   train/test split.
3. **New signals** (deferred, conditional) — weekly-trend alignment, sector/theme relative
   strength, volatility-contraction patterns. Only pursued as a follow-up if this sub-project's
   grid search cannot jointly satisfy hit-rate/frequency/profitability using the existing candidate
   pool — per YAGNI, not built speculatively.
4. **Statistical/ML model** (separate future spec, unchanged from sub-project 1's roadmap).

## Scope of This Sub-project

**In scope:**
- A new pure-function grid-search harness over: target_pct (flat, not ATR-scaled — floor 3%),
  stop_pct (flat), minimum score threshold (60 / 90 / 110), regime-gate on/off, D박스
  pattern include/exclude.
- Reusing `evaluate_candidate()` (`backtest/swing_signal_engine.py`) **completely unmodified** —
  the candidate population (which ticker/day combinations qualify as a signal, and their
  `pattern_type`/`score`/`grade`/`hold_days`) stays exactly as sub-project 1 generated it. This
  sub-project only re-decides *target/stop/inclusion*, not *what counts as a signal*.
- Reusing `apply_toss_liveprice()`, `simulate_exit()`, `apply_round_trip_cost()`
  (`backtest/toss_liveprice.py`, `backtest/simulate_exits.py`, `backtest/transaction_costs.py`)
  completely unmodified — each grid cell just calls them with different target/stop values.
- Reusing `backtest/market_regime_history.py` completely unmodified, calling its existing
  regime-level computation from the new grid-search module to gate candidates (restoring the
  "dead code" regime block, without touching the module that computes it).
- A chronological train (2022-01-01..2024-06-30) / test (2024-07-01..2026-01-01) split. Grid
  search and config selection happen only on train; the selected config is evaluated exactly once
  on test, and both numbers are reported side by side.
- A new analysis document reporting the grid search results, the selected config (or the Pareto
  frontier if no config satisfies all three constraints), and train-vs-test numbers.

**Explicitly out of scope (deferred):**
- Any change to `evaluate_candidate()`'s pattern/scoring logic itself (signal generation stays
  exactly as-is).
- ATR-scaled (as opposed to flat-percentage) target/stop — flat percentages are simpler to reason
  about, match the user's own framing (e.g. "target=3%, stop=2%"), and reduce the grid's
  dimensionality (fewer confounded axes = lower overfitting risk for a first pass).
- New signals (weekly-trend alignment, sector/theme relative strength, volatility-contraction) —
  conditional future work, see Roadmap Context above.
- Deploying any resulting config to `src/swing-scanner.src.js` — this sub-project produces a
  recommendation and evidence; production deployment is a separate, later decision.

## Architecture

Two sequential phases, both new, both built on sub-project 1's already-reviewed pure functions:

```
Phase 1 (candidate + forward-path caching):
  [existing, unmodified] evaluate_candidate() over 959 tickers x 2022-01-01..2026-01-01
        → candidate (ticker, date, entry, pattern_type, score, grade, hold_days)
                ↓
  [NEW] backtest/generate_signal_candidates.py
        → attaches each candidate's forward OHLC window (open/high/low/close for
          entry_idx..entry_idx+hold_days) and next_day_open, needed to evaluate ANY
          target/stop choice without re-fetching or re-scoring
        → written to backtest_candidates_with_paths.json (or equivalent)

Phase 2 (grid search over cached candidates, train/test split):
  [NEW] backtest/target_stop_grid_search.py, consuming Phase 1's cache
        → for each grid cell (target_pct, stop_pct, min_score, regime_gate, exclude_d_box):
            filter candidates by min_score/regime_gate/pattern
                ↓
          [existing, unmodified] apply_toss_liveprice(entry, target, stop, next_day_open)
                ↓
          [existing, unmodified] simulate_exit(df_window, entry_idx, entry=toss.entry,
                                                stop=toss.stop, target=toss.target,
                                                hold_days=hold_days)
                ↓
          [existing, unmodified] apply_round_trip_cost(gross_pnl)
                ↓
            aggregate: hit_rate, trades/week, avg pnl, 15-slot portfolio CAGR
                        (reusing backtest/analyze_portfolio_return.py's simulate_portfolio)
        → selection runs on train split only; selected config re-evaluated once on test split
        → both written to docs/03-analysis/swing-algo-target-stop-retuning.analysis.md
```

No changes to `swing_signal_engine.py`, `toss_liveprice.py`, `simulate_exits.py`,
`transaction_costs.py`, `market_regime_history.py`, or `analyze_portfolio_return.py` — all
consumed as-is via their existing function signatures.

## Components

### `backtest/generate_signal_candidates.py` (new)

**Produces:** a JSON/pickle artifact with one record per candidate:
`{ticker, code, date, entry, pattern_type, score, grade, hold_days, next_day_open,
window_open[], window_high[], window_low[], window_close[]}` where the `window_*` arrays cover
`entry_idx .. entry_idx + max_possible_hold_days - 1` (max over all grades/patterns'
`_hold_days()` values), so any grid cell's `hold_days` (fixed per candidate, from
`_hold_days(grade, pattern_type)` — unaffected by the target/stop grid) can slice the exact window
it needs without re-fetching.

**Consumes:** `evaluate_candidate()` (unmodified), the same per-ticker Yahoo OHLCV frames sub-project
1 used (reused from `backtest/yahoo_cache.py`'s disk cache — no new fetches expected for tickers
already cached; the 4 tickers sub-project 1 found unfetchable stay unfetchable, same as before).

### `backtest/target_stop_grid_search.py` (new)

**Produces:** `run_grid_search(candidates, grid, regime_lookup) -> List[GridResult]`, where
`GridResult` carries the grid-cell parameters plus `{hit_rate, trades_per_week, avg_pnl, cagr_15slot,
n_trades}` computed separately for train and test.

**Consumes:** Phase 1's cached candidates; `apply_toss_liveprice`, `simulate_exit`,
`apply_round_trip_cost` (all unmodified, called per grid cell per candidate); a `regime_lookup`
callable backed by `backtest/market_regime_history.py`'s existing (unmodified) regime-level
function, keyed by date, applying the same block rule already dead in production
(`regimeLevel >= 2 and grade != '강매' → excluded`) when `regime_gate=True`.

**Selection rule (train split only):** among grid cells with `hit_rate >= 0.90` and
`trades_per_week >= 5`, pick the one maximizing `cagr_15slot`. If none qualify, apply this
explicit fallback (not a vague "closeness score"): (1) filter to `trades_per_week >= 5` only —
the frequency floor is a hard constraint agreed with the user, not negotiable; (2) among that
filtered set, sort by `hit_rate` descending, then by `cagr_15slot` descending as a tiebreaker;
(3) report the top 5 rows of that sort plus the single best-`cagr_15slot` row overall (even if it
fails the frequency floor), so the reader can see both "closest to 90% while still meeting
frequency" and "best possible return regardless of frequency." Clearly state in the output that
the joint target was not met on training data when this fallback path is taken.

**Test evaluation:** run the single selected config (or, if no config qualified, the single
best-composite-score config) on the test split exactly once — no adjustment after seeing test
results.

## Error Handling

No new failure modes: Phase 1 reuses sub-project 1's already-resilient per-ticker fetch handling
(skip delisted/failed tickers, same 4 tickers expected to remain unfetchable). Phase 2 operates
purely on already-validated, already-cached numeric data — no I/O, no exceptions expected beyond
standard input-shape validation.

## Testing

- `generate_signal_candidates.py`: a test confirming the cached window arrays match the source
  ticker DataFrame for a known synthetic candidate (index alignment, correct length).
- `target_stop_grid_search.py`: value-pinning tests per branch —
  - a synthetic candidate set where a known target/stop combination is hit vs. not hit (reusing
    `simulate_exit`'s existing tested behavior, verifying correct wiring rather than
    re-testing `simulate_exit` itself).
  - regime-gate on/off: a candidate on a date with `regimeLevel=2` and `grade='매수'` is excluded
    when `regime_gate=True`, included when `False`; a `grade='강매'` candidate on the same date is
    included in both cases (matches production's original blocking rule).
  - D박스 exclude: a `pattern_type='D박스'` candidate is dropped when `exclude_d_box=True`.
  - min_score thresholds: candidates with `score` in [60,90) are excluded when `min_score=90`.
  - train/test date-boundary test: a candidate dated exactly `2024-06-30` is train; `2024-07-01`
    is test.
- Integration: run the real 2-phase pipeline over the 959-ticker universe, confirm no NaN in any
  grid cell's aggregates, and confirm the selected config's train numbers are internally consistent
  (e.g., `hit_rate` recomputed independently from raw per-trade results matches the reported value).

## Out of Scope / Explicit Non-Goals

- No claim that 90% hit-rate, ≥5/week frequency, and positive return are jointly achievable — this
  document specifies how to search for the best available trade-off and report honestly, not a
  guaranteed outcome.
- No production code changes (`src/swing-scanner.src.js`) — this sub-project stops at a
  backtested recommendation; deployment is a separate future decision made after reviewing results.
- No new signals — deferred to a conditional sub-project 3 (only if this sub-project's search
  space proves insufficient).

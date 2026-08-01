# swing-algo-momentum-continuation Analysis Report

> **Analysis Type**: Empirical Result Report (PDCA Do → Check)
>
> **Project**: showmoneyv2
> **Feature**: swing-algo-momentum-continuation — Swing Algo Enhancement Sub-project 5 ("F모멘텀")
> (momentum-continuation candidate engine — RS leadership + new high + trend alignment, the first
> empirical test of this hypothesis in this codebase)
> **Design Doc**: [2026-08-01-swing-algo-momentum-continuation-design.md](../superpowers/specs/2026-08-01-swing-algo-momentum-continuation-design.md)
> **Implementation Plan**: [2026-08-01-swing-algo-momentum-continuation.md](../superpowers/plans/2026-08-01-swing-algo-momentum-continuation.md)
> **Date**: 2026-08-01
> **Prior work**: [swing-algo-oversold-bounce-hitrate.analysis.md](swing-algo-oversold-bounce-hitrate.analysis.md)
> (sub-project 4 — E반등/oversold-bounce with all 5 trader-diagnosed hit-rate levers applied still
> failed the joint decision gate on every stage and pool; the `trades_per_week >= 5` frequency floor
> was never remotely approached across 3,481 evaluated configurations, max observed 0.60/week — that
> structural dead end triggered the pivot to a new candidate-generation hypothesis, momentum
> continuation, pursued here)

---

## 1. Method Summary

Per the design doc's §2 Entry Rule, all four conditions are evaluated at trigger day `idx`, AND'd
together, on top of the reused liquidity/quality base filters:

1. **Relative-strength leadership** — the ticker's own trailing-60-trading-day return ranks in the
   top 10% of the same day's cross-sectional distribution of trailing-60-day returns across the
   full 959-ticker operating universe.
2. **New high** — `close[idx] >= max(high[idx-60..idx-1])` (the trigger day's close at or above the
   *prior* 60 trading days' high, excluding today).
3. **Trend alignment** — `close[idx] > sma50[idx] > sma200[idx]`, the classic "stage 2 uptrend"
   ordering.
4. **Base filters** — the existing liquidity/quality gates reused unmodified (`MIN_PRICE`,
   `MIN_TURNOVER_ALGO`, no negative DART disclosure, no large net-sell supply flag, `rvol >= 1.0`).
   Note: `evaluate_candidate()`'s base filters (`backtest/swing_signal_engine.py` lines 112-121)
   also include an `rsi14 < 40` exclusion gate; that gate is deliberately **not** reused here — a
   candidate already sitting at a 60-day new high with `close > sma50 > sma200` is structurally
   almost never also oversold (`rsi14 < 40`), so the gate would rarely fire on this pattern's
   candidates anyway. It is omitted rather than redundant-but-harmless, and this document states
   that plainly instead of implying strict filter parity with `evaluate_candidate()`.

`entry = close[idx]`, `entry_idx = idx+1`, `hold_days = 10` — a single-day trigger with no
multi-day confirmation. Full rationale, formulas, and parameter values are in the design doc
(§2–§3); they are not re-derived here.

Train/test split, universe, and decision-gate rules are unchanged from every prior sub-project in
this line: 959-ticker operating universe, `2022-01-01`..`2026-01-01` scan range, train
(`2022-01-01`..`2024-06-30`) / test (`2024-07-01`..`2026-01-01`) split, and
`target_stop_grid_search.run_grid_search`'s unmodified decision/reliability rules (`hit_rate >=
90%` AND `trades_per_week >= 5` AND `cagr_15slot > 0` on both splits; `n_trades >= 50` on both
splits before any pass/fail conclusion is drawn).

## 2. Candidate Count and Skipped Tickers

The scan over the full 959-ticker operating universe (`backtest_momentum_candidates.json`)
produced **4,197 candidates** with **4 skipped tickers** — the same four 404s from Yahoo Finance
seen in every prior sub-project's scan, not a new issue:

- `042670.KS`
- `450140.KS`
- `019440.KS`
- `448830.KQ`

## 3. Train vs. Test Result

The 432-cell grid search (`backtest/target_stop_grid_search.py`'s unmodified `run_grid_search`,
6 `target_pct` × 6 `stop_pct` × 3 `min_score` × 2 `regime_gate` × 2 `exclude_d_box`) over the
4,197-candidate pool produced `selection.status = "target_not_met"` — no cell reached the joint
`hit_rate >= 90%` / `trades_per_week >= 5` bar. Since no cell qualified outright, the fallback rule
selected, among cells that at least cleared the `trades_per_week >= 5` frequency floor, the one
with the highest train `hit_rate` (tie-broken by `cagr_15slot`):

**Selected train config**: `target_pct=0.03, stop_pct=0.04, min_score=60, regime_gate=false,
exclude_d_box=false`

| Split | n_trades | Reliable (n≥50)? | hit_rate | trades_per_week | avg_pnl | cagr_15slot |
|-------|---------:|:-----------------:|---------:|-----------------:|--------:|-------------:|
| Train (2022-01-01..2024-06-30) | 921 | **Yes** | 48.75% | 7.077 | -0.75% | -20.42% |
| Test (2024-07-01..2026-01-01)  | 724 | **Yes** | 50.00% | 9.231 | -0.69% | -20.28% |

Both `n_trades` figures (921 train, 724 test) clear the `n_trades >= 50` reliability bar by more
than an order of magnitude, and both `trades_per_week` figures (7.077 train, 9.231 test) clear the
`>= 5` frequency floor — a first for this research line (see §5).

## 4. Decision-Gate Verdict

Applying the three-way outcome framework (target-met / target-not-met-but-reliable /
underpowered):

- **Not target-met**: `hit_rate` is 48.75% (train) / 50.00% (test) — essentially a coin flip,
  roughly 40 percentage points short of the 90% bar on both splits. `cagr_15slot` is deeply
  negative on both splits (-20.42% train, -20.28% test): the strategy loses money over a rolling
  15-slot portfolio simulation at this configuration.
- **But reliable, not underpowered**: `n_trades = 921` (train) and `n_trades = 724` (test) are both
  far above the `n_trades >= 50` statistical-reliability bar, and `trades_per_week = 7.077` (train)
  / `9.231` (test) both clear the `>= 5` frequency floor. This is the **first result in the entire
  research line** — across sub-projects 3 and 4's dozens of E반등 configurations and thousands of
  grid cells — where both the sample-size gate and the frequency floor are cleared on both splits
  simultaneously (E반등's maximum ever observed `trades_per_week` was 0.60, two orders of magnitude
  below the bar).

**Verdict: target-not-met, and reliably so.** This is not an inconclusive or underpowered result —
it is a statistically decisive negative result on hit_rate and returns. The strategy trades often
enough and with enough samples to trust the numbers; the numbers say this specific
parameterization does not work.

## 5. Why This Differs From E반등 Structurally

Momentum-continuation's entry conditions (RS-percentile leadership + new high + SMA50/SMA200
alignment) are evidently far more common in this universe than E반등's oversold-recovery
conditions: this scan produced **4,197 candidates**, roughly **~33-35x** more than any E반등 pool in
sub-projects 3-4 (which ranged **119-127** candidates before any tag/confirmation filtering). That
volume of candidates is precisely why this hypothesis produced a statistically decisive result on
its first attempt — a single hand-specified rule, no tuning, no additive levers — where E반등 could
never get past the frequency floor across two full sub-projects of iteration.

## 6. Limitations

Restating the design doc's §7 limitations, not re-deriving them:

- **Single hand-specified rule, not swept/tuned** — the 60-day RS/new-high lookback, the top-10%
  cutoff, and the 50/200-day SMA alignment periods are fixed by trader-review judgment, not
  grid-searched. A negative result here rules out this specific rule, not the momentum-continuation
  concept in general.
- **Single train/test split**, same acknowledged limitation as every prior sub-project.
- Inherits sub-project 1/2's limitations via the reused, unmodified simulation primitives: flat-fee
  assumption, orderbook ask/bid and pattern-C block not modeled, TOSS-LIVEPRICE using next-day-open
  as a live-price proxy.
- **Cross-sectional computation cost** — `build_universe_return_lookup` is `O(tickers × days)`
  once, noticeably slower than any prior additive signal's per-ticker-only cost, though still a
  one-time precompute, not per-grid-cell.
- `hold_days = 10` is a one-time judgment call, not swept; a negative result should not be read as
  ruling out momentum-continuation at other holding periods.
- **Static, survivors-only universe** (new to this sub-project) — the 959-ticker operating universe
  is a fixed, current-day list, and this sub-project's relative-strength percentile is the first
  cross-sectional signal in this research line: it is computed against tickers currently in that
  list only, so delisted/renamed tickers are absent from the comparison set. The bias direction
  cannot flip the verdict, though — a survivors-only universe raises the top-10% cutoff and selects
  for stronger names, i.e. it flatters the strategy if anything, and the result (target-not-met,
  reliably) is still decisively negative despite that.

Because this sub-project's result is **reliable** (not underpowered), these limitations are about
parameter choice, not sample size — a genuinely different situation from every E반등 analysis, where
small samples meant most limitations were about whether the numbers could be trusted at all. Here
the numbers can be trusted; the question is only which rule/parameterization was tested.

## 7. Next Step Recommendation

Three structural facts point to where the next iteration should focus, all drawn directly from the
same grid search result:

1. The selected cell's risk/reward shape is inverted: `target_pct=0.03` (3%) is *tighter* than
   `stop_pct=0.04` (4%) — the strategy is set up to lose more on a stop-out than it gains on a
   target hit, before even considering hit_rate. This looks like a backwards parameterization for
   a momentum-continuation bet at first glance — but the full grid (next point) shows the actual
   lever is a *wider target*, not a tighter stop: every `stop_pct` tighter than the grid's own
   maximum (0.04) produced zero positive-`cagr_15slot` cells, at any `target_pct`.
2. Checking all 432 train cells directly (not just the reported fallback) confirms this is not a
   one-off: exactly **6 cells** have `cagr_15slot > 0`, and every one of them sits at
   `target_pct=0.10` **and** `stop_pct=0.04` simultaneously — both the maximum value in their
   respective grids (`GRID_TARGET_PCT = [0.03, 0.04, 0.05, 0.06, 0.08, 0.10]`, `GRID_STOP_PCT =
   [0.01, 0.015, 0.02, 0.025, 0.03, 0.04]`, both defined in `backtest/target_stop_grid_search.py`).
   The 6 cells differ only in `min_score` (60/90/110) and `exclude_d_box` (false/true); the other 5
   `stop_pct` values tested (0.01, 0.015, 0.02, 0.025, 0.03) produce no positive-`cagr_15slot` cell
   at *any* `target_pct`, including at `target_pct=0.10`. So the pattern spans **both grid axes at
   once**, not `target_pct` alone — a follow-up that only widens `target_pct` past 0.10 while
   leaving `stop_pct` clamped at its 0.04 ceiling can't tell whether target, stop, or their ratio
   is the actual lever.
3. `selection.fallback_best_cagr` in the same grid search result — the single train cell with the
   highest `cagr_15slot` across all 432 cells, reported for diagnostic purposes even though it
   wasn't selected (selection prioritizes hit_rate among frequency-qualifying cells, per
   `select_best_config`'s tie-break rule) — is `target_pct=0.10, stop_pct=0.04, min_score=60,
   regime_gate=false, exclude_d_box=false`: `n_trades=1019`, `hit_rate=27.67%`,
   `trades_per_week=7.83`, `cagr_15slot=+0.53%`. Widening the target to 10% against the same 4%
   stop — restoring a normal risk/reward shape — turns train `cagr_15slot` from -20.4% to
   **slightly positive**, even though `hit_rate` is still far below 90%. That is a large swing
   driven entirely by target/stop shape, not by the entry signal.

**Concrete recommendation**: do not treat this as a dead hypothesis to be abandoned outright, and
do not jump straight to a sub-project-4-style hit-rate-improvement follow-up (additive
volume/sector/support tags) — those levers helped E반등's hit_rate only marginally and never solved
its actual (frequency) problem, whereas momentum-continuation's actual problem is not frequency
(already solved) but target/stop shape. The next sub-project should **re-run the existing 432-cell
grid with wider ranges on *both* `target_pct` and `stop_pct`** (extending past their current maxima
of 0.10 and 0.04 respectively) to determine whether a right-sized risk/reward shape — not a smarter
entry signal — is the actual lever this pattern needs, and to isolate whether target, stop, or
their ratio is doing the work. Only if a materially wider target/stop sweep still fails to
produce a cell with positive `cagr_15slot` and a plausible path to `hit_rate >= 90%` should this
hypothesis be closed and the research line pivot to low-volatility-accumulation, the other
deferred hypothesis named in the original Phase B design doc.

---

No production code (`src/swing-scanner.src.js`) has been changed by this sub-project — as with
every prior sub-project, that remains a separate, later decision.

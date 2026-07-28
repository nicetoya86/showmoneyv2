# swing-algo-target-stop-retuning Analysis Report

> **Analysis Type**: Empirical Result Report (PDCA Do → Check)
>
> **Project**: showmoneyv2
> **Feature**: swing-algo-target-stop-retuning — Swing Algo Enhancement Sub-project 2
> (Target/Stop & Threshold Retuning for High Hit-Rate)
> **Design Doc**: [2026-07-27-swing-algo-target-stop-retuning-design.md](../superpowers/specs/2026-07-27-swing-algo-target-stop-retuning-design.md)
> **Implementation Plan**: [2026-07-27-swing-algo-target-stop-retuning.md](../superpowers/plans/2026-07-27-swing-algo-target-stop-retuning.md)
> **Date**: 2026-07-28
> **Prior work**: [backtest.analysis.md](backtest.analysis.md) (sub-project 1, realistic backtest
> foundation — the TOSS-aware, fee-aware simulation this sub-project reuses unmodified)

---

## 1. Method Summary

This sub-project re-derives the swing algorithm's **target price, stop-loss, minimum score,
regime gate, and D박스-pattern inclusion** via a grid search, without touching candidate
generation (`evaluate_candidate()` — scoring/pattern logic — is reused completely unmodified).

- **Grid axes** (432 cells total): `target_pct` ∈ {3%, 4%, 5%, 6%, 8%, 10%} (flat, 3% floor, not
  ATR-scaled), `stop_pct` ∈ {1%, 1.5%, 2%, 2.5%, 3%, 4%}, `min_score` ∈ {60, 90, 110},
  `regime_gate` ∈ {off, on}, `exclude_d_box` ∈ {off, on}.
- **Data**: Phase 1 (`backtest/generate_signal_candidates.py`) re-ran `evaluate_candidate()` over
  the same 959-ticker universe as sub-project 1 and cached every qualifying candidate plus its
  forward OHLC price path — **21,587 candidates**, 4 tickers skipped (same delisted/unfetchable
  set as sub-project 1). Phase 2 (`backtest/target_stop_grid_search.py`) evaluates each of the 432
  configurations against that cache, reusing sub-project 1's `apply_toss_liveprice`,
  `simulate_exit`, `apply_round_trip_cost`, and `analyze_portfolio_return`'s 15-slot portfolio-CAGR
  simulation completely unmodified.
- **Train/test split**: train `2022-01-01`..`2024-06-30`, test `2024-07-01`..`2026-01-01`. The
  full 432-cell grid search and configuration selection ran **only** on train; the selected
  configuration was evaluated **exactly once** on test, with no re-selection afterward.
- **Selection rule** (train only): among cells with `hit_rate >= 90%` (fraction of trades that
  actually touch the target, not `pnl > 0`) **and** `trades_per_week >= 5`, pick the highest
  `cagr_15slot`. If none qualify — the case here — fall back to: filter to `trades_per_week >= 5`
  (hard constraint, never dropped), sort by `hit_rate` descending then `cagr_15slot` descending,
  and report the top 5 plus the single best-CAGR cell overall regardless of frequency.

## 2. Result: Target Not Met

**`selection.status = "target_not_met"`.** No configuration in the 432-cell grid jointly reached
90% hit-rate, ≥5 recommendations/week, and a positive expected return. In fact:

| Metric across all 432 train cells | Value |
|---|---|
| Cells with `hit_rate >= 90%` | **0 / 432** |
| Cells with `trades_per_week >= 5` | 432 / 432 (frequency was never the binding constraint) |
| Cells with `cagr_15slot > 0` | **0 / 432** |
| Best (max) `cagr_15slot` across the entire grid | **-9.62%/yr** |
| Worst (min) `cagr_15slot` across the entire grid | -29.96%/yr |

Every single grid cell — every combination of target, stop, score threshold, regime gate, and
D박스 inclusion tested — produced a negative expected annual return. The frequency floor was
never binding (every cell clears ≥5/week); the failure is entirely on hit-rate and profitability.

### Selected (fallback) configuration: train vs. test

Since no cell qualified, the fallback rule selected the highest-hit-rate cell among the
(trivially-satisfied) frequency-qualifying set: `target_pct=3%, stop_pct=4%, min_score=60,
regime_gate=off, exclude_d_box=on`.

| Metric | Train (2022-01-01..2024-06-30) | Test (2024-07-01..2026-01-01) |
|---|---:|---:|
| `n_trades` | 1,431 | 839 |
| `hit_rate` | 46.96% | 45.89% |
| `trades_per_week` | 11.00 | 10.70 |
| `avg_pnl` (net of cost) | -0.843% | -0.937% |
| `cagr_15slot` | -27.94%/yr | -29.59%/yr |
| `mdd_15slot` | -55.72% | -41.02% |

Train and test numbers are close (hit-rate within 1.1 points, CAGR within 1.6 points) — **no
evidence of overfitting** in this fallback selection; the negative result is consistent, not an
artifact of picking a lucky training-period config. This is the intuitive corner of the grid: a
tight 3% target (easiest to reach) paired with the widest 4% stop (rarely stops out) — it nearly
doubles the raw hit-rate of the un-retuned baseline (47% vs. sub-project 1's 32.17%) but still
loses money, because the reward-to-risk ratio (3:4) is worse than 1:1 and a chasing/rebase-blocked
trade or a stop-out costs more than the small, easy target gains.

### Best-CAGR configuration regardless of hit-rate or frequency (train)

For reference, the single best-`cagr_15slot` cell in the entire grid (still negative):
`target_pct=10%, stop_pct=1%, min_score=60, regime_gate=on, exclude_d_box=on` →
`hit_rate=7.40%`, `trades_per_week=8.93`, `avg_pnl=-0.327%`, `cagr_15slot=-9.62%/yr`,
`mdd_15slot=-23.66%`. A wide 10:1 target:stop ratio raises the per-win payoff enough to shrink the
loss to single digits annually, but hit-rate collapses to 7% — the fewer, larger wins do not
outweigh the much higher stop-out frequency at this candidate quality level.

## 3. Top-10 Train Configurations by CAGR

All ten are negative; every one of them also uses the widest stop (`stop_pct=1%`... note: this is
the *tightest* stop, 1%) paired with a wide target (8-10%) and `exclude_d_box=True` — the shape of
the least-bad corner of the grid, not a viable strategy:

| target_pct | stop_pct | min_score | regime_gate | exclude_d_box | n_trades | hit_rate | trades/wk | avg_pnl | cagr_15slot | mdd_15slot |
|---:|---:|---:|:---:|:---:|---:|---:|---:|---:|---:|---:|
| 10% | 1% | 60 | on | on | 1,162 | 7.40% | 8.93 | -0.327% | -9.62% | -23.66% |
| 8% | 1% | 110 | off | on | 1,121 | 9.10% | 8.61 | -0.347% | -9.63% | -23.39% |
| 8% | 1% | 110 | on | on | 1,121 | 9.10% | 8.61 | -0.347% | -9.63% | -23.39% |
| 10% | 1% | 60 | off | on | 1,180 | 7.37% | 9.07 | -0.324% | -9.77% | -23.84% |
| 8% | 1% | 90 | on | on | 1,130 | 9.12% | 8.68 | -0.346% | -9.78% | -23.21% |
| 8% | 1% | 60 | on | on | 1,131 | 9.11% | 8.69 | -0.347% | -9.78% | -23.26% |
| 10% | 1% | 90 | on | on | 1,161 | 7.41% | 8.92 | -0.327% | -9.83% | -23.85% |
| 10% | 1% | 110 | off | on | 1,152 | 7.38% | 8.85 | -0.329% | -9.96% | -24.05% |
| 10% | 1% | 110 | on | on | 1,152 | 7.38% | 8.85 | -0.329% | -9.96% | -24.05% |
| 10% | 1% | 90 | off | on | 1,174 | 7.41% | 9.02 | -0.327% | -10.07% | -24.65% |

All values in this table are read directly from `backtest_grid_search_results.json`, not
re-derived or rounded by hand beyond display precision.

**Pattern across all ten**: `stop_pct=1%` (tightest available) and `exclude_d_box=True` appear in
every row; `min_score` and `regime_gate` barely move the outcome (both regime-gate settings and
all three score thresholds appear in the top 10 with near-identical numbers) — the target/stop
ratio dominates, the score/regime/pattern filters are second-order at best.

## 4. Honest Conclusion

**No configuration in this 432-cell grid jointly reaches 90% hit-rate, ≥5 recommendations/week,
and a positive expected return — nor does any single cell reach a positive expected return in
isolation.** The best available trade-off found (widest reward-to-risk corner of the grid, 10%
target / 1% stop) still loses approximately **9.6% per year** under the 15-slot portfolio model,
a large improvement over the un-retuned baseline's -26%/yr (sub-project 1) but still decisively
negative.

This is not a tuning failure to be fixed by searching harder within this parameter family — the
grid already spans the full plausible range the design doc specified (3-10% target, 1-4% stop, 3
score thresholds, regime gate on/off, D박스 include/exclude), and the result is monotonically
negative across all 432 cells with no pocket of profitability at any corner. **The constraint is
the candidate pool itself** (which stocks/days `evaluate_candidate()` flags as signals), not the
exit parameters layered on top of it.

Per the design doc's roadmap, this result is exactly the trigger condition for the conditional
**sub-project 3 (new signals)** — weekly-trend alignment, sector/theme relative strength,
volatility-contraction patterns — since this sub-project's grid search could not jointly satisfy
hit-rate/frequency/profitability using the existing candidate pool.

## 5. Limitations

- **Flat-percentage, not ATR-scaled, target/stop** — a deliberate simplification (see design doc,
  "Explicitly out of scope"); an ATR-scaled sweep might land on a different corner, but the
  monotonically-negative pattern across the entire flat-pct grid (§2, §3) suggests the ceiling is
  structural (candidate quality), not an artifact of using flat percentages.
- **Single train/test split**, not walk-forward/k-fold — the test-period estimate is genuinely
  held-out (never seen during selection) but is still a single draw; a different split boundary
  could shift the exact numbers, though not plausibly from -28%/yr to positive given the margin.
- **Discrete grid** — the true optimum may lie between grid points (e.g. `stop_pct=1.2%`), but the
  smooth, monotonic degradation visible in §3 as `stop_pct` widens past 1% makes a hidden
  profitable pocket between grid points unlikely.
- Inherits all of sub-project 1's stated limitations (orderbook ask/bid and pattern-C blocks not
  modeled, single train/test split scope, flat-fee assumption) since this sub-project reuses that
  simulation machinery unmodified.

## 6. Next Step Recommendation

**No production code (`src/swing-scanner.src.js`) has been changed by this sub-project.**
Deployment of any configuration found here is explicitly out of scope and remains a separate,
later decision pending the user's review of these results — and given every tested configuration
is unprofitable, no configuration from this grid is recommended for deployment as-is.

The recommended next step, per the design doc's own roadmap, is to evaluate whether
**sub-project 3 (new signals)** is worth pursuing — this sub-project's negative, uniform result
across the full grid is the condition the roadmap defined for considering it.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-28 | Initial results write-up (Tasks 1-6 of the implementation plan) | Claude (same session) |

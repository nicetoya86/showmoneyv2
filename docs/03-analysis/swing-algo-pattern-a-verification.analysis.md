# swing-algo-pattern-a-verification Analysis Report

> **Analysis Type**: Empirical Result Report (PDCA Do → Check)
>
> **Project**: showmoneyv2
> **Feature**: swing-algo-pattern-a-verification — Swing Algo Enhancement Sub-project 7a
> (per-pattern `hit_rate`/`trades_per_week`/`cagr_15slot` verification for production pattern
> **A눌림목 (급등후눌림목)**, run in isolation from the other three production patterns for the
> first time in this research line)
> **Design Doc**: [2026-08-02-swing-algo-pattern-a-verification-design.md](../superpowers/specs/2026-08-02-swing-algo-pattern-a-verification-design.md)
> **Implementation Plan**: [2026-08-02-swing-algo-pattern-a-verification.md](../superpowers/plans/2026-08-02-swing-algo-pattern-a-verification.md)
> **Date**: 2026-08-02
> **Prior work**: [swing-algo-target-stop-retuning.analysis.md](swing-algo-target-stop-retuning.analysis.md)
> (sub-project 2 — grid-searched the POOLED A눌림목+B지지선+C촉매+D박스 candidate set, 432 cells,
> found it uniformly unprofitable — 0/432 cells cleared `hit_rate >= 90%`, best `cagr_15slot`
> across the entire grid was -9.62%/yr, and the fallback-selected config landed at
> `hit_rate=46.96%/45.89%` train/test with `cagr_15slot=-27.94%/-29.59%` — but never broke that
> result out per individual pattern, leaving open whether the pooled number was hiding a decent
> pattern averaged down by bad ones)

---

## 1. Method Summary

This sub-project makes **no changes to `evaluate_candidate()` (in `generate_signal_candidates.py`)
and no changes to `backtest/target_stop_grid_search.py`**. It only filters sub-project 2's already-committed
pooled candidate cache down to `pattern_type == "A눌림목"` and re-runs that module's existing,
unmodified `run_one_config`/`select_best_config` against the filtered subset.

The filter step produced `backtest_pattern_a_candidates.json`: **9,808 candidates**, confirmed
directly from the file (`len(candidates) == 9808`). This is the largest of the four production
patterns in the pooled set, as established in the design doc — see the design doc's Section 2 for
the pool-composition reasoning, not re-derived here.

The grid re-run produced `backtest_pattern_a_grid_results.json`, a **216-cell grid**
(`train_results` has exactly 216 entries) over:

- `target_pct` ∈ {3%, 4%, 5%, 6%, 8%, 10%} (6 values)
- `stop_pct` ∈ {1%, 1.5%, 2%, 2.5%, 3%, 4%} (6 values)
- `min_score` ∈ {60, 90, 110} (3 values)
- `regime_gate` ∈ {off, on} (2 values)
- `exclude_d_box` fixed `False` (meaningless on a pool already filtered to a single non-D pattern)

6 × 6 × 3 × 2 = 216 cells, matching sub-project 2's axis values exactly minus the redundant
`exclude_d_box` axis — see the design doc's Section 3 for why that axis was dropped rather than
kept at 432 cells.

Train/test split, decision gate, and reliability floor are unchanged from every prior sub-project:
train `2022-01-01`..`2024-06-30`, test `2024-07-01`..`2026-01-01`; a configuration passes only if,
on **both** splits, `hit_rate >= 90%` AND `trades_per_week >= 5` AND `cagr_15slot > 0`, with
`n_trades >= 50` as a prerequisite reliability floor before any pass/fail conclusion is trusted.

## 2. Grid Summary

From `backtest_pattern_a_grid_results.json`'s `summary` block, across all 216 train cells:

| Metric (train, 216 cells) | Value |
|---|---:|
| Grid cell count | 216 |
| Cells clearing `hit_rate >= 90%` | **0 / 216** |
| Cells clearing `trades_per_week >= 5` | 216 / 216 |
| Cells with `cagr_15slot > 0` | **0 / 216** |
| Cells clearing all three simultaneously (full train-side gate) | **0 / 216** |
| Max `hit_rate` across the grid | 49.34% |
| Max `cagr_15slot` across the grid | -6.28%/yr |
| Min `cagr_15slot` across the grid | -28.90%/yr |

Frequency was never the binding constraint — every single one of the 216 cells clears
`trades_per_week >= 5`, exactly as in sub-project 2's pooled grid. The binding constraint is
`cagr_15slot`: not one cell out of 216 is profitable on train, and the best any cell manages is
still a loss (-6.28%/yr, at `target_pct=10%, stop_pct=1%, min_score=110, regime_gate=False` —
`n_trades=1041, hit_rate=8.17%, avg_pnl=-0.25%, mdd_15slot=-14.85%`). The worst cell loses
-28.90%/yr (`target_pct=3%, stop_pct=2%, min_score=90, regime_gate=False` — `n_trades=1352,
hit_rate=25.07%`).

A trader's honest read on this shape: the grid confirms the same trade-off seen everywhere else in
this research line — cells with a tight target relative to stop buy a higher hit_rate but bleed
`cagr` (wide loss on each stop-out outweighs frequent small wins), while cells with a wide target
relative to stop preserve `cagr` somewhat but collapse hit_rate into single digits. There is no
corner of this grid where both move in the trader's favor at once.

## 3. Selected Configuration: Train vs. Test

`select_best_config`'s fallback rule (no cell cleared `hit_rate >= 90%`, so it fell back to
filtering on `trades_per_week >= 5` and sorting by `hit_rate` descending, then `cagr_15slot`
descending) selected:

**`target_pct=3%, stop_pct=4%, min_score=110, regime_gate=False`**

| Metric | Train | Test |
|---|---:|---:|
| `n_trades` | 1,287 | 786 |
| `hit_rate` | 49.34% | 54.33% |
| `trades_per_week` | 9.89 | 10.02 |
| `avg_pnl` | -0.71% | -0.37% |
| `cagr_15slot` | -21.22%/yr | -12.61%/yr |
| `mdd_15slot` | -45.16% | -19.34% |

Both splits clear `n_trades >= 50` by more than an order of magnitude (1,287 and 786), so this
result is statistically reliable, not a small-sample artifact. Both splits also clear
`trades_per_week >= 5` comfortably (9.89 and 10.02). Both splits fail `hit_rate >= 90%` badly
(short by roughly 41-46 percentage points) and both splits fail `cagr_15slot > 0` (both negative).

Test actually looks directionally *better* than train on every metric here — higher hit_rate
(54.33% vs 49.34%), less negative cagr (-12.61% vs -21.22%), and a much smaller drawdown (-19.34%
vs -45.16%). That is the opposite of the overfitting pattern one would worry about (a config that
looks great on train and falls apart on test); here the selected config is mediocre-to-bad on
train and merely bad on test. A trader reading this table should not take the better test numbers
as license to expect real-money performance close to the test column — with only one train/test
split, either number could be the one closer to "true" long-run behavior, and both describe a
losing strategy regardless.

## 4. Decision-Gate Verdict

Applying the three-way outcome framework (target-met / target-not-met-but-reliable /
underpowered) used by every prior sub-project in this line:

- **Not target-met**: `hit_rate` is 49.34% (train) and 54.33% (test) — both roughly 36-41
  percentage points short of the 90% bar. `selection['status'] == "target_not_met"` confirms this
  directly. `cagr_15slot` is negative on both splits (-21.22% train, -12.61% test), so even setting
  the 90% hit_rate bar aside, this configuration would not be a profitable deployment candidate on
  cagr grounds alone.
- **Reliable, not underpowered**: `n_trades = 1,287` (train) and `786` (test) both clear the
  `n_trades >= 50` statistical-reliability floor by more than an order of magnitude.
  `trades_per_week = 9.89` (train) and `10.02` (test) both clear the `>= 5` frequency floor. Every
  leg of the three-way framework except the 90% hit_rate bar (and the `cagr_15slot > 0` bar) is
  cleared on both splits.

**Verdict: target-not-met, but reliably so.** A눌림목 in isolation, across an exhaustive 216-cell
grid identical in structure to sub-project 2's pooled grid, cannot reach `hit_rate >= 90%`
profitably by target/stop/min_score/regime-gate tuning alone. Zero cells clear the hit_rate bar;
zero cells are even profitable on `cagr_15slot`. This is a decisive, well-powered negative result,
not a small-sample fluke or a near-miss.

## 5. Comparison to the Pooled Sub-project 2 Result

Sub-project 2's pooled A+B+C+D grid (432 cells, same `run_one_config`/`select_best_config`
machinery, same fallback selection rule): 0/432 cells cleared `hit_rate >= 90%`; grid extremes were
`cagr_15slot` max **-9.62%/yr**, min -29.96%/yr; the fallback-selected config landed at
`hit_rate=46.96%/45.89%` (train/test) with `cagr_15slot=-27.94%/-29.59%` (train/test).

Comparing like-for-like against A눌림목 alone:

| Comparison | Pooled (432 cells, A+B+C+D) | A눌림목 alone (216 cells) |
|---|---:|---:|
| Cells clearing `hit_rate >= 90%` | 0 / 432 | 0 / 216 |
| Grid max `cagr_15slot` (best cell, any hit_rate) | -9.62%/yr | -6.28%/yr |
| Grid min `cagr_15slot` (worst cell) | -29.96%/yr | -28.90%/yr |
| Fallback-selected config `hit_rate` (train / test) | 46.96% / 45.89% | 49.34% / 54.33% |
| Fallback-selected config `cagr_15slot` (train / test) | -27.94% / -29.59% | -21.22% / -12.61% |

On every one of these like-for-like pairs, A눌림목 in isolation is the same or mildly *better* than
the pooled result — not worse: its grid-best cagr cell (-6.28%) beats the pooled grid-best cell
(-9.62%), its grid-worst cell (-28.90%) is marginally less bad than the pooled grid-worst
(-29.96%), its selected-config hit_rate beats the pooled selected-config hit_rate on both splits,
and its selected-config cagr beats the pooled selected-config cagr on both splits (by roughly
6.7pp train and a much larger 17pp test).

It is worth being explicit about a comparison that looks worse on its face but is not a fair one:
A눌림목's *selected* configuration's cagr (-21.22% train) is more negative than the pooled grid's
single best cell anywhere in that grid (-9.62%). But that pooled -9.62% cell was never a candidate
for deployment either — it was the grid's best-*cagr* cell, not its selected config, and (per the
design doc's own convention) a config chosen purely for best cagr at any hit_rate typically carries
a very low hit_rate (A눌림목's own best-cagr cell, at -6.28%, has `hit_rate=8.17%` — essentially
unusable as a signal). Comparing a *selected* config (chosen to prioritize hit_rate first, per the
same fallback rule used everywhere in this line) against an *unselected* best-cagr outlier cell
from a different grid is not an apples-to-apples read, and doing so would produce a misleadingly
pessimistic conclusion about A눌림목 specifically.

**Honest trader-perspective read**: A눌림목 does not appear to be the pattern dragging the pooled
A+B+C+D result down. If anything, on every metric that can be compared consistently between the
two grids, A눌림목 alone is a touch stronger than the pool average — a materially better test-side
cagr (-12.61% vs -29.59%, a difference of nearly 17 percentage points) is the most striking single
data point. That implies one or more of the other three patterns (most plausibly whichever pattern
sub-project 2's pool weighted most heavily behind A눌림목, since A눌림목 alone is already 45% of the
pool) is dragging the blended number down harder than A눌림목 does on its own. But this is a
"less bad than an already-bad average" finding, not a "found an edge" finding — A눌림목 alone is
still comprehensively unprofitable (0/216 cells profitable, let alone at 90% hit_rate), and a
trader should not read "better than the pool" as "good." The pool being bad and A눌림목 being
slightly-less-bad-than-the-pool are both true at once.

## 6. Limitations

- **Single train/test split**, same acknowledged limitation as every prior sub-project in this
  line — neither the grid search nor the pooled-vs-isolated comparison has been validated across
  multiple splits or a walk-forward scheme.
- **Discrete 216-cell grid** — the true optimum may sit between grid points, but sub-project 2's
  monotonic-degradation pattern across the pooled set makes a hidden profitable pocket between
  points unlikely to reverse a clearly negative finding here.
- This sub-project inherits sub-project 1's simulation-machinery limitations (orderbook ask/bid and
  pattern-C-specific blocks not modeled, flat round-trip fee assumption) since `run_one_config` and
  its dependencies are reused unmodified.
- **C촉매 and D박스 are explicitly out of scope** — each gets its own sub-project (7b, 7c) after
  this one, per the user's decision to split rather than combine. The pooled-vs-isolated comparison
  in Section 5 is necessarily incomplete until those two verifications land: it is not yet possible
  to say which specific pattern(s) are dragging the pooled average down, only that A눌림목 does not
  appear to be the primary culprit.

## 7. Final Recommendation

**No change to A눌림목's current production deployment status is recommended.** No production code
(`src/swing-scanner.src.js`) was touched by this sub-project — it is a pure verification exercise
against already-committed backtest infrastructure and cached data. A눌림목 continues running in
production exactly as it does today.

This finding does not surface a new lever worth pursuing: the 216-cell grid is exhaustive over the
same axes used everywhere else in this research line, and it reproduces the now-familiar shape —
0/216 cells reach `hit_rate >= 90%`, 0/216 cells are even profitable, and the best-available
configuration is a reliable-but-losing -21.22%/-12.61% (train/test) `cagr_15slot`. There is nothing
here that argues for retuning A눌림목's target/stop/min_score/regime-gate parameters in production.

What this sub-project *does* establish, and the reason it was worth running: A눌림목 in isolation is
not meaningfully worse than sub-project 2's pooled A+B+C+D result, and by most like-for-like
measures is mildly better (see Section 5). The pooled result's poor economics are not attributable
to A눌림목 specifically. The open question this sub-project cannot answer is whether C촉매 or
D박스 — still unverified — are pulling the pooled average down harder than their pooled weight
alone would suggest. That question is explicitly deferred to sub-projects 7b (C촉매) and 7c (D박스),
which should be read before drawing any conclusion about the pooled system as a whole.

---

No production code (`src/swing-scanner.src.js`) has been changed by this sub-project. C촉매
(sub-project 7b) and D박스 (sub-project 7c) remain to be verified separately before any conclusion
is drawn about the full four-pattern production system.

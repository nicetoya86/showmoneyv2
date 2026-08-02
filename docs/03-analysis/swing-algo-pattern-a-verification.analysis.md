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
> pattern averaged down by bad ones; two of these three figures — the -9.62%/yr grid max and the
> `hit_rate=46.96%/45.89%`/`cagr_15slot=-27.94%/-29.59%` selected config — are from
> `exclude_d_box=True` cells, not the true A+B+C+D pool; see §5 for the corrected like-for-like
> comparison and its caveats)

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

*Footnote*: at `min_score=110`, `regime_gate` on vs. off produce bitwise-identical results across
all 36 matching cell pairs in this grid (verified directly against
`backtest_pattern_a_grid_results.json`). The selected config below has `regime_gate=False` at
`min_score=110`, but that is an arbitrary tiebreak between two identical rows, not evidence that
`regime_gate=False` outperforms `regime_gate=True`.

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
(short by roughly 36-41 percentage points — `90% - 49.34% = 40.66pp` train, `90% - 54.33% = 35.67pp`
test) and both splits fail `cagr_15slot > 0` (both negative).

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
zero cells are even profitable on `cagr_15slot` (train-side, per the 216-cell grid — the grid is
only fully evaluated on train; test is evaluated once, for the selected config only, as in §2).
This is a decisive, well-powered negative result, not a small-sample fluke or a near-miss.

## 5. Comparison to the Pooled Sub-project 2 Result

**Correction (post-review)**: an earlier version of this section compared A눌림목's 216-cell grid
against three headline numbers quoted from sub-project 2's analysis doc without checking which
`exclude_d_box` setting each one actually came from. Verified directly against
`backtest_grid_search_results.json`'s 432 `train_results` cells: the grid's overall max `cagr_15slot`
(-9.62%/yr) and the fallback-selected config (`hit_rate=46.96%/45.89%`, `cagr_15slot=-27.94%/-29.59%`)
are **both `exclude_d_box=True` cells** — i.e. an **A+B+C** pool, not A+B+C+D. Only the grid's overall
min `cagr_15slot` (-29.96%/yr) is genuinely `exclude_d_box=False` (true A+B+C+D). Comparing A눌림목's
216-cell, `exclude_d_box=False`-only grid against two A+B+C numbers and one A+B+C+D number under a
single "pooled A+B+C+D" label was not a like-for-like comparison. This section replaces that
comparison with a corrected `exclude_d_box=False` subgrid — though, as the caveat below explains,
even this corrected comparison is not a full like-for-like decomposition.

**Corrected pool**: the `exclude_d_box=False` subset of `backtest_grid_search_results.json`'s 432
`train_results` cells — 216 cells, matching A눌림목's own grid size exactly (verified directly:
`len([c for c in train_results if c['exclude_d_box'] is False]) == 216`). Within this subgrid, max
`cagr_15slot` is **-10.49%/yr** (`target_pct=6%, stop_pct=1%, min_score=60, regime_gate=True`,
`n_trades=1104, hit_rate=11.23%`), min is **-29.96%/yr** (same cell as the original full-grid min,
since it was already `exclude_d_box=False`: `target_pct=3%, stop_pct=4%, min_score=90,
regime_gate=True, n_trades=1406, hit_rate=45.95%`). Re-applying the same fallback selection rule
(filter `trades_per_week >= 5`, sort by `hit_rate` descending then `cagr_15slot` descending) within
just this subgrid selects `target_pct=3%, stop_pct=4%, min_score=60, regime_gate=False` with
**train** `hit_rate=46.14%, cagr_15slot=-29.31%/yr` (`n_trades=1424`). Note: this in-subgrid
selection has no corresponding **test**-side figure — `backtest_grid_search_results.json` only
computed a single `test_result`, for the original (mixed-pool, `exclude_d_box=True`) overall
selection, and reusing that number here would reintroduce the same mislabeling this correction is
fixing. The corrected pooled row below is therefore train-only.

**Important caveat on what this comparison does and does not control for**: `run_one_config`
calls `apply_daily_selection` (in `backtest/run_swing_v2_backtest.py`), which caps trades at
`max_per_day=3` / `max_per_week=15`, selecting among same-day candidates by `(grade, rank_score)`
descending. That means candidates compete for a scarce number of daily/weekly slots. When A눌림목
is run alone, its candidates no longer compete against B/C/D candidates for those slots, so a
materially different, larger *set* of A눌림목 signals gets selected than when A눌림목 runs pooled
with B/C/D — A눌림목 running alone includes many lower-ranked signals that would be crowded out of
daily slots when competing against B/C/D candidates in the pooled system. So "A눌림목 alone" is
**not** a decomposition of A눌림목's contribution to the pooled result; it is a different portfolio
entirely. The comparison below is like-for-like only in the narrow sense of grid shape and
`exclude_d_box` labeling (both are true 216-cell, `exclude_d_box=False`-consistent grids) — it does
not control for daily/weekly slot competition, and the two runs' selected trades are not the same
trades restricted to a subset.

Comparing these two runs (same grid shape, not a slot-competition-controlled decomposition):

| Comparison | Pooled A+B+C+D, `exclude_d_box=False` subgrid (216 cells, train) | A눌림목 alone (216 cells) |
|---|---:|---:|
| Cells clearing `hit_rate >= 90%` | 0 / 216 | 0 / 216 (train) |
| Grid max `cagr_15slot` (best cell, any hit_rate) | -10.49%/yr | -6.28%/yr (train) |
| Grid min `cagr_15slot` (worst cell) | -29.96%/yr | -28.90%/yr (train) |
| Fallback-selected config `hit_rate` | 46.14% (train) | 49.34% / 54.33% (train / test) |
| Fallback-selected config `cagr_15slot` | -29.31%/yr (train) | -21.22% / -12.61% (train / test) |

On every one of these train-side pairs, A눌림목 in isolation is the same or mildly *better* than
the true A+B+C+D pooled subgrid — not worse (bearing in mind, per the caveat above, that this is a
comparison of two differently-selected portfolios, not a decomposition of one into the other): its
grid-best cagr cell (-6.28%) beats
the pooled subgrid's grid-best cell (-10.49%), its grid-worst cell (-28.90%) is marginally less bad
than the pooled subgrid's grid-worst (-29.96%), and its selected-config train hit_rate (49.34%)
and cagr (-21.22%) both beat the pooled subgrid's selected-config train figures (46.14% and
-29.31% respectively, a gap of roughly 8.1pp cagr). A눌림목's test-side numbers (54.33%
hit_rate, -12.61% cagr) look better still, but there is no true-pool test-side figure to compare
them against — see the note above.

It is worth being explicit about a comparison that looks worse on its face but is not a fair one:
A눌림목's *selected* configuration's cagr (-21.22% train) is more negative than the (mixed-pool)
grid's single best cell anywhere in the original 432-cell grid (-9.62%, an `exclude_d_box=True`
cell — see the correction note above). But that -9.62% cell was never a candidate for deployment
either — it was the grid's best-*cagr* cell, not its selected config, and (per the design doc's own
convention) a config chosen purely for best cagr at any hit_rate typically carries a very low
hit_rate: that pooled grid's own best-cagr cell has `hit_rate=7.40%`
(`docs/03-analysis/swing-algo-target-stop-retuning.analysis.md`, line 85/98), and A눌림목's own
best-cagr cell (-6.28%) is much the same — `hit_rate=8.17%`, essentially unusable as a signal
either way. Comparing a *selected* config (chosen to prioritize hit_rate first, per the same
fallback rule used everywhere in this line) against an *unselected* best-cagr outlier cell is not
an apples-to-apples read regardless of which grid it comes from.

**Honest trader-perspective read**: on the corrected `exclude_d_box=False` comparison, A눌림목 run
alone does not look obviously worse than the true A+B+C+D pooled subgrid — its train-side numbers
are mildly better than the pooled subgrid's on every axis compared above. But this is not a
rigorous like-for-like decomposition of A눌림목's share of the pooled result (see the slot-competition
caveat above), so **which** of the other patterns (if any) is responsible for the pooled result's
weakness cannot be determined from this sub-project alone — see §7 for why the earlier "C촉매 or
D박스" framing has been withdrawn.
This is a "less bad than an already-bad pooled average" finding, not a "found an edge" finding —
A눌림목 alone is still comprehensively unprofitable (0/216 cells profitable, let alone at 90%
hit_rate), and a trader should not read "better than the pool" as "good." The pool being bad and
A눌림목 being slightly-less-bad-than-the-pool are both true at once.

Separately, and in a different context from the grid comparison above: A눌림목's raw candidate
count is 9,808 of the full 21,587-candidate A+B+C+D pool (per §1 and the design doc), i.e. **45.4%**
of all candidates by count. That 45.4% figure describes candidate-pool *share*, not grid cells, and
should not be conflated with the 216-cell subgrid comparison immediately above — the two are
different units (raw candidates vs. grid configurations) over different bases (21,587 full pool vs.
216-cell subgrid).

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
- **The §5 pooled-vs-A comparison does not control for daily/weekly slot competition.**
  `run_one_config` calls `apply_daily_selection`, which caps trades at `max_per_day=3` /
  `max_per_week=15` and selects by `(grade, rank_score)` descending, so A눌림목-alone and
  A눌림목-within-the-pool select substantially different, not directly decomposed, trade sets — see
  §5's caveat for detail.
- **C촉매 and D박스 are explicitly out of scope** — each gets its own sub-project (7b, 7c) after
  this one, per the user's decision to split rather than combine. **B지지선 is also out of scope
  here and remains unmeasured**: it was superseded in this research line by a purpose-built
  replacement pattern (E반등/oversold-bounce, sub-project 4), and that sub-project verified E반등
  using its own separate candidate generator — it never touched B지지선 or B지지선's own share of the
  pooled candidate set. The pooled-vs-isolated comparison in §5 is necessarily incomplete until
  7b/7c land (and B지지선's contribution is never directly measured by this research line's current
  scope): it is not yet possible to say which of B지지선, C촉매, or D박스 (if any) drags the true
  A+B+C+D pooled average down relative to its own weight in the pool, only that A눌림목 does not
  appear to be the primary culprit.

  > **Correction (2026-08-02, sub-project 9)**: the "superseded by E반등" framing above is
  > factually wrong. `isPatternB` (B지지선) remained live and unchanged in `src/swing-scanner.src.js`
  > the entire time; E반등/oversold-bounce never shipped to production (every analysis document in
  > that track states "no production code changed"). B지지선 was simply unverified in isolation, not
  > deprecated — it has since been verified: see
  > `docs/03-analysis/swing-algo-pattern-b-verification.analysis.md` §1.

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

What this sub-project *does* establish, and the reason it was worth running: A눌림목 in isolation
does not look obviously worse than the true, corrected A+B+C+D pooled subgrid comparison in §5 (the
`exclude_d_box=False` 216-cell subgrid — D박스 is *not* excluded from this comparison), and by most
train-side measures is mildly better. This is a directional finding, not a rigorous like-for-like
decomposition — as §5's caveat explains, `apply_daily_selection`'s daily/weekly slot competition
means A눌림목-alone and A눌림목-within-the-pool select substantially different trade sets, so this
comparison cannot cleanly attribute a share of the pooled result to A눌림목. **This sub-project does
not establish that C촉매 or D박스 specifically are the patterns pulling the pooled average down** —
an earlier version of this section drew that inference from a mixed-pool (`exclude_d_box=True`)
comparison that has since been corrected (see §5's correction note), and neither the corrected
comparison nor the slot-competition caveat supports singling out any specific pattern as the
culprit. **B지지선 is also an open question, not a settled one** — it was superseded in this research
line by a purpose-built replacement pattern (E반등/oversold-bounce, sub-project 4), and that
sub-project verified E반등 using its own separate candidate generator, not B지지선's own share of the
pooled candidate set, which remains unmeasured. What remains genuinely open is each of B지지선's,
C촉매's, and D박스's *individual* contribution to the pooled average, which this sub-project cannot
determine and does not attempt to. C촉매 and D박스 are explicitly deferred to sub-projects 7b (C촉매)
and 7c (D박스); B지지선's own contribution is not currently scheduled to be measured by any planned
sub-project, so 7b/7c should not be read as completing a full four-pattern decomposition of the
pooled result.

> **Correction (2026-08-02, sub-project 9)**: "B지지선 ... superseded ... not currently scheduled"
> above is stale/wrong on both counts. E반등 never shipped to production; B지지선 (`isPatternB`)
> remained live throughout. It has since been individually verified — see
> `docs/03-analysis/swing-algo-pattern-b-verification.analysis.md`. All four patterns (A/B/C/D)
> now have isolated-verification data on record; this still does not decompose the pooled result
> (see that document's own §5/§6 for why).

---

No production code (`src/swing-scanner.src.js`) has been changed by this sub-project. C촉매
(sub-project 7b) and D박스 (sub-project 7c) remain to be verified separately, and B지지선's own share
of the pooled candidate set remains unmeasured by any currently planned sub-project — no conclusion
should be drawn about the full four-pattern production system until that gap is addressed.

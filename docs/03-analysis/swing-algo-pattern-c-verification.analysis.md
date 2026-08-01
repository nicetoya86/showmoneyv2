# swing-algo-pattern-c-verification Analysis Report

> **Analysis Type**: Empirical Result Report (PDCA Do → Check)
>
> **Project**: showmoneyv2
> **Feature**: swing-algo-pattern-c-verification — Swing Algo Enhancement Sub-project 7b
> (per-pattern `hit_rate`/`trades_per_week`/`cagr_15slot` verification for production pattern
> **C촉매 (촉매이벤트)**, run in isolation from the other three production patterns, following the
> same method as sub-project 7a)
> **Design Doc**: [2026-08-02-swing-algo-pattern-c-verification-design.md](../superpowers/specs/2026-08-02-swing-algo-pattern-c-verification-design.md)
> **Implementation Plan**: [2026-08-02-swing-algo-pattern-c-verification.md](../superpowers/plans/2026-08-02-swing-algo-pattern-c-verification.md)
> **Date**: 2026-08-02
> **Prior work**: [swing-algo-pattern-a-verification.analysis.md](swing-algo-pattern-a-verification.analysis.md)
> (sub-project 7a — same method applied to A눌림목; found target_not_met, no change to production
> status recommended, and established the slot-competition caveat and unmeasured-patterns caveat
> this sub-project carries forward) and
> [swing-algo-target-stop-retuning.analysis.md](swing-algo-target-stop-retuning.analysis.md)
> (sub-project 2 — grid-searched the pooled A눌림목+B지지선+C촉매+D박스 candidate set, found it
> uniformly unprofitable, never broken out per pattern)

---

## 1. Method Summary

This sub-project makes **no changes to `evaluate_candidate()` (in `generate_signal_candidates.py`)
and no changes to `backtest/target_stop_grid_search.py`**. It only filters sub-project 2's
already-committed pooled candidate cache down to `pattern_type == "C촉매"` and re-runs that
module's existing, unmodified `run_one_config`/`select_best_config` against the filtered subset.

The filter step produced `backtest_pattern_c_candidates.json`: **5,226 candidates**, confirmed
directly from the file (`len(candidates['candidates']) == 5226`).

The grid re-run produced `backtest_pattern_c_grid_results.json`, a **216-cell grid**
(`train_results` has exactly 216 entries, confirmed directly) over:

- `target_pct` ∈ {3%, 4%, 5%, 6%, 8%, 10%} (6 values)
- `stop_pct` ∈ {1%, 1.5%, 2%, 2.5%, 3%, 4%} (6 values)
- `min_score` ∈ {60, 90, 110} (3 values)
- `regime_gate` ∈ {off, on} (2 values)
- `exclude_d_box` fixed `False` (meaningless on a pool already filtered to a single non-D pattern)

6 × 6 × 3 × 2 = 216 cells, identical axis structure to sub-project 7a's A눌림목 grid.

Train/test split, decision gate, and reliability floor are unchanged from every prior sub-project:
train `2022-01-01`..`2024-06-30`, test `2024-07-01`..`2026-01-01`; a configuration passes only if,
on **both** splits, `hit_rate >= 90%` AND `trades_per_week >= 5` AND `cagr_15slot > 0`, with
`n_trades >= 50` as a prerequisite reliability floor before any pass/fail conclusion is trusted.

C촉매 ("촉매이벤트") is disclosure/supply-event-driven (DART filings, 외국인/기관 순매수), a
qualitatively different trigger from A눌림목's technical pullback setup — noted here as context for
the comparison in §5, not as a finding in itself.

## 2. Grid Summary

From `backtest_pattern_c_grid_results.json`'s `summary` block, across all 216 train cells:

| Metric (train, 216 cells) | Value |
|---|---:|
| Grid cell count | 216 |
| Cells clearing `hit_rate >= 90%` | **0 / 216** |
| Cells clearing `trades_per_week >= 5` | 216 / 216 |
| Cells with `cagr_15slot > 0` | **0 / 216** |
| Cells clearing all three simultaneously (full train-side gate) | **0 / 216** |
| Max `hit_rate` across the grid | 46.23% |
| Max `cagr_15slot` across the grid | -10.36%/yr |
| Min `cagr_15slot` across the grid | -25.94%/yr |

As in every prior sub-project, frequency is never the binding constraint — all 216 cells clear
`trades_per_week >= 5`. The binding constraint is `cagr_15slot`: not one cell out of 216 is
profitable on train. The best any cell manages is `target_pct=10%, stop_pct=1%, min_score=90,
regime_gate=False` — `n_trades=1025, hit_rate=6.63%, avg_pnl=-0.41%, cagr_15slot=-10.36%,
mdd_15slot=-24.99%`. The worst cell is `target_pct=3%, stop_pct=4%, min_score=90,
regime_gate=False` — `n_trades=1231, hit_rate=46.22%, cagr_15slot=-25.94%,
mdd_15slot=-52.53%`.

A trader's honest read: the same shape recurs — tight-target/wide-stop cells buy a moderate hit
rate but bleed cagr, wide-target/tight-stop cells preserve cagr somewhat (still deeply negative)
but collapse hit_rate into single digits. There is no cell anywhere in this grid where both move in
the trader's favor at once. C촉매's grid-best cagr cell (-10.36%) is meaningfully worse than
A눌림목's grid-best cagr cell (-6.28%, per 7a) — see §5 for the full cross-pattern comparison.

## 3. Selected Configuration: Train vs. Test

`select_best_config`'s fallback rule (no cell cleared `hit_rate >= 90%`, so it fell back to
filtering on `trades_per_week >= 5` and sorting by `hit_rate` descending, then `cagr_15slot`
descending) selected:

**`target_pct=3%, stop_pct=4%, min_score=60, regime_gate=False`**

| Metric | Train | Test |
|---|---:|---:|
| `n_trades` | 1,233 | 782 |
| `hit_rate` | 46.23% | 44.25% |
| `trades_per_week` | 9.47 | 9.97 |
| `avg_pnl` | -0.88% | -1.05% |
| `cagr_15slot` | -25.56%/yr | -31.50%/yr |
| `mdd_15slot` | -51.92% | -43.42% |

Both splits clear `n_trades >= 50` by more than an order of magnitude (1,233 and 782), so this
result is statistically reliable, not a small-sample artifact. Both splits clear
`trades_per_week >= 5` comfortably (9.47 and 9.97). Both splits fail `hit_rate >= 90%` badly
(short by 43.77pp train, 45.75pp test) and both splits fail `cagr_15slot > 0` (both deeply
negative).

Unlike A눌림목 (7a), where test looked directionally *better* than train on every metric (higher
hit_rate, less negative cagr, smaller drawdown), C촉매's test result is **worse than train on
cagr** — -31.50% test vs. -25.56% train, a further 5.94pp of annualized loss out of sample — even
though hit_rate is roughly similar between splits (44.25% test vs. 46.23% train, only a 1.98pp
gap). Drawdown is the one metric that improves out of sample here (mdd -43.42% test vs. -51.92%
train), so this is not a uniform test-side collapse, but the profitability metric that matters most
(cagr) moves in the wrong direction. A trader should read this as a more concerning generalization
pattern than 7a's: A눌림목's already-weak result held steady-to-improving out of sample, while
C촉매's already-weak result appears to be deteriorating out of sample on the metric that decides
whether the strategy makes money. With only one train/test split, this cannot be distinguished from
noise with certainty, but it is not a reassuring signal for an event-driven pattern, where one might
hope a real catalyst would behave more consistently across time, not less.

## 4. Decision-Gate Verdict

Applying the three-way outcome framework (target-met / target-not-met-but-reliable /
underpowered) used by every prior sub-project in this line:

- **Not target-met**: `hit_rate` is 46.23% (train) and 44.25% (test) — both roughly 44-46
  percentage points short of the 90% bar. `selection['status'] == "target_not_met"` confirms this
  directly. `cagr_15slot` is negative on both splits (-25.56% train, -31.50% test), so even
  setting the 90% hit_rate bar aside, this configuration would not be a profitable deployment
  candidate on cagr grounds alone.
- **Reliable, not underpowered**: `n_trades = 1,233` (train) and `782` (test) both clear the
  `n_trades >= 50` statistical-reliability floor by more than an order of magnitude.
  `trades_per_week = 9.47` (train) and `9.97` (test) both clear the `>= 5` frequency floor. Every
  leg of the three-way framework except the 90% hit_rate bar (and the `cagr_15slot > 0` bar) is
  cleared on both splits.

**Verdict: target-not-met, but reliably so.** C촉매 in isolation, across an exhaustive 216-cell grid
identical in structure to sub-project 7a's A눌림목 grid, cannot reach `hit_rate >= 90%` profitably
by target/stop/min_score/regime-gate tuning alone. Zero cells clear the hit_rate bar; zero cells
are even profitable on `cagr_15slot` (train-side, per the 216-cell grid — the grid is only fully
evaluated on train; test is evaluated once, for the selected config only). This is a decisive,
well-powered negative result, not a small-sample fluke or a near-miss — and, per §3, the test-side
deterioration on cagr makes this result look, if anything, slightly worse out of sample than train
alone would suggest.

## 5. Comparison to Sub-project 7a (A눌림목) and to the Pooled Sub-project 2 Result

**Slot-competition caveat (stated up front, per this plan's Global Constraints)**: `run_one_config`
calls `apply_daily_selection` (in `backtest/run_swing_v2_backtest.py`), which caps trades at
`max_per_day=3` / `max_per_week=15`, selecting among same-day candidates by `(grade, rank_score)`
descending. This means candidates compete for a scarce number of daily/weekly slots. Any comparison
between C촉매-isolated (this sub-project), A눌림목-isolated (7a), and the pooled A+B+C+D subgrid is
**not a like-for-like decomposition** — each isolated run's candidates only compete against
themselves for slots, so candidates that would be crowded out by other patterns in the pooled
system can appear in an isolated run instead. Every comparison below is stated with this caveat in
mind; no new uncommitted numbers are introduced to try to quantify the crowding-out effect itself —
it is described qualitatively only.

**Reference points, re-derived directly from their source files this session:**

- **A눌림목 isolated (7a)**, from `backtest_pattern_a_grid_results.json`: grid max train
  `cagr_15slot` = -6.28%/yr, grid min = -28.90%/yr, 0/216 cells clear `hit_rate >= 90%`. Selected
  config: train `n=1287, hit_rate=49.34%, cagr_15slot=-21.22%`; test `n=786, hit_rate=54.33%,
  cagr_15slot=-12.61%`.
- **Pooled A+B+C+D, `exclude_d_box=False` subgrid**, re-derived from
  `backtest_grid_search_results.json`'s 432 `train_results` cells filtered to `exclude_d_box is
  False` (216 cells, confirmed by direct count): grid max train `cagr_15slot` = **-10.49%/yr**
  (`target_pct=6%, stop_pct=1%, min_score=60, regime_gate=True, n_trades=1104,
  hit_rate=11.23%`), grid min = **-29.96%/yr** (`target_pct=3%, stop_pct=4%, min_score=90,
  regime_gate=True, n_trades=1406, hit_rate=45.95%`). Re-applying the same fallback selection rule
  (filter `trades_per_week >= 5`, sort by `hit_rate` descending then `cagr_15slot` descending)
  within just this subgrid selects `target_pct=3%, stop_pct=4%, min_score=60, regime_gate=False`
  with **train** `hit_rate=46.14%, cagr_15slot=-29.31%/yr, n_trades=1424`. As established in
  7a's corrected §5, this in-subgrid selection has no corresponding **test**-side figure —
  `backtest_grid_search_results.json` only computed a single `test_result`, for the original
  mixed-pool (`exclude_d_box=True`) selection — so the pooled row below is train-only. Note also
  that this pooled subgrid's fallback-selected cell and C촉매's own selected cell share
  `min_score=60`, while A눌림목's (7a) selected cell used `min_score=110` — a further
  non-like-for-like axis on top of the slot-competition caveat, since the three
  "fallback-selected" rows in the table below do not hold `min_score` constant across patterns.

**Three-way comparison table (train-side; caveated per above — not a decomposition):**

| Metric | Pooled A+B+C+D, `exclude_d_box=False` subgrid (216 cells) | A눌림목 alone (7a, 216 cells) | C촉매 alone (this sub-project, 216 cells) |
|---|---:|---:|---:|
| Cells clearing `hit_rate >= 90%` | 0 / 216 | 0 / 216 | 0 / 216 |
| Grid max `cagr_15slot` (train) | -10.49%/yr | -6.28%/yr | -10.36%/yr |
| Grid min `cagr_15slot` (train) | -29.96%/yr | -28.90%/yr | -25.94%/yr |
| Fallback-selected `hit_rate` (train) | 46.14% | 49.34% | 46.23% |
| Fallback-selected `cagr_15slot` (train) | -29.31%/yr | -21.22%/yr | -25.56%/yr |

Test-side, for reference (no pooled test-side figure exists to compare against, per the note
above): A눌림목 `hit_rate=54.33%, cagr_15slot=-12.61%`; C촉매 `hit_rate=44.25%,
cagr_15slot=-31.50%`.

**Honest trader-perspective read**: on this train-side comparison, C촉매 in isolation sits *between*
A눌림목 and the pooled subgrid on most axes — its grid-best cagr cell (-10.36%) is essentially tied
with the pooled subgrid's grid-best cell (-10.49%, a 0.12pp gap) and clearly worse than A눌림목's
(-6.28%); its selected-config cagr (-25.56%) is better than the pooled subgrid's selected-config
cagr (-29.31%, a ~3.75pp gap) but worse than A눌림목's (-21.22%, a ~4.34pp gap in the other
direction). C촉매's grid-worst cell (-25.94%) is actually the *least bad* of the three worst-cell
figures compared here. On hit_rate, C촉매's selected-config train figure (46.23%) sits almost
exactly on top of the pooled subgrid's (46.14%) and meaningfully below A눌림목's (49.34%). Once test
is considered, the picture diverges further: A눌림목's test numbers improve on its own train numbers
(a finding from 7a's document's own §3), while C촉매's test numbers are worse than its own train
numbers on cagr (this document's §3 above) — so on an out-of-sample view, C촉매 looks like the
weaker of the two isolated patterns, not just "in between" on a train-only view. None of this should be read as a rigorous decomposition
of either pattern's share of the pooled result — per the slot-competition caveat, each of these
three numbers comes from a differently-selected portfolio of trades, not from partitioning one
shared trade set into components. What can be said, properly caveated: C촉매 in isolation does not
look like an obviously stronger pattern than the pooled average it sits inside, and its test-side
deterioration is a mildly more concerning signal than anything seen in 7a's A눌림목 result. It is
not, on these numbers, a candidate for isolated deployment or for retuning — it is comprehensively
unprofitable at every grid cell, the same as every other pattern examined in this research line so
far.

## 6. What Remains Open

This sub-project adds only C촉매's isolated profile to the record. It does **not**, combined with
7a, constitute a partial decomposition of the pooled system — per the slot-competition caveat in
§5, isolated-pattern runs and the pooled run select materially different trade sets, so no
per-pattern "share" of the pooled result can be read off from these two sub-projects together.

A눌림목's own pooled contribution remains separately unmeasured (isolated ≠ pooled share, per the
slot-competition caveat). B지지선's pooled contribution also remains unmeasured: B지지선 was
superseded in this research line by a purpose-built replacement pattern (E반등/oversold-bounce,
sub-project 4), and that sub-project verified E반등 using its own separate candidate generator — it
never touched B지지선 or B지지선's own share of the pooled candidate set.

D박스 (sub-project 7c) still remains to be verified. Until it lands, no conclusion should be drawn
about a full four-pattern decomposition of the pooled A+B+C+D result. The patterns now individually
examined are A눌림목 (7a) and C촉매 (this sub-project) — B지지선 and D박스 remain unmeasured in
isolation. Having completed isolated verification does not, by itself, establish that either
A눌림목 or C촉매 is or isn't responsible for the pooled result's weakness.

## 7. Limitations

- **Single train/test split**, same acknowledged limitation as every prior sub-project in this
  line — neither the grid search nor the cross-pattern comparison has been validated across
  multiple splits or a walk-forward scheme.
- **Discrete 216-cell grid** — the true optimum may sit between grid points, but the
  monotonic-degradation pattern seen across every prior grid in this line (including this one, see
  §2) makes a hidden profitable pocket between points unlikely to reverse a clearly negative
  finding here.
- **Slot-competition confound** (§5) — any comparison against A눌림목's isolated result or the
  pooled A+B+C+D result is directional, not a decomposition. `run_one_config` calls
  `apply_daily_selection`, which caps trades at `max_per_day=3` / `max_per_week=15` and selects by
  `(grade, rank_score)` descending, so C촉매-alone and C촉매-within-the-pool select substantially
  different, not directly decomposed, trade sets.
- This sub-project inherits sub-project 1's simulation-machinery limitations: orderbook ask/bid
  ratio and pattern-C buy-ratio blocks are not modeled in the backtest simulation (confirmed still
  current per `docs/03-analysis/backtest.analysis.md`'s GAP-1/GAP-2 fix notes), since
  `run_one_config` and its dependencies are reused unmodified. **This caveat weighs more heavily on
  this sub-project than it did on 7a's A눌림목 result**: production holds back C촉매 signals when
  the live buy-execution ratio falls below 40% (`TOSS_WEAK_BUY_RATIO_C` in
  `src/swing-scanner.src.js`, lines ~1568/1691), a real-time filter `backtest/toss_liveprice.py`
  explicitly cannot model historically (no historical equivalent, since it requires real-time
  order-book/trade-tape data that does not exist historically — see that file's lines 18-22). This
  session's 5,226-candidate / 1,233-train-trade pool is therefore a superset of what production
  would have actually sent for C촉매 specifically — some measured "trades" here would never have
  reached a real user.
- **Flat round-trip fee assumption** — same inherited simulation-machinery limitation noted in
  7a's Limitations section: the backtest simulation assumes a flat round-trip fee, not a
  size/liquidity-sensitive one.
- **Unmeasured-patterns caveat**: A눌림목's and B지지선's own pooled contributions remain separately
  unmeasured (isolated ≠ pooled share, per the slot-competition caveat). B지지선 was superseded by a
  purpose-built replacement pattern (E반등, sub-project 4) that verified E반등, not B지지선 itself.
  This sub-project adds only C촉매's isolated profile to the record — it does not, combined with
  7a, constitute a partial decomposition of the pooled system. D박스 (7c) still remains to be
  verified.

## 8. Final Recommendation

**No change to C촉매's current production deployment status is recommended.** No production code
(`src/swing-scanner.src.js`) was touched by this sub-project — it is a pure verification exercise
against already-committed backtest infrastructure and cached data. C촉매 continues running in
production exactly as it does today (subject to the `TOSS_WEAK_BUY_RATIO_C` caveat in §7 above —
production does not send every signal this backtest counts as a trade), pending D박스's result in
sub-project 7c.

This finding does not surface a new lever worth pursuing: the 216-cell grid is exhaustive over the
same axes used everywhere else in this research line, and it produces the now-familiar shape — 0/216
cells reach `hit_rate >= 90%`, 0/216 cells are even profitable on train, and the best-available
configuration is a reliable-but-losing -25.56%/-31.50% (train/test) `cagr_15slot`. There is nothing
here that argues for retuning C촉매's target/stop/min_score/regime-gate parameters in production.

What this sub-project *does* establish: C촉매 in isolation sits roughly between A눌림목's isolated
result (7a) and the pooled subgrid comparison on most train-side metrics (§5), but its test-side
result is worse than its own train result on cagr — the opposite of A눌림목's pattern, where test
improved on train. That makes C촉매 the weaker of the two isolated patterns examined so far on an
out-of-sample view, though this is a directional read, not a precise ranking, given the
slot-competition caveat that makes any cross-run comparison an imperfect one. **This sub-project
does not establish that C촉매 specifically is the pattern pulling the pooled average down** — the
slot-competition caveat means neither this sub-project nor 7a can cleanly attribute a share of the
pooled result to any one pattern. D박스 (sub-project 7c) remains to be verified, and B지지선's own
contribution to the pool is not currently scheduled to be measured by any planned sub-project, so
7b (this document) plus 7a and the upcoming 7c should not be read as completing a full four-pattern
decomposition of the pooled result.

---

No production code (`src/swing-scanner.src.js`) has been changed by this sub-project. D박스
(sub-project 7c) remains to be verified separately, and B지지선's own share of the pooled candidate
set remains unmeasured by any currently planned sub-project — no conclusion should be drawn about
the full four-pattern production system until that gap is addressed.

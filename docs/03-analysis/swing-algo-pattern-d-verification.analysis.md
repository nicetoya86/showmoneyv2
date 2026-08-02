# swing-algo-pattern-d-verification Analysis Report

> **Analysis Type**: Empirical Result Report (PDCA Do → Check)
>
> **Project**: showmoneyv2
> **Feature**: swing-algo-pattern-d-verification — Swing Algo Enhancement Sub-project 7c
> (per-pattern `hit_rate`/`trades_per_week`/`cagr_15slot` verification for production pattern
> **D박스 (박스권돌파)**, run in isolation from the other three production patterns, following the
> same method as sub-projects 7a and 7b)
> **Design Doc**: [2026-08-02-swing-algo-pattern-d-verification-design.md](../superpowers/specs/2026-08-02-swing-algo-pattern-d-verification-design.md)
> **Implementation Plan**: [2026-08-02-swing-algo-pattern-d-verification.md](../superpowers/plans/2026-08-02-swing-algo-pattern-d-verification.md)
> **Date**: 2026-08-02
> **Prior work**: [swing-algo-pattern-a-verification.analysis.md](swing-algo-pattern-a-verification.analysis.md)
> (sub-project 7a — same method applied to A눌림목; found target_not_met, no change to production
> status recommended, and established the slot-competition caveat and unmeasured-patterns caveat
> this sub-project carries forward) and
> [swing-algo-pattern-c-verification.analysis.md](swing-algo-pattern-c-verification.analysis.md)
> (sub-project 7b — same method applied to C촉매; also found target_not_met, no change to
> production status recommended, and restated both caveats up front, plus flagged a test-side
> deterioration on cagr this sub-project checks for as well)

---

## 1. Method Summary

This sub-project makes **no changes to `evaluate_candidate()` (in `generate_signal_candidates.py`)
and no changes to `backtest/target_stop_grid_search.py`**. It only filters sub-project 2's
already-committed pooled candidate cache down to `pattern_type == "D박스"` and re-runs that
module's existing, unmodified `run_one_config`/`select_best_config` against the filtered subset.

The filter step produced `backtest_pattern_d_candidates.json`: **4,557 candidates**, confirmed
directly from the file (`len(candidates['candidates']) == 4557`), split `hold_days=5` (3,710) /
`hold_days=4` (847) — also confirmed directly from the file.

The grid re-run produced `backtest_pattern_d_grid_results.json`, a **216-cell grid**
(`train_results` has exactly 216 entries, confirmed directly) over:

- `target_pct` ∈ {3%, 4%, 5%, 6%, 8%, 10%} (6 values)
- `stop_pct` ∈ {1%, 1.5%, 2%, 2.5%, 3%, 4%} (6 values)
- `min_score` ∈ {60, 90, 110} (3 values)
- `regime_gate` ∈ {off, on} (2 values)
- `exclude_d_box` fixed `False` — here this is a no-op for a different reason than in 7b: the pool
  is *entirely* D박스 candidates, so `exclude_d_box=True` would trivially zero out every result
  rather than harmlessly excluding nothing.

6 × 6 × 3 × 2 = 216 cells, identical axis structure to sub-projects 7a's and 7b's grids.

Train/test split, decision gate, and reliability floor are unchanged from every prior sub-project:
train `2022-01-01`..`2024-06-30`, test `2024-07-01`..`2026-01-01`; a configuration passes only if,
on **both** splits, `hit_rate >= 90%` AND `trades_per_week >= 5` AND `cagr_15slot > 0`, with
`n_trades >= 50` as a prerequisite reliability floor before any pass/fail conclusion is trusted.

D박스 ("박스권돌파") is a technical box-breakout trigger (`currentPrice > box25High`, a volume
multiple, `sma20 > sma60`), qualitatively different from both A눌림목's pullback-and-bounce trigger
and C촉매's disclosure/supply-event trigger — noted here as context for the comparison in §5, not
as a finding in itself.

## 2. Grid Summary

From `backtest_pattern_d_grid_results.json`'s `summary` block, across all 216 train cells:

| Metric (train, 216 cells) | Value |
|---|---:|
| Grid cell count | 216 |
| Cells clearing `hit_rate >= 90%` | **0 / 216** |
| Cells clearing `trades_per_week >= 5` | 216 / 216 |
| Cells with `cagr_15slot > 0` | **0 / 216** |
| Cells clearing all three simultaneously (full train-side gate) | **0 / 216** |
| Max `hit_rate` across the grid | 45.68% |
| Max `cagr_15slot` across the grid | -6.43%/yr |
| Min `cagr_15slot` across the grid | -24.67%/yr |

As in every prior sub-project, frequency is never the binding constraint — all 216 cells clear
`trades_per_week >= 5`. The binding constraint is `cagr_15slot`: not one cell out of 216 is
profitable on train. The best any cell manages is `target_pct=10%, stop_pct=1%, min_score=60,
regime_gate=False` — `n_trades=973, hit_rate=7.09%, avg_pnl=-0.29%, cagr_15slot=-6.43%,
mdd_15slot=-17.95%`. The worst cell is `target_pct=5%, stop_pct=4%, min_score=90,
regime_gate=False` — `n_trades=1138, hit_rate=32.16%, cagr_15slot=-24.67%, mdd_15slot=-51.67%`.

A trader's honest read: the now-familiar shape recurs a third time — tight-target/wide-stop cells
buy a moderate hit rate but bleed cagr, wide-target/tight-stop cells preserve cagr somewhat (still
deeply negative) but collapse hit_rate into single digits. There is no cell anywhere in this grid
where both move in the trader's favor at once. D박스's grid-best cagr cell (-6.43%) is close to,
but marginally behind, A눌림목's grid-best cagr cell (-6.28%, per 7a — a narrow 0.15pp gap in
A눌림목's favor), and clearly better than C촉매's (-10.36%, per 7b) — see §5 for the full
cross-pattern comparison.

## 3. Selected Configuration: Train vs. Test

`select_best_config`'s fallback rule (no cell cleared `hit_rate >= 90%`, so it fell back to
filtering on `trades_per_week >= 5` and sorting by `hit_rate` descending, then `cagr_15slot`
descending) selected:

**`target_pct=3%, stop_pct=4%, min_score=110, regime_gate=False`**

| Metric | Train | Test |
|---|---:|---:|
| `n_trades` | 996 | 678 |
| `hit_rate` | 45.68% | 45.72% |
| `trades_per_week` | 7.65 | 8.64 |
| `avg_pnl` | -0.78% | -0.86% |
| `cagr_15slot` | -19.29%/yr | -23.34%/yr |
| `mdd_15slot` | -42.47% | -33.14% |

Both splits clear `n_trades >= 50` by more than an order of magnitude (996 and 678), so this
result is statistically reliable, not a small-sample artifact. Both splits clear
`trades_per_week >= 5` comfortably (7.65 and 8.64). Both splits fail `hit_rate >= 90%` badly
(short by 44.32pp train, 44.28pp test) and both splits fail `cagr_15slot > 0` (both deeply
negative).

Hit_rate is essentially flat between splits here (45.68% train vs. 45.72% test, a 0.04pp gap —
neither A눌림목's clear test-side improvement nor C촉매's test-side decline). Cagr, however, moves
in the wrong direction out of sample: -19.29% train to -23.34% test, a further 4.05pp of
annualized loss — smaller than C촉매's 5.94pp test-side cagr deterioration (7b), but the same
direction, and unlike A눌림목's cagr, which improved by 8.61pp out of sample (7a). Drawdown improves
out of sample here (mdd -33.14% test vs. -42.47% train), the same direction as C촉매's mdd (D박스's
train-side drawdown is the smallest of the three at -42.47%, vs. -45.16% for A눌림목 and -51.92% for
C촉매; out of sample, though, A눌림목's -19.34% is materially smaller than D박스's -33.14%, which in
turn beats C촉매's -43.42%). A trader should read this as a third distinct generalization shape in
this research line: A눌림목
looked steady-to-improving out of sample, C촉매 looked steady-to-worsening on both hit_rate and
cagr, and D박스 looks flat on hit_rate but mildly worsening on cagr — not a reassuring signal for
what is, after all, an exhaustive negative result on train already.

## 4. Decision-Gate Verdict

Applying the three-way outcome framework (target-met / target-not-met-but-reliable /
underpowered) used by every prior sub-project in this line:

- **Not target-met**: `hit_rate` is 45.68% (train) and 45.72% (test) — both roughly 44 percentage
  points short of the 90% bar. `selection['status'] == "target_not_met"` confirms this directly.
  `cagr_15slot` is negative on both splits (-19.29% train, -23.34% test), so even setting the 90%
  hit_rate bar aside, this configuration would not be a profitable deployment candidate on cagr
  grounds alone.
- **Reliable, not underpowered**: `n_trades = 996` (train) and `678` (test) both clear the
  `n_trades >= 50` statistical-reliability floor by more than an order of magnitude.
  `trades_per_week = 7.65` (train) and `8.64` (test) both clear the `>= 5` frequency floor. Every
  leg of the three-way framework except the 90% hit_rate bar (and the `cagr_15slot > 0` bar) is
  cleared on both splits.

**Verdict: target-not-met, but reliably so.** D박스 in isolation, across an exhaustive 216-cell
grid identical in structure to sub-projects 7a's and 7b's grids, cannot reach `hit_rate >= 90%`
profitably by target/stop/min_score/regime-gate tuning alone. Zero cells clear the hit_rate bar;
zero cells are even profitable on `cagr_15slot` (train-side, per the 216-cell grid — the grid is
only fully evaluated on train; test is evaluated once, for the selected config only). This is a
decisive, well-powered negative result, not a small-sample fluke or a near-miss — the third such
result in this research line, with no cell of the three 216-cell grids run so far (7a, 7b, this
sub-project) reaching profitability.

## 5. Comparison to Sub-project 7a (A눌림목), 7b (C촉매), and to the Pooled Sub-project 2 Result

**Slot-competition caveat (stated up front, per this plan's Global Constraints)**: `run_one_config`
calls `apply_daily_selection` (in `backtest/run_swing_v2_backtest.py`), which caps trades at
`max_per_day=3` / `max_per_week=15`, selecting among same-day candidates by `(grade, rank_score)`
descending. This means candidates compete for a scarce number of daily/weekly slots. Any comparison
between D박스-isolated (this sub-project), A눌림목-isolated (7a), C촉매-isolated (7b), and the
pooled A+B+C+D subgrid is **not a like-for-like decomposition** — each isolated run's candidates
only compete against themselves for slots, so candidates that would be crowded out by other
patterns in the pooled system can appear in an isolated run instead. Every comparison below is
stated with this caveat in mind; no new uncommitted numbers are introduced to try to quantify the
crowding-out effect itself — it is described qualitatively only.

**Reference points, cited directly from their source documents (not re-derived this session):**

- **A눌림목 isolated (7a)**, from `swing-algo-pattern-a-verification.analysis.md`: grid max train
  `cagr_15slot` = -6.28%/yr, grid min = -28.90%/yr, 0/216 cells clear `hit_rate >= 90%`. Selected
  config: train `n=1287, hit_rate=49.34%, cagr_15slot=-21.22%`; test `n=786, hit_rate=54.33%,
  cagr_15slot=-12.61%`.
- **C촉매 isolated (7b)**, from `swing-algo-pattern-c-verification.analysis.md`: grid max train
  `cagr_15slot` = -10.36%/yr, grid min = -25.94%/yr, 0/216 cells clear `hit_rate >= 90%`. Selected
  config: train `n=1233, hit_rate=46.23%, cagr_15slot=-25.56%`; test `n=782, hit_rate=44.25%,
  cagr_15slot=-31.50%`.
- **Pooled A+B+C+D, `exclude_d_box=False` subgrid**, from 7a's corrected §5 (re-derived there
  directly from `backtest_grid_search_results.json`'s 432 `train_results` cells filtered to
  `exclude_d_box is False`, 216 cells): grid max train `cagr_15slot` = **-10.49%/yr**
  (`target_pct=6%, stop_pct=1%, min_score=60, regime_gate=True, n_trades=1104,
  hit_rate=11.23%`), grid min = **-29.96%/yr** (`target_pct=3%, stop_pct=4%, min_score=90,
  regime_gate=True, n_trades=1406, hit_rate=45.95%`). The same fallback selection rule applied
  within just this subgrid selects `target_pct=3%, stop_pct=4%, min_score=60, regime_gate=False`
  with **train** `hit_rate=46.14%, cagr_15slot=-29.31%/yr, n_trades=1424` — train-only, since
  `backtest_grid_search_results.json` only computed a single `test_result`, for the original
  mixed-pool (`exclude_d_box=True`) selection, per 7a's and 7b's own notes on this point.

**Four-way comparison table (train-side; caveated per above — not a decomposition):**

| Metric | Pooled A+B+C+D, `exclude_d_box=False` subgrid (216 cells) | A눌림목 alone (7a, 216 cells) | C촉매 alone (7b, 216 cells) | D박스 alone (this sub-project, 216 cells) |
|---|---:|---:|---:|---:|
| Cells clearing `hit_rate >= 90%` | 0 / 216 | 0 / 216 | 0 / 216 | 0 / 216 |
| Grid max `cagr_15slot` (train) | -10.49%/yr | -6.28%/yr | -10.36%/yr | -6.43%/yr |
| Grid min `cagr_15slot` (train) | -29.96%/yr | -28.90%/yr | -25.94%/yr | -24.67%/yr |
| Fallback-selected `hit_rate` (train) | 46.14% | 49.34% | 46.23% | 45.68% |
| Fallback-selected `cagr_15slot` (train) | -29.31%/yr | -21.22%/yr | -25.56%/yr | -19.29%/yr |

Test-side, for reference (no pooled test-side figure exists to compare against, per the note
above): A눌림목 `hit_rate=54.33%, cagr_15slot=-12.61%`; C촉매 `hit_rate=44.25%,
cagr_15slot=-31.50%`; D박스 `hit_rate=45.72%, cagr_15slot=-23.34%`.

**Honest trader-perspective read**: on train-side numbers, D박스 in isolation is not the clear best
of the three isolated patterns on grid-max cagr — its grid-best cagr cell (-6.43%) is marginally
*behind* A눌림목's (-6.28%, a narrow 0.15pp gap, within noise, so A눌림목's grid-max is the better of
the two) though still clearly ahead of C촉매's (-10.36%). Where D박스 does come out ahead of both is
on the *selected*-configuration cagr: its selected-config train cagr (-19.29%) is the best of the
three selected-config figures, beating both A눌림목's (-21.22%, a ~1.93pp gap) and C촉매's (-25.56%,
a ~6.27pp gap). D박스 also has the least-bad grid-worst cell (-24.67%, vs. -28.90% for A눌림목 and
-25.94% for C촉매). On hit_rate, though, D박스's selected-config train figure (45.68%) is the
*lowest* of the three, sitting below C촉매's (46.23%) and further below A눌림목's (49.34%) — so
D박스 buys its better selected-config cagr with a slightly worse hit_rate, the same target/stop
trade-off seen within every single grid in this line, just playing out differently across patterns.

The out-of-sample picture complicates a simple ranking further: A눌림목's test numbers improved on
its own train numbers (7a's §3), C촉매's test numbers were worse than its own train numbers on cagr
(7b's §3), and D박스's test numbers are flat on hit_rate but also worse than train on cagr (this
document's §3) — a third, distinct pattern of generalization, not clearly matching either prior
sub-project. None of this should be read as a rigorous decomposition of any pattern's share of the
pooled result — per the slot-competition caveat, each of these four numbers comes from a
differently-selected portfolio of trades, not from partitioning one shared trade set into
components. What can be said, properly caveated: D박스 in isolation does not look like an obviously
weaker pattern than A눌림목 or C촉매 on this train-side comparison — if anything its cagr profile is
the mildest loss of the three — but it is not, on these numbers, a candidate for isolated
deployment or for retuning either. It is comprehensively unprofitable at every one of its 216 grid
cells, the same as every other pattern examined in this research line so far, and its test-side
cagr deterioration (smaller than C촉매's, but present) is not a reassuring sign for an
already-negative result.

## 6. What Remains Open

This sub-project adds D박스's isolated profile to the record, alongside 7a's A눌림목 and 7b's
C촉매. Together, this **completes individual isolated verification for 3 of the 4 production
patterns (A/C/D)**. It does **not**, combined with 7a and 7b, constitute a full decomposition of
the pooled system — per the slot-competition caveat in §5, isolated-pattern runs and the pooled run
select materially different trade sets, so no per-pattern "share" of the pooled result can be read
off from these three sub-projects together.

A눌림목's and C촉매's own pooled contributions remain separately unmeasured (isolated ≠ pooled
share, per the slot-competition caveat) — their isolated profiles are on record, but that is not
the same as knowing how much of the pooled A+B+C+D result each pattern is actually responsible for.

**B지지선 remains the sole production pattern without isolated verification — by design, not by
oversight.** It was superseded in this research line by a purpose-built replacement pattern
(E반등/oversold-bounce, sub-project 4), and that sub-project verified E반등 using its own separate
candidate generator; it never touched B지지선 or B지지선's own share of the pooled candidate set.
No sub-project currently planned in this research line measures B지지선's isolated profile or its
pooled contribution. With 7a/7b/7c complete, the per-pattern isolated-verification arc for A/C/D is
closed; B지지선 and any true decomposition of the pooled system's result remain open questions this
plan does not attempt to close.

> **Correction (2026-08-02, sub-project 9)**: the "superseded by E반등... by design, not by
> oversight" framing above is factually wrong. `isPatternB` (B지지선) remained live and unchanged
> in `src/swing-scanner.src.js` throughout; E반등 never shipped to production. B지지선 has since
> been individually verified: see `docs/03-analysis/swing-algo-pattern-b-verification.analysis.md`.
> All four patterns (A/B/C/D) now have isolated-verification data on record; this still does not
> decompose the pooled result.

## 7. Limitations

- **Single train/test split**, same acknowledged limitation as every prior sub-project in this
  line — neither the grid search nor the cross-pattern comparison has been validated across
  multiple splits or a walk-forward scheme.
- **Discrete 216-cell grid** — the true optimum may sit between grid points, but the
  monotonic-degradation pattern seen across every prior grid in this line (including this one, see
  §2) makes a hidden profitable pocket between points unlikely to reverse a clearly negative
  finding here.
- **Slot-competition confound** (§5) — any comparison against A눌림목's or C촉매's isolated results
  or the pooled A+B+C+D result is directional, not a decomposition. `run_one_config` calls
  `apply_daily_selection`, which caps trades at `max_per_day=3` / `max_per_week=15` and selects by
  `(grade, rank_score)` descending, so D박스-alone and D박스-within-the-pool select substantially
  different, not directly decomposed, trade sets.
- This sub-project inherits sub-project 1's simulation-machinery limitations: orderbook ask/bid
  ratio blocks are not modeled in the backtest simulation, since `run_one_config` and its
  dependencies are reused unmodified. Unlike C촉매 (7b), **D박스 has no analogous real-time
  execution-ratio gate** — `TOSS_WEAK_BUY_RATIO_C` in `src/swing-scanner.src.js` only branches on
  `patternType === 'C촉매'` — so this particular simulation-vs-production gap does not apply to
  D박스's results specifically.
- **Flat round-trip fee assumption** — same inherited simulation-machinery limitation noted in
  7a's and 7b's Limitations sections: the backtest simulation assumes a flat round-trip fee, not a
  size/liquidity-sensitive one.
- **Unmeasured-patterns caveat**: A눌림목's and C촉매's own pooled contributions remain separately
  unmeasured (isolated ≠ pooled share, per the slot-competition caveat). B지지선 was superseded by a
  purpose-built replacement pattern (E반등, sub-project 4) that verified E반등, not B지지선 itself,
  and B지지선's own pooled contribution is not currently scheduled to be measured by any planned
  sub-project. This sub-project, combined with 7a and 7b, does not constitute a decomposition of
  the pooled system — it completes individual isolated verification for A/C/D only.
  **Correction (2026-08-02, sub-project 9)**: the "superseded"/"not currently scheduled" framing
  is wrong — see the correction note in §6; B지지선 has since been individually verified.

## 8. Final Recommendation

**No change to D박스's current production deployment status is recommended.** No production code
(`src/swing-scanner.src.js`) was touched by this sub-project — it is a pure verification exercise
against already-committed backtest infrastructure and cached data. D박스 continues running in
production exactly as it does today.

This finding does not surface a new lever worth pursuing: the 216-cell grid is exhaustive over the
same axes used everywhere else in this research line, and it produces the now-familiar shape — 0/216
cells reach `hit_rate >= 90%`, 0/216 cells are even profitable on train, and the best-available
configuration is a reliable-but-losing -19.29%/-23.34% (train/test) `cagr_15slot`. There is nothing
here that argues for retuning D박스's target/stop/min_score/regime-gate parameters in production.

What this sub-project *does* establish: D박스 in isolation has the mildest train-side
*selected-config* cagr loss of the three patterns examined in this research line (7a, 7b, this
sub-project) — its selected-config cagr edges out both A눌림목's and C촉매's, though its grid-best
cagr cell sits marginally behind A눌림목's (-6.43% vs. -6.28%, within noise) while still ahead of
C촉매's — but its test-side result
deteriorates on cagr the same direction as C촉매's (though by a smaller margin), and its hit_rate is
the lowest of the three on the selected configuration. This is a directional read, not a precise
ranking, given the slot-competition caveat that makes any cross-run comparison an imperfect one.
**This sub-project does not establish that D박스 specifically is a stronger or weaker pattern than
A눌림목 or C촉매 within the pooled system** — the slot-competition caveat means none of 7a, 7b, or
this sub-project can cleanly attribute a share of the pooled result to any one pattern.

With this sub-project, **individual isolated verification is now complete for 3 of the 4 production
patterns (A/C/D)** — all three come back target_not_met, all three are comprehensively unprofitable
across an exhaustive 216-cell grid, and none surfaces a retuning lever worth pursuing. **This
changes nothing about any of A눌림목's, C촉매's, or D박스's current production deployment status**:
each continues running in production exactly as it does today, this research line having found no
isolated-pattern-level basis to alter any of them. B지지선 remains the sole production pattern
without isolated verification, by design (superseded by E반등 in sub-project 4, not overlooked), and
is not currently scheduled to be measured by any planned sub-project. Any future decomposition of
the *pooled* system's result (as opposed to the isolated per-pattern profiles now on record for
A/C/D) would require a dedicated new sub-project this plan does not attempt — 7a, 7b, and this
document should not be read as having decomposed the pooled A+B+C+D result, only as having each
individually verified one pattern's own isolated profile.

> **Correction (2026-08-02, sub-project 9)**: "B지지선 remains ... by design (superseded by E반등
> ... not overlooked), and is not currently scheduled" above is wrong and stale on every count.
> `isPatternB` remained live in `src/swing-scanner.src.js` throughout; E반등 never shipped to
> production; B지지선 has since been individually verified — see
> `docs/03-analysis/swing-algo-pattern-b-verification.analysis.md`. All four patterns (A/B/C/D)
> now have isolated-verification data on record for the first time in this research line.

---

No production code (`src/swing-scanner.src.js`) has been changed by this sub-project. With 7a
(A눌림목), 7b (C촉매), and this document (D박스) complete, the per-pattern isolated-verification arc
of this research line is closed for A/C/D. B지지선's own share of the pooled candidate set remains
unmeasured by any currently planned sub-project, and no true decomposition of the pooled A+B+C+D
result has been attempted — no conclusion should be drawn about the full four-pattern production
system beyond what each pattern's own isolated profile shows.

# swing-algo-pattern-b-verification Analysis Report

> **Analysis Type**: Empirical Result Report (PDCA Do → Check)
>
> **Project**: showmoneyv2
> **Feature**: swing-algo-pattern-b-verification — Swing Algo Enhancement Sub-project 9
> (per-pattern `hit_rate`/`trades_per_week`/`cagr_15slot` verification for production pattern
> **B지지선 (지지선반등)**, run in isolation from the other three production patterns — the fourth
> and final pattern verified in this manner, completing the isolated-verification arc for all four
> production patterns for the first time in this research line)
> **Design Doc**: [2026-08-02-swing-algo-pattern-b-verification-design.md](../superpowers/specs/2026-08-02-swing-algo-pattern-b-verification-design.md)
> **Implementation Plan**: [2026-08-02-swing-algo-pattern-b-verification.md](../superpowers/plans/2026-08-02-swing-algo-pattern-b-verification.md)
> **Date**: 2026-08-02
> **Prior work**: [swing-algo-pattern-a-verification.analysis.md](swing-algo-pattern-a-verification.analysis.md)
> (sub-project 7a — same method applied to A눌림목; found target_not_met, established the
> slot-competition caveat this document restates verbatim, and first flagged B지지선 as
> "superseded by E반등" — a mischaracterization this document corrects, see §1),
> [swing-algo-pattern-c-verification.analysis.md](swing-algo-pattern-c-verification.analysis.md)
> (sub-project 7b — same method applied to C촉매; also target_not_met, repeated the same
> "B지지선 superseded" framing), and
> [swing-algo-pattern-d-verification.analysis.md](swing-algo-pattern-d-verification.analysis.md)
> (sub-project 7c — same method applied to D박스; also target_not_met, repeated the same framing a
> third time and stated "B지지선 remains the sole production pattern without isolated verification —
> by design, not by oversight." This document establishes that the "by design" premise itself was
> wrong: see §1.)

---

## 1. Method Summary

This sub-project makes **no changes to `evaluate_candidate()` (in `generate_signal_candidates.py`)
and no changes to `backtest/target_stop_grid_search.py`**. It only filters sub-project 2's
already-committed pooled candidate cache down to `pattern_type == "B지지선"` and re-runs that
module's existing, unmodified `run_one_config`/`select_best_config` against the filtered subset.

The filter step produced `backtest_pattern_b_candidates.json`: **1,996 candidates**, confirmed
directly from the file (`len(candidates['candidates']) == 1996`), all at `hold_days=5` (confirmed
directly — no other `hold_days` value appears). This is the smallest of the four production
patterns' candidate pools in the original A+B+C+D pool (A눌림목 9,808; C촉매 5,226; D박스 4,557;
B지지선 1,996 — summing to the same 21,587-candidate total established in sub-project 7a's
document), a caveat carried into §4 and §7 below.

The grid re-run produced `backtest_pattern_b_grid_results.json`, a **216-cell grid**
(`train_results` has exactly 216 entries, confirmed directly) over:

- `target_pct` ∈ {3%, 4%, 5%, 6%, 8%, 10%} (6 values)
- `stop_pct` ∈ {1%, 1.5%, 2%, 2.5%, 3%, 4%} (6 values)
- `min_score` ∈ {60, 90, 110} (3 values)
- `regime_gate` ∈ {off, on} (2 values)
- `exclude_d_box` fixed `False` (meaningless on a pool already filtered to a single non-D pattern,
  identical reasoning to 7a's and 7b's grids)

6 × 6 × 3 × 2 = 216 cells, identical axis structure to sub-projects 7a's, 7b's, and 7c's grids.

Train/test split, decision gate, and reliability floor are unchanged from every prior sub-project:
train `2022-01-01`..`2024-06-30`, test `2024-07-01`..`2026-01-01`; a configuration passes only if,
on **both** splits, `hit_rate >= 90%` AND `trades_per_week >= 5` AND `cagr_15slot > 0`, with
`n_trades >= 50` as a prerequisite reliability floor before any pass/fail conclusion is trusted.

B지지선 ("지지선반등") is a technical support-bounce trigger — a 60-day pullback band
(`corrPct60`), proximity to a past support level (`proxToPast`), the candle turning up
(`dailyChange >= 0.0`), a volume confirmation (`rvolVal >= 1.5`), and an RSI "golden zone"
(`40 <= rsi14 <= 72`) — distinct from A눌림목's post-spike pullback trigger, C촉매's
disclosure/supply-event trigger, and D박스's box-breakout trigger. Noted here as context for the
comparison in §5, not as a finding in itself.

**Correction of the prior "B지지선 superseded by E반등" framing.** Sub-projects 7a, 7b, and 7c each
stated, in their Limitations/What-Remains-Open sections, that B지지선 was "superseded" in this
research line by a purpose-built replacement pattern (E반등/oversold-bounce, sub-projects 4/5/5b/6)
and was therefore out of scope by design. That framing was wrong on the production-code facts.
Verified directly this session:

- `docs/03-analysis/swing-algo-oversold-bounce-hitrate.analysis.md` (sub-project 4, the E반등 sub-
  project 7a/7b/7c each cited as B지지선's "replacement") closes with the sentence: **"No production
  code (`src/swing-scanner.src.js`) has been changed by this sub-project — as with every prior
  sub-project in this line, that remains a separate, later decision."** E반등/oversold-bounce was
  investigated purely as backtest research; it never shipped to production, in that sub-project or
  in any of its follow-ons (5/5b/6, per the MEMORY.md record of this research line).
- `src/swing-scanner.src.js` lines 1325-1332 define `isPatternB` — confirmed still present and live,
  unchanged, checked directly this session:
  ```js
  const isPatternB = (
    corrPct60 <= -PB_CORR_MIN  &&
    corrPct60 >= -PB_CORR_MAX  &&
    proxToPast <= PB_LEVEL_PROX &&
    dailyChange >= 0.0         &&
    rvolVal >= 1.5             &&
    Number.isFinite(rsi14Val) && rsi14Val >= 40 && rsi14Val <= 72
  );
  ```
  This sits alongside `isPatternA`, `isPatternC`, and `isPatternD` in the same live scanning
  function, gated into the OR at line 1346 (`if (!isPatternA && !isPatternB && !isPatternC &&
  !isPatternD) return;`) exactly like the other three production patterns.

B지지선 was never replaced, deprecated, or removed from production at any point in this research
line. It has been live and running in `src/swing-scanner.src.js` the entire time sub-projects 7a,
7b, and 7c were describing it as superseded. This sub-project is not re-verifying a deprecated
pattern — **it is verifying a currently-live production pattern that was simply skipped in the
prior three sub-projects due to that mischaracterization.** With this correction on record, §6
below states what this means for the "all four patterns now verified" milestone.

## 2. Grid Summary

From `backtest_pattern_b_grid_results.json`'s `summary` block, across all 216 train cells:

| Metric (train, 216 cells) | Value |
|---|---:|
| Grid cell count | 216 |
| Cells clearing `hit_rate >= 90%` | **0 / 216** |
| Cells clearing `trades_per_week >= 5` | **29 / 216** |
| Cells with `cagr_15slot > 0` | **0 / 216** |
| Cells clearing all three simultaneously (full train-side gate) | **0 / 216** |
| Max `hit_rate` across the grid | 50.21% |
| Max `cagr_15slot` across the grid | -1.11%/yr |
| Min `cagr_15slot` across the grid | -12.29%/yr |

**This is the first pattern in this research line where frequency is not universally cleared.**
A눌림목, C촉매, and D박스 all cleared `trades_per_week >= 5` on all 216/216 cells; B지지선 clears it
on only **29/216** cells (13.4%). This tracks directly with B지지선 having the smallest candidate
pool of the four (1,996 vs. 4,557-9,808) — the tighter target/stop cells that would otherwise
produce more trades per week simply have fewer underlying candidates to draw from. The binding
constraint is still `cagr_15slot`, not frequency, in the sense that even among the 29 cells that do
clear frequency, none is profitable — but frequency is no longer a free pass the way it was for
A/C/D.

Both the grid-best and grid-worst cagr cells happen to fall outside that 29-cell frequency-passing
subset: the best cell is `target_pct=8%, stop_pct=4%, min_score=60, regime_gate=True` —
`n_trades=406, hit_rate=26.60%, avg_pnl=-0.23%, cagr_15slot=-1.11%, mdd_15slot=-14.73%,
trades_per_week=3.12` (below 5). The worst cell is `target_pct=5%, stop_pct=3%, min_score=60,
regime_gate=False` — `n_trades=745, hit_rate=29.80%, cagr_15slot=-12.29%, mdd_15slot=-30.53%,
trades_per_week=5.72` (above 5).

A trader's honest read: the familiar tight-target/wide-stop-vs-wide-target/tight-stop trade-off
recurs a fourth time, but B지지선's grid is meaningfully shallower than the other three — its
grid-best cagr (-1.11%) is far closer to breakeven than A눌림목's (-6.28%, 7a), D박스's (-6.43%,
7c), or C촉매's (-10.36%, 7b). That is a genuinely different shape from the other three patterns'
grids, not just a milder version of the same result — see §5 for the full cross-pattern read, with
the slot-competition caveat applied before drawing any conclusion from it.

## 3. Selected Configuration: Train vs. Test

`select_best_config`'s fallback rule (no cell cleared `hit_rate >= 90%`, so it fell back to
filtering on `trades_per_week >= 5` and sorting by `hit_rate` descending, then `cagr_15slot`
descending) selected:

**`target_pct=3%, stop_pct=4%, min_score=60, regime_gate=False`**

| Metric | Train | Test |
|---|---:|---:|
| `n_trades` | 727 | 489 |
| `hit_rate` | 50.21% | 48.47% |
| `trades_per_week` | 5.59 | 6.23 |
| `avg_pnl` | -0.54% | -0.68% |
| `cagr_15slot` | -10.28%/yr | -13.62%/yr |
| `mdd_15slot` | -24.71% | -20.23% |

Both splits clear `n_trades >= 50` by more than an order of magnitude (727 and 489), so this result
is statistically reliable, not a small-sample artifact — this holds despite B지지선 having the
smallest candidate pool of the four patterns (§1), addressing directly the risk the design/plan
flagged going in. Both splits clear `trades_per_week >= 5`, though more narrowly than A/C/D's
selected configs (5.59 train / 6.23 test, versus A눌림목's 9.89/10.02, C촉매's 9.47/9.97, D박스's
7.65/8.64 — B지지선's selected config sits closest to the frequency floor of any pattern examined so
far, consistent with §2's smaller frequency-passing cell count). Both splits fail `hit_rate >= 90%`
badly (short by 39.79pp train, 41.53pp test) and both splits fail `cagr_15slot > 0` (both negative).

Hit_rate is close between splits (50.21% train vs. 48.47% test, a 1.74pp gap, mildly worse
out-of-sample — the same direction as C촉매's decline, not A눌림목's improvement or D박스's flat
read). Cagr moves clearly in the wrong direction out of sample: -10.28% train to -13.62% test, a
further 3.34pp of annualized loss — smaller in absolute terms than C촉매's 5.94pp test-side cagr
deterioration (7b) or D박스's 4.05pp (7c), but the same direction as both, continuing a pattern
where three of the four isolated patterns now examined (C촉매, D박스, B지지선) all get worse on
cagr out of sample, and only A눌림목 improved. Drawdown improves out of sample (mdd -20.23% test
vs. -24.71% train), the same direction as C촉매's and D박스's mdd behavior.

**Honest trader-perspective read on the train-to-test move**: a train cagr of -10.28% degrading to
a test cagr of -13.62% at the selected config is not "close but needs tuning" — it is a
configuration that loses money at an annualized rate approaching a sixth of capital per year, on
both splits, with the out-of-sample split *worse*, not better. A trader would not describe this as
a near-miss requiring a small parameter nudge; the grid in §2 shows this is not a tuning problem
(the best cell anywhere in an exhaustive 216-cell sweep is still -1.11%, and that cell fails the
frequency floor). This is a structurally unprofitable pattern at the tested parameterizations, not
a promising one sitting just outside the gate. The one point in B지지선's favor relative to the
other three patterns is that its shortfall is smaller in magnitude — -10.28%/-13.62% is the
mildest of the four selected-config cagr pairs (vs. A눌림목's -21.22%/-12.61%, C촉매's
-25.56%/-31.50%, D박스's -19.29%/-23.34%) — but "least unprofitable of four unprofitable patterns"
is not the same as "profitable," and should not be read as such.

## 4. Decision-Gate Verdict

Applying the three-way outcome framework (target-met / target-not-met-but-reliable / underpowered)
used by every prior sub-project in this line:

- **Not target-met**: `hit_rate` is 50.21% (train) and 48.47% (test) — both roughly 40-42
  percentage points short of the 90% bar. `selection['status'] == "target_not_met"` confirms this
  directly. `cagr_15slot` is negative on both splits (-10.28% train, -13.62% test), so even setting
  the 90% hit_rate bar aside, this configuration would not be a profitable deployment candidate on
  cagr grounds alone.
- **Reliable, not underpowered**: `n_trades = 727` (train) and `489` (test) both clear the
  `n_trades >= 50` statistical-reliability floor comfortably — by roughly 14.5x and 9.8x
  respectively. `trades_per_week = 5.59` (train) and `6.23` (test) both clear the `>= 5` frequency
  floor, though more narrowly than any prior pattern's selected config (§3). Every leg of the
  three-way framework except the 90% hit_rate bar (and the `cagr_15slot > 0` bar) is cleared on
  both splits.

**Verdict: target-not-met, but reliably so — not underpowered.** The design doc and plan flagged,
given B지지선's smaller candidate pool (1,996 vs. 4,557-9,808 for the other three patterns), that
this was the one place in this sub-project where a reliability shortfall was a real risk worth
extra attention. That risk did not materialize: both splits clear `n_trades >= 50` comfortably
(727 and 489), so this is a well-powered negative result, not a small-sample fluke. B지지선 in
isolation, across an exhaustive 216-cell grid identical in structure to sub-projects 7a's, 7b's,
and 7c's grids, cannot reach `hit_rate >= 90%` profitably by target/stop/min_score/regime-gate
tuning alone. Zero cells clear the hit_rate bar; zero cells are even profitable on `cagr_15slot`
(train-side, per the 216-cell grid). This is the fourth such decisive, well-powered negative result
in this research line — no cell of any of the four 216-cell grids run so far (7a, 7b, 7c, this
sub-project) reaches profitability.

## 5. Comparison to Sub-projects 7a (A눌림목), 7b (C촉매), 7c (D박스), and to the Pooled Sub-project 2 Result

**Slot-competition caveat (stated up front, per this plan's Global Constraints)**: `run_one_config`
calls `apply_daily_selection` (in `backtest/run_swing_v2_backtest.py`), which caps trades at
`max_per_day=3` / `max_per_week=15`, selecting among same-day candidates by `(grade, rank_score)`
descending. This means candidates compete for a scarce number of daily/weekly slots. Any comparison
between B지지선-isolated (this sub-project), A눌림목-isolated (7a), C촉매-isolated (7b),
D박스-isolated (7c), and the pooled A+B+C+D subgrid is **not a like-for-like decomposition** — each
isolated run's candidates only compete against themselves for slots, so candidates that would be
crowded out by other patterns in the pooled system can appear in an isolated run instead. Every
comparison below is stated with this caveat in mind; no new uncommitted numbers are introduced to
try to quantify the crowding-out effect itself — it is described qualitatively only.

**Reference points, cited directly from their source documents (not re-derived this session):**

- **A눌림목 isolated (7a)**, from `swing-algo-pattern-a-verification.analysis.md`: grid max train
  `cagr_15slot` = -6.28%/yr, grid min = -28.90%/yr, 0/216 cells clear `hit_rate >= 90%`, 216/216
  cells clear `trades_per_week >= 5`. Selected config: train `n=1287, hit_rate=49.34%,
  cagr_15slot=-21.22%`; test `n=786, hit_rate=54.33%, cagr_15slot=-12.61%`.
- **C촉매 isolated (7b)**, from `swing-algo-pattern-c-verification.analysis.md`: grid max train
  `cagr_15slot` = -10.36%/yr, grid min = -25.94%/yr, 0/216 cells clear `hit_rate >= 90%`, 216/216
  cells clear `trades_per_week >= 5`. Selected config: train `n=1233, hit_rate=46.23%,
  cagr_15slot=-25.56%`; test `n=782, hit_rate=44.25%, cagr_15slot=-31.50%`.
- **D박스 isolated (7c)**, from `swing-algo-pattern-d-verification.analysis.md`: grid max train
  `cagr_15slot` = -6.43%/yr, grid min = -24.67%/yr, 0/216 cells clear `hit_rate >= 90%`, 216/216
  cells clear `trades_per_week >= 5`. Selected config: train `n=996, hit_rate=45.68%,
  cagr_15slot=-19.29%`; test `n=678, hit_rate=45.72%, cagr_15slot=-23.34%`.
- **Pooled A+B+C+D, `exclude_d_box=False` subgrid**, from 7a's corrected §5 (re-derived there
  directly from `backtest_grid_search_results.json`'s 432 `train_results` cells filtered to
  `exclude_d_box is False`, 216 cells): grid max train `cagr_15slot` = **-10.49%/yr**
  (`target_pct=6%, stop_pct=1%, min_score=60, regime_gate=True, n_trades=1104,
  hit_rate=11.23%`), grid min = **-29.96%/yr**. The same fallback selection rule applied within
  just this subgrid selects `target_pct=3%, stop_pct=4%, min_score=60, regime_gate=False` with
  **train** `hit_rate=46.14%, cagr_15slot=-29.31%/yr, n_trades=1424` — train-only, per 7a's and
  7b's own notes that `backtest_grid_search_results.json` only computed a single `test_result`, for
  the original mixed-pool (`exclude_d_box=True`) selection.

**Five-way comparison table (train-side; caveated per above — not a decomposition):**

| Metric | Pooled A+B+C+D subgrid (216 cells) | A눌림목 alone (7a) | C촉매 alone (7b) | D박스 alone (7c) | B지지선 alone (this sub-project) |
|---|---:|---:|---:|---:|---:|
| Cells clearing `hit_rate >= 90%` | 0/216 | 0/216 | 0/216 | 0/216 | 0/216 |
| Cells clearing `trades_per_week >= 5` | 216/216 | 216/216 | 216/216 | 216/216 | **29/216** |
| Grid max `cagr_15slot` (train) | -10.49%/yr | -6.28%/yr | -10.36%/yr | -6.43%/yr | **-1.11%/yr** |
| Grid min `cagr_15slot` (train) | -29.96%/yr | -28.90%/yr | -25.94%/yr | -24.67%/yr | **-12.29%/yr** |
| Fallback-selected `hit_rate` (train) | 46.14% | 49.34% | 46.23% | 45.68% | **50.21%** |
| Fallback-selected `cagr_15slot` (train) | -29.31%/yr | -21.22%/yr | -25.56%/yr | -19.29%/yr | **-10.28%/yr** |

Test-side, for reference (no pooled test-side figure exists to compare against, per the note
above): A눌림목 `hit_rate=54.33%, cagr_15slot=-12.61%`; C촉매 `hit_rate=44.25%,
cagr_15slot=-31.50%`; D박스 `hit_rate=45.72%, cagr_15slot=-23.34%`; B지지선 `hit_rate=48.47%,
cagr_15slot=-13.62%`.

**Honest trader-perspective read**: on every train-side metric in the table above, B지지선 in
isolation looks the *least bad* of the four patterns examined in this research line — its
grid-best cagr cell (-1.11%) is the closest to breakeven of any of the four, its grid-worst cell
(-12.29%) is the least severe of the four, its selected-config hit_rate (50.21%) is the highest of
the four, and its selected-config cagr (-10.28%) is by a wide margin the least negative of the
four (roughly 9-15pp better than A눌림목's, C촉매's, or D박스's selected-config train cagr). This is
a real, consistent pattern across every metric compared, not a single cherry-picked number.

But this must be read against two things that qualify it heavily, not just the standard
slot-competition caveat. First, B지지선's frequency profile is structurally different: only 29/216
cells even clear `trades_per_week >= 5`, versus 216/216 for every other pattern — B지지선's
"better" numbers come from a candidate pool an order of magnitude smaller (1,996 vs. 4,557-9,808),
and a smaller, more selective pool naturally produces less-negative average outcomes on some axes
without that implying the underlying signal is actually stronger; it may simply be trading less
often at all, on the trades it does take. Second, and more importantly, both splits still fail
`cagr_15slot > 0` decisively — a train cagr of -10.28% degrading to -13.62% on test is not a
marginal miss on an otherwise-working pattern, it is a comprehensively unprofitable one, same as
the other three. **"Least bad of four bad patterns" is the correct and complete characterization
here — not "close" and not "structurally different from the others in a way that changes the
production recommendation."** None of this should be read as a rigorous decomposition of any
pattern's share of the pooled result — per the slot-competition caveat, each of these five numbers
comes from a differently-selected portfolio of trades, not from partitioning one shared trade set
into components. What can be said, properly caveated: B지지선 in isolation does not look like an
obviously weaker pattern than A눌림목, C촉매, or D박스 — if anything, on this train-side comparison
it looks like the mildest loss of the four — but it is not, on these numbers, a candidate for
isolated deployment or for retuning either. It is comprehensively unprofitable at 187 of its 216
grid cells (the 29 that clear frequency, plus every cell examined for cagr regardless of
frequency, are all negative), consistent with every other pattern examined in this research line,
and its test-side cagr deterioration (present, though smaller in magnitude than C촉매's or D박스's)
is not a reassuring sign for an already-negative result.

## 6. What Remains Open

**With this sub-project, individual isolated verification is now complete for all four production
patterns (A/B/C/D) for the first time in this research line.** No production pattern remains
unmeasured in isolation. This closes a gap that had persisted since sub-project 2 first ran the
pooled grid search: sub-projects 7a, 7b, and 7c covered A눌림목, C촉매, and D박스 respectively, each
one incorrectly stating that B지지선 was out of scope "by design" because it had been superseded by
E반등 (§1's correction) — this sub-project shows that premise was false, and B지지선's own isolated
profile is now on record alongside the other three.

This still does **not** constitute a decomposition of the pooled system's result. Per the
slot-competition caveat in §5, isolated-pattern runs and the pooled run select materially different
trade sets — each pattern's own isolated profile is now known, but not its *share* of the pooled
A+B+C+D result. Knowing that all four patterns are individually unprofitable in isolation does not
tell us how much each one drags down (or props up) the pooled average, because none of these four
sub-projects' candidates competed against each other for `apply_daily_selection`'s daily/weekly
slots the way they do in the real pooled system. Any future work claiming to explain the pooled
system's weakness on a per-pattern basis — i.e., true attribution of the pooled result to its
constituent patterns — would need a dedicated new sub-project this research line has not yet
scoped, let alone run.

## 7. Limitations

- **Single train/test split**, same acknowledged limitation as every prior sub-project in this
  line — neither the grid search nor the cross-pattern comparison has been validated across
  multiple splits or a walk-forward scheme.
- **Discrete 216-cell grid** — the true optimum may sit between grid points, but the
  monotonic-degradation pattern seen across every prior grid in this line (including this one, see
  §2) makes a hidden profitable pocket between points unlikely to reverse a clearly negative
  finding here.
- **Slot-competition confound** (§5) — any comparison against A눌림목's, C촉매's, or D박스's
  isolated results, or against the pooled A+B+C+D result, is directional, not a decomposition.
  `run_one_config` calls `apply_daily_selection`, which caps trades at `max_per_day=3` /
  `max_per_week=15` and selects by `(grade, rank_score)` descending, so B지지선-alone and
  B지지선-within-the-pool select substantially different, not directly decomposed, trade sets.
- **Smallest-candidate-pool-of-the-four caveat**: B지지선's 1,996-candidate pool is roughly a
  fifth the size of A눌림목's (9,808) and well under half of C촉매's (5,226) or D박스's (4,557).
  This manifests concretely in §2 as only 29/216 grid cells clearing the `trades_per_week >= 5`
  floor, versus 216/216 for every other pattern — a materially different frequency profile that
  should be kept in mind when reading §5's cross-pattern comparison. It did not, however, translate
  into an unreliable selected-config result: both train (727) and test (489) clear `n_trades >= 50`
  comfortably (§4), so the smaller pool is a frequency-profile difference, not a reliability
  failure.
- This sub-project inherits sub-project 1's simulation-machinery limitations: orderbook ask/bid
  ratio blocks are not modeled in the backtest simulation, since `run_one_config` and its
  dependencies are reused unmodified. Like D박스 (7c) and unlike C촉매 (7b), **B지지선 has no
  analogous real-time execution-ratio gate** — `TOSS_WEAK_BUY_RATIO_C` in
  `src/swing-scanner.src.js` only branches on `patternType === 'C촉매'` — so this particular
  simulation-vs-production gap does not apply to B지지선's results specifically.
- **Flat round-trip fee assumption** — same inherited simulation-machinery limitation noted in
  7a's, 7b's, and 7c's Limitations sections: the backtest simulation assumes a flat round-trip fee,
  not a size/liquidity-sensitive one.
- **Unmeasured-patterns caveat**: with this sub-project, A눌림목's, C촉매's, D박스's, and B지지선's
  own isolated profiles are all now on record (7a, 7b, 7c, this document). None of the four
  patterns' own *pooled contribution* has been measured (isolated ≠ pooled share, per the
  slot-competition caveat) — this sub-project, combined with 7a/7b/7c, completes individual
  isolated verification for all four patterns but does not constitute a decomposition of the
  pooled system, per §6.

## 8. Final Recommendation

**No change to B지지선's current production deployment status is recommended.** No production code
(`src/swing-scanner.src.js`) was touched by this sub-project — it is a pure verification exercise
against already-committed backtest infrastructure and cached data. B지지선 continues running in
production exactly as it does today, per `isPatternB`'s unchanged definition at lines 1325-1332
(confirmed still live, §1).

This finding does not surface a new lever worth pursuing: the 216-cell grid is exhaustive over the
same axes used everywhere else in this research line, and while it produces a shallower loss than
any other pattern examined so far (0/216 cells reach `hit_rate >= 90%`, 0/216 cells are even
profitable on train, best-available configuration is a reliable-but-losing -10.28%/-13.62%
(train/test) `cagr_15slot`), it is still comprehensively unprofitable. There is nothing here that
argues for retuning B지지선's target/stop/min_score/regime-gate parameters in production.

What this sub-project *does* establish: B지지선 in isolation has the mildest loss profile of the
four patterns examined in this research line on every train-side metric compared in §5 — grid-best
cagr, grid-worst cagr, selected-config hit_rate, and selected-config cagr all favor B지지선 over
A눌림목, C촉매, and D박스. This is a directional read, not a precise ranking, given the
slot-competition caveat that makes any cross-run comparison an imperfect one, and it is
additionally complicated by B지지선's much smaller candidate pool and correspondingly narrower
frequency-passing subset (29/216 vs. 216/216 for the others). **This sub-project does not
establish that B지지선 specifically is a stronger pattern than A눌림목, C촉매, or D박스 within the
pooled system** — the slot-competition caveat means none of 7a, 7b, 7c, or this sub-project can
cleanly attribute a share of the pooled result to any one pattern.

Separately, and more importantly for how this document should be read: **the "B지지선 superseded by
E반등" framing that appeared in 7a, 7b, and 7c was a mischaracterization, now corrected (§1).**
E반등/oversold-bounce (sub-projects 4/5/5b/6) never shipped to production — confirmed directly
against `swing-algo-oversold-bounce-hitrate.analysis.md`'s explicit "no production code changed"
closing statement — and B지지선 (`isPatternB`) has remained live in `src/swing-scanner.src.js` the
entire time. This sub-project was not optional cleanup; it verified a currently-live production
pattern that three prior sub-projects incorrectly treated as already retired.

**With this sub-project, individual isolated verification is now complete for all four production
patterns (A/B/C/D)** — all four come back target_not_met, all four are comprehensively unprofitable
across an exhaustive 216-cell grid, and none surfaces a retuning lever worth pursuing. **This
changes nothing about any of A눌림목's, C촉매's, D박스's, or B지지선's current production deployment
status**: each continues running in production exactly as it does today, this research line having
found no isolated-pattern-level basis to alter any of them. Any future decomposition of the
*pooled* system's result (as opposed to the isolated per-pattern profiles now on record for all
four) would require a dedicated new sub-project this plan does not attempt — 7a, 7b, 7c, and this
document should not be read as having decomposed the pooled A+B+C+D result, only as having each
individually verified one pattern's own isolated profile.

---

No production code (`src/swing-scanner.src.js`) has been changed by this sub-project. With 7a
(A눌림목), 7b (C촉매), 7c (D박스), and this document (B지지선) complete, the per-pattern
isolated-verification arc of this research line is closed for all four production patterns for the
first time. No true decomposition of the pooled A+B+C+D result has been attempted by any sub-project
in this line — no conclusion should be drawn about the full four-pattern production system beyond
what each pattern's own isolated profile shows.

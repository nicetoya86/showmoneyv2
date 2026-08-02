# swing-algo-pattern-d-verification Design

> **Project**: showmoneyv2
> **Feature**: Swing Algo Enhancement Sub-project 7c — per-pattern hit_rate/cagr verification
> for production pattern **D박스 (박스권돌파)**
> **Prior work**: [swing-algo-pattern-a-verification.analysis.md](../../03-analysis/swing-algo-pattern-a-verification.analysis.md)
> (7a — A눌림목, target_not_met, no change recommended) and
> [swing-algo-pattern-c-verification.analysis.md](../../03-analysis/swing-algo-pattern-c-verification.analysis.md)
> (7b — C촉매, target_not_met, no change recommended; both flagged the slot-competition and
> unmeasured-patterns caveats this sub-project inherits — see Section 3 below)
> **Date**: 2026-08-02

---

## 1. Context and Goal

This is the third and last of three sibling sub-projects (7a=A눌림목 complete, 7b=C촉매 complete,
7c=D박스 this one) verifying whether each of `src/swing-scanner.src.js`'s four production patterns
reaches the 90%-hit-rate decision gate **in isolation** — a gap identified because sub-project 2
only ever grid-searched the pooled A+B+C+D candidate set (finding it uniformly unprofitable) and
never broke the result out per pattern.

**D박스 is a technical breakout trigger**, distinct from both prior patterns examined. Per
`src/swing-scanner.src.js` lines 1339-1343, `isPatternD` requires `currentPrice > box25High`
(price breaks above the 25-day box high), `rvolVal >= PD_VOL_MULT` (volume multiple), `dailyChange
>= PD_BREAK_MIN`, and `sma20 > sma60` (uptrend filter) — a classic box-breakout setup, unlike
A눌림목's pullback-and-bounce or C촉매's disclosure/supply-event trigger. There is no D-specific
real-time execution-ratio gate analogous to C촉매's `TOSS_WEAK_BUY_RATIO_C` (verified: that
constant and its use at line 1691 only branch on `patternType === 'C촉매'`), so this sub-project
does not inherit that particular simulation-vs-production gap.

**Goal**: determine D박스's own `hit_rate`/`trades_per_week`/`cagr_15slot` profile in isolation,
against the same decision gate used everywhere else in this research line, completing individual
verification for 3 of the 4 production patterns (B지지선 was superseded by a purpose-built
replacement, E반등, in sub-project 4, and is not separately scheduled).

## 2. Data Source (no regeneration)

`backtest_candidates_with_paths.json` (sub-project 2's committed artifact, unmodified) already
contains everything needed. Filtering `pattern_type == "D박스"` yields **4,557 candidates**
(verified directly against the file this session), split `hold_days=5` (3,710) vs `hold_days=4`
(847) — both already baked into the cached `hold_days` field. Date range spans
`2022-01-04`..`2025-12-30`, matching every prior sub-project's universe/range convention.

**No new candidate generation.** `generate_signal_candidates.py`'s `evaluate_candidate()` is not
touched — this sub-project only filters the existing cache and re-runs the existing grid search.

## 3. Grid, Method, and a Carried-Forward Methodological Caveat

Identical to sub-projects 7a/7b: reuse `target_stop_grid_search.run_one_config`/`select_best_config`
unmodified, 216-cell custom grid (`target_pct` × `stop_pct` × `min_score` × `regime_gate`,
`exclude_d_box` fixed `False`), train `2022-01-01`..`2024-06-30` / test `2024-07-01`..`2026-01-01`,
decision gate `hit_rate >= 0.90` AND `trades_per_week >= 5.0` AND `cagr_15slot > 0` on both splits
with `n_trades >= 50` as a reliability floor (three-way outcome framework).

**Why `exclude_d_box` must still be forced `False` here, and why that's a no-op for a different
reason than in 7b**: `target_stop_grid_search.py`'s `build_grid()` has an `exclude_d_box` axis
whose entire purpose is excluding D박스 candidates from a *pooled* A+B+C+D grid search. In 7b's
C촉매-only pool, `exclude_d_box=True` was a no-op because no D박스 candidates existed in that pool
to exclude. Here, the pool is *entirely* D박스 candidates, so `exclude_d_box=True` would trivially
zero out every result (excluding the only pattern present) rather than doing nothing — an even more
important reason to build the grid directly (216 cells over the other four axes) rather than call
`build_grid()`, which would otherwise silently duplicate or corrupt half the grid.

**Carried-forward caveat** (same as 7a/7b): `run_one_config` calls `apply_daily_selection`, which
caps trades at `max_per_day=3`/`max_per_week=15`, ranked by `(grade, rank_score)` descending. This
means that whenever the analysis document compares D박스-in-isolation against the pooled A+B+C+D
result (or against 7a's A눌림목 / 7b's C촉매 isolated results), the runs are **not decomposing a
shared trade set** — each run's candidates compete only against themselves for daily slots. Any
cross-run comparison in this sub-project's analysis document must state this explicitly.

**Reminder for the implementer**: `run_one_config`'s `start`/`end` params only affect the
`trades_per_week` denominator — they do **not** filter candidates by date. Pre-filter before
calling:
```python
train_candidates = [c for c in d_candidates if train_start_ts <= pd.Timestamp(c.date) <= train_end_ts]
test_candidates  = [c for c in d_candidates if test_start_ts  <= pd.Timestamp(c.date) <= test_end_ts]
```

## 4. Data Flow

```
backtest_candidates_with_paths.json (sub-project 2, unchanged)
  -> filter pattern_type == "D박스"
  -> backtest_pattern_d_candidates.json (new committed artifact, 4,557 candidates)

backtest_pattern_d_candidates.json
  -> target_stop_grid_search.run_one_config() [unmodified], 216-cell custom grid,
     once per cell x {train, test}
  -> backtest_pattern_d_grid_results.json (new committed artifact)

-> docs/03-analysis/swing-algo-pattern-d-verification.analysis.md (new)
```

## 5. Error Handling

Identical to every prior sub-project: no new failure modes, since no new computation logic is
introduced.

## 6. Testing

No new source code, so no new unit tests. Sanity check to run and report during execution: confirm
the filtered pool is exactly 4,557 candidates with the expected `hold_days` split (3,710 at 5 days
/ 847 at 4 days, per this session's direct inspection) before running the grid — if the count
doesn't match, investigate before proceeding.

## 7. Limitations

- **Single train/test split**, same acknowledged limitation as every prior sub-project.
- **Discrete 216-cell grid** — same caveat as 7a/7b: the true optimum may sit between grid points,
  but the monotonic-degradation pattern seen across every prior grid in this line makes a hidden
  profitable pocket unlikely to reverse a clearly negative or clearly positive finding here.
- **Slot-competition confound** (Section 3) — any comparison against pooled or cross-pattern
  results is directional, not a decomposition.
- Inherits sub-project 1's simulation-machinery limitations (orderbook ask/bid ratio block not
  modeled in the backtest simulation) — same as 7a/7b, this is a general limitation, not a
  D박스-specific one (D박스 has no analogous real-time execution-ratio gate the way C촉매 does).
- **Flat round-trip fee assumption** — same inherited simulation-machinery limitation as 7a/7b.
- **Unmeasured-patterns caveat**: A눌림목's and C촉매's own pooled contributions remain separately
  unmeasured (isolated ≠ pooled share, per the slot-competition caveat) — this sub-project adds
  only D박스's isolated profile to the record. B지지선 was superseded by a purpose-built
  replacement pattern (E반등, sub-project 4) and its own pooled contribution is not currently
  scheduled to be measured by any planned sub-project. With this sub-project, 3 of 4 production
  patterns (A/C/D) will have individual isolated-verification data on record; B지지선 remains the
  sole exception, by design (superseded, not overlooked).

No production code (`src/swing-scanner.src.js`) is changed by this sub-project — deployment of any
finding here is a separate, later decision.

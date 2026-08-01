# swing-algo-pattern-c-verification Design

> **Project**: showmoneyv2
> **Feature**: Swing Algo Enhancement Sub-project 7b — per-pattern hit_rate/cagr verification
> for production pattern **C촉매 (촉매이벤트)**
> **Prior work**: [swing-algo-pattern-a-verification.analysis.md](../../03-analysis/swing-algo-pattern-a-verification.analysis.md)
> (sub-project 7a — same method applied to A눌림목; found target_not_met, no change to
> production status recommended, and flagged an important methodological caveat this
> sub-project inherits — see Section 3 below)
> **Date**: 2026-08-02

---

## 1. Context and Goal

This is the second of three sibling sub-projects (7a=A눌림목 complete, 7b=C촉매 this one,
7c=D박스 next) verifying whether each of `src/swing-scanner.src.js`'s four production patterns
reaches the 90%-hit-rate decision gate **in isolation** — a gap identified because sub-project 2
only ever grid-searched the pooled A+B+C+D candidate set (finding it uniformly unprofitable) and
never broke the result out per pattern.

**C촉매 is qualitatively different from A눌림목.** Per `src/swing-scanner.src.js`'s scoring logic,
C촉매 ("촉매이벤트") is triggered by disclosure/supply events (DART filings, 외국인/기관 순매수
— see the `'긍정공시'`/`'당일공시'`/`'외국인+기관동반'` signal tags around line 1387-1394) rather
than A눌림목's pullback-and-bounce technical setup. An event-driven trigger could plausibly behave
very differently from a technical pattern — either cleaner (a real catalyst moves price with less
noise) or noisier (news-driven pops that fade fast) — so this sub-project's result is not assumed
to resemble 7a's; it's a genuinely open question.

**Goal**: determine C촉매's own `hit_rate`/`trades_per_week`/`cagr_15slot` profile in isolation,
against the same decision gate used everywhere else in this research line.

## 2. Data Source (no regeneration)

`backtest_candidates_with_paths.json` (sub-project 2's committed artifact, unmodified) already
contains everything needed. Filtering `pattern_type == "C촉매"` yields **5,226 candidates**
(verified directly against the file this session), split `hold_days=2` (5,030, the pattern's
production default) vs `hold_days=5` (196, grade `강매` override via production's `getHoldDays()`
logic — both already baked into the cached `hold_days` field). Date range spans
`2022-01-04`..`2025-12-30`, matching every prior sub-project's universe/range convention.

**No new candidate generation.** `generate_signal_candidates.py`'s `evaluate_candidate()` is not
touched — this sub-project only filters the existing cache and re-runs the existing grid search.

## 3. Grid, Method, and a Carried-Forward Methodological Caveat

Identical to sub-project 7a: reuse `target_stop_grid_search.run_one_config`/`select_best_config`
unmodified, 216-cell custom grid (`target_pct` × `stop_pct` × `min_score` × `regime_gate`,
`exclude_d_box` fixed `False` — a no-op on a single non-D pattern pool), train `2022-01-01`..
`2024-06-30` / test `2024-07-01`..`2026-01-01`, decision gate `hit_rate >= 0.90` AND
`trades_per_week >= 5.0` AND `cagr_15slot > 0` on both splits with `n_trades >= 50` as a
reliability floor (three-way outcome framework).

**Carried-forward caveat, stated up front this time rather than discovered during final review**
(as it was for 7a): `run_one_config` calls `apply_daily_selection`, which caps trades at
`max_per_day=3`/`max_per_week=15`, ranked by `(grade, rank_score)` descending. This means that
whenever the analysis document compares C촉매-in-isolation against the pooled A+B+C+D result (or
against 7a's A눌림목 result), the two runs are **not decomposing a shared trade set** — each run's
candidates compete only against themselves for daily slots, so a candidate that would be crowded
out by higher-ranked A/B/D candidates in the pooled system can appear in the isolated run instead.
Any cross-run comparison in this sub-project's analysis document must state this explicitly, not
imply a like-for-like decomposition. Same reminder as every prior sub-project regarding
`run_one_config`'s `start`/`end` params: they only affect the `trades_per_week` denominator, not
candidate filtering — callers must pre-filter the candidate list by date themselves.

**Reminder for the implementer**: `run_one_config`'s `start`/`end` params only affect the
`trades_per_week` denominator — they do **not** filter candidates by date. Pre-filter before
calling:
```python
train_candidates = [c for c in c_candidates if train_start_ts <= pd.Timestamp(c.date) <= train_end_ts]
test_candidates  = [c for c in c_candidates if test_start_ts  <= pd.Timestamp(c.date) <= test_end_ts]
```

## 4. Data Flow

```
backtest_candidates_with_paths.json (sub-project 2, unchanged)
  -> filter pattern_type == "C촉매"
  -> backtest_pattern_c_candidates.json (new committed artifact, 5,226 candidates)

backtest_pattern_c_candidates.json
  -> target_stop_grid_search.run_one_config() [unmodified], 216-cell custom grid,
     once per cell x {train, test}
  -> backtest_pattern_c_grid_results.json (new committed artifact)

-> docs/03-analysis/swing-algo-pattern-c-verification.analysis.md (new)
```

## 5. Error Handling

Identical to every prior sub-project: no new failure modes, since no new computation logic is
introduced.

## 6. Testing

No new source code, so no new unit tests. Sanity check to run and report during execution: confirm
the filtered pool is exactly 5,226 candidates with the expected `hold_days` split (5,030 at 2 days
/ 196 at 5 days, per this session's direct inspection) before running the grid — if the count
doesn't match, investigate before proceeding.

## 7. Limitations

- **Single train/test split**, same acknowledged limitation as every prior sub-project.
- **Discrete 216-cell grid** — same caveat as 7a/sub-project 2: the true optimum may sit between
  grid points, but the monotonic-degradation pattern seen across every prior grid in this line
  makes a hidden profitable pocket unlikely to reverse a clearly negative or clearly positive
  finding here.
- **Slot-competition confound** (Section 3) — any comparison against pooled or cross-pattern
  results is directional, not a decomposition.
- Inherits sub-project 1's simulation-machinery limitations (orderbook ask/bid and pattern-C
  itself's own noted "blocks not modeled" caveat from sub-project 1 — worth re-checking against
  the actual simulation code during Task 3's write-up rather than assuming it still applies
  verbatim, since it was written about a different context originally).
- **A눌림목's own pooled contribution remains unmeasured** (per 7a's corrected analysis) and
  **B지지선's pooled contribution remains unmeasured** (per the same correction) — this
  sub-project adds C촉매's isolated profile to the record but does not, by itself, complete a
  four-pattern decomposition. That requires 7c (D박스) plus a dedicated pooled-decomposition
  effort this plan does not attempt.

No production code (`src/swing-scanner.src.js`) is changed by this sub-project — deployment of any
finding here is a separate, later decision.

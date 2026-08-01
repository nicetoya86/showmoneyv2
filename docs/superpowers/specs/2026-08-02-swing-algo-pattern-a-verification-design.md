# swing-algo-pattern-a-verification Design

> **Project**: showmoneyv2
> **Feature**: Swing Algo Enhancement Sub-project 7a — per-pattern hit_rate/cagr verification
> for production pattern **A눌림목 (급등후눌림목)**
> **Prior work**: [swing-algo-target-stop-retuning.analysis.md](../../03-analysis/swing-algo-target-stop-retuning.analysis.md)
> (sub-project 2 — grid-searched the POOLED A+B+C+D candidate set, found it uniformly
> unprofitable; never broke the result out per individual pattern)
> **Date**: 2026-08-02

---

## 1. Context and Goal

`src/swing-scanner.src.js` currently generates 4 production pattern types: A눌림목(급등후눌림목),
B지지선(지지선반등), C촉매(촉매이벤트), D박스(박스권돌파). Of these:

- **B지지선** was superseded in this research line by a purpose-built "E반등"
  (oversold-bounce) candidate generator and put through 5 trader-diagnosed hit-rate levers
  (sub-project 4) — all failed the decision gate, but at least the pattern got dedicated scrutiny.
- **A momentum-continuation pattern (F모멘텀)**, not one of the original 4, was designed and
  verified from scratch (sub-project 5-6) and is the one config in this research line's history
  with a genuinely positive, reliable `cagr_15slot` (Config A: +27.93%/+29.80% train/test).
- **A눌림목, C촉매, D박스 have never individually been through this process.** Sub-project 2 ran
  a single grid search over all four patterns pooled together (`generate_signal_candidates.py`'s
  `evaluate_candidate()`, 21,587 candidates) and found the pooled result uniformly unprofitable
  (0/432 cells hit `hit_rate >= 90%`; best `cagr_15slot` across the whole grid was -9.62%/yr). That
  pooled number could be hiding a decent individual pattern averaged down by bad ones, or every
  pattern could be equally bad — nobody has checked. All three are still live in production,
  sending real recommendations, on that unverified basis.

**Goal of this sub-project**: determine A눌림목's own `hit_rate`/`trades_per_week`/`cagr_15slot`
profile in isolation, against the same 90%-hit-rate decision gate used everywhere else in this
research line. This is the first of three sibling sub-projects (7a/7b/7c for A/C/D respectively,
per user decision) — C촉매 and D박스 are explicitly out of scope here and will each get their own
brainstorm → design → plan → SDD cycle afterward.

## 2. Data Source (no regeneration)

`backtest_candidates_with_paths.json` (sub-project 2's committed artifact, unmodified) already
contains all the data needed: 21,587 cached candidates over the standard 959-ticker universe,
`2022-01-01`..`2026-01-01`, each tagged with a `pattern_type` field. Filtering
`pattern_type == "A눌림목"` yields **9,808 candidates** (verified directly against the file this
session) — by far the largest of the four patterns (45% of the pooled set), split `hold_days=3`
(grade `매수`, the pattern default) vs `hold_days=5` (grade `강매`, production's
`getHoldDays()` override), both already baked into the cached `hold_days` field exactly as
production computes them. Date range spans the full `2022-01-04`..`2025-12-30` window, consistent
with every prior sub-project's universe/range convention.

**No new candidate generation.** `generate_signal_candidates.py` and its `evaluate_candidate()`
scoring/pattern logic are not touched — this sub-project only filters the existing cache and
re-runs the existing grid search on the filtered subset.

## 3. Grid and Method

Reuse `target_stop_grid_search.run_one_config` completely unmodified. Per the user's explicit
choice, the grid axes match sub-project 2's exactly, minus `exclude_d_box` (meaningless once the
pool is pre-filtered to a single non-D pattern — fixed to `False`, confirmed as a no-op by reading
`run_one_config`'s filter logic: it only ever excludes `pattern_type == "D박스"` rows, which don't
exist in this filtered pool):

- `target_pct` ∈ {3%, 4%, 5%, 6%, 8%, 10%} (6)
- `stop_pct` ∈ {1%, 1.5%, 2%, 2.5%, 3%, 4%} (6)
- `min_score` ∈ {60, 90, 110} (3)
- `regime_gate` ∈ {off, on} (2)
- `exclude_d_box` fixed `False`

**216 cells** (not `build_grid()`'s 432 — that function's own `exclude_d_box` axis would just
duplicate every cell twice for no reason on this pool, so the 216-cell list is constructed
directly rather than calling `build_grid()`).

**Train/test split** (same convention as every prior sub-project): train `2022-01-01`..`2024-06-30`,
selection runs only on train; test `2024-07-01`..`2026-01-01` evaluated exactly once, no
re-selection. **Reminder baked in for the implementer** (this exact bug has recurred before in
this research line): `run_one_config`'s `start`/`end` params only affect the `trades_per_week`
denominator — they do **not** filter candidates by date. The caller must pre-filter the candidate
list itself before each call:
```python
train_candidates = [c for c in a_candidates if train_start_ts <= pd.Timestamp(c.date) <= train_end_ts]
test_candidates  = [c for c in a_candidates if test_start_ts  <= pd.Timestamp(c.date) <= test_end_ts]
```

**Decision gate** (identical across this whole research line): a configuration passes only if,
on **both** train and test, `hit_rate >= 0.90` AND `trades_per_week >= 5.0` AND `cagr_15slot > 0`,
with `n_trades >= 50` as a prerequisite reliability floor before drawing any pass/fail conclusion
(three-way outcome: target-met / target-not-met-but-reliable / underpowered). Selection among
train cells: reuse `select_best_config` unmodified (qualifying-cells-by-CAGR, falling back to
top-hit-rate-among-frequency-qualifying if none qualify — same fallback sub-project 2 hit).

## 4. Data Flow

```
backtest_candidates_with_paths.json (sub-project 2, unchanged)
  -> filter pattern_type == "A눌림목"
  -> backtest_pattern_a_candidates.json (new committed artifact, 9,808 candidates)

backtest_pattern_a_candidates.json
  -> target_stop_grid_search.run_one_config() [unmodified], 216-cell custom grid,
     once per cell x {train, test}
  -> backtest_pattern_a_grid_results.json (new committed artifact)

-> docs/03-analysis/swing-algo-pattern-a-verification.analysis.md (new)
```

## 5. Error Handling

Identical to every prior sub-project: no new failure modes, since no new computation logic is
introduced. `run_one_config` already handles zero-trade cells (`n_trades=0` → `cagr_15slot=nan`)
and empty-window candidates.

## 6. Testing

No new source code, so no new unit tests. Sanity check to run and report during execution (not a
formal test): confirm the filtered pool is exactly 9,808 candidates with the expected
`hold_days` split (4,995 at 3 days / 4,813 at 5 days, per this session's direct inspection) before
running the grid — if the count doesn't match, investigate before proceeding.

## 7. Limitations

- **Single train/test split**, same acknowledged limitation as every prior sub-project in this
  line (flagged as a separate, not-yet-addressed research gap in the brainstorming that led here).
- **Discrete 216-cell grid** — same caveat as sub-project 2: the true optimum may sit between grid
  points, but sub-project 2's monotonic-degradation pattern across the pooled set makes a hidden
  profitable pocket between points unlikely to reverse a clearly negative or clearly positive
  finding here.
- This sub-project inherits sub-project 1's simulation-machinery limitations (orderbook ask/bid
  and pattern-C-specific blocks not modeled, flat round-trip fee assumption) since `run_one_config`
  and its dependencies are reused unmodified.
- **C촉매 and D박스 are explicitly out of scope** — each gets its own sub-project (7b, 7c) after
  this one, per the user's decision to split rather than combine.

No production code (`src/swing-scanner.src.js`) is changed by this sub-project — as with every
prior sub-project, deployment of any finding here is a separate, later decision.

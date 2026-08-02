# swing-algo-pattern-b-verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine whether production pattern **B지지선 (지지선반등)**, evaluated in isolation
(not pooled with A/C/D), can reach the 90%-hit_rate decision gate on its own — and commit the
honest answer, whatever it is, as reproducible data + an analysis document. This completes
individual isolated verification for **all four** production patterns (A/B/C/D) for the first
time in this research line.

**Architecture:** No new source code — this sub-project filters an existing committed cache and
re-runs an existing, unmodified grid-search function. `backtest/target_stop_grid_search.py`'s
`run_one_config` and `select_best_config` are reused exactly as sub-projects 7a/7b/7c used them,
just against a candidate list pre-filtered to `pattern_type == "B지지선"` and the same custom
216-cell grid used throughout this line.

**Tech Stack:** Python, pandas, existing `backtest/` modules. No new dependencies, no new files
under `backtest/` or `backtest/tests/`.

## Global Constraints

- **No source code is created or modified.** Every task in this plan produces only data JSON
  files and (in the final task) a markdown analysis document. If any step seems to require new
  logic beyond what's listed below, stop and flag it rather than writing new code.
- Reused, unmodified functions and their exact import paths:
  - `from backtest.generate_signal_candidates import CachedCandidate`
  - `from backtest.target_stop_grid_search import run_one_config, select_best_config, MIN_HIT_RATE, MIN_TRADES_PER_WEEK, GRID_TARGET_PCT, GRID_STOP_PCT, GRID_MIN_SCORE, GRID_REGIME_GATE`
- Reused, already-committed data files (do not re-fetch/regenerate):
  `backtest_candidates_with_paths.json` (sub-project 2, 21,587 candidates, all 4 pattern types),
  `backtest_regime_lookup.json`.
- Pattern filter: `pattern_type == "B지지선"` (exact string, verified against the actual cache
  this session — do not guess or re-derive from mangled terminal output; copy this literal
  string). Expected count: **1,996** candidates, **all at `hold_days=5`** (no grade-override
  split — verified this session that B지지선's own pattern-default `hold_days` is already 5,
  identical to the `강매` override value, so no split is observable in this pattern's data,
  unlike A/C/D) — verify this exact count and uniform `hold_days` in Task 1 before proceeding to
  Task 2.
- Grid (216 cells, built directly — do NOT call `build_grid()`, which has an `exclude_d_box` axis
  that would just duplicate every cell since no D박스 candidates exist in this filtered pool):
  ```python
  grid = [
      {"target_pct": tp, "stop_pct": sp, "min_score": ms, "regime_gate": rg, "exclude_d_box": False}
      for tp in GRID_TARGET_PCT
      for sp in GRID_STOP_PCT
      for ms in GRID_MIN_SCORE
      for rg in GRID_REGIME_GATE
  ]
  ```
- Train split: `2022-01-01`..`2024-06-30`. Test split: `2024-07-01`..`2026-01-01`.
- **`run_one_config` does not filter candidates by date itself** — its `start`/`end` parameters
  are used only to compute the `trades_per_week` denominator. Every script in this plan must
  pre-filter the candidate list by date range before calling it:
  ```python
  train_start_ts = pd.to_datetime("2022-01-01", utc=True)
  train_end_ts = pd.to_datetime("2024-06-30", utc=True)
  test_start_ts = pd.to_datetime("2024-07-01", utc=True)
  test_end_ts = pd.to_datetime("2026-01-01", utc=True)
  train_candidates = [c for c in candidates if train_start_ts <= pd.Timestamp(c.date) <= train_end_ts]
  test_candidates = [c for c in candidates if test_start_ts <= pd.Timestamp(c.date) <= test_end_ts]
  ```
  Passing the same unfiltered candidate list for both "train" and "test" calls is a real bug that
  has recurred and been caught multiple times in this research line's history — every step below
  must filter first.
- **Decision gate** (applies on both train and test): `hit_rate >= 0.90` AND
  `trades_per_week >= 5.0` AND `cagr_15slot > 0`. **Reliability floor**: `n_trades >= 50` on both
  splits is a prerequisite before drawing any pass/fail conclusion — report the three-way outcome
  (target-met / target-not-met-but-reliable / underpowered) rather than a bare pass/fail. This
  matters more here than in any prior sub-project: at 1,996 total candidates (the smallest pool
  of the four patterns examined — vs. D박스's 4,557, C촉매's 5,226, A눌림목's 9,808), the train
  split may plausibly have fewer than 50 trades in some grid cells, and the reliability floor
  check must not be skipped or softened.
- **Slot-competition caveat** (established in 7a's final review, restated up front since 7b):
  `run_one_config` calls `apply_daily_selection` (`backtest/run_swing_v2_backtest.py`), which caps
  trades at `max_per_day=3`/`max_per_week=15`, ranked by `(grade, rank_score)` descending. Any
  comparison in Task 3's analysis document between B지지선-in-isolation and a pooled result
  (sub-project 2's A+B+C+D grid, or 7a/7b/7c's isolated results) is **not a like-for-like
  decomposition** — each isolated run's candidates only ever compete against themselves for daily
  slots. Task 3 must state this explicitly wherever such a comparison appears, and must NOT
  introduce new uncommitted numbers to quantify the crowding-out effect (describe it
  qualitatively only — every number in the document must trace to a committed JSON file).
- **Unmeasured-patterns caveat, closing out with this sub-project**: with 7a (A눌림목), 7b
  (C촉매), 7c (D박스) already complete and this sub-project covering B지지선, **all four
  production patterns will have isolated-verification data on record for the first time** in this
  research line. Task 3 must state this plainly, and must also correct the prior mischaracterization
  in 7a/7b/7c's documents that B지지선 was "superseded by E반등" — verified this session that
  E반등/oversold-bounce (sub-projects 4/5/5b/6) never shipped to production (every analysis
  document in that track states "no production code changed"; see
  `docs/03-analysis/swing-algo-oversold-bounce-hitrate.analysis.md`'s closing line specifically).
  B지지선 (`isPatternB` in `src/swing-scanner.src.js`, lines 1325-1332) has been live, unchanged,
  and simply unverified in isolation — same situation A/C/D were in before 7a/7b/7c. This
  completion still does **not** constitute a decomposition of the pooled A+B+C+D result (per the
  slot-competition caveat) — it only means every pattern's own isolated profile is now known, not
  each pattern's *share* of the pooled result.
- No bracket placeholders or invented numbers in the final analysis document (Task 3) — every
  number must trace to a JSON file this plan commits, or to an already-committed prior analysis
  document cited by name.

---

### Task 1: Filter and commit the B지지선 candidate pool

**Files:** none created except the output JSON — this is an execution-only task.

- [ ] **Step 1: Filter the existing cache to B지지선 only and save**

```bash
python -c "
import json
from collections import Counter

d = json.load(open('backtest_candidates_with_paths.json', encoding='utf-8'))
b_candidates = [c for c in d['candidates'] if c['pattern_type'] == 'B지지선']

out = {'params': d['params'], 'candidates': b_candidates}
json.dump(out, open('backtest_pattern_b_candidates.json', 'w', encoding='utf-8'), ensure_ascii=False)

print('B지지선 count:', len(b_candidates))
print('hold_days distribution:', dict(Counter(c['hold_days'] for c in b_candidates)))
print('date range:', min(c['date'] for c in b_candidates), '..', max(c['date'] for c in b_candidates))
"
```

Expected: `B지지선 count: 1996`, `hold_days distribution: {5: 1996}` (all at 5, no split), date
range spanning `2022-01-04`..`2025-12-30`. **If the count doesn't match 1,996, or if any candidate
has a `hold_days` other than 5, stop and investigate before proceeding.**

- [ ] **Step 2: Commit**

```bash
git add backtest_pattern_b_candidates.json
git commit -m "data(backtest): filter B지지선 candidates for individual pattern verification (sub-project 9)"
```

---

### Task 2: Grid search B지지선 in isolation, train-select, test-confirm once

**Files:** none created except the output JSON — this is an execution-only task.

**Interfaces:**
- Consumes: `backtest_pattern_b_candidates.json` (Task 1 of this plan), `backtest_regime_lookup.json`.

- [ ] **Step 1: Run the 216-cell grid on train, select the best config, confirm once on test**

```bash
python -c "
import json
import math
import pandas as pd
from backtest.generate_signal_candidates import CachedCandidate
from backtest.target_stop_grid_search import (
    run_one_config, select_best_config, MIN_HIT_RATE, MIN_TRADES_PER_WEEK,
    GRID_TARGET_PCT, GRID_STOP_PCT, GRID_MIN_SCORE, GRID_REGIME_GATE,
)

d = json.load(open('backtest_pattern_b_candidates.json', encoding='utf-8'))
candidates = [CachedCandidate(**c) for c in d['candidates']]
regime_lookup = json.load(open('backtest_regime_lookup.json', encoding='utf-8'))

train_start_ts = pd.to_datetime('2022-01-01', utc=True)
train_end_ts = pd.to_datetime('2024-06-30', utc=True)
test_start_ts = pd.to_datetime('2024-07-01', utc=True)
test_end_ts = pd.to_datetime('2026-01-01', utc=True)
train_candidates = [c for c in candidates if train_start_ts <= pd.Timestamp(c.date) <= train_end_ts]
test_candidates = [c for c in candidates if test_start_ts <= pd.Timestamp(c.date) <= test_end_ts]
print('train candidates:', len(train_candidates), 'test candidates:', len(test_candidates))

grid = [
    {'target_pct': tp, 'stop_pct': sp, 'min_score': ms, 'regime_gate': rg, 'exclude_d_box': False}
    for tp in GRID_TARGET_PCT
    for sp in GRID_STOP_PCT
    for ms in GRID_MIN_SCORE
    for rg in GRID_REGIME_GATE
]
print('grid cells:', len(grid))

train_results = [
    run_one_config(train_candidates, regime_lookup=regime_lookup, start='2022-01-01', end='2024-06-30', **cell)
    for cell in grid
]

selection = select_best_config(train_results)
chosen = selection['config']
test_result = run_one_config(
    test_candidates, regime_lookup=regime_lookup, start='2024-07-01', end='2026-01-01',
    target_pct=chosen['target_pct'], stop_pct=chosen['stop_pct'], min_score=chosen['min_score'],
    regime_gate=chosen['regime_gate'], exclude_d_box=chosen['exclude_d_box'],
)

finite_cagrs = [r['cagr_15slot'] for r in train_results if isinstance(r['cagr_15slot'], float) and not math.isnan(r['cagr_15slot'])]
summary = {
    'grid_cells': len(grid),
    'cells_hit_rate_ge_90_train': sum(1 for r in train_results if r['hit_rate'] >= MIN_HIT_RATE),
    'cells_freq_ge_5_train': sum(1 for r in train_results if r['trades_per_week'] >= MIN_TRADES_PER_WEEK),
    'cells_cagr_positive_train': sum(1 for r in train_results if r['cagr_15slot'] > 0),
    'cells_full_gate_train': sum(1 for r in train_results if r['hit_rate'] >= MIN_HIT_RATE and r['trades_per_week'] >= MIN_TRADES_PER_WEEK and r['cagr_15slot'] > 0),
    'max_hit_rate_train': max(r['hit_rate'] for r in train_results),
    'max_cagr_train': max(finite_cagrs) if finite_cagrs else None,
    'min_cagr_train': min(finite_cagrs) if finite_cagrs else None,
}

out = {
    'train_results': train_results,
    'selection': selection,
    'test_result': test_result,
    'summary': summary,
}
json.dump(out, open('backtest_pattern_b_grid_results.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

print('selection status:', selection['status'])
print('selected config:', chosen)
print('selected train:', {k: selection['config'][k] for k in ('n_trades','hit_rate','trades_per_week','cagr_15slot')})
print('selected test  :', {k: test_result[k] for k in ('n_trades','hit_rate','trades_per_week','cagr_15slot')})
print('summary:', summary)
"
```

Expected: no exception; `train_results` has exactly 216 entries; `selection['status']` is either
`'target_met'` or `'target_not_met'` (both are valid, honest outcomes — do not treat
`'target_not_met'` as a failure of this task, only as the answer). **Pay close attention to
`n_trades` on both the selected train config and the test result** — given the smaller candidate
pool (1,996 vs. 4,557-9,808 for A/C/D), it is plausible the selected config's `n_trades` falls
below the 50-trade reliability floor on one or both splits; if so, report this honestly in Task 3
as "underpowered" rather than reading a pass/fail into it. Report the actual printed numbers
honestly in Task 3, whatever they are.

- [ ] **Step 2: Commit**

```bash
git add backtest_pattern_b_grid_results.json
git commit -m "data(backtest): 216-cell grid search for B지지선 pattern in isolation (sub-project 9)"
```

---

### Task 3: Write the final analysis document

**Files:**
- Create: `docs/03-analysis/swing-algo-pattern-b-verification.analysis.md`

- [ ] **Step 1: Assemble the honest, fully-cited summary**

Using the real numbers from `backtest_pattern_b_candidates.json` and
`backtest_pattern_b_grid_results.json` (both committed in Tasks 1-2), write
`docs/03-analysis/swing-algo-pattern-b-verification.analysis.md` with these sections (no bracket
placeholders — every number must be the actual value read from these JSON files):

- **Header** matching the convention of
  `docs/03-analysis/swing-algo-pattern-d-verification.analysis.md` (Analysis Type, Project,
  Feature, Design Doc / Implementation Plan links — Design Doc is
  `docs/superpowers/specs/2026-08-02-swing-algo-pattern-b-verification-design.md`, Implementation
  Plan is `docs/superpowers/plans/2026-08-02-swing-algo-pattern-b-verification.md` — Prior work
  citing `swing-algo-pattern-a-verification.analysis.md`, `swing-algo-pattern-c-verification.analysis.md`,
  and `swing-algo-pattern-d-verification.analysis.md`, Date `2026-08-02`).
- **Method summary**: restate that this sub-project makes no changes to `evaluate_candidate()` or
  `target_stop_grid_search.py`, only filters the existing pooled cache down to `pattern_type ==
  "B지지선"` (state the actual filtered count from `backtest_pattern_b_candidates.json`, all at
  `hold_days=5`) and re-runs the existing grid search on a 216-cell grid (state the 4 axes and
  their values). Note briefly that B지지선 is a technical support-bounce trigger (60-day pullback
  band + proximity to a past support level + turning up + volume + RSI golden zone), distinct
  from A눌림목/C촉매/D박스's own triggers. **This section must also explicitly correct the prior
  "superseded by E반등" framing** from 7a/7b/7c's documents: state plainly that E반등/oversold-bounce
  (sub-projects 4/5/5b/6) never shipped to production (cite
  `docs/03-analysis/swing-algo-oversold-bounce-hitrate.analysis.md`'s "no production code changed"
  statement by name), and that B지지선 (`isPatternB` in `src/swing-scanner.src.js`) has remained
  live and unchanged the entire time — this sub-project is not re-verifying a deprecated pattern,
  it is verifying a currently-live one that was simply skipped in the prior three sub-projects due
  to that mischaracterization.
- **Grid summary table**: from `backtest_pattern_b_grid_results.json`'s `summary` block — grid
  cell count, how many cells cleared `hit_rate>=90%` on train, how many cleared
  `trades_per_week>=5`, how many had `cagr_15slot>0`, how many cleared all three simultaneously
  (train-side full gate), and the max/min train `cagr_15slot` across the grid.
- **Selected configuration: train vs. test**: from `selection` and `test_result` — the exact
  chosen `target_pct`/`stop_pct`/`min_score`/`regime_gate`, and for both train and test:
  `n_trades`, `hit_rate`, `trades_per_week`, `avg_pnl`, `cagr_15slot`, `mdd_15slot`.
- **Decision-gate verdict**: state plainly whether B지지선 in isolation reaches
  `hit_rate >= 90%` AND `trades_per_week >= 5` AND `cagr_15slot > 0` on **both** splits, using the
  three-way framework (target-met / target-not-met-but-reliable / underpowered) — explicitly
  confirm whether `n_trades >= 50` holds on both splits before asserting reliability. Given the
  smaller candidate pool, do not skip or soften this check even if it shows the result is
  underpowered on one or both splits.
- **Comparison to sub-projects 7a (A눌림목), 7b (C촉매), 7c (D박스), and to the pooled sub-project
  2 result**: state whether B지지선 in isolation looks meaningfully different from the other three
  isolated results and from the pooled A+B+C+D result — better, worse, indistinguishable, or (if
  underpowered) not meaningfully comparable at all. **This section must open with the
  slot-competition caveat verbatim** (from this plan's Global Constraints): any such comparison is
  not a like-for-like decomposition. Do not introduce new uncommitted numbers to quantify the
  effect — describe it qualitatively. Give an honest trader-perspective read on what the
  comparison (properly caveated) suggests, without overclaiming precision it doesn't have.
- **What remains open**: state plainly that **with this sub-project, individual isolated
  verification is now complete for all four production patterns (A/B/C/D) for the first time** in
  this research line — no pattern remains unmeasured in isolation. State clearly that this still
  does not constitute a decomposition of the pooled system's result (per the slot-competition
  caveat) — each pattern's own isolated profile is now known, but not its *share* of the pooled
  result. Any future work claiming to explain the pooled system's weakness per-pattern would need
  a dedicated new sub-project.
- **Limitations**: restate the design doc's Section 7 limitations (single train/test split,
  discrete grid, slot-competition confound, smallest-candidate-pool-of-the-four caveat, inherited
  simulation-machinery limitations).
- **Final recommendation**: state plainly whether this finding changes anything about B지지선's
  current production deployment status — base this on the actual numbers found, do not assume the
  answer before reading them. If the result is target_not_met (matching every other pattern in
  this line so far), state that no change to B지지선's deployment is recommended. If underpowered,
  state that plainly too and note what would be needed to get a reliable read (e.g. a larger
  candidate pool, which isn't something this sub-project can produce without regenerating the base
  cache).

State explicitly that no production code (`src/swing-scanner.src.js`) was changed by this
sub-project.

- [ ] **Step 2: Commit the analysis document**

```bash
git add docs/03-analysis/swing-algo-pattern-b-verification.analysis.md
git commit -m "docs: final analysis for swing algo sub-project 9 (B지지선 pattern individual verification)"
```

---

## Self-Review Notes

- **Spec coverage**: Task 1 covers the design doc's Section 2 (filter, no regeneration, sanity
  check on count and uniform hold_days). Task 2 covers Section 3 (216-cell grid,
  train-select/test-confirm-once, decision gate, slot-competition caveat, extra attention to the
  reliability floor given the smaller pool). Task 3 covers the analysis document requirement
  implied throughout the design doc (Section 1's goal statement and E반등 correction, Section 3's
  caveat, Section 7's limitations), and explicitly carries forward the E반등-superseded correction
  and the "all four patterns now verified" milestone rather than leaving either to be
  rediscovered.
- **Placeholder scan**: no TBD/TODO. Every script is complete, runnable code with exact import
  paths and exact filter strings verified against the actual committed cache this session.
- **Type consistency**: `CachedCandidate` field names and `run_one_config`/`select_best_config`'s
  parameter and return-value names (`target_pct`, `stop_pct`, `min_score`, `regime_gate`,
  `exclude_d_box`, `regime_lookup`, `n_trades`, `hit_rate`, `trades_per_week`, `cagr_15slot`,
  `mdd_15slot`, `avg_pnl`) match their actual definitions in `backtest/target_stop_grid_search.py`
  throughout every task — identical to sub-projects 7a/7b/7c's plans, no invented names.

# swing-algo-pattern-a-verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine whether production pattern **A눌림목 (급등후눌림목)**, evaluated in isolation
(not pooled with B/C/D as sub-project 2 did), can reach the 90%-hit_rate decision gate on its own
— and commit the honest answer, whatever it is, as reproducible data + an analysis document.

**Architecture:** No new source code — this sub-project filters an existing committed cache and
re-runs an existing, unmodified grid-search function. `backtest/target_stop_grid_search.py`'s
`run_one_config` and `select_best_config` are reused exactly as sub-project 2 used them, just
against a candidate list pre-filtered to a single pattern and a custom 216-cell grid (the same 4
axes sub-project 2 used, minus the meaningless-on-a-single-pattern `exclude_d_box` axis).

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
- Pattern filter: `pattern_type == "A눌림목"` (exact string, verified against the actual cache
  this session — do not guess or re-derive from mangled terminal output; copy this literal
  string). Expected count: **9,808** candidates, split `hold_days=3` (4,995) / `hold_days=5`
  (4,813) — verify this exact count in Task 1 before proceeding to Task 2.
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
  (target-met / target-not-met-but-reliable / underpowered) rather than a bare pass/fail.
- No bracket placeholders or invented numbers in the final analysis document (Task 3) — every
  number must trace to a JSON file this plan commits.

---

### Task 1: Filter and commit the A눌림목 candidate pool

**Files:** none created except the output JSON — this is an execution-only task.

- [ ] **Step 1: Filter the existing cache to A눌림목 only and save**

```bash
python -c "
import json
from collections import Counter

d = json.load(open('backtest_candidates_with_paths.json', encoding='utf-8'))
a_candidates = [c for c in d['candidates'] if c['pattern_type'] == 'A눌림목']

out = {'params': d['params'], 'candidates': a_candidates}
json.dump(out, open('backtest_pattern_a_candidates.json', 'w', encoding='utf-8'), ensure_ascii=False)

print('A눌림목 count:', len(a_candidates))
print('hold_days distribution:', dict(Counter(c['hold_days'] for c in a_candidates)))
print('date range:', min(c['date'] for c in a_candidates), '..', max(c['date'] for c in a_candidates))
"
```

Expected: `A눌림목 count: 9808`, `hold_days distribution: {3: 4995, 5: 4813}` (order may vary),
date range spanning `2022-01-04`..`2025-12-30`. **If the count doesn't match 9,808, stop and
investigate before proceeding** — this is the reliability check called for in the design doc's
Section 6.

- [ ] **Step 2: Commit**

```bash
git add backtest_pattern_a_candidates.json
git commit -m "data(backtest): filter A눌림목 candidates for individual pattern verification (sub-project 7a)"
```

---

### Task 2: Grid search A눌림목 in isolation, train-select, test-confirm once

**Files:** none created except the output JSON — this is an execution-only task.

**Interfaces:**
- Consumes: `backtest_pattern_a_candidates.json` (Task 1 of this plan), `backtest_regime_lookup.json`.

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

d = json.load(open('backtest_pattern_a_candidates.json', encoding='utf-8'))
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
json.dump(out, open('backtest_pattern_a_grid_results.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

print('selection status:', selection['status'])
print('selected config:', chosen)
print('selected train:', {k: selection['config'][k] for k in ('n_trades','hit_rate','trades_per_week','cagr_15slot')})
print('selected test  :', {k: test_result[k] for k in ('n_trades','hit_rate','trades_per_week','cagr_15slot')})
print('summary:', summary)
"
```

Expected: no exception; `train_results` has exactly 216 entries; `selection['status']` is either
`'target_met'` or `'target_not_met'` (both are valid, honest outcomes — do not treat
`'target_not_met'` as a failure of this task, only as the answer). Report the actual printed
numbers honestly in Task 3, whatever they are.

- [ ] **Step 2: Commit**

```bash
git add backtest_pattern_a_grid_results.json
git commit -m "data(backtest): 216-cell grid search for A눌림목 pattern in isolation (sub-project 7a)"
```

---

### Task 3: Write the final analysis document

**Files:**
- Create: `docs/03-analysis/swing-algo-pattern-a-verification.analysis.md`

- [ ] **Step 1: Assemble the honest, fully-cited summary**

Using the real numbers from `backtest_pattern_a_candidates.json` and
`backtest_pattern_a_grid_results.json` (both committed in Tasks 1-2), write
`docs/03-analysis/swing-algo-pattern-a-verification.analysis.md` with these sections (no bracket
placeholders — every number must be the actual value read from these JSON files):

- **Header** matching the convention of `docs/03-analysis/swing-algo-momentum-sector-filter.analysis.md`
  (Analysis Type, Project, Feature, Design Doc / Implementation Plan links, Prior work, Date).
- **Method summary**: restate that this sub-project makes no changes to `evaluate_candidate()` or
  `target_stop_grid_search.py`, only filters the existing pooled cache down to `pattern_type ==
  "A눌림목"` (state the actual filtered count from `backtest_pattern_a_candidates.json`) and
  re-runs the existing grid search on a 216-cell grid (state the 4 axes and their values), linking
  to the design doc rather than re-deriving the reasoning.
- **Grid summary table**: from `backtest_pattern_a_grid_results.json`'s `summary` block — grid
  cell count, how many cells cleared `hit_rate>=90%` on train, how many cleared
  `trades_per_week>=5`, how many had `cagr_15slot>0`, how many cleared all three simultaneously
  (train-side full gate), and the max/min train `cagr_15slot` across the grid.
- **Selected configuration: train vs. test**: from `selection` and `test_result` — the exact
  chosen `target_pct`/`stop_pct`/`min_score`/`regime_gate`, and for both train and test:
  `n_trades`, `hit_rate`, `trades_per_week`, `avg_pnl`, `cagr_15slot`, `mdd_15slot`.
- **Decision-gate verdict**: state plainly whether A눌림목 in isolation reaches
  `hit_rate >= 90%` AND `trades_per_week >= 5` AND `cagr_15slot > 0` on **both** splits, using the
  three-way framework (target-met / target-not-met-but-reliable / underpowered) consistent with
  every prior sub-project — explicitly confirm whether `n_trades >= 50` holds on both splits before
  asserting reliability.
- **Comparison to the pooled sub-project 2 result**: state whether A눌림목 in isolation looks
  meaningfully different from sub-project 2's pooled A+B+C+D result (best `cagr_15slot` -9.62%/yr,
  0/432 cells passing `hit_rate>=90%`) — better, worse, or indistinguishable — and give an honest
  trader-perspective read on what that implies about whether A눌림목 specifically is dragging the
  pool down, holding it up, or riding in line with the average.
- **Limitations**: single train/test split, discrete 216-cell grid (same caveats as every prior
  sub-project — copy language from the design doc's Section 7 rather than re-deriving).
- **Final recommendation**: state plainly whether this finding changes anything about A눌림목's
  current production deployment status (no production code has been touched, so the honest answer
  may simply be "no change recommended, pattern continues running as-is pending C촉매/D박스 results
  in sub-projects 7b/7c") — do not overstate a modest finding into a call to action it doesn't
  support.

State explicitly that no production code (`src/swing-scanner.src.js`) was changed by this
sub-project, and that C촉매 (sub-project 7b) and D박스 (sub-project 7c) remain to be verified
separately.

- [ ] **Step 2: Commit the analysis document**

```bash
git add docs/03-analysis/swing-algo-pattern-a-verification.analysis.md
git commit -m "docs: final analysis for swing algo sub-project 7a (A눌림목 pattern individual verification)"
```

---

## Self-Review Notes

- **Spec coverage**: Task 1 covers the design doc's Section 2 (filter, no regeneration, sanity
  check on count). Task 2 covers Section 3 (216-cell grid, train-select/test-confirm-once,
  decision gate). Task 3 covers the analysis document requirement implied throughout the design
  doc (Section 1's goal statement, Section 7's limitations).
- **Placeholder scan**: no TBD/TODO. Every script is complete, runnable code with exact import
  paths and exact filter strings verified against the actual committed cache this session (not
  guessed from mangled terminal output).
- **Type consistency**: `CachedCandidate` field names and `run_one_config`/`select_best_config`'s
  parameter and return-value names (`target_pct`, `stop_pct`, `min_score`, `regime_gate`,
  `exclude_d_box`, `regime_lookup`, `n_trades`, `hit_rate`, `trades_per_week`, `cagr_15slot`,
  `mdd_15slot`, `avg_pnl`) match their actual definitions in `backtest/target_stop_grid_search.py`
  throughout every task — no invented parameter or field names.

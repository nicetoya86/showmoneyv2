# swing-algo-pattern-b-verification Design

> **Project**: showmoneyv2
> **Feature**: Swing Algo Enhancement Sub-project 9 — per-pattern hit_rate/cagr verification
> for production pattern **B지지선 (지지선반등)**
> **Prior work**: [swing-algo-pattern-a-verification.analysis.md](../../03-analysis/swing-algo-pattern-a-verification.analysis.md)
> (7a — A눌림목), [swing-algo-pattern-c-verification.analysis.md](../../03-analysis/swing-algo-pattern-c-verification.analysis.md)
> (7b — C촉매), [swing-algo-pattern-d-verification.analysis.md](../../03-analysis/swing-algo-pattern-d-verification.analysis.md)
> (7c — D박스) — all three target_not_met, no change recommended, all flagged the
> slot-competition and unmeasured-patterns caveats this sub-project inherits (see Section 3 below)
> **Date**: 2026-08-02

---

## 1. Context and Goal, Including a Correction to Prior Sub-Projects' Framing

This is the fourth and final sub-project verifying whether each of `src/swing-scanner.src.js`'s
four production patterns reaches the 90%-hit-rate decision gate **in isolation**.

**Correction to 7a/7b/7c's stated framing**: those three design/analysis documents describe
B지지선 as "superseded by a purpose-built replacement pattern (E반등/oversold-bounce, sub-project
4)" and treat its isolated verification as intentionally out of scope for that reason. This session
verified directly against the current production file that this framing is **incorrect**:
`isPatternB` (lines 1325-1332 of `src/swing-scanner.src.js`) is present, unchanged, and live in
production today. E반등/oversold-bounce was a parallel **backtest-only research track**
(sub-projects 4, 5, 5b, 6) that never reached the profitability bar and was never deployed — every
analysis document in that track states explicitly that no production code was changed (see, e.g.,
`docs/03-analysis/swing-algo-oversold-bounce-hitrate.analysis.md`'s closing line: "No production
code (`src/swing-scanner.src.js`) has been changed by this sub-project"). B지지선 was never
replaced; it was simply the one pattern this research line hadn't gotten to yet, same as A/C/D
were before 7a/7b/7c. This document corrects the record rather than repeating the error.

**B지지선 is a technical support-bounce trigger** (`src/swing-scanner.src.js` lines 1325-1332):
`corrPct60` (60-day pullback) within a band, `proxToPast` (price near a past support/resistance
level), `dailyChange >= 0` (turning up today), `rvol >= 1.5`, RSI in a golden-zone band — distinct
from A눌림목's event-triggered pullback, C촉매's disclosure/supply-event trigger, and D박스's
box-breakout trigger.

**Goal**: determine B지지선's own `hit_rate`/`trades_per_week`/`cagr_15slot` profile in isolation,
completing individual isolated verification for **all four** production patterns (A/B/C/D) for the
first time in this research line.

## 2. Data Source (no regeneration)

`backtest_candidates_with_paths.json` (sub-project 2's committed artifact, unmodified) already
contains everything needed. Filtering `pattern_type == "B지지선"` yields **1,996 candidates**
(verified directly against the file this session), **all at `hold_days=5`** — unlike A/C/D, there
is no visible grade-override split in this pattern's data, and this is not an oversight: verified
against both `src/swing-scanner.src.js`'s `getHoldDays()` (line ~1721) and its Python port
`backtest/swing_signal_engine.py::_hold_days()` (line 61) that B지지선's own pattern-default
hold_days **is already 5**, identical to the `강매` (strong-buy) override value — so whether or
not a given B지지선 candidate independently qualifies as `강매`, `hold_days` comes out to 5 either
way, and no split is observable in the cached data. Date range spans `2022-01-04`..`2025-12-30`,
matching every prior sub-project's universe/range convention.

**No new candidate generation.** `generate_signal_candidates.py`'s `evaluate_candidate()` is not
touched — this sub-project only filters the existing cache and re-runs the existing grid search.

## 3. Grid, Method, and Carried-Forward Methodological Caveats

Identical to sub-projects 7a/7b/7c: reuse `target_stop_grid_search.run_one_config`/`select_best_config`
unmodified, 216-cell custom grid (`target_pct` × `stop_pct` × `min_score` × `regime_gate`,
`exclude_d_box` fixed `False` — a no-op on a single non-D pattern pool, same reasoning as 7a/7b),
train `2022-01-01`..`2024-06-30` / test `2024-07-01`..`2026-01-01`, decision gate `hit_rate >=
0.90` AND `trades_per_week >= 5.0` AND `cagr_15slot > 0` on both splits with `n_trades >= 50` as a
reliability floor (three-way outcome framework). Note: at 1,996 total candidates (smaller than
A눌림목's 9,808 or C촉매's 5,226, though larger than D박스's 4,557), the train split will have
noticeably fewer candidates than any prior sub-project in this line — the reliability floor check
matters more here than it has before; if `n_trades < 50` on either split, the outcome must be
reported as underpowered, not silently treated as a pass or fail.

**Carried-forward slot-competition caveat** (stated up front, as in 7b/7c): `run_one_config` calls
`apply_daily_selection`, which caps trades at `max_per_day=3`/`max_per_week=15`, ranked by
`(grade, rank_score)` descending. Any comparison in this sub-project's analysis document between
B지지선-in-isolation and the pooled A+B+C+D result (or 7a/7b/7c's isolated results) is **not a
like-for-like decomposition** — describe such comparisons qualitatively only, never introduce new
uncommitted numbers to quantify the crowding-out effect.

**Reminder for the implementer**: `run_one_config`'s `start`/`end` params only affect the
`trades_per_week` denominator — they do **not** filter candidates by date. Pre-filter before
calling:
```python
train_candidates = [c for c in b_candidates if train_start_ts <= pd.Timestamp(c.date) <= train_end_ts]
test_candidates  = [c for c in b_candidates if test_start_ts  <= pd.Timestamp(c.date) <= test_end_ts]
```

## 4. Data Flow

```
backtest_candidates_with_paths.json (sub-project 2, unchanged)
  -> filter pattern_type == "B지지선"
  -> backtest_pattern_b_candidates.json (new committed artifact, 1,996 candidates)

backtest_pattern_b_candidates.json
  -> target_stop_grid_search.run_one_config() [unmodified], 216-cell custom grid,
     once per cell x {train, test}
  -> backtest_pattern_b_grid_results.json (new committed artifact)

-> docs/03-analysis/swing-algo-pattern-b-verification.analysis.md (new)
```

## 5. Error Handling

Identical to every prior sub-project: no new failure modes, since no new computation logic is
introduced.

## 6. Testing

No new source code, so no new unit tests. Sanity check to run and report during execution: confirm
the filtered pool is exactly 1,996 candidates, all at `hold_days=5`, before running the grid — if
either doesn't match, investigate before proceeding.

## 7. Limitations

- **Single train/test split**, same as every prior sub-project.
- **Discrete 216-cell grid**, same caveat as 7a/7b/7c.
- **Slot-competition confound** (Section 3) — any comparison against pooled or cross-pattern
  results is directional, not a decomposition.
- **Smallest candidate pool of the four patterns examined in isolation** (1,996, vs. D박스's
  4,557, C촉매's 5,226, A눌림목's 9,808) — the reliability floor (`n_trades >= 50` on both splits)
  is more likely to bind here than in any prior sub-project; if it doesn't clear, the honest
  three-way outcome framework reports underpowered rather than forcing a pass/fail read.
- Inherits sub-project 1's simulation-machinery limitations (orderbook ask/bid ratio not modeled).
- **Flat round-trip fee assumption**, same as every prior sub-project.
- **Unmeasured-patterns caveat, now closed out**: with this sub-project, all four production
  patterns (A/B/C/D) will have isolated-verification data on record for the first time. This still
  does **not** constitute a decomposition of the pooled A+B+C+D result (per the slot-competition
  caveat) — it only means every pattern's own isolated profile is now known, not each pattern's
  *share* of the pooled result.

No production code (`src/swing-scanner.src.js`) is changed by this sub-project.

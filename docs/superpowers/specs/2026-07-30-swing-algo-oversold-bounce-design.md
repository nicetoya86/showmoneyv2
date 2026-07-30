# Swing Algorithm Enhancement — Sub-project 3 Phase B: Oversold-Bounce Candidate Engine

## Context and Goal

**Where Phase A left off:** sub-project 3 Phase A (`docs/superpowers/specs/2026-07-28-swing-algo-new-signal-filters-design.md`) tested three additive filters (trend alignment, volatility contraction, sector strength) layered on top of the *existing* 21,587-candidate pool produced by `evaluate_candidate()`. All 8 filter-subset combinations missed the 90%-hit-rate / ≥5-per-week / positive-return joint target on both train and test (`docs/03-analysis/swing-algo-new-signal-filters.analysis.md`); the best (triple-tag combo) was still -7.79%/yr on test. Per that design doc's own roadmap, this uniform negative result is the defined trigger condition for **Phase B**.

**Why Phase A could never succeed at this:** `evaluate_candidate()` (`backtest/swing_signal_engine.py`) applies two hard filters *before* any of its four patterns (A눌림목/B지지선/C촉매/D박스) are even checked — `rvol < 1.0 → return None` (line 115) and `rsi14 < 40 → return None` (line 117). Any stock that is currently oversold never enters the candidate pool at all. Phase A could only ever narrow that pool; it could never add to it.

**This phase's goal:** build a genuinely new candidate-generation path — a fifth pattern, parallel to A/B/C/D, that specifically admits oversold-recovery setups the current engine structurally excludes — and backtest it with the same rigor (same universe, same train/test split, same decision-gate bar) as every prior sub-project in this line.

**Hypothesis chosen (of three considered — momentum/52-week-high continuation, low-volatility quiet accumulation, oversold bounce):** oversold bounce, because its excluding hard filter (`rsi14 < 40`) is a single unambiguous boundary, its entry trigger (RSI recovery) is a single well-defined event day (easier to specify without stacking free parameters the way Phase A's 3-tag/8-subset sweep did), and genuine oversold dips inside an uptrend are common enough to plausibly clear the `n_trades >= 50` reliability bar. The low-volatility hypothesis was set aside because "quiet" has no natural entry-day trigger and risks either parameter proliferation or sparse/degenerate sampling; the momentum-continuation hypothesis was set aside as a possible future candidate if this phase also fails.

## Roadmap Context

1. ~~Realistic backtest foundation~~ (sub-project 1, done)
2. ~~Target/stop/threshold retuning~~ (sub-project 2, done — target not met, existing pool uniformly unprofitable)
3. ~~New signal filters, Phase A~~ (done — target not met, no additive filter subset on the existing pool clears the bar)
   **[This document] Phase B — oversold-bounce candidate-generation engine** — a new, independent
   pattern admitting candidates A/B/C/D structurally cannot flag.
4. Statistical/ML model (separate future spec, unchanged from sub-project 1's roadmap; distinct
   from this phase — this phase is a single hand-specified rule, not a trained classifier).

## Scope of This Phase

**In scope:**
- A new candidate-generation script, `backtest/generate_oversold_candidates.py`, scanning the same
  959-ticker operating universe (`backtest/tickers_operating.txt`) over the same date range as
  prior sub-projects, using only already-cached data (Yahoo OHLCV, DART disclosures, KRX supply —
  all previously fetched and disk-cached by sub-projects 1-3; no new network fetch expected).
- A single, fully-specified entry rule (five conditions, all fixed thresholds — see "Entry Rule"
  below), producing `CachedCandidate`-compatible records reusable by the existing
  `backtest/target_stop_grid_search.py` pipeline **completely unmodified**.
- Running the existing `run_grid_search` (target_pct × stop_pct × regime_gate grid; `min_score` and
  `exclude_d_box` axes present but made no-ops by construction — see "Grid Reuse" below) against
  the new candidate pool, same train (`2022-01-01`..`2024-06-30`) / test (`2024-07-01`..`2026-01-01`)
  split as every prior sub-project.
- A decision-gate analysis document, same honesty standard as sub-projects 2 and 3 Phase A: state
  plainly whether the selected train config clears 90% hit-rate / ≥5-per-week / positive return on
  **both** train and test, with the `n_trades >= 50` reliability rule applied.

**Explicitly out of scope:**
- Any change to `evaluate_candidate()`, `src/swing-scanner.src.js`, or any of sub-project 1/2/3's
  already-reviewed modules (`target_stop_grid_search.py`, `simulate_exit`, `apply_toss_liveprice`,
  `apply_round_trip_cost`, `analyze_portfolio_return`) — all consumed as-is.
- A trained/statistical model (roadmap item 4) — this phase is one hand-specified rule.
- The momentum-continuation or low-volatility-accumulation hypotheses (deferred; only pursued if
  this phase also fails, per the same conditional-next-step pattern Phase A used for this phase).
- Deployment of any resulting configuration — a separate, later decision per this project's
  established pattern (no prior sub-project has touched production code either).

## Design Revisions from Initial Draft (trader review)

Three corrections made before finalizing, per a pullback ("눌림목") trading-perspective review of
the first draft (which had only: RSI crosses up through 40, price above SMA60, close ≥ open):

1. **RSI-40-crossup alone is not "oversold."** 40 is simply `evaluate_candidate()`'s existing hard
   filter boundary inverted — trading practice treats RSI readings under ~30-35 as a genuine
   oversold condition, not 40. A bare cross of the 40 line is noise-prone (e.g. RSI oscillating
   39.8 → 40.2 across two days would qualify despite representing no real oversold dip). **Fixed:**
   added a depth requirement — RSI14 must have printed ≤ 35 at some point in the 5 bars immediately
   before the trigger day (`idx-5..idx`), so the day-of cross through 40 is confirmed to follow a
   real oversold excursion, not line noise.
2. **No pullback-depth condition, despite the pattern being named for one.** The original draft
   only checked *momentum* (RSI) and long-term *trend context* (SMA60), never *how far the stock
   had actually pulled back* — so a stock trading sideways with mild RSI wobble could qualify just
   as easily as a real double-digit retracement. **Fixed:** added `high20 = max(high[idx-20..idx])`
   and require `current_price / high20 - 1 <= -0.08` — at least an 8% retracement from the trailing
   20-day high, the same scale of pullback depth `is_a`'s `pullback_from_event` already uses
   elsewhere in this codebase (`PA_PULLBACK_MIN=0.03`..`PA_PULLBACK_MAX=0.15`).
3. **Bounce confirmation too weak.** `close >= open` (any green candle, even by one tick) is a weak
   reversal signal on its own. **Fixed:** strengthened to `close[idx] > high[idx-1]` — the trigger
   day must close above the *prior day's high*, a materially stronger confirmation that the
   reversal is actually underway, not just a marginally green day inside a continuing decline.

All three fixes are additional **fixed thresholds** inside one coherent rule, not new free
parameters to grid-search or additional tag combinations to sweep — they do not reintroduce the
combinatorial-subset pattern that Phase A used (8 subsets × 432 cells). This phase still runs a
single candidate pool through target/stop/regime_gate variation only.

## Entry Rule (all conditions AND'd, evaluated at trigger day `idx`)

Reused unmodified from `evaluate_candidate()`'s existing base filters (liquidity/quality gates, not
directionally specific — kept so the new pattern isn't tested on illiquid or fundamentally-flagged
junk):
- `current_price >= 1000` (`MIN_PRICE`)
- `current_price * vol[idx] >= 5,000,000,000` (`MIN_TURNOVER_ALGO`)
- No DART disclosure matching `NEGATIVE_DART_RE` on `idx`'s date
- Not (`supply.frgn < -1,000,000,000` or `supply.org < -1,000,000,000`) on `idx`'s date
- `rvol >= 1.0` (kept deliberately — a bounce should have at least average volume behind it; this
  is the *other* of the two original hard filters, left untouched so this phase tests the RSI
  hypothesis in isolation rather than conflating it with the separate low-volume hypothesis)

New, specific to this pattern:
- `rsi14[idx] >= 40 and rsi14[idx-1] < 40` (cross-up day)
- `min(rsi14[idx-5 .. idx-1]) <= 35` (confirms a real oversold excursion preceded the cross)
- `current_price / max(high[idx-20 .. idx]) - 1 <= -0.08` (≥8% pullback from the trailing 20-day high)
- `close[idx] > sma60[idx]` (broader uptrend context — not a falling knife)
- `close[idx] > high[idx-1]` (bounce confirmed by a close above the prior day's high)

If all hold, emit one `CachedCandidate` (from `backtest/generate_signal_candidates.py`, imported
unmodified):
- `entry = close[idx]`
- `hold_days = 5` (same horizon as `B지지선`, the closest existing conceptual analog — a
  support-bounce trade)
- `pattern_type = "E반등"` (new letter; guarantees `exclude_d_box`'s `pattern_type == "D박스"` check
  is always a no-op for this pool)
- `score = 110` (constant, equal to the top of `GRID_MIN_SCORE = [60, 90, 110]` — guarantees
  `c.score < min_score` never trips for any grid cell, making the `min_score` axis a no-op; this
  phase deliberately does not test a score/strength dimension, per the "single coherent hypothesis,
  no extra free parameters" principle above)
- `rank_score = score` (constant; same-day multi-candidate ties broken by Python's stable sort over
  insertion order — no bounce-strength ranking metric is introduced, again to avoid adding an
  untested free parameter)
- `grade = "매수"` (anything other than `"강매"`, so `regime_gate`'s existing `grade != "강매"` check
  behaves exactly as it does for A/B/D-pattern candidates today)
- `window_open/high/low/close` = forward `hold_days`-bar OHLC window, same slicing convention as
  `generate_signal_candidates.py`

## Grid Reuse

`backtest/target_stop_grid_search.py`'s `run_grid_search`/`run_one_config`/`build_grid` are called
**with zero code changes**. Its 432-cell grid (`GRID_TARGET_PCT` × `GRID_STOP_PCT` ×
`GRID_MIN_SCORE` × `GRID_REGIME_GATE` × `GRID_EXCLUDE_D_BOX`) still executes in full, but by
construction (constant `score=110`, `pattern_type="E반등"` above) only `target_pct` (6) ×
`stop_pct` (6) × `regime_gate` (2) = 72 cells produce distinct results; the remaining 6× redundancy
from `min_score`/`exclude_d_box` is wasted compute, not a correctness issue, and is accepted rather
than modifying already-reviewed code for a minor efficiency gain.

## Architecture

```
[existing, unmodified] per-ticker Yahoo OHLCV (cache/yahoo/*.json, already on disk)
[existing, unmodified] backtest/cache/dart, backtest/cache/krx_supply (already on disk)
[existing, unmodified] backtest_regime_lookup.json (already on disk)
                ↓
[NEW] backtest/generate_oversold_candidates.py
      → scan_oversold_candidates(tickers, start, end) -> Tuple[List[CachedCandidate], List[skip]]
        (mirrors generate_signal_candidates.py's per-ticker/per-day loop structure and its
        dart/supply lookups; swaps evaluate_candidate() for the Entry Rule above)
      → written to backtest_oversold_candidates.json
                ↓
[existing, unmodified] backtest/target_stop_grid_search.run_grid_search
                ↓
[NEW, orchestration only] backtest_oversold_grid_search_results.json
      → {train_results, selection, test_result}
                ↓
[NEW] docs/03-analysis/swing-algo-oversold-bounce.analysis.md
      → decision-gate verdict, same bar as sub-projects 2 and 3 Phase A
```

## Components

### `backtest/generate_oversold_candidates.py` (new)

**Produces:** `scan_oversold_candidates(tickers: List[str], *, start: str, end: str, dart_api_key: str = DART_API_KEY) -> Tuple[List[CachedCandidate], List[Dict[str,str]]]` — same signature shape as `generate_signal_candidates.generate_candidates`, returning `(candidates, skipped_tickers)`.

**Consumes:** `backtest.yahoo_cache.fetch_yahoo_chart` (disk-cache hit for all previously-fetched tickers), `backtest.dart_history.fetch_disclosures_for_date`, `backtest.krx_supply_history.fetch_supply_for_date` (all unmodified, all already populated), `backtest.indicators.rsi14`/`sma` (unmodified), `backtest.generate_signal_candidates.CachedCandidate` (unmodified dataclass, imported not redefined).

### Orchestration (execution-only, no new reusable module)

Load `backtest_oversold_candidates.json`, call `run_grid_search` with the same train/test split
string constants used by sub-project 3 Phase A's Task 8, write
`backtest_oversold_grid_search_results.json`.

## Error Handling

- Ticker fetch failure: same as `generate_signal_candidates.py` — caught, ticker skipped, recorded
  in `skipped_tickers`, scan continues. Not a new failure mode.
- No new failure modes beyond what `generate_signal_candidates.py` already has, since this script
  mirrors its structure exactly and only swaps the per-day predicate.

## Testing

Value-pinning tests, no "runs without error" tests:

- Entry-rule predicate (extracted as its own testable function, e.g. `_is_oversold_bounce(df, idx)
  -> bool`): synthetic series engineered to (a) satisfy all five conditions → `True`; (b) satisfy
  everything except the RSI depth condition (RSI touches 38, never ≤35) → `False`; (c) satisfy
  everything except the 8% pullback depth (only 3% off the 20-day high) → `False`; (d) satisfy
  everything except the prior-day-high breakout (close between open and prior close, not above
  prior high) → `False`; (e) satisfy everything except the SMA60 uptrend context (price below
  SMA60) → `False`.
- `scan_oversold_candidates`: integration-style test with a small synthetic multi-ticker dataset
  confirming `CachedCandidate` fields are populated as specified (`hold_days=5`, `score=110`,
  `pattern_type="E반등"`, `grade="매수"`, `rank_score=score`, correct forward-window slicing).
- **No regression risk to existing tests**: `target_stop_grid_search.py`,
  `generate_signal_candidates.py`, and `swing_signal_engine.py` are not modified by this phase, so
  their existing test suites need no re-verification beyond a full-suite run to confirm nothing
  else broke.

## Limitations

- **Single hand-specified rule, not a swept/tuned parameter set** — the five thresholds (35, 8%,
  60-bar SMA, prior-day-high, hold_days=5) are fixed by trader-review judgment, not derived from
  the data, and are not grid-searched. This avoids Phase A's data-snooping-via-many-configurations
  risk, but also means this phase cannot rule out that a nearby threshold choice would perform
  differently — a negative result here rules out *this specific rule*, not the oversold-bounce
  concept in general.
- **Single train/test split**, inherited from sub-projects 1-3 — same acknowledged limitation as
  every prior sub-project in this line.
- Inherits all of sub-project 1/2's stated limitations (flat-percentage target/stop, orderbook
  ask/bid and pattern-C blocks not modeled, flat-fee assumption) since this phase reuses that
  simulation machinery unmodified.
- **Sample-size risk called out explicitly, not just theoretically**: the five-condition rule (deep
  oversold + meaningful pullback + uptrend context + strong bounce confirmation, all at once) is
  more restrictive than any single A/B/C/D pattern condition. If the resulting candidate count is
  too small to clear `n_trades >= 50` on both train and test, the analysis document must report
  this plainly as an inconclusive/underpowered result, not a negative one — these are different
  conclusions and must not be conflated.

## Next Step Recommendation (to be filled in by the analysis document, not here)

No production code (`src/swing-scanner.src.js`) is changed by this phase. The analysis document
produced at the end of this phase must state plainly whether the selected train config reaches the
joint target with a statistically reliable trade count on test, and recommend either (a) that
configuration as a deployment candidate (a separate, later decision), (b) scoping the
momentum-continuation or low-volatility-accumulation hypotheses as a follow-up (per this phase's
own "Explicitly out of scope" note), or (c) if the result is underpowered rather than negative,
recommend loosening exactly which threshold (with rationale) before concluding either way.

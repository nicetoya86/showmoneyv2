# Swing Algorithm Enhancement — Sub-project 3 Phase A: New Signal Filters (Trend/Sector/Volatility)

## Context and Goal

**Where sub-project 2 left off:** a 432-cell grid search over target/stop/min-score/regime-gate/
D박스-inclusion, run against sub-project 1's 21,587 cached candidates, found **0/432 cells**
reach 90% hit-rate, 0/432 reach a positive expected return
(`docs/03-analysis/swing-algo-target-stop-retuning.analysis.md`). The conclusion: the constraint
is the **candidate pool itself** (what `evaluate_candidate()` flags as a signal), not the exit
parameters layered on top of it.

**This phase's goal, as agreed with the user:** before building an entirely new candidate-
generation engine (a large, expensive undertaking), first test cheaply whether the *existing*
candidate pool already contains a profitable subset that simple, additive filters can isolate —
using three signal families the user named: weekly-trend alignment, sector/theme relative
strength, and volatility-contraction patterns. This is **Phase A** of sub-project 3. **Phase B**
(an entirely new candidate-generation engine, admitting stocks the current A/B/C/D pattern engine
doesn't currently flag at all) is explicitly conditional: pursued only if Phase A's filters fail
to find a qualifying subset, per YAGNI — not built speculatively alongside Phase A.

**Explicit, agreed expectation-setting:** same honesty standard as sub-project 2 — if no filter
subset reaches the joint target (90% hit-rate, ≥5/week, positive return) on training data, that
negative result is reported plainly, not papered over, and becomes the trigger to scope Phase B
(not a directive to keep loosening Phase A's constraints after the fact).

## Roadmap Context

1. ~~Realistic backtest foundation~~ (sub-project 1, done)
2. ~~Target/stop/threshold retuning~~ (sub-project 2, done — target not met, existing pool
   uniformly unprofitable)
3. **[This document] New signal filters, Phase A** — additive filters/boosts on the existing
   candidate pool, reusing sub-project 1/2's pipeline unmodified wherever possible.
   **Phase B** (new candidate-generation engine) — conditional, only if Phase A fails; scoped in a
   separate follow-up design if triggered.
4. Statistical/ML model (separate future spec, unchanged from sub-project 1's roadmap).

## Scope of This Phase (Phase A)

**In scope:**
- Three new boolean signal "tags" computed per `(ticker, date)` from data already available as of
  the candidate's signal day (`idx`) — no lookahead into `entry_idx` or later:
  1. **Trend alignment**: last-completed-week's weekly close vs. a 10-week weekly SMA.
  2. **Volatility contraction**: ATR/price percentile-rank computed over a *pre-event* window
     (`idx-60..idx-10`), deliberately excluding the most recent 10 bars — see "Design Revisions"
     below for why.
  3. **Sector relative strength**: candidate's sector's trailing-20-day average return (equal-
     weighted across the already-cached universe) ranked against all sectors' trailing-20-day
     returns, gated by a minimum sector sample size.
- A one-time KRX sector-classification snapshot (reusing production's existing `MDCSTAT01501`
  endpoint pattern, currently dead code at `src/swing-scanner.src.js:988-1019`).
- Extending `backtest/target_stop_grid_search.py`'s `run_one_config`/`run_grid_search` with an
  optional tag-filter parameter, defaulting to "no filter" (byte-identical to sub-project 2's
  existing behavior — regression-tested).
- Running the existing 432-cell grid against each of 8 tag subsets (∅ plus all 7 non-empty
  combinations of the 3 tags), reusing sub-project 1/2's TOSS-LIVEPRICE, exit-simulation,
  transaction-cost, and portfolio-CAGR machinery completely unmodified.
- A decision-gate analysis document: if any subset's selected config meets 90% hit-rate / ≥5 per
  week / positive return **and** has a statistically meaningful trade count, recommend it and stop
  (no Phase B needed). If none do, report that honestly and recommend scoping Phase B.

**Explicitly out of scope (deferred to conditional Phase B):**
- Any new candidate source that isn't already produced by `evaluate_candidate()` — Phase A can
  only ever narrow the existing 21,587-candidate pool, never add to it.
- Point-in-time sector classification history (Phase A uses one static snapshot — see Limitations).
- Market-cap-weighted or KRX-published sector index returns (Phase A approximates with an equal-
  weighted average across the already-cached 959-ticker universe — see Limitations).
- Any change to `evaluate_candidate()`'s own scoring/pattern logic, or to
  `src/swing-scanner.src.js` — this phase stops at a backtested recommendation.

## Design Revisions from Initial Draft (trader review)

Four corrections made before finalizing, per a professional-trading-perspective review:

1. **Trend alignment metric replaced.** Originally proposed as "last completed week's close >
   the week before" — too noisy (a single up week is not a trend). Replaced with **weekly close
   vs. a 10-week (≈50-trading-day) weekly SMA**, a standard, smoother trend definition. Also
   deliberately a *weekly*-timeframe signal, distinct from the daily `sma20 > sma60` already used
   in D박스's gate and general scoring (`swing_signal_engine.py:165,224`) — so it adds genuinely
   new information rather than repainting an existing rule.
2. **Volatility-contraction window shifted to exclude the trigger event.** The existing A/C/D
   patterns all *require* a volume/price expansion to have already fired as of `idx`
   (`event_vol_mult >= 3.0..5.0`, breakout conditions) — so a naive "ATR percentile is currently
   low" check contradicts the very definition of the candidates it would be applied to, and would
   match almost nothing. Fixed: compute the ATR/price percentile-rank over `idx-60..idx-10`,
   excluding the most recent 10 bars (which contain the expansion event), to correctly capture
   "was this stock coiled *before* the move" rather than "is it still coiled *now*."
3. **Sector-strength minimum-sample guard added.** An equal-weighted "sector average return"
   computed over a sector with only 1-2 tickers in our 959-ticker universe is effectively self-
   comparison, not a real signal. Fixed: require **≥5 tickers** with cached data in a sector before
   computing its trailing return; sectors below that threshold return `False` (not "unknown
   defaults to True" — a conservative default, consistent with the codebase's other "fail closed"
   patterns like TOSS blocking).
4. **Statistical-reliability reporting rule added.** Testing 8 tag subsets × 432 grid cells
   (3,456 configurations) against the same single train/test split (sub-project 2's already-
   acknowledged limitation) meaningfully raises data-snooping risk versus sub-project 2's single
   432-cell sweep. Fixed: the analysis document must flag any subset's qualifying/selected config
   whose train `n_trades < 50` as **statistically unreliable regardless of its hit_rate**, and
   must not recommend such a config for the joint-target claim.

## Architecture

```
[NEW] backtest/krx_sector_snapshot.py
      → fetch_sector_snapshot(trd_dd) -> Dict[code, sector_code]
      → one-time call (most recent available trading day), mirrors krx_supply_history.py's
        style exactly (headers, disk cache, fail-to-empty-dict)

[existing, unmodified] per-ticker Yahoo OHLCV (already on disk via yahoo_cache's local cache
from sub-project 1/2's runs -- re-reading is a cache hit, no network cost)
[existing, unmodified] backtest/generate_signal_candidates.py's cached candidates
(backtest_candidates_with_paths.json, 21,587 candidates)
                ↓
[NEW] backtest/candidate_signals.py
      → compute_trend_alignment(df, idx) -> bool
      → compute_vol_contraction(df, idx) -> bool
      → compute_sector_strength(sector_map, per_ticker_closes, code, date) -> bool
      → tag_candidates(candidates, per_ticker_ohlcv, sector_map) -> Dict[(ticker,date), Dict[str,bool]]
      → written to backtest_candidate_tags.json
                ↓
[MODIFIED, additive-only] backtest/target_stop_grid_search.py
      → run_one_config(..., required_tags: FrozenSet[str] = frozenset(),
                        tags_lookup: Dict = {}) -- default reproduces sub-project 2 exactly
      → run_grid_search(...) same extension, passed through
                ↓
[NEW, orchestration only] loop over 8 tag subsets x existing 432-cell grid
      → backtest_signal_filter_results.json: {tag_subset: {train_results, selection, test_result}}
                ↓
[NEW] docs/03-analysis/swing-algo-new-signal-filters.analysis.md
      → per-subset train/test comparison, statistical-reliability flags, decision-gate verdict
```

No changes to `evaluate_candidate()`, `apply_toss_liveprice`, `simulate_exit`,
`apply_round_trip_cost`, `analyze_portfolio_return`, or any of sub-project 1/2's already-reviewed
modules — all consumed as-is.

## Components

### `backtest/krx_sector_snapshot.py` (new)

**Produces:** `fetch_sector_snapshot(trd_dd: str) -> Dict[str, str]` mapping stock code → 6-char
sector code, parsed from `IDX_IND_NM`/`SECT_TP_NM` fields — same fields, same parsing rule
(`.strip().slice(0,6)`) as the currently-dead `src/swing-scanner.src.js:1018` logic.

**Consumes:** `MDCSTAT01501` via `data.krx.co.kr` (same endpoint, headers, and disk-cache pattern
as `backtest/krx_supply_history.py`'s `fetch_supply_for_date`). Called once, for the latest date
present in `backtest_candidates_with_paths.json` (i.e. the most recent day sub-project 2's
candidate cache actually covers), to build a static snapshot.

### `backtest/candidate_signals.py` (new)

**Produces:**
- `compute_trend_alignment(df: pd.DataFrame, idx: int) -> bool` — resamples `df.iloc[:idx+1]` to
  weekly closes (ISO week, keeping only fully-completed weeks strictly before the week containing
  `idx`), returns `True` if the last completed week's close > the 10-week SMA of weekly closes.
  Returns `False` if fewer than 10 completed weeks of history exist.
- `compute_vol_contraction(df: pd.DataFrame, idx: int, *, lookback=60, exclude_recent=10,
  percentile=0.2) -> bool` — computes `atr(high,low,close,14) / close` for each bar in
  `idx-lookback..idx-exclude_recent`, returns `True` if that ratio *at* `idx-exclude_recent` (the
  most recent point in the pre-event window) is at or below the `percentile`-th percentile of the
  window. Returns `False` if the window has fewer than 20 bars.
- `compute_sector_strength(sector_map: Dict[str,str], per_ticker_closes: Dict[str, pd.Series],
  code: str, date: pd.Timestamp, *, lookback=20, top_frac=0.3, min_sector_size=5) -> bool` — for
  every sector with ≥`min_sector_size` cached tickers, computes the equal-weighted trailing-
  `lookback`-day return as of `date`; returns `True` if `code`'s sector's return ranks in the top
  `top_frac` of all qualifying sectors that day. Returns `False` if `code`'s sector has
  `< min_sector_size` tickers or is unmapped (fail-closed, consistent with TOSS blocking's
  fail-closed default elsewhere in this codebase).
- `tag_candidates(candidates: List[CachedCandidate], per_ticker_ohlcv: Dict[str, pd.DataFrame],
  sector_map: Dict[str,str]) -> Dict[Tuple[str,str], Dict[str,bool]]` — orchestrates all three
  per candidate, keyed by `(ticker, date)` to allow lookup from the grid-search side without
  re-threading through `CachedCandidate` itself.

**Consumes:** `backtest/indicators.py`'s existing `atr()` (unmodified); per-ticker OHLCV re-read
from `yahoo_cache`'s disk cache (already populated by sub-project 1/2's runs — no new network
fetch expected for any of the 955 already-fetched tickers).

### `backtest/target_stop_grid_search.py` (modified, additive-only)

`run_one_config` gains two keyword-only parameters: `required_tags: FrozenSet[str] = frozenset()`
and `tags_lookup: Dict[Tuple[str,str], Dict[str,bool]] = {}`. In the per-day candidate filter loop
(alongside the existing `min_score`/`exclude_d_box`/`regime_gate` checks), a candidate is dropped
if `required_tags` is non-empty and any tag in it is not `True` in
`tags_lookup.get((c.ticker, c.date), {})`. With the defaults, behavior is **byte-identical** to
sub-project 2 — verified by re-running sub-project 2's existing 10 tests unchanged.
`run_grid_search` passes both parameters through unchanged.

### Orchestration (execution-only, no new reusable module)

For each of the 8 tag subsets (`∅` reuses sub-project 2's already-committed
`backtest_grid_search_results.json` train_results directly rather than re-running; the other 7 run
the existing 432-cell grid with `required_tags` set), run `run_grid_search` and collect
`{tag_subset, train_results, selection, test_result}` into
`backtest_signal_filter_results.json`.

## Error Handling

- Sector-snapshot fetch failure: returns `{}` (matches `fetch_supply_for_date`'s existing
  fail-to-empty pattern). Downstream effect: every candidate's `sector_strong` tag becomes `False`
  (fail-closed) rather than raising — the analysis document must state plainly if this happened,
  since it would make the sector-strength subset's results meaningless (all-False is not "no
  candidates have strong sectors," it's "we couldn't check").
- No other new failure modes: `candidate_signals.py` operates on already-validated, already-cached
  numeric data (no I/O beyond the one sector snapshot and re-reading already-cached OHLCV files).

## Testing

Value-pinning tests per function, no "runs without error" tests:

- `compute_trend_alignment`: synthetic weekly-uptrend series (close rises steadily) → `True`;
  synthetic weekly-downtrend series → `False`; fewer than 10 weeks of history → `False`.
- `compute_vol_contraction`: synthetic series with a tight pre-event range then a sharp breakout
  in the excluded last-10-bar window → `True`; synthetic series with a consistently wide range
  throughout → `False`.
- `compute_sector_strength`: synthetic 2-sector universe (sector A's tickers all up 10%, sector
  B's all down 10%, both with ≥5 tickers) → sector-A candidate `True`, sector-B candidate `False`;
  a sector with only 2 tickers → `False` regardless of its return.
- `tag_candidates`: integration-style test with a handful of synthetic candidates confirming the
  `(ticker,date)` keying is correct and all three tags are present per entry.
- **Regression test**: `run_one_config` and `run_grid_search` called with default
  `required_tags=frozenset()` reproduce sub-project 2's existing 10 tests' exact expected values
  unchanged (guards the "no filter = sub-project 2 behavior" invariant).
- `krx_sector_snapshot.fetch_sector_snapshot`: mocked-response test confirming correct
  `code -> sector_code` parsing and the empty-dict fallback on request failure.

## Limitations

- **Static sector classification** applied across the whole 2022-2026 backtest window (one
  snapshot, not point-in-time history) — a documented simplification; sector reclassification is
  rare enough that this is reasonable, but it means a ticker that changed sectors mid-window is
  misclassified for part of it.
- **Equal-weighted, universe-limited sector returns**, not KRX's published sector indices or a
  market-cap-weighted average — an approximation using only the 955 already-cached tickers, not
  the true full-market sector composition.
- **Single train/test split**, now stress-tested across 8x more configurations than sub-project 2
  — see "Design Revisions" #4 for the mitigation (n_trades reliability flag); this does not
  eliminate the added data-snooping risk, only surfaces it honestly.
- Inherits all of sub-project 1/2's stated limitations (flat-percentage target/stop, orderbook
  checks not modeled, discrete grid) since this phase reuses that machinery unmodified.

## Next Step Recommendation (to be filled in by the analysis document, not here)

No production code (`src/swing-scanner.src.js`) is changed by this phase. The analysis document
produced at the end of Phase A must state plainly whether any tag subset reaches the joint target
with a statistically reliable trade count, and recommend either (a) that configuration, ending
sub-project 3 here, or (b) scoping Phase B (new candidate-generation engine) as a follow-up
sub-project, per the roadmap above.

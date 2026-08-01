# swing-algo-momentum-continuation Design

> **Project**: showmoneyv2
> **Feature**: Swing Algo Enhancement Sub-project 5 — "F모멘텀" (momentum-continuation) candidate
> engine, a new pattern parallel to A/B/C/D and E반등
> **Prior work**: [swing-algo-oversold-bounce-hitrate.analysis.md](../../03-analysis/swing-algo-oversold-bounce-hitrate.analysis.md)
> (sub-project 4 — E반등 with all 5 trader-diagnosed hit-rate levers still failed the joint
> decision gate; recommendation was to pivot to a different candidate-generation hypothesis)
> **Date**: 2026-08-01

---

## 1. Context and Goal

Sub-projects 3 and 4 (oversold-bounce, "E반등") are closed: even after five trader-diagnosed
hit-rate levers, no configuration cleared the joint decision gate, and the `trades_per_week >= 5`
frequency floor was never remotely approached (max observed 0.60/week across 3,481 evaluated
configurations). The original Phase B design doc named two deferred, out-of-scope alternative
hypotheses for exactly this situation: momentum-continuation and low-volatility-accumulation. This
sub-project pursues **momentum-continuation**: strongest-stocks-stay-strong, betting on the
continuation of an already-established uptrend rather than a reversal off oversold conditions.

Neither hypothesis has prior data in this codebase as an independent candidate-generation engine.
(Low-volatility-accumulation's core signal, `vol_contraction`, was tested once in Phase A but only
as an additive filter layered on the existing A/B/C/D pool, not as its own trigger — a materially
different, weaker test than what this document proposes for momentum-continuation.)

**This phase's goal:** build a genuinely new candidate-generation path — a sixth pattern, "F모멘텀,"
parallel to A/B/C/D and E반등 — and backtest it with the same rigor (same universe, same train/test
split, same decision-gate bar) as every prior sub-project in this line.

## 2. Entry Rule

All four conditions evaluated at trigger day `idx`, AND'd together, on top of the reused
liquidity/quality base filters:

1. **Relative-strength leadership**: the ticker's own trailing-60-trading-day return
   (`close[idx] / close[idx-60] - 1`) ranks in the top 10% of the same day's cross-sectional
   distribution of trailing-60-day returns across the full 959-ticker operating universe.
2. **New high**: `close[idx] >= max(high[idx-60..idx])` — the trigger day's close is at or above
   the trailing 60-trading-day high (roughly a 3-month new high).
3. **Trend alignment**: `close[idx] > sma50[idx] > sma200[idx]` — classic "stage 2 uptrend"
   ordering, using the existing `sma()` function from `backtest/indicators.py`.
4. **Base filters** (reused unmodified from `evaluate_candidate()`'s liquidity/quality gates,
   `backtest/swing_signal_engine.py` lines 112-121): `current_price >= MIN_PRICE`,
   `current_price * volume[idx] >= MIN_TURNOVER_ALGO`, no negative DART disclosure match, no
   large net-sell supply flag, `rvol >= 1.0`.

`entry = close[idx+1]`, `entry_idx = idx+2`, `hold_days = 10` — a single-day trigger, no multi-day
confirmation layer (unlike E반등's later-added 2-day confirmation). This phase deliberately stays a
single hand-specified rule, matching Phase B's own original scope note ("this phase is one
hand-specified rule") — additive refinements are only justified after seeing whether the base rule
is even directionally promising, the same conditional-next-step discipline this line has used
throughout.

`hold_days = 10` (double E반등's 5) reflects that a continuation bet needs more time to play out
than a short-term bounce; this is a deliberate, one-time design choice, not swept.

## 3. Architecture

New module `backtest/generate_momentum_candidates.py`, structurally parallel to
`backtest/generate_oversold_candidates.py` but with one added wrinkle: condition 1 (relative
strength) is **cross-sectional** — it needs every ticker's trailing return on the same day, not
just one ticker's own time series. Every prior additive signal in this codebase (Phase A's
`trend_alignment`/`vol_contraction`/`sector_strong`, sub-project 4's `volume_confirm`/
`sector_strong`/`support_confluence`) was single-ticker time-series or sector-scoped; this is the
first universe-wide cross-sectional signal in this line.

**Components:**
- `compute_trailing_return(df, idx, lookback=60) -> float` — `close[idx]/close[idx-lookback] - 1`,
  `NaN` if `idx < lookback`.
- `build_universe_return_lookup(per_ticker_ohlcv, *, lookback=60, top_frac=0.10) -> Dict[str, float]`
  — for each calendar date (ISO string key) with data across the universe, gathers every ticker's
  valid trailing-`lookback`-day return that date, computes the value at the `(1 - top_frac)`
  quantile of that day's distribution, and stores it as that date's RS cutoff. Precomputed once
  before the main scan loop, mirroring `candidate_signals.build_sector_returns_by_date`'s
  precompute-then-lookup structure (same reason: testable in isolation, computed once rather than
  recomputed per ticker).
- `_is_momentum_continuation(df, idx, *, rs_threshold) -> bool` — evaluates conditions 1-3 above;
  `rs_threshold` is the calling day's value from `build_universe_return_lookup`'s output (or
  `None`/missing, in which case this function fails closed and returns `False` — see §5).
- `_passes_base_filters(df, idx, *, supply, dart_items) -> bool` — a fresh, local implementation of
  condition 4, not imported from `generate_oversold_candidates.py`. That function is
  module-private (leading underscore); per the convention already established when
  `atr_stop_grid_search.py` chose to duplicate `target_stop_grid_search._window_df` rather than
  import a private cross-module symbol, this module does the same rather than reaching into a
  sibling module's internals. The duplicated logic is ~10 lines, identical in content to the
  existing `_passes_base_filters`.
- `scan_momentum_candidates(tickers, *, start, end, dart_api_key=DART_API_KEY) -> Tuple[List[CachedCandidate], List[Dict]]`
  — fetches OHLCV per ticker (same fetch/cache/skip pattern as every prior scan function in this
  line), builds `per_ticker_ohlcv`, calls `build_universe_return_lookup` once, then iterates
  ticker × day exactly like `generate_oversold_candidates.scan_oversold_candidates`, emitting
  `CachedCandidate(pattern_type="F모멘텀", score=110, rank_score=110, grade="매수", hold_days=10, ...)`
  for each day/ticker that passes all four conditions.
- `target_stop_grid_search.py` is **not modified** — the resulting candidate pool is run through
  its existing, unmodified `run_grid_search` exactly as every prior sub-project has done.

## 4. Data Flow

```
per_ticker_ohlcv (959 tickers, Yahoo fetch, same cache as every prior sub-project)
  -> build_universe_return_lookup(lookback=60, top_frac=0.10)   [date_key -> rs_threshold]
  -> scan_momentum_candidates: for each (ticker, day):
       base filters -> RS (own trailing return >= that day's rs_threshold)
       -> new-high -> trend alignment -> CachedCandidate
  -> backtest_momentum_candidates.json
  -> target_stop_grid_search.run_grid_search (unmodified) -> backtest_momentum_grid_search_results.json
  -> docs/03-analysis/swing-algo-momentum-continuation.analysis.md
```

## 5. Error Handling

- A ticker whose fetch fails (404/network error) is recorded in `skipped_tickers` and excluded from
  both the return lookup and the scan, exactly like every prior scan function in this line — not
  treated as a bug.
- A date with too few tickers contributing a valid trailing return (e.g., early in the 5-year fetch
  window, before 60 trading days of history exist) is simply absent from
  `build_universe_return_lookup`'s output dict; `_is_momentum_continuation` fails closed (`False`)
  when `rs_threshold` is `None`/missing for that day, rather than raising or defaulting to a
  guessed threshold.
- Insufficient per-ticker history for `compute_trailing_return`, `sma50`/`sma200`, or the 60-day
  high window (`idx < 200`, since `sma200` is the binding constraint) is handled by the existing
  `sma()` function's `NaN`-on-insufficient-window behavior; `_is_momentum_continuation` checks
  `np.isfinite` on every computed value before comparing, consistent with `_is_oversold_bounce`'s
  existing pattern.

## 6. Testing

Value-pinning tests in `backtest/tests/test_generate_momentum_candidates.py`, following this line's
established convention (synthetic DataFrame fixtures with numerically pre-verified values,
monkeypatch for network isolation in the scan-level test):

- `compute_trailing_return`: a fixed close-price fixture with a known 60-bar-ago value, asserting
  the exact computed return; a fixture with `idx < 60` asserting `NaN`.
- `build_universe_return_lookup`: a small synthetic `per_ticker_ohlcv` (a handful of tickers, a
  known distribution of trailing returns on one date) asserting the exact computed cutoff value at
  `top_frac=0.10`, and a date excluded entirely (e.g. all tickers lack 60 bars of history) asserting
  that date key is absent from the result.
- `_is_momentum_continuation`: one fixture where all three conditions (RS, new-high, alignment) are
  true → `True`; one fixture each where exactly one condition fails → `False`; a
  `rs_threshold=None` case → `False` (fail-closed).
- `scan_momentum_candidates`: monkeypatched fetch/base-filter/condition functions (mirroring
  `test_generate_oversold_candidates.py`'s `test_scan_oversold_candidates_caches_window_and_fields`
  pattern) asserting correct `date`/`entry`/`pattern_type`/`hold_days`/window fields, plus a
  fetch-failure test asserting the ticker lands in `skipped_tickers`.

## 7. Limitations

- **Single hand-specified rule, not swept/tuned** — the 60-day RS/new-high lookback, the top-10%
  cutoff, and the 50/200-day SMA alignment periods are fixed by trader-review judgment, not
  grid-searched. A negative or inconclusive result here rules out this specific rule, not the
  momentum-continuation concept in general — the same caveat every prior sub-project in this line
  has carried for its initial hand-specified rule.
- **Single train/test split**, same acknowledged limitation as every prior sub-project.
- Inherits sub-project 1/2's limitations via the reused, unmodified simulation primitives: flat-fee
  assumption, orderbook ask/bid and pattern-C block not modeled, TOSS-LIVEPRICE using next-day-open
  as a live-price proxy.
- **Cross-sectional computation cost**: `build_universe_return_lookup` is `O(tickers × days)` once,
  versus every prior additive signal's per-ticker-only cost — expected to be noticeably slower than
  Phase A/sub-project 4's tag computation, though still a one-time precompute, not per-grid-cell.
- `hold_days = 10` is a one-time judgment call (not swept) reflecting the hypothesis that
  continuation plays need more time than a short-term bounce; a negative result should not be
  read as ruling out momentum-continuation at other holding periods.

No production code (`src/swing-scanner.src.js`) is changed by this phase. The analysis document
produced at the end of this phase must state plainly whether the selected train config reaches the
joint target (`hit_rate >= 90%`, `trades_per_week >= 5`, `cagr_15slot > 0`) with a statistically
reliable trade count (`n_trades >= 50`) on **both** train and test, using the same three-way outcome
framework (target-met / target-not-met-but-reliable / underpowered) as every prior sub-project.

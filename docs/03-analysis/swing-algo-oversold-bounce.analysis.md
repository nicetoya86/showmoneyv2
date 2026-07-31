# swing-algo-oversold-bounce Analysis Report

> **Analysis Type**: Empirical Result Report (PDCA Do → Check)
>
> **Project**: showmoneyv2
> **Feature**: swing-algo-oversold-bounce — Swing Algo Enhancement Sub-project 3, Phase B
> (Oversold-Bounce Candidate-Generation Engine, pattern "E반등")
> **Design Doc**: [2026-07-30-swing-algo-oversold-bounce-design.md](../superpowers/specs/2026-07-30-swing-algo-oversold-bounce-design.md)
> **Implementation Plan**: [2026-07-30-swing-algo-oversold-bounce.md](../superpowers/plans/2026-07-30-swing-algo-oversold-bounce.md)
> **Date**: 2026-07-31
> **Prior work**: [swing-algo-new-signal-filters.analysis.md](swing-algo-new-signal-filters.analysis.md)
> (sub-project 3 Phase A — all 8 additive-filter subsets on the *existing* candidate pool missed the
> joint target; that uniform negative result is the trigger condition for this Phase B new-engine attempt)

---

## 1. Method Summary

This phase does not filter the existing A/B/C/D candidate pool (Phase A's approach); it builds a
genuinely new candidate-generation path — a fifth pattern, "E반등" (oversold bounce) — admitting
stocks that `evaluate_candidate()`'s hard filter (`rsi14 < 40 → return None`,
`backtest/swing_signal_engine.py:117`) structurally excludes before any A/B/C/D pattern is even
checked. Full derivation and trader-review corrections are in the design doc; the five entry-rule
conditions (all AND'd, evaluated at trigger day `idx`), on top of the reused liquidity/quality base
filters:

- **RSI cross-up**: `rsi14[idx] >= 40 and rsi14[idx-1] < 40`.
- **Oversold depth** (not just a bare 40-line cross, which is noise-prone): `min(rsi14[idx-5..idx-1]) <= 35`
  — confirms a real oversold excursion preceded the cross.
- **Pullback depth** (the pattern is named for one, so one is required): `current_price / max(high[idx-20..idx]) - 1 <= -0.08`
  — at least an 8% retracement from the trailing 20-day high.
- **Uptrend context**: `close[idx] > sma60[idx]` — not a falling knife.
- **Bounce confirmation** (strengthened from a weak "any green candle" draft): `close[idx] > high[idx-1]`
  — the trigger day must close above the *entire prior day's range*, a materially stronger reversal
  signal.

Candidates were scanned over the same 959-ticker operating universe
(`backtest/tickers_operating.txt`), same `2022-01-01`..`2026-01-01` date range, and reused already-cached
Yahoo OHLCV/DART/KRX-supply data — no new network fetch, except 4 tickers that 404'd against Yahoo
(likely delisted/renamed since prior sub-projects' fetch; recorded in `skipped_tickers`, not treated
as a bug). The scan produced **119 raw candidates**.

Candidates were fed through `backtest/target_stop_grid_search.py`'s existing `run_grid_search`
**completely unmodified** — same 432-cell grid, same train (`2022-01-01`..`2024-06-30`) / test
(`2024-07-01`..`2026-01-01`) split as sub-projects 2 and 3 Phase A, same train-only selection rule
(highest `cagr_15slot` among cells clearing `hit_rate >= 90%` and `trades_per_week >= 5`; falls back
to `trades_per_week >= 5` sorted by `hit_rate` then `cagr_15slot` if none qualify), same
`n_trades >= 50` statistical-reliability rule. Source data read directly from the committed
`backtest_oversold_candidates.json` (119 candidates) and `backtest_oversold_grid_search_results.json`
(full grid + selection + test result); no numbers below are estimated.

## 2. Train vs. Test Result

Selected train config: `target_pct=0.10, stop_pct=0.025, min_score=60, regime_gate=false, exclude_d_box=false`
(train selection status: `target_not_met` — no cell cleared the 90%/5-per-week bar, so the fallback
rule picked this cell by `trades_per_week` then `hit_rate`/`cagr_15slot`).

| Split | n_trades | Reliable (n≥50)? | hit_rate | trades_per_week | avg_pnl | cagr_15slot |
|-------|---------:|:-----------------:|---------:|-----------------:|--------:|-------------:|
| Train (2022-01-01..2024-06-30) | 66 | Yes | 16.7% | 0.51 | 0.16% | 0.38% |
| Test (2024-07-01..2026-01-01)  | 41 | **No** | 26.8% | 0.52 | 1.29% | 2.39% |

## 3. Decision-Gate Verdict: Underpowered (Outcome 3)

Per the design doc's explicitly-called-out sample-size risk: the five-condition rule is more
restrictive than any single A/B/C/D pattern condition, and the reliability rule requires
`n_trades >= 50` on **both** train and test before drawing a pass/fail conclusion. Train clears this
(66 trades) but **test does not (41 trades)** — so this result is **inconclusive/underpowered, not a
negative result**, and must not be conflated with one.

For completeness, the raw numbers are also far from the 90%-hit-rate / ≥5-per-week / positive-return
joint target on both splits (hit_rate 17-27% vs. 90% required; trades_per_week ~0.5 vs. 5 required)
— but per the design doc's own rule, the test split's trade count is too small to treat this as a
statistically reliable negative verdict on the "E반등" hypothesis itself; it is a verdict on *this
specific parameterization's frequency*, which the small sample cannot support drawing a hit-rate
conclusion from either way.

**Which threshold to loosen first:** the **bounce-confirmation condition** (`close[idx] > high[idx-1]`),
not the RSI depth (35) or pullback depth (8%). Per the design doc's Design Revisions section, this
condition was the last and most-strengthened correction — from a weak "any green candle"
(`close >= open`) to requiring the trigger day's close to exceed the *entire prior day's range*. That
is a single-day, high-bar condition stacked on top of same-day RSI cross-up, oversold depth, pullback
depth, and SMA60 context all firing together — the most likely bottleneck suppressing frequency
without diluting what "oversold" or "pullback" mean (loosening RSI depth or pullback depth would
directly weaken the oversold-bounce hypothesis being tested; loosening the confirmation bar to, e.g.,
`close[idx] > close[idx-1]` keeps the reversal-confirmation intent while relaxing only how strong that
single day's move must be).

## 4. Limitations

- **Single hand-specified rule, not swept/tuned** — all five thresholds (35, 8%, 60-bar SMA,
  prior-day-high, hold_days=5) are fixed by trader-review judgment, not grid-searched; a negative or
  inconclusive result here rules out *this specific rule*, not the oversold-bounce concept in general.
- **Single train/test split**, same acknowledged limitation as every prior sub-project in this line.
- Inherits all of sub-project 1/2's limitations: flat-percentage target/stop, orderbook ask/bid and
  pattern-C blocks not modeled, flat-fee assumption — all reused unmodified via
  `target_stop_grid_search.py`.
- **Sample-size risk, realized**: as anticipated by the design doc, the five-condition rule proved
  restrictive enough (119 raw candidates, 66/41 train/test after target/stop simulation) to leave the
  test split underpowered — exactly the outcome the design doc flagged as a live possibility, not a
  hypothetical one.

## 5. Next Step Recommendation (superseded by Section 6 — see below)

No production code (`src/swing-scanner.src.js`) has been changed by this phase — as with every prior
sub-project, that remains a separate, later decision. Given the underpowered (not negative) verdict,
the recommended next step was to loosen the bounce-confirmation threshold specifically (Section 3)
and re-run the same scan/grid-search pipeline unmodified, rather than immediately pivoting to the
momentum-continuation or low-volatility-accumulation hypotheses — this is a cheaper, more targeted
next probe than starting a new hypothesis from scratch, and directly tests whether frequency (not the
underlying oversold-bounce economics) was the binding constraint. That retry was run — see Section 6.

## 6. Retry: Loosened Bounce-Confirmation Threshold

**Change:** `_is_oversold_bounce`'s bounce-confirmation condition was relaxed from
`close[idx] > high[idx-1]` (close above the *entire prior day's range*) to
`close[idx] > close[idx-1]` (close above the prior day's *close* only) — the specific loosening
Section 3 recommended, keeping RSI depth (35), pullback depth (8%), and SMA60 context untouched.
Everything else (universe, date range, train/test split, grid-search pipeline) is identical to the
initial run.

**Result: raw candidate count barely moved.** 119 → **127** raw candidates (+8, +6.7%) — the
bounce-confirmation condition was evidently *not* the primary bottleneck suppressing frequency.

| Split | Cell | n_trades | Reliable (n≥50)? | hit_rate | trades_per_week | cagr_15slot |
|-------|------|---------:|:-----------------:|---------:|-----------------:|------------:|
| Train — same cell as original selection (`target_pct=0.10, stop_pct=0.025, regime_gate=false`) | before → after | 66 → 72 | Yes → Yes | 16.7% → 15.3% | 0.51 → 0.55 | 0.38% → **-0.02%** |
| Test — same cell | before → after | 41 → **42** | No → **No** | 26.8% → 26.2% | 0.52 → 0.54 | 2.39% → 2.45% |
| Train — grid's own fallback selection (`best_cagr_overall`, picked independently each run) | — | 66 → 31 | Yes → **No** | 16.7% → 12.9% | 0.51 → 0.24 | 0.38% → 0.23% |
| Test — grid's own fallback selection | — | 41 → 20 | No → No | 26.8% → 20.0% | 0.52 → 0.26 | 2.39% → 0.88% |

Two things stand out:

1. **Held fixed on the same cell, test `n_trades` moved 41 → 42** — one additional trade. The
   loosening did not meaningfully close the gap to the `n_trades >= 50` reliability bar; test remains
   underpowered.
2. **The grid's own fallback-selection rule (`select_best_config`, "no cell clears the joint bar, so
   pick the train cell with the single highest `cagr_15slot` across all 432 cells") picked a
   *different, less reliable* cell this time** (`regime_gate=true, stop_pct=0.02`, train n=31, test
   n=20) — an artifact of that selection rule being sensitive to noise in small samples, not evidence
   the new candidates are worse. Both selected-cell views (same-cell comparison and each run's own
   fallback pick) are reported here for transparency; the same-cell comparison is the more meaningful
   one for judging whether the retry worked.

**Verdict: the retry did not resolve the sample-size problem.** Loosening bounce-confirmation was the
cheapest, most targeted lever available, and it moved test `n_trades` by only 1 (41→42). This is a
genuine (not merely inconclusive) finding about *this specific lever*: the joint requirement of RSI
depth (≤35) + pullback depth (≥8%) + SMA60 uptrend context, all coinciding on one trigger day, is the
real constraint on frequency — not the strength of the same-day confirmation candle. Further loosening
the confirmation clause alone (e.g. dropping it entirely) is very unlikely to add enough trades to
matter, since it was already shown to be nearly inert (+8 raw candidates, +1 test trade).

## 7. Next Step Recommendation (current)

Given Section 6's result, the recommended next step is **not** a further tweak to the
bounce-confirmation clause. Two options, in order of cost:

- **(a) Loosen RSI depth or pullback depth instead** — e.g. RSI depth from ≤35 to ≤38, or pullback
  depth from ≥8% to ≥6% — accepting that this now measurably dilutes what "oversold" or "pullback"
  means (per Section 3's original caution), in exchange for a real chance at clearing `n_trades >= 50`
  on test. This should be treated as testing a materially different (weaker) hypothesis, not a minor
  retry, and reported with that framing.
- **(b) Treat the oversold-bounce hypothesis as inconclusive at this restrictiveness and pivot** to
  the momentum-continuation or low-volatility-accumulation hypotheses (deferred from the design doc's
  "Explicitly out of scope" list), rather than continuing to hand-tune this rule's thresholds one at a
  time.

No production code (`src/swing-scanner.src.js`) has been changed by this phase or its retry. Which of
(a) or (b) to pursue is a decision pending the user's review of these results, not one to make
unilaterally here.

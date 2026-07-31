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

## 5. Next Step Recommendation

No production code (`src/swing-scanner.src.js`) has been changed by this phase — as with every prior
sub-project, that remains a separate, later decision. Given the underpowered (not negative) verdict,
the recommended next step is to loosen the bounce-confirmation threshold specifically (Section 3)
and re-run the same scan/grid-search pipeline unmodified, rather than immediately pivoting to the
momentum-continuation or low-volatility-accumulation hypotheses — this is a cheaper, more targeted
next probe than starting a new hypothesis from scratch, and directly tests whether frequency (not the
underlying oversold-bounce economics) was the binding constraint. Pivoting to a different hypothesis
remains the fallback if a loosened confirmation bar still fails to clear `n_trades >= 50` on test.
Any further work is pending the user's review of these results.

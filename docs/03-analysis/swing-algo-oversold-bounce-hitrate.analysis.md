# swing-algo-oversold-bounce-hitrate Analysis Report

> **Analysis Type**: Empirical Result Report (PDCA Do → Check)
>
> **Project**: showmoneyv2
> **Feature**: swing-algo-oversold-bounce-hitrate — Swing Algo Enhancement Sub-project 4 ("Phase C")
> (E반등/oversold-bounce pattern hit_rate improvement — all 5 trader-diagnosed levers applied)
> **Design Doc**: [2026-08-01-swing-algo-oversold-bounce-hitrate-design.md](../superpowers/specs/2026-08-01-swing-algo-oversold-bounce-hitrate-design.md)
> **Implementation Plan**: [2026-08-01-swing-algo-oversold-bounce-hitrate.md](../superpowers/plans/2026-08-01-swing-algo-oversold-bounce-hitrate.md)
> **Date**: 2026-08-01
> **Prior work**: [swing-algo-oversold-bounce.analysis.md](swing-algo-oversold-bounce.analysis.md)
> (sub-project 3 Phase B + retry — best grid cell reached only ~43.3% hit_rate on train with an
> underpowered test sample (n=41→42 after the bounce-confirmation retry); that shortfall triggered
> the user's request for a professional-trader review, which produced the 5 items applied here)

---

## 1. Method Summary

Per the design doc's trader review, 5 items were diagnosed against Phase B's E반등 rule:

1. **Volume confirmation** — trigger-day rvol, strengthened beyond the existing base filter (`rvol >= 1.0`) to `rvol >= 1.5`.
2. **Sector relative strength / regime context** — reuse of Phase A's `sector_strong` computation, unmodified.
3. **2-day confirmation** — require the RSI cross-up to still hold one bar later, guarding against a single-day whipsaw.
4. **Support proximity** — proximity to an actual pivot-low support level, replacing the arbitrary 8% pullback-depth threshold's implicit assumption of "any" retracement being meaningful.
5. **ATR-based volatility-adjusted target/stop** — replacing the fixed-percentage target/stop grid with one scaled by each candidate's own ATR.

The user's instruction was to apply items 1 through 5, in order, with none skipped. As the design
doc explains (§2), applying them literally in numeric order would be wasteful: item 3 changes the
entry rule itself (producing a new candidate pool), while items 1/2/4 are additive boolean tags
layered on top of whatever pool exists, and item 5 is an independent target/stop mechanism. Tagging
a pool that item 3 would later replace would mean recomputing all tags. The approved execution
order was therefore **3 → 1, 2, 4 → 5**, covering all 5 items while avoiding rework; this document
reports on all 5 in that order. Full rationale, formulas, and parameter values (`rvol >= 1.5`,
pivot-low lookback 40 bars / ±3% tolerance, ATR grid `target_mult ∈ {1.0, 1.5, 2.0, 3.0}` ×
`stop_mult ∈ {0.5, 1.0, 1.5, 2.0}`) are in the design doc; they are not re-derived here.

All three stages reuse the same 959-ticker operating universe, `2022-01-01`..`2026-01-01` scan
range, and the same train (`2022-01-01`..`2024-06-30`) / test (`2024-07-01`..`2026-01-01`) split
and `target_stop_grid_search.run_grid_search` decision/reliability rules as every prior sub-project
in this line (`hit_rate >= 90%` and `trades_per_week >= 5` and `cagr_15slot > 0` on both splits;
`n_trades >= 50` on both splits before any pass/fail conclusion is drawn).

## 2. Stage 1 Result (Item 3 — 2-day Confirmation)

**Candidate count**: v2 (Phase B's pool, no 2-day confirmation) had **127** candidates. v3 (with
the 2-day confirmation requirement added) has **123** candidates — a reduction of **4** candidates
(-3.1%). Both scans hit the same 4 tickers' 404s from Yahoo (`042670.KS`, `450140.KS`, `019440.KS`,
`448830.KQ`), recorded in `skipped_tickers`, not a new issue. This drop is real but far smaller
than the design doc's stated expectation ("v3 후보 수가 더 줄어들 것으로 예상됨") might suggest for
a materially more restrictive condition — reported plainly rather than assumed to be larger.

**v3 pool run through the unmodified grid search with no tags** (`backtest_oversold_v3_none_results.json`),
selected train config `target_pct=0.10, stop_pct=0.04, min_score=60, regime_gate=true,
exclude_d_box=false` (selection status: `target_not_met`):

| Split | n_trades | Reliable (n≥50)? | hit_rate | trades_per_week | avg_pnl | cagr_15slot |
|-------|---------:|:-----------------:|---------:|-----------------:|--------:|-------------:|
| Train (2022-01-01..2024-06-30) | 21 | **No** | 19.05% | 0.16 | 1.41% | 1.49% |
| Test (2024-07-01..2026-01-01)  | 23 | **No** | 8.70%  | 0.29 | -1.25% | -2.28% |

Stage 1 in isolation is underpowered on both splits — 21 and 23 trades respectively, both well
under the `n_trades >= 50` reliability bar — before any tags from Stage 2 are layered on.

## 3. Stage 2 Result (Items 1, 2, 4 — Tag Subsets)

Tag counts on the 123-candidate v3 pool (`backtest_oversold_v3_tags.json`, recomputed directly
from the file): **volume_confirm = 61**, **sector_strong = 16**, **support_confluence = 62** — all
confirmed against the controller's own count. All 7 non-empty tag subsets (`backtest_oversold_v3_tagsweep_results.json`)
plus the untagged (∅) pool from Stage 1 above are shown together, each run through the unmodified
grid search with its own train-selected config:

| Pool | Split | n_trades | Reliable (n≥50)? | hit_rate | trades_per_week | avg_pnl | cagr_15slot |
|---|---|---:|:---:|---:|---:|---:|---:|
| ∅ (untagged) | Train | 21 | **No** | 19.05% | 0.16 | 1.41% | 1.49% |
| ∅ (untagged) | Test | 23 | **No** | 8.70% | 0.29 | -1.25% | -2.28% |
| volume_confirm | Train | 6 | **No** | 33.33% | 0.05 | 2.72% | 0.95% |
| volume_confirm | Test | 12 | **No** | 8.33% | 0.15 | -2.00% | -2.43% |
| sector_strong | Train | 5 | **No** | 40.00% | 0.04 | 1.40% | 0.55% |
| sector_strong | Test | 2 | **No** | 0.00% | 0.03 | -4.20% | n/a* |
| support_confluence | Train | 42 | **No** | 26.19% | 0.32 | 1.30% | 1.61% |
| support_confluence | Test | 18 | **No** | 11.11% | 0.23 | -0.04% | -0.04% |
| volume_confirm+sector_strong | Train | 2 | **No** | 100.00% | 0.02 | 3.80% | 2.03% |
| volume_confirm+sector_strong | Test | 2 | **No** | 0.00% | 0.03 | -1.70% | -0.68% |
| volume_confirm+support_confluence | Train | 2 | **No** | 50.00% | 0.02 | 5.48% | 15.93% |
| volume_confirm+support_confluence | Test | 2 | **No** | 0.00% | 0.03 | -2.20% | -6.90% |
| sector_strong+support_confluence | Train | 3 | **No** | 33.33% | 0.02 | 2.47% | 0.58% |
| sector_strong+support_confluence | Test | 0 | **No** | 0.00% | 0.00 | 0.00% | n/a* |
| volume_confirm+sector_strong+support_confluence | Train | 2 | **No** | 100.00% | 0.02 | 3.80% | 2.03% |
| volume_confirm+sector_strong+support_confluence | Test | 1 | **No** | 0.00% | 0.01 | -1.70% | n/a* |

\* `cagr_15slot` is `NaN` in the source JSON when the split has too few trades (0-2) to compute a
portfolio curve; recorded as `n/a` here rather than a fabricated number.

**Every one of the 8 pools (∅ + 7 tag subsets) is unreliable on both train and test** — the largest
train `n_trades` across all 8 is 42 (`support_confluence`), still under the 50-trade bar, and every
test split has `n_trades` between 0 and 23. Some cells show eye-catching hit_rate numbers (100% on
two 2-trade pools) — these are explicitly **not** evidence of anything per the `n_trades >= 50` rule
inherited from Phase A/B: a 2-trade 100% hit rate is noise, not signal, and must not be read as a
promising subset.

## 4. Stage 3 Result (Item 5 — ATR-based Target/Stop)

**Pool selection** (per the implementation plan's Task 7 Step 1 rule: pick whichever of the 8 Stage
2 pools has the largest test `n_trades`, tie-break to the untagged pool): comparing test `n_trades`
across all 8 rows in the Section 3 table — ∅ (23), volume_confirm (12), sector_strong (2),
support_confluence (18), and all three-tag combinations (≤2) — the **untagged (∅) v3 pool** has the
largest test `n_trades` (23) of any of the 8, and is also the pool with the fewest additional free
parameters. Both criteria point to the same pool, so item 5's ATR grid was run on the **untagged v3
pool**, not any tagged subset. This choice is recorded here explicitly, per the plan's instruction
to treat it as a reported decision rather than a hidden detail.

Note on comparability: `atr_stop_grid_search.py`'s `run_one_atr_config` applies no
`min_score`/`regime_gate`/`exclude_d_box` filtering at all — this is by design, per the design
doc's explicit scoping of those axes out of the ATR script (design doc §Stage 3). Because of this,
the ATR grid's trade counts (train 66-75 per cell below) are naturally larger than Section 2/3's
gated flat-grid cells and are not directly comparable to them on that basis — the larger `n_trades`
seen in Stage 3 is a byproduct of the ungated comparison, not evidence that the ATR mechanism or
the pool choice performs better.

The 16-cell ATR grid (`target_mult ∈ {1.0, 1.5, 2.0, 3.0}` × `stop_mult ∈ {0.5, 1.0, 1.5, 2.0}`) on
train (`backtest_oversold_atr_grid_results.json`):

| target_mult | stop_mult | n_trades | hit_rate | trades_per_week | avg_pnl | cagr_15slot |
|---:|---:|---:|---:|---:|---:|---:|
| 1.0 | 0.5 | 66 | 31.82% | 0.51 | 0.15% | 0.29% |
| 1.0 | 1.0 | 74 | 44.59% | 0.57 | -0.24% | -0.36% |
| 1.0 | 1.5 | 74 | 50.00% | 0.57 | -0.41% | -0.55% |
| 1.0 | 2.0 | 74 | 51.35% | 0.57 | -0.48% | -0.73% |
| 1.5 | 0.5 | 67 | 22.39% | 0.51 | 0.30% | 0.56% |
| 1.5 | 1.0 | 75 | 29.33% | 0.58 | -0.01% | -0.19% |
| 1.5 | 1.5 | 75 | 34.67% | 0.58 | -0.07% | -0.30% |
| 1.5 | 2.0 | 75 | 36.00% | 0.58 | -0.11% | -0.43% |
| 2.0 | 0.5 | 67 | 16.42% | 0.51 | 0.58% | 1.03% |
| 2.0 | 1.0 | 75 | 22.67% | 0.58 | 0.22% | 0.27% |
| 2.0 | 1.5 | 75 | 24.00% | 0.58 | -0.19% | -0.64% |
| 2.0 | 2.0 | 75 | 25.33% | 0.58 | -0.21% | -0.78% |
| **3.0** | **0.5** | **67** | **5.97%** | **0.51** | **0.54%** | **1.09%** ← selected |
| 3.0 | 1.0 | 75 | 9.33% | 0.58 | 0.21% | 0.09% |
| 3.0 | 1.5 | 75 | 9.33% | 0.58 | -0.26% | -0.87% |
| 3.0 | 2.0 | 75 | 9.33% | 0.58 | -0.31% | -1.04% |

Selection status: `target_not_met` — no cell clears the joint 90%-hit-rate / ≥5-per-week bar. No
cell even clears the `trades_per_week >= 5` frequency floor alone (max is 0.58), so the fallback
chain fell all the way to `best_cagr_overall`, which picked `target_mult=3.0, stop_mult=0.5`
(highest train `cagr_15slot` = 1.09% among all 16 cells) — the same cell reported in the
`fallback_best_cagr` field of the raw result.

Chosen config's train vs. test result:

| Split | n_trades | Reliable (n≥50)? | hit_rate | trades_per_week | avg_pnl | cagr_15slot |
|-------|---------:|:-----------------:|---------:|-----------------:|--------:|-------------:|
| Train (2022-01-01..2024-06-30) | 67 | **Yes** | 5.97% | 0.51 | 0.54% | 1.09% |
| Test (2024-07-01..2026-01-01)  | 47 | **No**  | 8.51% | 0.60 | 0.37% | 0.62% |

## 5. Decision-Gate Verdict

No result anywhere across Stage 1, Stage 2 (8 pools), or Stage 3 (16 cells) reaches
`hit_rate >= 90%`, `trades_per_week >= 5`, and `cagr_15slot > 0` on both train and test — reliably
or otherwise. The frequency floor alone (`trades_per_week >= 5`) is never cleared by any cell in
any stage; the highest observed value anywhere is 0.60 (Stage 3 test), two orders of magnitude
below the bar.

Applying the three-way outcome framework (target-met / target-not-met-but-reliable / underpowered),
explicitly stage by stage:

- **Stage 1 (∅ v3 pool, no tags): Underpowered.** Train `n_trades=21` and test `n_trades=23` are
  both below the 50-trade reliability bar. No pass/fail conclusion can be drawn from these numbers
  either way.
- **Stage 2 (all 7 tag subsets): Underpowered**, uniformly. The largest train sample across all 7
  subsets is 42 (`support_confluence`), still short of 50; every test sample is 18 or fewer. The
  handful of high hit_rate figures (e.g. 100% on 2-trade pools) are sampling noise, not a
  target-met result, and are explicitly not treated as one.
- **Stage 3 (ATR grid on the untagged pool): Mixed — the one place in this sub-project where a
  reliable half exists, and it is a genuine (not underpowered) negative result.** Train
  `n_trades=67` clears the 50-trade bar, so the train hit_rate of 5.97% is a **statistically
  reliable, genuinely target-not-met** result, not an inconclusive one — it misses the 90% bar by
  roughly 84 percentage points, an order of magnitude short, not a borderline miss. Test
  `n_trades=47` falls just short of the 50-trade bar, so the test side remains formally
  underpowered and the full **joint** (both-split) gate cannot be conclusively evaluated. However,
  given how decisively train fails (5.97% vs. 90%), it is very unlikely that a few additional test
  trades would flip the picture; this is functionally a negative result for the ATR-based
  target/stop mechanism specifically.

Overall: no stage or pool anywhere clears the joint decision gate, reliably or otherwise. The
predominant honest label across Stages 1 and 2 is **Underpowered** (Outcome 3) — small samples that
cannot support a pass/fail conclusion. Stage 3 is the one place with a statistically reliable
result, and that reliable result is a clear **target-not-met** (Outcome 2), not merely inconclusive.

## 6. Limitations

Restating the design doc's §7 limitations, not re-deriving them:

- **Parameter proliferation, realized as flagged.** This sub-project introduced several new free
  parameters simultaneously (2-day confirmation threshold, `rvol >= 1.5`, pivot-low lookback = 40
  days / tolerance = ±3%, and the 4×4 ATR multiplier grid) — more than the "one lever at a time"
  discipline of Phase A/B. The design doc's mitigation (report Stage 1 and Stage 2 individually,
  not just the final combination) is exactly what Sections 2-4 above do.
- **First-cut, unswept judgment calls.** The pivot-low lookback (40 days) and proximity tolerance
  (±3%) were fixed by trader-review judgment at design time, not grid-searched, and are not swept
  here — a negative/underpowered result rules out these specific values, not the underlying
  support-confluence concept in general.
- **Sample-size risk — materialized largely as anticipated, and worse in Stage 2 than Stage 1
  alone.** The design doc explicitly flagged that Stage 1's 2-day confirmation would shrink the
  pool further and that Stage 2's AND-style tag filters would shrink it more, likely leaving almost
  no combination with `n_trades >= 50` on both splits. That is exactly what happened: Stage 1's
  own untagged pool was already underpowered (21/23), and every one of the 7 tag subsets in Stage 2
  compounds that (down to single digits or low 40s on train, ≤18 on test). Stage 3's ATR grid,
  run on the pool with the largest test `n_trades` of the 8 (§4's pool selection), still landed at
  test `n_trades=47` — just 3 trades short of the reliability bar, the closest any part of this
  sub-project came to a reliable joint (both-split) result. Note this larger sample is a byproduct
  of `atr_stop_grid_search.py` applying no `min_score`/`regime_gate`/`exclude_d_box` filtering
  (§4), not evidence of the pool choice or ATR mechanism performing better.
- Inherits Phase B's other limitations (orderbook ask/bid and pattern-C blocks not modeled,
  flat-fee assumption) via the reused, unmodified simulation primitives; Stage 3's ATR-based
  target/stop replaces the flat-percentage assumption specifically, but the rest is unchanged.
- Single train/test split — same acknowledged limitation as every prior sub-project in this line.

## 7. Next Step Recommendation

Given the actual results — every stage and pool misses the joint decision gate, the frequency floor
is never remotely approached (max 0.60 trades/week vs. 5 required), and the one statistically
reliable result available (Stage 3 train, n=67) misses the hit_rate bar by an order of magnitude
(5.97% vs. 90%) rather than by a narrow margin — this line of the E반등 hypothesis, with all 5
trader-diagnosed levers now applied, **should be considered complete**. Further hand-tuning of any
single lever (e.g., sweeping the ATR multiplier grid further, adjusting the pivot-low tolerance, or
loosening the 2-day confirmation) is not a reasonable next step: none of the **3,481** evaluated
configurations examined across this sub-project (8 pools [∅ untagged + 7 tag subsets] × 432
flat-grid train cells + 8 corresponding test evaluations = 3,464, plus the ATR grid's 16 train
cells + 1 test evaluation = 17; 3,464 + 17 = 3,481) came remotely close to the 5-per-week
frequency floor, so the binding constraint is structural (the pattern is simply too rare in this
universe/date-range at any of the tested parameterizations) rather than a fine-tuning problem that
one more parameter sweep would fix.

**Concrete recommendation**: do not continue iterating on E반등 thresholds. Pivot to a different
candidate-generation hypothesis — the momentum-continuation or low-volatility-accumulation patterns
noted as deferred, out-of-scope alternatives in the original Phase B design doc — rather than
spending further sub-projects tuning this specific pattern's parameters.

No production code (`src/swing-scanner.src.js`) has been changed by this sub-project — as with
every prior sub-project in this line, that remains a separate, later decision.

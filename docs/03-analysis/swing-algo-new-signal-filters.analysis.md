# swing-algo-new-signal-filters Analysis Report

> **Analysis Type**: Empirical Result Report (PDCA Do → Check)
>
> **Project**: showmoneyv2
> **Feature**: swing-algo-new-signal-filters — Swing Algo Enhancement Sub-project 3, Phase A
> (New Signal Filters: Trend Alignment / Sector Relative Strength / Volatility Contraction)
> **Design Doc**: [2026-07-28-swing-algo-new-signal-filters-design.md](../superpowers/specs/2026-07-28-swing-algo-new-signal-filters-design.md)
> **Implementation Plan**: [2026-07-28-swing-algo-new-signal-filters.md](../superpowers/plans/2026-07-28-swing-algo-new-signal-filters.md)
> **Date**: 2026-07-29
> **Prior work**: [swing-algo-target-stop-retuning.analysis.md](swing-algo-target-stop-retuning.analysis.md)
> (sub-project 2 — the 432-cell target/stop/threshold grid search that found 0/432 cells
> profitable on the existing candidate pool, the trigger condition for this sub-project)

---

## 1. Method Summary

This phase tests whether three **additive boolean signal tags** — computed per `(ticker, date)`
from data already available as of the candidate's signal day, no lookahead — can isolate a
profitable, high-hit-rate subset from sub-project 1/2's existing 21,587-candidate pool, without
building a new candidate-generation engine. Full derivation, formulas, and the trader-review
corrections are in the design doc; only the corrections most relevant to interpreting the numbers
below are restated here:

- **Trend alignment** (`trend_aligned`): last completed week's close vs. a 10-week weekly SMA —
  revised from a noisier "up week vs. prior week" draft, and deliberately a weekly-timeframe
  signal distinct from the existing daily `sma20 > sma60` gate already used elsewhere in scoring.
  Fired on 15,336 / 21,587 candidates (71.0%).
- **Volatility contraction** (`vol_contraction`): ATR/price percentile-rank computed over a
  *pre-event* window (`idx-60..idx-10`), deliberately excluding the most recent 10 bars — the
  existing A/C/D patterns require a volume/price expansion to have already fired at `idx`, so a
  naive "still low volatility right now" check would contradict the candidates' own definition.
  Fired on 6,630 / 21,587 candidates (30.7%).
- **Sector relative strength** (`sector_strong`): candidate's sector's trailing-20-day
  equal-weighted return, ranked against all sectors with ≥5 cached tickers that day, `True` if in
  the top 30% (`top_frac=0.3`); fails closed (`False`) if the sector has fewer than 5 tickers or is
  unmapped. Fired on 10,859 / 21,587 candidates (50.3%) — see Limitations for why this is higher
  than "top 30% of sectors" naively suggests.
- **Sweep**: the existing 432-cell target/stop/min-score/regime-gate/D박스-inclusion grid from
  sub-project 2 (unmodified) was re-run against each of the 8 tag subsets (∅ plus all 7 non-empty
  combinations of the 3 tags) — `∅` reuses sub-project 2's already-committed result directly rather
  than re-running. `target_stop_grid_search.py`'s `run_one_config`/`run_grid_search` gained an
  additive `required_tags`/`tags_lookup` parameter pair (default `frozenset()`, byte-identical to
  sub-project 2's existing behavior, regression-tested). All of sub-project 1/2's TOSS-LIVEPRICE,
  exit-simulation, transaction-cost, and 15-slot portfolio-CAGR machinery is reused unmodified.
- **Train/test split**: identical to sub-project 2 — train `2022-01-01`..`2024-06-30`, test
  `2024-07-01`..`2026-01-01`. Selection (train only) is sub-project 2's existing rule: among cells
  with `hit_rate >= 90%` and `trades_per_week >= 5`, pick the highest `cagr_15slot`; if none qualify
  (the case for all 8 subsets here), fall back to filtering to `trades_per_week >= 5` and sorting by
  `hit_rate` descending then `cagr_15slot` descending. The selected config per subset is evaluated
  **exactly once** on test, with no re-selection afterward.
- **Statistical-reliability rule**: any subset's selected config with train `n_trades < 50` must be
  flagged unreliable regardless of hit_rate (per the design doc's Design Revision #4, added because
  testing 8 subsets × 432 cells against one train/test split raises data-snooping risk versus
  sub-project 2's single 432-cell sweep).

Source data read directly from the committed `backtest_signal_filter_results.json` (8 subsets) and
`backtest_candidate_tags.json` (21,587 tagged candidates); no numbers below are estimated.

## 2. Per-Subset Results: Train vs. Test

All 8 subsets, `status = target_not_met` for every one. Train `n_trades` ranges 655–1,431 and test
`n_trades` ranges 406–839 across all subsets — every subset clears `n_trades >= 50` by a wide
margin, so **all 8 are statistically reliable** per the design doc's rule; none is disqualified for
low sample size.

| Subset (tags required) | Split | `n_trades` | `hit_rate` | `trades_per_week` | `avg_pnl` | `cagr_15slot` | Reliable (n≥50)? |
|---|---|---:|---:|---:|---:|---:|:---:|
| **none** (no filter, sub-project 2 baseline) | Train | 1,431 | 46.96% | 11.00 | -0.843% | -27.94%/yr | Yes |
| | Test | 839 | 45.89% | 10.70 | -0.937% | -29.59%/yr | Yes |
| **trend_aligned** | Train | 1,249 | 45.72% | 9.60 | -0.933% | -26.60%/yr | Yes |
| | Test | 790 | 47.59% | 10.07 | -0.832% | -25.52%/yr | Yes |
| **vol_contraction** | Train | 922 | 48.70% | 7.08 | -0.708% | -16.30%/yr | Yes |
| | Test | 612 | 50.33% | 7.80 | -0.624% | -16.21%/yr | Yes |
| **sector_strong** | Train | 1,267 | 47.59% | 9.74 | -0.781% | -24.20%/yr | Yes |
| | Test | 778 | 45.89% | 9.92 | -0.955% | -28.70%/yr | Yes |
| **trend_aligned+vol_contraction** | Train | 800 | 47.75% | 6.15 | -0.688% | -13.71%/yr | Yes |
| | Test | 517 | 49.52% | 6.59 | -0.614% | -13.61%/yr | Yes |
| **trend_aligned+sector_strong** | Train | 1,240 | 47.42% | 9.53 | -0.748% | -21.96%/yr | Yes |
| | Test | 793 | 45.90% | 10.11 | -0.922% | -28.25%/yr | Yes |
| **vol_contraction+sector_strong** | Train | 729 | 48.56% | 5.60 | -0.655% | -12.02%/yr | Yes |
| | Test | 442 | 47.74% | 5.64 | -0.744% | -14.03%/yr | Yes |
| **trend_aligned+vol_contraction+sector_strong** | Train | 655 | 37.71% | 5.03 | -0.824% | -14.12%/yr | Yes |
| | Test | 406 | 43.10% | 5.18 | -0.523% | -7.79%/yr | Yes |

All numbers read directly from `backtest_signal_filter_results.json`'s `selection.config` (train)
and `test_result` (test) fields per subset, not re-derived or hand-rounded beyond display
precision.

**No hit_rate anywhere in this table reaches 90%.** The highest hit_rate observed is
`vol_contraction`'s test value of 50.33% — essentially a coin flip, not a 90%-hit-rate strategy.
**Every `cagr_15slot` in the table is negative** — no subset, no split, turns the strategy
profitable.

## 3. Decision-Gate Verdict

**No reliable subset reaches the joint target — `hit_rate >= 90%` AND `trades_per_week >= 5` AND
`cagr_15slot > 0` — on train, on test, or on both.** Every one of the 8 subsets is `status =
target_not_met`, exactly like sub-project 2's uniform result. Adding these three signal tags,
individually or in any combination, **never turns the strategy profitable** in this train/test
split, and hit_rate never rises above roughly 50%.

There is, however, a real and worth-reporting pattern: **the loss shrinks as filters are combined**,
though it never crosses into profit. Read off the test-`cagr_15slot` column above:

- No filter: **-29.59%/yr**
- Best single tag (`vol_contraction`): -16.21%/yr
- Best pair (`trend_aligned+vol_contraction`): -13.61%/yr
- All three tags together: **-7.79%/yr** — the best result of all 8 subsets, on a real,
  non-trivial test sample (`n_trades=406`), not a low-n artifact.

This improvement is **driven almost entirely by `vol_contraction`**, not by all three tags equally.
Compare the subsets that omit `vol_contraction` — `trend_aligned` alone (-25.52%/yr test),
`sector_strong` alone (-28.70%/yr, actually the *worst* single-tag result, slightly worse than no
filter at all), and `trend_aligned+sector_strong` (-28.25%/yr, barely different from no filter) —
against every subset that includes `vol_contraction`, all of which land in the -7.79% to -16.21%/yr
range. `sector_strong` in particular adds little to no improvement on its own or paired with
`trend_aligned`, consistent with the sector-strength selectivity caveat in §5 below. The
"monotonic improvement with more tags" framing is only approximately true — it holds cleanly along
the paths that include `vol_contraction`, but adding `sector_strong` to a `vol_contraction`-based
subset (`vol_contraction+sector_strong`, -14.03%/yr) is very slightly *worse* than
`trend_aligned+vol_contraction` (-13.61%/yr) alone, before the full triple combination pulls ahead
to -7.79%/yr.

**Verdict: target not met. No subset is recommended for deployment.** Per the design doc's roadmap
and the same honesty standard applied in sub-project 2, this negative result is the condition for
scoping **Phase B** (a new candidate-generation engine, admitting stocks the current A/B/C/D
pattern engine does not currently flag at all) as the next sub-project. The 90%/5-per-week/
positive-return bar is not loosened after the fact to manufacture a "success" — filtering the
existing candidate pool, even along the most-improved axis found (`vol_contraction`), reduces but
does not eliminate the loss.

## 4. Best Available Subset Regardless of the Joint Target

Applying the design doc's stated fallback rule — among reliable subsets with
`trades_per_week >= 5`, the highest test `hit_rate` — all 8 subsets qualify on frequency, so the
comparison is over all 8:

**`vol_contraction` alone** has the highest test `hit_rate`: **50.33%** (test `n_trades=612`,
`trades_per_week=7.80`, `avg_pnl=-0.624%`, `cagr_15slot=-16.21%/yr`). This is the closest any
subset comes to the 90% hit-rate bar by this specific metric — still 40 points short, and still
losing money at roughly -16%/yr.

Note the tension this creates with §3: by hit_rate, `vol_contraction` alone is "best available";
by `cagr_15slot` (arguably the more decision-relevant number, since every subset's hit_rate is far
from the 90% bar regardless), the triple-tag subset
(`trend_aligned+vol_contraction+sector_strong`, test hit_rate 43.10%, `cagr_15slot=-7.79%/yr`) is
the least-bad result overall. Neither is a "found it" result — both are reported for completeness,
the same way sub-project 2 reported both its fallback-selected and best-CAGR-regardless
configurations without recommending either for deployment.

## 5. Limitations

- **Sector-strength selectivity is weaker than "top 30% of sectors" implies.** `sector_strong`
  fired `True` for 50.3% of all candidates (10,859/21,587) — well above what a naive reading of
  `top_frac=0.3` suggests. Root cause: `build_sector_returns_by_date` only has the ~915 tickers that
  actually produced candidates to group into sectors on any given date (not the full market), so on
  many dates few sectors clear the `min_sector_size=5` gate, and
  `compute_sector_strength`'s `cutoff_idx = max(0, int(len(ranked) * top_frac) - 1)` collapses
  toward including nearly everything when the qualifying-sector count is small. In practice,
  `sector_strong` behaves closer to "not in the worst sectors among a sparse comparison set" than
  "top 30% of real market sectors." This is consistent with §3's finding that `sector_strong`
  contributes little to no improvement on its own or in combination — it is a genuine limitation of
  this phase's sector-strength signal, not a bug, and is out of scope to fix here (the code
  producing this behavior was already reviewed and merged in Tasks 4/7 of this sub-project).
- **Sector data source deviates from the original design.** The design doc specified a KRX
  (`data.krx.co.kr`) sector-classification snapshot via the `MDCSTAT01501` endpoint. That endpoint
  was found to return HTTP 400 ("LOGOUT") in this environment — a session-flow block specific to
  this environment, not a code bug — so `backtest/krx_sector_snapshot.py` was revised to source the
  same code→sector mapping from Naver Finance's industry-group pages instead (same public function
  signature and return type, ~4,036 codes fetched live). This is a legitimate, already-reviewed
  substitution, noted here so a reader comparing this document against the design doc understands
  why the data source differs from what was originally specified.
- **Static sector classification**, one snapshot (2025-12-30) applied across the entire 2022-2026
  backtest window, not point-in-time history — a ticker that changed sectors mid-window is
  misclassified for part of it. Documented as an accepted simplification in the design doc.
- **Equal-weighted, universe-limited sector returns** — an approximation using only the ~915
  tickers that produced cached candidates, not KRX's published sector indices or a market-cap-
  weighted average across the true full market. This is the same limitation underlying the
  sector-strength selectivity caveat above.
- **Discrete tag-subset sweep, not a continuous search** — only the 8 combinations of 3 binary tags
  were tested (e.g. no continuous threshold sweep on the volatility-contraction percentile or the
  sector top-fraction), so a different threshold choice for any one signal might perform
  differently; the pattern in §3 (that `vol_contraction`-based subsets consistently outperform
  `sector_strong`-based ones) is unlikely to reverse, but the exact numbers could shift.
- **Added data-snooping exposure from testing 8 subsets × 432 cells** (3,456 configurations)
  against a single train/test split — mitigated, not eliminated, by the `n_trades >= 50`
  reliability rule (§2 confirms all 8 subsets clear this bar). A different train/test split
  boundary could shift the exact numbers, though not plausibly enough to turn any subset's
  `cagr_15slot` from double-digit-negative to positive.
- Inherits all of sub-project 1/2's stated limitations (flat-percentage target/stop, orderbook
  ask/bid and pattern-C blocks not modeled, single train/test split, flat-fee assumption) since this
  phase reuses that simulation machinery unmodified.

## 6. Next Step Recommendation

**No production code (`src/swing-scanner.src.js`) has been changed by this sub-project.** Every
change in this phase is confined to `backtest/` scripts and cached data files. Deployment of any
configuration found here is explicitly out of scope and remains a separate, later decision pending
the user's review — and given every subset is unprofitable, no configuration from this sweep is
recommended for deployment as-is.

Per the design doc's roadmap, the recommended next step is to **scope Phase B** — a new
candidate-generation engine admitting stocks the current A/B/C/D pattern engine does not currently
flag at all — as a separate follow-up sub-project, since Phase A's additive filters on the existing
candidate pool, even at their best (`vol_contraction`, or the full triple-tag combination), could
not lift hit_rate anywhere near 90% or turn the expected return positive. This is the trigger
condition the design doc defined for Phase B, and that decision is left to the user before any
further work begins.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-29 | Initial results write-up (Tasks 1-8 of the implementation plan) | Claude (same session) |

# swing-algo-momentum-sector-filter Design

> **Project**: showmoneyv2
> **Feature**: Swing Algo Enhancement Sub-project 6 — final deployment-config selection for
> momentum-continuation ("F모멘텀"), plus a sector-strength additive filter to modestly improve
> win rate without sacrificing frequency
> **Prior work**: [swing-algo-momentum-continuation.analysis.md](../../03-analysis/swing-algo-momentum-continuation.analysis.md)
> (sub-project 5 — built the F모멘텀 entry engine, confirmed 90% hit_rate is unreachable
> profitably via target/stop tuning alone; this document is the exploration log and design for
> what to do about that, ending in a concrete, honest deployment recommendation)
> **Date**: 2026-08-01

---

## 1. Context and Goal

Sub-project 5 closed with two viable but imperfect configurations on the same 4,197-candidate
momentum-continuation pool (`backtest_momentum_candidates.json`, unchanged, reused as-is):

- **Config A** (`target_pct=0.10, stop_pct=0.10`, symmetric 1:1, `hold_days=10`): reliable,
  healthy frequency, **strongly positive cagr** (+27.93% train / +29.80% test), but **hit_rate
  only ~44-45%** (roughly a coin flip per individual pick).
- **Config B** (`target_pct=0.03`, stop effectively removed, `hold_days=10`): the highest hit_rate
  found anywhere in this research line (**80.51% train / 81.19% test**), but stop being
  effectively absent leaves individual positions with **unbounded single-name downside risk**, and
  overall cagr is far lower (+4.60%/+7.70%) — a real operational risk, not just a cosmetic
  tradeoff, for a system that would actually recommend trades to a user.

The user chose **Config A** or the more marketable path forward, on the trader-level judgment that
an "80% hit rate" built on a de-facto absent stop-loss is not a responsible design, even though its
headline hit_rate looks better. This document designs the final refinement on top of Config A:
**can win rate be improved further without destroying Config A's frequency or its reliance on a
real, bounded stop?**

### 1.1 What was already tried and ruled out (this session, exploratory, not separately committed)

Before landing on the recommendation below, the following were tested empirically against the
existing momentum-continuation pool and existing shared infrastructure — reported here for the
record, since the eventual analysis document must not omit negative results:

- **Wider/narrower target-stop grids** (target 0.5%-30%, stop 1%-10%): hit_rate and `cagr_15slot`
  are monotonically opposed; no cell anywhere achieves both `hit_rate >= 90%` and `cagr > 0`
  (already committed in sub-project 5's analysis doc, Sections 8-9).
- **Tightened entry-rule thresholds** (RS top 2%, breakout margin +2%, trigger-day `rvol >= 2.0`,
  `hold_days=5`): candidate pool collapsed 4,197 → 697; `trades_per_week` collapsed to ~1.9-2.65
  (well under the 5/week floor); train/test hit_rate and cagr diverged sharply (80.32%/-0.14% train
  vs 75.00%/-14.25% test) — a sign of instability on the smaller sample, not a usable result.
- **Breakeven-ratchet exit** (move stop to entry+cost once price rises past a small trigger): at
  `hold_days=5`, breakeven-or-better rate capped near 44-45% (55% of trades fail immediately,
  before any exit mechanism can help). At `hold_days=10` with a very wide initial stop (15-20%),
  breakeven-or-better rate did reach 90%+ — but manual inspection of the underlying trades showed
  the **median trade result was exactly 0%** and the strongly positive cagr was driven by a
  handful of extreme outlier winners (one single trade at +260%); the wide stop also meant a real
  minority of trades absorbed the full -15% to -20% loss. This "90%" was judged misleading (not
  representative of a typical trade) and rejected.
- **Weekly portfolio/basket framing** (redefine success as "the week's average return is
  positive/+3%", not a per-stock outcome): only 53-57% of weeks were net positive on Config A's
  trades, and just 28-35% of weeks averaged +3% — momentum strategies are known to have low
  diversification benefit within a single time window (correlated market-regime risk, cf.
  "momentum crashes" in the trading literature), so basket framing did not meaningfully close the
  gap either.
- **Market-regime gate** (`regime_gate=True`, existing `backtest_regime_lookup.json`): a modest
  hit_rate lift on Config A (44.32%→48.19% train, 45.32%→50.52% test) but train
  `trades_per_week` fell to 3.40 (below the 5/week floor) — same pattern already observed for
  E반등 in sub-project 4; this coarse a filter costs more frequency than it buys in hit_rate.
- **A fresh entry-signal hypothesis (low-volatility-accumulation)**, the other alternative named
  in the original Phase B design doc: a quick 200-ticker gut-check (vol-contraction + above-SMA60
  context, reusing `candidate_signals.compute_vol_contraction` unmodified) found a **70.5%**
  forward 3%-touch rate — *lower* than momentum-continuation's own 80.51% ceiling — and a
  **negative median** 10-day forward return, an unpromising sign for expected value. Not pursued
  further.
- **Volume confirmation at moderate thresholds** (`rvol >= 1.3` or `>= 1.5`) on top of Config A:
  no hit_rate improvement at either threshold, and `rvol >= 1.5` cut test `cagr_15slot` from
  +29.80% to essentially 0% (+1.23%). Ruled out.

### 1.2 What worked, modestly

**Sector-relative-strength filtering** (`sector_strong`, computed by `candidate_signals.py`'s
existing, unmodified `tag_candidates()` — the exact function built in sub-project 3 Phase A,
reusing the already-committed `backtest_sector_map.json`) applied as a `required_tags` filter on
Config A:

| Filter | Pool | Train (n / hit_rate / tpw / cagr) | Test (n / hit_rate / tpw / cagr) |
|---|---:|---|---|
| None (baseline) | 4,197 | 1,038 / 44.32% / 7.98 / +27.93% | 854 / 45.32% / 10.89 / +29.80% |
| `sector_strong` | 2,638 | 781 / 45.33% / 6.00 / +14.30% | 643 / **49.14%** / 8.20 / +27.09% |

This is the only lever tested that raised hit_rate (test: +3.8pp) while `trades_per_week` stayed
comfortably above the 5/week floor on both splits. It is not dramatic, and it is not free: train
`cagr_15slot` drops by roughly half (27.93%→14.30%) while test cagr holds up (29.80%→27.09%) — a
train/test divergence that must be reported honestly, not smoothed over, in the eventual analysis
document.

## 2. Decision

**Adopt Config A (`target_pct=0.10, stop_pct=0.10, hold_days=10`) as the deployment baseline**,
with `sector_strong` as an optional additive filter, and **do not continue chasing 90% hit_rate**
— it has now been shown unreachable, profitably, across every lever this research line has
infrastructure for (target/stop shape, entry selectivity, exit mechanism, portfolio framing,
regime timing, and one alternative entry hypothesis). Momentum-continuation should be reported
honestly as a **return-focused strategy with a realistic ~44-49% per-pick win rate**, not a
high-hit-rate strategy.

This sub-project's deliverable is narrow and almost entirely execution + analysis, not new code:

1. Reproduce the `sector_strong` tagging on the committed momentum-continuation pool (calling
   `candidate_signals.build_sector_returns_by_date`/`tag_candidates`, both unmodified) and save the
   tag lookup as a committed artifact (the exploratory numbers above were computed ad hoc this
   session and are not yet backed by a committed, reproducible file).
2. Re-run `target_stop_grid_search.run_one_config` (unmodified) at the fixed Config A parameters,
   both without and with the `sector_strong` filter, on properly-saved output.
3. Write the final analysis document comparing both, restating every negative result from Section
   1.1 for the historical record (this document is the design, not the analysis — the analysis
   document must independently reproduce and fact-check every number, not cite this document's
   ad hoc figures as authoritative).

**No new source files.** Every function used (`tag_candidates`, `build_sector_returns_by_date`,
`run_one_config`) already exists, is already unmodified-by-design in this research line, and needs
no new tests — this sub-project produces no new library code, only data artifacts and a report.

## 3. Data Flow

```
backtest_momentum_candidates.json (sub-project 5, unchanged)
  + backtest_sector_map.json (sub-project 3 Phase A, unchanged)
  + per-ticker OHLCV (yahoo_cache disk cache, no new network fetch)
  -> candidate_signals.tag_candidates() [unmodified]
  -> backtest_momentum_sector_tags.json (new committed artifact)

backtest_momentum_candidates.json + backtest_momentum_sector_tags.json
  -> target_stop_grid_search.run_one_config() [unmodified], target_pct=0.10/stop_pct=0.10,
     once with required_tags=frozenset(), once with required_tags={"sector_strong"}
  -> backtest_momentum_sectorfilter_results.json (new committed artifact)

-> docs/03-analysis/swing-algo-momentum-sector-filter.analysis.md (new)
```

## 4. Error Handling

Identical to every prior sub-project's convention: a ticker/date `tag_candidates` can't locate
fails closed (`sector_strong=False`), not raised; no new failure modes are introduced since no new
computation logic is written.

## 5. Testing

No new source code, so no new unit tests. The one thing worth double-checking during execution
(not a formal test, a sanity check to run and report): confirm the `sector_strong` count and
filtered train/test `n_trades`/`hit_rate`/`cagr_15slot` figures in the committed output JSON match
what's reported in Section 1.2 above to within rounding — if they don't match, investigate before
writing the analysis document (the Section 1.2 numbers were computed ad hoc this session and must
be treated as a hypothesis to verify, not a foregone conclusion, per this project's no-invented-
numbers convention).

## 6. Limitations

- **Train/test cagr divergence for the `sector_strong`-filtered config** (14.30% vs 27.09%) is
  larger than baseline Config A's own train/test divergence (27.93% vs 29.80%) — worth flagging
  explicitly as a stability concern in the analysis document, not glossed over just because the
  test-side number looks good.
- **Single train/test split**, same acknowledged limitation as every prior sub-project.
- **This is a settled-for-realistic outcome, not a solved problem**: hit_rate of ~45-49% is
  reported as the honest, final answer to "can this reach 90%" — the analysis document must state
  plainly that it cannot, rather than reframing the sector filter's modest gain as if it closes
  the gap.
- Every negative result in Section 1.1 was produced via ad hoc, uncommitted exploration this
  session (no saved JSON, no git history) — the analysis document must independently regenerate
  and commit whichever of those figures it chooses to cite, rather than asserting them from memory
  of this design document's prose.

No production code (`src/swing-scanner.src.js`) has been changed by this sub-project — as with
every prior sub-project, that remains a separate, later decision.

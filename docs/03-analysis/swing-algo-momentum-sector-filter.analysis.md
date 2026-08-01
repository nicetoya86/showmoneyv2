# swing-algo-momentum-sector-filter Analysis Report

> **Analysis Type**: Empirical Result Report (PDCA Do → Check)
>
> **Project**: showmoneyv2
> **Feature**: swing-algo-momentum-sector-filter — Swing Algo Enhancement Sub-project 6 (final
> deployment-config selection for momentum-continuation "F모멘텀", plus a `sector_strong`
> sector-relative-strength additive filter tested as a modest win-rate lever)
> **Design Doc**: [2026-08-01-swing-algo-momentum-sector-filter-design.md](../superpowers/specs/2026-08-01-swing-algo-momentum-sector-filter-design.md)
> **Implementation Plan**: [2026-08-01-swing-algo-momentum-sector-filter.md](../superpowers/plans/2026-08-01-swing-algo-momentum-sector-filter.md)
> **Date**: 2026-08-01
> **Prior work**: [swing-algo-momentum-continuation.analysis.md](swing-algo-momentum-continuation.analysis.md)
> (sub-project 5 — built the F모멘텀 entry engine on the 4,197-candidate momentum-continuation pool;
> confirmed empirically, across two follow-up grids covering `target_pct` 0.5%-30% and `stop_pct`
> 1%-10%, that `hit_rate >= 90%` is unreachable profitably via target/stop tuning alone; landed on
> two viable configurations — **Config A** (`target_pct=0.10, stop_pct=0.10, hold_days=10`:
> reliable, +27.93%/+29.80% train/test `cagr_15slot`, but only ~44-45% hit_rate) and **Config B**
> (`target_pct=0.03`, stop effectively removed: 80.51%/81.19% hit_rate, but unbounded single-name
> downside risk from the de-facto absent stop) — this sub-project picks up from that fork)

---

## 1. Method Summary

This sub-project makes **no changes to the momentum-continuation entry rule and no changes to
`backtest/target_stop_grid_search.py`**. Every number below comes from re-running that module's
existing, unmodified `run_one_config` (and other already-existing `backtest/` functions) against
the already-committed `backtest_momentum_candidates.json` pool (4,197 candidates, unchanged from
sub-project 5), fixed at Config A's parameters (`target_pct=0.10, stop_pct=0.10, min_score=60,
regime_gate=False, exclude_d_box=False, hold_days=10`).

The one additive piece of logic exercised is `sector_strong`, a `required_tags` filter computed by
`candidate_signals.py`'s existing, unmodified `tag_candidates()`/`compute_sector_strength()`
(originally built in sub-project 3 Phase A), reusing the already-committed `backtest_sector_map.json`.
No new source file, no new function, and no new library code were written for this sub-project —
see the design doc's §2 "Decision" for the full rationale of why this is execution + analysis only,
which is not re-derived here.

Train/test split is unchanged from every prior sub-project: train `2022-01-01`..`2024-06-30`, test
`2024-07-01`..`2026-01-01`, with the joint decision-gate rule `hit_rate >= 90%` AND
`trades_per_week >= 5` AND `cagr_15slot > 0` on both splits, and `n_trades >= 50` on both splits
required before any pass/fail conclusion is trusted.

This document also restates, with real committed numbers, every alternative that was explored and
ruled out this session (design doc §1.1) — those explorations are reproduced here as committed
JSON artifacts rather than cited from the design doc's ad hoc figures, per the design doc's own
§5 sanity-check requirement.

## 2. Config A vs. `sector_strong`-Filtered Comparison

Source: `backtest_momentum_sectorfilter_results.json`. `sector_strong` tag counts sourced from
`backtest_momentum_sector_tags.json`: of the 4,197 candidates in the pool, **2,638 (62.85%)** are
tagged `sector_strong=true`.

| Filter | Split | n_trades | n≥50 (reliable)? | hit_rate | trades_per_week | cagr_15slot |
|---|---|---:|:---:|---:|---:|---:|
| None (baseline Config A) | Train | 1,038 | Yes | 44.32% | 7.98 | +27.93% |
| None (baseline Config A) | Test  | 854   | Yes | 45.32% | 10.89 | +29.80% |
| `sector_strong` | Train | 781 | Yes | 45.33% | 6.00 | +14.30% |
| `sector_strong` | Test  | 643 | Yes | 49.14% | 8.20 | +27.09% |

(All four `n_trades` figures clear the `n_trades >= 50` reliability bar by more than an order of
magnitude, and all four `trades_per_week` figures clear the `>= 5` frequency floor — the
`sector_strong` filter costs roughly 25% of Config A's trade count but does not push frequency
anywhere near the floor.)

Net effect of the filter: hit_rate rises modestly (+1.01pp train, 44.32%→45.33%; +3.83pp test,
45.32%→49.14%), while `cagr_15slot` drops sharply on train (+27.93%→+14.30%, a **48.8% relative
cut**, -13.63pp) and only mildly on test (+29.80%→+27.09%, a 9.1% relative cut, -2.71pp). This
train/test divergence is discussed in full in §5 (Limitations) — it is the central tension this
sub-project has to resolve.

A trader's honest read: a 1-4 percentage-point hit_rate bump that costs roughly half your train-side
CAGR is not obviously worth it on its own — this is the kind of filter that looks good in a single
backtest table and needs to survive more than one split before anyone should size real capital
around it.

## 3. Ruled-Out Explorations

### 3.1 Entry-tightening (RS top 2%, breakout margin +2%, trigger `rvol >= 2.0`, `hold_days=5`)

Source: `backtest_momentum_entrytighten_explore.json`. Tightening the entry rule collapsed the
candidate pool from 4,197 to **697**. Train: `n_trades=249`, `hit_rate=80.32%`,
`trades_per_week=1.91`, `cagr_15slot=-0.14%`. Test: `n_trades=208`, `hit_rate=75.00%`,
`trades_per_week=2.65`, `cagr_15slot=-14.25%`.

Both splits' `trades_per_week` are well under the `5/week` floor (1.91 train, 2.65 test), and the
train/test hit_rate gap (80.32% vs 75.00%) and especially the cagr gap (-0.14% vs -14.25%) show
instability consistent with a shrunken, noisier sample. This does not change the sub-project's
conclusion — a tighter entry buys headline hit_rate at the cost of the frequency floor and result
stability, the same trade-off pattern E반등 hit repeatedly in sub-projects 3-4.

### 3.2 Breakeven-ratchet exit at `hold_days=5`

Source: `backtest_momentum_breakeven_hold5.json`. Moving the stop to breakeven once price rises
1.5% past entry, on the original `hold_days=5` pool: train `n_trades=1,012`,
`breakeven_rate=44.47%`, `trades_per_week=7.78`, `avg_pnl=0.15%`, `cagr_15slot=+3.14%`. Test:
`n_trades=809`, `breakeven_rate=44.99%`, `trades_per_week=10.32`, `avg_pnl=0.52%`,
`cagr_15slot=+19.38%`.

Train result_counts show why the ratchet can't help much at this hold: **558 of 1,012 trades
(55.1%)** hit the initial stop outright (`initial_stop`), before the ratchet mechanism ever had a
chance to activate — the breakeven-or-better rate is capped near 44-45% because more than half of
trades fail immediately. Does not change the conclusion: the exit mechanism cannot rescue a hold
window too short for the ratchet to matter.

### 3.3 Breakeven-ratchet exit at `hold_days=10` with a wide (20%) initial stop — the misleading "90%" result

Source: `backtest_momentum_breakeven_hold10_wide.json` (train split only). Headline
`breakeven_rate=94.44%` on `n_trades=1,062` — on its face, comfortably above the 90% bar. But the
`mean_pnl` (1.72%) and `median_pnl` (**exactly 0.00%**) diverge sharply: the median trade earns
nothing at all, and the high mean is pulled almost entirely by a handful of extreme outliers.
`top_10_pnls` confirms this: nine of the ten best trades cluster in the +47.8% to +67.6% range, and
the single best trade returns **+260.33%** (`2.603263157894737`) — a single position driving a
large share of the aggregate `cagr_15slot=85.21%`. Meanwhile `bottom_10_pnls` shows the wide 20%
stop's real cost: all ten worst trades lose exactly **-20.2%** (the stop level plus round-trip
cost), i.e. a real minority of trades absorb the full downside the wide stop was designed to avoid.

**Why this was rejected**: a median trade result of exactly 0% is not a "90% hit rate" in any
useful sense — it means the typical trade neither meaningfully wins nor loses, and the impressive
mean/cagr is a small number of outlier winners doing all the work, a classic sign of an unreliable,
non-representative headline figure rather than a real edge. A trader relying on this table alone
would badly overestimate what a typical trade in this configuration actually looks like.

### 3.4 Weekly portfolio/basket framing

Source: `backtest_momentum_weekly_basket.json`. Redefining success as "the week's average trade
return is positive / >= +3%" on Config A's own trades (target=stop=10%, hold=10): train — 107
weeks, average basket size 9.70 trades/week, **57.01%** of weeks net positive, only **34.58%** of
weeks averaged >= +3%. Test — 79 weeks, average basket size 10.81 trades/week, **53.16%** of weeks
net positive, only **27.85%** of weeks averaged >= +3%.

Basket framing does not close the gap to 90% on either measure, and the positive-week rate is
barely better than a coin flip. This is consistent with momentum strategies' known low
diversification benefit within a single time window (correlated market-regime exposure — the
"momentum crashes" phenomenon documented in the trading literature) — a basket of momentum picks in
the same week tends to win or lose together, so averaging across the basket doesn't manufacture a
high hit rate the way it might for uncorrelated picks.

### 3.5 Market-regime gate (both Config A and Config B)

Source: `backtest_momentum_regime_gate.json`.

- **Config A** (`target=stop=10%`): regime gate lifts hit_rate modestly (train 44.32%→48.19%, test
  45.32%→50.52%(1)) but train `trades_per_week` falls to **3.40** (442 trades over the train
  window), below the 5/week floor — the gate fails the frequency requirement on the train split
  even though it clears the hit_rate direction and the test-side frequency (6.13/week).
  ((1) exact JSON value: `hit_rate=0.5051975051975052` → 50.52%.)
- **Config B** (`target=3%, stop` effectively removed): regime gate barely moves hit_rate (train
  80.51%→80.61%, test 81.19%→82.04%) while train `trades_per_week` falls to **3.01** — same
  frequency-floor failure pattern, and no meaningful hit_rate gain to offset it.

Same pattern already seen for E반등 in sub-project 4: a coarse timing filter costs more frequency
than it buys in hit_rate. Does not change the conclusion for either config.

### 3.6 Low-volatility-accumulation gut-check (alternative entry hypothesis)

Source: `backtest_momentum_lowvol_and_volume_explore.json` (`low_vol_accumulation` key). A 200-ticker
sample using the existing, unmodified `candidate_signals.compute_vol_contraction` plus an
above-SMA60 filter produced **17,279 qualifying samples**, a **70.50%** forward 3%-touch rate over
10 days, average 10-day forward return **+1.28%**, but **median 10-day forward return -0.55%** (a
negative median despite a positive mean — the same "mean pulled up by outliers, typical case is a
loser" shape flagged in §3.3).

70.50% is *below* momentum-continuation's own 80.51% Config-B ceiling, and the negative median is
an unpromising expected-value sign. Not pursued as a replacement entry hypothesis.

### 3.7 Moderate volume (relative-volume) filters on Config A

Source: `backtest_momentum_lowvol_and_volume_explore.json` (`volume_filters` key).

- `rvol >= 1.3` (pool 3,705): train `n=993`, `hit_rate=44.41%`, `cagr_15slot=+22.22%`; test `n=828`,
  `hit_rate=45.17%`, `cagr_15slot=+24.50%`.
- `rvol >= 1.5` (pool 3,353): train `n=963`, `hit_rate=44.55%`, `cagr_15slot=+9.61%`; test `n=792`,
  `hit_rate=44.57%`, `cagr_15slot=+1.23%`.

Neither threshold improves hit_rate over baseline Config A (44.32%/45.32%) — both sit within
±0.3pp of baseline — while `rvol >= 1.5` cuts test `cagr_15slot` from +29.80% to essentially flat
(+1.23%). Ruled out: volume confirmation adds cost without a hit_rate benefit.

## 4. Decision-Gate Verdict

Applying the three-way outcome framework used by every prior sub-project (target-met /
target-not-met-but-reliable / underpowered) to the `sector_strong`-filtered Config A
(`backtest_momentum_sectorfilter_results.json`, the sub-project's main deliverable):

- **Not target-met**: `hit_rate` is 45.33% (train) / 49.14% (test) — roughly 41-45 percentage
  points short of the 90% bar on both splits. No configuration examined anywhere in this
  sub-project or its predecessor (sub-project 5's widened and small-target grids, both cited in
  the Prior-work summary above) reaches `hit_rate >= 90%` while remaining profitable.
- **Reliable, not underpowered**: `n_trades = 781` (train) and `n_trades = 643` (test) both clear
  the `n_trades >= 50` statistical-reliability bar by more than an order of magnitude.
  `trades_per_week = 6.00` (train) and `8.20` (test) both clear the `>= 5` frequency floor.
  `cagr_15slot` is positive on both splits (+14.30% train, +27.09% test). Every leg of the
  three-way framework except the 90% hit_rate bar itself is cleared on both splits — this is a
  fully reliable, decisively negative-on-hit_rate-only result, not a small-sample fluke.

**Verdict: target-not-met, but reliably so, and unchanged from sub-project 5's conclusion.** The
`sector_strong` filter is a real, reproducible, modest hit_rate lift — not noise — but it does not
come close to closing the 45-point gap to 90%, and (per §2) it costs roughly half of Config A's
train-side `cagr_15slot` to get there. Combined with every ruled-out lever in §3 (entry tightening,
both breakeven variants, weekly framing, regime gating, an alternative entry hypothesis, and volume
filters), this sub-project confirms sub-project 5's finding across every remaining lever this
research line has infrastructure for: **90% hit_rate is not achievable for momentum-continuation,
profitably, by any tested mechanism.**

## 5. Limitations

- **Train/test `cagr_15slot` divergence for the `sector_strong` filter is a real, named
  instability, not glossed over**: the filtered config's train cagr drops by **48.8%** relative
  (+27.93%→+14.30%, a -13.63pp absolute drop) while its test cagr only drops **9.1%** relative
  (+29.80%→+27.09%, -2.71pp). Unfiltered Config A's own train/test cagr are close together
  (+27.93% vs +29.80%, a +6.7% relative move in the *same* direction); the `sector_strong` filter
  introduces a much larger and oppositely-signed relative swing between splits — the kind of
  divergence that should raise a flag about whether the train-side economics or the test-side
  economics is the more representative number, not be resolved by assuming the better-looking
  (test) number is the true one.
- **Single train/test split**, the same acknowledged limitation as every prior sub-project in this
  line — neither the baseline nor the `sector_strong`-filtered comparison has been validated across
  multiple splits or a walk-forward scheme.
- **This is a settled-for-realistic outcome, not a solved problem.** A ~44-49% per-pick hit_rate is
  reported as the honest, final answer to "can momentum-continuation reach 90% hit_rate" — it
  cannot, within the exit mechanisms and filters this research line has tested. The `sector_strong`
  filter's modest gain does not close that gap and should not be read as if it does.
- Every ruled-out exploration in §3 was originally produced ad hoc, uncommitted, during the design
  session; the figures in this document are the independently re-run, committed reproductions
  (`backtest_momentum_entrytighten_explore.json`, `backtest_momentum_breakeven_hold5.json`,
  `backtest_momentum_breakeven_hold10_wide.json`, `backtest_momentum_weekly_basket.json`,
  `backtest_momentum_regime_gate.json`, `backtest_momentum_lowvol_and_volume_explore.json`), not a
  restatement of the design doc's earlier ad hoc numbers. They match the design doc's prose to
  within rounding on every figure checked (see §3 above).

## 6. Final Recommendation

**Production candidate: Config A, unfiltered** (`target_pct=0.10, stop_pct=0.10, min_score=60,
regime_gate=False, exclude_d_box=False, hold_days=10`) — the deployment baseline, reliable and
profitable on both splits (+27.93%/+29.80% cagr, 44.32%/45.32% hit_rate, both well above the
frequency floor).

The `sector_strong` filter should be treated as an **optional, secondary variant**, not a
replacement for the baseline default: its hit_rate gain is real but modest (+1.0pp train, +3.8pp
test) and it costs roughly a third of Config A's trade count (1,038→781 train, 854→643 test) and
about half of train-side `cagr_15slot` (+27.93%→+14.30%) for that gain. The test-side cagr holds up
well (+29.80%→+27.09%), but per §5, the size of the train/test divergence itself is a stability
flag under a single train/test split — not a result that should be trusted more than the unfiltered
baseline just because its test-side number looks fine. Users who specifically value a few extra
points of per-pick hit_rate over frequency and full CAGR robustness may reasonably opt into
`sector_strong`; it should not become the unconditional default given the honesty standard this
research line has held itself to.

**No further hit-rate-chasing is recommended for momentum-continuation.** Between sub-project 5's
two follow-up grids (target 0.5%-30%, stop 1%-10%, both reported in the Prior-work summary above)
and this sub-project's seven additional ruled-out levers (§3), the tested space now covers
target/stop shape, entry selectivity, exit mechanism (ratchet), portfolio framing, regime timing, a
volume-based lever, and one alternative entry hypothesis. None reach `hit_rate >= 90%` profitably.
Momentum-continuation should be reported and used as a **return-focused strategy with a realistic
~44-49% per-pick win rate**, not reframed as a high-hit-rate strategy — consistent with the design
doc's decision.

---

No production code (`src/swing-scanner.src.js`) has been changed by this sub-project — as with
every prior sub-project, that remains a separate, later decision.

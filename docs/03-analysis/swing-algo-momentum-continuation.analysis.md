# swing-algo-momentum-continuation Analysis Report

> **Analysis Type**: Empirical Result Report (PDCA Do → Check)
>
> **Project**: showmoneyv2
> **Feature**: swing-algo-momentum-continuation — Swing Algo Enhancement Sub-project 5 ("F모멘텀")
> (momentum-continuation candidate engine — RS leadership + new high + trend alignment, the first
> empirical test of this hypothesis in this codebase)
> **Design Doc**: [2026-08-01-swing-algo-momentum-continuation-design.md](../superpowers/specs/2026-08-01-swing-algo-momentum-continuation-design.md)
> **Implementation Plan**: [2026-08-01-swing-algo-momentum-continuation.md](../superpowers/plans/2026-08-01-swing-algo-momentum-continuation.md)
> **Date**: 2026-08-01
> **Prior work**: [swing-algo-oversold-bounce-hitrate.analysis.md](swing-algo-oversold-bounce-hitrate.analysis.md)
> (sub-project 4 — E반등/oversold-bounce with all 5 trader-diagnosed hit-rate levers applied still
> failed the joint decision gate on every stage and pool; the `trades_per_week >= 5` frequency floor
> was never remotely approached across 3,481 evaluated configurations, max observed 0.60/week — that
> structural dead end triggered the pivot to a new candidate-generation hypothesis, momentum
> continuation, pursued here)

---

## 1. Method Summary

Per the design doc's §2 Entry Rule, all four conditions are evaluated at trigger day `idx`, AND'd
together, on top of the reused liquidity/quality base filters:

1. **Relative-strength leadership** — the ticker's own trailing-60-trading-day return ranks in the
   top 10% of the same day's cross-sectional distribution of trailing-60-day returns across the
   full 959-ticker operating universe.
2. **New high** — `close[idx] >= max(high[idx-60..idx-1])` (the trigger day's close at or above the
   *prior* 60 trading days' high, excluding today).
3. **Trend alignment** — `close[idx] > sma50[idx] > sma200[idx]`, the classic "stage 2 uptrend"
   ordering.
4. **Base filters** — the existing liquidity/quality gates reused unmodified (`MIN_PRICE`,
   `MIN_TURNOVER_ALGO`, no negative DART disclosure, no large net-sell supply flag, `rvol >= 1.0`).
   Note: `evaluate_candidate()`'s base filters (`backtest/swing_signal_engine.py` lines 112-121)
   also include an `rsi14 < 40` exclusion gate; that gate is deliberately **not** reused here — a
   candidate already sitting at a 60-day new high with `close > sma50 > sma200` is structurally
   almost never also oversold (`rsi14 < 40`), so the gate would rarely fire on this pattern's
   candidates anyway. It is omitted rather than redundant-but-harmless, and this document states
   that plainly instead of implying strict filter parity with `evaluate_candidate()`.

`entry = close[idx]`, `entry_idx = idx+1`, `hold_days = 10` — a single-day trigger with no
multi-day confirmation. Full rationale, formulas, and parameter values are in the design doc
(§2–§3); they are not re-derived here.

Train/test split, universe, and decision-gate rules are unchanged from every prior sub-project in
this line: 959-ticker operating universe, `2022-01-01`..`2026-01-01` scan range, train
(`2022-01-01`..`2024-06-30`) / test (`2024-07-01`..`2026-01-01`) split, and
`target_stop_grid_search.run_grid_search`'s unmodified decision/reliability rules (`hit_rate >=
90%` AND `trades_per_week >= 5` AND `cagr_15slot > 0` on both splits; `n_trades >= 50` on both
splits before any pass/fail conclusion is drawn).

## 2. Candidate Count and Skipped Tickers

The scan over the full 959-ticker operating universe (`backtest_momentum_candidates.json`)
produced **4,197 candidates** with **4 skipped tickers** — the same four 404s from Yahoo Finance
seen in every prior sub-project's scan, not a new issue:

- `042670.KS`
- `450140.KS`
- `019440.KS`
- `448830.KQ`

## 3. Train vs. Test Result

The 432-cell grid search (`backtest/target_stop_grid_search.py`'s unmodified `run_grid_search`,
6 `target_pct` × 6 `stop_pct` × 3 `min_score` × 2 `regime_gate` × 2 `exclude_d_box`) over the
4,197-candidate pool produced `selection.status = "target_not_met"` — no cell reached the joint
`hit_rate >= 90%` / `trades_per_week >= 5` bar. Since no cell qualified outright, the fallback rule
selected, among cells that at least cleared the `trades_per_week >= 5` frequency floor, the one
with the highest train `hit_rate` (tie-broken by `cagr_15slot`):

**Selected train config**: `target_pct=0.03, stop_pct=0.04, min_score=60, regime_gate=false,
exclude_d_box=false`

| Split | n_trades | Reliable (n≥50)? | hit_rate | trades_per_week | avg_pnl | cagr_15slot |
|-------|---------:|:-----------------:|---------:|-----------------:|--------:|-------------:|
| Train (2022-01-01..2024-06-30) | 921 | **Yes** | 48.75% | 7.077 | -0.75% | -20.42% |
| Test (2024-07-01..2026-01-01)  | 724 | **Yes** | 50.00% | 9.231 | -0.69% | -20.28% |

Both `n_trades` figures (921 train, 724 test) clear the `n_trades >= 50` reliability bar by more
than an order of magnitude, and both `trades_per_week` figures (7.077 train, 9.231 test) clear the
`>= 5` frequency floor — a first for this research line (see §5).

## 4. Decision-Gate Verdict

Applying the three-way outcome framework (target-met / target-not-met-but-reliable /
underpowered):

- **Not target-met**: `hit_rate` is 48.75% (train) / 50.00% (test) — essentially a coin flip,
  roughly 40 percentage points short of the 90% bar on both splits. `cagr_15slot` is deeply
  negative on both splits (-20.42% train, -20.28% test): the strategy loses money over a rolling
  15-slot portfolio simulation at this configuration.
- **But reliable, not underpowered**: `n_trades = 921` (train) and `n_trades = 724` (test) are both
  far above the `n_trades >= 50` statistical-reliability bar, and `trades_per_week = 7.077` (train)
  / `9.231` (test) both clear the `>= 5` frequency floor. This is the **first result in the entire
  research line** — across sub-projects 3 and 4's dozens of E반등 configurations and thousands of
  grid cells — where both the sample-size gate and the frequency floor are cleared on both splits
  simultaneously (E반등's maximum ever observed `trades_per_week` was 0.60, two orders of magnitude
  below the bar).

**Verdict: target-not-met, and reliably so.** This is not an inconclusive or underpowered result —
it is a statistically decisive negative result on hit_rate and returns. The strategy trades often
enough and with enough samples to trust the numbers; the numbers say this specific
parameterization does not work.

## 5. Why This Differs From E반등 Structurally

Momentum-continuation's entry conditions (RS-percentile leadership + new high + SMA50/SMA200
alignment) are evidently far more common in this universe than E반등's oversold-recovery
conditions: this scan produced **4,197 candidates**, roughly **~33-35x** more than any E반등 pool in
sub-projects 3-4 (which ranged **119-127** candidates before any tag/confirmation filtering). That
volume of candidates is precisely why this hypothesis produced a statistically decisive result on
its first attempt — a single hand-specified rule, no tuning, no additive levers — where E반등 could
never get past the frequency floor across two full sub-projects of iteration.

## 6. Limitations

Restating the design doc's §7 limitations, not re-deriving them:

- **Single hand-specified rule, not swept/tuned** — the 60-day RS/new-high lookback, the top-10%
  cutoff, and the 50/200-day SMA alignment periods are fixed by trader-review judgment, not
  grid-searched. A negative result here rules out this specific rule, not the momentum-continuation
  concept in general.
- **Single train/test split**, same acknowledged limitation as every prior sub-project.
- Inherits sub-project 1/2's limitations via the reused, unmodified simulation primitives: flat-fee
  assumption, orderbook ask/bid and pattern-C block not modeled, TOSS-LIVEPRICE using next-day-open
  as a live-price proxy.
- **Cross-sectional computation cost** — `build_universe_return_lookup` is `O(tickers × days)`
  once, noticeably slower than any prior additive signal's per-ticker-only cost, though still a
  one-time precompute, not per-grid-cell.
- `hold_days = 10` is a one-time judgment call, not swept; a negative result should not be read as
  ruling out momentum-continuation at other holding periods.
- **Static, survivors-only universe** (new to this sub-project) — the 959-ticker operating universe
  is a fixed, current-day list, and this sub-project's relative-strength percentile is the first
  cross-sectional signal in this research line: it is computed against tickers currently in that
  list only, so delisted/renamed tickers are absent from the comparison set. The bias direction
  cannot flip the verdict, though — a survivors-only universe raises the top-10% cutoff and selects
  for stronger names, i.e. it flatters the strategy if anything, and the result (target-not-met,
  reliably) is still decisively negative despite that.

Because this sub-project's result is **reliable** (not underpowered), these limitations are about
parameter choice, not sample size — a genuinely different situation from every E반등 analysis, where
small samples meant most limitations were about whether the numbers could be trusted at all. Here
the numbers can be trusted; the question is only which rule/parameterization was tested.

## 7. Next Step Recommendation

Three structural facts point to where the next iteration should focus, all drawn directly from the
same grid search result:

1. The selected cell's risk/reward shape is inverted: `target_pct=0.03` (3%) is *tighter* than
   `stop_pct=0.04` (4%) — the strategy is set up to lose more on a stop-out than it gains on a
   target hit, before even considering hit_rate. This looks like a backwards parameterization for
   a momentum-continuation bet at first glance — but the full grid (next point) shows the actual
   lever is a *wider target*, not a tighter stop: every `stop_pct` tighter than the grid's own
   maximum (0.04) produced zero positive-`cagr_15slot` cells, at any `target_pct`.
2. Checking all 432 train cells directly (not just the reported fallback) confirms this is not a
   one-off: exactly **6 cells** have `cagr_15slot > 0`, and every one of them sits at
   `target_pct=0.10` **and** `stop_pct=0.04` simultaneously — both the maximum value in their
   respective grids (`GRID_TARGET_PCT = [0.03, 0.04, 0.05, 0.06, 0.08, 0.10]`, `GRID_STOP_PCT =
   [0.01, 0.015, 0.02, 0.025, 0.03, 0.04]`, both defined in `backtest/target_stop_grid_search.py`).
   The 6 cells differ only in `min_score` (60/90/110) and `exclude_d_box` (false/true); the other 5
   `stop_pct` values tested (0.01, 0.015, 0.02, 0.025, 0.03) produce no positive-`cagr_15slot` cell
   at *any* `target_pct`, including at `target_pct=0.10`. So the pattern spans **both grid axes at
   once**, not `target_pct` alone — a follow-up that only widens `target_pct` past 0.10 while
   leaving `stop_pct` clamped at its 0.04 ceiling can't tell whether target, stop, or their ratio
   is the actual lever.
3. `selection.fallback_best_cagr` in the same grid search result — the single train cell with the
   highest `cagr_15slot` across all 432 cells, reported for diagnostic purposes even though it
   wasn't selected (selection prioritizes hit_rate among frequency-qualifying cells, per
   `select_best_config`'s tie-break rule) — is `target_pct=0.10, stop_pct=0.04, min_score=60,
   regime_gate=false, exclude_d_box=false`: `n_trades=1019`, `hit_rate=27.67%`,
   `trades_per_week=7.83`, `cagr_15slot=+0.53%`. Widening the target to 10% against the same 4%
   stop — restoring a normal risk/reward shape — turns train `cagr_15slot` from -20.4% to
   **slightly positive**, even though `hit_rate` is still far below 90%. That is a large swing
   driven entirely by target/stop shape, not by the entry signal.

**Concrete recommendation**: do not treat this as a dead hypothesis to be abandoned outright, and
do not jump straight to a sub-project-4-style hit-rate-improvement follow-up (additive
volume/sector/support tags) — those levers helped E반등's hit_rate only marginally and never solved
its actual (frequency) problem, whereas momentum-continuation's actual problem is not frequency
(already solved) but target/stop shape. The next sub-project should **re-run the existing 432-cell
grid with wider ranges on *both* `target_pct` and `stop_pct`** (extending past their current maxima
of 0.10 and 0.04 respectively) to determine whether a right-sized risk/reward shape — not a smarter
entry signal — is the actual lever this pattern needs, and to isolate whether target, stop, or
their ratio is doing the work. Only if a materially wider target/stop sweep still fails to
produce a cell with positive `cagr_15slot` and a plausible path to `hit_rate >= 90%` should this
hypothesis be closed and the research line pivot to low-volatility-accumulation, the other
deferred hypothesis named in the original Phase B design doc.

## 8. Widened Target/Stop Grid Follow-up (Executed)

Per Section 7's recommendation, the 432-cell grid was re-run against the same 4,197-candidate pool
with both `target_pct` and `stop_pct` widened past their original maxima, using
`target_stop_grid_search.py`'s existing `run_one_config`/`select_best_config` functions directly
(no modification to that file, and no new module — both functions already take `target_pct`/
`stop_pct` as plain arguments and operate on generic result dicts, so a one-off script was
sufficient, matching the precedent set by Phase A's tag-subset sweep):

- `target_pct ∈ {0.10, 0.15, 0.20, 0.25, 0.30}` (previously capped at 0.10)
- `stop_pct ∈ {0.04, 0.06, 0.08, 0.10}` (previously capped at 0.04)
- `min_score`/`regime_gate`/`exclude_d_box` unchanged (`{60, 90, 110}` × `{False, True}` ×
  `{False, True}`), for methodological consistency with every prior grid in this line

240 cells total (`backtest_momentum_widegrid_results.json`).

**Result: `selection.status = "target_not_met"` still — but the underlying economics flipped from
clearly negative to clearly positive and reliable.**

| Split | n_trades | Reliable (n≥50)? | hit_rate | trades_per_week | cagr_15slot |
|-------|---------:|:-----------------:|---------:|-----------------:|-------------:|
| Train (2022-01-01..2024-06-30) | 1,038 | **Yes** | 44.32% | 7.98 | **+27.93%** |
| Test (2024-07-01..2026-01-01)  | 854   | **Yes** | 45.32% | 10.89 | **+29.80%** |

Selected config: `target_pct=0.10, stop_pct=0.10` (a **symmetric 1:1** risk/reward, not the
inverted 3%/4% shape from Section 3) `, min_score=60, regime_gate=false, exclude_d_box=false`.

Three things stand out:

1. **234 of 240 cells now have positive train `cagr_15slot`**, versus 6 of 432 in the original grid
   — confirming Section 7's diagnosis that the original grid's ceiling, not the entry signal, was
   suppressing returns. The single best-`cagr_15slot` cell in this wider grid (`target_pct=0.20,
   stop_pct=0.10`, otherwise identical) reaches `n_trades=1,054`, `hit_rate=23.81%`,
   `trades_per_week=8.10`, `cagr_15slot=+52.09%` on train — reported here for completeness, not
   selected, since `select_best_config`'s fallback tier still prioritizes `hit_rate` among
   frequency-qualifying cells over raw `cagr_15slot`.
2. **`hit_rate` still never approaches the 90% bar anywhere in the widened grid.** The single
   highest `hit_rate` among all 240 cells is 48.19% (`target_pct=0.10, stop_pct=0.10,
   regime_gate=true`), and that cell fails the frequency floor (`trades_per_week=3.40 < 5`). Widening
   target/stop fixed the sign and magnitude of returns; it did not — and structurally could not —
   move `hit_rate` anywhere close to 90%. This confirms the two problems (returns vs. hit_rate) are
   genuinely separate levers, not the same one.
3. **This is the first configuration in the entire research line (sub-projects 1-5) with reliable,
   positive `cagr_15slot` on both train and test simultaneously.** Every prior result in this line —
   every E반등 configuration in sub-projects 3-4, and Section 3's original momentum-continuation
   grid — was either underpowered, or reliable-but-negative. This is reliable and positive.

**Updated verdict**: still formally **target-not-met** against this research line's strict joint
bar (`hit_rate >= 90%` is not met anywhere, in either grid) — the 90% hit_rate requirement is simply
not achievable with this entry signal at any target/stop shape tested so far, widened or not. But
the widened grid demonstrates that, independent of the formal decision gate, a symmetric 10%/10%
target/stop on this same entry signal is a reliable, profitable configuration on both splits
(+27.93%/+29.80% CAGR), which is a materially different practical conclusion than Section 4's
original "the strategy loses money" framing — that framing was specific to the narrow original
grid's boundary, not to the entry signal itself.

**Next step**: this is now a decision point rather than a further grid-search question — extending
`target_pct`/`stop_pct` further (the grid already reached 30%/10% without finding a hit_rate anywhere
near 90%) is unlikely to close the hit_rate gap, since points 2-3 above show target/stop shape and
hit_rate are independent levers. The two live options: (a) treat the 90%-hit-rate joint bar as the
wrong criterion for evaluating a momentum-continuation strategy specifically (a trend-following
approach naturally trades a lower win rate for a much larger average win — the classic asymmetric
payoff shape — and this line's 90% bar was originally calibrated for an oversold-bounce-style high-
hit-rate approach), and evaluate this configuration instead against a return-focused bar (positive,
reliable `cagr_15slot`, which it already clears); or (b) treat the 90% bar as non-negotiable across
this entire research line for consistency and formally close momentum-continuation as
target-not-met, pivoting to low-volatility-accumulation. This choice is a human decision about what
this research line is actually optimizing for, not one this analysis can make unilaterally.

## 9. Directly Targeting 90% Hit Rate (Executed)

Following an explicit user request to find an execution strategy that meets the 90% hit_rate goal
specifically, a second follow-up grid was run: since a smaller target relative to the stop should
mechanically be touched more often within the fixed 10-day hold window, `target_pct` was swept much
smaller than Section 8's range — `{0.005, 0.01, 0.015, 0.02, 0.025, 0.03}` (0.5%-3%) — against
`stop_pct ∈ {0.02, 0.03, 0.04, 0.06, 0.08, 0.10}`, same `min_score`/`regime_gate`/`exclude_d_box`
sweep as every prior grid, 432 cells total (`backtest_momentum_smalltarget_results.json`), same
one-off-script approach as Section 8 (`target_stop_grid_search.py` untouched).

**Result: hit_rate rose close to the 90% bar, but never reached it, and every cell's `cagr_15slot`
went negative — with zero exceptions.**

- **0 of 432 cells** reach `hit_rate >= 90%`. The single highest is **87.48%**
  (`target_pct=0.005, stop_pct=0.10`), `n_trades=663` (train, reliable), `trades_per_week=5.09`
  (clears the floor, barely) — but `avg_pnl=-0.98%` and `cagr_15slot=-18.40%`. Test split for this
  same (selected) config: `n_trades=544`, `hit_rate=88.79%`, `trades_per_week=6.94`,
  `cagr_15slot=-18.40%` (train and test track each other closely here).
- **0 of 432 cells have positive `cagr_15slot`** — not a near-miss, a clean sweep. Every cell in
  this smaller-target grid loses money, and the higher `hit_rate` climbs, the worse `cagr_15slot`
  generally gets (e.g. `target_pct=0.01` reaches `hit_rate=86.14%` at `cagr_15slot=-15.26%`;
  `target_pct=0.005` reaches `hit_rate=87.48%` at `cagr_15slot=-18.40%` — hit_rate keeps climbing as
  target shrinks, but returns keep getting worse, not better).

**Why this happens (not a bug, a payoff-asymmetry mechanism):** shrinking `target_pct` makes the
target easy to touch (hence higher `hit_rate`), but each win is now tiny (0.5%-3%, largely consumed
by the fixed 0.2% round-trip cost), while the `stop_pct` losses that still occasionally occur stay
large (2%-10%). At `target_pct=0.005, stop_pct=0.10`: 87.5% of trades win a net ~0.3%, but the
remaining 12.5% lose ~10.2% — expected value per trade ≈ `0.875×0.3% + 0.125×(-10.2%) ≈ -1.0%`,
matching the observed deeply negative `cagr_15slot`. This is the textbook "high win rate, poor
risk/reward" trap: hit_rate and expectancy are moving in opposite directions here, not the same
one, and no amount of further target-shrinking closes the gap — it makes both problems worse
simultaneously (hit_rate approaches but never reaches 90%, while losses on the rare stop-outs
dominate the expectancy even more).

**Combined with Section 8's finding** (widening target/stop instead pushes `cagr_15slot` solidly
positive at target=stop=10%, but `hit_rate` tops out at 48%): across the full explored space
(`target_pct` from 0.5% to 30%, `stop_pct` from 1% to 10%, 672 total cells examined across both
follow-ups plus the original 432), **`hit_rate` and `cagr_15slot` are monotonically opposed** for
this entry signal under a fixed-percentage target/stop exit — pushing either metric toward its
goal (90% hit_rate, or higher CAGR) moves the other one further away. No cell anywhere in this
space achieves both `hit_rate >= 90%` and `cagr_15slot > 0`.

**Conclusion: a 90%-hit_rate execution strategy is not achievable for this entry signal via
fixed-percentage target/stop tuning, profitably or otherwise.** Reaching 90% hit_rate specifically
would require abandoning the fixed-%-target/stop exit mechanism entirely — e.g. a trailing stop,
partial profit-taking, a volatility-adjusted (not flat-percentage) target, or a materially longer
hold window than this pool's fixed 10 days (which would require a new candidate scan, since
`hold_days` is baked into each cached candidate's window at scan time) — and even then, matching a
90% hit_rate to positive economics is not guaranteed; it runs against the general market-microstructure
reality that momentum/trend-following signals structurally trade a lower win rate for a larger
average win (the opposite shape from a high-hit-rate strategy), which is also why sub-project 3-4's
E반등 (an explicitly high-hit-rate-oriented hypothesis) could never generate enough trade frequency
to test at scale, while this hypothesis generates ample frequency but the wrong win-rate shape for
a 90% bar.

This sharpens rather than resolves the Section 8 decision point: it is not simply a matter of
picking a criterion to evaluate the *existing* 10%/10% configuration by — reaching literal 90%
`hit_rate` with this entry signal and exit family has now been demonstrated empirically
unreachable without profitability collapsing. The two live options from Section 8 stand as before,
now on firmer empirical footing: (a) evaluate momentum-continuation on a return-focused criterion
instead of the 90%-hit_rate bar (the 10%/10% configuration already clears that: reliable,
+27.93%/+29.80% cagr on both splits), since a 90%-hit_rate-compatible execution strategy for this
signal does not exist within the tested exit-mechanism family; or (b) keep the 90% bar
non-negotiable for consistency across this research line, formally close momentum-continuation as
target-not-met, and pivot to low-volatility-accumulation.

---

No production code (`src/swing-scanner.src.js`) has been changed by this sub-project — as with
every prior sub-project, that remains a separate, later decision.

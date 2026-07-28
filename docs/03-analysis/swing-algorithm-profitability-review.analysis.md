# Swing Algorithm Profitability Review

**Scope:** `src/swing-scanner.src.js` (production swing-recommendation engine) — code-review + empirical backtest (200 KRX tickers, 2024-01-01 ~ 2026-01-01 for the original naive/crude-approximation runs below; superseded by a TOSS-aware + fee-aware re-run over 959 tickers, 2022-01-01 ~ 2026-01-01 — see "Entry-model comparison" under Empirical Backtest Results).

## Executive Summary

> **[Superseded — read this first]** The numbers in this section reflect the *original* naive
> entry-fill model (signal-day close, no transaction costs, 200 tickers / 2 years) and are kept
> for historical traceability. The realistic, TOSS-LIVEPRICE-aware and fee-aware re-run over the
> full 959-ticker universe and a 4-year window found the edge to be **negative: -0.478% avg PnL /
> trade, 32.17% win rate** (2,686 trades) — see "Entry-model comparison: naive vs. crude
> approximation vs. TOSS-aware + fee-aware" under Empirical Backtest Results for the full
> three-way comparison and interpretation. Do not use the +0.89%/+0.14% figures below as the
> algorithm's current best-estimate edge.

| Item | Value |
|---|---|
| Backtest trades | 1,202 |
| Win rate | 40.68% |
| Avg PnL / trade | 0.89% |
| Median PnL / trade | -4.00% |
| Max drawdown | -92.80% (see Limitations — single naive compounding account, not a realistic portfolio figure) |
| Avg PnL / trade — next-day-open entry sensitivity | **+0.14%** (see Limitations — entry-fill model) |
| Win rate — next-day-open entry sensitivity | **39.68%** |

The algorithm shows a positive per-trade edge under the entry-fill mechanics the backtest
actually computes (avg PnL +0.89%, driven by a right-skewed payoff: a 40.68% win rate combined
with a fixed -4% median loss is only profitable overall because winning trades are large enough
to outweigh the much more frequent -4% stop-outs). **That headline number is highly sensitive to
an unrealistic entry-price assumption, though:** entries are booked at the signal day's close,
and roughly 0.79pp of the average trade's return is nothing more than the overnight gap to the
next day's open — a fill this backtest never actually has to earn (see Limitations). Recomputing
PnL at the next-day open, the fill production could realistically achieve, collapses the edge to
**+0.14% avg PnL / 39.68% win rate** — most of the reported edge is overnight gap, not selection
skill. The edge is not uniform under either entry model: the 60-89 score tier is a net loser and
the D박스 pattern is the weakest by win rate (see below). Several headline caveats materially
affect how these numbers should be read — the entry-fill sensitivity above, KRX supply-side
signals never firing anywhere in this run, and the drawdown/equity figures being an illustrative
single-account model, not a realistic portfolio simulation (see Limitations).

## Code Review Findings

### 1. Market-regime bear protection has silently regressed to dead code
`getMarketRegime()` (src/swing-scanner.src.js:403-530) computes a 3-tier KOSPI/KOSDAQ + macro
(NASDAQ/VIX/S&P futures) regime level, but is **never called**. A prior gap-analysis
(`docs/03-analysis/trailing-stop-regime-fix.analysis.md`, 2026-05-02) confirms the blocking
rule `if (regimeLevel >= 2 && grade !== '강매') return;` existed and passed review at that
date. It is absent from the current file. Production has been trading regime-blind since
this regression, despite `store.regimeCache`/log lines still giving the impression the
safety layer is active.

**Quantified impact (this backtest):** restoring the gate would have blocked 127 of 1,202
trades (10.6%) — trades: 1,202 → 1,075; win rate: 40.68% → 40.56% (−0.12pp); avg PnL: 0.89% →
0.92% (+0.03pp). In this specific backtest window, restoring the gate is **not** a large
profitability lever — the effect on win rate and average PnL is within noise, and the only
clear change is fewer trades taken. **Recommendation stands regardless:** this is still dead
code masquerading as an active safety layer (misleading logs/cache naming, silent regression
from a previously-reviewed and approved check), which is a code-integrity problem independent
of whether this one backtest window happened to show a large or small effect. A different
2024-2026 window with a sharper bear leg could show a much bigger benefit than this sample
did; the gate's job is tail-risk protection, and this backtest period may simply not have
stressed it much. Fix the discrepancy between what the code claims to do and what it does,
but do not sell the fix internally as "will meaningfully lift avg PnL" based on this result.

### 2. Two indicator/pattern implementations are dead code
`calcBB()` (Bollinger Bands) and `detectCupAndHandle()` are fully implemented but never
called from the candidate-generation path. They add maintenance surface with zero effect
on trading decisions.

### 3. Scoring weights are hand-tuned on a 30-stock hindsight sample, never statistically validated
Per `docs/01-plan/features/showmoneyv2.plan.md`, the ~15 scoring bonuses/penalties were
set from reviewing 30 stocks in hindsight ("30종목 복기 기반"), not fit or cross-validated
against a larger out-of-sample dataset. This backtest is the first out-of-sample check
these weights have received.

### 4. The pipeline is fragile under upstream data-format changes
Earlier this session, a Naver API response-normalization regression (missing BOM/Buffer/
string-JSON handling in the newly-unified `lib/naverClient.js`) caused the weekly
performance report to silently show 0 entries for 15 real recommendations. The same
class of failure could silently zero out the *live* scanner's candidate generation without
any error surfacing, given the pattern of `catch(e) { return null }` swallowing seen
throughout this codebase.

### 5. Real-time Toss confirmation cannot be backtested — and its omission inflates PnL, not just trade count
`tossConfirm()` (src/swing-scanner.src.js:1613+) blocks sends when the ask/bid ratio or
buy-execution ratio look unfavorable, using live order-book data with no historical
equivalent. On its own this piece only ever reduces trade count (never invents trades), so
on trade *frequency* the backtest remains an upper bound, as previously noted.

However, `TOSS-LIVEPRICE` (src/swing-scanner.src.js:1652-1710, added 2026-07-19) does more
than gate frequency: entry is computed from 전일 종가 (prior close), but the actual send
happens at 09:10 the next morning, so production (a) **blocks** the send if the live price
already reached target/stop by send time (추격매수 위험 — chasing risk), and (b) **rebases**
`entry`/`target`/`stop` onto the live price when the gap exceeds a threshold. This backtest
models neither behavior — it simply books the entire overnight gap between the signal-day
close and the next-day open as trade PnL (see the entry-fill correction in Limitations: that
gap alone is +0.786%/trade, essentially the whole reported edge). `TOSS-LIVEPRICE` exists
specifically to remove that gap from what actually gets filled.

So the previous framing here had the PnL direction backwards: this backtest is an **upper
bound** on realized per-trade PnL relative to what production's live-price logic would
actually allow, **not a lower bound**. The trade-*count* claim above still holds — Toss can
only reduce how many trades fire, never invent one — but do not read the reported avg PnL /
win rate as conservative relative to live execution; they are optimistic.

## Empirical Backtest Results

### Overall

| Trades | Win rate | Avg PnL | Median PnL |
|---|---|---|---|
| 1,202 | 40.68% | 0.89% | -4.00% |

### By pattern type

| Pattern | Trades | Win rate | Avg PnL | Median PnL |
|---|---|---|---|---|
| A눌림목 (pullback) | 353 | 40.79% | 0.62% | -3.71% |
| B지지선 (support line) | 61 | 42.62% | 0.65% | -4.00% |
| C촉매 (catalyst) | 454 | 41.85% | 1.30% | -4.00% |
| D박스 (box range) | 334 | 38.62% | 0.65% | -4.00% |

C촉매 has both the highest win rate-adjacent avg PnL (best avg PnL of all four patterns at
1.30%) and the second-highest win rate (41.85%), making it the strongest pattern in this
sample. D박스 has the lowest win rate (38.62%) of the four patterns while its avg PnL
(0.65%) is in line with A눌림목/B지지선 — its edge relies more heavily on payoff asymmetry
than on selection accuracy, making it the weakest pattern on a risk-adjusted (win-rate)
basis.

### By score tier

| Score tier | Trades | Win rate | Avg PnL | Median PnL |
|---|---|---|---|---|
| 60-89 | 40 | 35.00% | -0.69% | -3.35% |
| 90-109 | 168 | 39.29% | 0.38% | -3.76% |
| 110+ | 994 | 41.15% | 1.03% | -4.00% |

The 60-89 tier is the **only net-losing tier** (avg PnL -0.69% over 40 trades), and it also
has the lowest win rate of the three tiers (35.00%). Score is a real, monotonic signal here:
win rate and avg PnL both rise cleanly from 60-89 → 90-109 → 110+, with the 110+ tier
carrying 994 of the 1,202 trades (82.7%) and essentially all of the algorithm's positive
edge.

### Regime what-if: dead code vs. restored

| | As deployed (regime-blind) | If regime gate were restored |
|---|---|---|
| Trades | 1,202 | 1,075 |
| Win rate | 40.68% | 40.56% |
| Avg PnL | 0.89% | 0.92% |

Restoring the gate removes 127 trades (10.6% of the total) and leaves win rate and avg PnL
essentially unchanged (within ~0.1pp / ~0.03pp respectively). See Finding 1 for the
interpretation of this result.

### Entry-model comparison: naive vs. crude approximation vs. TOSS-aware + fee-aware

| Entry model | Universe | Trades | Win rate | Avg PnL (net where noted) |
|---|---|---|---|---|
| Signal-day close (naive, original committed baseline) | 200 tickers, 2y | 1,202 | 40.68% | +0.886% (gross) |
| Crude next-day-open approximation (same-session sensitivity check) | 200 tickers, 2y | 1,202 | 39.68% | +0.142% (gross) |
| TOSS-LIVEPRICE-aware + fee-aware (this sub-project) | 959 tickers, 4y | 2,686 | 32.17% | -0.478% (net of ~0.2% round-trip cost) |

Once entries are reconstructed from TOSS-LIVEPRICE (blocking un-fillable setups outright, and
rebasing entries onto the live price whenever the gap exceeds 2%; gaps under 2% are not rebased
in production either, so roughly two-thirds of trades — the "as_is" path — still book a bounded,
sub-2% overnight gap, while the "rebased" third do not) and a realistic ~0.2% round-trip
transaction cost is applied, the measured edge does not land between the naive and
crude-approximation figures — it goes negative, at -0.478%/trade, further from both prior numbers
than they are from each other. Notably, "as_is" trades average -0.537% pnl versus -0.359% for
"rebased" trades — the residual overnight-gap effect in the as_is trades is making the reported
number *less* negative than a fully gap-free measurement would show, so if anything the -0.478%
headline is still slightly optimistic in production's favor here, not overstated in the
pessimistic direction. This is a reversal, not just an erosion: the naive baseline's +0.886% and
the crude sensitivity check's +0.142% were both nominally profitable before costs; the
TOSS-aware, fee-aware measurement is the first of the three to be tested against real fill prices
and real costs, and it comes back negative. Read plainly, this backtest does not currently show a
profitable edge once realistic entry pricing and transaction costs are included.

That said, the reversal between row 2 and row 3 is not attributable to entry-model realism and
fees alone — the ticker universe also grew from 200 to 959 tickers and the window lengthened
from 2 years to 4 years (now spanning 2022's bear market) at the same time, and the sample's
score-tier composition shifted substantially as a result: the 110+ tier was 82.7% of trades in
the original 1,202-trade run but is 99.1% of trades in the new 2,686-trade run. Decomposing the
fee effect specifically: this run's **gross** (pre-fee) avg PnL is -0.278%, so the ~0.2%
round-trip cost accounts for only about 0.2 percentage points of the full 1.364-point swing from
the original +0.886% to -0.478%; the remaining ~1.16 points are confounded across entry-model
realism, universe size, and date range simultaneously, and this table cannot cleanly attribute
them to any one of those changes. A clean apples-to-apples attribution would require re-running
this plan's code on the original 200-ticker/2-year window specifically — a natural task for a
follow-up sub-project, not something resolved here. None of this softens the headline conclusion:
whichever combination of factors drives it, this backtest does not currently show a profitable
edge, and — per the entry-fill note above and the TOSS-quota note in Limitations — the -0.478%
figure is, if anything, a slightly optimistic estimate rather than a pessimistic one. Separately,
the `mdd` (-99.99999953%) and `equity_end` (~4.9e-9) figures from this run reflect the same naive,
single-account, 100%-capital-per-trade sequential-compounding equity model flagged elsewhere in
this document (see Executive Summary / Limitations) — they describe what happens if one account
sequentially bets its entire balance on every trade in a row, not a claim that a realistically
diversified portfolio running this strategy would go to zero.

### Portfolio-level expected annual return (diversified account, current algorithm version)

The naive single-account `mdd`/`equity_end` above and the crude round-robin figures below are
both stand-ins for "what would a real follower's account do" — production itself defines no
position-sizing rule (it is a recommendation feed, not an execution/allocation engine), so any
answer requires an explicit, documented assumption. `backtest/analyze_portfolio_return.py` (new,
2026-07-27) takes the same 2,686 realistic (TOSS-aware, fee-aware) trades used above, sorts them
chronologically, round-robins them across *N* equal-capital slots (approximating an account that
runs *N* concurrent positions, each re-invested into the next trade as it frees up), and computes
a real CAGR and MDD from the resulting equity curve — instead of the single-slot (N=1) model that
produces the degenerate -100%/~0 figures above. This is still a modeling choice, not a measured
fact: round-robin-by-date-order approximates concurrent occupancy but does not reconstruct exact
calendar overlap.

| N slots | Final equity (of 1.0 start) | Total return | CAGR | MDD |
|---|---|---|---|---|
| 5 | 0.027 | -97.30% | -59.58% | -97.33% |
| 10 | 0.171 | -82.92% | -35.81% | -82.92% |
| **15** (matches `MAX_WEEKLY_SENDS`) | **0.301** | **-69.94%** | **-26.03%** | **-70.00%** |
| 20 | 0.456 | -54.42% | -17.89% | -55.34% |
| 30 | 0.593 | -40.70% | -12.29% | -40.84% |
| 50 | 0.743 | -25.66% | -7.17% | -25.71% |
| 100 | 0.879 | -12.10% | -3.18% | -12.46% |
| 200 | 0.936 | -6.39% | -1.64% | -6.40% |

N=15 is the primary scenario because it is the only concurrency-relevant constant production
actually defines (`MAX_WEEKLY_SENDS = 15`, `src/swing-scanner.src.js:24`) — a follower trying to
act on every recommendation the current algorithm generates would realistically be running on the
order of 15 concurrent positions, not hundreds. Under that assumption, **the expected annualized
return of the current algorithm version is approximately -26% per year**, with a max drawdown
around -70%. Even the most generous over-diversification scenario tested (N=200, which is not
achievable in practice given the 15/week signal cap) still lands at roughly -1.6%/year — negative
under every diversification level modeled. This is consistent with, not contradictory to, the
-0.478% per-trade average above: at ~45 trades/slot/year (2,686 trades / 15 slots / ~4 years), a
per-trade edge this negative compounds into a large annual loss, and realized losses run somewhat
worse than the trade-average would naively suggest (compounding a negatively-skewed return stream
— frequent -4.2% stop-outs against fewer, larger wins — costs more than the arithmetic mean
implies).

**Bottom line:** based on the current, un-retuned algorithm (`src/swing-scanner.src.js`, no
scoring/pattern/regime changes — those are deferred to sub-project 2), a realistic
diversified-account expected return is negative, not positive, across every tested diversification
level. There is no reading of this data in which the current version of the algorithm has a
positive expected annual return.

## Limitations

- **[Historical — describes the original 200-ticker/2-year naive and crude-approximation
  runs only; superseded by the TOSS-aware run below] Entry-fill model booked the overnight gap
  as free profit — it did not simulate a next-day-open entry.** An earlier version of this
  document claimed entries are simulated at next-day open; that was incorrect for those original
  runs. `backtest/swing_signal_engine.py:314` sets `entry=current_price`, which is the **signal
  day's close** (`current_price = float(close[idx])` earlier in the same function). In the
  original 1,202-trade run, `run_swing_v2_backtest.py`'s exit walk started at the next trading
  day but the PnL calculation still divided by the stale signal-day close (`entry=cand.entry`),
  so every one of those trades' reported PnL silently included the full overnight gap between
  the signal day's close and the next day's open, without that gap ever having needed to be
  tradeable. Re-joining the committed `backtest_out_swing_v2.json` against the cached Yahoo
  OHLCV data (`cache/yahoo/`, still present in this worktree) to recompute PnL entered at the
  *actual* next-day open instead, across all 1,202 trades:

  | Entry model | Avg PnL / trade | Win rate |
  |---|---|---|
  | Signal-day close (what the original code computed) | +0.886% | 40.68% |
  | Next-day open (a fill production could realistically achieve) | **+0.142%** | **39.68%** |

  Average overnight gap = **+0.786%/trade** in that original run — this gap was essentially the
  entire reported edge. **This plan's TOSS-aware run supersedes both rows above** (see
  "Entry-model comparison" under Empirical Backtest Results): entry is now computed via
  `apply_toss_liveprice()` (`backtest/toss_liveprice.py`), called from
  `run_swing_v2_backtest.py:125`, and the exit walk / PnL calculation use `entry=toss.entry`
  (lines 131-135) rather than the stale signal-day close. Under that model only the ~66.7% of
  trades on the "as_is" path (gap under the 2% rebase threshold — which production genuinely
  does *not* rebase, so this is correct fidelity to production, not a bug) still book something
  resembling the old overnight-gap effect, and even for those it is bounded to under 2%
  magnitude; the remaining ~33.3% ("rebased" path) have entries reconstructed at the live price
  and do not have this issue at all. See the "Entry-model comparison" subsection above for the
  as_is-vs-rebased PnL split and the direction of the residual bias this leaves (it makes the
  headline slightly optimistic, not pessimistic). Exits still check daily high/low against
  target/stop under every entry
  model discussed here; none of them capture intraday order fills exactly the way the live
  09:00-13:00 scanning cadence does (same caveat as `backtest/README.md`).
- **[Historical — the original naive/crude-approximation runs were gross of all costs;
  transaction costs are now modeled] No transaction costs were modeled in the original runs.**
  Neither of the two original deliverables (rows 1-2 of the Entry-model comparison table)
  included Korean brokerage fees, 증권거래세 (securities transaction tax), or slippage anywhere
  in the backtest. A realistic KRX round trip costs roughly 0.15-0.2% (sell-side transaction tax
  plus brokerage commission both ways). Against the +0.886% signal-day-close headline this was a
  meaningful haircut; against the +0.142% next-day-open sensitivity figure it plausibly could
  have flipped the sign to net-negative. **This plan's TOSS-aware run now models this cost
  directly:** `apply_round_trip_cost()` (`backtest/transaction_costs.py`), called from
  `run_swing_v2_backtest.py:136`, applies a ~0.2% round-trip cost to every trade, and the
  -0.478%/trade headline in the Entry-model comparison table is already net of that cost (gross
  avg PnL for that run is -0.278% — see the Entry-model comparison subsection for the full
  decomposition). Do not read the -0.478% figure as a number that still needs a fee haircut
  applied to it.
- **[Historical — this was fixed in code by this plan; see below] One extra day of exposure
  versus what production intended, in the original runs.** The original
  `backtest/simulate_exits.py` exit loop ran `range(entry_idx, end + 1)` where
  `end = entry_idx + hold_days` — that was `hold_days + 1` bars, not `hold_days` bars.
  Production's `getHoldDays` (JS) describes "최대 N거래일" (max N trading days) counting the
  entry day itself, so every simulated trade in the original runs was held one extra trading day
  beyond what production intended, affecting all timeout exits and giving every trade one extra
  chance to touch target/stop before timing out. The original conclusion here — "a fidelity note,
  not a defect to fix in code" — has been **reversed by this plan**: `backtest/simulate_exits.py`
  now computes `end = min(len(df) - 1, entry_idx + hold_days - 1)`, which matches production's
  "최대 N거래일" semantics exactly (hold_days counts the entry day itself as day 1). This was a
  real defect and it was fixed in code; the TOSS-aware run in the Entry-model comparison table
  above reflects the corrected hold-days logic.
- Toss real-time order-book confirmation (the separate ask/bid-ratio block and pattern-C
  weak-buy-ratio block, `TOSS_ASK_BID_BLOCK_RATIO`/`TOSS_WEAK_BUY_RATIO_C`) is still not modeled
  on the trade-count side (see Finding 5) — live *trade count* is plausibly lower than backtested
  trade count to the extent Toss successfully filters bad fills on those two checks, which need
  real-time orderbook/trade-tape data with no historical equivalent (out of scope, see
  `backtest/toss_liveprice.py`'s module docstring). **[Historical — TOSS-LIVEPRICE's
  entry-rebasing/blocking behavior specifically (the live-price block/rebase, as opposed to the
  two orderbook checks above) is now modeled by this plan]** the prior version of this bullet said
  entry-rebasing/blocking was also unmodeled and made the backtest's PnL an upper bound; that is
  no longer true for the TOSS-aware run in the Entry-model comparison table, which reconstructs
  that behavior via `apply_toss_liveprice()`.
- **TOSS-blocked candidates consume this backtest's weekly send quota; production's do not.**
  In `backtest/run_swing_v2_backtest.py`, `apply_daily_selection()` (line 117) increments the
  weekly count/dedup-set for every selected candidate *before* the TOSS block check runs later
  in the same loop (line 126). In production (`src/swing-scanner.src.js:1825`), that
  bookkeeping only happens for candidates that actually get sent — `if (res) { ...
  store.weeklyRecommendations[...].push(...) }` gates both `MAX_WEEKLY_SENDS` and the dedup set
  on a successful send, so a TOSS-blocked candidate in production never consumes its weekly slot
  or dedup eligibility, and a different (next-ranked) candidate fills that slot instead. In this
  backtest, a TOSS-blocked candidate still burns the slot, so no replacement candidate is ever
  considered for it. Measured impact: 148 of 205 weeks hit the 15-selection weekly cap, and 109
  of the 146 TOSS blocks landed in those cap-bound weeks — roughly 109 weekly slots (≈4% of the
  2,686-trade count) that production would have refilled with a different candidate were instead
  left empty here. Directionally, the omitted replacement candidates would have been lower-ranked
  (worse-scored) than the blocked ones, and on an already-negative-edge strategy, adding more
  lower-quality trades would plausibly make the average PnL more negative, not less — so this gap
  likely biases the current -0.478% figure slightly optimistic too, the same direction as the
  residual as_is entry-gap effect noted above. Not code-fixed here — fixing it would require
  re-running the 1-3 hour backtest, which is out of scope for this documentation-only pass;
  recommended for the next sub-project's re-run (move the TOSS block check before quota
  bookkeeping, or refund the slot when a candidate is blocked).
- Gap-detection nuance in `getMarketRegime` (today-vs-yesterday gap source switching) is
  simplified to pure SMA-based leveling in the what-if reconstruction (Task 4) — the
  what-if numbers are directionally, not exactly, faithful to the original blocking rule. Two
  further not-fully-faithful details in the same reconstruction, disclosed here for the same
  reason: (a) the macro overlay compares a Korean trading day's return to the
  **same-calendar-date** NASDAQ/VIX close, when the US session for that date actually closes
  ~06:00 KST the *next* day — production intends the prior completed US session; this only
  affects the secondary what-if comparison (whose "marginal effect" conclusion in Finding 1 is
  robust to this), not the primary results. (b) `SP500_DOWN_THRESH` — one of production's three
  macro triggers — is commented out/unused in the regime reconstruction. Neither is a new bug;
  both are the same category of "not fully faithful, and here's specifically how" as the
  gap-detection note above.
- **KRX supply-data unavailable for this entire run.** The KRX foreign/institutional
  net-buy endpoint (`data.krx.co.kr`) returned HTTP 400 for every call during this backtest
  (build-time evidence in `backtest/tickers_operating.meta.json`'s `errors` field: `"KRX
  error: 400 Client Error: Bad Request..."`), consistent with the endpoint's known
  session/auth requirement (it expects a browser session this environment doesn't have).
  This was handled gracefully by the code — it returns `{}` per day with no crash, which is
  **not a bug** — but it means the supply-based score bonuses ("외국인+기관동반",
  "외국인순매수", "기관순매수") and the negative-supply hard-block never fired anywhere in
  this backtest. Every one of the 1,202 trades above was generated primarily from price/volume
  signals, with DART disclosures and (unavailable, see above) supply signals contributing to
  only a small minority of trades — of the 1,202 trades, only about 18 had any same-day DART
  disclosure for their code, and only about 2 matched a positive keyword, so DART's practical
  contribution to this specific backtest is negligible. That is not a bug — it matches
  production's `page_count=100` pagination limit — it was simply under-disclosed until now. This
  is a real fidelity gap in *this specific run* relative to what production actually does
  (production presumably has working KRX access) — it is not a fundamental limitation of the
  Python port itself, and should not be read as "the port is missing this feature."
- **The equity curve model is a single naive sequentially-compounding account, not
  realistic parallel position-sizing.** `mdd = -92.80%` and `equity_end = 1855.16x` (starting
  from 1.0) are correct outputs of the reviewed/approved equity calculation
  (`equity[i] = equity[i-1] * (1 + pnl)`, applied to all 1,202 trades in date order, one
  after another), but this model implicitly assumes 100% of capital is rolled into every
  single trade sequentially. It does **not** model realistically running up to 3 concurrent
  positions/day (which the daily selection cap actually allows) with proper position sizing
  across a real portfolio. Treat the per-trade `win_rate` / `avg_pnl` / `median_pnl`
  statistics above as the primary, most trustworthy signal of this algorithm's edge; treat
  `mdd` / `equity_end` as illustrative of extreme volatility under a simplistic single-account
  compounding assumption only, not as a realistic portfolio drawdown or return figure. A
  reader should not conclude "this strategy returned 1855x" or "this strategy has a real 93%
  max drawdown" from these two numbers without this caveat.

## Recommendations (priority order)

1. Restore the regime entry-blocking check (Finding 1) — fix the dead/misleading code
   regardless of profitability impact, but note this backtest found only a marginal
   difference (10.6% fewer trades, win rate/avg PnL essentially unchanged), so do not
   position the fix internally as a major expected profitability improvement based on this
   sample alone.
2. Remove or genuinely wire up `calcBB`/`detectCupAndHandle` (Finding 2) — pick one.
3. Re-tune scoring weights using this backtest's per-signal breakdown rather than the
   original 30-stock hindsight sample (Finding 3).
4. Add the same BOM/Buffer response-normalization defense used in `swing_scanner_code.js`
   to any future shared HTTP client refactor (Finding 4 — already fixed once today for the
   weekly reporter; audit remaining call sites).
5. Tighten or remove the 60-89 score tier from candidate generation, and separately re-examine
   the D박스 (box-range) pattern's entry criteria. The 60-89 tier is the only net-losing
   segment in this entire backtest (40 trades, -0.69% avg PnL, 35.00% win rate — the lowest
   of any tier), so raising the minimum actionable score threshold above 89 would likely
   remove pure drag with only 40 trades' worth of opportunity cost. Separately, D박스 has the
   lowest win rate of the four patterns (38.62%, vs. 40-43% for the other three) even though
   its avg PnL is unremarkable (0.65%) rather than compensating with outsized payoffs the way
   C촉매 does — its risk-adjusted return (win rate) is the weakest of the four patterns and its
   entry logic warrants a closer look before continuing to size it the same as the other three
   patterns.

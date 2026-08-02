# swing-algo-partial-exit-simulation Analysis Report

> **Analysis Type**: Empirical Result Report (PDCA Do → Check)
>
> **Project**: showmoneyv2
> **Feature**: swing-algo-partial-exit-simulation — Swing Algo Enhancement Sub-project 8
> (backtest the ACTUAL 3-tranche partial-exit + ATR trailing-stop mechanism production's Telegram
> message promises users, replacing the binary target/stop/timeout exit model that the existing
> -26.03%/yr headline figure is built on)
> **Design Doc**: [2026-08-02-swing-algo-partial-exit-simulation-design.md](../superpowers/specs/2026-08-02-swing-algo-partial-exit-simulation-design.md)
> **Implementation Plan**: [2026-08-02-swing-algo-partial-exit-simulation.md](../superpowers/plans/2026-08-02-swing-algo-partial-exit-simulation.md)
> **Date**: 2026-08-02
> **Prior work**: [swing-algorithm-profitability-review.analysis.md](swing-algorithm-profitability-review.analysis.md)
> (established the -0.478%/trade net, 32.17% win rate, -26.03%/yr @ N=15 / -70.00% MDD headline
> under the binary target/stop/timeout exit model — this sub-project re-tests that same
> 959-ticker/2022-2026 universe under a different exit model only, changing nothing about
> candidate generation, scoring, or entry-fill logic)

## Method summary

This sub-project adds exactly one new function, `simulate_exit_partial()`
(`backtest/simulate_exits.py`), and one new parameter, `exit_model` (`"binary"` default /
`"partial"`), to the existing Line A pipeline (`backtest/run_swing_v2_backtest.py`). Candidate
generation (`evaluate_candidate`), weekly-cap selection (`apply_daily_selection`), and
TOSS-LIVEPRICE entry reconstruction (`apply_toss_liveprice`) are all unmodified — the only thing
that changed between the two committed result files is which function decides when and at what
price a position exits. The re-run uses the identical 959-ticker, 2022-01-01..2026-01-01 universe
that produced the -26.03%/yr binary-model figure, with the same TOSS-LIVEPRICE entry reconstruction
and the same ~0.2% round-trip transaction cost applied to both.

The new exit state machine, in one paragraph: before price ever touches `entry * 1.02`, only the
original ATR-scaled `stop` is live (full position exits on stop or `hold_days` timeout). The first
touch of `entry * 1.02` sells 30% of the original position; from that point a trailing stop
(`running_high * (1 - trailingPct)`, `trailingPct = clamp(ATR% of entry, 1.0%, 3.0%)`) is active
against the remaining 70%, and a touch of `entry * 1.04` sells another 30% (of the original
position). The final 40% (or 70%, if +4% never triggers) exits on whichever comes first between a
trailing-stop breach and the `hold_days` timeout. See the design doc Sections 3-4 for the complete
state machine and the same-bar tie-break convention (worse-for-the-trader outcome checked first on
any day with an ambiguous multi-threshold touch) — that convention is not restated here.

No production code (`src/swing-scanner.src.js`) was changed by this sub-project. This is a
backtest-only re-simulation of an exit discipline production already promises; it does not alter
what production does.

## Binary vs. partial comparison table

Trade-level, from each committed JSON file's `stats` block (both 2,686 trades, same universe/date
range/entry model/transaction cost):

| Model | Trades | Win rate | Avg PnL (net) |
|---|---|---|---|
| Binary (target/stop/timeout) — `backtest_out_swing_v2_realistic.json` | 2,686 | 32.17% | -0.478% |
| Partial-exit + trailing stop — `backtest_out_swing_v2_partial_exit.json` | 2,686 | 52.35% | +0.0066% |
| **Difference (partial − binary)** | — | **+20.18pp** | **+0.484pp** |

Portfolio-level, round-robin across *N* equal-capital concurrent slots
(`backtest/analyze_portfolio_return.py`, unmodified). N=15 is primary because `MAX_WEEKLY_SENDS =
15` (`src/swing-scanner.src.js:24`) is the only concurrency-relevant constant production actually
defines. Binary-model figures are the existing ones from the profitability-review's
"Portfolio-level expected annual return" section; partial-model figures are this sub-project's
Task 4 output (re-verified against the committed JSON this session).

| N slots | Binary CAGR | Binary MDD | Partial CAGR | Partial MDD |
|---|---|---|---|---|
| 5 | -59.58% | -97.33% | -14.64% | -72.81% |
| 10 | -35.81% | -82.92% | -6.48% | -44.97% |
| **15 (primary)** | **-26.03%** | **-70.00%** | **-1.59%** (-1.5864%) | **-32.67%** (-32.6697%) |
| 20 | -17.89% | -55.34% | -1.47% | -21.42% |
| 30 | -12.29% | -40.84% | -0.33% | -15.50% |
| 50 | -7.17% | -25.71% | -0.22% | -8.89% |
| 100 | -3.18% | -12.46% | +0.14% | -4.56% |
| 200 | -1.64% | -6.40% | +0.04% | -2.30% |

Note the crossover: at N=100 and N=200 the partial-exit model's CAGR turns marginally positive.
Neither is achievable in practice — both exceed what a 15-signal/week production cap can ever
supply concurrently — and the profitability-review document already flags N=200 under the binary
model as "not achievable in practice" for the same reason. The only concurrency level that matches
what production can actually deliver, N=15, remains negative under both exit models.

## Result-tag breakdown

From the partial-exit run's 2,686 trades (`t["result"]`, independently re-counted against the
committed JSON this session):

| Result tag | Count | % of total |
|---|---|---|
| `trail` | 1,322 | 49.2% |
| `pretrigger_stop` | 1,141 | 42.5% |
| `target4_then_trail` | 171 | 6.4% |
| `pretrigger_timeout` | 26 | 1.0% |
| `target4_then_timeout` | 16 | 0.6% |
| `trigger_then_timeout` | 10 | 0.4% |
| **Total** | **2,686** | **100%** |

Derived groupings (new, previously unmeasured information about how often production's promised
exit discipline actually engages):

- **Never even reach +2%** (`pretrigger_stop` + `pretrigger_timeout`): 1,167 trades, **43.45%**.
  For these trades the entire 3-tranche/trailing-stop machinery never engages at all — the trade
  is a plain stop-out or timeout, indistinguishable in mechanism from a binary-model loss.
- **Ride the trailing stop after triggering** (`trail` + `target4_then_trail`): 1,493 trades,
  **55.58%**. This is the majority of trades, but only just — a bit over half.
- **Reach the +4% partial at all** (`target4_then_trail` + `target4_then_timeout`): 187 trades,
  **6.96%** — the "double partial" outcome production's message describes as the best case is rare.
- **Time out without ever using the trailing mechanism** (`trigger_then_timeout`): 10 trades,
  **0.37%** — negligible; almost every trade that triggers the +2% tranche eventually resolves via
  the trailing stop, not a plain timeout.

## Honest trader-perspective verdict

The exit mechanism makes the headline number **substantially better, but it is not a wash and it
does not flip the sign.** Quantified: win rate moves +20.18pp (32.17% → 52.35%), avg PnL moves
+0.484pp (-0.478% → +0.0066%), and portfolio CAGR at N=15 moves from -26.03%/yr to -1.59%/yr — a
reduction in annual loss of roughly 94% in absolute magnitude, with MDD improving from -70.00% to
-32.67%. **This magnitude of improvement is not a settled fact — it is sensitive to the
trailing-stop fill-price convention documented in Limitations below.** Under the convention actually
implemented (fill at the computed level regardless of the fill day's own open), the improvement is
as dramatic as stated above; under a next-open stop-fill convention, avg PnL and CAGR both move
substantially the other direction (see Limitations for the reproduced numbers). The qualitative
bottom line — a real, large improvement in degree, not a sign flip, entry signal still lacks
positive edge — holds either way, but the precise size of the improvement should not be quoted as a
single settled number. With that caveat, it is still honest to say the prior -26%/yr headline
was in substantial part an artifact of assuming a full-target-or-bust exit model that does not
match what production actually tells users to do — most of the apparent loss was hiding a real
exit-discipline benefit that no backtest in this repo had measured until now.

But it is equally honest to say this does **not** prove the algorithm profitable. Two separate
numbers say so: first, avg PnL per trade is +0.0066% — a number so close to zero it is
indistinguishable from breakeven, not a demonstrated positive edge; second, and more decisively,
portfolio CAGR at N=15 — the only concurrency level production can actually deliver — is still
**-1.59%/yr**, i.e. still a losing strategy at the account level, just a much less badly losing
one. A trader reading only "win rate went from 32% to 52%" would be misled into thinking the
system now wins; it does not win, it merely stops losing as badly, because it wins slightly less
than half the time and its losses (the 42.5% `pretrigger_stop` cohort, still hitting the full stop)
still outweigh its (now more frequent, smaller) wins on net.

This result shifts more of the blame for the original -26%/yr figure onto the **exit-model
assumption** than onto the entry signal in one specific sense — the binary model was clearly too
punitive relative to what production would really let a position ride out. But it does *not*
exonerate the entry signal: with the more realistic exit now in place, the *residual* edge — what's
left after the exit discipline gets full credit — is essentially zero, not positive. The
pattern-selection logic (which candidates get chosen, how they're scored, ranked, and which pattern
detectors fire) still has to explain why, even with a generous trailing-stop exit, the average trade
nets nothing. The result-tag breakdown makes the mechanism of that residual weakness concrete:
43.45% of all trades (`pretrigger_stop` + `pretrigger_timeout`) never even reach the first +2%
partial-exit trigger — for those trades the trailing-stop benefit this sub-project measured simply
does not apply, and they look exactly like the binary model's losers, full stop. The trailing
mechanism's entire measured benefit is concentrated in the 55.58% of trades that do trigger it; it
cannot rescue the ~43% that stop out or time out before ever tasting a partial gain, and those
trades' entry-timing/selection quality is what determines whether that ~43% shrinks or grows —
that lever lives entirely in the entry signal, not the exit mechanism.

## Limitations

Restated in substance from the design doc's Section 10 (see that document for full detail):

- **Daily-bar-only same-day ordering assumption** is the single largest source of uncertainty this
  sub-project introduces. Because the cached OHLC data has no intraday tick data, any day on which
  more than one threshold could plausibly have been crossed (e.g. a low that undercuts the trailing
  stop and a high that clears +4% on the same day) is resolved by a documented, conservative
  tie-break (worse-for-the-trader outcome checked first). **For the multi-threshold tie-break
  itself this is a reasonable "pessimistic" framing. But for the trailing-stop *fill price*
  specifically, a final whole-branch review found the opposite is true**: `simulate_exit_partial()`
  fills the trailing exit at `running_high * (1 - trailing_pct)` regardless of where the fill day
  actually opened, and in the large majority of trailing exits that computed level sits *above*
  where the stock was actually tradeable that day — this is systematically more favorable to the
  trader than either coherent alternative (continuous intraday tracking, or a realistic
  next-open stop-order fill), not "slightly pessimistic." See the subsection immediately below for
  the quantified finding and its effect on the headline numbers.
- **Trailing-stop fill-price optimism (found in final review, not caught during implementation).**
  Across the 1,493 trades that resolve via `trail` or `target4_then_trail`, in 977 of them (65.4%,
  independently re-verified against the committed JSON this session) the fill day's own `open`
  price is already below the booked trailing-stop fill price — meaning the model books a fill the
  stock could not actually have been sold at, always to the trader's benefit. Replaying the
  running-high state machine day-by-day shows the mechanism in the large majority of these cases
  (974 of 977): the trailing level is computed from `running_high` as of the *previous* day's
  close and is never re-checked against that same prior day's own low — so when the level jumps up
  off a fresh high made the day before, and the position finally exits the next day, the fill can be
  booked well above where the stock has already fallen to by that day's open. Concrete example
  already in the committed data: ticker `085910.KQ`, signal `2022-01-13`, entry 5650 — the +2%
  trigger fires `2022-01-14` (day's high 6480 sets `running_high=6480`), and the remaining 70% books
  a trailing exit on `2022-01-17` at 6285.60 (`6480 * 0.97`) — but `2022-01-17`'s own open was 5990,
  4.9% below the booked fill. Re-pricing every `stop`/`trail` fill in the whole 2,686-trade dataset
  as `min(booked_level, open_of_fill_day)` — the standard convention for a stop order that only
  becomes executable at the next tradable open once triggered — was reproduced exactly against the
  committed JSON: avg net PnL moves from +0.0066% to **-0.9155%**, and portfolio CAGR at N=15 moves
  from -1.59%/yr to **-34.79%/yr** (MDD -81.84%, win_rate 42.63%) — i.e. *worse* than the
  binary-model baseline's -26.03%/yr. This is reported as a sensitivity check under an alternative,
  arguably more realistic fill convention, not as a replacement headline number — the actually
  implemented convention is what's in the committed JSON and is internally consistent, just
  previously under-disclosed as favorable rather than pessimistic.
- **Flat, non-per-fill transaction cost.** The existing ~0.2% round-trip cost is applied once to
  the blended `gross_pnl` across all tranches, assuming fee scales with sold value rather than
  number of fills. This is the same flat-fee simplification every prior sub-project in this
  research line has inherited, now explicitly extended to a multi-tranche exit.
- **Inherits every limitation already documented for the underlying Line A pipeline**: the
  TOSS-LIVEPRICE entry-fill approximation, KRX supply-API sandbox blockage (foreign/institutional
  net-buy signals never fire in this environment), and the discrete/no-fee historical validation
  gap for the real-time ask/bid and buy-ratio gates. None of these change in this sub-project —
  only the exit simulation changed, not entry or candidate generation.
- **Single run, no walk-forward.** This produces one number for one universe/date-range, matching
  every prior sub-project's practice in this research line — not a fresh limitation, just restated.
- **Does not extend to Line B** (sub-projects 2/4/5b/6/7a-c). Those results remain reported under
  the binary exit model unless a future sub-project extends `CachedCandidate` with `atr_pct` and
  regenerates its cache — out of scope here.

## Final recommendation

This finding does **not** change the recommended next step from the honest trader-perspective gap
review that opened this priority list. The exit mechanism turned out to be a large, real
improvement in *degree* (loss cut by ~94% at N=15 under the implemented fill convention — see
Limitations for why that specific magnitude is a modeling-sensitive number, not a settled one) but
not a *sign flip* — the realistic exit discipline lands at -1.59%/yr (implemented convention) to
-34.79%/yr (next-open stop-fill convention) at the one concurrency level production can actually
deliver, and the underlying per-trade edge is, at best, a statistical wash (+0.0066% avg PnL under
the implemented convention, clearly negative under the alternative), not a demonstrated profit under
either convention. Because the exit-mechanism question is now answered — and answered as "meaningfully
better, still not profitable" rather than "was the whole problem" — this result reinforces, rather
than displaces, **priority-3's re-fit of the scoring weights against real (not 30-stock hindsight)
data and isolating B지지선** as the higher-leverage next step. Further tuning of the exit mechanism
itself (e.g. adjusting the +2%/+4% trigger levels or the trailing-stop ATR clamp) is lower priority
than fixing what candidates get selected in the first place: the 43.45% of trades that never reach
the first partial-exit trigger at all are a *selection* problem — no exit-side tuning can improve a
trade that never gets far enough into profit for the exit mechanism to engage.

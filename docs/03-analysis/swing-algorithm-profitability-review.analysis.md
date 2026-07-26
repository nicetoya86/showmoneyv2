# Swing Algorithm Profitability Review

**Scope:** `src/swing-scanner.src.js` (production swing-recommendation engine) — code-review + empirical backtest (200 KRX tickers, 2024-01-01 ~ 2026-01-01).

## Executive Summary

| Item | Value |
|---|---|
| Backtest trades | 1,202 |
| Win rate | 40.68% |
| Avg PnL / trade | 0.89% |
| Median PnL / trade | -4.00% |
| Max drawdown | -92.80% (see Limitations — single naive compounding account, not a realistic portfolio figure) |

The algorithm shows a real positive per-trade edge (avg PnL +0.89%, driven by a right-skewed
payoff: a 40.68% win rate combined with a fixed -4% median loss is only profitable overall
because winning trades are large enough to outweigh the much more frequent -4% stop-outs). The
edge is not uniform: the 60-89 score tier is a net loser and the D박스 pattern is the weakest by
win rate (see below). Two headline caveats materially affect how these numbers should be read —
KRX supply-side signals never fired anywhere in this run, and the drawdown/equity figures are an
illustrative single-account model, not a realistic portfolio simulation (see Limitations).

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

### 5. Real-time order-book confirmation (Toss) cannot be backtested
`tossConfirm()` (src/swing-scanner.src.js:1613+) blocks sends when the ask/bid ratio or
buy-execution ratio look unfavorable, using live order-book data with no historical
equivalent. Its effect is unmeasured — it can only reduce trade count (never invents
trades), so the backtest below is an upper bound on trade frequency and a lower bound on
"how bad the worst-executed signals would have been" (Toss's job is specifically to catch
those).

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

## Limitations

- Daily-bar backtest: entries are simulated at next-day open, exits check daily high/low
  against target/stop — this does not capture intraday order fills exactly the way the
  live 09:00-13:00 scanning cadence does (same caveat as `backtest/README.md`).
- Toss real-time confirmation not modeled (see Finding 5) — live win rate is plausibly
  *higher* than backtested win rate to the extent Toss successfully filters bad fills.
- Gap-detection nuance in `getMarketRegime` (today-vs-yesterday gap source switching) is
  simplified to pure SMA-based leveling in the what-if reconstruction (Task 4) — the
  what-if numbers are directionally, not exactly, faithful to the original blocking rule.
- **KRX supply-data unavailable for this entire run.** The KRX foreign/institutional
  net-buy endpoint (`data.krx.co.kr`) returned HTTP 400 for every call during this backtest
  (build-time evidence in `backtest/tickers_operating.meta.json`'s `errors` field: `"KRX
  error: 400 Client Error: Bad Request..."`), consistent with the endpoint's known
  session/auth requirement (it expects a browser session this environment doesn't have).
  This was handled gracefully by the code — it returns `{}` per day with no crash, which is
  **not a bug** — but it means the supply-based score bonuses ("외국인+기관동반",
  "외국인순매수", "기관순매수") and the negative-supply hard-block never fired anywhere in
  this backtest. Every one of the 1,202 trades above was generated purely from
  price/volume/DART-disclosure signals, with zero supply-side signal contribution. This is a
  real fidelity gap in *this specific run* relative to what production actually does
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

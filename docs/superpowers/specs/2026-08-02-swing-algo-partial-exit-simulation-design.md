# swing-algo-partial-exit-simulation Design

> **Project**: showmoneyv2
> **Feature**: Swing Algo Enhancement Sub-project 8 — backtest the ACTUAL exit mechanism
> production promises users (3-tranche partial exit + ATR trailing stop), replacing the
> binary target/stop/timeout model the current headline CAGR figure is built on.
> **Prior work**: [swing-algorithm-profitability-review.analysis.md](../../03-analysis/swing-algorithm-profitability-review.analysis.md)
> (the -0.478%/trade, -26.03%/yr @ N=15 headline this sub-project re-tests under a different
> exit model — see "Portfolio-level expected annual return" section there)
> **Date**: 2026-08-02

---

## 1. Context and Goal

This is priority-2 of an honest trader-perspective gap review conducted this session (priority-1,
restoring the dead regime gate and raising `MIN_SCORE_FINAL`, is already committed —
`d4d1e33`/`bec9f01`). The gap: **no backtest in this repo simulates the exit mechanism production
actually tells users to run.** `src/swing-scanner.src.js`'s Telegram message (lines 1782-1811)
promises:

```
- 트레일링: +2% 도달시 고점 -X% 이동   (X = clamp(ATR% of entry, 1.0, 3.0))
📊 분할청산: 1차(30%) +2% / 2차(30%) +4% / 잔여(40%) 트레일링
```

**This is a fixed instruction, decoupled from the per-trade computed `target`/`target1`.** The
message separately shows "최종 목표: (+Y%)" and "1차 목표: (+Z%)" from the real ATR-scaled
per-pattern formula (`Y`/`Z` vary 8%-30% by pattern), but the partial-exit schedule is *always*
+2%/+4% regardless of what `Y`/`Z` actually are — an internal inconsistency in production itself,
noted here for the record, not something this sub-project fixes (out of scope: this sub-project
backtests what's promised, it does not change `src/swing-scanner.src.js`).

Every backtest run so far (`backtest/simulate_exits.py::simulate_exit()`) uses a simple binary
model: exit at first `target`/`stop` touch, else timeout at `hold_days`. The current headline
figure (**-0.478%/trade net, -26.03%/yr CAGR @ N=15 concurrent slots**, 959 tickers,
2022-01-01..2026-01-01, TOSS-LIVEPRICE-aware, fee-aware) is built entirely on that binary model.
Nobody knows whether that number is optimistic or pessimistic relative to what production's real
exit discipline would produce.

**Goal**: implement a second exit-simulation function that faithfully models the 3-tranche
partial-exit + trailing-stop mechanism, re-run it against the same 959-ticker/4-year universe used
for the -26.03%/yr figure, and report the resulting win rate / avg PnL / portfolio CAGR side by
side with the binary-model number — honestly, whichever direction it moves.

## 2. Why This Attaches to Line A (`run_swing_v2_backtest.py`), Not Line B (sub-projects 2/7a-c)

This repo has two backtest lines. **Line B** (`backtest/generate_signal_candidates.py`'s
`CachedCandidate` + `backtest/target_stop_grid_search.py`) caches only a forward-looking
5-day OHLC window per candidate and overrides target/stop with an arbitrary flat
`target_pct`/`stop_pct` grid — it has no access to historical bars *before* the signal day, so it
cannot recompute ATR, and it doesn't carry an `atr_pct` field on `CachedCandidate` at all.

**Line A** (`backtest/run_swing_v2_backtest.py::backtest_swing_v2()`) is the one that actually
produced the -26.03%/yr figure being re-tested here, and it holds each ticker's **full multi-year
OHLC history** in memory (`per_ticker[ticker]`) — so ATR(14) as of the signal day can be recomputed
inline from data already in scope, using the exact same `backtest/indicators.py::atr()` function
`swing_signal_engine.py` already uses internally. This sub-project's new code attaches to Line A.
(Extending Line B to support this would require adding `atr_pct` to `CachedCandidate` and
regenerating `backtest_candidates_with_paths.json` from scratch — a separate, larger task, not
attempted here.)

## 3. Confirmed Exit State Machine

Confirmed with the user this session, based on the production message text:

1. **Before +2% is ever touched**: only the original ATR-scaled `stop` is active. Touching
   `target`/`target1` does nothing — those are a separate "final target" display value, not a
   partial-exit trigger. Full position (100%) exits only via `stop` or `hold_days` timeout.
2. **First touch of `entry * 1.02`**: sell 30% of the original position at `entry * 1.02`.
3. **Remaining 70%, tracked from that point**:
   - If price later touches `entry * 1.04`: sell another 30% (of the *original* position) at
     `entry * 1.04`.
   - Simultaneously, a trailing stop is live: `running_high * (1 - trailingPct)`, `running_high`
     ratcheting up with each new high since the +2% trigger, `trailingPct = clamp(ATR% of entry,
     1.0%, 3.0%)` (production's exact formula, line 1787).
   - The remaining 40% (after the +4% partial) exits on whichever comes first: a trailing-stop
     breach, or the `hold_days` timeout.
4. **If the trailing stop is breached before the +4% partial ever triggers**: the entire remaining
   70% (the 40% "core" plus the still-unsold 30% second tranche) exits at the trailing-stop price
   in one shot.

**Arithmetic check (not a new assumption, just confirms the state machine is self-consistent):**
once the trailing stop is active, its level is always at or above `running_high * 0.97` (worst
case, `trailingPct = 3%`), and `running_high >= entry * 1.02` by definition of having triggered —
so the trailing floor is always **above** `entry * 0.9894`. Every pattern's original `stop` floor
is `stopPct >= 4%` (`>=5%` for B지지선), i.e. `stop <= entry * 0.96`. The trailing stop can
therefore never sit below the original hard stop once active — the original stop is safely
superseded, not something that needs to be carried forward as a parallel floor during the runner
phase.

## 4. Same-Bar Ambiguity: Daily-Bar-Only Data, Documented Tie-Break Convention

The cached OHLC data (both Line A's full ticker history and Line B's window) is **daily bars only**
— open/high/low/close, no intraday tick data. Within a single day, if more than one threshold
could plausibly have been touched (e.g. a day's low undercuts the stop *and* its high clears
+2%), the true intraday order is unknowable from this data. Extending this repo's existing
convention (`simulate_exit()`'s documented same-bar target+stop tie-break, which conservatively
resolves to stop), this sub-project adopts the same bias throughout: **whenever a day could
plausibly trigger more than one outcome, check the worse-for-the-trader outcome first.**
Concretely, day-by-day:

- **Pre-trigger phase**: check `stop` breach before checking the +2% trigger. A day whose low
  undercuts stop AND whose high clears +2% is scored as a full stop-out, not a partial trigger.
- **Runner phase**: check trailing-stop breach (using the *prior* day's `running_high`, not the
  current day's — see below) before checking the +4% partial trigger, and before updating
  `running_high` with the current day's high. A day that could plausibly hit both is scored as a
  trailing-stop exit for the full remaining weight, not a +4% partial.
- **`running_high` update timing**: the trailing level checked on day *i* is derived from
  `running_high` as accumulated through day *i-1*'s close (i.e. "yesterday's peak, checked
  against today's low"). Only after that check does day *i*'s high get folded into
  `running_high` for tomorrow's level. This avoids a circular "today's price move causes today's
  own stop-out" reading and matches how a real trailing-stop order works (the broker's stop level
  is set from the prior peak, not from a still-forming bar).
- **Timeout**: if `hold_days` elapses with weight still open, that weight exits at the final
  day's close — identical to `simulate_exit()`'s existing timeout convention.

This is a **documented limitation, not a claim of certainty** — see Section 7.

## 5. New Function: `backtest/simulate_exits.py::simulate_exit_partial()`

Added as a sibling to the existing `simulate_exit()`, which is **not modified** (every prior
sub-project's cached results that call it stay reproducible).

```python
def simulate_exit_partial(
    df: pd.DataFrame,
    entry_idx: int,
    *,
    entry: float,
    stop: float,
    atr_pct: float,
    hold_days: int,
) -> Dict[str, Any]:
    """3-tranche partial-exit + trailing-stop model matching the exact text of
    src/swing-scanner.src.js's Telegram message (lines 1782-1811): 30% @ +2%, 30% @ +4%,
    remaining 40% on trailing-stop-breach or hold_days timeout (whichever first), trailing
    width = clamp(atr_pct, 0.01, 0.03) of entry. See docs/superpowers/specs/
    2026-08-02-swing-algo-partial-exit-simulation-design.md Sections 3-4 for the exact state
    machine and same-bar tie-break convention this implements.

    Returns exit_price as the POSITION-WEIGHTED AVERAGE fill price across whichever tranches
    executed (weights always sum to 1.0) -- downstream pnl math
    ((exit_price - entry) / entry) is therefore unchanged from simulate_exit()'s contract,
    since pnl_pct = sum(weight_i * (price_i/entry - 1)) = (sum(weight_i * price_i))/entry - 1
    algebraically. `tranches` lists each individual fill for auditability;
    `result` is one of: "pretrigger_stop", "pretrigger_timeout", "trail",
    "target4_then_trail", "target4_then_timeout", "trigger_then_timeout".
    """
```

**No new dependencies.** Pure Python/pandas, same style as the existing function.

**Interfaces:**
- Consumes: a `pandas.DataFrame` with `open`/`high`/`low`/`close` columns (same contract as
  `simulate_exit`), `entry`/`stop` (already TOSS-LIVEPRICE-rebased, matching how
  `backtest_swing_v2()` already calls `simulate_exit` today), `atr_pct` (new — the caller computes
  this, see Section 6), `hold_days`.
- Produces: `{"exit_price": float, "result": str, "days_held": int, "tranches": List[Dict]}`. The
  `exit_price`/`days_held` keys match `simulate_exit()`'s existing return contract exactly, so
  `backtest_swing_v2()`'s downstream `gross_pnl = (exit_price - entry) / entry` line needs zero
  changes.

## 6. Wiring: `backtest/run_swing_v2_backtest.py`

- Add `exit_model: str = "binary"` parameter to `backtest_swing_v2()`. Default preserves the
  existing behavior and the existing committed `backtest_out_swing_v2_realistic.json` stays
  exactly reproducible (nothing about the default path changes).
- When `exit_model == "partial"`, compute `atr_pct` inline right before the exit-simulation call,
  reusing `backtest/indicators.py::atr()` on the **full** `per_ticker[ticker]` history (already in
  scope in this loop) at the signal-day index — same formula and same NaN/zero fallback
  `swing_signal_engine.py` uses internally (lines 276-282), so the two ATR values agree. Pass it to
  `simulate_exit_partial(..., atr_pct=atr_pct)`; `atr_pct` is computed from `toss.entry` as the
  denominator (matching production's `c.atrAbs / c.entry` in the Telegram message, where `c.entry`
  may already be TOSS-rebased).
- `main()` gets a `--exit-model {binary,partial}` CLI argument (default `binary`).
- **Transaction cost stays exactly as today** — `apply_round_trip_cost()` is applied once to the
  blended `gross_pnl`, unchanged. This is a deliberate simplification, not an oversight: the
  existing flat 0.2% round-trip figure already assumes a proportional (not per-order-minimum) fee
  structure; under that assumption, three proportional sell fills summing to 100% of the position
  cost the same total sell-side fee as one full-position sell, so splitting the exit into tranches
  doesn't change the total fee — see Section 7 for the flat-fee limitation this inherits unchanged.

## 7. Data Flow

```
backtest/tickers_operating.txt (959 tickers, already used for the existing -26.03%/yr run)
  + cache/yahoo/*.json, backtest/cache/krx_supply/*.json, backtest/cache/dart/*.json
    (all already locally cached from the prior run -- this re-run should not need fresh
    network fetches for the same universe/date-range)
  -> backtest_swing_v2(..., exit_model="partial")
       [same candidate-gen (evaluate_candidate, unmodified) + apply_daily_selection (unmodified)
        + apply_toss_liveprice (unmodified) as today, only the exit-simulation call differs]
  -> backtest_out_swing_v2_partial_exit.json (new committed artifact; same schema as
     backtest_out_swing_v2_realistic.json plus a `tranches` field per trade)

backtest_out_swing_v2_partial_exit.json
  -> backtest/analyze_portfolio_return.py [UNMODIFIED -- already schema-compatible, only reads
     trade["date"]/trade["pnl"]] run against the new file
  -> docs/03-analysis/swing-algo-partial-exit-simulation.analysis.md (new)
```

## 8. Error Handling

No new failure modes beyond what `backtest_swing_v2()` already handles (per-ticker fetch failures
are already caught and recorded in `skipped_tickers`). `simulate_exit_partial()` is pure
computation over an in-memory DataFrame — no I/O, no new exception paths to design for.

## 9. Testing

New logic (a multi-branch state machine) gets real unit tests in
`backtest/tests/test_simulate_exit_partial.py` — this is the first sub-project in this research
line to add new *logic* (not just new data), so it's held to this repo's normal test bar, not the
"execution-only, no source touched" bar sub-projects 7a-c used. Cases to cover (constructed with
small synthetic OHLC DataFrames, not live data):
- Never triggers +2%, stops out pre-trigger (`pretrigger_stop`).
- Never triggers +2%, times out pre-trigger (`pretrigger_timeout`).
- Triggers +2%, then trailing-stop breach before +4% (`trail`) — verify the 30% tranche at +2%
  priced correctly and the remaining 70% exits at the trailing level.
- Triggers +2%, then +4%, then trailing breach on the remaining 40% (`target4_then_trail`).
- Triggers +2%, then +4%, then times out (`target4_then_timeout`).
- Triggers +2%, never hits +4% or trailing breach, times out (`trigger_then_timeout`).
- Same-bar tie-break case: a day whose low undercuts stop and whose high clears +2% in the
  pre-trigger phase — assert it resolves to `pretrigger_stop`, not a trigger.
- Same-bar tie-break case in the runner phase: a day whose low undercuts the trailing level and
  whose high clears +4% — assert it resolves to a trailing exit, not a +4% partial.
- `exit_price` weighted-average arithmetic: assert `pnl_pct = (exit_price - entry) / entry`
  matches a hand-computed weighted sum for a multi-tranche case.

## 10. Limitations

- **Daily-bar-only same-day ordering assumption** (Section 4) — the single largest source of
  uncertainty this sub-project introduces. The conservative tie-break biases the simulation
  slightly pessimistic relative to whatever production's real intraday order actually is; this
  cannot be resolved without intraday data, which this repo does not have access to.
- **Flat, non-per-fill transaction cost** (Section 6) — same inherited limitation as every prior
  sub-project, now explicitly extended to assume fee scales with sold value, not number of fills.
- Inherits every limitation already documented for the underlying Line A pipeline this attaches
  to: TOSS-LIVEPRICE entry-fill approximation, KRX supply-API sandbox blockage, discrete/no-fee
  historical validation of the ask/bid and buy-ratio real-time gates (none of these change in this
  sub-project — this sub-project only changes the *exit* simulation, not entry or candidate
  generation).
- **Single run, no walk-forward** — this produces one number for one universe/date-range, matching
  every prior sub-project's practice in this research line; not a fresh limitation, just restated.
- Does not extend to Line B (sub-projects 2/4/5b/6/7a-c) — those results remain reported under the
  binary exit model unless a future sub-project extends `CachedCandidate` with `atr_pct` and
  regenerates its cache (out of scope here, see Section 2).

No production code (`src/swing-scanner.src.js`) is changed by this sub-project — it backtests what
production already promises users, it does not alter that promise.

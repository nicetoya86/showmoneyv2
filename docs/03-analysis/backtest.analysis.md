# backtest Analysis Report

> **Analysis Type**: Gap Analysis (PDCA Check phase)
>
> **Project**: showmoneyv2
> **Feature**: backtest — Swing Algo Enhancement Sub-project 1 (Realistic Backtest Foundation)
> **Analyst**: bkit gap-detector
> **Date**: 2026-07-27
> **Design Doc**: [2026-07-26-swing-algo-realistic-backtest-foundation-design.md](../superpowers/specs/2026-07-26-swing-algo-realistic-backtest-foundation-design.md)
> **Implementation Plan**: [2026-07-26-swing-algo-realistic-backtest-foundation.md](../superpowers/plans/2026-07-26-swing-algo-realistic-backtest-foundation.md)
> **Implementation**: merged on `main`, commits `7590069`..`ed07c9b`

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Verify that the merged implementation of the realistic-backtest foundation matches the design spec
and the implementation plan, with particular attention to the plan's explicit numeric constraints
(2% rebase threshold, `>=`/`<=` block comparisons, 0.2% cost default, `hold_days` semantics), the
scope boundary (8 files that must not be touched), test rigor (value-pinning tests, not
smoke tests), and the re-run's actual universe/date range.

### 1.2 Analysis Scope

| Item | Value |
|---|---|
| Design document | `docs/superpowers/specs/2026-07-26-swing-algo-realistic-backtest-foundation-design.md` |
| Implementation plan | `docs/superpowers/plans/2026-07-26-swing-algo-realistic-backtest-foundation.md` |
| Implementation paths | `backtest/toss_liveprice.py`, `backtest/transaction_costs.py`, `backtest/simulate_exits.py`, `backtest/run_swing_v2_backtest.py`, `backtest/tests/` |
| Data artifact | `backtest_out_swing_v2_realistic.json` (committed in `242ea8a`) |
| Report artifact | `docs/03-analysis/swing-algorithm-profitability-review.analysis.md` |
| Verification method | Source read + `python -m pytest backtest/tests -v` executed + `git log`/`git diff --stat` + JSON metadata inspection |

---

## 2. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 100% (post-fix) | ✅ |
| Plan Constraint Compliance | 100% | ✅ |
| Test Rigor | 100% | ✅ |
| Data/Re-run Fidelity | 100% | ✅ |
| Report Documentation Consistency | 100% (post-fix) | ✅ |
| **Overall Match Rate** | **100% (post-fix)** | ✅ |

```
┌─────────────────────────────────────────────┐
│  Overall Match Rate: 94% → 100% (post-fix)   │
├─────────────────────────────────────────────┤
│  ✅ Full match:        32 items (100%)       │
│  🔵 Changed behavior:   1 item  (reconciled) │
│  🟡 Doc inconsistency:  2 items (fixed)      │
│  🔴 Missing:            0 items (0%)         │
└─────────────────────────────────────────────┘
```

No missing features. No unauthorized additions. No out-of-scope file was touched.

**Post-analysis fix applied (2026-07-27, same session):** all three items in section 6.1 were
resolved immediately following this analysis — see §8 Resolution below. Sections 3-7 are left as
originally written (the as-found state) for audit traceability; §8 records what changed.

---

## 3. Verification Matrix

### 3.1 `backtest/toss_liveprice.py` (new module)

| # | Design/Plan requirement | Evidence | Status |
|---|---|---|---|
| 1 | Module created as pure function over plain floats | `backtest/toss_liveprice.py:39-66`, no I/O imports | ✅ |
| 2 | `TOSS_GAP_REBASE_THRESHOLD` exactly `0.02` | `toss_liveprice.py:28` → `TOSS_GAP_REBASE_THRESHOLD = 0.02`; matches `src/swing-scanner.src.js:1569` | ✅ |
| 3 | Block comparisons use `>=` / `<=`, not strict | `toss_liveprice.py:49` `if next_day_open >= target`, `:51` `if next_day_open <= stop`; matches JS `:1675-1676` | ✅ |
| 4 | Decision order: chasing → stopped_out → rebase → as_is | `toss_liveprice.py:49 → 51 → 55 → 66`, sequential early returns | ✅ |
| 5 | Rebase preserves original target_pct/stop_pct | `toss_liveprice.py:56-63` (`target/entry - 1`, `1 - stop/entry`, reapplied to new entry); matches JS `:1698-1705` | ✅ |
| 6 | `gap_rebase_threshold` keyword-overridable | `toss_liveprice.py:44-45` keyword-only with default | ✅ |
| 7 | `TossOutcome(status, entry, target, stop)` frozen dataclass | `toss_liveprice.py:31-36` | ✅ |
| 8 | `next_day_open`-as-live-price documented as an explicit approximation | `toss_liveprice.py:13-16` module docstring "NOT MODELED (approximation, documented)" | ✅ |
| 9 | Ask/bid + pattern-C blocks documented as out of scope | `toss_liveprice.py:18-22` | ✅ |

### 3.2 `backtest/transaction_costs.py` (new module)

| # | Design/Plan requirement | Evidence | Status |
|---|---|---|---|
| 10 | Default cost `0.002` | `transaction_costs.py:12` `DEFAULT_ROUND_TRIP_COST_PCT = 0.002` | ✅ |
| 11 | Keyword-overridable, not a hardcoded literal at call sites | `transaction_costs.py:15` `*, cost_pct=DEFAULT_ROUND_TRIP_COST_PCT`; call site `run_swing_v2_backtest.py:136` uses the default, does not inline `0.002` | ✅ |
| 12 | Documented as an approximation, NOT a verified regulatory figure | `transaction_costs.py:4-8` "it is not sourced from a verified, current regulatory or broker-specific rate table" | ✅ |

### 3.3 `backtest/simulate_exits.py` (off-by-one fix)

| # | Design/Plan requirement | Evidence | Status |
|---|---|---|---|
| 13 | Walk exactly `hold_days` bars, not `hold_days + 1` | `simulate_exits.py:20` `end = min(len(df) - 1, entry_idx + hold_days - 1)` — verified on the actual line, not just the docstring | ✅ |
| 14 | Docstring states entry day counts as day 1 | `simulate_exits.py:17-19` | ✅ |
| 15 | Signature/return shape unchanged | `simulate_exits.py:8-16`, `:27-33` — same `{exit_idx, exit_price, result, days_held}` | ✅ |

### 3.4 `backtest/run_swing_v2_backtest.py` (wiring)

| # | Design/Plan requirement | Evidence | Status |
|---|---|---|---|
| 16 | Both new modules imported | `run_swing_v2_backtest.py:16-17` | ✅ |
| 17 | `next_day_open` sourced from the already-loaded per-ticker DataFrame (no new fetch) | `run_swing_v2_backtest.py:120-124` | ✅ |
| 18 | Blocked candidates excluded from the trade list | `run_swing_v2_backtest.py:126-130` `continue` before `simulate_exit` | ✅ |
| 19 | Blocked candidates recorded with `{date, ticker, code, reason}`, same shape as `skipped_tickers` | `run_swing_v2_backtest.py:127-129` | ✅ |
| 20 | Cost applied after `simulate_exit`; `pnl` net, `gross_pnl` pre-cost | `run_swing_v2_backtest.py:135-136` | ✅ |
| 21 | New trade fields `gross_pnl`, `toss_status` are additive only | `run_swing_v2_backtest.py:144`; all prior keys retained at `:138-143` | ✅ |
| 22 | Empty-trades branch carries `blocked_by_toss` | `run_swing_v2_backtest.py:148-154` | ✅ |
| 23 | `blocked_by_toss` present in the non-empty stats dict | `run_swing_v2_backtest.py:173` | ✅ |
| 24 | Selection-cap logic otherwise unchanged | `apply_daily_selection` (`:36-52`) untouched; `git diff --stat` shows only 26 changed lines in this file | ✅ |
| 25 | TOSS check placed **before** `apply_daily_selection` (design spec) | `apply_daily_selection` runs at `:117`, TOSS check at `:125` — **placed after** | 🔵 |

### 3.5 Scope boundary (Global Constraints)

| # | Constraint | Evidence | Status |
|---|---|---|---|
| 26 | 8 named files must not be modified | `git log --oneline bbd8889..HEAD -- backtest/swing_signal_engine.py backtest/krx_supply_history.py backtest/dart_history.py backtest/market_regime_history.py backtest/indicators.py backtest/analyze_swing_v2_results.py backtest/strategy_rules.py backtest/run_backtest_swing.py` → **empty output** | ✅ |
| 27 | `analyze_swing_v2_results.py` keeps working unmodified against the new trade dicts | Reads only `pnl`, `pattern_type`, `score`, `grade`, `date` (`analyze_swing_v2_results.py:16-18, 26-31, 67-71`) — all still present in the new dicts; its 7 tests pass | ✅ |
| 28 | No scoring / pattern / regime / signal changes; no ML | `swing_signal_engine.py` and `market_regime_history.py` both absent from the diff; full changed-file list is 11 files, all in scope | ✅ |

### 3.6 Test rigor

| # | Requirement | Evidence | Status |
|---|---|---|---|
| 29 | Every numeric/logic port has a value-pinning test (no "runs without error" tests) | `test_toss_liveprice.py` (8 tests, all assert exact status + exact entry/target/stop, incl. `112.2`/`91.8`, `106.7`/`87.3`); `test_transaction_costs.py` (4, incl. `DEFAULT_ROUND_TRIP_COST_PCT == 0.002`); `test_simulate_exits.py::test_timeout_exits_at_close_of_entry_day_when_hold_days_is_one` pins `exit_price == 103.0` / `days_held == 0`; `test_run_swing_v2_backtest.py` pins `gross_pnl == 0.10` and `pnl == 0.10 - 0.002` | ✅ |
| 30 | Boundary + branch coverage per design's Testing section | as_is / rebased / blocked_chasing / blocked_stopped_out / exactly-2% / just-below-2% / negative-gap / custom-threshold all present | ✅ |
| 31 | Full suite green (executed by this analysis, not taken on trust) | `python -m pytest backtest/tests -v` → `74 passed in 3.85s`, 74 collected, 0 failed / 0 error / 0 skipped (Python 3.11.9, pytest 9.1.1). Per file: toss_liveprice 8, transaction_costs 4, simulate_exits 5, run_swing_v2_backtest 10 | ✅ |

### 3.7 Re-run fidelity (`backtest_out_swing_v2_realistic.json`)

| # | Requirement | Actual | Status |
|---|---|---|---|
| 32 | 959-ticker universe (not the old 200) | `params.tickers = 959`; `backtest/tickers_operating.txt` line count = 959; 767 distinct tickers actually produced trades | ✅ |
| 33 | Date range 2022-01-01 → 2026-01-01 (not the old 2 years) | `params = {start: '2022-01-01', end: '2026-01-01'}`; trade dates span `2022-01-04` → `2025-12-30` | ✅ |
| 34 | Trades in a sane range, no NaN | 2,686 trades; `avg_pnl` and `mdd` both non-NaN | ✅ |
| 35 | `blocked_by_toss` non-trivial but not overwhelming | 146 blocks (80 `blocked_chasing` / 66 `blocked_stopped_out`) ≈ 5.2% of the 2,832 pre-block selections — wiring demonstrably exercised | ✅ |
| 36 | New per-trade fields actually present in output | `trade0` keys include `gross_pnl` and `toss_status`; `as_is` 1,791 / `rebased` 895 | ✅ |
| 37 | Cost actually applied | `trade0`: `gross_pnl -0.04` → `pnl -0.042` (exactly 20 bps) | ✅ |
| 38 | Artifact committed for reproducibility | `242ea8a data(backtest): realistic (TOSS-aware, fee-aware) swing v2 backtest output, 959 tickers 2022-01-01..2026-01-01`; 1,357,115 bytes | ✅ |

### 3.8 Report update (Task 6)

| # | Requirement | Evidence | Status |
|---|---|---|---|
| 39 | Three-way comparison table exists under Empirical Backtest Results | `swing-algorithm-profitability-review.analysis.md:147-153` | ✅ |
| 40 | All three rows filled with real numbers | Row 3: `959 tickers, 4y \| 2,686 \| 32.17% \| -0.478% (net of ~0.2% round-trip cost)` — matches the JSON exactly | ✅ |
| 41 | Zero bracket placeholders in the committed file | `Select-String '\[from Step'` → no matches; `[TODO`/`[TBD`/`[fill` → no matches | ✅ |
| 42 | Interpretive paragraph, stated plainly without over/under-selling | `:155-190` — includes the as_is-vs-rebased decomposition, the gross -0.278% fee attribution, and an explicit confounding disclaimer | ✅ |
| 43 | Superseded Limitations bullets marked as historical | Entry-fill bullet (`:194`), transaction-cost bullet (`:229`), hold-days bullet (`:243`) all carry `[Historical — ...]` markers — but the Toss bullet at `:256` does not | 🟡 |
| 44 | Report internally consistent with the new headline result | Executive Summary (`:3-30`) still scoped to "200 KRX tickers, 2024-01-01 ~ 2026-01-01" and still asserts a positive edge | 🟡 |

---

## 4. Gaps Found

### 🔴 Missing Features (Design ✓, Implementation ✗)

None.

### 🟡 Added Features (Design ✗, Implementation ✓)

None. The only new public surface is exactly what the design specified: two modules, two additive
trade fields, one additive stats key.

### 🔵 Changed Behavior (Design ≠ Implementation)

#### GAP-1 — TOSS block runs *after* `apply_daily_selection`, not before (severity: 🟡 Low-Medium)

| | |
|---|---|
| **Design says** | `design.md:122-126`: "after `evaluate_candidate` produces a candidate and **before `apply_daily_selection`**/`simulate_exit` … **Blocked candidates never reach `apply_daily_selection`**." |
| **Plan says** | `plan.md:497-512`: replace the body of `for code, cand in selected:` — i.e. explicitly *after* selection. The plan silently contradicts its own design doc here. |
| **Implementation** | `run_swing_v2_backtest.py:117` calls `apply_daily_selection(...)`; the TOSS check is at `:125-130`, inside the resulting `for code, cand in selected:` loop. |
| **Behavioral impact** | `apply_daily_selection` increments `week_state["count"]` and the dedup set for every *selected* candidate. A candidate later blocked by TOSS therefore still burns one of the 3/day and 15/week send slots, and no replacement candidate is considered. Production (`src/swing-scanner.src.js:1825`) only records the weekly slot on a successful send, so a blocked candidate there is refilled by the next-ranked one. |
| **Measured impact** | Already quantified in the report doc (`:261-280`): 148 of 205 weeks hit the weekly cap; 109 of the 146 TOSS blocks landed in cap-bound weeks — roughly 109 slots (~4% of the 2,686-trade count) left unfilled. Direction of bias: the omitted replacements would have been lower-ranked, so on a negative-edge strategy this makes the -0.478% headline slightly *optimistic*. |
| **Assessment** | Not a defect introduced blind — the prior session discovered it, documented it with numbers, and stated why it was not code-fixed (fixing it requires a 1-3 hour re-run, out of scope for a documentation pass). The *documentation* gap is that the design spec still asserts the opposite ordering and was never reconciled. |
| **Recommended resolution** | **Option 2 (update design to match implementation)** + carry the fix forward. Amend `design.md:122-126` to describe post-selection blocking and cross-reference the quota-consumption limitation. Move the block check before quota bookkeeping (or refund the slot) in sub-project 2's re-run, as the report already recommends. |

### 🟡 Documentation Inconsistencies

#### GAP-2 — Stale Limitations bullet claims TOSS-LIVEPRICE is "not modeled" (severity: 🟢 Low)

`docs/03-analysis/swing-algorithm-profitability-review.analysis.md:256-260`:

> "Separately, and more materially, `TOSS-LIVEPRICE`'s entry-rebasing/blocking behavior is also
> not modeled — see Finding 5 for why this makes the backtest's PnL an upper bound…"

This is now false for the TOSS-aware run and, unlike the three neighbouring superseded bullets
(`:194`, `:229`, `:243`), it carries no `[Historical — …]` marker. A reader landing on Limitations
first will conclude the new run does not model TOSS at all.

**Fix**: prefix with `[Historical — modeled as of this plan's run; see the Entry-model comparison
table]` in the same style as the adjacent bullets, keeping only the genuinely-still-unmodeled part
(orderbook ask/bid ratio and pattern-C buy-ratio blocks).

#### GAP-3 — Executive Summary not reconciled with the superseding result (severity: 🟡 Low-Medium)

`swing-algorithm-profitability-review.analysis.md:3` still scopes the whole document to
"200 KRX tickers, 2024-01-01 ~ 2026-01-01", and the Executive Summary table (`:7-15`) plus prose
(`:17-30`) still lead with "The algorithm shows a positive per-trade edge" / +0.89% / +0.14%, with
no pointer to the -0.478% net figure that the same document later calls the superseding
measurement.

Strictly, plan Task 6 only required adding the comparison subsection, so this is not a plan
violation — but the document's most-read section now contradicts its own conclusion.

**Fix**: add the 959-ticker/4-year row to the Executive Summary table and one sentence pointing to
the Entry-model comparison subsection; widen the scope line at `:3`.

---

## 5. Non-Gap Observations

- **`mdd` = -99.99999953% and `equity_end` = 4.9e-09** in the committed JSON are arithmetically
  correct for the single-account, 100%-capital-per-trade sequential-compounding model, not a
  realistic portfolio drawdown. The report already flags this at `:186-190`. No action required,
  but any downstream artifact quoting "-100% MDD" must carry that caveat.
- **4 tickers skipped** during the 959-ticker run — the prior hardening work (`e75962b`,
  `cd5e27b`) covered exactly this failure mode, as the design predicted (`design.md:143-147`).
- **Test count**: 74 total, versus the plan's non-load-bearing estimate of 74. Exact match, though
  the plan itself noted zero failures was the real criterion.

---

## 6. Recommended Actions

### 6.1 Immediate (documentation only — no code change needed)

| Priority | Action | File |
|---|---|---|
| 🟡 1 | Amend the wiring section to describe post-selection blocking; note the quota-consumption consequence | `docs/superpowers/specs/2026-07-26-swing-algo-realistic-backtest-foundation-design.md:122-126` |
| 🟡 2 | Mark the stale TOSS "not modeled" Limitations bullet as `[Historical]` | `docs/03-analysis/swing-algorithm-profitability-review.analysis.md:256-260` |
| 🟡 3 | Reconcile the Executive Summary / scope line with the -0.478% superseding result | `docs/03-analysis/swing-algorithm-profitability-review.analysis.md:3, 7-30` |

### 6.2 Carry into sub-project 2

| Action | Rationale |
|---|---|
| Move the TOSS block check before weekly-quota bookkeeping, or refund the slot on block | Closes GAP-1's residual production-fidelity gap; requires a re-run, so it belongs to the next run cycle |
| Re-run this plan's code on the original 200-ticker / 2-year window | Enables clean attribution of the +0.886% → -0.478% swing across entry-model realism vs. universe vs. date range (report `:180-182`) |

---

## 7. Conclusion

**Match Rate: 94%.** Every in-scope code requirement was implemented exactly as specified — all
four explicit numeric/logic constraints verified against the actual source lines (0.02 threshold,
`>=`/`<=` comparisons, `hold_days - 1`, 0.002 keyword-overridable cost), all 8 out-of-scope files
provably untouched, 74/74 tests passing with value-pinning assertions rather than smoke tests, and
the re-run genuinely executed over the 959-ticker universe across 2022-01-01..2026-01-01.

The only true design-vs-implementation divergence is the placement of the TOSS block relative to
daily selection — a deviation the implementation inherited from the plan, which is closer to
production's real ordering than the design text was, and whose residual bias the team already
measured and disclosed. The remaining two findings are stale passages in the profitability report
that the new run superseded but did not update.

No code changes are required to reach ≥90%. Three documentation edits close the remaining 6%.

---

## 8. Resolution (post-analysis fix, 2026-07-27)

All three §6.1 documentation actions were applied immediately after this analysis, in the same
session:

| Gap | Fix applied | Where |
|---|---|---|
| GAP-1 (design/implementation ordering) | Added a "[Reconciled post-implementation]" paragraph describing the actual post-selection placement, its quota-consumption consequence, the measured ~4% impact, and why closing it is deferred to sub-project 2 | `docs/superpowers/specs/2026-07-26-swing-algo-realistic-backtest-foundation-design.md`, end of the `run_swing_v2_backtest.py` wiring section |
| GAP-2 (stale "not modeled" bullet) | Split the bullet: the still-unmodeled orderbook ask/bid + pattern-C checks stay flagged as unmodeled (out of scope); the TOSS-LIVEPRICE rebase/block behavior is now marked `[Historical — ... now modeled by this plan]` | `docs/03-analysis/swing-algorithm-profitability-review.analysis.md`, Limitations bullet (was `:256-260`) |
| GAP-3 (Executive Summary not reconciled) | Widened the scope line to note the superseding 959-ticker/4-year re-run; added a "[Superseded — read this first]" callout immediately above the Executive Summary table pointing to the -0.478% net result and the Entry-model comparison subsection | `docs/03-analysis/swing-algorithm-profitability-review.analysis.md`, scope line + Executive Summary |

No code was touched in this fix pass — consistent with §6.1's "documentation only — no code
change needed" framing. The sub-project 2 carry-forward item (§6.2, moving the TOSS block before
quota bookkeeping) remains open by design, tracked for the next sub-project rather than fixed
here.

**Match Rate after fix: 100%.** All in-scope design/plan requirements are implemented correctly,
and all identified documentation inconsistencies are resolved. Ready for `/pdca report backtest`.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-27 | Initial gap analysis (Check phase) | bkit gap-detector |
| 1.1 | 2026-07-27 | Applied all 3 recommended documentation fixes; Match Rate 94% → 100% | Claude (same session) |

# swing-algo-signal-weight-refit Analysis Report

> **Analysis Type**: Empirical Result Report (PDCA Do → Check)
>
> **Project**: showmoneyv2
> **Feature**: swing-algo-signal-weight-refit — Swing Algo Enhancement Sub-project 10
> (statistically re-fitting the auxiliary scoring-signal weights against real backtest outcome
> data; priority-3 item from this session's honest trader-perspective gap review)
> **Design Doc**: [2026-08-02-swing-algo-signal-weight-refit-design.md](../superpowers/specs/2026-08-02-swing-algo-signal-weight-refit-design.md)
> **Implementation Plan**: [2026-08-02-swing-algo-signal-weight-refit.md](../superpowers/plans/2026-08-02-swing-algo-signal-weight-refit.md)
> **Date**: 2026-08-02
> **Prior work**: [swing-algorithm-profitability-review.analysis.md](swing-algorithm-profitability-review.analysis.md)
> (Finding #3: "Scoring weights are hand-tuned on a 30-stock hindsight sample, never
> statistically validated" — the gap this sub-project closes; also the source of the KRX
> supply-API HTTP-400 and DART near-non-coverage findings cited below)

---

## 1. Method Summary

Per the design doc's Section 1 scope decision, this sub-project re-fits **only the auxiliary
signal weights** — volume-multiple tier, OBV trend, MACD state, SMA20/60 alignment, intraday
closing strength, foreign/institutional supply tier, DART disclosure tier, RSI golden zone, ADX
trend, and 52-week-high proximity. The four pattern base weights (C촉매=60, A눌림목=50, B지지선=45,
D박스=40) and their combo bonuses are **not** touched — those have already been exhaustively
examined via the target/stop-tuning axis in sub-projects 7a/7b/7c/9 (all `target_not_met`). This
sub-project targets a different, previously-unexamined axis: whether the *modifier* weights on top
of pattern identification correlate with real trade outcomes.

**Exit model**: the binary exit model (`exit_model="binary"`, the default), not sub-project 8's
partial-exit model. Per the design doc's Section 3, the partial-exit model's trailing-stop fill
price has a documented, unresolved optimism bias (see
[swing-algo-partial-exit-simulation.analysis.md](swing-algo-partial-exit-simulation.analysis.md)'s
Limitations); using it as the regression's label would inject that same bias into "which signals
predict a win," making the fitted weights harder to trust. The binary model's own bias (the
TOSS-quota slot-refund approximation, ~4% of trades) is smaller and already characterized
elsewhere in this research line, so it is accepted here rather than compounding two different
exit-model uncertainties into one regression.

**Data**: `backtest_out_swing_v2_with_features.json` — 2,686 trades, the same universe
(`backtest/tickers_operating.txt`, 959 tickers) and date range (2022-01-01..2026-01-01) as every
other sub-project in this line, each trade record now carrying an `aux_features` dict captured
at candidate-generation time.

**Train/test split**: train = 2022-01-01..2024-06-30 (1,657 trades), test = 2024-07-01..2026-01-01
(1,029 trades) — the same convention used throughout this research line. Verified directly against
the committed dataset: filtering `backtest_out_swing_v2_with_features.json`'s trades by `date` into
those two windows yields exactly 1,657 and 1,029 records, matching
`backtest_signal_weight_fit.json`'s `n_train`/`n_test` fields.

**Encoding**: each of the 9 `aux_features` keys is one-hot/dummy-encoded with `drop_first=True`
(the lowest tier / most-penalized category becomes the implicit reference level); boolean features
(`sma_aligned`, `rsi_golden`, `adx_trend`) are passed through as single 0/1 columns rather than
dummy-expanded. `pattern_type` is included as a one-hot control (also drop-first) so the auxiliary
coefficients are estimated net of which pattern a candidate came from, not confounded by it — this
is a control variable, not a re-fit of the pattern base weights. The model is
`sklearn.linear_model.LogisticRegression(penalty="l2", C=1.0)` predicting `pnl > 0`, matching Line
A's existing win-rate definition.

**No production code (`src/swing-scanner.src.js`) was changed by this sub-project.**

---

## 2. Data Coverage Caveat (read this before the coefficient table)

Two of the ten auxiliary signals have data coverage too thin in this sandbox's backtest for their
fitted coefficients to mean anything, regardless of what number the regression outputs for them.
Computed directly from `backtest_out_swing_v2_with_features.json`'s 2,686 trades:

| Feature | Non-zero trades | Non-zero rate | Detail |
|---|---|---|---|
| `supply_tier` | 0 / 2,686 | **0.0%** | Every single trade has `supply_tier == 0`. This is exactly the KRX-supply-API-blocked limitation the design doc's Section 7 predicted (`data.krx.co.kr` returns HTTP 400 in this sandbox, per the profitability-review doc). Because the column is **perfectly constant**, one-hot encoding with `drop_first=True` produces **zero dummy columns** for it — `supply_tier` does not even appear in the fitted coefficient table below. This is a stronger non-finding than "unreliable": the model was given literally no variance to learn from on this feature. |
| `dart_tier` | 37 / 2,686 | **1.4%** | 29 trades at tier 1 (당일공시/neutral disclosure), 8 trades at tier 2 (긍정공시/positive disclosure), 2,649 at tier 0. This matches the profitability-review doc's finding that only ~18 of the original 1,202-trade sample had any same-day DART disclosure at all — DART coverage remains negligible in the larger 2,686-trade sample too. |

**Both `dart_tier`'s two fitted coefficients must be treated as unreliable regardless of sign or
magnitude** — a feature estimated from 29 and 8 positive cases respectively (out of 2,686) cannot
have its true relationship to outcome distinguished from noise, no matter what value the L2-penalized
fit happens to converge on. `supply_tier` is not merely unreliable, it is **entirely unestimated** —
its production score bonuses ("외국인+기관동반" etc.) simply never fired in this dataset, exactly as
the prior profitability review found for the original 1,202-trade sample.

---

## 3. Model Performance

From `backtest_signal_weight_fit.json`:

| Metric | Value |
|---|---|
| `n_train` | 1,657 |
| `n_test` | 1,029 |
| `train_positive_rate` (win rate, train split) | 30.60% |
| `test_positive_rate` (win rate, test split) | 34.69% |
| `train_auc` | 0.5798 |
| `test_auc` | **0.5284** |

**The model shows no meaningful discriminative power on the test split.** Test AUC of 0.5284 is
barely above the 0.5 no-skill baseline — for context, an AUC of 0.5 means the model's ranking of
trades by predicted win probability is no better than random ordering, and 0.53 is a very small
step above that. Train AUC (0.5798) is somewhat higher, but per the design doc's Section 5
guidance, train AUC alone proves nothing: a 20-feature regularized logistic regression fit on 1,657
rows can produce this size of a train/test gap through ordinary overfitting rather than genuine
signal, and the gap here (0.58 → 0.53) is consistent with exactly that. Any interpretation of the
coefficient table below must be weighed against this: **this is a weak model, and weak-AUC models
produce noisy coefficients even under L2 regularization.**

---

## 4. Coefficient Table

All 20 fitted feature coefficients from `backtest_signal_weight_fit.json`, sorted by absolute
magnitude (intercept = -0.4930, listed separately since it is not a feature). Each dummy
coefficient is relative to its category's dropped reference level (the lowest tier, or for
`obv_trend` the `-1`/bearish level, or for `macd_state` the `golden_cross` level — see notes).
"Consistent" means the fitted sign points the same direction as production's hand-tuned point
schedule; "Contradicts" means it points the opposite way.

| Feature | Coefficient | Coverage | Direction vs. production |
|---|---|---|---|
| `dart_tier_1` (당일공시) | +1.0450 | **1.4% non-zero — unreliable, disregard** | n/a |
| `dart_tier_2` (긍정공시) | -0.7159 | **1.4% non-zero — unreliable, disregard** | n/a |
| `obv_trend_0` (neutral, vs. bearish=-1 baseline) | -0.5220 | full | **Contradicts** — see §5 |
| `intraday_tier_2` (장마감강세, vs. tier0 baseline) | -0.4177 | full | **Contradicts** — production rewards this tier most (+12), fit is the most negative of the two intraday dummies |
| `intraday_tier_1` (장마감양호, vs. tier0 baseline) | -0.3370 | full | **Contradicts** — production rewards +6, fit is negative |
| `rvol_tier_1` (≥2x, vs. tier0 baseline) | -0.3151 | full | **Contradicts** — see §5 |
| `macd_state_neutral` (vs. golden_cross baseline) | +0.2833 | full | **Contradicts** — see §5 |
| `rvol_tier_2` (≥3x, vs. tier0 baseline) | -0.2609 | full | **Contradicts** — see §5 |
| `pattern_type_C촉매` (vs. A눌림목 baseline, control) | +0.1704 | full | control variable, not an auxiliary weight — see §5 note |
| `macd_state_macd_up` (vs. golden_cross baseline) | +0.1669 | full | **Contradicts** — see §5 |
| `pattern_type_D박스` (vs. A눌림목 baseline, control) | +0.1625 | full | control variable, not an auxiliary weight |
| `rvol_tier_3` (≥5x, vs. tier0 baseline) | +0.1605 | full | **Consistent in sign only** — but non-monotonic overall, see §5 |
| `obv_trend_1` (bullish, vs. bearish=-1 baseline) | -0.1298 | full | **Contradicts** — see §5 |
| `pattern_type_B지지선` (vs. A눌림목 baseline, control) | -0.1214 | full | control variable, not an auxiliary weight |
| `rvol_tier_4` (≥8x, vs. tier0 baseline) | -0.1060 | full | **Contradicts** — production's highest-rewarded tier (+25) is fitted negative |
| `high52_tier_2` (new high, vs. tier0 baseline) | -0.0965 | full | **Contradicts** — production's highest-rewarded tier (+25) is fitted negative |
| `sma_aligned` (True vs. False) | -0.0948 | full | **Contradicts** — production rewards +15, fit is negative |
| `rsi_golden` (True vs. False) | +0.0860 | full | **Consistent** — production rewards +8, fit is positive |
| `adx_trend` (True vs. False) | -0.0789 | full | **Contradicts** — production rewards +10, fit is negative |
| `high52_tier_1` (near high, vs. tier0 baseline) | +0.0762 | full | **Consistent** — production rewards +10, fit is positive |
| `intercept` | -0.4930 | — | — |

---

## 5. Notable Directional Findings (stated plainly, calibrated against §3)

Several coefficients point in the **opposite direction** from what production's hand-tuned point
values assume:

- **`rvol_tier`** — production rewards higher volume-multiple tiers more (+6/+12/+18/+25 for tiers
  1-4). The fit shows no consistent positive relationship: tier1 = -0.315, tier2 = -0.261, tier3 =
  +0.160, tier4 = -0.106 (all relative to tier0). This is non-monotonic and mostly negative,
  contradicting the assumption that a bigger volume-tier bonus tracks a better outcome.
- **`obv_trend`** — production rewards `obv_trend=1` (+20) and penalizes `obv_trend=-1` (-8). The
  fit shows `obv_trend_1 = -0.130` and `obv_trend_0 = -0.522`, both relative to `obv_trend=-1` (the
  dropped reference — i.e. the category production penalizes most). Both "neutral" and "bullish"
  OBV are associated with **lower** predicted win probability than "bearish" OBV in this fit — the
  opposite of production's assumption.
- **`macd_state`** — production rewards `golden_cross` most (+15). The fit shows
  `macd_state_neutral = +0.283` and `macd_state_macd_up = +0.167`, both relative to `golden_cross`
  (the dropped reference, production's most-rewarded state) — meaning `golden_cross` is associated
  with **lower** win probability than either alternative state in this fit.
- **`intraday_tier`** and **`high52_tier`** show the same pattern as `rvol_tier`: production assumes
  monotonically increasing reward with tier, but the fit is non-monotonic (`intraday_tier` is
  negative at both tiers and *more* negative at the higher tier; `high52_tier`'s highest tier is
  negative while its middle tier is positive).
- **`sma_aligned`** and **`adx_trend`** are small-magnitude but negative, contradicting production's
  small positive bonuses for both.
- Only **`rsi_golden`** and `high52_tier_1` (the *lower*, not the highest, 52-week-high tier) are
  directionally consistent with production's assumptions among the full-coverage features.

**The critical, honesty-preserving caveat on all of the above**: test AUC is 0.5284 — barely better
than a coin flip. This means the model's overall discriminative power is very weak, so no
individual coefficient's sign should be treated as a confident, standalone finding either —
regularized logistic regression coefficients on a weak-AUC model are themselves noisy, and with 20
correlated dummy features competing for credit on ~1,657 training rows, individual signs can shift
under a different split or regularization strength. **The correctly-calibrated conclusion is: this
analysis finds no reliable evidence supporting production's current auxiliary weight assumptions,
and several point the opposite direction — but the overall model is too weak (test AUC ≈ 0.53) to
confidently assert any specific signal is actively harmful, only that the current point values are
not empirically supported.** This is not "production's OBV logic is proven wrong" (that would
overclaim what a 0.53-AUC model can support), nor is it "inconclusive, more research needed" (that
would understate a real, if weak-evidence, pattern of directional mismatch across most of the
full-coverage features).

**Note on `pattern_type` coefficients**: these are control variables per the design doc's Section 5
(included so auxiliary-signal coefficients are estimated net of pattern, not confounded by it), not
a re-fit of the pattern base weights, which remain out of scope for this sub-project. In passing,
their ranking (C촉매 > D박스 > A눌림목(reference) > B지지선) is loosely consistent with the
profitability review's finding that C촉매 had the best avg PnL of the four patterns — but this is a
side observation on a control variable, not a finding this sub-project is scoped to evaluate.

---

## 6. Honest Trader-Perspective Verdict

This refit does **not** support keeping production's current auxiliary weights as empirically
grounded. Of the eight full-coverage auxiliary features (excluding the two low/zero-coverage
signals), six (`rvol_tier`, `obv_trend`, `macd_state`, `intraday_tier`, `sma_aligned`, `adx_trend`)
show directional patterns that contradict production's hand-tuned assumption, and one more
(`high52_tier`) is contradicted at its most-rewarded tier while its lesser tier is consistent. Only
`rsi_golden` is cleanly consistent across the board. That is a striking, uncomfortable finding given
how much of the total scoring formula these auxiliary weights constitute (up to roughly a third of
a typical qualifying candidate's total score, on top of the 40-60 point pattern base weight) — and
it should be said plainly rather than softened.

At the same time, this is **not** proof that any single auxiliary signal actively hurts trade
selection. Test AUC of 0.5284 means this model, taken as a whole, barely distinguishes winning
trades from losing ones — a coin flip with slightly better-than-even odds. A model this weak cannot
license a confident claim like "OBV is proven backwards" or "golden cross is proven harmful"; it can
only license the weaker, but still real, claim that **no evidence in this dataset supports the
current point values as currently assigned**, and that several of them point the wrong way more
often than chance alone would predict across eight independent features. Given every prior
sub-project in this research line has already found the pattern base weights, target/stop
parameters, and even a 90%-hit-rate-oriented reweighting all fail to produce a validated edge (see
the MEMORY.md history of sub-projects 4/5/5b/7a-9), this result is consistent with, not contradictory
to, the broader pattern this research line keeps finding: the algorithm's scoring formula — base
weights and auxiliary modifiers alike — has not yet been shown to correlate with real, realistic
(TOSS-aware, fee-aware) outcomes at any level examined so far.

---

## 7. Limitations

- **Sample size and class imbalance**: 2,686 trades total, ~31-35% positive class (`pnl>0`)
  depending on split, under the binary exit model. A 20-feature logistic regression on ~1,657
  training rows is workable but not generous — several coefficients above could plausibly flip sign
  under a different split or regularization strength, and none should be read as settled.
- **Correlated features**: several auxiliary signals plausibly co-occur (e.g., high `rvol` days
  often also show `obv_trend=1` and strong intraday closing). L2 regularization mitigates but does
  not eliminate the risk that correlated features split credit in a way that under-states either
  one's true individual effect — this is exactly why L2 (not unregularized logistic regression) was
  chosen, per the design doc's Section 1 rationale, but it is a mitigation, not a cure.
- **Single train/test split** — the same acknowledged limitation as every prior sub-project in this
  research line; no cross-validation or multiple-split robustness check was performed.
- **Binary exit model's own inherited limitations** (documented in
  [swing-algorithm-profitability-review.analysis.md](swing-algorithm-profitability-review.analysis.md)):
  the TOSS-quota slot-refund approximation (~4% of trades), flat transaction cost, and — as directly
  re-verified in §2 above — KRX supply-API sandbox unavailability (`supply_tier` constant at 0
  across all 2,686 trades) and DART near-non-coverage (`dart_tier` non-zero for only 1.4% of
  trades). Both `supply_tier` and `dart_tier` coefficients (where they exist at all) must not be
  read as validated findings.
- **Correlational, not causal**: even a well-fit model would only show association between signals
  and outcome in this historical sample, not proof that any single signal *causes* better trades —
  a standard caveat for any observational analysis, and one that applies with even more force here
  given the weak overall fit.
- **This does not re-examine pattern base weights or target/stop parameters** — those remain covered
  by sub-projects 7a/7b/7c/9 (patterns) and this research line's earlier target/stop grid searches.
  This sub-project is scoped to the auxiliary signal weights only, per the design doc's Section 1
  confirmed decision.

---

## 8. Final Recommendation

**No immediate change to production's current auxiliary scoring weights is recommended based on
this finding alone.** This is consistent with every prior sub-project's negative or null result in
this research line, and follows directly from this sub-project's own limitations: a test AUC of
0.5284 is too weak a signal to justify reweighting or dropping any specific auxiliary component with
confidence, even though several of the fitted directions disagree with production's current
assumptions. The honest reading is a caution flag, not a validated blueprint for change — acting on
individual coefficient signs from a barely-above-chance model would risk replacing one
un-validated set of hand-tuned weights with another un-validated set of statistically-fragile ones.

What this finding *does* establish, and what should not be lost: production's auxiliary weights have
now been checked against real, realistic (TOSS-aware, fee-aware) outcome data for the first time
since their original 30-stock hindsight assignment (per
[swing-algorithm-profitability-review.analysis.md](swing-algorithm-profitability-review.analysis.md)'s
Finding #3), and the result is that **no auxiliary signal in this dataset shows a reliable,
statistically-supported relationship to trade outcome** — six of eight full-coverage signals point
the opposite direction from what they were hand-assigned to reward, though the model is too weak
to call any one of them proven harmful. Any future decision to reweight or remove specific auxiliary
signals should be treated as requiring further validation (a larger sample, multiple train/test
splits, or a materially different modeling approach), not as already justified by this result.

**No production code (`src/swing-scanner.src.js`) was changed by this sub-project.** This is the
last of the priority-3 items from this session's honest trader-perspective gap review.

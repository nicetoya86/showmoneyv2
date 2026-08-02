# swing-algo-signal-weight-refit Design

> **Project**: showmoneyv2
> **Feature**: Swing Algo Enhancement Sub-project 10 — statistically re-fit the auxiliary
> scoring-signal weights against real backtest outcome data (priority-3 item from this
> session's honest trader-perspective gap review)
> **Prior work**: [swing-algorithm-profitability-review.analysis.md](../../03-analysis/swing-algorithm-profitability-review.analysis.md)
> (Finding #3: "Scoring weights are hand-tuned on a 30-stock hindsight sample, never
> statistically validated" — the gap this sub-project closes)
> **Date**: 2026-08-02

---

## 1. Context and Goal

`src/swing-scanner.src.js`'s scoring formula (and its faithful Python port,
`backtest/swing_signal_engine.py`) assigns points for ~11 auxiliary signal components on top of
the 4 pattern-identification base weights (C촉매=60, A눌림목=50, B지지선=45, D박스=40, plus combo
bonuses) — volume-multiple tier, OBV trend, MACD state, SMA20/60 alignment, intraday closing
strength, foreign/institutional net-buy tier, DART disclosure tier, RSI golden zone, ADX trend,
and 52-week-high proximity. Every one of these point values (25/18/12/6 for volume tiers, +20/-8
for OBV, etc.) was hand-assigned once, on a 30-stock hindsight review, and has never been checked
against the real backtest outcome data this research line has since accumulated.

**Scope decision, confirmed with the user this session**: this sub-project re-fits only the
**auxiliary signal weights** listed above. The four pattern base weights (60/50/45/40) and their
combo bonuses are held fixed — those have already been exhaustively examined via the
target/stop-tuning axis in sub-projects 7a/7b/8/9 (all four patterns individually target_not_met).
This sub-project targets a different, never-examined axis: whether the *modifier* weights on top
of pattern identification actually correlate with real trade outcomes.

**Goal**: fit an L2-regularized logistic regression predicting `pnl > 0` (the same win-rate
definition Line A already uses) from the 9 auxiliary signal features, using the same
959-ticker/2022-2026 universe and train/test discipline as every other sub-project in this line,
and report — honestly — whether the current hand-tuned weights are directionally supported,
contradicted, or statistically indistinguishable from noise.

## 2. A Data Gap Discovered This Session, and How This Design Closes It Minimally

Neither `backtest_candidates_with_paths.json` (Line B's cache) nor
`backtest_out_swing_v2_realistic.json` (Line A's committed trades) stores which individual signals
fired for a given candidate — only the final summed `score`. `SwingCandidate.signals` (a
`List[str]` of human-readable tags like `"거래량3x"`, `"RSI골든존"`) exists at generation time but
is not persisted to either cache.

**Parsing the `signals` tag list back into features is not sufficient**, and this is a real,
verified gap: `swing_signal_engine.py`'s OBV-negative case (`score -= 8` when `obvTrend == -1`,
line 208-209) has **no corresponding tag** — a candidate with negative OBV looks identical, in the
`signals` list, to one with neutral OBV. Every other score contributor has a matching tag; this
one is silent. Reconstructing features from tags alone would misclassify this one axis.

**Minimal fix**: add one new field to `SwingCandidate` —
```python
aux_features: Dict[str, object] = field(default_factory=dict)
```
with a **default value**, so this is purely additive: every existing call site that constructs
`SwingCandidate(...)` without this field (there are 5 in `backtest/tests/test_run_swing_v2_backtest.py`
and `test_run_swing_v2_backtest_exit_model.py`) continues to work unchanged. Only
`evaluate_candidate()`'s own construction (line 309) is extended to populate it, from variables
(`rvol`, `obv_result`, `macd_result`, `sma20`/`sma60`, `intraday_strength`, `frgn`/`org`,
`dart_items`, `rsi14_val`, `adx_result`, `current_price`/`high252`) already computed in scope at
that point — no new computation, just capturing values already calculated for the existing scoring
logic. This is the first sub-project in this research line to add a field to an existing
dataclass, but it changes zero existing behavior (default-guarded, additive only) — every prior
sub-project's tests and cached results remain valid and unaffected.

**`aux_features` keys and encodings** (ordinal/boolean, matching the score tiers exactly):
| Key | Type | Values | Matches score logic at |
|---|---|---|---|
| `rvol_tier` | int | 0 (none) / 1 (≥2x) / 2 (≥3x) / 3 (≥5x) / 4 (≥8x) | lines 192-203 |
| `obv_trend` | int | -1 / 0 / 1 | lines 205-209 |
| `macd_state` | str | `"golden_cross"` / `"macd_up"` / `"neutral"` | lines 211-217 (the hard-reject branch, 218-222, never reaches here — those candidates return `None` before `SwingCandidate` construction) |
| `sma_aligned` | bool | sma20 > sma60 | line 224 |
| `intraday_tier` | int | 0 (neither) / 1 (≥0.5) / 2 (≥0.7) | lines 227-232 |
| `supply_tier` | int | 0 (none) / 1 (기관만, org-only) / 2 (외국인만, frgn-only) / 3 (동반, both) | lines 234-243 |
| `dart_tier` | int | 0 (none) / 1 (당일공시, neutral) / 2 (긍정공시, positive) | lines 245-251 |
| `rsi_golden` | bool | 50 ≤ RSI14 ≤ 70 | lines 253-255 |
| `adx_trend` | bool | ADX ≥ 20 and +DI > -DI | lines 256-258 |
| `high52_tier` | int | 0 (neither) / 1 (near, ≥95%) / 2 (new high) | lines 259-264 |

## 3. Data Flow — Reusing Line A's Existing Pipeline, Not a New One

Because `aux_features` lives on `SwingCandidate` and `backtest/run_swing_v2_backtest.py::backtest_swing_v2()`
already constructs one `cand` per selected trade, the simplest and lowest-risk approach is to
thread `cand.aux_features` into the trade-record dict (the same pattern sub-project 8 used for
`tranches`) rather than writing an entirely new data-generation pipeline:

```
backtest/tickers_operating.txt (959 tickers) + existing local caches (cache/yahoo,
  backtest/cache/krx_supply, backtest/cache/dart — same universe/date-range already
  fetched for backtest_out_swing_v2_realistic.json and sub-project 8's partial-exit run)
  -> backtest_swing_v2(..., exit_model="binary")  [UNMODIFIED call path, only SwingCandidate
     gains the new field and the trade dict gains one new key]
  -> backtest_out_swing_v2_with_features.json (new committed artifact — same 2,686 trades as
     backtest_out_swing_v2_realistic.json, now each with an aux_features dict attached)

backtest_out_swing_v2_with_features.json
  -> backtest/fit_signal_weights.py (new script, uses scikit-learn)
       - train split 2022-01-01..2024-06-30 / test split 2024-07-01..2026-01-01 (same convention
         as every sub-project in this line)
       - L2-regularized logistic regression, target = pnl > 0
       - one-hot/ordinal-encode aux_features (rvol_tier and other ordinal ints get one-hot
         dummies, not raw integers, since the point-scale is not necessarily linear in tier index)
  -> backtest_signal_weight_fit.json (new committed artifact: coefficients, train/test AUC,
     current-vs-fitted directional comparison)

-> docs/03-analysis/swing-algo-signal-weight-refit.analysis.md (new)
```

**Why binary exit model, not sub-project 8's partial-exit model**: the partial-exit model's
trailing-stop fill price has a documented, unresolved optimism bias (see
`docs/03-analysis/swing-algo-partial-exit-simulation.analysis.md`'s Limitations) — using it as the
regression's label would inject that same bias into "which signals predict a win," making the
fitted weights harder to trust. The binary model is simpler and its only documented bias
(TOSS-quota slot-refund approximation, ~4% of trades) is smaller and already characterized. This
sub-project accepts the binary model's own limitations (same as every prior use of it in this
line) rather than compounding two different sets of exit-model uncertainty into one regression.

## 4. New Dependency: scikit-learn

`backtest/requirements.txt` currently lists only `pandas`/`numpy`/`requests`. This sub-project adds
`scikit-learn` — the first new dependency in this research line. Justification, confirmed with the
user this session: `scikit-learn`'s `LogisticRegression` is the standard, well-tested,
already-installed-in-this-sandbox tool for L2-regularized logistic regression; hand-rolling
IRLS/Newton's-method via `scipy.optimize` would be more code, harder to audit, and not more
correct than using the standard library everyone reviewing this analysis will recognize. This
dependency is research-script-only — it is never imported by anything under `src/` and does not
touch the production `n8n` Function-node runtime, so it carries none of that environment's "no
local `require`" constraint (see `src/swing-scanner.src.js`'s own top-of-file comment about the
n8n sandbox). Pin the version actually installed (`scikit-learn==1.5.2`, confirmed installed this
session) in `backtest/requirements.txt` with a one-line comment explaining the research-only scope.

## 5. Model Details

- **Target**: `pnl > 0` (binary), from `backtest_out_swing_v2_with_features.json`'s existing `pnl`
  field (already fee-adjusted, per Line A's existing convention — unchanged from
  `backtest_out_swing_v2_realistic.json`).
- **Features**: the 9 `aux_features` keys from Section 2, one-hot/dummy-encoded (drop-first to
  avoid the dummy-variable trap): `rvol_tier` (4 dummies), `obv_trend` (2 dummies), `macd_state` (2
  dummies), `sma_aligned` (1, already boolean), `intraday_tier` (2 dummies), `supply_tier` (3
  dummies), `dart_tier` (2 dummies), `rsi_golden` (1), `adx_trend` (1), `high52_tier` (2 dummies) —
  20 total feature columns. Also include `pattern_type` as a control (one-hot, 3 dummies) so the
  auxiliary-signal coefficients are estimated net of which pattern the candidate came from, not
  confounded by it — this does NOT mean pattern base weights are being refit (they still are not
  touched in production or reported as a recommendation), it only prevents "C촉매 candidates
  happen to have more DART tags" from leaking into the DART coefficient's estimate.
- **Regularization**: `LogisticRegression(penalty="l2", C=1.0, ...)` — scikit-learn's default `C`
  is a reasonable starting point given this is exploratory, not production-tuned; if train/test AUC
  diverge a lot, the analysis document should say so honestly rather than hand-picking a `C` that
  produces a nicer-looking result.
- **Evaluation, both splits, both reported**: AUC-ROC, and the actual fitted coefficient table
  (log-odds contribution per feature, translated to an approximate "points" scale by rescaling so
  the largest-magnitude coefficient matches the current hand-tuned scoring's largest single
  auxiliary weight, purely for intuitive comparison — the document must state plainly that this
  rescaling is for readability only, not a proposed literal replacement of the production point
  values).
- **No production code changes**: this sub-project produces a comparison and a recommendation, not
  a live reweighting. Whether to ever act on the finding is a separate, later decision — consistent
  with every other sub-project in this line.

## 6. Testing

This is the second sub-project in this line (after sub-project 8) to add new logic, not just data
— held to the normal engineering bar:
- `backtest/tests/test_swing_signal_engine.py` (existing file) gets new cases asserting
  `aux_features` is populated correctly for known signal combinations (e.g., a candidate
  constructed to have `rvol=6.0` should get `aux_features["rvol_tier"] == 3`; one with negative OBV
  should get `aux_features["obv_trend"] == -1`, closing exactly the gap Section 2 identified).
- Existing `SwingCandidate(...)` construction call sites in
  `backtest/tests/test_run_swing_v2_backtest.py` and `test_run_swing_v2_backtest_exit_model.py`
  must continue to pass unmodified (regression guard for the "purely additive" claim in Section 2).
- `backtest/fit_signal_weights.py` gets unit tests on its encoding logic (ordinal-to-dummy
  conversion) using small synthetic feature/outcome arrays with a known, hand-computable answer —
  not asserting on real backtest data (that's what the analysis document reports).

## 7. Limitations

- **Sample size and class imbalance**: ~2,686 trades total, ~32% positive class (`pnl>0`) under
  the binary model. A 20+1(pattern-control)-feature logistic regression on this sample size is
  workable but not generous — report standard errors or at least flag any coefficient whose sign
  flips between train and test as unreliable, don't present it as settled.
- **Correlated features**: several auxiliary signals plausibly co-occur (e.g. high rvol days often
  also show OBV↑ and strong intraday closing) — L2 regularization mitigates but does not eliminate
  the risk that correlated features split credit in a way that under-states either one's true
  individual effect. This is exactly why L2 (not unregularized OLS/logit) was chosen, per Section
  1's stated rationale, but it is a mitigation, not a cure.
- **Single train/test split**, same acknowledged limitation as every prior sub-project.
- **Binary exit model's own inherited limitations** (documented in
  `docs/03-analysis/swing-algorithm-profitability-review.analysis.md`): TOSS-quota slot-refund
  approximation (~4% of trades), flat transaction cost, KRX supply-API sandbox unavailability
  (`data.krx.co.kr` returns HTTP 400 in this sandbox for every call, per that document's §Limitations
  — meaning `supply_tier` will be `0` for essentially every historical candidate; the
  supply-based score bonuses "never fired anywhere in this backtest" per that document's exact
  wording) and DART near-non-coverage (that same document found only ~18 of 1,202 original trades
  had any same-day DART disclosure at all, ~2 with a positive keyword — so `dart_tier` will also be
  overwhelmingly `0`). **Both `supply_tier` and `dart_tier` must be flagged explicitly in the
  analysis document as having too little non-zero variance in this sandbox's data for their fitted
  coefficients to be trustworthy** — a feature that's constant (or ~98% constant) across the
  training set cannot have its weight meaningfully estimated, regardless of what the regression
  numerically outputs for it.
- **Correlational, not causal**: even a well-fit model shows association between signals and
  outcome in this historical sample, not a proof any single signal *causes* better trades — a
  standard caveat for any observational analysis, worth stating plainly rather than assumed
  understood.
- **This does not re-examine pattern base weights or target/stop parameters** — those remain
  covered by sub-projects 7a/7b/7c/9 (patterns) and this research line's earlier target/stop grid
  searches. This sub-project is scoped to the auxiliary signal weights only, per Section 1's
  confirmed decision.

No production code (`src/swing-scanner.src.js`) is changed by this sub-project.

# swing-algo-signal-weight-refit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Statistically re-fit the auxiliary scoring-signal weights (volume tier, OBV, MACD,
SMA alignment, intraday strength, supply, DART, RSI, ADX, 52-week-high proximity) against real
backtest outcome data, using an L2-regularized logistic regression, and report — honestly —
whether the current hand-tuned point values are supported, contradicted, or statistically
indistinguishable from noise. Pattern base weights (60/50/45/40) are NOT touched or refit.

**Architecture:** Add one additive, default-guarded field (`aux_features`) to the existing
`SwingCandidate` dataclass, populate it inline in `evaluate_candidate()` at the exact points each
score component is already computed (no new computation, no behavior change to score/signals/grade/
target/stop). Thread it through `backtest_swing_v2()`'s existing trade dict (same pattern
sub-project 8 used for `tranches`). Re-run the existing binary-exit backtest to produce a dataset
with both real outcomes and features. Fit the regression in a new, separate script.

**Tech Stack:** Python, pandas, numpy, scikit-learn (new dependency, research-script-only — see
Global Constraints). No changes to `src/swing-scanner.src.js`.

## Global Constraints

- **No production code (`src/swing-scanner.src.js`) is touched.** This sub-project produces a
  research recommendation, not a live reweighting.
- **`SwingCandidate`'s new `aux_features` field must have a default** (`field(default_factory=dict)`)
  so every existing call site that constructs `SwingCandidate(...)` without it — five of them, in
  `backtest/tests/test_run_swing_v2_backtest.py` and `test_run_swing_v2_backtest_exit_model.py` —
  continues to work completely unmodified. This is the regression guard for the "purely additive"
  claim; do not add a required (no-default) field.
- **Pattern base weights, combo bonuses, target/stop formulas, and grade logic are unchanged.**
  Only the auxiliary signal score branches (lines 192-264 of `backtest/swing_signal_engine.py` as
  of this session) gain an extra statement recording their already-computed value into
  `aux_features` — the `score +=`/`signals.append(...)` calls themselves are untouched.
- **`aux_features` keys and encodings** (exact, from the design doc):
  - `rvol_tier`: int, 0/1/2/3/4 (none / ≥2x / ≥3x / ≥5x / ≥8x)
  - `obv_trend`: int, -1/0/1
  - `macd_state`: str, `"golden_cross"` / `"macd_up"` / `"neutral"`
  - `sma_aligned`: bool
  - `intraday_tier`: int, 0/1/2 (neither / ≥0.5 / ≥0.7)
  - `supply_tier`: int, 0/1/2/3 (none / 기관만 / 외국인만 / 동반)
  - `dart_tier`: int, 0/1/2 (none / 당일공시 / 긍정공시)
  - `rsi_golden`: bool
  - `adx_trend`: bool
  - `high52_tier`: int, 0/1/2 (neither / near / new high)
- **Binary exit model only** (`exit_model="binary"`, the default) — never the partial-exit model
  from sub-project 8, per the design doc's documented reason (partial-exit's trailing-fill
  optimism bias would contaminate the regression's labels).
- **Same universe/date-range as every prior Line A run**: `backtest/tickers_operating.txt` (959
  tickers), `2022-01-01`..`2026-01-01`, same train (`2022-01-01`..`2024-06-30`) / test
  (`2024-07-01`..`2026-01-01`) split as every sub-project in this line.
- **`scikit-learn` is a new dependency, scoped to `backtest/` research scripts only** — add
  `scikit-learn==1.5.2` (the version already installed in this sandbox) to
  `backtest/requirements.txt` with a one-line comment. Never imported from anything under `src/`.
- No bracket placeholders or invented numbers in the final analysis document (Task 5) — every
  number must trace to a JSON file this plan commits.
- Work directly on `main`, no feature branch — matches this research line's established
  convention.

---

### Task 1: Add `aux_features` to `SwingCandidate`, populate in `evaluate_candidate()`

**Files:**
- Modify: `backtest/swing_signal_engine.py` (the `SwingCandidate` dataclass at line 48-58, and
  `evaluate_candidate()`'s scoring block at lines 170-264 and its `return SwingCandidate(...)` at
  line 309-319)
- Test: `backtest/tests/test_swing_signal_engine.py` (existing file, add new test functions)

**Interfaces:**
- Produces: `SwingCandidate.aux_features: Dict[str, object]`, always populated with exactly the 10
  keys listed in Global Constraints (never a partial dict — every key gets a value on every
  successful `evaluate_candidate()` call, using the tier/state values from Global Constraints).
  Task 2 consumes this field by reading `cand.aux_features` directly.

- [ ] **Step 1: Write the failing tests**

Add to `backtest/tests/test_swing_signal_engine.py` (this file already has a `_flat_df` helper and
a `test_pattern_d_box_breakout_produces_candidate` fixture that reliably produces a valid
`SwingCandidate` — reuse that exact fixture construction for the consistency checks below, since
it is already proven to produce a real candidate):

```python
def _assert_aux_features_consistent_with_signals(result):
    """Cross-checks that aux_features (the new structured field) agrees with signals (the
    existing, already-correct tag list) for every tiered/boolean component that has a
    corresponding tag. This does not require hand-predicting rvol/RSI/ADX/OBV from OHLC math --
    it only requires that the NEW field never contradicts the OLD, already-tested field."""
    signals = result.signals
    aux = result.aux_features

    assert set(aux.keys()) == {
        "rvol_tier", "obv_trend", "macd_state", "sma_aligned", "intraday_tier",
        "supply_tier", "dart_tier", "rsi_golden", "adx_trend", "high52_tier",
    }

    if "거래량8x+" in signals:
        assert aux["rvol_tier"] == 4
    elif "거래량5x" in signals:
        assert aux["rvol_tier"] == 3
    elif "거래량3x" in signals:
        assert aux["rvol_tier"] == 2
    elif "거래량2x" in signals:
        assert aux["rvol_tier"] == 1
    else:
        assert aux["rvol_tier"] == 0

    if "OBV수급↑" in signals:
        assert aux["obv_trend"] == 1
    # NOTE: obv_trend == -1 has NO corresponding tag (this is the exact gap this sub-project's
    # design doc identified) -- covered by test_obv_negative_is_captured_even_without_a_tag below,
    # not by this generic consistency check.

    if "MACD골든크로스" in signals:
        assert aux["macd_state"] == "golden_cross"
    elif "MACD↑" in signals:
        assert aux["macd_state"] == "macd_up"
    else:
        assert aux["macd_state"] == "neutral"

    assert aux["sma_aligned"] == ("일봉정배열" in signals)

    if "장마감강세" in signals:
        assert aux["intraday_tier"] == 2
    elif "장마감양호" in signals:
        assert aux["intraday_tier"] == 1
    else:
        assert aux["intraday_tier"] == 0

    if "외국인+기관동반" in signals:
        assert aux["supply_tier"] == 3
    elif "외국인순매수" in signals:
        assert aux["supply_tier"] == 2
    elif "기관순매수" in signals:
        assert aux["supply_tier"] == 1
    else:
        assert aux["supply_tier"] == 0

    if "긍정공시" in signals:
        assert aux["dart_tier"] == 2
    elif "당일공시" in signals:
        assert aux["dart_tier"] == 1
    else:
        assert aux["dart_tier"] == 0

    assert aux["rsi_golden"] == ("RSI골든존" in signals)
    assert aux["adx_trend"] == ("ADX추세↑" in signals)

    if "52주신고가" in signals:
        assert aux["high52_tier"] == 2
    elif "신고가근접" in signals:
        assert aux["high52_tier"] == 1
    else:
        assert aux["high52_tier"] == 0


def test_aux_features_consistent_with_signals_on_d_box_fixture():
    n = 300
    df = _flat_df(n=n, base=10000.0)
    df.loc[n - 1, "close"] = 11000.0
    df.loc[n - 1, "open"] = 10050.0
    df.loc[n - 1, "high"] = 11050.0
    df.loc[n - 1, "low"] = 10000.0
    df.loc[n - 1, "volume"] = 2_000_000.0 * 3.0
    for i in range(n - 60, n - 1):
        df.loc[i, "close"] = 10000.0 + (i - (n - 60)) * 2.0
        df.loc[i, "open"] = df.loc[i, "close"]
        df.loc[i, "high"] = df.loc[i, "close"] * 1.001
        df.loc[i, "low"] = df.loc[i, "close"] * 0.999

    result = evaluate_candidate(df, n - 1, supply={}, dart_items=[], day_of_week=2)
    assert result is not None
    _assert_aux_features_consistent_with_signals(result)


def test_aux_features_consistent_with_signals_with_supply_and_dart():
    n = 300
    df = _flat_df(n=n, base=10000.0)
    df.loc[n - 1, "close"] = 11000.0
    df.loc[n - 1, "open"] = 10050.0
    df.loc[n - 1, "high"] = 11050.0
    df.loc[n - 1, "low"] = 10000.0
    df.loc[n - 1, "volume"] = 2_000_000.0 * 3.0
    for i in range(n - 60, n - 1):
        df.loc[i, "close"] = 10000.0 + (i - (n - 60)) * 2.0
        df.loc[i, "open"] = df.loc[i, "close"]
        df.loc[i, "high"] = df.loc[i, "close"] * 1.001
        df.loc[i, "low"] = df.loc[i, "close"] * 0.999

    result = evaluate_candidate(
        df, n - 1,
        supply={"frgn": 600_000_000, "org": 600_000_000},
        dart_items=["계약체결 공시"],
        day_of_week=2,
    )
    assert result is not None
    assert result.aux_features["supply_tier"] == 3  # both frgn and org > 500M -> 외국인+기관동반
    assert result.aux_features["dart_tier"] == 2     # "계약체결" matches the positive-keyword regex
    _assert_aux_features_consistent_with_signals(result)


def test_obv_negative_is_captured_even_without_a_tag():
    """The critical case this sub-project's design doc identified: obvTrend == -1 subtracts
    score (line 208-209 of swing_signal_engine.py) but appends NO signal tag, so aux_features is
    the only way to observe it. Construct a price series whose most recent 5 bars show
    net-negative OBV momentum relative to the preceding 5 bars (declining closes on rising
    volume, per backtest/indicators.py::obv()'s slope formula), combined with a D박스 breakout on
    the final bar so a candidate is still produced.

    NOTE FOR IMPLEMENTER: this fixture is a best-effort construction, not a hand-verified one --
    OBV's rolling 5-bar-average-vs-prior-5-bar-average slope is not simple to predict by hand.
    Run this test after implementing Step 3; if `result.aux_features["obv_trend"]` is not -1,
    print `df.tail(15)` and adjust the decline's steepness/volume in the `n-15..n-2` range (NOT
    the final breakout bar, which must stay as specified for the D박스 pattern to still fire)
    until it is. This iteration is expected, not a sign the plan is wrong.
    """
    n = 300
    df = _flat_df(n=n, base=10000.0)
    for i in range(n - 60, n - 1):
        df.loc[i, "close"] = 10000.0 + (i - (n - 60)) * 2.0
        df.loc[i, "open"] = df.loc[i, "close"]
        df.loc[i, "high"] = df.loc[i, "close"] * 1.001
        df.loc[i, "low"] = df.loc[i, "close"] * 0.999
    # Override the last 14 bars (before the breakout bar) with a declining-price/rising-volume
    # run to push recent OBV below prior OBV.
    for i in range(n - 15, n - 1):
        step = i - (n - 15)
        df.loc[i, "close"] = 10000.0 + (n - 60 - (n - 15)) * 2.0 - step * 15.0
        df.loc[i, "open"] = df.loc[i, "close"] + 5.0
        df.loc[i, "high"] = df.loc[i, "close"] * 1.001
        df.loc[i, "low"] = df.loc[i, "close"] * 0.998
        df.loc[i, "volume"] = 2_000_000.0 * (1.0 + step * 0.1)
    # Breakout bar (must stay strong enough to still fire D박스 and clear MIN_SCORE_FINAL).
    df.loc[n - 1, "close"] = 11500.0
    df.loc[n - 1, "open"] = 10100.0
    df.loc[n - 1, "high"] = 11550.0
    df.loc[n - 1, "low"] = 10050.0
    df.loc[n - 1, "volume"] = 2_000_000.0 * 4.0

    result = evaluate_candidate(df, n - 1, supply={}, dart_items=[], day_of_week=2)
    assert result is not None
    assert result.aux_features["obv_trend"] == -1
    assert "OBV수급↑" not in result.signals  # confirms the no-tag gap: no positive tag either


def test_swing_candidate_construction_without_aux_features_still_works():
    """Regression guard: existing call sites across the test suite construct SwingCandidate(...)
    without aux_features. This must keep working unmodified after this task."""
    from backtest.swing_signal_engine import SwingCandidate
    c = SwingCandidate(
        pattern_type="D박스", score=100, rank_score=100, grade="매수",
        entry=1000.0, target=1100.0, stop=960.0, hold_days=4, signals=[],
    )
    assert c.aux_features == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_swing_signal_engine.py -v`
Expected: FAIL — `AttributeError: 'SwingCandidate' object has no attribute 'aux_features'` (or a
`TypeError` on construction) for the new tests; the pre-existing tests in this file continue to
pass unchanged (they don't reference `aux_features` at all).

- [ ] **Step 3: Implement**

In `backtest/swing_signal_engine.py`, add the import and field:

```python
from dataclasses import dataclass, field
```

```python
@dataclass(frozen=True)
class SwingCandidate:
    pattern_type: str
    score: int
    rank_score: int
    grade: str
    entry: float
    target: float
    stop: float
    hold_days: int
    signals: List[str]
    aux_features: Dict[str, object] = field(default_factory=dict)
```

In `evaluate_candidate()`, initialize `aux_features: Dict[str, object] = {}` alongside the existing
`signals: List[str] = []` at the top of the scoring block (around line 172), then add one line to
each branch recording the already-computed tier/state (every `if`/`elif` gets an `aux_features[...]
= ...` line; every branch that currently has no `else` gets one added purely to set the
zero/neutral value — this does not change `score` or `signals` at all):

```python
    aux_features: Dict[str, object] = {}

    if rvol >= 8.0:
        score += 25
        signals.append("거래량8x+")
        aux_features["rvol_tier"] = 4
    elif rvol >= 5.0:
        score += 18
        signals.append("거래량5x")
        aux_features["rvol_tier"] = 3
    elif rvol >= 3.0:
        score += 12
        signals.append("거래량3x")
        aux_features["rvol_tier"] = 2
    elif rvol >= 2.0:
        score += 6
        signals.append("거래량2x")
        aux_features["rvol_tier"] = 1
    else:
        aux_features["rvol_tier"] = 0

    if obv_result["obvTrend"] == 1:
        score += 20
        signals.append("OBV수급↑")
        aux_features["obv_trend"] = 1
    elif obv_result["obvTrend"] == -1:
        score -= 8
        aux_features["obv_trend"] = -1
    else:
        aux_features["obv_trend"] = 0

    if macd_result["goldenCross"]:
        score += 15
        signals.append("MACD골든크로스")
        aux_features["macd_state"] = "golden_cross"
    elif np.isfinite(macd_result["hist"]) and macd_result["hist"] > 0:
        if np.isfinite(macd_result["histPrev"]) and macd_result["hist"] > macd_result["histPrev"]:
            score += 10
            signals.append("MACD↑")
            aux_features["macd_state"] = "macd_up"
        else:
            aux_features["macd_state"] = "neutral"
    elif (
        np.isfinite(macd_result["hist"]) and np.isfinite(macd_result["histPrev"])
        and macd_result["hist"] < 0 and macd_result["histPrev"] < 0 and not is_c
    ):
        return None
    else:
        aux_features["macd_state"] = "neutral"

    if sma20[idx] > sma60[idx]:
        score += 15
        signals.append("일봉정배열")
        aux_features["sma_aligned"] = True
    else:
        aux_features["sma_aligned"] = False

    if intraday_strength >= 0.7:
        score += 12
        signals.append("장마감강세")
        aux_features["intraday_tier"] = 2
    elif intraday_strength >= 0.5:
        score += 6
        signals.append("장마감양호")
        aux_features["intraday_tier"] = 1
    else:
        aux_features["intraday_tier"] = 0

    frgn, org = supply.get("frgn", 0), supply.get("org", 0)
    if frgn > 500_000_000 and org > 500_000_000:
        score += 20
        signals.append("외국인+기관동반")
        aux_features["supply_tier"] = 3
    elif frgn > 500_000_000:
        score += 12
        signals.append("외국인순매수")
        aux_features["supply_tier"] = 2
    elif org > 500_000_000:
        score += 8
        signals.append("기관순매수")
        aux_features["supply_tier"] = 1
    else:
        aux_features["supply_tier"] = 0

    if dart_items:
        if _re.search(POSITIVE_DART_RE, " ".join(dart_items)):
            score += 20
            signals.append("긍정공시")
            aux_features["dart_tier"] = 2
        else:
            score += 5
            signals.append("당일공시")
            aux_features["dart_tier"] = 1
    else:
        aux_features["dart_tier"] = 0

    if np.isfinite(rsi14_val) and 50 <= rsi14_val <= 70:
        score += 8
        signals.append("RSI골든존")
        aux_features["rsi_golden"] = True
    else:
        aux_features["rsi_golden"] = False

    if np.isfinite(adx_result["adx"]) and adx_result["adx"] >= 20 and adx_result["plusDI"] > adx_result["minusDI"]:
        score += 10
        signals.append("ADX추세↑")
        aux_features["adx_trend"] = True
    else:
        aux_features["adx_trend"] = False

    if current_price >= high252:
        score += 25
        signals.append("52주신고가")
        aux_features["high52_tier"] = 2
    elif high252 > 0 and current_price / high252 >= 0.95:
        score += 10
        signals.append("신고가근접")
        aux_features["high52_tier"] = 1
    else:
        aux_features["high52_tier"] = 0
```

**Important**: this replaces the existing lines 192-264 block entirely (every `if`/`elif` gets its
extra `aux_features[...]` line and the `else` branches are new) — the numeric conditions
(`>= 8.0`, `> 500_000_000`, etc.) and every `score +=`/`signals.append(...)` call are copied
verbatim from the current file, not altered. Then update the final `return SwingCandidate(...)`
(line 309-319) to pass it through:

```python
    return SwingCandidate(
        pattern_type=pattern_type,
        score=score,
        rank_score=rank_score,
        grade=grade,
        entry=current_price,
        target=target,
        stop=stop,
        hold_days=_hold_days(grade, pattern_type),
        signals=signals,
        aux_features=aux_features,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_swing_signal_engine.py -v`
Expected: PASS. If `test_obv_negative_is_captured_even_without_a_tag` fails because
`obv_trend != -1`, follow the iteration note in that test's docstring — print `df.tail(15)` and
the computed `obv_result`, adjust the decline/volume ramp in the `n-15..n-2` range until the
slope crosses the `-0.005` threshold in `backtest/indicators.py::obv()`. Do not weaken the
assertion instead of fixing the fixture.

- [ ] **Step 5: Run the full existing test suite to confirm no regressions**

Run: `python -m pytest backtest/tests/test_swing_signal_engine.py backtest/tests/test_run_swing_v2_backtest.py backtest/tests/test_run_swing_v2_backtest_exit_model.py backtest/tests/test_target_stop_grid_search.py -v`
Expected: PASS, all files — this is the regression guard confirming every existing
`SwingCandidate(...)` construction site (the 5 in the run_swing_v2_backtest test files, plus
whatever `target_stop_grid_search` tests construct `CachedCandidate` from, which is unaffected
since `CachedCandidate` is a separate dataclass) still works.

- [ ] **Step 6: Commit**

```bash
git add backtest/swing_signal_engine.py backtest/tests/test_swing_signal_engine.py
git commit -m "feat(backtest): add aux_features to SwingCandidate (additive, default-guarded)"
```

---

### Task 2: Thread `aux_features` into `backtest_swing_v2()`'s trade records

**Files:**
- Modify: `backtest/run_swing_v2_backtest.py`
- Test: `backtest/tests/test_run_swing_v2_backtest_exit_model.py` (add one test) — or create
  `backtest/tests/test_run_swing_v2_backtest_aux_features.py` if you prefer a separate file; either
  is fine, just don't duplicate the existing monkeypatch fixture pattern incorrectly.

**Interfaces:**
- Consumes: `SwingCandidate.aux_features` (Task 1).
- Produces: every trade dict `backtest_swing_v2()` appends to its `trades` list now includes an
  `"aux_features"` key (a `dict`, always present — unlike `"tranches"` from sub-project 8, which
  was conditional on `exit_model`, this key is unconditional since `aux_features` is populated
  regardless of exit model).

- [ ] **Step 1: Write the failing test**

Create `backtest/tests/test_run_swing_v2_backtest_aux_features.py`, following the exact
monkeypatch/fixture pattern from `backtest/tests/test_run_swing_v2_backtest.py::test_backtest_swing_v2_records_toss_status_and_net_pnl`:

```python
import pandas as pd

from backtest.run_swing_v2_backtest import backtest_swing_v2


def test_trade_records_include_aux_features(monkeypatch):
    from backtest import run_swing_v2_backtest as mod

    ticker = "000004.KS"
    df = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04"], utc=True
        ),
        "open": [100.0, 101.0, 101.0],
        "high": [101.0, 102.0, 115.0],
        "low": [99.0, 100.0, 100.0],
        "close": [100.0, 101.0, 112.0],
        "volume": [1_000_000.0, 1_000_000.0, 1_000_000.0],
    })

    monkeypatch.setattr(mod, "fetch_yahoo_chart", lambda spec: {"_fake_for": spec.ticker})
    monkeypatch.setattr(mod, "chart_to_ohlcv_daily", lambda data: (df.copy(), None))
    monkeypatch.setattr(mod, "fetch_supply_for_date", lambda trd_dd: {})
    monkeypatch.setattr(mod, "fetch_disclosures_for_date", lambda trd_dd, api_key: {})

    from backtest.swing_signal_engine import SwingCandidate

    def fake_evaluate_candidate(df_arg, idx, *, supply, dart_items, day_of_week):
        if idx != 1:
            return None
        return SwingCandidate(
            pattern_type="D박스", score=100, rank_score=100, grade="매수",
            entry=100.0, target=110.0, stop=90.0, hold_days=3, signals=[],
            aux_features={
                "rvol_tier": 2, "obv_trend": 1, "macd_state": "golden_cross",
                "sma_aligned": True, "intraday_tier": 2, "supply_tier": 0,
                "dart_tier": 0, "rsi_golden": True, "adx_trend": False, "high52_tier": 0,
            },
        )

    monkeypatch.setattr(mod, "evaluate_candidate", fake_evaluate_candidate)

    df_trades, stats = backtest_swing_v2([ticker], start="2024-01-01", end="2024-01-05")
    assert stats["trades"] == 1
    row = df_trades.iloc[0]
    assert row["aux_features"] == {
        "rvol_tier": 2, "obv_trend": 1, "macd_state": "golden_cross",
        "sma_aligned": True, "intraday_tier": 2, "supply_tier": 0,
        "dart_tier": 0, "rsi_golden": True, "adx_trend": False, "high52_tier": 0,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backtest/tests/test_run_swing_v2_backtest_aux_features.py -v`
Expected: FAIL — `KeyError: 'aux_features'` (the trade dict doesn't have this key yet).

- [ ] **Step 3: Implement**

In `backtest/run_swing_v2_backtest.py`, find the `trades.append({...})` block (the one that already
has the conditional `**({"tranches": sim["tranches"]} if "tranches" in sim else {})` line from
sub-project 8) and add one unconditional key:

```python
            trades.append({
                "date": day.isoformat(), "ticker": ticker, "code": code,
                "pattern_type": cand.pattern_type, "grade": cand.grade,
                "score": cand.score, "rank_score": cand.rank_score,
                "entry": toss.entry, "stop": toss.stop, "target": toss.target,
                "exit_price": float(sim["exit_price"]), "result": sim["result"],
                "days_held": sim["days_held"], "pnl": pnl,
                "gross_pnl": gross_pnl, "toss_status": toss.status,
                "aux_features": cand.aux_features,
                **({"tranches": sim["tranches"]} if "tranches" in sim else {}),
            })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_run_swing_v2_backtest_aux_features.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full existing backtest test suite to confirm no regressions**

Run: `python -m pytest backtest/tests/test_run_swing_v2_backtest.py backtest/tests/test_run_swing_v2_backtest_exit_model.py -v`
Expected: PASS, unchanged (13 tests total from sub-project 8's state) — `aux_features` is a new
key added to every trade dict, which does not break any existing assertion that reads specific
keys rather than asserting the dict's exact key set.

- [ ] **Step 6: Commit**

```bash
git add backtest/run_swing_v2_backtest.py backtest/tests/test_run_swing_v2_backtest_aux_features.py
git commit -m "feat(backtest): thread aux_features into backtest_swing_v2 trade records"
```

---

### Task 3: Run the real backtest to produce the labeled feature dataset

**Files:** none created except the output JSON — this is an execution-only task.

**Interfaces:**
- Consumes: `backtest_swing_v2(..., exit_model="binary")` (default, Tasks 1-2's changes),
  `backtest/tickers_operating.txt`, local caches (already populated from prior sub-projects' runs
  over the identical universe/date-range).

- [ ] **Step 1: Run the backtest**

```bash
python -m backtest.run_swing_v2_backtest --tickers backtest/tickers_operating.txt --start 2022-01-01 --end 2026-01-01 --out backtest_out_swing_v2_with_features.json
```

(Note: no `--exit-model` flag needed — `binary` is the default.) Expected: completes without
exception, should run substantially from local cache (same universe/date-range as
`backtest_out_swing_v2_realistic.json` and sub-project 8's partial-exit run) — no fresh network
fetches expected beyond the small number of known Yahoo 404s for delisted tickers seen in prior
runs.

- [ ] **Step 2: Sanity-check against the existing binary-model baseline**

```bash
python -c "
import json
a = json.load(open('backtest_out_swing_v2_realistic.json', encoding='utf-8'))
b = json.load(open('backtest_out_swing_v2_with_features.json', encoding='utf-8'))
print('baseline trades:', a['stats']['trades'], 'win_rate:', a['stats']['win_rate'], 'avg_pnl:', a['stats']['avg_pnl'])
print('with-features trades:', b['stats']['trades'], 'win_rate:', b['stats']['win_rate'], 'avg_pnl:', b['stats']['avg_pnl'])
missing = sum(1 for t in b['trades'] if 'aux_features' not in t or not t['aux_features'])
print('trades missing aux_features:', missing, 'of', len(b['trades']))
"
```

Expected: `trades`/`win_rate`/`avg_pnl` **exactly match** `backtest_out_swing_v2_realistic.json`
(this run uses the identical default `exit_model="binary"` path, unmodified by this plan's Tasks
1-2 per the Global Constraints — Task 1/2's changes are additive-only) — any divergence at all
means something in Tasks 1-2 accidentally changed existing behavior, and must be investigated
before proceeding, not pushed through. `trades missing aux_features` must be `0`.

- [ ] **Step 3: Commit**

```bash
git add backtest_out_swing_v2_with_features.json
git commit -m "data(backtest): re-run binary backtest with aux_features captured per trade (sub-project 10)"
```

---

### Task 4: Fit the L2-regularized logistic regression

**Files:**
- Create: `backtest/fit_signal_weights.py`
- Test: `backtest/tests/test_fit_signal_weights.py`
- Modify: `backtest/requirements.txt`

**Interfaces:**
- Consumes: `backtest_out_swing_v2_with_features.json` (Task 3).
- Produces: `encode_features(trades: List[Dict]) -> Tuple[pd.DataFrame, pd.Series]` (returns a
  one-hot/dummy-encoded feature matrix and a `pnl > 0` label series) and
  `fit_and_evaluate(train_df, train_y, test_df, test_y) -> Dict[str, Any]` (fits
  `sklearn.linear_model.LogisticRegression`, returns coefficients + train/test AUC). Both are
  pure functions the test file exercises directly with small synthetic inputs — no real backtest
  data needed for the tests themselves.

- [ ] **Step 1: Add the new dependency**

In `backtest/requirements.txt`, add:
```
scikit-learn==1.5.2  # sub-project 10 only: L2-regularized logistic regression for signal-weight
                     # refit research script. Never imported from src/ or the n8n runtime.
```

- [ ] **Step 2: Write the failing tests**

Create `backtest/tests/test_fit_signal_weights.py`:

```python
import pandas as pd

from backtest.fit_signal_weights import encode_features, fit_and_evaluate


def _trade(pattern_type, pnl, **aux_overrides):
    aux = {
        "rvol_tier": 0, "obv_trend": 0, "macd_state": "neutral", "sma_aligned": False,
        "intraday_tier": 0, "supply_tier": 0, "dart_tier": 0, "rsi_golden": False,
        "adx_trend": False, "high52_tier": 0,
    }
    aux.update(aux_overrides)
    return {"pattern_type": pattern_type, "pnl": pnl, "aux_features": aux}


def test_encode_features_produces_expected_columns():
    trades = [
        _trade("D박스", 0.05, rvol_tier=2, obv_trend=1, sma_aligned=True),
        _trade("A눌림목", -0.03, rvol_tier=0, obv_trend=-1, sma_aligned=False),
    ]
    X, y = encode_features(trades)
    assert len(X) == 2
    assert list(y) == [True, False]
    # one-hot dummy columns must exist for the non-default levels actually observed
    assert any(c.startswith("rvol_tier_") for c in X.columns)
    assert any(c.startswith("pattern_type_") for c in X.columns)
    assert "sma_aligned" in X.columns  # boolean features are not dummy-expanded


def test_encode_features_handles_missing_aux_features_gracefully():
    # a trade with an empty aux_features dict (shouldn't happen post-Task-3, but the encoder
    # must not crash on it -- treat every key as its zero/neutral default)
    trades = [{"pattern_type": "D박스", "pnl": 0.02, "aux_features": {}}]
    X, y = encode_features(trades)
    assert len(X) == 1


def test_fit_and_evaluate_returns_coefficients_and_auc():
    import numpy as np
    rng = np.random.RandomState(0)
    n = 200
    trades = []
    for i in range(n):
        rvol_tier = int(rng.randint(0, 5))
        # construct a clear, learnable relationship: higher rvol_tier -> more often a win
        pnl = 0.05 if rng.random() < (0.2 + 0.15 * rvol_tier) else -0.03
        trades.append(_trade("D박스", pnl, rvol_tier=rvol_tier))
    X, y = encode_features(trades)
    split = n // 2
    result = fit_and_evaluate(X.iloc[:split], y.iloc[:split], X.iloc[split:], y.iloc[split:])
    assert "coefficients" in result
    assert "train_auc" in result and "test_auc" in result
    assert 0.5 <= result["train_auc"] <= 1.0
    # rvol_tier's dummy columns should have a positive coefficient given the constructed
    # relationship (higher tier -> more wins) -- at least one rvol_tier_* coefficient > 0
    rvol_coefs = [v for k, v in result["coefficients"].items() if k.startswith("rvol_tier_")]
    assert any(c > 0 for c in rvol_coefs)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest backtest/tests/test_fit_signal_weights.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.fit_signal_weights'`.

- [ ] **Step 4: Implement `backtest/fit_signal_weights.py`**

```python
"""
Sub-project 10: fits an L2-regularized logistic regression predicting `pnl > 0` from the
auxiliary scoring-signal features (aux_features on each committed trade record), to check
whether src/swing-scanner.src.js's hand-tuned auxiliary weights (never statistically validated,
per docs/03-analysis/swing-algorithm-profitability-review.analysis.md Finding #3) are supported
by real backtest outcome data. Pattern base weights (60/50/45/40) are NOT refit here -- see
docs/superpowers/specs/2026-08-02-swing-algo-signal-weight-refit-design.md Section 1 for the
confirmed scope decision.

Does not change any production code or recommend a literal weight replacement -- see that
design doc's Section 5.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score


def encode_features(trades: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, pd.Series]:
    rows = []
    labels = []
    for t in trades:
        aux = t.get("aux_features") or {}
        row = {
            "pattern_type": t["pattern_type"],
            "rvol_tier": aux.get("rvol_tier", 0),
            "obv_trend": aux.get("obv_trend", 0),
            "macd_state": aux.get("macd_state", "neutral"),
            "sma_aligned": bool(aux.get("sma_aligned", False)),
            "intraday_tier": aux.get("intraday_tier", 0),
            "supply_tier": aux.get("supply_tier", 0),
            "dart_tier": aux.get("dart_tier", 0),
            "rsi_golden": bool(aux.get("rsi_golden", False)),
            "adx_trend": bool(aux.get("adx_trend", False)),
            "high52_tier": aux.get("high52_tier", 0),
        }
        rows.append(row)
        labels.append(t["pnl"] > 0)

    df = pd.DataFrame(rows)
    # rvol_tier/obv_trend/intraday_tier/supply_tier/dart_tier/high52_tier are ordinal ints but
    # not assumed linear in score contribution -- one-hot them; macd_state/pattern_type are
    # already categorical strings.
    dummy_cols = ["pattern_type", "rvol_tier", "obv_trend", "macd_state", "intraday_tier",
                  "supply_tier", "dart_tier", "high52_tier"]
    X = pd.get_dummies(df, columns=dummy_cols, drop_first=True)
    y = pd.Series(labels, name="win")
    return X, y


def fit_and_evaluate(
    train_X: pd.DataFrame, train_y: pd.Series, test_X: pd.DataFrame, test_y: pd.Series,
) -> Dict[str, Any]:
    # Align columns in case train/test one-hot encoding produced different dummy sets (a level
    # present in one split but not the other) -- reindex test to train's columns, filling 0.
    test_X = test_X.reindex(columns=train_X.columns, fill_value=0)

    model = LogisticRegression(penalty="l2", C=1.0, max_iter=1000)
    model.fit(train_X, train_y)

    train_pred = model.predict_proba(train_X)[:, 1]
    test_pred = model.predict_proba(test_X)[:, 1]

    coefficients = dict(zip(train_X.columns, model.coef_[0].tolist()))
    coefficients["intercept"] = float(model.intercept_[0])

    return {
        "coefficients": coefficients,
        "train_auc": float(roc_auc_score(train_y, train_pred)),
        "test_auc": float(roc_auc_score(test_y, test_pred)),
        "n_train": int(len(train_y)),
        "n_test": int(len(test_y)),
        "train_positive_rate": float(train_y.mean()),
        "test_positive_rate": float(test_y.mean()),
    }


def main() -> None:
    d = json.load(open("backtest_out_swing_v2_with_features.json", encoding="utf-8"))
    trades = d["trades"]

    train_trades = [t for t in trades if "2022-01-01" <= t["date"] <= "2024-06-30"]
    test_trades = [t for t in trades if "2024-07-01" <= t["date"] <= "2026-01-01"]
    print(f"train trades: {len(train_trades)}  test trades: {len(test_trades)}")

    train_X, train_y = encode_features(train_trades)
    test_X, test_y = encode_features(test_trades)

    result = fit_and_evaluate(train_X, train_y, test_X, test_y)
    print(json.dumps({k: v for k, v in result.items() if k != "coefficients"}, indent=2))
    print("coefficients:")
    for k, v in sorted(result["coefficients"].items(), key=lambda kv: -abs(kv[1])):
        print(f"  {k}: {v:.4f}")

    json.dump(result, open("backtest_signal_weight_fit.json", "w", encoding="utf-8"),
               ensure_ascii=False, indent=2)
    print("wrote backtest_signal_weight_fit.json")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest backtest/tests/test_fit_signal_weights.py -v`
Expected: PASS.

- [ ] **Step 6: Run the real fit against the committed dataset**

```bash
python -m backtest.fit_signal_weights
```

Expected: no exception, prints train/test trade counts, AUC values, and the coefficient table,
writes `backtest_signal_weight_fit.json`. Report the actual printed numbers honestly regardless of
what they show — a train/test AUC near 0.5 (no better than chance) is a valid, expected outcome
given this research line's track record, not a task failure.

- [ ] **Step 7: Commit**

```bash
git add backtest/fit_signal_weights.py backtest/tests/test_fit_signal_weights.py backtest/requirements.txt backtest_signal_weight_fit.json
git commit -m "feat(backtest): fit L2-regularized logistic regression for auxiliary signal weights (sub-project 10)"
```

---

### Task 5: Write the final analysis document

**Files:**
- Create: `docs/03-analysis/swing-algo-signal-weight-refit.analysis.md`

- [ ] **Step 1: Assemble the honest, fully-cited summary**

Using the real numbers from `backtest_out_swing_v2_with_features.json` and
`backtest_signal_weight_fit.json` (both committed in Tasks 3-4), write
`docs/03-analysis/swing-algo-signal-weight-refit.analysis.md` with these sections (no bracket
placeholders):

- **Header** matching this research line's convention (Analysis Type, Project, Feature, Design
  Doc = `docs/superpowers/specs/2026-08-02-swing-algo-signal-weight-refit-design.md`,
  Implementation Plan = `docs/superpowers/plans/2026-08-02-swing-algo-signal-weight-refit.md`,
  Prior work citing `docs/03-analysis/swing-algorithm-profitability-review.analysis.md`'s Finding
  #3, Date `2026-08-02`).
- **Method summary**: restate the scope decision (auxiliary signals only, pattern base weights
  untouched), the binary-exit-model choice and why (not sub-project 8's partial-exit model, per
  the design doc's stated reason), the train/test split, and the one-hot encoding scheme.
- **Data coverage caveat, stated prominently, not buried**: report the actual non-zero rate of
  `supply_tier` and `dart_tier` in the committed dataset (compute directly:
  `sum(1 for t in trades if t['aux_features']['supply_tier'] != 0) / len(trades)` and the same for
  `dart_tier`) — per the design doc's Section 7, these are expected to be almost entirely zero in
  this sandbox (KRX supply API HTTP 400, DART near-non-coverage per the profitability-review doc),
  and any fitted coefficient for these features must be flagged as unreliable if the non-zero rate
  is low, regardless of what the model outputs numerically.
- **Model performance**: train and test AUC from `backtest_signal_weight_fit.json`, plus
  `n_train`/`n_test`/`train_positive_rate`/`test_positive_rate`. State plainly whether the model
  shows real discriminative power (AUC meaningfully above 0.5 on the *test* split specifically —
  train AUC alone proves nothing given regularization can still overfit with enough features
  relative to sample size) or not.
- **Coefficient table**: the fitted coefficients from `backtest_signal_weight_fit.json`, sorted by
  magnitude, with the low-coverage features (`supply_tier`, `dart_tier`) explicitly marked as
  unreliable per the caveat above regardless of their sign/magnitude. For every other feature,
  state whether its sign is directionally consistent with production's current hand-tuned weight
  (e.g., does `rvol_tier`'s coefficient increase with tier, matching production's increasing
  25/18/12/6 point schedule?) or contradicts it.
- **Honest trader-perspective verdict**: does this refit support keeping the current auxiliary
  weights, suggest specific ones should be dropped or reweighted, or show the whole auxiliary
  layer has no measurable predictive power once real outcome data is checked? Be specific — if
  test AUC is indistinguishable from 0.5, say plainly that no evidence here supports any of the
  auxiliary weights actually improving trade selection, which would be a significant, uncomfortable
  finding given how much of the scoring formula these weights constitute. Do not soften a null
  result into "further research needed" language without substance.
- **Limitations**: restate the design doc's Section 7 limitations (sample size/class imbalance,
  correlated features, single train/test split, binary-exit-model's inherited limitations,
  supply/DART low-coverage, correlational-not-causal).
- **Final recommendation**: state plainly whether this finding changes anything about production's
  current auxiliary scoring weights — likely "no immediate change recommended without further
  validation" given every prior sub-project's negative results and this sub-project's own honest
  limitations, but base this on the actual numbers found, do not assume the answer before reading
  them. Note explicitly that no production code was changed and this is the last of the
  priority-3 items from this session's gap review.

State explicitly that no production code (`src/swing-scanner.src.js`) was changed by this
sub-project.

- [ ] **Step 2: Commit the analysis document**

```bash
git add docs/03-analysis/swing-algo-signal-weight-refit.analysis.md
git commit -m "docs: final analysis for swing algo sub-project 10 (auxiliary signal-weight refit)"
```

---

## Self-Review Notes

- **Spec coverage**: Task 1 covers design doc Section 2 in full (the additive field, the exact
  encodings, the OBV-negative gap the design doc specifically called out — with a dedicated test).
  Task 2 covers Section 3's data-flow requirement to thread features through the existing Line A
  pipeline rather than building a new one. Task 3 covers Section 3's re-run requirement and the
  binary-vs-partial exit model decision from Section 3's "why binary" subsection. Task 4 covers
  Section 4 (new dependency, justified) and Section 5 (model details, regularization, evaluation
  on both splits). Task 5 covers the analysis document implied by Section 1's goal and Section 7's
  limitations, plus the low-coverage caveat for `supply_tier`/`dart_tier` specifically called out
  there.
- **Placeholder scan**: no TBD/TODO. `test_obv_negative_is_captured_even_without_a_tag` is
  explicitly flagged as needing possible fixture iteration (not a placeholder — it has complete,
  runnable code and a clear pass criterion, with documented iteration instructions if the first
  attempt doesn't hit the target OBV state, consistent with normal TDD practice of running a test
  and adjusting based on real output).
- **Type consistency**: `aux_features` key names and value types are identical across Task 1's
  dataclass field, Task 2's trade-dict threading, and Task 4's `encode_features()` — all 10 keys
  (`rvol_tier`, `obv_trend`, `macd_state`, `sma_aligned`, `intraday_tier`, `supply_tier`,
  `dart_tier`, `rsi_golden`, `adx_trend`, `high52_tier`) match exactly, no invented names, matching
  the design doc's Section 2 table throughout every task.

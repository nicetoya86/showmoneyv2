import numpy as np
import pandas as pd

from backtest.swing_signal_engine import evaluate_candidate, MIN_SCORE_FINAL, SCORE_STRONG_FINAL


def _flat_df(n=300, base=10000.0, vol=2_000_000.0):
    close = np.full(n, base)
    df = pd.DataFrame(
        {
            "open": close, "high": close * 1.001, "low": close * 0.999,
            "close": close, "volume": np.full(n, vol),
        }
    )
    return df


def test_no_pattern_returns_none():
    df = _flat_df()
    result = evaluate_candidate(df, len(df) - 1, supply={}, dart_items=[], day_of_week=2)
    assert result is None


def test_pattern_d_box_breakout_produces_candidate():
    n = 300
    df = _flat_df(n=n, base=10000.0)
    # box ceiling for last PD_DAYS(25) days stays at 10000, then breaks out hard on the last bar
    df.loc[n - 1, "close"] = 11000.0
    df.loc[n - 1, "open"] = 10050.0
    df.loc[n - 1, "high"] = 11050.0
    df.loc[n - 1, "low"] = 10000.0
    df.loc[n - 1, "volume"] = 2_000_000.0 * 3.0  # PD_VOL_MULT=2.5 -> use 3x
    # daily_uptrend requires sma20 > sma60 at breakout bar: ramp last 60 bars up slightly
    for i in range(n - 60, n - 1):
        df.loc[i, "close"] = 10000.0 + (i - (n - 60)) * 2.0
        df.loc[i, "open"] = df.loc[i, "close"]
        df.loc[i, "high"] = df.loc[i, "close"] * 1.001
        df.loc[i, "low"] = df.loc[i, "close"] * 0.999

    result = evaluate_candidate(df, n - 1, supply={}, dart_items=[], day_of_week=2)
    assert result is not None
    assert result.pattern_type == "D박스"
    assert result.score >= MIN_SCORE_FINAL
    assert result.stop < result.entry < result.target


def test_score_below_min_returns_none():
    # A pattern D breakout too weak on volume (only 2.6x, right at threshold but no other bonuses)
    # combined with RSI < 40 hard filter should reject via F-filter
    n = 300
    df = _flat_df(n=n, base=10000.0)
    for i in range(n - 30, n):
        df.loc[i, "close"] = 10000.0 - (i - (n - 30)) * 50.0  # sharp decline -> RSI < 40
        df.loc[i, "open"] = df.loc[i, "close"]
        df.loc[i, "high"] = df.loc[i, "close"]
        df.loc[i, "low"] = df.loc[i, "close"]
    result = evaluate_candidate(df, n - 1, supply={}, dart_items=[], day_of_week=2)
    assert result is None


def test_negative_dart_keyword_hard_blocks():
    n = 300
    df = _flat_df(n=n, base=10000.0)
    df.loc[n - 1, "close"] = 11000.0
    df.loc[n - 1, "high"] = 11050.0
    df.loc[n - 1, "volume"] = 2_000_000.0 * 3.0
    for i in range(n - 60, n - 1):
        df.loc[i, "close"] = 10000.0 + (i - (n - 60)) * 2.0
        df.loc[i, "high"] = df.loc[i, "close"] * 1.001
        df.loc[i, "low"] = df.loc[i, "close"] * 0.999
    result = evaluate_candidate(
        df, n - 1, supply={}, dart_items=["소송 제기 관련 조회공시"], day_of_week=2
    )
    assert result is None


def test_negative_supply_hard_blocks():
    n = 300
    df = _flat_df(n=n, base=10000.0)
    df.loc[n - 1, "close"] = 11000.0
    df.loc[n - 1, "high"] = 11050.0
    df.loc[n - 1, "volume"] = 2_000_000.0 * 3.0
    for i in range(n - 60, n - 1):
        df.loc[i, "close"] = 10000.0 + (i - (n - 60)) * 2.0
        df.loc[i, "high"] = df.loc[i, "close"] * 1.001
        df.loc[i, "low"] = df.loc[i, "close"] * 0.999
    result = evaluate_candidate(
        df, n - 1, supply={"frgn": -2_000_000_000, "org": 0}, dart_items=[], day_of_week=2
    )
    assert result is None


def test_grade_strong_when_score_at_least_110():
    n = 300
    df = _flat_df(n=n, base=10000.0)
    df.loc[n - 1, "close"] = 12000.0
    df.loc[n - 1, "high"] = 12050.0
    df.loc[n - 1, "open"] = 10100.0
    df.loc[n - 1, "low"] = 10000.0
    df.loc[n - 1, "volume"] = 2_000_000.0 * 9.0  # >=8x RVOL bonus
    for i in range(n - 60, n - 1):
        df.loc[i, "close"] = 10000.0 + (i - (n - 60)) * 2.0
        df.loc[i, "high"] = df.loc[i, "close"] * 1.001
        df.loc[i, "low"] = df.loc[i, "close"] * 0.999
    result = evaluate_candidate(
        df, n - 1, supply={"frgn": 600_000_000, "org": 600_000_000}, dart_items=[], day_of_week=2
    )
    assert result is not None
    if result.score >= SCORE_STRONG_FINAL:
        assert result.grade == "강매"
        assert result.hold_days == 5


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
    print `df.tail(15)` and the computed `obv_result`, adjust the decline's steepness/volume in
    the `n-15..n-2` range (NOT the final breakout bar, which must stay as specified for the D박스
    pattern to still fire) until it is. This iteration is expected, not a sign the plan is wrong.
    """
    n = 300
    df = _flat_df(n=n, base=10000.0)
    for i in range(n - 60, n - 1):
        df.loc[i, "close"] = 10000.0 + (i - (n - 60)) * 2.0
        df.loc[i, "open"] = df.loc[i, "close"]
        df.loc[i, "high"] = df.loc[i, "close"] * 1.001
        df.loc[i, "low"] = df.loc[i, "close"] * 0.999
    # Override the last 14 bars (before the breakout bar) with a declining-price/rising-volume
    # run to push recent OBV below prior OBV. The decline continues from the ramp's natural
    # level at n-15 (rather than an artificial lower base) so it doesn't also drag sma20 below
    # sma60 -- that would kill the D박스 pattern's daily_uptrend requirement (sma20>sma60) and
    # make evaluate_candidate() return None regardless of OBV. (First iteration used a base ~180
    # points below the ramp's continuation point, which produced obv_trend==-1 correctly but
    # always returned None because sma20 < sma60; anchoring the decline's start to the ramp's
    # actual level at n-15 fixes this while preserving the same decline slope/volume ramp.)
    base_at_start = 10000.0 + ((n - 15) - (n - 60)) * 2.0
    for i in range(n - 15, n - 1):
        step = i - (n - 15)
        df.loc[i, "close"] = base_at_start - step * 15.0
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

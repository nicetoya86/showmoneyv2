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

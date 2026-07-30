import numpy as np
import pandas as pd

from backtest import generate_oversold_candidates as mod


def _build_df(flat_n, flat_level, rally_days, rally_step, decline_days, decline_step, bounce_close):
    """Builds a synthetic OHLCV DataFrame: flat history -> rally -> decline -> one bounce day
    (the last row, returned as `idx`). All price paths below were verified against the real
    backtest.indicators.rsi14/sma functions before being written into this test."""
    closes = [float(flat_level)] * flat_n
    for i in range(1, rally_days + 1):
        closes.append(flat_level + i * rally_step)
    last = closes[-1]
    for i in range(1, decline_days + 1):
        closes.append(last - i * decline_step)
    closes.append(bounce_close)
    close = np.array(closes, dtype="float64")
    high = close * 1.01
    low = close * 0.99
    openp = np.concatenate([[close[0]], close[:-1]])
    df = pd.DataFrame({
        "open": openp, "high": high, "low": low, "close": close,
        "volume": np.full(len(close), 2_000_000_000.0),
    })
    return df, len(close) - 1


def test_is_oversold_bounce_all_conditions_true():
    df, idx = _build_df(48, 950, 16, 15, 18, 13, 1067.2639)
    assert mod._is_oversold_bounce(df, idx) is True


def test_is_oversold_bounce_false_when_no_rsi_crossup():
    # RSI never crosses back up through 40 (bounce too small)
    df, idx = _build_df(45, 900, 18, 25, 22, 11, 1122.3227)
    assert mod._is_oversold_bounce(df, idx) is False


def test_is_oversold_bounce_false_when_no_oversold_depth():
    # RSI crosses up through 40, but never dipped to <=35 in the prior 5 bars
    df, idx = _build_df(38, 900, 19, 30, 18, 15, 1272.0)
    assert mod._is_oversold_bounce(df, idx) is False


def test_is_oversold_bounce_false_when_pullback_too_shallow():
    # only ~5% off the 20-day high, short of the required 8%
    df, idx = _build_df(49, 1100, 15, 10, 25, 9, 1148.0)
    assert mod._is_oversold_bounce(df, idx) is False


def test_is_oversold_bounce_false_when_below_sma60():
    # bounce day's close is still below the 60-day SMA (no uptrend context)
    df, idx = _build_df(49, 1000, 7, 25, 19, 15, 996.8)
    assert mod._is_oversold_bounce(df, idx) is False


def test_is_oversold_bounce_false_when_not_above_prior_day_high():
    # same price path as the all-true case, but the prior day had a long upper wick
    # (high raised well above the bounce day's close) so the breakout confirmation fails
    df, idx = _build_df(48, 950, 16, 15, 18, 13, 1067.2639)
    df.loc[idx - 1, "high"] = 1117.2639
    assert mod._is_oversold_bounce(df, idx) is False

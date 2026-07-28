import pandas as pd

from backtest.candidate_signals import compute_trend_alignment


def _ohlcv_df(dates, opens, highs, lows, closes):
    return pd.DataFrame({
        "timestamp_utc": dates,
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": [1_000_000.0] * len(closes),
    })


def _flat_ohlcv_df(dates, closes):
    return _ohlcv_df(dates, closes, closes, closes, closes)


def test_trend_alignment_true_for_steady_uptrend():
    dates = pd.bdate_range("2024-01-01", periods=65, tz="UTC")  # 13 weeks of business days
    closes = [100.0 + i for i in range(65)]
    df = _flat_ohlcv_df(dates, closes)
    assert compute_trend_alignment(df, len(df) - 1) is True


def test_trend_alignment_false_for_steady_downtrend():
    dates = pd.bdate_range("2024-01-01", periods=65, tz="UTC")
    closes = [200.0 - i for i in range(65)]
    df = _flat_ohlcv_df(dates, closes)
    assert compute_trend_alignment(df, len(df) - 1) is False


def test_trend_alignment_false_with_fewer_than_10_completed_weeks():
    dates = pd.bdate_range("2024-01-01", periods=20, tz="UTC")  # only 4 weeks of business days
    closes = [100.0 + i for i in range(20)]
    df = _flat_ohlcv_df(dates, closes)
    assert compute_trend_alignment(df, len(df) - 1) is False

import numpy as np
import pandas as pd

from backtest import generate_momentum_candidates as mod


def test_compute_trailing_return_value_pinned():
    n = 65
    close = np.full(n, 100.0)
    close[64] = 130.0
    df = pd.DataFrame({"close": close})
    result = mod.compute_trailing_return(df, 64, lookback=60)
    assert abs(result - 0.3) < 1e-9


def test_compute_trailing_return_nan_when_idx_below_lookback():
    n = 60
    df = pd.DataFrame({"close": np.full(n, 100.0)})
    assert np.isnan(mod.compute_trailing_return(df, 59, lookback=60))


def _flat_with_final_bump(n, flat_level, final_close, dates):
    close = np.full(n, flat_level)
    close[-1] = final_close
    return pd.DataFrame({"timestamp_utc": dates, "close": close})


def test_build_universe_return_lookup_value_pinned():
    n = 65
    dates = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    returns = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10]
    per_ticker = {
        f"T{i}.KS": _flat_with_final_bump(n, 100.0, 100.0 * (1 + r), dates)
        for i, r in enumerate(returns)
    }

    lookup = mod.build_universe_return_lookup(per_ticker, lookback=60, top_frac=0.10)

    last_date_key = dates[-1].date().isoformat()
    assert abs(lookup[last_date_key] - 0.091) < 1e-9
    # every ticker is flat (return 0.0) on days 60-63 -- a separate, correctly-zero cutoff
    mid_date_key = dates[60].date().isoformat()
    assert abs(lookup[mid_date_key] - 0.0) < 1e-9


def test_build_universe_return_lookup_excludes_dates_with_no_valid_return():
    n = 65
    dates = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    per_ticker = {"T0.KS": _flat_with_final_bump(n, 100.0, 105.0, dates)}
    lookup = mod.build_universe_return_lookup(per_ticker, lookback=60, top_frac=0.10)
    day59_key = dates[59].date().isoformat()
    assert day59_key not in lookup  # idx=59 < lookback=60 everywhere -- no valid return that day


def _build_momentum_df(n, closes, highs=None):
    closes = np.asarray(closes, dtype="float64")
    highs = np.asarray(highs, dtype="float64") if highs is not None else closes * 1.001
    return pd.DataFrame({
        "timestamp_utc": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
        "open": closes, "high": highs, "low": closes * 0.999, "close": closes,
        "volume": np.full(n, 2_000_000_000.0),
    })


def test_is_momentum_continuation_true_when_all_conditions_hold():
    n = 210
    close = np.linspace(100, 400, n)
    df = _build_momentum_df(n, close)
    idx = n - 1
    assert mod._is_momentum_continuation(df, idx, rs_threshold=0.05) is True


def test_is_momentum_continuation_false_when_rs_threshold_none():
    n = 210
    close = np.linspace(100, 400, n)
    df = _build_momentum_df(n, close)
    assert mod._is_momentum_continuation(df, n - 1, rs_threshold=None) is False


def test_is_momentum_continuation_false_when_return_below_threshold():
    n = 210
    close = np.linspace(100, 400, n)
    df = _build_momentum_df(n, close)
    # own trailing-60d return here is ~0.274 -- an impossibly high threshold forces a miss
    assert mod._is_momentum_continuation(df, n - 1, rs_threshold=999.0) is False


def test_is_momentum_continuation_false_when_not_at_new_high():
    n = 210
    close = np.linspace(100, 400, n)
    high = close * 1.001
    idx = n - 1
    # a spike 5 bars before idx that exceeds the final close -- the prior-60-day high wins
    close = close.copy()
    high = high.copy()
    close[idx - 5] = close[idx] * 1.05
    high[idx - 5] = close[idx - 5] * 1.001
    df = _build_momentum_df(n, close, highs=high)
    assert mod._is_momentum_continuation(df, idx, rs_threshold=0.05) is False


def test_is_momentum_continuation_false_when_trend_not_aligned():
    # long steep decline (drags sma200 high), then a flat base, then a small tick-up that is a
    # new high vs the flat base (last 60 bars) but still far below the sma50/sma200 built from
    # the earlier decline -- isolates the trend-alignment condition specifically
    close = np.concatenate([
        np.linspace(1000, 200, 100),
        np.full(109, 150.0),
        [155.0],
    ])
    df = _build_momentum_df(len(close), close)
    idx = len(close) - 1
    assert mod._is_momentum_continuation(df, idx, rs_threshold=0.01) is False

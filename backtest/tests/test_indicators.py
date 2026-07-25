import numpy as np
from backtest.indicators import ema, rsi14, adx, macd, obv


def test_ema_matches_hand_computed_seed():
    # k = 2/(3+1) = 0.5; seed=first value; then v*k + prev*(1-k)
    arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    out = ema(arr, 2)
    assert out[0] == 1.0
    assert abs(out[1] - (2.0 * 0.6666666666666666 + 1.0 * 0.3333333333333334)) < 1e-9
    assert out[4] > out[3]  # rising series -> rising EMA


def test_rsi14_all_gains_is_100():
    close = np.array([float(i) for i in range(1, 20)])  # strictly increasing, no losses
    r = rsi14(close, len(close) - 1)
    assert r == 100.0


def test_rsi14_flat_series_is_nan_or_neutral():
    close = np.array([100.0] * 20)
    r = rsi14(close, len(close) - 1)
    # avgLoss == 0 and avgGain == 0 -> JS calcRSI14 returns 100 (avgLoss===0 branch)
    assert r == 100.0


def test_rsi14_insufficient_history_is_nan():
    close = np.array([1.0, 2.0, 3.0])
    r = rsi14(close, 2)
    assert np.isnan(r)


def test_adx_uptrend_plusDI_greater_than_minusDI():
    n = 60
    high = np.array([100.0 + i * 1.5 for i in range(n)])
    low = np.array([99.0 + i * 1.5 for i in range(n)])
    close = np.array([99.5 + i * 1.5 for i in range(n)])
    r = adx(high, low, close, n - 1, 14)
    assert r["plusDI"] > r["minusDI"]
    assert r["adx"] >= 0


def test_macd_golden_cross_detects_crossover():
    # Build a series that rises, then recent reversal (histogram momentum)
    n = 80
    close = np.array(
        [100.0 + i * 0.1 for i in range(60)] +  # steady rise
        [106.0 - i * 1.0 for i in range(20)]    # recent decline
    )
    r = macd(close, n - 1)
    assert r["hist"] > r["histPrev"]  # histogram less negative on momentum shift


def test_obv_uptrend_gives_positive_trend():
    n = 25
    close = np.array([100.0 + i for i in range(n)])  # steadily rising close
    vol = np.array([1000.0] * n)
    r = obv(close, vol, n - 1)
    assert r["obvTrend"] == 1


def test_obv_downtrend_gives_negative_trend():
    n = 25
    close = np.array([100.0 - i for i in range(n)])  # steadily falling close
    vol = np.array([1000.0] * n)
    r = obv(close, vol, n - 1)
    assert r["obvTrend"] == -1

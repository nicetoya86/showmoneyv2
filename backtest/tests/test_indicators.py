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


def test_rsi14_flat_series_avgloss_zero_returns_100():
    """When all closes are identical, avgLoss == 0 -> RS undefined -> RSI = 100."""
    close = np.array([100.0] * 20)
    r = rsi14(close, len(close) - 1)
    # avgLoss == 0 and avgGain == 0 -> JS calcRSI14 returns 100 (avgLoss===0 branch)
    assert r == 100.0


def test_rsi14_insufficient_history_is_nan():
    close = np.array([1.0, 2.0, 3.0])
    r = rsi14(close, 2)
    assert np.isnan(r)


def test_rsi14_mixed_gains_losses_pinned_value():
    """Verify RSI with genuine mixed up/down bars (src/swing-scanner.src.js:106-125)."""
    # Series with varied gains and losses: up, down, up, up, down, up, up, down, up...
    close = np.array([100, 102, 101, 103, 105, 104, 106, 108, 107, 109,
                      110, 111, 110, 112, 113, 112, 114, 115, 114, 116,
                      117, 116, 118, 119, 120])
    r = rsi14(close, len(close) - 1)
    # Pinned value: RSI reflects balance of gains vs losses
    assert abs(r - 80.13859863867724) < 0.01


def test_adx_uptrend_plusDI_greater_than_minusDI():
    """Directional check: in uptrend, +DI should exceed -DI."""
    n = 60
    high = np.array([100.0 + i * 1.5 for i in range(n)])
    low = np.array([99.0 + i * 1.5 for i in range(n)])
    close = np.array([99.5 + i * 1.5 for i in range(n)])
    r = adx(high, low, close, n - 1, 14)
    assert r["plusDI"] > r["minusDI"]
    assert r["adx"] >= 0


def test_adx_uptrend_pinned_values():
    """Verify exact ADX, +DI, -DI values for steady uptrend fixture (src/swing-scanner.src.js:127-174)."""
    n = 60
    high = np.array([100.0 + i * 1.5 for i in range(n)])
    low = np.array([99.0 + i * 1.5 for i in range(n)])
    close = np.array([99.5 + i * 1.5 for i in range(n)])
    r = adx(high, low, close, n - 1, 14)
    # Pinned values from actual function run
    assert abs(r["adx"] - 100.0) < 0.01
    assert abs(r["plusDI"] - 75.0) < 0.01
    assert abs(r["minusDI"] - 0.0) < 0.01


def test_macd_golden_cross_detects_crossover():
    """Verify MACD histogram and field values for momentum shift (src/swing-scanner.src.js:191-215)."""
    # Build a series that rises, then recent reversal (histogram momentum)
    n = 80
    close = np.array(
        [100.0 + i * 0.1 for i in range(60)] +  # steady rise
        [106.0 - i * 1.0 for i in range(20)]    # recent decline
    )
    r = macd(close, n - 1)
    # Momentum check: histogram should increase (become less negative)
    assert r["hist"] > r["histPrev"]
    # Pinned values from actual function run
    assert abs(r["macd"] - (-4.069918865317774)) < 0.01
    assert abs(r["signal"] - (-3.1076282598165945)) < 0.01
    assert abs(r["hist"] - (-0.9622906055011797)) < 0.01
    assert abs(r["histPrev"] - (-0.9942268768571183)) < 0.01
    assert r["goldenCross"] is False  # No golden cross in this fixture


def test_macd_golden_cross_true_when_macd_crosses_above_signal():
    """Verify goldenCross=True when MACD line crosses from below to above signal line (src/swing-scanner.src.js:191-215)."""
    # Engineer a fixture: extended flat consolidation, then sharp drop + recovery
    # This creates MACD < signal at n-2, then MACD > signal at n-1 (golden cross)
    close = np.array([100.0] * 60 + [100.0, 100.0, 100.0, 85.0, 75.0, 95.0, 125.0])
    r = macd(close, len(close) - 1)
    # Verify the golden cross condition
    assert r["goldenCross"] is True
    # Verify pinned MACD/signal values at crossover
    assert abs(r["macd"] - 0.0042348412286798975) < 0.01
    assert abs(r["signal"] - (-0.9173311889550937)) < 0.01
    assert abs(r["hist"] - 0.9215660301837736) < 0.01


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

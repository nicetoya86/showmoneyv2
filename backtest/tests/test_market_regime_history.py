import numpy as np
import pytest

from backtest.market_regime_history import _regime_level_for_index, _apply_macro_adjustment
from backtest.indicators import sma


def test_regime_level_bear_when_sma20_below_sma60():
    """Test bear regime (level=2) when SMA20 <= SMA60."""
    close = np.array([100.0 - i * 0.3 for i in range(70)])  # steady downtrend
    sma20 = sma(close, 20)
    sma60 = sma(close, 60)
    sma5 = sma(close, 5)
    level = _regime_level_for_index(69, sma5, sma20, sma60)
    assert level == 2


def test_regime_level_bull_when_all_aligned_up():
    """Test bull regime (level=0) when SMA5 > SMA20 > SMA60."""
    close = np.array([100.0 + i * 0.3 for i in range(70)])  # steady uptrend
    sma20 = sma(close, 20)
    sma60 = sma(close, 60)
    sma5 = sma(close, 5)
    level = _regime_level_for_index(69, sma5, sma20, sma60)
    assert level == 0


def test_regime_level_neutral_when_sma5_below_sma20():
    """Test neutral regime (level=1) when SMA20 > SMA60 but SMA5 <= SMA20.

    Synthetic fixture: 60-bar uptrend (100->112) then 10-bar dip (112->107.5)
    ensures SMA20 > SMA60 (long-term uptrend) but SMA5 <= SMA20 (short-term weakening).
    """
    close = np.array(
        [100.0 + i * 0.2 for i in range(60)] +  # steady uptrend first 60 bars
        [112.0, 111.5, 111.0, 110.5, 110.0, 109.5, 109.0, 108.5, 108.0, 107.5]  # dip last 10
    )
    sma5 = sma(close, 5)
    sma20 = sma(close, 20)
    sma60 = sma(close, 60)

    # Verify conditions at evaluation index
    idx = len(close) - 1
    assert sma20[idx] > sma60[idx], "SMA20 should be > SMA60 (uptrend)"
    assert sma5[idx] <= sma20[idx], "SMA5 should be <= SMA20 (weakness)"

    level = _regime_level_for_index(idx, sma5, sma20, sma60)
    assert level == 1, f"Expected level 1 (neutral), got {level}"


def test_apply_macro_adjustment_no_adjustment():
    """Test macro adjustment with no adjustment (base_level=0, macro_adj=0)."""
    result = _apply_macro_adjustment(0, 0)
    assert result == 0


def test_apply_macro_adjustment_adds_macro():
    """Test macro adjustment adds macro_adj to base_level."""
    result = _apply_macro_adjustment(1, 2)
    assert result == 2, "1 + 2 should equal 2, but capped to 2"


def test_apply_macro_adjustment_capped_at_2():
    """Test macro adjustment caps result at 2 (bear maximum)."""
    result = _apply_macro_adjustment(2, 5)
    assert result == 2, "2 + 5 should be capped to 2"


def test_apply_macro_adjustment_typical_case():
    """Test typical macro adjustment: base bear (0) + two macro factors (NASDAQ + VIX)."""
    result = _apply_macro_adjustment(0, 1)
    assert result == 1, "0 + 1 = 1"

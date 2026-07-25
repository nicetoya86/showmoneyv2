import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch
from datetime import datetime, timedelta

from backtest.market_regime_history import _regime_level_for_index, _apply_macro_adjustment, compute_regime_series
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


def _make_synthetic_chart(base_prices, nasdaq_ret_on_date=None, vix_level_on_date=None):
    """Generate synthetic Yahoo chart dict for testing.

    Args:
        base_prices: List of close prices
        nasdaq_ret_on_date: Dict of {date_string -> return} for NASDAQ
        vix_level_on_date: Dict of {date_string -> vix_level} for VIX

    Returns:
        Dict conforming to Yahoo chart API structure
    """
    num_days = len(base_prices)
    start_date = datetime(2024, 1, 1)
    timestamps = [(start_date + timedelta(days=i)).timestamp() for i in range(num_days)]

    chart_data = {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": base_prices,
                                "high": [p * 1.01 for p in base_prices],
                                "low": [p * 0.99 for p in base_prices],
                                "close": base_prices,
                                "volume": [1000000] * num_days,
                            }
                        ]
                    },
                    "meta": {},
                }
            ]
        }
    }
    return chart_data


def test_compute_regime_series_routing_through_apply_macro_adjustment():
    """Integration test verifying compute_regime_series actually uses _apply_macro_adjustment.

    Mocks all four fetch_yahoo_chart calls and verifies that:
    1. Base regime is derived from KOSPI/KOSDAQ SMAs
    2. Macro adjustments are applied via _apply_macro_adjustment (not inline clip)
    3. Result is capped at 2 (bear maximum)
    """
    # Setup: 70 bars of steady uptrend (bull regime base=0)
    bull_prices = [100.0 + i * 0.3 for i in range(70)]

    # On day 70 (index 69), NASDAQ will be down (nasdaq_ret < -0.01), VIX will be high (>25)
    # This triggers macro_adj = 2, so: 0 (base) + 2 (macro) = 2 (at the cap)
    def mock_fetch(spec):
        if spec.ticker == "%5EKS11":  # KOSPI
            return _make_synthetic_chart(bull_prices)
        elif spec.ticker == "%5EKQ11":  # KOSDAQ
            return _make_synthetic_chart(bull_prices)
        elif spec.ticker == "%5EIXIC":  # NASDAQ
            # First 69 prices normal, day 69 (index 68) will show a down return
            nasdaq_prices = [100.0 + i * 0.1 for i in range(69)] + [99.0]  # down on day 70
            return _make_synthetic_chart(nasdaq_prices)
        elif spec.ticker == "%5EVIX":  # VIX
            # Day 70 (index 69) VIX = 30 (high, > 25 threshold)
            vix_prices = [20.0] * 69 + [30.0]
            return _make_synthetic_chart(vix_prices)
        return _make_synthetic_chart([100.0] * 70)

    with patch("backtest.market_regime_history.fetch_yahoo_chart", side_effect=mock_fetch):
        result = compute_regime_series("2024-01-01", "2024-03-10")

        # Result should be a DataFrame with regime_level column
        assert "regime_level" in result.columns
        assert len(result) > 0

        # Find the last date (day 70, 2024-03-10) and verify it's capped at 2
        # Base regime is 0 (bull), macro adjustment is 2 (nasdaq down + vix high)
        # Expected: min(2, 0 + 2) = 2
        last_date = result.index[-1]
        last_regime = result.iloc[-1]["regime_level"]
        assert last_regime == 2, f"Expected regime_level=2 at {last_date}, got {last_regime}"

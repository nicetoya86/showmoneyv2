import pandas as pd

from backtest.market_regime_history import _regime_level_for_index
from backtest.indicators import sma
import numpy as np


def test_regime_level_bear_when_sma20_below_sma60():
    close = np.array([100.0 - i * 0.3 for i in range(70)])  # steady downtrend
    sma20 = sma(close, 20)
    sma60 = sma(close, 60)
    sma5 = sma(close, 5)
    level = _regime_level_for_index(69, sma5, sma20, sma60)
    assert level == 2


def test_regime_level_bull_when_all_aligned_up():
    close = np.array([100.0 + i * 0.3 for i in range(70)])  # steady uptrend
    sma20 = sma(close, 20)
    sma60 = sma(close, 60)
    sma5 = sma(close, 5)
    level = _regime_level_for_index(69, sma5, sma20, sma60)
    assert level == 0

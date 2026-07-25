from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import sma
from .yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart

NASDAQ_DOWN_THRESH = -0.01
SP500_DOWN_THRESH = -0.007
VIX_HIGH_THRESH = 25.0


def _regime_level_for_index(i: int, sma5: np.ndarray, sma20: np.ndarray, sma60: np.ndarray) -> int:
    if not (np.isfinite(sma20[i]) and np.isfinite(sma60[i])):
        return 0
    if sma20[i] <= sma60[i]:
        return 2
    if np.isfinite(sma5[i]) and sma5[i] <= sma20[i]:
        return 1
    return 0


def _single_index_regime(ticker: str, start: str, end: str) -> pd.Series:
    data = fetch_yahoo_chart(YahooFetchSpec(ticker=ticker, range="5y", interval="1d"))
    df, _ = chart_to_ohlcv_daily(data)
    close = df["close"].to_numpy(dtype="float64")
    sma5, sma20, sma60 = sma(close, 5), sma(close, 20), sma(close, 60)
    levels = [_regime_level_for_index(i, sma5, sma20, sma60) for i in range(len(close))]
    s = pd.Series(levels, index=df["timestamp_utc"].dt.date)
    mask = (s.index >= pd.to_datetime(start).date()) & (s.index <= pd.to_datetime(end).date())
    return s[mask]


def compute_regime_series(start: str, end: str) -> pd.DataFrame:
    """Daily regime_level (0=bull,1=neutral,2=bear) for KOSPI∪KOSDAQ + NASDAQ/VIX/ES=F macro overlay."""
    ks = _single_index_regime("%5EKS11", start, end)
    kq = _single_index_regime("%5EKQ11", start, end)
    base = pd.concat([ks, kq], axis=1).max(axis=1).fillna(0).astype(int)

    nasdaq_data = fetch_yahoo_chart(YahooFetchSpec(ticker="%5EIXIC", range="5y", interval="1d"))
    nasdaq_df, _ = chart_to_ohlcv_daily(nasdaq_data)
    nasdaq_ret = nasdaq_df["close"].pct_change()
    nasdaq_ret.index = nasdaq_df["timestamp_utc"].dt.date

    vix_data = fetch_yahoo_chart(YahooFetchSpec(ticker="%5EVIX", range="5y", interval="1d"))
    vix_df, _ = chart_to_ohlcv_daily(vix_data)
    vix_level = vix_df.set_index(vix_df["timestamp_utc"].dt.date)["close"]

    macro_adj = pd.Series(0, index=base.index)
    for d in base.index:
        adj = 0
        if d in nasdaq_ret.index and pd.notna(nasdaq_ret.get(d)) and nasdaq_ret[d] < NASDAQ_DOWN_THRESH:
            adj += 1
        if d in vix_level.index and vix_level[d] > VIX_HIGH_THRESH:
            adj += 1
        macro_adj[d] = adj

    regime_level = (base + macro_adj).clip(upper=2)
    return pd.DataFrame({"regime_level": regime_level})

from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import sma
from .yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart

# Macro adjustment thresholds (src/swing-scanner.src.js:30, 32)
NASDAQ_DOWN_THRESH = -0.01
# SP500_DOWN_THRESH = -0.007  # Reserved/unused: ES=F futures data not fetched in this simplified reconstruction
VIX_HIGH_THRESH = 25.0


def _regime_level_for_index(i: int, sma5: np.ndarray, sma20: np.ndarray, sma60: np.ndarray) -> int:
    """Classify regime level for a single bar based on SMA crossovers.

    Returns 0 (bull), 1 (neutral), or 2 (bear) mirroring
    src/swing-scanner.src.js:475-492 (KOSPI/KOSDAQ regime-level tiering block).

    Rules:
    - If SMA20 <= SMA60: return 2 (bear)
    - Else if SMA5 <= SMA20: return 1 (neutral, short-term weakening)
    - Else: return 0 (bull, all SMAs aligned upward)
    """
    if not (np.isfinite(sma20[i]) and np.isfinite(sma60[i])):
        return 0
    if sma20[i] <= sma60[i]:
        return 2
    if np.isfinite(sma5[i]) and sma5[i] <= sma20[i]:
        return 1
    return 0


def _apply_macro_adjustment(base_level: int, macro_adj: int) -> int:
    """Apply macro adjustment to base SMA-derived regime level, capped at 2 (bear).

    Mirrors src/swing-scanner.src.js:508-509 (Math.min(2, regimeLevel + macroAdj)).

    Args:
        base_level: Base regime level (0/1/2) from SMA analysis
        macro_adj: Macro adjustment (+1 for NASDAQ down, +1 for high VIX, etc.)

    Returns:
        Adjusted regime level, clamped to [0, 2]
    """
    return min(2, base_level + macro_adj)


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
    """Daily regime_level (0=bull,1=neutral,2=bear) for KOSPI∪KOSDAQ + NASDAQ/VIX macro overlay.

    Combines base SMA-derived regime for KOSPI and KOSDAQ with macro adjustments
    from NASDAQ returns (src/swing-scanner.src.js:504-509) and VIX levels
    (src/swing-scanner.src.js:30, 32, 507-509).
    """
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

    # Apply macro adjustment via the tested _apply_macro_adjustment function
    regime_level = pd.Series(
        [_apply_macro_adjustment(int(b), int(m)) for b, m in zip(base, macro_adj)],
        index=base.index,
    )
    return pd.DataFrame({"regime_level": regime_level})

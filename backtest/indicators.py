from __future__ import annotations

import numpy as np
import pandas as pd


def sma(arr: np.ndarray, window: int) -> np.ndarray:
    if window <= 0:
        raise ValueError("window must be > 0")
    s = pd.Series(arr, dtype="float64")
    return s.rolling(window).mean().to_numpy(dtype="float64")


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int = 14) -> np.ndarray:
    """
    Average True Range (ATR) using Wilder-style true range, simple rolling mean for simplicity.
    Returns array aligned to input length (leading values may be NaN).
    """
    if not (len(high) == len(low) == len(close)):
        raise ValueError("high/low/close lengths must match")
    h = pd.Series(high, dtype="float64")
    l = pd.Series(low, dtype="float64")
    c = pd.Series(close, dtype="float64")
    prev_close = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev_close).abs(), (l - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(window).mean().to_numpy(dtype="float64")


def max_drawdown(equity: np.ndarray) -> float:
    """
    Max drawdown for an equity curve array.
    """
    eq = np.asarray(equity, dtype="float64")
    if eq.size == 0:
        return 0.0
    peaks = np.maximum.accumulate(eq)
    dd = (eq - peaks) / np.where(peaks == 0, np.nan, peaks)
    return float(np.nanmin(dd))


def ema(arr: np.ndarray, window: int) -> np.ndarray:
    """Port of swing-scanner.src.js `ema()` — seeded EMA (first finite value seeds, not SMA-seeded)."""
    out = np.full(len(arr), np.nan, dtype="float64")
    k = 2.0 / (window + 1)
    prev = np.nan
    for i, raw in enumerate(arr):
        v = float(raw)
        if not np.isfinite(v):
            continue
        if not np.isfinite(prev):
            out[i] = v
            prev = v
            continue
        out[i] = v * k + prev * (1 - k)
        prev = out[i]
    return out


def rsi14(close: np.ndarray, idx: int) -> float:
    """Port of swing-scanner.src.js `calcRSI14()` — simple (non-Wilder) rolling avg gain/loss."""
    period = 14
    start = max(0, idx - period * 3)
    sl = close[start : idx + 1]
    if len(sl) < period + 1:
        return float("nan")
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        d = float(sl[i]) - float(sl[i - 1])
        if d > 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(sl)):
        d = float(sl[i]) - float(sl[i - 1])
        avg_gain = (avg_gain * (period - 1) + max(d, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-d, 0.0)) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, idx: int, period: int = 14) -> dict:
    """Port of swing-scanner.src.js `calcADX()`."""
    need = period * 3 + 2
    start = max(0, idx - need)
    hi = high[start : idx + 1].astype("float64")
    lo = low[start : idx + 1].astype("float64")
    cl = close[start : idx + 1].astype("float64")
    n = len(hi)
    if n < period + 2:
        return {"adx": float("nan"), "plusDI": float("nan"), "minusDI": float("nan")}

    plus_dm, minus_dm, tr = [], [], []
    for i in range(1, n):
        up_move = hi[i] - hi[i - 1]
        down_move = lo[i - 1] - lo[i]
        plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)
        tr.append(max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])))

    def smooth(arr):
        s = sum(arr[:period])
        out = [s]
        for i in range(period, len(arr)):
            s = s - s / period + arr[i]
            out.append(s)
        return out

    s_tr, s_pdm, s_mdm = smooth(tr), smooth(plus_dm), smooth(minus_dm)
    dx = []
    for i in range(len(s_tr)):
        if s_tr[i] == 0:
            dx.append(0.0)
            continue
        pdi = (s_pdm[i] / s_tr[i]) * 100
        mdi = (s_mdm[i] / s_tr[i]) * 100
        total = pdi + mdi
        dx.append(0.0 if total == 0 else (abs(pdi - mdi) / total) * 100)
    if len(dx) < period:
        return {"adx": float("nan"), "plusDI": float("nan"), "minusDI": float("nan")}
    adx_val = sum(dx[:period]) / period
    for i in range(period, len(dx)):
        adx_val = (adx_val * (period - 1) + dx[i]) / period
    last = len(s_tr) - 1
    plus_di = (s_pdm[last] / s_tr[last]) * 100 if s_tr[last] > 0 else 0.0
    minus_di = (s_mdm[last] / s_tr[last]) * 100 if s_tr[last] > 0 else 0.0
    return {"adx": adx_val, "plusDI": plus_di, "minusDI": minus_di}


def macd(close: np.ndarray, idx: int) -> dict:
    """Port of swing-scanner.src.js `calcMACD()` — 12/26/9."""
    nan = {"macd": float("nan"), "signal": float("nan"), "hist": float("nan"), "histPrev": float("nan"), "goldenCross": False}
    start = max(0, idx - 26 * 4)
    sl = close[start : idx + 1]
    if len(sl) < 35:
        return nan
    fast = ema(sl, 12)
    slow = ema(sl, 26)
    macd_line = np.array([
        (f - s) if (np.isfinite(f) and np.isfinite(s)) else np.nan
        for f, s in zip(fast, slow)
    ])
    macd_valid = macd_line[np.isfinite(macd_line)]
    if len(macd_valid) < 9:
        return nan
    signal_arr = ema(macd_valid, 9)
    n = min(len(macd_valid), len(signal_arr))
    if n < 2:
        return nan
    last_macd, last_signal = macd_valid[n - 1], signal_arr[n - 1]
    prev_macd, prev_signal = macd_valid[n - 2], signal_arr[n - 2]
    return {
        "macd": last_macd,
        "signal": last_signal,
        "hist": last_macd - last_signal,
        "histPrev": prev_macd - prev_signal,
        "goldenCross": bool(prev_macd < prev_signal and last_macd >= last_signal),
    }


def obv(close: np.ndarray, vol: np.ndarray, idx: int) -> dict:
    """Port of swing-scanner.src.js `calcOBV()` — slope of last-5 vs prior-5 OBV average."""
    n = min(len(close), len(vol), idx + 1)
    if n < 20:
        return {"obvTrend": 0}
    running = 0.0
    obv_arr = []
    for i in range(n):
        if i > 0:
            d = float(close[i]) - float(close[i - 1])
            if d > 0:
                running += float(vol[i]) if np.isfinite(vol[i]) else 0.0
            elif d < 0:
                running -= float(vol[i]) if np.isfinite(vol[i]) else 0.0
        obv_arr.append(running)
    recent = sum(obv_arr[-5:]) / 5
    prior = sum(obv_arr[-10:-5]) / 5
    if prior == 0:
        return {"obvTrend": 0}
    slope = (recent - prior) / abs(prior)
    if slope > 0.005:
        return {"obvTrend": 1}
    if slope < -0.005:
        return {"obvTrend": -1}
    return {"obvTrend": 0}


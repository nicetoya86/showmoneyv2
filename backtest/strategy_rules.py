from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .indicators import atr as calc_atr
from .indicators import sma as calc_sma


@dataclass(frozen=True)
class Signal:
    date: pd.Timestamp  # trading date in UTC (aligned to Yahoo daily candle timestamp)
    ticker: str
    name: str
    kind: str  # "Scalping" | "Swing"
    entry: float
    stop: float
    target: float
    score: int
    prob: float
    strict: bool
    tags: List[str]


@dataclass(frozen=True)
class ConservativeConfig:
    # mimic current n8n defaults + conservative min2 relax
    min_price: float = 1000.0
    min_turnover: float = 1_000_000_000.0  # 10억 (KRW)

    # NOTE:
    # Scalping and Swing score distributions are very different.
    # Swing scoring (15+35+40) cannot reach 65 unless BOTH patterns hit,
    # so we keep scalping score thresholds as-is, and use separate swing thresholds.
    scalping_min_score_strict: int = 70
    scalping_min_score_relax: int = 65

    swing_min_score_strict: int = 70
    swing_min_score_relax: int = 50

    pup_strict: float = 0.90
    pup_relax: float = 0.88

    pmat_strict: float = 0.92
    pmat_relax: float = 0.90

    min_daily_picks: int = 2
    max_daily_picks: int = 6  # scalping default

    # ATR plan (for backtest). n8n may still use fixed %; we evaluate ATR-based too.
    atr_window: int = 14
    stop_mult: float = 1.7
    target_mult: float = 2.4

    # swing holding limit (days) for simplified daily-bar backtest
    swing_holding_days: int = 12


def _safe_num(x: Optional[float]) -> float:
    try:
        if x is None:
            return float("nan")
        return float(x)
    except Exception:
        return float("nan")


def _rsi14(close: np.ndarray) -> np.ndarray:
    """
    RSI(14) similar to the JS version used in workflow (simple rolling average gains/losses).
    """
    if close.size < 15:
        return np.full_like(close, np.nan, dtype="float64")
    diff = np.diff(close)
    up = np.maximum(diff, 0.0)
    dn = np.maximum(-diff, 0.0)
    # align to close length (prepend NaN)
    up_s = pd.Series(np.concatenate([[np.nan], up]), dtype="float64")
    dn_s = pd.Series(np.concatenate([[np.nan], dn]), dtype="float64")
    au = up_s.rolling(14).mean()
    ad = dn_s.rolling(14).mean()
    rs = au / ad.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.to_numpy(dtype="float64")


def build_hitalk_features_daily(df: pd.DataFrame, idx: int) -> Dict[str, float]:
    """
    Build feature set compatible with models:
    - models/hitalk_setup_up_model.json
    - models/hitalk_setup_mat_model.json

    Feature keys mirror the workflow's JS `hitalkFeaturesFromDaily`.
    """
    close = df["close"].to_numpy(dtype="float64")
    high = df["high"].to_numpy(dtype="float64")
    low = df["low"].to_numpy(dtype="float64")
    vol = df["volume"].to_numpy(dtype="float64")

    n = close.size
    i = int(max(0, min(idx, n - 1)))

    sma20 = calc_sma(close, 20)
    sma60 = calc_sma(close, 60)
    uptrend = 1.0 if np.isfinite(sma20[i]) and np.isfinite(sma60[i]) and sma20[i] > sma60[i] else 0.0

    prev = close[i - 1] if i >= 1 else np.nan
    daily_change = (close[i] / prev - 1.0) if np.isfinite(prev) and prev > 0 and close[i] > 0 else 0.0

    rsi = _rsi14(close)
    rsi14 = float(rsi[i]) if np.isfinite(rsi[i]) else 50.0

    start20 = max(0, i - 20)
    start60 = max(0, i - 60)

    prev20 = np.nanmax(high[start20:i]) if (i - start20) >= 1 else np.nan
    prev60 = np.nanmax(high[start60:i]) if (i - start60) >= 1 else np.nan

    breakout20 = 1.0 if np.isfinite(prev20) and close[i] > prev20 else 0.0
    breakout_ratio = (close[i] / prev20) if np.isfinite(prev20) and prev20 > 0 and close[i] > 0 else 1.0
    breakout60 = 1.0 if np.isfinite(prev60) and close[i] > prev60 else 0.0
    breakout60_ratio = (close[i] / prev60) if np.isfinite(prev60) and prev60 > 0 and close[i] > 0 else 1.0

    v20 = vol[start20:i]
    vavg20 = float(np.nanmean(v20)) if v20.size else np.nan
    vtoday = float(vol[i]) if np.isfinite(vol[i]) else np.nan
    volume_surge = (vtoday / vavg20) if np.isfinite(vtoday) and np.isfinite(vavg20) and vavg20 > 0 else 1.0

    v5 = vol[max(0, i - 5) : i]
    v60 = vol[start60:i]
    vavg5 = float(np.nanmean(v5)) if v5.size else np.nan
    vavg60 = float(np.nanmean(v60)) if v60.size else np.nan
    volume_surge5 = (vtoday / vavg5) if np.isfinite(vtoday) and np.isfinite(vavg5) and vavg5 > 0 else 1.0
    volume_surge60 = (vtoday / vavg60) if np.isfinite(vtoday) and np.isfinite(vavg60) and vavg60 > 0 else 1.0
    volume_trend_5_20 = (vavg5 / vavg20) if np.isfinite(vavg5) and np.isfinite(vavg20) and vavg20 > 0 else 1.0

    hl = (high[i] - low[i]) if np.isfinite(high[i]) and np.isfinite(low[i]) else 0.0
    volatility = (hl / close[i]) if close[i] > 0 else 0.0

    def _ret(n_days: int) -> float:
        j = i - n_days
        cj = close[j] if j >= 0 else np.nan
        return float(close[i] / cj - 1.0) if np.isfinite(cj) and cj > 0 and close[i] > 0 else 0.0

    ret5 = _ret(5)
    ret20 = _ret(20)
    dist_sma20 = (close[i] / sma20[i] - 1.0) if np.isfinite(sma20[i]) and sma20[i] > 0 and close[i] > 0 else 0.0
    dist_sma60 = (close[i] / sma60[i] - 1.0) if np.isfinite(sma60[i]) and sma60[i] > 0 and close[i] > 0 else 0.0
    trend_strength = ((sma20[i] - sma60[i]) / close[i]) if np.isfinite(sma20[i]) and np.isfinite(sma60[i]) and close[i] > 0 else 0.0

    # atr14 in workflow is "avg(high-low)/close" over last 14 bars (ratio)
    if i >= 1:
        start14 = max(0, i - 14)
        hl14 = (high[start14:i] - low[start14:i]).astype("float64")
        hl14 = hl14[np.isfinite(hl14)]
        atr14 = float(np.nanmean(hl14) / close[i]) if hl14.size and close[i] > 0 else 0.0
    else:
        atr14 = 0.0

    return {
        "daily_change": float(daily_change),
        "uptrend": float(uptrend),
        "rsi14": float(rsi14),
        "breakout20": float(breakout20),
        "breakout_ratio": float(breakout_ratio),
        "breakout60": float(breakout60),
        "breakout60_ratio": float(breakout60_ratio),
        "volume_surge": float(volume_surge),
        "volume_surge5": float(volume_surge5),
        "volume_surge60": float(volume_surge60),
        "volume_trend_5_20": float(volume_trend_5_20),
        "volatility": float(volatility),
        "atr14": float(atr14),
        "ret5": float(ret5),
        "ret20": float(ret20),
        "dist_sma20": float(dist_sma20),
        "dist_sma60": float(dist_sma60),
        "trend_strength": float(trend_strength),
        "price": float(close[i]),
        # convenience (absolute ATR for risk plan)
        "atr_abs": float(atr14 * close[i]) if close[i] > 0 else float("nan"),
    }


def score_scalping(feats: Dict[str, float]) -> Tuple[int, List[str]]:
    score = 0
    tags: List[str] = []
    if feats.get("uptrend", 0.0) >= 1:
        score += 15
        tags.append("일봉정배열")
    if feats.get("volume_surge", 0.0) >= 2.5:
        score += 25
        tags.append("거래량급증")
    if feats.get("breakout20", 0.0) >= 1:
        score += 25
        tags.append("20일돌파")
    if feats.get("ret5", 0.0) > 0:
        score += 10
        tags.append("5일상승")
    if feats.get("daily_change", 0.0) > 0.02:
        score += 10
        tags.append("당일강세")
    return int(score), tags


def score_swing(feats: Dict[str, float], *, box_breakout: bool, n_pattern: bool, daily_uptrend: bool) -> Tuple[int, List[str]]:
    score = 0
    tags: List[str] = []
    if daily_uptrend:
        score += 15
        tags.append("일봉정배열")
    else:
        # In n8n swing: mandatory gate
        return 0, ["정배열아님"]

    if box_breakout:
        score += 35
        tags.append("박스권돌파(20일)")
    if n_pattern:
        score += 40
        tags.append("N자형눌림목")
    return int(score), tags


def compute_atr_plan(entry: float, atr_val: float, cfg: ConservativeConfig) -> Tuple[float, float]:
    """
    ATR-based stop/target for backtest evaluation (conservative).
    """
    if not np.isfinite(atr_val) or atr_val <= 0:
        # fallback: 5% stop, 10% target
        return entry * (1 - 0.05), entry * (1 + 0.10)
    stop = entry - atr_val * cfg.stop_mult
    target = entry + atr_val * cfg.target_mult
    return float(stop), float(target)


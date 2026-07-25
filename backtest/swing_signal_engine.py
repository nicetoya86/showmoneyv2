"""
Faithful Python port of the swing-scanner pattern/scoring/grade/target/stop logic
in src/swing-scanner.src.js (as of 2026-07-25). Every constant below is copied
verbatim from that file; line numbers refer to that source at port time.

NOT MODELED: Toss real-time order-book confirmation (src/swing-scanner.src.js:1562-1700+) —
no historical tick/orderbook data exists to replay this gate. See report §Limitations.

NOT APPLIED: market-regime entry blocking. getMarketRegime()'s blocking logic
(`if regimeLevel>=2 and grade!='강매': return`) exists in an older commit
(see docs/03-analysis/trailing-stop-regime-fix.analysis.md, 2026-05-02) but is
absent from the current production file — the function is computed but never
called. This engine matches CURRENT production behavior (regime-blind).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .indicators import adx as calc_adx
from .indicators import atr as calc_atr
from .indicators import macd as calc_macd
from .indicators import obv as calc_obv
from .indicators import rsi14 as calc_rsi14
from .indicators import sma

MIN_PRICE = 1000.0
MIN_TURNOVER_ALGO = 5_000_000_000.0
MIN_SCORE_FINAL = 60
SCORE_STRONG_FINAL = 110
MIN_RR_RATIO_FINAL = 1.5

PA_VOL_MULT, PA_PRICE_MOVE, PA_DAYS_MIN, PA_DAYS_MAX = 3.0, 0.05, 1, 10
PA_PULLBACK_MAX, PA_PULLBACK_MIN = 0.15, 0.03
PB_CORR_MIN, PB_CORR_MAX, PB_LEVEL_PROX = 0.20, 0.50, 0.08
PC_VOL_MULT, PC_PRICE_MIN, PC_STR_MIN = 5.0, 0.05, 0.50
PD_VOL_MULT, PD_BREAK_MIN, PD_DAYS = 2.5, 0.02, 25

NEGATIVE_DART_RE = "소송|횡령|배임|감사의견|불성실|조회"
POSITIVE_DART_RE = "계약체결|특허|인허가|수주|투자유치|증자"

import re as _re


@dataclass(frozen=True)
class SwingCandidate:
    pattern_type: str
    score: int
    rank_score: int
    grade: str
    entry: float
    target: float
    stop: float
    hold_days: int
    signals: List[str]


def _hold_days(grade: str, pattern_type: str) -> int:
    if grade == "강매":
        return 5
    if grade == "급등":
        return 2
    return {"C촉매": 2, "A눌림목": 3, "B지지선": 5, "D박스": 4}.get(pattern_type, 3)


def evaluate_candidate(
    df: pd.DataFrame,
    idx: int,
    *,
    supply: Optional[Dict[str, float]] = None,
    dart_items: Optional[List[str]] = None,
    day_of_week: int,
) -> Optional[SwingCandidate]:
    """
    df must have columns open/high/low/close/volume, sorted ascending by date.
    idx is the "as of close" evaluation day. day_of_week: Mon=1 .. Sun=0 (JS getUTCDay convention).
    """
    supply = supply or {}
    dart_items = dart_items or []

    close = df["close"].to_numpy(dtype="float64")
    high = df["high"].to_numpy(dtype="float64")
    low = df["low"].to_numpy(dtype="float64")
    openp = df["open"].to_numpy(dtype="float64")
    vol = df["volume"].to_numpy(dtype="float64")

    if idx < 70 or idx >= len(close):
        return None

    current_price = float(close[idx])
    prev_close = float(close[idx - 1]) if idx >= 1 else 0.0
    if current_price < MIN_PRICE:
        return None
    daily_change = (current_price / prev_close - 1.0) if prev_close > 0 else 0.0

    sma20 = sma(close, 20)
    sma60 = sma(close, 60)
    vol_window = vol[max(0, idx - 20) : idx]
    vol20_avg = float(vol_window.sum() / max(1, min(20, idx))) if len(vol_window) else 0.0
    rvol = (vol[idx] / vol20_avg) if vol20_avg > 0 else 0.0
    rsi14_val = calc_rsi14(close, idx)
    adx_result = calc_adx(high, low, close, idx, 14)
    high252 = float(np.max(high[max(0, idx - 252) : idx + 1]))
    day_range = high[idx] - low[idx]
    intraday_strength = ((close[idx] - openp[idx]) / day_range) if day_range > 0 else 0.0
    macd_result = calc_macd(close, idx)
    obv_result = calc_obv(close, vol, idx)

    # ---- F: base filters ----
    if current_price * (vol[idx] if np.isfinite(vol[idx]) else 0.0) < MIN_TURNOVER_ALGO:
        return None
    if rvol < 1.0:
        return None
    if np.isfinite(rsi14_val) and rsi14_val < 40:
        return None
    if dart_items and _re.search(NEGATIVE_DART_RE, " ".join(dart_items)):
        return None
    if supply.get("frgn", 0) < -1_000_000_000 or supply.get("org", 0) < -1_000_000_000:
        return None

    # ---- P: pattern pre-calcs ----
    window_start = max(0, idx - 15)
    event_idx = window_start + int(np.argmax(vol[window_start : idx + 1]))
    event_vol_mult = (vol[event_idx] / vol20_avg) if vol20_avg > 0 else 0.0
    event_days_ago = idx - event_idx
    event_day_change = (
        (close[event_idx] / close[event_idx - 1] - 1.0) if event_idx > 0 and close[event_idx - 1] > 0 else 0.0
    )
    event_high_since = float(np.max(high[event_idx : idx + 1])) if event_idx <= idx else current_price
    pullback_from_event = (current_price / event_high_since - 1.0) if event_high_since > 0 else 0.0

    high60 = float(np.max(high[max(0, idx - 60) : idx + 1]))
    corr_pct60 = (current_price / high60 - 1.0) if high60 > 0 else 0.0

    past_slice = close[max(0, idx - 50) : max(1, idx - 20)]
    past_avg_price = float(past_slice.mean()) if len(past_slice) else 0.0
    prox_to_past = abs(current_price / past_avg_price - 1.0) if past_avg_price > 0 else 1.0

    box25_high = float(np.max(high[max(0, idx - PD_DAYS) : idx])) if idx > 0 else current_price

    is_a = (
        event_vol_mult >= PA_VOL_MULT
        and event_day_change >= PA_PRICE_MOVE
        and PA_DAYS_MIN <= event_days_ago <= PA_DAYS_MAX
        and -PA_PULLBACK_MAX <= pullback_from_event <= -PA_PULLBACK_MIN
        and rvol >= 1.2
        and daily_change >= -0.03
    )
    is_b = (
        -PB_CORR_MAX <= corr_pct60 <= -PB_CORR_MIN
        and prox_to_past <= PB_LEVEL_PROX
        and daily_change >= 0.0
        and rvol >= 1.5
        and np.isfinite(rsi14_val) and 40 <= rsi14_val <= 72
    )
    is_c = (
        rvol >= PC_VOL_MULT
        and daily_change >= PC_PRICE_MIN
        and intraday_strength >= PC_STR_MIN
        and np.isfinite(rsi14_val) and rsi14_val <= 82
    )
    is_d = current_price > box25_high and rvol >= PD_VOL_MULT and daily_change >= PD_BREAK_MIN and sma20[idx] > sma60[idx]

    if not (is_a or is_b or is_c or is_d):
        return None

    # ---- S: scoring ----
    score = 0
    signals: List[str] = []
    if is_c:
        score += 60
        signals.append("촉매이벤트")
    if is_a:
        score += 50
        signals.append("급등후눌림목")
    if is_b:
        score += 45
        signals.append("지지선반등")
    if is_d:
        score += 40
        signals.append("박스권돌파")
    if is_a and is_b:
        score += 15
        signals.append("복합A+B")
    if is_c and is_d:
        score += 10
        signals.append("복합C+D")

    if rvol >= 8.0:
        score += 25
        signals.append("거래량8x+")
    elif rvol >= 5.0:
        score += 18
        signals.append("거래량5x")
    elif rvol >= 3.0:
        score += 12
        signals.append("거래량3x")
    elif rvol >= 2.0:
        score += 6
        signals.append("거래량2x")

    if obv_result["obvTrend"] == 1:
        score += 20
        signals.append("OBV수급↑")
    elif obv_result["obvTrend"] == -1:
        score -= 8

    if macd_result["goldenCross"]:
        score += 15
        signals.append("MACD골든크로스")
    elif np.isfinite(macd_result["hist"]) and macd_result["hist"] > 0:
        if np.isfinite(macd_result["histPrev"]) and macd_result["hist"] > macd_result["histPrev"]:
            score += 10
            signals.append("MACD↑")
    elif (
        np.isfinite(macd_result["hist"]) and np.isfinite(macd_result["histPrev"])
        and macd_result["hist"] < 0 and macd_result["histPrev"] < 0 and not is_c
    ):
        return None

    if sma20[idx] > sma60[idx]:
        score += 15
        signals.append("일봉정배열")
    if intraday_strength >= 0.7:
        score += 12
        signals.append("장마감강세")
    elif intraday_strength >= 0.5:
        score += 6
        signals.append("장마감양호")

    frgn, org = supply.get("frgn", 0), supply.get("org", 0)
    if frgn > 500_000_000 and org > 500_000_000:
        score += 20
        signals.append("외국인+기관동반")
    elif frgn > 500_000_000:
        score += 12
        signals.append("외국인순매수")
    elif org > 500_000_000:
        score += 8
        signals.append("기관순매수")

    if dart_items:
        if _re.search(POSITIVE_DART_RE, " ".join(dart_items)):
            score += 20
            signals.append("긍정공시")
        else:
            score += 5
            signals.append("당일공시")

    if np.isfinite(rsi14_val) and 50 <= rsi14_val <= 70:
        score += 8
        signals.append("RSI골든존")
    if np.isfinite(adx_result["adx"]) and adx_result["adx"] >= 20 and adx_result["plusDI"] > adx_result["minusDI"]:
        score += 10
        signals.append("ADX추세↑")
    if current_price >= high252:
        score += 25
        signals.append("52주신고가")
    elif high252 > 0 and current_price / high252 >= 0.95:
        score += 10
        signals.append("신고가근접")

    if score < MIN_SCORE_FINAL:
        return None

    # ---- G2: grade ----
    is_strong = score >= SCORE_STRONG_FINAL
    is_surge = is_c and rvol >= 8.0 and daily_change >= 0.08
    is_short_trade = (not is_strong) and (not is_surge) and is_c and rvol >= 5.0
    grade = "강매" if is_strong else "급등" if is_surge else "매도차익" if is_short_trade else "매수"

    # ---- T: target/stop (priority: strong > C > A > B > D) ----
    atr_abs = calc_atr(high, low, close, 14)[idx - 1] if idx >= 1 else float("nan")
    # calcAtrAbs in JS excludes the current bar (mean(high-low) over trailing window ending idx-1);
    # backtest/indicators.atr() is a rolling mean of true range INCLUDING the bar at each position,
    # so we deliberately read index idx-1 to get the same "as of yesterday's close of window" value.
    if not np.isfinite(atr_abs) or atr_abs <= 0:
        atr_abs = float(np.nanmean(high[max(0, idx - 14) : idx] - low[max(0, idx - 14) : idx]))
    atr_pct = atr_abs / current_price if current_price > 0 else 0.0

    if is_strong:
        target_pct, stop_pct = max(0.10, atr_pct * 1.9), max(0.04, atr_pct * 1.0)
    elif is_c:
        target_pct, stop_pct = max(0.10, atr_pct * 1.8), max(0.04, atr_pct * 0.9)
    elif is_a:
        target_pct = max(abs(pullback_from_event) * 1.3 + 0.03, atr_pct * 1.6, 0.08)
        stop_pct = max(0.04, atr_pct * 0.9)
    elif is_b:
        target_pct = max(abs(corr_pct60) * 0.45, 0.10, atr_pct * 1.5)
        stop_pct = max(0.05, atr_pct * 1.0)
    else:
        target_pct, stop_pct = max(0.10, atr_pct * 1.5), max(0.04, atr_pct * 0.8)

    target_pct = min(target_pct, 0.30)
    stop_pct = min(stop_pct, 0.08)
    target = current_price * (1 + target_pct)
    stop = current_price * (1 - stop_pct)
    rr = (target - current_price) / max(current_price - stop, 1.0)
    if rr < MIN_RR_RATIO_FINAL:
        return None

    pattern_type = "C촉매" if is_c else "A눌림목" if is_a else "B지지선" if is_b else "D박스"
    dow_adj = 3 if day_of_week == 4 else 2 if day_of_week == 3 else -5 if day_of_week == 5 else 0
    rank_score = score + dow_adj

    return SwingCandidate(
        pattern_type=pattern_type,
        score=score,
        rank_score=rank_score,
        grade=grade,
        entry=current_price,
        target=target,
        stop=stop,
        hold_days=_hold_days(grade, pattern_type),
        signals=signals,
    )

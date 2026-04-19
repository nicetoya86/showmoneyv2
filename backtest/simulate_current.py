"""
simulate_current.py — swing_scanner_code.js 현재 알고리즘 시뮬레이션
2026-04-19

현재 구현된 모든 필터를 Python으로 재현:
  - Grade system (강매/급등/매도차익) + ATR 목표 배수 분기
  - OBV-01: 수급 필수 조건
  - MACD-01: MACD 히스토그램 연속 하락 차단 (신규)
  - RSI-01: RSI 방향성 확인 보너스 (신규)
  - DELIST-01: 연속 하락 + 거래량 급감 차단 (신규)

Usage:
  python -m backtest.simulate_current --tickers backtest/tickers_operating_200.txt \
      --start 2025-10-01 --end 2026-04-19 --out sim_result.json

  # OLD vs NEW 비교 (필터 비활성화):
  python -m backtest.simulate_current ... --no-macd-filter --no-rsi-dir --no-delist
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .indicators import atr as calc_atr_arr, max_drawdown, sma as calc_sma_arr
from .yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart


# ─── 상수 (n8n 코드와 동일) ───────────────────────────────────────────────
ATR_STOP_MULT        = 1.9
ATR_TARGET_MULT      = 2.8   # 강매
ATR_TARGET_MULT_NORM = 2.0   # 급등·기타
ATR_TARGET_SHORT     = 1.5   # 매도차익
CAP_STOP_PCT         = 0.10
CAP_TARGET_PCT       = 0.25
MIN_TARGET_PCT       = 0.05
MIN_RR_RATIO         = 1.5
RSI_MIN_ENTRY        = 45
RSI_MAX_ENTRY        = 80
RSI_SURGE_MAX        = 90
ADX_TREND_MIN        = 20
RVOL_GRADE_A         = 3.0
RVOL_GRADE_B         = 2.0
RVOL_GRADE_C         = 1.5
SURGE_DAILY_CHANGE   = 0.05
SURGE_RVOL_MIN       = 5.0
SURGE_SCORE_BONUS    = 50
NEW_HIGH52W_BONUS    = 40
SCORE_STRONG         = 120
SCORE_SURGE          = 100
HOLD_STRONG          = 5
HOLD_SURGE           = 3
HOLD_SHORTTRADE      = 3
RELAX_SCORE          = 60
# 신규
RSI_RISING_BONUS     = 10
DELIST_CONSEC_DOWN   = 5
DELIST_VOL_DROP      = 0.3


# ─── 지표 계산 함수 ────────────────────────────────────────────────────────

def _sma(arr: np.ndarray, w: int) -> np.ndarray:
    return calc_sma_arr(arr, w)


def _rsi14(close: np.ndarray, idx: int) -> float:
    """JS calcRSI14 재현: 단순이동평균 방식"""
    period = 14
    if idx < period:
        return float("nan")
    gains, losses = [], []
    for i in range(max(0, idx - period), idx):
        d = close[i + 1] - close[i]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    if not gains:
        return float("nan")
    ag = float(np.mean(gains))
    al = float(np.mean(losses))
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)


def _macd(close: np.ndarray, idx: int) -> Dict[str, float]:
    """MACD(12,26,9) — 지수이동평균"""
    if idx < 33:
        return {"hist": float("nan"), "histPrev": float("nan"), "goldenCross": False}

    def _ema_val(data, period, end) -> float:
        k = 2.0 / (period + 1)
        v = data[max(0, end - period * 3) : end + 1]
        if len(v) < period:
            return float("nan")
        result = float(np.mean(v[:period]))
        for x in v[period:]:
            result = x * k + result * (1 - k)
        return result

    ema12 = _ema_val(close, 12, idx)
    ema26 = _ema_val(close, 26, idx)
    if not (np.isfinite(ema12) and np.isfinite(ema26)):
        return {"hist": float("nan"), "histPrev": float("nan"), "goldenCross": False}

    macd_line = ema12 - ema26

    # signal(9) — use simple mean of last 9 macd values as approximation
    macd_vals = []
    for j in range(max(0, idx - 15), idx + 1):
        e12 = _ema_val(close, 12, j)
        e26 = _ema_val(close, 26, j)
        if np.isfinite(e12) and np.isfinite(e26):
            macd_vals.append(e12 - e26)
    if len(macd_vals) < 9:
        return {"hist": float("nan"), "histPrev": float("nan"), "goldenCross": False}
    signal = float(np.mean(macd_vals[-9:]))
    hist = macd_line - signal

    # prev hist (idx-1)
    if idx >= 1:
        ema12p = _ema_val(close, 12, idx - 1)
        ema26p = _ema_val(close, 26, idx - 1)
        if np.isfinite(ema12p) and np.isfinite(ema26p):
            macd_prev = ema12p - ema26p
            signal_prev = float(np.mean((macd_vals[:-1])[-9:])) if len(macd_vals) > 9 else signal
            hist_prev = macd_prev - signal_prev
        else:
            hist_prev = float("nan")
    else:
        hist_prev = float("nan")

    golden_cross = (
        np.isfinite(hist) and hist > 0
        and np.isfinite(hist_prev) and hist_prev <= 0
    )
    return {"hist": hist, "histPrev": hist_prev, "goldenCross": bool(golden_cross)}


def _obv_trend(close: np.ndarray, vol: np.ndarray, idx: int, period: int = 20) -> int:
    """OBV 트렌드: +1(상승) / -1(하락) / 0(불명)"""
    if idx < period:
        return 0
    obv_vals = [0.0]
    start = max(0, idx - period)
    for i in range(start + 1, idx + 1):
        d = close[i] - close[i - 1]
        if d > 0:
            obv_vals.append(obv_vals[-1] + vol[i])
        elif d < 0:
            obv_vals.append(obv_vals[-1] - vol[i])
        else:
            obv_vals.append(obv_vals[-1])
    if len(obv_vals) < 2:
        return 0
    half = len(obv_vals) // 2
    return 1 if float(np.mean(obv_vals[half:])) > float(np.mean(obv_vals[:half])) else -1


def _atr_abs(high: np.ndarray, low: np.ndarray, close: np.ndarray, idx: int, window: int = 14) -> float:
    end = idx + 1
    start = max(0, end - window - 1)
    h, l, c = high[start:end], low[start:end], close[start:end]
    if len(h) < 2:
        return float("nan")
    prev_c = c[:-1]
    tr = np.maximum.reduce([
        np.abs(h[1:] - l[1:]),
        np.abs(h[1:] - prev_c),
        np.abs(l[1:] - prev_c),
    ])
    if len(tr) == 0:
        return float("nan")
    return float(np.mean(tr[-window:]))


# ─── DELIST-01 체크 ────────────────────────────────────────────────────────

def _delist_risk(close: np.ndarray, vol: np.ndarray, idx: int) -> bool:
    if idx < 8:
        return False
    consec_down = 0
    for ci in range(idx - 4, idx + 1):
        if ci > 0 and close[ci] < close[ci - 1]:
            consec_down += 1
    recent_vol = float(np.mean(vol[max(0, idx - 3): idx + 1]))
    prev_vol   = float(np.mean(vol[max(0, idx - 8): idx - 3])) if idx >= 8 else 0.0
    vol_dropped = prev_vol > 0 and (recent_vol / prev_vol) < DELIST_VOL_DROP
    return consec_down >= DELIST_CONSEC_DOWN and vol_dropped


# ─── 패턴 점수 계산 ────────────────────────────────────────────────────────

def _score_stock(
    close: np.ndarray,
    high:  np.ndarray,
    low:   np.ndarray,
    vol:   np.ndarray,
    idx:   int,
    *,
    use_macd_filter: bool = True,
    use_rsi_dir:     bool = True,
    use_delist:      bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Returns dict with score, grade, entry/stop/target, signals
    or None if filtered out.
    """
    if idx < 60:
        return None

    current_price = close[idx]
    prev_close    = close[idx - 1] if idx >= 1 else current_price
    daily_change  = (current_price / prev_close - 1.0) if prev_close > 0 else 0.0

    if current_price < 1000:
        return None

    # SMA 정배열
    sma20 = _sma(close, 20)
    sma60 = _sma(close, 60)
    if not (np.isfinite(sma20[idx]) and np.isfinite(sma60[idx]) and sma20[idx] > sma60[idx]):
        return None

    # RVOL
    vol20_avg = float(np.mean(vol[max(0, idx - 20): idx])) if idx >= 20 else float("nan")
    rvol_val  = (vol[idx] / vol20_avg) if vol20_avg > 0 else 0.0
    if rvol_val < 1.0:
        return None

    is_surge_candidate = daily_change >= SURGE_DAILY_CHANGE and rvol_val >= SURGE_RVOL_MIN

    # RSI 필터
    rsi14_val = _rsi14(close, idx)
    if np.isfinite(rsi14_val):
        if rsi14_val < RSI_MIN_ENTRY:
            return None
        if is_surge_candidate and rsi14_val > RSI_SURGE_MAX:
            return None
        if not is_surge_candidate and rsi14_val > RSI_MAX_ENTRY:
            return None

    # DELIST-01
    if use_delist and _delist_risk(close, vol, idx):
        return None

    # 52주 고가/저가
    start252 = max(0, idx - 251)
    high252   = float(np.nanmax(high[start252: idx + 1]))
    low252    = float(np.nanmin(low[start252: idx + 1]))
    pth       = current_price / high252 if high252 > 0 else 1.0
    price_from_low = (current_price - low252) / low252 if low252 > 0 else 0.0

    score    = 0
    signals: List[str] = []

    # 박스권돌파 (20일 고가 돌파)
    recent20_high = float(np.nanmax(high[max(0, idx - 20): idx])) if idx >= 1 else float("nan")
    if np.isfinite(recent20_high) and current_price > recent20_high:
        score += 35
        signals.append("박스권돌파")

    # N자형 눌림목 (10일 고가 > 현재 * 1.15 & SMA20 근접 3%)
    recent10_high = float(np.nanmax(high[max(0, idx - 10): idx])) if idx >= 1 else float("nan")
    if (np.isfinite(recent10_high) and recent10_high > current_price * 1.15
            and np.isfinite(sma20[idx]) and abs(current_price - sma20[idx]) / current_price < 0.03):
        score += 40
        signals.append("N자형눌림목")

    # 정배열 보너스
    score += 15
    signals.append("정배열")

    # RVOL 보너스
    if rvol_val >= RVOL_GRADE_A:
        score += 20; signals.append("RVOL-A")
    elif rvol_val >= RVOL_GRADE_B:
        score += 12; signals.append("RVOL-B")
    elif rvol_val >= RVOL_GRADE_C:
        score += 5;  signals.append("RVOL-C")

    # 52주 신고가/근접
    if current_price >= high252:
        score += NEW_HIGH52W_BONUS; signals.append("52주신고가")
    elif pth >= 0.95:
        score += 15; signals.append("신고가근접95")
    elif pth >= 0.90:
        score += 8;  signals.append("신고가근접90")

    # 저점 반등
    if price_from_low >= 1.0:
        score += 20; signals.append("저점반등100%")
    elif price_from_low >= 0.30:
        score += 10; signals.append("저점반등30%")

    # 급등 보너스
    if is_surge_candidate:
        score += SURGE_SCORE_BONUS
        signals.append("급등후보")

    # RSI-01: 방향성 보너스
    if use_rsi_dir and np.isfinite(rsi14_val):
        rsi5ago = _rsi14(close, max(0, idx - 5))
        rsi_rising = np.isfinite(rsi5ago) and rsi14_val > rsi5ago
        if rsi_rising and rsi14_val >= 50:
            score += RSI_RISING_BONUS; signals.append("RSI상승모멘텀")
        if rsi14_val >= 65 and rsi14_val <= 75:
            score += 5; signals.append("RSI골든존")
    elif np.isfinite(rsi14_val):
        # OLD: 골든존만
        if rsi14_val >= 65 and rsi14_val <= 75:
            score += 10; signals.append("RSI모멘텀")

    # MACD
    macd_result = _macd(close, idx)
    hist     = macd_result["hist"]
    hist_prev = macd_result["histPrev"]
    if macd_result["goldenCross"]:
        score += 15; signals.append("MACD골든크로스")
    elif np.isfinite(hist) and hist > 0:
        if np.isfinite(hist_prev) and hist > hist_prev:
            score += 10; signals.append("MACD모멘텀↑")
        else:
            score += 5; signals.append("MACD양호")
    elif np.isfinite(hist) and np.isfinite(hist_prev) and hist < 0 and hist_prev < 0:
        score -= 10  # 하락 패널티

    # RELAX_SCORE 통과 여부
    if score < RELAX_SCORE:
        return None

    # 등급 판정
    is_strong    = score >= SCORE_STRONG
    is_surge     = (not is_strong
                    and score >= SCORE_SURGE
                    and daily_change >= SURGE_DAILY_CHANGE
                    and rvol_val >= SURGE_RVOL_MIN)
    is_short     = (not is_strong and not is_surge
                    and daily_change >= 0.02 and rvol_val >= RVOL_GRADE_A)
    strict_pass  = score >= 80

    grade = ("강매"     if is_strong
             else "급등"     if is_surge
             else "매도차익" if is_short
             else "매수"     if strict_pass
             else "관심")

    if grade in ("관심", "매수"):
        return None

    # OBV-01: 수급 필수 조건
    obv_trend = _obv_trend(close, vol, idx)
    has_supply = (obv_trend == 1) or (rvol_val >= RVOL_GRADE_A)
    if not has_supply and grade != "강매":
        return None

    # MACD-01: 연속 하락 차단
    if use_macd_filter:
        macd_neg = (np.isfinite(hist) and hist < 0
                    and np.isfinite(hist_prev) and hist_prev < 0)
        if macd_neg and grade != "강매":
            return None

    # ATR 목표 계산
    atr_abs = _atr_abs(high, low, close, idx)
    if not np.isfinite(atr_abs) or atr_abs <= 0:
        return None

    stop   = current_price - atr_abs * ATR_STOP_MULT
    t_mult = (ATR_TARGET_MULT if grade == "강매"
              else ATR_TARGET_SHORT if grade == "매도차익"
              else ATR_TARGET_MULT_NORM)
    target = current_price + atr_abs * t_mult

    stop   = max(stop,   current_price * (1 - CAP_STOP_PCT))
    target = min(target, current_price * (1 + CAP_TARGET_PCT))
    target = max(target, current_price * (1 + MIN_TARGET_PCT))

    rr = (target - current_price) / (current_price - stop) if current_price > stop else 0.0
    if rr < MIN_RR_RATIO:
        return None

    hold_days = (HOLD_STRONG if grade == "강매"
                 else HOLD_SURGE if grade == "급등"
                 else HOLD_SHORTTRADE)

    return {
        "score":      score,
        "grade":      grade,
        "rvol":       round(rvol_val, 2),
        "rsi14":      round(rsi14_val, 1) if np.isfinite(rsi14_val) else None,
        "daily_chg":  round(daily_change * 100, 2),
        "entry":      round(current_price, 0),
        "stop":       round(stop, 0),
        "target":     round(target, 0),
        "hold_days":  hold_days,
        "signals":    signals,
    }


# ─── 거래 시뮬레이션 ──────────────────────────────────────────────────────

def _simulate_trade(
    close: np.ndarray,
    high:  np.ndarray,
    low:   np.ndarray,
    entry_idx: int,
    *,
    entry: float,
    stop: float,
    target: float,
    hold_days: int,
) -> Dict[str, Any]:
    end = min(len(close) - 1, entry_idx + hold_days)
    for i in range(entry_idx, end + 1):
        hi, lo = float(high[i]), float(low[i])
        hit_t = hi >= target
        hit_s = lo <= stop
        if hit_t and hit_s:  # 같은 날 양쪽 도달 → 보수적으로 손절
            return {"exit_idx": i, "exit": stop, "result": "stop", "days": i - entry_idx}
        if hit_t:
            return {"exit_idx": i, "exit": target, "result": "target", "days": i - entry_idx}
        if hit_s:
            return {"exit_idx": i, "exit": stop, "result": "stop", "days": i - entry_idx}
    exit_p = float(close[end])
    return {"exit_idx": end, "exit": exit_p, "result": "timeout", "days": end - entry_idx}


# ─── 메인 백테스트 루프 ────────────────────────────────────────────────────

def run_simulation(
    tickers: List[str],
    *,
    start: str,
    end: str,
    use_macd_filter: bool = True,
    use_rsi_dir:     bool = True,
    use_delist:      bool = True,
    max_daily_picks: int  = 4,
    label: str = "sim",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:

    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts   = pd.Timestamp(end,   tz="UTC")

    per_ticker: Dict[str, pd.DataFrame] = {}
    print(f"[{label}] Fetching {len(tickers)} tickers...")
    for i, t in enumerate(tickers, 1):
        try:
            data = fetch_yahoo_chart(YahooFetchSpec(ticker=t, range="2y", interval="1d"))
            df, _ = chart_to_ohlcv_daily(data)
            df = df.sort_values("timestamp_utc").reset_index(drop=True)
            per_ticker[t] = df
        except Exception as e:
            if i <= 5 or i % 50 == 0:
                print(f"  skip {t}: {e}")
        if i % 100 == 0:
            print(f"  {i}/{len(tickers)} fetched")

    print(f"[{label}] Building trading days...")
    all_days = sorted({d for df in per_ticker.values() for d in df["timestamp_utc"].tolist()})
    all_days = [d for d in all_days if start_ts <= d <= end_ts]

    trades: List[Dict[str, Any]] = []

    for day in all_days:
        day_candidates: List[Dict[str, Any]] = []

        for t, df in per_ticker.items():
            idxs = df.index[df["timestamp_utc"] == day].tolist()
            if not idxs:
                continue
            idx = int(idxs[0])
            if idx + 1 >= len(df):
                continue

            close = df["close"].to_numpy(dtype="float64")
            high  = df["high"].to_numpy(dtype="float64")
            low   = df["low"].to_numpy(dtype="float64")
            vol   = df["volume"].to_numpy(dtype="float64")

            sig = _score_stock(
                close, high, low, vol, idx,
                use_macd_filter=use_macd_filter,
                use_rsi_dir=use_rsi_dir,
                use_delist=use_delist,
            )
            if sig is None:
                continue

            sig["ticker"] = t
            sig["date"]   = day.isoformat()
            sig["_df"]    = df
            sig["_idx"]   = idx
            day_candidates.append(sig)

        if not day_candidates:
            continue

        # 강매 우선, 점수순 정렬 → 상위 max_daily_picks 선택
        day_candidates.sort(
            key=lambda x: (x["grade"] == "강매", x["score"]),
            reverse=True,
        )
        selected = day_candidates[:max_daily_picks]

        for cand in selected:
            df_t     = cand["_df"]
            entry_i  = cand["_idx"] + 1  # 다음 거래일 시가 진입
            if entry_i >= len(df_t):
                continue

            close_t = df_t["close"].to_numpy(dtype="float64")
            high_t  = df_t["high"].to_numpy(dtype="float64")
            low_t   = df_t["low"].to_numpy(dtype="float64")

            # 진입가: 다음 거래일 시가 (없으면 종가 사용)
            entry_p = float(df_t.loc[entry_i, "open"]) if "open" in df_t.columns else cand["entry"]
            if not np.isfinite(entry_p) or entry_p <= 0:
                entry_p = cand["entry"]

            # 시가 기준으로 stop/target 재계산 비율 유지
            ratio = entry_p / cand["entry"]
            stop_p   = cand["stop"]   * ratio
            target_p = cand["target"] * ratio

            sim = _simulate_trade(
                close_t, high_t, low_t, entry_i,
                entry=entry_p, stop=stop_p, target=target_p,
                hold_days=cand["hold_days"],
            )
            pnl = (sim["exit"] - entry_p) / entry_p

            trades.append({
                "date":     cand["date"],
                "ticker":   cand["ticker"],
                "grade":    cand["grade"],
                "score":    cand["score"],
                "rvol":     cand["rvol"],
                "rsi14":    cand["rsi14"],
                "daily_chg": cand["daily_chg"],
                "signals":  "|".join(cand["signals"]),
                "entry":    round(entry_p, 0),
                "stop":     round(stop_p, 0),
                "target":   round(target_p, 0),
                "exit":     round(sim["exit"], 0),
                "result":   sim["result"],
                "days":     sim["days"],
                "pnl":      round(pnl * 100, 2),
            })

    df_out = pd.DataFrame(trades)
    if df_out.empty:
        return df_out, {"label": label, "trades": 0}

    df_out["date_ts"] = pd.to_datetime(df_out["date"])
    df_out = df_out.sort_values(["date_ts", "ticker"]).reset_index(drop=True)

    equity = [1.0]
    for p in df_out["pnl"].tolist():
        equity.append(equity[-1] * (1.0 + p / 100))
    equity_arr = np.array(equity, dtype="float64")

    # 등급별 집계
    by_grade: Dict[str, Any] = {}
    for g in df_out["grade"].unique():
        gdf = df_out[df_out["grade"] == g]
        by_grade[g] = {
            "n":        int(len(gdf)),
            "win_rate": round(float((gdf["pnl"] > 0).mean()) * 100, 1),
            "avg_pnl":  round(float(gdf["pnl"].mean()), 2),
            "target_rate": round(float((gdf["result"] == "target").mean()) * 100, 1),
        }

    stats = {
        "label":        label,
        "period":       f"{start} ~ {end}",
        "tickers":      len(per_ticker),
        "trades":       int(len(df_out)),
        "win_rate":     round(float((df_out["pnl"] > 0).mean()) * 100, 1),
        "avg_pnl":      round(float(df_out["pnl"].mean()), 2),
        "median_pnl":   round(float(df_out["pnl"].median()), 2),
        "target_rate":  round(float((df_out["result"] == "target").mean()) * 100, 1),
        "stop_rate":    round(float((df_out["result"] == "stop").mean()) * 100, 1),
        "timeout_rate": round(float((df_out["result"] == "timeout").mean()) * 100, 1),
        "mdd":          round(float(max_drawdown(equity_arr)) * 100, 2),
        "equity_end":   round(float(equity_arr[-1]), 4),
        "by_grade":     by_grade,
        "filters": {
            "macd_filter": use_macd_filter,
            "rsi_dir":     use_rsi_dir,
            "delist":      use_delist,
        },
    }
    return df_out, stats


# ─── CLI ─────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="swing_scanner_code.js 현재 알고리즘 시뮬레이션")
    ap.add_argument("--tickers", default="backtest/tickers_operating_200.txt")
    ap.add_argument("--start", default="2025-10-01")
    ap.add_argument("--end",   default="2026-04-18")
    ap.add_argument("--max-picks", type=int, default=4)
    ap.add_argument("--out", default="sim_result.json")
    ap.add_argument("--no-macd-filter", action="store_true", help="MACD-01 필터 비활성화 (OLD 비교용)")
    ap.add_argument("--no-rsi-dir",     action="store_true", help="RSI-01 방향성 비활성화 (OLD 비교용)")
    ap.add_argument("--no-delist",      action="store_true", help="DELIST-01 비활성화 (OLD 비교용)")
    ap.add_argument("--compare",        action="store_true", help="OLD vs NEW 비교 모드")
    args = ap.parse_args()

    tickers_path = Path(args.tickers)
    tickers = [x.strip() for x in tickers_path.read_text(encoding="utf-8").splitlines()
               if x.strip() and not x.startswith("#")]
    print(f"Universe: {len(tickers)} tickers | Period: {args.start} ~ {args.end}")

    if args.compare:
        # NEW 알고리즘
        df_new, stats_new = run_simulation(
            tickers, start=args.start, end=args.end,
            use_macd_filter=True, use_rsi_dir=True, use_delist=True,
            max_daily_picks=args.max_picks, label="NEW",
        )
        # OLD 알고리즘 (신규 필터 비활성)
        df_old, stats_old = run_simulation(
            tickers, start=args.start, end=args.end,
            use_macd_filter=False, use_rsi_dir=False, use_delist=False,
            max_daily_picks=args.max_picks, label="OLD",
        )
        def _to_records(df: pd.DataFrame) -> list:
            if df.empty:
                return []
            cols = [c for c in df.columns if c != "date_ts"]
            return df[cols].to_dict(orient="records")

        out = {
            "NEW": {"stats": stats_new, "trades": _to_records(df_new)},
            "OLD": {"stats": stats_old, "trades": _to_records(df_old)},
        }
        _print_comparison(stats_old, stats_new)
    else:
        df_out, stats = run_simulation(
            tickers, start=args.start, end=args.end,
            use_macd_filter=not args.no_macd_filter,
            use_rsi_dir=not args.no_rsi_dir,
            use_delist=not args.no_delist,
            max_daily_picks=args.max_picks,
            label="NEW" if not (args.no_macd_filter or args.no_rsi_dir or args.no_delist) else "custom",
        )
        def _to_records(df: pd.DataFrame) -> list:
            if df.empty:
                return []
            cols = [c for c in df.columns if c != "date_ts"]
            return df[cols].to_dict(orient="records")

        out = {"stats": stats, "trades": _to_records(df_out)}
        _print_stats(stats)

    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {args.out}")


def _print_stats(s: Dict[str, Any]) -> None:
    print("\n" + "=" * 50)
    print(f"[{s['label']}] {s['period']} | {s['tickers']} tickers")
    print("=" * 50)
    print(f"  거래 수:      {s['trades']:>6}건")
    print(f"  승률:         {s['win_rate']:>6.1f}%")
    print(f"  평균 수익:    {s['avg_pnl']:>+6.2f}%")
    print(f"  중위 수익:    {s['median_pnl']:>+6.2f}%")
    print(f"  목표가 도달: {s['target_rate']:>6.1f}%")
    print(f"  손절:         {s['stop_rate']:>6.1f}%")
    print(f"  타임아웃:     {s['timeout_rate']:>6.1f}%")
    print(f"  MDD:         {s['mdd']:>+6.2f}%")
    print(f"  최종 자산:   {s['equity_end']:.4f}x")
    if s.get("by_grade"):
        print("\n  [등급별]")
        for g, v in s["by_grade"].items():
            print(f"    {g:6s}: {v['n']:3d}건 | 승률 {v['win_rate']:.0f}% | 평균 {v['avg_pnl']:+.2f}% | 목표 {v['target_rate']:.0f}%")


def _print_comparison(old: Dict[str, Any], new: Dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print("  OLD(신규 필터 없음) vs NEW(MACD+RSI방향성+DELIST 적용)")
    print("=" * 60)
    rows = [
        ("거래 수 (건)",    old["trades"],       new["trades"],       ""),
        ("승률 (%)",        old["win_rate"],      new["win_rate"],     "%"),
        ("평균 수익 (%)",   old["avg_pnl"],       new["avg_pnl"],      "%"),
        ("중위 수익 (%)",   old["median_pnl"],    new["median_pnl"],   "%"),
        ("목표가 도달 (%)", old["target_rate"],   new["target_rate"],  "%"),
        ("손절 (%)",        old["stop_rate"],     new["stop_rate"],    "%"),
        ("MDD (%)",         old["mdd"],           new["mdd"],          "%"),
        ("최종 자산 (x)",   old["equity_end"],    new["equity_end"],   "x"),
    ]
    print(f"  {'지표':<18} {'OLD':>10} {'NEW':>10} {'개선':>8}")
    print(f"  {'-'*18} {'-'*10} {'-'*10} {'-'*8}")
    for name, ov, nv, unit in rows:
        try:
            diff = nv - ov
            arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "─")
            print(f"  {name:<18} {str(ov)+unit:>10} {str(nv)+unit:>10} {arrow}{abs(diff):.2f}{unit:>3}")
        except Exception:
            print(f"  {name:<18} {str(ov):>10} {str(nv):>10}")
    print("=" * 60)


if __name__ == "__main__":
    main()

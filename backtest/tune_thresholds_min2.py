from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from .models import LogisticModel
from .strategy_rules import ConservativeConfig, build_hitalk_features_daily, score_scalping, score_swing
from .yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart
from .indicators import sma


def _load_tickers(path: Path) -> List[str]:
    lines = [x.strip() for x in path.read_text(encoding="utf-8").splitlines()]
    return [x for x in lines if x and not x.startswith("#")]


def _iter_days(per_ticker: Dict[str, pd.DataFrame], start: pd.Timestamp, end: pd.Timestamp) -> List[pd.Timestamp]:
    all_days = sorted({d for df in per_ticker.values() for d in df["timestamp_utc"].tolist()})
    return [d for d in all_days if start <= d <= end]


def _build_per_ticker(tickers: List[str], *, years: str) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for t in tickers:
        data = fetch_yahoo_chart(YahooFetchSpec(ticker=t, range=years, interval="1d"))
        df, _ = chart_to_ohlcv_daily(data)
        df = df.sort_values("timestamp_utc").reset_index(drop=True)
        out[t] = df
    return out


def _candidate_table_scalping(
    per_ticker: Dict[str, pd.DataFrame],
    *,
    model: LogisticModel,
    start: pd.Timestamp,
    end: pd.Timestamp,
    min_price: float,
    min_turnover: float,
) -> Dict[str, List[Tuple[float, int]]]:
    """
    Returns per-day list of (prob, score) for candidates passing basic price/turnover gates.
    """
    out: Dict[str, List[Tuple[float, int]]] = {}
    for day in _iter_days(per_ticker, start, end):
        key = day.date().isoformat()
        rows: List[Tuple[float, int]] = []
        for t, df in per_ticker.items():
            idxs = df.index[df["timestamp_utc"] == day].tolist()
            if not idxs:
                continue
            idx = int(idxs[0])
            if idx < 70:
                continue
            price = float(df.loc[idx, "close"])
            vol = float(df.loc[idx, "volume"])
            if not (price >= min_price and price * vol >= min_turnover):
                continue
            feats = build_hitalk_features_daily(df, idx)
            score, _ = score_scalping(feats)
            p = float(model.predict_proba(feats))
            rows.append((p, score))
        if rows:
            out[key] = rows
    return out


def _candidate_table_swing(
    per_ticker: Dict[str, pd.DataFrame],
    *,
    model: LogisticModel,
    start: pd.Timestamp,
    end: pd.Timestamp,
    min_price: float,
    min_turnover: float,
) -> Dict[str, List[Tuple[float, int]]]:
    out: Dict[str, List[Tuple[float, int]]] = {}
    for day in _iter_days(per_ticker, start, end):
        key = day.date().isoformat()
        rows: List[Tuple[float, int]] = []
        for t, df in per_ticker.items():
            idxs = df.index[df["timestamp_utc"] == day].tolist()
            if not idxs:
                continue
            idx = int(idxs[0])
            if idx < 70:
                continue
            price = float(df.loc[idx, "close"])
            vol = float(df.loc[idx, "volume"])
            if not (price >= min_price and price * vol >= min_turnover):
                continue

            close = df["close"].to_numpy(dtype="float64")
            high = df["high"].to_numpy(dtype="float64")
            sma20 = sma(close, 20)
            sma60 = sma(close, 60)
            daily_uptrend = bool(np.isfinite(sma20[idx]) and np.isfinite(sma60[idx]) and sma20[idx] > sma60[idx])
            if not daily_uptrend:
                continue

            recent20_high = float(np.nanmax(high[max(0, idx - 20) : idx])) if idx >= 1 else float("nan")
            box_breakout = bool(np.isfinite(recent20_high) and close[idx] > recent20_high)
            recent10_high = float(np.nanmax(high[max(0, idx - 10) : idx])) if idx >= 1 else float("nan")
            n_pattern = bool(
                np.isfinite(recent10_high)
                and recent10_high > close[idx] * 1.15
                and np.isfinite(sma20[idx])
                and abs(close[idx] - sma20[idx]) / close[idx] < 0.03
            )

            feats = build_hitalk_features_daily(df, idx)
            score, _ = score_swing(feats, box_breakout=box_breakout, n_pattern=n_pattern, daily_uptrend=daily_uptrend)
            if score <= 0:
                continue
            p = float(model.predict_proba(feats))
            rows.append((p, score))
        if rows:
            out[key] = rows
    return out


def _evaluate_min2(
    day_rows: Dict[str, List[Tuple[float, int]]],
    *,
    p_strict: float,
    p_relax: float,
    score_strict: int,
    score_relax: int,
    min_picks: int,
    max_picks: int,
) -> Dict[str, float]:
    selected_counts: List[int] = []
    strict_counts: List[int] = []
    for rows in day_rows.values():
        strict_cnt = sum(1 for p, s in rows if (p >= p_strict and s >= score_strict))
        relax_cnt = sum(1 for p, s in rows if (p >= p_relax and s >= score_relax))
        # strict first, then fill until min_picks (if possible)
        sel = min(max_picks, strict_cnt)
        if sel < min_picks:
            need = min(min_picks - sel, max_picks - sel)
            extra = max(0, min(need, relax_cnt - strict_cnt))
            sel += extra
        selected_counts.append(sel)
        strict_counts.append(min(strict_cnt, max_picks))
    if not selected_counts:
        return {"days": 0, "avg": 0.0, "median": 0.0, "min2_ratio": 0.0, "strict_ratio": 0.0}
    avg = float(np.mean(selected_counts))
    med = float(np.median(selected_counts))
    min2 = float(np.mean([1.0 if c >= min_picks else 0.0 for c in selected_counts]))
    # strict_ratio among selected: approximate by strict_cnt / max(sel,1) averaged
    sr = float(np.mean([(sc / max(sel, 1)) for sc, sel in zip(strict_counts, selected_counts)]))
    return {"days": int(len(selected_counts)), "avg": avg, "median": med, "min2_ratio": min2, "strict_ratio": sr}


def tune(
    day_rows: Dict[str, List[Tuple[float, int]]],
    *,
    score_strict: int,
    score_relax: int,
    min_picks: int,
    max_picks: int,
    target_avg: float,
    p_min: float,
    p_max: float,
    p_step: float,
    weight_min2: float,
    weight_avg: float,
    weight_strict: float,
) -> Dict[str, Any]:
    # grid search (conservative bounds)
    p_grid = [round(float(x), 2) for x in np.arange(p_min, p_max + (p_step / 2.0), p_step)]
    best = None
    best_obj = None
    best_metrics = None
    for p_strict in p_grid:
        for p_relax in p_grid:
            if p_relax > p_strict:
                continue
            m = _evaluate_min2(
                day_rows,
                p_strict=p_strict,
                p_relax=p_relax,
                score_strict=score_strict,
                score_relax=score_relax,
                min_picks=min_picks,
                max_picks=max_picks,
            )
            # objective: maximize min2 coverage, keep avg near target, prefer higher strict_ratio
            obj = (
                (1.0 - m["min2_ratio"]) * weight_min2
                + abs(m["avg"] - target_avg) * weight_avg
                + (0.5 - m["strict_ratio"]) * weight_strict
            )
            if best is None or obj < best_obj:
                best = (p_strict, p_relax)
                best_obj = obj
                best_metrics = m
    assert best is not None and best_metrics is not None
    return {
        "p_strict": float(best[0]),
        "p_relax": float(best[1]),
        "score_strict": int(score_strict),
        "score_relax": int(score_relax),
        "metrics": best_metrics,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default=pd.Timestamp.utcnow().strftime("%Y-%m-%d"))
    ap.add_argument("--years", default="5y", help="Yahoo range parameter (e.g., 2y, 5y, 10y)")
    ap.add_argument("--out", default="thresholds_min2.json")
    ap.add_argument("--scalping-min-picks", type=int, default=None, help="단타 일 최소 추천 수(기본: config 값)")
    ap.add_argument("--swing-min-picks", type=int, default=None, help="스윙 일 최소 추천 수(기본: config 값)")
    args = ap.parse_args()

    cfg = ConservativeConfig()
    tickers = _load_tickers(Path(args.tickers))
    per_ticker = _build_per_ticker(tickers, years=args.years)

    start = pd.to_datetime(args.start, utc=True)
    end = pd.to_datetime(args.end, utc=True)

    up_model = LogisticModel.from_json(Path("models/hitalk_setup_up_model.json"))
    mat_model = LogisticModel.from_json(Path("models/hitalk_setup_mat_model.json"))

    scalping_rows = _candidate_table_scalping(
        per_ticker,
        model=up_model,
        start=start,
        end=end,
        min_price=cfg.min_price,
        min_turnover=cfg.min_turnover,
    )
    swing_rows = _candidate_table_swing(
        per_ticker,
        model=mat_model,
        start=start,
        end=end,
        min_price=cfg.min_price,
        min_turnover=cfg.min_turnover,
    )

    out = {
        "generatedAt": pd.Timestamp.utcnow().isoformat() + "Z",
        "range": {"start": args.start, "end": args.end, "years": args.years},
        "tickers": len(tickers),
        "scalping": tune(
            scalping_rows,
            score_strict=cfg.scalping_min_score_strict,
            score_relax=cfg.scalping_min_score_relax,
            min_picks=int(args.scalping_min_picks) if args.scalping_min_picks is not None else cfg.min_daily_picks,
            max_picks=cfg.max_daily_picks,
            target_avg=2.4,
            p_min=0.82,
            p_max=0.96,
            p_step=0.01,
            weight_min2=5.0,
            weight_avg=0.7,
            weight_strict=0.5,
        ),
        "swing": tune(
            swing_rows,
            score_strict=cfg.swing_min_score_strict,
            score_relax=cfg.swing_min_score_relax,
            min_picks=int(args.swing_min_picks) if args.swing_min_picks is not None else cfg.min_daily_picks,
            max_picks=4,
            target_avg=2.2,
            # swing pMAT tends to be lower; allow wider search.
            p_min=0.60,
            p_max=0.92,
            p_step=0.01,
            # prioritize "at least 2" more strongly for swing.
            weight_min2=8.0,
            weight_avg=0.5,
            weight_strict=0.2,
        ),
    }

    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


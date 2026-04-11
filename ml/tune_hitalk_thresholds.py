import argparse
import json
import os
import random
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Reuse helpers from hitalk_train_setups_binary.py by loading the module file directly
# (workspace may not be installed as a package on Windows).
import importlib.util

_mod_path = os.path.join(os.path.dirname(__file__), "hitalk_train_setups_binary.py")
_spec = importlib.util.spec_from_file_location("hitalk_train_setups_binary", _mod_path)
if _spec is None or _spec.loader is None:
    raise RuntimeError("Failed to load hitalk_train_setups_binary.py")
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)  # type: ignore

FEATURE_COLS = _m.FEATURE_COLS
build_features = _m.build_features
fetch_daily_window = _m.fetch_daily_window
find_idx_kst = _m.find_idx_kst
krx_top_turnover_codes = _m.krx_top_turnover_codes
load_hitalk = _m.load_hitalk


def load_model(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def predict_bin(model: Dict[str, Any], feat_row: Dict[str, float]) -> float:
    cols = model["feature_cols"]
    x = np.array([float(feat_row.get(c, 0.0) or 0.0) for c in cols], dtype=np.float64)
    mu = np.array(model["scaler"]["mean"], dtype=np.float64)
    sc = np.array(model["scaler"]["scale"], dtype=np.float64)
    sc = np.where(sc == 0, 1.0, sc)
    xs = (x - mu) / sc
    w = np.array(model["coef"], dtype=np.float64)
    b = float(model["intercept"])
    return float(sigmoid(float(np.dot(w, xs) + b)))


def choose_threshold(counts_by_day: Dict[str, int], target_avg: float, *, min_nonzero_days_ratio: float = 0.5) -> Tuple[float, Dict[str, Any]]:
    # Grid search threshold 0.50~0.95
    days = list(counts_by_day.keys())
    if not days:
        return 0.8, {"reason": "no_days"}

    # We'll approximate by assuming monotonicity: higher threshold -> fewer passes.
    # We need distribution of per-stock scores to do exact. Instead we pass precomputed per-day list in caller.
    raise NotImplementedError


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default="hitalk_full_data.xlsx")
    ap.add_argument("--cache-yahoo", default="cache/yahoo")
    ap.add_argument("--cache-krx", default="cache/krx")
    ap.add_argument("--model-up", default="models/hitalk_setup_up_model.json")
    ap.add_argument("--model-mat", default="models/hitalk_setup_mat_model.json")
    ap.add_argument("--top-turnover", type=int, default=800)
    ap.add_argument("--sample-per-day", type=int, default=0, help="If >0, randomly sample this many tickers per day from the top-turnover list to speed up tuning.")
    ap.add_argument("--eval-days", type=int, default=80)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--target-up", type=float, default=4.0)
    ap.add_argument("--target-mat", type=float, default=2.5)
    ap.add_argument("--out", default="models/hitalk_thresholds.json")
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    up_model = load_model(args.model_up)
    mat_model = load_model(args.model_mat)

    df = load_hitalk(args.xlsx)
    # evaluate on recent unique dates (prefer 2025 first)
    df["rec_date"] = pd.to_datetime(df["rec_date"], errors="coerce")
    df = df.dropna(subset=["rec_date"])
    unique_days = sorted(df["rec_date"].dt.date.unique().tolist())
    unique_days = unique_days[-args.eval_days :]

    # For each day: compute pUP/pMAT for all top-turnover codes (or a subset if too slow)
    day_scores_up: Dict[str, List[float]] = {}
    day_scores_mat: Dict[str, List[float]] = {}

    for day in unique_days:
        day_ts = pd.Timestamp(day)
        try:
            codes = krx_top_turnover_codes(args.cache_krx, day_ts, top_n=args.top_turnover)
        except Exception:
            continue
        if args.sample_per_day and args.sample_per_day > 0 and len(codes) > args.sample_per_day:
            codes = random.sample(codes, args.sample_per_day)
        su: List[float] = []
        sm: List[float] = []
        for code6 in codes:
            fetched = fetch_daily_window(args.cache_yahoo, code6, day_ts)
            if fetched is None:
                continue
            _, series = fetched
            idx = find_idx_kst(series, day_ts)
            if idx is None or idx < 60:
                continue
            feats = build_features(series, idx)
            # fill NaNs with 0 (models are standardized; 0 after standardization ~ mean)
            for k in FEATURE_COLS:
                if not np.isfinite(feats.get(k, np.nan)):
                    feats[k] = np.nan
            # replace NaN with per-day median-ish 0 fallback
            for k in feats:
                if feats[k] is None or not np.isfinite(feats[k]):
                    feats[k] = 0.0
            su.append(predict_bin(up_model, feats))
            sm.append(predict_bin(mat_model, feats))
        if su:
            day_scores_up[str(day)] = su
        if sm:
            day_scores_mat[str(day)] = sm
        print(f"[tune] day={day} tickers_scored={len(codes)} kept_up={len(su)} kept_mat={len(sm)}")
        time.sleep(0.05)

    def tune(day_scores: Dict[str, List[float]], target_avg: float) -> Dict[str, Any]:
        thresholds = [round(x, 2) for x in np.arange(0.50, 0.96, 0.01)]
        best = None
        best_obj = None
        for thr in thresholds:
            counts = [sum(1 for p in ps if p >= thr) for ps in day_scores.values()]
            if not counts:
                continue
            avg = float(np.mean(counts))
            nonzero = float(np.mean([1.0 if c > 0 else 0.0 for c in counts]))
            # We want near target and not too sparse
            obj = abs(avg - target_avg) + (0.2 if nonzero < 0.55 else 0.0)
            if best is None or obj < best_obj:
                best = thr
                best_obj = obj
        if best is None:
            best = 0.80
        counts = [sum(1 for p in ps if p >= best) for ps in day_scores.values()]
        return {
            "threshold": float(best),
            "avg_candidates_per_day": float(np.mean(counts)) if counts else 0.0,
            "median_candidates_per_day": float(np.median(counts)) if counts else 0.0,
            "p90_candidates_per_day": float(np.quantile(counts, 0.90)) if counts else 0.0,
            "nonzero_day_ratio": float(np.mean([1.0 if c > 0 else 0.0 for c in counts])) if counts else 0.0,
            "days_evaluated": int(len(counts)),
        }

    up_tuned = tune(day_scores_up, args.target_up)
    mat_tuned = tune(day_scores_mat, args.target_mat)

    out = {
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "eval_days": args.eval_days,
        "top_turnover": args.top_turnover,
        "targets": {"up_avg": args.target_up, "mat_avg": args.target_mat},
        "UP": up_tuned,
        "MAT": mat_tuned,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"written {args.out}")
    print(out)


if __name__ == "__main__":
    main()



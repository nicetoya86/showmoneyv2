import argparse
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


@dataclass
class YahooSeries:
    timestamp: np.ndarray  # epoch seconds
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _http_get_json(url: str, *, timeout: int = 20, retries: int = 3, sleep_sec: float = 1.0) -> Dict[str, Any]:
    last_err: Optional[Exception] = None
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
    }
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            if i < retries - 1:
                time.sleep(sleep_sec * (i + 1))
    raise RuntimeError(f"GET failed: {url} ({last_err})")


def _cache_path(cache_dir: str, key: str) -> str:
    return os.path.join(cache_dir, f"{_sha1(key)}.json")


def cached_get_json(cache_dir: str, url: str, *, timeout: int = 20, retries: int = 3) -> Dict[str, Any]:
    _ensure_dir(cache_dir)
    p = _cache_path(cache_dir, url)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    data = _http_get_json(url, timeout=timeout, retries=retries)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def load_hitalk_xlsx(xlsx_path: str) -> pd.DataFrame:
    df = pd.read_excel(xlsx_path, sheet_name=0)
    df = df.copy()
    df.columns = ["type", "name", "code", "rec_price", "hit_price", "return_pct", "hit_days", "rec_date", "sell_date"]
    df["rec_date"] = pd.to_datetime(df["rec_date"], errors="coerce")
    df["sell_date"] = pd.to_datetime(df["sell_date"], errors="coerce")
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["type"] = df["type"].astype(str).str.strip()
    df = df.dropna(subset=["rec_date", "code", "type"])
    return df


def kr_code_to_yahoo_ticker(code: str) -> str:
    # We don't know market(KS/KQ) from file; heuristic:
    # - If code is in KOSPI it is .KS else .KQ. We can't query KRX here reliably.
    # Practical approach: try .KS first; if no data, fallback to .KQ during fetch.
    return code


def parse_yahoo_series(resp: Dict[str, Any]) -> Optional[YahooSeries]:
    try:
        result = resp["chart"]["result"][0]
        ts = np.array(result["timestamp"], dtype=np.int64)
        quote = result["indicators"]["quote"][0]
        def arr(key: str) -> np.ndarray:
            v = quote.get(key, [])
            out = np.array([x if x is not None else np.nan for x in v], dtype=np.float64)
            return out
        o = arr("open")
        h = arr("high")
        l = arr("low")
        c = arr("close")
        v = arr("volume")
        return YahooSeries(timestamp=ts, open=o, high=h, low=l, close=c, volume=v)
    except Exception:
        return None


def yahoo_chart_url(ticker: str, *, range_: str, interval: str) -> str:
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_}&interval={interval}"


def yahoo_chart_url_period(ticker: str, *, period1: int, period2: int, interval: str) -> str:
    # Explicit time window so older recommendations (e.g., 2022) can be fetched.
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={period1}&period2={period2}&interval={interval}"


def fetch_daily_series(cache_dir: str, code6: str) -> Optional[Tuple[str, YahooSeries]]:
    # Try KOSPI suffix first then KOSDAQ
    for suffix in (".KS", ".KQ"):
        ticker = f"{code6}{suffix}"
        url = yahoo_chart_url(ticker, range_="1y", interval="1d")
        try:
            resp = cached_get_json(cache_dir, url)
        except Exception:
            continue
        ser = parse_yahoo_series(resp)
        if ser is None or ser.close.size < 60 or np.all(np.isnan(ser.close)):
            continue
        return ticker, ser
    return None


def fetch_daily_series_window(cache_dir: str, code6: str, rec_date: pd.Timestamp) -> Optional[Tuple[str, YahooSeries]]:
    """
    Fetch daily series around rec_date (instead of 'last 1y from today') so that
    older rows in hitalk_full_data are not dropped.
    """
    # window: rec_date-240d to rec_date+5d
    start = (rec_date - pd.Timedelta(days=240)).to_pydatetime()
    end = (rec_date + pd.Timedelta(days=5)).to_pydatetime()
    p1 = int(start.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    p2 = int(end.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

    for suffix in (".KS", ".KQ"):
        ticker = f"{code6}{suffix}"
        url = yahoo_chart_url_period(ticker, period1=p1, period2=p2, interval="1d")
        try:
            resp = cached_get_json(cache_dir, url)
        except Exception:
            continue
        ser = parse_yahoo_series(resp)
        if ser is None or ser.close.size < 60 or np.all(np.isnan(ser.close)):
            continue
        return ticker, ser
    return None


def sma(x: np.ndarray, w: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=np.float64)
    if x.size < w:
        return out
    csum = np.cumsum(np.nan_to_num(x, nan=0.0))
    for i in range(w - 1, x.size):
        start = i - w + 1
        total = csum[i] - (csum[start - 1] if start > 0 else 0.0)
        out[i] = total / w
    return out


def rsi(close: np.ndarray, p: int = 14) -> np.ndarray:
    out = np.full(close.shape, np.nan, dtype=np.float64)
    if close.size < p + 1:
        return out
    diff = np.diff(close)
    up = np.maximum(diff, 0)
    dn = np.maximum(-diff, 0)
    # simple moving average for stability
    au = sma(np.concatenate([[np.nan], up]), p)
    ad = sma(np.concatenate([[np.nan], dn]), p)
    for i in range(close.size):
        if i == 0:
            continue
        if i >= au.size or i >= ad.size:
            continue
        if np.isnan(au[i]) or np.isnan(ad[i]):
            continue
        rs = 999.0 if ad[i] == 0 else au[i] / ad[i]
        out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def find_index_for_date(series: YahooSeries, rec_date: pd.Timestamp, tz_offset_hours: int = 9) -> Optional[int]:
    # Yahoo timestamps are UTC seconds. We convert to KST date string and match.
    target = rec_date.date().isoformat()
    for i, t in enumerate(series.timestamp):
        dt = datetime.utcfromtimestamp(int(t)) + timedelta(hours=tz_offset_hours)
        if dt.date().isoformat() == target:
            return i
    # fallback: nearest previous
    # choose last index with date <= target
    best: Optional[int] = None
    for i, t in enumerate(series.timestamp):
        dt = datetime.utcfromtimestamp(int(t)) + timedelta(hours=tz_offset_hours)
        if dt.date().isoformat() <= target:
            best = i
    return best


def build_features_daily(series: YahooSeries, idx: int) -> Dict[str, float]:
    c = series.close
    h = series.high
    l = series.low
    v = series.volume

    close = c[idx]
    prev_close = c[idx - 1] if idx - 1 >= 0 else np.nan
    daily_change = (close / prev_close - 1.0) if (prev_close and not np.isnan(prev_close) and prev_close > 0) else np.nan

    sma20 = sma(c, 20)
    sma60 = sma(c, 60)
    uptrend = 1.0 if (not np.isnan(sma20[idx]) and not np.isnan(sma60[idx]) and sma20[idx] > sma60[idx]) else 0.0

    rsi14 = rsi(c, 14)
    rsi_v = rsi14[idx] if idx < rsi14.size else np.nan

    # breakout strength: close vs last 20-day high (excluding today)
    start20 = max(0, idx - 20)
    prev20_high = np.nanmax(h[start20:idx]) if idx - start20 >= 1 else np.nan
    breakout20 = 1.0 if (not np.isnan(prev20_high) and close > prev20_high) else 0.0
    breakout_ratio = (close / prev20_high) if (not np.isnan(prev20_high) and prev20_high > 0) else np.nan

    # longer breakout windows
    start60 = max(0, idx - 60)
    prev60_high = np.nanmax(h[start60:idx]) if idx - start60 >= 1 else np.nan
    breakout60 = 1.0 if (not np.isnan(prev60_high) and close > prev60_high) else 0.0
    breakout60_ratio = (close / prev60_high) if (not np.isnan(prev60_high) and prev60_high > 0) else np.nan

    # volume surge: today's volume vs 20-day avg (excluding today)
    vwin = v[start20:idx]
    vavg = np.nanmean(vwin) if vwin.size >= 5 else np.nan
    vsurge = (v[idx] / vavg) if (not np.isnan(vavg) and vavg > 0) else np.nan

    # short/long volume ratios
    v5 = v[max(0, idx - 5):idx]
    v60 = v[start60:idx]
    vavg5 = np.nanmean(v5) if v5.size >= 3 else np.nan
    vavg60 = np.nanmean(v60) if v60.size >= 10 else np.nan
    vsurge5 = (v[idx] / vavg5) if (not np.isnan(vavg5) and vavg5 > 0) else np.nan
    vsurge60 = (v[idx] / vavg60) if (not np.isnan(vavg60) and vavg60 > 0) else np.nan
    vtrend_5_20 = (vavg5 / vavg) if (not np.isnan(vavg5) and not np.isnan(vavg) and vavg > 0) else np.nan

    # volatility: (high-low)/close for today (approx)
    hl = (series.high[idx] - series.low[idx]) if (not np.isnan(series.high[idx]) and not np.isnan(series.low[idx])) else np.nan
    volat = (hl / close) if (not np.isnan(hl) and close and close > 0) else np.nan

    # multi-day returns
    def ret_n(n: int) -> float:
        j = idx - n
        if j < 0 or np.isnan(c[j]) or c[j] <= 0 or np.isnan(close) or close <= 0:
            return np.nan
        return float(close / c[j] - 1.0)

    ret5 = ret_n(5)
    ret20 = ret_n(20)

    # distance from moving averages
    dist_sma20 = (close / sma20[idx] - 1.0) if (not np.isnan(sma20[idx]) and sma20[idx] > 0 and close > 0) else np.nan
    dist_sma60 = (close / sma60[idx] - 1.0) if (not np.isnan(sma60[idx]) and sma60[idx] > 0 and close > 0) else np.nan
    trend_strength = ((sma20[idx] - sma60[idx]) / close) if (not np.isnan(sma20[idx]) and not np.isnan(sma60[idx]) and close > 0) else np.nan

    # ATR-ish ratio over last 14 days
    start14 = max(0, idx - 14)
    hl14 = (h[start14:idx] - l[start14:idx]) if idx - start14 >= 5 else np.array([], dtype=np.float64)
    atr_ratio = (np.nanmean(hl14) / close) if (hl14.size >= 5 and close > 0) else np.nan

    return {
        "daily_change": float(daily_change) if not np.isnan(daily_change) else np.nan,
        "uptrend": float(uptrend),
        "rsi14": float(rsi_v) if not np.isnan(rsi_v) else np.nan,
        "breakout20": float(breakout20),
        "breakout_ratio": float(breakout_ratio) if not np.isnan(breakout_ratio) else np.nan,
        "breakout60": float(breakout60),
        "breakout60_ratio": float(breakout60_ratio) if not np.isnan(breakout60_ratio) else np.nan,
        "volume_surge": float(vsurge) if not np.isnan(vsurge) else np.nan,
        "volume_surge5": float(vsurge5) if not np.isnan(vsurge5) else np.nan,
        "volume_surge60": float(vsurge60) if not np.isnan(vsurge60) else np.nan,
        "volume_trend_5_20": float(vtrend_5_20) if not np.isnan(vtrend_5_20) else np.nan,
        "volatility": float(volat) if not np.isnan(volat) else np.nan,
        "atr14": float(atr_ratio) if not np.isnan(atr_ratio) else np.nan,
        "ret5": float(ret5) if not np.isnan(ret5) else np.nan,
        "ret20": float(ret20) if not np.isnan(ret20) else np.nan,
        "dist_sma20": float(dist_sma20) if not np.isnan(dist_sma20) else np.nan,
        "dist_sma60": float(dist_sma60) if not np.isnan(dist_sma60) else np.nan,
        "trend_strength": float(trend_strength) if not np.isnan(trend_strength) else np.nan,
        "price": float(close) if not np.isnan(close) else np.nan,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default="hitalk_full_data.xlsx")
    ap.add_argument("--cache-dir", default="cache/yahoo")
    ap.add_argument("--out-model", default="models/hitalk_type_model.json")
    ap.add_argument("--out-trainset", default="ml/hitalk_trainset.parquet")
    ap.add_argument("--max-samples", type=int, default=1200)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    df = load_hitalk_xlsx(args.xlsx)
    # Keep only core types to start; 중기 is too small -> optional later
    keep_types = ["단타", "급등", "재료", "스윙", "단기"]
    df = df[df["type"].isin(keep_types)].copy()

    # stratified sampling
    df = df.sample(frac=1.0, random_state=args.seed)  # shuffle
    sampled = []
    for t, g in df.groupby("type"):
        k = min(len(g), max(50, int(args.max_samples * (len(g) / len(df)))))
        sampled.append(g.head(k))
    sdf = pd.concat(sampled, ignore_index=True)
    sdf = sdf.sample(frac=1.0, random_state=args.seed).reset_index(drop=True)

    rows: List[Dict[str, Any]] = []
    skipped = 0
    for _, r in sdf.iterrows():
        code6 = str(r["code"]).zfill(6)
        rec_date = r["rec_date"]
        fetched = fetch_daily_series_window(args.cache_dir, code6, rec_date)
        if fetched is None:
            skipped += 1
            continue
        ticker, series = fetched
        idx = find_index_for_date(series, rec_date)
        if idx is None or idx < 60 or idx >= series.close.size:
            skipped += 1
            continue
        feat = build_features_daily(series, idx)
        if any(np.isnan(v) for v in feat.values()):
            # keep, but later we will fillna
            pass
        rows.append(
            {
                "type": r["type"],
                "ticker": ticker,
                "code": code6,
                "rec_date": rec_date.date().isoformat(),
                **feat,
            }
        )
        time.sleep(0.05)  # gentle rate limit

    train = pd.DataFrame(rows)
    if train.empty:
        raise SystemExit("No training rows built. Network/cache issue?")

    # fill missing numeric values with median
    feature_cols = [
        "daily_change",
        "uptrend",
        "rsi14",
        "breakout20",
        "breakout_ratio",
        "breakout60",
        "breakout60_ratio",
        "volume_surge",
        "volume_surge5",
        "volume_surge60",
        "volume_trend_5_20",
        "volatility",
        "atr14",
        "ret5",
        "ret20",
        "dist_sma20",
        "dist_sma60",
        "trend_strength",
        "price",
    ]
    for c in feature_cols:
        med = train[c].median()
        train[c] = train[c].fillna(med)

    X = train[feature_cols].to_numpy(dtype=np.float64)
    y = train["type"].to_numpy()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=args.seed, stratify=y
    )
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    clf = LogisticRegression(
        multi_class="multinomial",
        solver="lbfgs",
        max_iter=1000,
        n_jobs=None,
        class_weight="balanced",
        random_state=args.seed,
    )
    clf.fit(X_train_s, y_train)
    y_pred = clf.predict(X_test_s)

    print("=== Training set ===")
    print(f"built_rows={len(train)} skipped={skipped}")
    print(pd.Series(y).value_counts())
    print("\n=== Classification report ===")
    print(classification_report(y_test, y_pred, digits=3))
    print("\n=== Confusion matrix (rows=true, cols=pred) ===")
    labels = list(clf.classes_)
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    print(labels)
    print(cm)

    _ensure_dir(os.path.dirname(args.out_model))
    model = {
        "classes": labels,
        "feature_cols": feature_cols,
        "scaler": {
            "mean": scaler.mean_.tolist(),
            "scale": scaler.scale_.tolist(),
        },
        "coef": clf.coef_.tolist(),  # shape [n_classes, n_features]
        "intercept": clf.intercept_.tolist(),
        "meta": {
            "source": args.xlsx,
            "generatedAt": datetime.utcnow().isoformat() + "Z",
            "train_rows": int(len(train)),
            "skipped": int(skipped),
            "seed": int(args.seed),
        },
    }
    with open(args.out_model, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=2)

    # persist trainset for debugging
    _ensure_dir(os.path.dirname(args.out_trainset))
    train.to_parquet(args.out_trainset, index=False)
    print(f"\nSaved model -> {args.out_model}")
    print(f"Saved trainset -> {args.out_trainset}")


if __name__ == "__main__":
    main()



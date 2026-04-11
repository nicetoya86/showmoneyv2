from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from .indicators import max_drawdown, sma
from .models import LogisticModel
from .strategy_rules import ConservativeConfig, Signal, build_hitalk_features_daily, compute_atr_plan, score_swing
from .yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart


def _load_tickers(path: Path) -> List[str]:
    lines = [x.strip() for x in path.read_text(encoding="utf-8").splitlines()]
    return [x for x in lines if x and not x.startswith("#")]


def _simulate_trade_daily(
    df: pd.DataFrame,
    entry_idx: int,
    *,
    entry: float,
    stop: float,
    target: float,
    max_holding_days: int,
    conservative_if_both_hit: bool = True,
) -> Dict[str, Any]:
    end = min(len(df) - 1, entry_idx + max_holding_days)
    for i in range(entry_idx, end + 1):
        hi = float(df.loc[i, "high"])
        lo = float(df.loc[i, "low"])
        hit_target = hi >= target
        hit_stop = lo <= stop
        if hit_target and hit_stop:
            if conservative_if_both_hit:
                return {"exit_idx": i, "exit_price": stop, "result": "stop", "days_held": i - entry_idx}
            return {"exit_idx": i, "exit_price": target, "result": "target", "days_held": i - entry_idx}
        if hit_target:
            return {"exit_idx": i, "exit_price": target, "result": "target", "days_held": i - entry_idx}
        if hit_stop:
            return {"exit_idx": i, "exit_price": stop, "result": "stop", "days_held": i - entry_idx}

    exit_price = float(df.loc[end, "close"])
    return {"exit_idx": end, "exit_price": exit_price, "result": "timeout", "days_held": end - entry_idx}


def backtest_swing(
    tickers: List[str],
    *,
    cfg: ConservativeConfig,
    mat_model: LogisticModel,
    start: str,
    end: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    per_ticker: Dict[str, pd.DataFrame] = {}
    for t in tickers:
        data = fetch_yahoo_chart(YahooFetchSpec(ticker=t, range="5y", interval="1d"))
        df, _ = chart_to_ohlcv_daily(data)
        df = df.sort_values("timestamp_utc").reset_index(drop=True)
        per_ticker[t] = df

    start_ts = pd.to_datetime(start, utc=True)
    end_ts = pd.to_datetime(end, utc=True)

    all_days = sorted({d for df in per_ticker.values() for d in df["timestamp_utc"].tolist()})
    all_days = [d for d in all_days if start_ts <= d <= end_ts]

    trades: List[Dict[str, Any]] = []

    for day in all_days:
        candidates: List[Signal] = []
        for t, df in per_ticker.items():
            idxs = df.index[df["timestamp_utc"] == day].tolist()
            if not idxs:
                continue
            idx = int(idxs[0])
            if idx < 70 or idx + 1 >= len(df):
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
            score, tags = score_swing(feats, box_breakout=box_breakout, n_pattern=n_pattern, daily_uptrend=daily_uptrend)
            if score <= 0:
                continue

            p_mat = float(mat_model.predict_proba(feats))
            strict_pass = (p_mat >= cfg.pmat_strict) and (score >= cfg.swing_min_score_strict)
            relaxed_pass = (p_mat >= cfg.pmat_relax) and (score >= cfg.swing_min_score_relax)
            if not relaxed_pass:
                continue

            entry_idx = idx + 1
            entry = float(df.loc[entry_idx, "open"])
            atr_val = float(feats.get("atr_abs", np.nan))
            stop, target = compute_atr_plan(entry, atr_val, cfg)

            candidates.append(
                Signal(
                    date=day,
                    ticker=t,
                    name=t,
                    kind="Swing",
                    entry=entry,
                    stop=stop,
                    target=target,
                    score=score,
                    prob=p_mat,
                    strict=bool(strict_pass),
                    tags=tags + ([] if strict_pass else ["완화"]),
                )
            )

        if not candidates:
            continue

        candidates.sort(key=lambda s: (s.prob, s.score), reverse=True)
        strict_selected = [c for c in candidates if c.strict][: cfg.max_daily_picks]
        selected = list(strict_selected)
        if len(selected) < cfg.min_daily_picks:
            need = min(cfg.min_daily_picks - len(selected), cfg.max_daily_picks - len(selected))
            used = {s.ticker for s in selected}
            fillers = [c for c in candidates if (c.ticker not in used) and (not c.strict)][:need]
            selected.extend(fillers)

        for s in selected:
            df = per_ticker[s.ticker]
            entry_day_idx = int(df.index[df["timestamp_utc"] == s.date][0]) + 1
            sim = _simulate_trade_daily(
                df,
                entry_day_idx,
                entry=s.entry,
                stop=s.stop,
                target=s.target,
                max_holding_days=cfg.swing_holding_days,
            )
            pnl = (float(sim["exit_price"]) - s.entry) / s.entry
            trades.append(
                {
                    "date": s.date.isoformat(),
                    "ticker": s.ticker,
                    "strict": s.strict,
                    "score": s.score,
                    "prob": s.prob,
                    "entry": s.entry,
                    "stop": s.stop,
                    "target": s.target,
                    "exit_price": float(sim["exit_price"]),
                    "result": sim["result"],
                    "days_held": sim["days_held"],
                    "pnl": pnl,
                }
            )

    df_trades = pd.DataFrame(trades)
    if df_trades.empty:
        return df_trades, {"reason": "no_trades"}

    df_trades["date_ts"] = pd.to_datetime(df_trades["date"])
    df_trades = df_trades.sort_values(["date_ts", "ticker"]).reset_index(drop=True)

    equity = [1.0]
    for pnl in df_trades["pnl"].astype(float).tolist():
        equity.append(equity[-1] * (1.0 + pnl))
    equity_arr = np.asarray(equity, dtype="float64")

    stats = {
        "trades": int(len(df_trades)),
        "win_rate": float((df_trades["pnl"] > 0).mean()) if len(df_trades) else 0.0,
        "avg_pnl": float(df_trades["pnl"].mean()) if len(df_trades) else 0.0,
        "median_pnl": float(df_trades["pnl"].median()) if len(df_trades) else 0.0,
        "mdd": float(max_drawdown(equity_arr)),
        "equity_end": float(equity_arr[-1]),
        "strict_ratio": float((df_trades["strict"] == True).mean()) if len(df_trades) else 0.0,  # noqa: E712
    }
    return df_trades, stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True, help="Path to tickers.txt (one per line, e.g., 005930.KS)")
    ap.add_argument("--start", default="2024-01-01", help="UTC date (YYYY-MM-DD)")
    ap.add_argument("--end", default=pd.Timestamp.utcnow().strftime("%Y-%m-%d"), help="UTC date (YYYY-MM-DD)")
    ap.add_argument("--model-mat", default="models/hitalk_setup_mat_model.json")
    ap.add_argument("--out", default="backtest_out_swing.json")
    args = ap.parse_args()

    tickers = _load_tickers(Path(args.tickers))
    cfg = ConservativeConfig(max_daily_picks=4)  # swing default
    mat_model = LogisticModel.from_json(Path(args.model_mat))

    df_trades, stats = backtest_swing(
        tickers,
        cfg=cfg,
        mat_model=mat_model,
        start=args.start,
        end=args.end,
    )

    out = {
        "kind": "Swing",
        "params": {"start": args.start, "end": args.end, "tickers": len(tickers)},
        "stats": stats,
        "trades": df_trades.to_dict(orient="records"),
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


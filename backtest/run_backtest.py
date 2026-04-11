from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from .indicators import max_drawdown
from .models import LogisticModel
from .strategy_rules import ConservativeConfig, Signal, build_hitalk_features_daily, compute_atr_plan, score_scalping
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
    """
    Daily-bar simulation:
    - iterate next candles up to holding limit
    - if high>=target and low<=stop on same day:
        conservative_if_both_hit=True => count as stop hit first
    """
    end = min(len(df) - 1, entry_idx + max_holding_days)
    for i in range(entry_idx, end + 1):
        hi = float(df.loc[i, "high"])
        lo = float(df.loc[i, "low"])
        if np.isfinite(hi) and np.isfinite(lo):
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

    # time exit at close
    exit_price = float(df.loc[end, "close"])
    return {"exit_idx": end, "exit_price": exit_price, "result": "timeout", "days_held": end - entry_idx}


def backtest_scalping(
    tickers: List[str],
    *,
    cfg: ConservativeConfig,
    up_model: LogisticModel,
    start: str,
    end: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Simplified daily-bar backtest for scalping:
    - candidate if score>=relax_score and pUP>=relax threshold
    - strict/relaxed tagging
    - per-day: strict picks first, then fill up to min_daily_picks with relaxed
    - trade simulation: entry at next-day open (conservative, avoids lookahead)
    """
    per_ticker: Dict[str, pd.DataFrame] = {}
    for t in tickers:
        data = fetch_yahoo_chart(YahooFetchSpec(ticker=t, range="2y", interval="1d"))
        df, _ = chart_to_ohlcv_daily(data)
        df = df.sort_values("timestamp_utc").reset_index(drop=True)
        per_ticker[t] = df

    start_ts = pd.to_datetime(start, utc=True)
    end_ts = pd.to_datetime(end, utc=True)

    # build unified calendar by collecting all dates across tickers
    all_days = sorted({d for df in per_ticker.values() for d in df["timestamp_utc"].tolist()})
    all_days = [d for d in all_days if start_ts <= d <= end_ts]

    trades: List[Dict[str, Any]] = []
    signals_out: List[Signal] = []

    for day in all_days:
        candidates: List[Signal] = []
        for t, df in per_ticker.items():
            idxs = df.index[df["timestamp_utc"] == day].tolist()
            if not idxs:
                continue
            idx = int(idxs[0])
            if idx < 70 or idx + 1 >= len(df):
                continue

            # rule-based score (matches n8n intent)
            feats = build_hitalk_features_daily(df, idx)
            score, tags = score_scalping(feats)

            # ML prob (UP model)
            p_up = float(up_model.predict_proba(feats))

            strict_pass = (p_up >= cfg.pup_strict) and (score >= cfg.scalping_min_score_strict)
            relaxed_pass = (p_up >= cfg.pup_relax) and (score >= cfg.scalping_min_score_relax)
            if not relaxed_pass:
                continue

            entry_idx = idx + 1  # next day open (avoid lookahead)
            entry = float(df.loc[entry_idx, "open"])
            atr_val = float(feats.get("atr_abs", np.nan))
            stop, target = compute_atr_plan(entry, atr_val, cfg)
            sig = Signal(
                date=day,
                ticker=t,
                name=t,
                kind="Scalping",
                entry=entry,
                stop=stop,
                target=target,
                score=score,
                prob=p_up,
                strict=bool(strict_pass),
                tags=tags + ([] if strict_pass else ["완화"]),
            )
            candidates.append(sig)

        if not candidates:
            continue

        # rank: probability first, then score
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
                max_holding_days=2,  # scalping: short holding
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
            signals_out.append(s)

    df_trades = pd.DataFrame(trades)
    if df_trades.empty:
        return df_trades, {"reason": "no_trades"}

    # equity curve (simple: equal weight each trade, sequential by date)
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
    ap.add_argument("--model-up", default="models/hitalk_setup_up_model.json")
    ap.add_argument("--out", default="backtest_out_scalping.json")
    args = ap.parse_args()

    tickers = _load_tickers(Path(args.tickers))
    cfg = ConservativeConfig()
    up_model = LogisticModel.from_json(Path(args.model_up))

    df_trades, stats = backtest_scalping(
        tickers,
        cfg=cfg,
        up_model=up_model,
        start=args.start,
        end=args.end,
    )

    out = {
        "kind": "Scalping",
        "params": {"start": args.start, "end": args.end, "tickers": len(tickers)},
        "stats": stats,
        "trades": df_trades.to_dict(orient="records"),
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


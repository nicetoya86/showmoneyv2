from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import requests

from .dart_history import fetch_disclosures_for_date
from .indicators import max_drawdown
from .krx_supply_history import fetch_supply_for_date
from .simulate_exits import simulate_exit
from .toss_liveprice import apply_toss_liveprice
from .transaction_costs import apply_round_trip_cost
from .swing_signal_engine import SwingCandidate, evaluate_candidate
from .yahoo_cache import YahooFetchSpec, chart_to_ohlcv_daily, fetch_yahoo_chart

GRADE_ORDER = {"강매": 4, "급등": 3, "매도차익": 2, "매수": 1}
MAX_STOCK_PER_SEND = 3
MAX_WEEKLY_SENDS = 15
DART_API_KEY = "34a9b090d2a7b1ee689a240fef68667d36b389e7"  # matches production (already public in this repo)


def _load_tickers(path: Path) -> List[str]:
    lines = [x.strip() for x in path.read_text(encoding="utf-8").splitlines()]
    return [x for x in lines if x and not x.startswith("#")]


def _code_of(ticker: str) -> str:
    return ticker[:-3] if ticker.endswith(".KS") or ticker.endswith(".KQ") else ticker


def apply_daily_selection(
    todays_candidates: List[Tuple[str, SwingCandidate]],
    week_state: Dict[str, Any],
    *,
    max_per_day: int = MAX_STOCK_PER_SEND,
    max_per_week: int = MAX_WEEKLY_SENDS,
) -> List[Tuple[str, SwingCandidate]]:
    """Mirrors src/swing-scanner.src.js:1520-1554 (weekly cap -> dedup -> grade/rank sort -> top-N/day)."""
    if week_state["count"] >= max_per_week:
        return []
    qualified = [(code, c) for code, c in todays_candidates if code not in week_state["codes"]]
    qualified.sort(key=lambda pair: (GRADE_ORDER.get(pair[1].grade, 0), pair[1].rank_score), reverse=True)
    selected = qualified[:max_per_day]
    for code, _ in selected:
        week_state["codes"].add(code)
        week_state["count"] += 1
    return selected


def _iso_week_key(date: pd.Timestamp) -> Tuple[int, int]:
    iso = date.isocalendar()
    return (int(iso[0]), int(iso[1]))


def backtest_swing_v2(
    tickers: List[str],
    *,
    start: str,
    end: str,
    dart_api_key: str = DART_API_KEY,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    per_ticker: Dict[str, pd.DataFrame] = {}
    skipped_tickers: List[Dict[str, str]] = []
    for t in tickers:
        try:
            data = fetch_yahoo_chart(YahooFetchSpec(ticker=t, range="5y", interval="1d"))
            df, _ = chart_to_ohlcv_daily(data)
            df = df.sort_values("timestamp_utc").reset_index(drop=True)
            per_ticker[t] = df
        except (requests.exceptions.RequestException, ValueError) as e:
            print(f"WARNING: skipping ticker {t} - fetch failed: {e}")
            skipped_tickers.append({"ticker": t, "error": str(e)})
            continue

    start_ts = pd.to_datetime(start, utc=True)
    end_ts = pd.to_datetime(end, utc=True)
    all_days = sorted({d for df in per_ticker.values() for d in df["timestamp_utc"].tolist()})
    all_days = [d for d in all_days if start_ts <= d <= end_ts]

    trades: List[Dict[str, Any]] = []
    week_state: Dict[str, Any] = {"key": None, "count": 0, "codes": set()}
    code_to_ticker = {_code_of(t): t for t in tickers}
    blocked_by_toss: List[Dict[str, str]] = []

    for day in all_days:
        week_key = _iso_week_key(day)
        if week_key != week_state["key"]:
            week_state = {"key": week_key, "count": 0, "codes": set()}

        trd_dd = day.strftime("%Y%m%d")
        supply_map = fetch_supply_for_date(trd_dd)
        dart_map = fetch_disclosures_for_date(trd_dd, api_key=dart_api_key)

        todays_candidates: List[Tuple[str, SwingCandidate]] = []
        for t, df in per_ticker.items():
            idxs = df.index[df["timestamp_utc"] == day].tolist()
            if not idxs:
                continue
            idx = int(idxs[0])
            if idx + 1 >= len(df):
                continue
            code = _code_of(t)
            cand = evaluate_candidate(
                df, idx,
                supply=supply_map.get(code, {}),
                dart_items=dart_map.get(code, []),
                day_of_week=int(day.isoweekday() % 7),  # Mon=1..Sun=0, matches JS getUTCDay()
            )
            if cand is not None:
                todays_candidates.append((code, cand))

        selected = apply_daily_selection(todays_candidates, week_state)
        for code, cand in selected:
            ticker = code_to_ticker[code]
            df = per_ticker[ticker]
            entry_idx = int(df.index[df["timestamp_utc"] == day][0]) + 1
            if entry_idx >= len(df):
                continue
            next_day_open = float(df.iloc[entry_idx]["open"])
            toss = apply_toss_liveprice(cand.entry, cand.target, cand.stop, next_day_open)
            if toss.status in ("blocked_chasing", "blocked_stopped_out"):
                blocked_by_toss.append({
                    "date": day.isoformat(), "ticker": ticker, "code": code, "reason": toss.status,
                })
                continue
            sim = simulate_exit(
                df, entry_idx,
                entry=toss.entry, stop=toss.stop, target=toss.target, hold_days=cand.hold_days,
            )
            gross_pnl = (float(sim["exit_price"]) - toss.entry) / toss.entry
            pnl = apply_round_trip_cost(gross_pnl)
            trades.append({
                "date": day.isoformat(), "ticker": ticker, "code": code,
                "pattern_type": cand.pattern_type, "grade": cand.grade,
                "score": cand.score, "rank_score": cand.rank_score,
                "entry": toss.entry, "stop": toss.stop, "target": toss.target,
                "exit_price": float(sim["exit_price"]), "result": sim["result"],
                "days_held": sim["days_held"], "pnl": pnl,
                "gross_pnl": gross_pnl, "toss_status": toss.status,
            })

    df_trades = pd.DataFrame(trades)
    if df_trades.empty:
        empty_stats: Dict[str, Any] = {"reason": "no_trades"}
        if skipped_tickers:
            empty_stats["skipped_tickers"] = skipped_tickers
        if blocked_by_toss:
            empty_stats["blocked_by_toss"] = blocked_by_toss
        return df_trades, empty_stats

    df_trades["date_ts"] = pd.to_datetime(df_trades["date"])
    df_trades = df_trades.sort_values(["date_ts", "code"]).reset_index(drop=True)
    df_trades = df_trades.drop(columns=["date_ts"])  # Drop temp column before serialization

    equity = [1.0]
    for pnl in df_trades["pnl"].astype(float).tolist():
        equity.append(equity[-1] * (1.0 + pnl))
    equity_arr = np.asarray(equity, dtype="float64")

    stats = {
        "trades": int(len(df_trades)),
        "win_rate": float((df_trades["pnl"] > 0).mean()),
        "avg_pnl": float(df_trades["pnl"].mean()),
        "median_pnl": float(df_trades["pnl"].median()),
        "mdd": float(max_drawdown(equity_arr)),
        "equity_end": float(equity_arr[-1]),
        "skipped_tickers": skipped_tickers,
        "blocked_by_toss": blocked_by_toss,
    }
    return df_trades, stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-01-01")
    ap.add_argument("--out", default="backtest_out_swing_v2.json")
    args = ap.parse_args()

    tickers = _load_tickers(Path(args.tickers))
    df_trades, stats = backtest_swing_v2(tickers, start=args.start, end=args.end)

    out = {
        "params": {"start": args.start, "end": args.end, "tickers": len(tickers)},
        "stats": stats,
        "trades": df_trades.to_dict(orient="records") if not df_trades.empty else [],
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

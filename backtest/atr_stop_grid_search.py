"""
Sub-project 4 (Phase C) Stage 3: item 5, an ATR-based/volatility-adjusted target and stop in
place of target_stop_grid_search.py's flat target_pct/stop_pct -- that file stays unmodified
(off-limits per every prior sub-project's design docs). Reuses the same TOSS-LIVEPRICE,
exit-simulation, transaction-cost, and portfolio-CAGR primitives, replacing only how
target/stop are derived from entry. See
docs/superpowers/specs/2026-08-01-swing-algo-oversold-bounce-hitrate-design.md.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd

from .analyze_portfolio_return import cagr_and_mdd, simulate_portfolio
from .generate_signal_candidates import CachedCandidate
from .run_swing_v2_backtest import _iso_week_key, apply_daily_selection
from .simulate_exits import simulate_exit
from .target_stop_grid_search import MIN_HIT_RATE, MIN_TRADES_PER_WEEK
from .toss_liveprice import apply_toss_liveprice
from .transaction_costs import apply_round_trip_cost


def _window_df(c: CachedCandidate) -> pd.DataFrame:
    """Lazily builds and caches the small per-candidate OHLC DataFrame simulate_exit needs.
    A local duplicate of target_stop_grid_search.py's identical private helper -- kept
    separate rather than imported, since that file's leading-underscore helpers are not
    meant to be a cross-module interface."""
    cached = getattr(c, "_atr_window_df_cache", None)
    if cached is None:
        cached = pd.DataFrame({
            "open": c.window_open, "high": c.window_high,
            "low": c.window_low, "close": c.window_close,
        })
        c._atr_window_df_cache = cached
    return cached


def run_one_atr_config(
    candidates: List[CachedCandidate],
    *,
    target_mult: float,
    stop_mult: float,
    atr_lookup: Dict[Tuple[str, str], float],
    start: str,
    end: str,
) -> Dict[str, Any]:
    start_ts = pd.to_datetime(start, utc=True)
    end_ts = pd.to_datetime(end, utc=True)
    weeks = max((end_ts - start_ts).days / 7.0, 1e-9)

    by_day: Dict[pd.Timestamp, List[CachedCandidate]] = {}
    for c in candidates:
        by_day.setdefault(pd.Timestamp(c.date), []).append(c)

    week_state: Dict[str, Any] = {"key": None, "count": 0, "codes": set()}
    trades: List[Dict[str, Any]] = []
    for day in sorted(by_day.keys()):
        week_key = _iso_week_key(day)
        if week_key != week_state["key"]:
            week_state = {"key": week_key, "count": 0, "codes": set()}

        filtered = [(c.code, c) for c in by_day[day]]
        selected = apply_daily_selection(filtered, week_state)
        for code, c in selected:
            atr_pct = atr_lookup.get((c.ticker, c.date))
            if atr_pct is None:
                continue
            new_target = c.entry * (1 + target_mult * atr_pct)
            new_stop = c.entry * (1 - stop_mult * atr_pct)
            next_day_open = c.window_open[0] if c.window_open else c.entry
            toss = apply_toss_liveprice(c.entry, new_target, new_stop, next_day_open)
            if toss.status in ("blocked_chasing", "blocked_stopped_out"):
                continue
            df = _window_df(c)
            if df.empty:
                continue
            sim = simulate_exit(
                df, 0, entry=toss.entry, stop=toss.stop, target=toss.target, hold_days=c.hold_days,
            )
            gross_pnl = (float(sim["exit_price"]) - toss.entry) / toss.entry
            pnl = apply_round_trip_cost(gross_pnl)
            trades.append({
                "date": c.date, "ticker": c.ticker, "code": code,
                "pnl": pnl, "result": sim["result"],
            })

    n_trades = len(trades)
    base = {"target_mult": target_mult, "stop_mult": stop_mult}
    if n_trades == 0:
        return {
            **base, "n_trades": 0, "hit_rate": 0.0, "trades_per_week": 0.0,
            "avg_pnl": 0.0, "cagr_15slot": float("nan"), "mdd_15slot": 0.0,
        }

    hit_rate = sum(1 for t in trades if t["result"] == "target") / n_trades
    avg_pnl = sum(t["pnl"] for t in trades) / n_trades
    trades_sorted = sorted(trades, key=lambda t: (t["date"], t["ticker"]))
    curve = simulate_portfolio(trades_sorted, 15)
    _, mdd, _, cagr = cagr_and_mdd(curve, trades_sorted[0]["date"], trades_sorted[-1]["date"])

    return {
        **base, "n_trades": n_trades, "hit_rate": hit_rate,
        "trades_per_week": n_trades / weeks, "avg_pnl": avg_pnl,
        "cagr_15slot": cagr, "mdd_15slot": mdd,
    }


GRID_TARGET_MULT = [1.0, 1.5, 2.0, 3.0]
GRID_STOP_MULT = [0.5, 1.0, 1.5, 2.0]


def build_atr_grid() -> List[Dict[str, float]]:
    return [
        {"target_mult": tm, "stop_mult": sm}
        for tm in GRID_TARGET_MULT
        for sm in GRID_STOP_MULT
    ]


def select_best_atr_config(train_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    qualifying = [
        r for r in train_results
        if r["hit_rate"] >= MIN_HIT_RATE and r["trades_per_week"] >= MIN_TRADES_PER_WEEK
    ]
    if qualifying:
        best = max(qualifying, key=lambda r: r["cagr_15slot"])
        return {"status": "target_met", "config": best, "fallback_top5": [], "fallback_best_cagr": None}

    freq_ok = [r for r in train_results if r["trades_per_week"] >= MIN_TRADES_PER_WEEK]
    fallback_sorted = sorted(freq_ok, key=lambda r: (r["hit_rate"], r["cagr_15slot"]), reverse=True)
    best_cagr_overall = max(train_results, key=lambda r: r["cagr_15slot"]) if train_results else None
    chosen = fallback_sorted[0] if fallback_sorted else best_cagr_overall
    return {
        "status": "target_not_met",
        "config": chosen,
        "fallback_top5": fallback_sorted[:5],
        "fallback_best_cagr": best_cagr_overall,
    }


def run_atr_grid_search(
    candidates: List[CachedCandidate],
    *,
    atr_lookup: Dict[Tuple[str, str], float],
    train_start: str,
    train_end: str,
    test_start: str,
    test_end: str,
) -> Dict[str, Any]:
    train_start_ts = pd.to_datetime(train_start, utc=True)
    train_end_ts = pd.to_datetime(train_end, utc=True)
    test_start_ts = pd.to_datetime(test_start, utc=True)
    test_end_ts = pd.to_datetime(test_end, utc=True)
    train_candidates = [c for c in candidates if train_start_ts <= pd.Timestamp(c.date) <= train_end_ts]
    test_candidates = [c for c in candidates if test_start_ts <= pd.Timestamp(c.date) <= test_end_ts]

    grid = build_atr_grid()
    train_results = [
        run_one_atr_config(
            train_candidates, atr_lookup=atr_lookup, start=train_start, end=train_end, **cell
        )
        for cell in grid
    ]
    selection = select_best_atr_config(train_results)
    chosen = selection["config"]
    test_result = run_one_atr_config(
        test_candidates, atr_lookup=atr_lookup, start=test_start, end=test_end,
        target_mult=chosen["target_mult"], stop_mult=chosen["stop_mult"],
    )
    return {"train_results": train_results, "selection": selection, "test_result": test_result}

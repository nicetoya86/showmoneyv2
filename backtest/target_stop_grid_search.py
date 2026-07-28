"""
Phase 2 of the target/stop retuning sub-project: grid-searches target_pct/stop_pct/min_score/
regime_gate/exclude_d_box combinations against Phase 1's cached candidates
(backtest/generate_signal_candidates.py), reusing sub-project 1's TOSS-LIVEPRICE, exit-simulation,
transaction-cost, and portfolio-CAGR functions unmodified. See
docs/superpowers/specs/2026-07-27-swing-algo-target-stop-retuning-design.md for the full design.

hit_rate here means (result == "target").mean() -- the fraction of trades that actually touched
the target price -- which is NOT the same metric as run_swing_v2_backtest.py's win_rate stat
((pnl > 0).mean()). Do not conflate the two.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from .analyze_portfolio_return import cagr_and_mdd, simulate_portfolio
from .generate_signal_candidates import CachedCandidate
from .run_swing_v2_backtest import _iso_week_key, apply_daily_selection
from .simulate_exits import simulate_exit
from .toss_liveprice import apply_toss_liveprice
from .transaction_costs import apply_round_trip_cost


def _window_df(c: CachedCandidate) -> pd.DataFrame:
    """Lazily builds and caches the small per-candidate OHLC DataFrame simulate_exit needs.
    Cached on the CachedCandidate instance itself so repeated grid cells (which all reuse the
    same candidate objects) don't rebuild it ~432 times per candidate."""
    cached = getattr(c, "_window_df_cache", None)
    if cached is None:
        cached = pd.DataFrame({
            "open": c.window_open, "high": c.window_high,
            "low": c.window_low, "close": c.window_close,
        })
        c._window_df_cache = cached
    return cached


def run_one_config(
    candidates: List[CachedCandidate],
    *,
    target_pct: float,
    stop_pct: float,
    min_score: int,
    regime_gate: bool,
    exclude_d_box: bool,
    regime_lookup: Dict[str, int],
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

        filtered = []
        for c in by_day[day]:
            if c.score < min_score:
                continue
            if exclude_d_box and c.pattern_type == "D박스":
                continue
            if regime_gate:
                level = regime_lookup.get(day.date().isoformat(), 0)
                if level >= 2 and c.grade != "강매":
                    continue
            filtered.append((c.code, c))

        selected = apply_daily_selection(filtered, week_state)
        for code, c in selected:
            new_target = c.entry * (1 + target_pct)
            new_stop = c.entry * (1 - stop_pct)
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
    base = {
        "target_pct": target_pct, "stop_pct": stop_pct, "min_score": min_score,
        "regime_gate": regime_gate, "exclude_d_box": exclude_d_box,
    }
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


GRID_TARGET_PCT = [0.03, 0.04, 0.05, 0.06, 0.08, 0.10]
GRID_STOP_PCT = [0.01, 0.015, 0.02, 0.025, 0.03, 0.04]
GRID_MIN_SCORE = [60, 90, 110]
GRID_REGIME_GATE = [False, True]
GRID_EXCLUDE_D_BOX = [False, True]

MIN_HIT_RATE = 0.90
MIN_TRADES_PER_WEEK = 5.0


def build_grid() -> List[Dict[str, Any]]:
    return [
        {
            "target_pct": tp, "stop_pct": sp, "min_score": ms,
            "regime_gate": rg, "exclude_d_box": ed,
        }
        for tp in GRID_TARGET_PCT
        for sp in GRID_STOP_PCT
        for ms in GRID_MIN_SCORE
        for rg in GRID_REGIME_GATE
        for ed in GRID_EXCLUDE_D_BOX
    ]


def select_best_config(train_results: List[Dict[str, Any]]) -> Dict[str, Any]:
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


def run_grid_search(
    candidates: List[CachedCandidate],
    *,
    regime_lookup: Dict[str, int],
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

    grid = build_grid()
    train_results = [
        run_one_config(
            train_candidates, regime_lookup=regime_lookup, start=train_start, end=train_end, **cell
        )
        for cell in grid
    ]
    selection = select_best_config(train_results)
    chosen = selection["config"]
    test_result = run_one_config(
        test_candidates, regime_lookup=regime_lookup, start=test_start, end=test_end,
        target_pct=chosen["target_pct"], stop_pct=chosen["stop_pct"], min_score=chosen["min_score"],
        regime_gate=chosen["regime_gate"], exclude_d_box=chosen["exclude_d_box"],
    )
    return {"train_results": train_results, "selection": selection, "test_result": test_result}

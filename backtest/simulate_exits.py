from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd


def simulate_exit(
    df: pd.DataFrame,
    entry_idx: int,
    *,
    entry: float,
    stop: float,
    target: float,
    hold_days: int,
) -> Dict[str, Any]:
    """Day-by-day forward walk from entry_idx: exits on first target/stop touch, else at
    hold_days timeout. hold_days counts the entry day itself as day 1 (matches production's
    "최대 N거래일" semantics) — hold_days=1 means only entry_idx is held."""
    end = min(len(df) - 1, entry_idx + hold_days - 1)
    for i in range(entry_idx, end + 1):
        hi = float(df.iloc[i]["high"])
        lo = float(df.iloc[i]["low"])
        hit_target = hi >= target
        hit_stop = lo <= stop
        if hit_target and hit_stop:
            return {"exit_idx": i, "exit_price": stop, "result": "stop", "days_held": i - entry_idx}
        if hit_target:
            return {"exit_idx": i, "exit_price": target, "result": "target", "days_held": i - entry_idx}
        if hit_stop:
            return {"exit_idx": i, "exit_price": stop, "result": "stop", "days_held": i - entry_idx}
    exit_price = float(df.iloc[end]["close"])
    return {"exit_idx": end, "exit_price": exit_price, "result": "timeout", "days_held": end - entry_idx}


def _finalize_partial(
    tranches: List[Dict[str, Any]], entry: float, days_held: int, result: str
) -> Dict[str, Any]:
    total_weight = sum(t["weight"] for t in tranches)
    exit_price = (
        sum(t["weight"] * t["price"] for t in tranches) / total_weight
        if total_weight > 0 else entry
    )
    return {"exit_price": exit_price, "result": result, "days_held": days_held, "tranches": tranches}


def simulate_exit_partial(
    df: pd.DataFrame,
    entry_idx: int,
    *,
    entry: float,
    stop: float,
    atr_pct: float,
    hold_days: int,
) -> Dict[str, Any]:
    """3-tranche partial-exit + trailing-stop model matching src/swing-scanner.src.js's Telegram
    message (lines 1782-1811): 30% @ +2%, 30% @ +4%, remaining 40% on trailing-stop-breach or
    hold_days timeout (whichever first). Trailing width = clamp(atr_pct, 1%, 3%) of entry.
    See docs/superpowers/specs/2026-08-02-swing-algo-partial-exit-simulation-design.md
    Sections 3-4 for the full state machine and same-bar tie-break convention this implements.

    Same-bar tie-break: whenever a day could plausibly trigger more than one outcome, the
    worse-for-the-trader outcome is checked first (stop before the +2% trigger pre-trigger;
    trailing-stop breach before the +4% partial in the runner phase). The running high used for
    a day's trailing-stop check is as of the *previous* day's close -- the current day's own high
    only feeds into the running high used for the *next* day's check.

    Returns exit_price as the position-weighted average fill price across whichever tranches
    executed (weights sum to 1.0) -- downstream pnl math ((exit_price - entry) / entry) is
    unchanged from simulate_exit()'s contract, since
    pnl_pct = sum(weight_i * (price_i/entry - 1)) = (sum(weight_i * price_i))/entry - 1
    algebraically.
    """
    trailing_pct = max(0.01, min(atr_pct, 0.03))
    trigger_price = entry * 1.02
    target4_price = entry * 1.04

    end = min(len(df) - 1, entry_idx + hold_days - 1)

    tranches: List[Dict[str, Any]] = []
    triggered = False
    target4_taken = False
    running_high = 0.0
    remaining_weight = 1.0

    for i in range(entry_idx, end + 1):
        hi = float(df.iloc[i]["high"])
        lo = float(df.iloc[i]["low"])

        if not triggered:
            if lo <= stop:
                tranches.append({"day_idx": i, "weight": remaining_weight, "price": stop, "reason": "stop"})
                return _finalize_partial(tranches, entry, i - entry_idx, "pretrigger_stop")
            if hi >= trigger_price:
                tranches.append({"day_idx": i, "weight": 0.30, "price": trigger_price, "reason": "trigger_2pct"})
                remaining_weight -= 0.30
                triggered = True
                running_high = max(trigger_price, hi)
            continue

        trailing_level = running_high * (1 - trailing_pct)
        if lo <= trailing_level:
            tranches.append({"day_idx": i, "weight": remaining_weight, "price": trailing_level, "reason": "trail"})
            result = "target4_then_trail" if target4_taken else "trail"
            return _finalize_partial(tranches, entry, i - entry_idx, result)
        if not target4_taken and hi >= target4_price:
            tranches.append({"day_idx": i, "weight": 0.30, "price": target4_price, "reason": "target4"})
            remaining_weight -= 0.30
            target4_taken = True
        running_high = max(running_high, hi)

    exit_close = float(df.iloc[end]["close"])
    tranches.append({"day_idx": end, "weight": remaining_weight, "price": exit_close, "reason": "timeout"})
    if not triggered:
        result = "pretrigger_timeout"
    elif target4_taken:
        result = "target4_then_timeout"
    else:
        result = "trigger_then_timeout"
    return _finalize_partial(tranches, entry, end - entry_idx, result)

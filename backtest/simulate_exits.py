from __future__ import annotations

from typing import Any, Dict

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
    """Day-by-day forward walk from entry_idx: exits on first target/stop touch, else at hold_days timeout."""
    end = min(len(df) - 1, entry_idx + hold_days)
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

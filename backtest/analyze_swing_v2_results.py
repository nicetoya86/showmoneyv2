from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

SCORE_TIERS = [("60-89", 60, 89), ("90-109", 90, 109), ("110+", 110, 10_000)]


def _stats_for(rows: List[dict]) -> Dict[str, Any]:
    if not rows:
        return {"trades": 0, "win_rate": 0.0, "avg_pnl": 0.0, "median_pnl": 0.0}
    df = pd.DataFrame(rows)
    return {
        "trades": int(len(df)),
        "win_rate": float((df["pnl"] > 0).mean()),
        "avg_pnl": float(df["pnl"].mean()),
        "median_pnl": float(df["pnl"].median()),
    }


def analyze(trades: List[dict]) -> Dict[str, Any]:
    overall = _stats_for(trades)

    by_pattern: Dict[str, Any] = {}
    for pattern in sorted({t["pattern_type"] for t in trades}):
        by_pattern[pattern] = _stats_for([t for t in trades if t["pattern_type"] == pattern])

    by_score_tier: Dict[str, Any] = {}
    for label, lo, hi in SCORE_TIERS:
        by_score_tier[label] = _stats_for([t for t in trades if lo <= t["score"] <= hi])

    return {"overall": overall, "by_pattern": by_pattern, "by_score_tier": by_score_tier}


def regime_what_if(trades: List[dict], regime_df: pd.DataFrame) -> Dict[str, Any]:
    """Compares as-deployed (regime-blind) results against the lost production rule:
    `if regimeLevel>=2 and grade!='강매': block` and `if regimeLevel>=1 and grade=='매도차익': block`.
    """
    as_deployed = _stats_for(trades)

    kept: List[dict] = []
    for t in trades:
        day = pd.Timestamp(t["date"]).date()
        level = int(regime_df["regime_level"].get(day, 0))
        if level >= 2 and t["grade"] != "강매":
            continue
        if level >= 1 and t["grade"] == "매도차익":
            continue
        kept.append(t)

    return {"as_deployed": as_deployed, "if_gate_active": _stats_for(kept)}

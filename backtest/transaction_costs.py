"""
Transaction cost modeling for backtest PnL.

DEFAULT_ROUND_TRIP_COST_PCT (0.2%) is an APPROXIMATION of a Korean round-trip retail
equity trade (sell-side 증권거래세 / securities transaction tax, plus brokerage
commission both ways) — it is not sourced from a verified, current regulatory or
broker-specific rate table. Confirm and adjust the actual figure before using this for
real capital-allocation decisions.
"""
from __future__ import annotations

DEFAULT_ROUND_TRIP_COST_PCT = 0.002


def apply_round_trip_cost(pnl: float, *, cost_pct: float = DEFAULT_ROUND_TRIP_COST_PCT) -> float:
    """Returns pnl minus an approximate round-trip trading cost, both expressed as
    fractions (e.g. 0.05 = 5%, 0.002 = 0.2%)."""
    return pnl - cost_pct

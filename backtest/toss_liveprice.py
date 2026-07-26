"""
Faithful daily-bar reconstruction of production's TOSS-LIVEPRICE logic
(src/swing-scanner.src.js:1652-1710, added 2026-07-19).

Production computes an entry/target/stop from the prior day's close, but the actual
send happens at 09:10 using a real-time live price. If the live price already reached
target/stop by send time, the send is blocked outright; if the gap between the prior
close and the live price exceeds TOSS_GAP_REBASE_THRESHOLD, entry/target/stop are
rebased onto the live price (preserving the original target/stop distances as
percentages). Below that threshold, production does NOT rebase — the original
close-based entry stands.

NOT MODELED (approximation, documented): this backtest has no intraday tick/orderbook
data, so `next_day_open` is used as the only available proxy for the real 09:10 live
price. This is a simplification, not an exact reproduction — the true 09:10 price can
differ from the day's opening print.

NOT MODELED (out of scope): production's separate ask/bid-ratio block
(TOSS_ASK_BID_BLOCK_RATIO) and pattern-C weak-buy-ratio block (TOSS_WEAK_BUY_RATIO_C)
require real-time orderbook/trade-tape data with no historical equivalent; only the
live-price block/rebase behavior (which needs just a price, not orderbook depth) is
reconstructed here.
"""
from __future__ import annotations

from dataclasses import dataclass

TOSS_GAP_REBASE_THRESHOLD = 0.02


@dataclass(frozen=True)
class TossOutcome:
    status: str  # "as_is" | "rebased" | "blocked_chasing" | "blocked_stopped_out"
    entry: float
    target: float
    stop: float


def apply_toss_liveprice(
    entry: float,
    target: float,
    stop: float,
    next_day_open: float,
    *,
    gap_rebase_threshold: float = TOSS_GAP_REBASE_THRESHOLD,
) -> TossOutcome:
    """Port of the TOSS-LIVEPRICE block/rebase decision, using next_day_open as the
    live-price proxy. See module docstring for the approximation this implies."""
    if next_day_open >= target:
        return TossOutcome(status="blocked_chasing", entry=entry, target=target, stop=stop)
    if next_day_open <= stop:
        return TossOutcome(status="blocked_stopped_out", entry=entry, target=target, stop=stop)

    gap_pct = (next_day_open - entry) / entry
    if abs(gap_pct) >= gap_rebase_threshold:
        target_pct = target / entry - 1
        stop_pct = 1 - stop / entry
        new_entry = next_day_open
        return TossOutcome(
            status="rebased",
            entry=new_entry,
            target=new_entry * (1 + target_pct),
            stop=new_entry * (1 - stop_pct),
        )

    return TossOutcome(status="as_is", entry=entry, target=target, stop=stop)

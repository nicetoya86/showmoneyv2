"""
Portfolio-level expected-return estimate for the CURRENT (unmodified, this-plan-realistic)
swing-recommendation algorithm, derived from the already-committed
`backtest_out_swing_v2_realistic.json` (959 tickers, 2022-01-01..2026-01-01, TOSS-LIVEPRICE-aware,
fee-aware, 2,686 trades).

WHY THIS EXISTS: `backtest/run_swing_v2_backtest.py`'s own `mdd`/`equity_end` stats model a single
account that puts 100% of capital into every trade sequentially (no diversification across
concurrent positions) -- already documented in
docs/03-analysis/swing-algorithm-profitability-review.analysis.md as "an illustrative
single-account model, not a realistic portfolio simulation" (hence the degenerate -99.9999995%
MDD / ~5e-9 equity_end figures there). Production (src/swing-scanner.src.js) caps recommendations
at MAX_WEEKLY_SENDS = 15/week (line 24) -- it is a signal service, not a position-sizing engine,
so it does not itself define how much capital a follower puts behind each recommendation. This
script fills that gap with a documented, transparent assumption: an equal-weight, N-concurrent-slot
account that could realistically follow every recommendation this backtest generated.

METHOD: sort the 2,686 real (dated, realistic-model) trades chronologically, round-robin-assign
them across N slots of equal starting capital (1/N each), compound each slot's equity trade-by-trade
in the order its assigned trades occurred, and track the *portfolio* equity curve (mean of the N
slots) after every individual trade event to get a real CAGR and a real (non-degenerate) MDD.
N=15 is the primary scenario (grounded in MAX_WEEKLY_SENDS, the only concurrency-relevant constant
production actually defines); N=5/10/20 are reported for sensitivity. This is a modeling choice,
not a measured fact -- flagged as such in the output.

LIMITATION (documented, not fixed here): round-robin by sort order approximates real concurrent
occupancy but does not model actual calendar overlap (a trade's `days_held` vs. the next trade's
entry date). Given trades are heavily cap-bound (documented in the profitability review: 148/205
weeks hit the weekly cap), this approximation is reasonable but not exact.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def load_trades(path: str = "backtest_out_swing_v2_realistic.json"):
    d = json.load(open(path, encoding="utf-8"))
    trades = d["trades"]
    trades_sorted = sorted(trades, key=lambda t: (t["date"], t["ticker"]))
    return trades_sorted, d["stats"], d["params"]


def simulate_portfolio(trades_sorted, n_slots: int):
    slot_equity = [1.0] * n_slots
    curve = []  # (date, portfolio_equity) after each trade event
    for i, tr in enumerate(trades_sorted):
        slot = i % n_slots
        slot_equity[slot] *= (1.0 + tr["pnl"])
        curve.append((tr["date"], sum(slot_equity) / n_slots))
    return curve


def cagr_and_mdd(curve, start_date: str, end_date: str):
    equity_series = [e for _, e in curve]
    peak = 1.0
    max_dd = 0.0
    for e in equity_series:
        peak = max(peak, e)
        dd = (e - peak) / peak
        max_dd = min(max_dd, dd)
    final_equity = equity_series[-1] if equity_series else 1.0
    d0 = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
    d1 = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
    years = (d1 - d0).days / 365.25
    cagr = final_equity ** (1.0 / years) - 1.0 if final_equity > 0 and years > 0 else float("nan")
    return final_equity, max_dd, years, cagr


def main():
    trades_sorted, stats, params = load_trades()
    start_date = trades_sorted[0]["date"]
    end_date = trades_sorted[-1]["date"]

    print(f"Trades: {len(trades_sorted)}  |  Span: {start_date[:10]} -> {end_date[:10]}")
    print(f"Per-trade avg net pnl: {stats['avg_pnl']*100:.3f}%  |  win_rate: {stats['win_rate']*100:.2f}%")
    print()
    print(f"{'N slots':>8} | {'final equity':>14} | {'total return':>13} | {'years':>6} | {'CAGR':>9} | {'MDD':>9}")
    print("-" * 78)
    for n in (5, 10, 15, 20, 30, 50, 100, 200):
        curve = simulate_portfolio(trades_sorted, n)
        final_equity, max_dd, years, cagr = cagr_and_mdd(curve, start_date, end_date)
        marker = "  <- MAX_WEEKLY_SENDS-grounded" if n == 15 else ""
        print(
            f"{n:>8} | {final_equity:>14.4f} | {(final_equity-1)*100:>12.2f}% | "
            f"{years:>6.2f} | {cagr*100:>8.2f}% | {max_dd*100:>8.2f}%{marker}"
        )


if __name__ == "__main__":
    main()

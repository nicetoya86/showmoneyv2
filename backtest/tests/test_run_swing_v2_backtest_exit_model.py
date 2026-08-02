import inspect

import pandas as pd

from backtest.run_swing_v2_backtest import backtest_swing_v2


def test_exit_model_defaults_to_binary():
    sig = inspect.signature(backtest_swing_v2)
    assert sig.parameters["exit_model"].default == "binary"


def test_partial_exit_model_produces_tranches_field(monkeypatch):
    from backtest import run_swing_v2_backtest as mod

    ticker = "000003.KS"
    # idx1 (2024-01-03) is the signal day (entry=100.0, close). entry_idx=2 (2024-01-04):
    # high=103 clears the +2% trigger (102) -> 30% tranche. idx3 (2024-01-05): high=104
    # clears +4% (104) -> another 30% tranche, low=101 does not breach the trailing level
    # (103*0.98=100.94). idx4 (2024-01-06, the last day in the hold_days=3 window: entry_idx=2
    # + hold_days=3 - 1 = 4): low=102 does not breach the trailing level (104*0.98=101.92) ->
    # remaining 40% times out at this day's close. Neither target(110) nor stop(90) is ever
    # touched across idx 2-4, so the binary model on this same fixture also times out (at the
    # last day's close) -- both models produce exactly one trade, with result "timeout"/
    # "target4_then_timeout" respectively, which is what this test distinguishes.
    df = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-06"], utc=True
        ),
        "open":  [100.0, 100.0, 101.0, 102.0, 103.5],
        "high":  [101.0, 101.0, 103.0, 104.0, 103.0],
        "low":   [99.0,  99.0,  100.0, 101.0, 102.0],
        "close": [100.0, 100.0, 102.0, 103.5, 103.3],
        "volume": [1_000_000.0] * 5,
    })

    monkeypatch.setattr(mod, "fetch_yahoo_chart", lambda spec: {"_fake_for": spec.ticker})
    monkeypatch.setattr(mod, "chart_to_ohlcv_daily", lambda data: (df.copy(), None))
    monkeypatch.setattr(mod, "fetch_supply_for_date", lambda trd_dd: {})
    monkeypatch.setattr(mod, "fetch_disclosures_for_date", lambda trd_dd, api_key: {})

    from backtest.swing_signal_engine import SwingCandidate

    def fake_evaluate_candidate(df_arg, idx, *, supply, dart_items, day_of_week):
        if idx != 1:
            return None
        return SwingCandidate(
            pattern_type="D박스", score=100, rank_score=100, grade="매수",
            entry=100.0, target=110.0, stop=90.0, hold_days=3, signals=[],
        )

    monkeypatch.setattr(mod, "evaluate_candidate", fake_evaluate_candidate)

    df_trades_binary, stats_binary = mod.backtest_swing_v2(
        [ticker], start="2024-01-01", end="2024-01-07",
    )
    assert stats_binary["trades"] == 1
    assert "tranches" not in df_trades_binary.columns
    assert df_trades_binary.iloc[0]["result"] in {"target", "stop", "timeout"}

    df_trades_partial, stats_partial = mod.backtest_swing_v2(
        [ticker], start="2024-01-01", end="2024-01-07", exit_model="partial",
    )
    assert stats_partial["trades"] == 1
    row_partial = df_trades_partial.iloc[0]
    assert row_partial["result"] in {
        "pretrigger_stop", "pretrigger_timeout", "trail",
        "target4_then_trail", "target4_then_timeout", "trigger_then_timeout",
    }
    assert isinstance(row_partial["tranches"], list) and len(row_partial["tranches"]) > 0


def test_partial_exit_model_atr_uses_own_ticker_signal_idx_not_stale_outer_idx(monkeypatch):
    """Regression guard: the candidate-building loop (per_ticker.items()) reassigns an outer
    `idx` variable per ticker/day before the per-selected-trade exit-simulation block runs. If
    the partial-exit ATR lookup reused that stale outer `idx` instead of a per-ticker
    `signal_idx = entry_idx - 1`, it would index into the CURRENTLY selected ticker's (shorter)
    OHLC arrays using a position that belongs to a DIFFERENT ticker that happened to be
    processed later in that day's building loop -- raising IndexError here (ticker_a has only
    4 rows; the stale idx from ticker_b is 5, out of bounds) rather than merely returning a
    wrong number, which is what makes this scenario minimal but conclusive.

    ticker_a: 4 rows, signal day at local idx=2 (2024-01-05) -> entry_idx=3.
    ticker_b: 6 rows ending on the same calendar day (2024-01-05) at local idx=5 -- its last
    row, so it's skipped for candidate generation (no next-day entry) but still overwrites the
    building loop's outer `idx` to 5 before that skip. ticker_a is listed first, so per_ticker
    iterates ticker_a (idx=2) then ticker_b (idx=5) for this day, leaving idx=5 stale when the
    selected-trades loop processes ticker_a's trade next.
    """
    from backtest import run_swing_v2_backtest as mod
    from backtest.swing_signal_engine import SwingCandidate

    ticker_a = "000006.KS"
    ticker_b = "000007.KS"

    df_a = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(
            ["2024-01-03", "2024-01-04", "2024-01-05", "2024-01-06"], utc=True
        ),
        "open":  [99.0, 99.0, 100.0, 100.2],
        "high":  [100.0, 100.5, 101.0, 101.0],
        "low":   [98.0, 99.0, 99.0, 99.5],
        "close": [99.0, 100.0, 100.0, 100.5],
        "volume": [1_000_000.0] * 4,
    })
    df_b = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(
            ["2023-12-31", "2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            utc=True,
        ),
        "open":  [50.0] * 6,
        "high":  [51.0] * 6,
        "low":   [49.0] * 6,
        "close": [50.0] * 6,
        "volume": [1_000_000.0] * 6,
    })
    df_map = {ticker_a: df_a, ticker_b: df_b}

    monkeypatch.setattr(mod, "fetch_yahoo_chart", lambda spec: {"_fake_for": spec.ticker})
    monkeypatch.setattr(mod, "chart_to_ohlcv_daily", lambda data: (df_map[data["_fake_for"]].copy(), None))
    monkeypatch.setattr(mod, "fetch_supply_for_date", lambda trd_dd: {})
    monkeypatch.setattr(mod, "fetch_disclosures_for_date", lambda trd_dd, api_key: {})

    def fake_evaluate_candidate(df_arg, idx, *, supply, dart_items, day_of_week):
        # Only ticker_a (4 rows) at its signal day (local idx=2) produces a candidate;
        # ticker_b (6 rows) never does, regardless of idx.
        if len(df_arg) != 4 or idx != 2:
            return None
        return SwingCandidate(
            pattern_type="D박스", score=100, rank_score=100, grade="매수",
            entry=100.0, target=110.0, stop=90.0, hold_days=1, signals=[],
        )

    monkeypatch.setattr(mod, "evaluate_candidate", fake_evaluate_candidate)

    df_trades, stats = mod.backtest_swing_v2(
        [ticker_a, ticker_b], start="2023-12-25", end="2024-01-10", exit_model="partial",
    )

    assert stats["trades"] == 1
    row = df_trades.iloc[0]
    assert row["ticker"] == ticker_a
    # With the correct signal_idx=2 (entry_idx=3 - 1), the ATR fallback window is
    # high_arr[0:2]-low_arr[0:2] -> all-NaN 14-day ATR falls back cleanly and hold_days=1 means
    # only the entry day (idx=3) is walked: neither the +2% trigger (102) nor the stop (90) is
    # touched, so the 100% remaining tranche times out at that day's close (100.5). The stale
    # idx=5 bug would instead raise IndexError against ticker_a's 4-row arrays.
    assert row["result"] == "pretrigger_timeout"
    assert row["tranches"] == [{"day_idx": 3, "weight": 1.0, "price": 100.5, "reason": "timeout"}]

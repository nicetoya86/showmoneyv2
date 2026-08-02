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

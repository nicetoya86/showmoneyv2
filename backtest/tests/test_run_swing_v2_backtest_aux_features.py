import pandas as pd

from backtest.run_swing_v2_backtest import backtest_swing_v2


def test_trade_records_include_aux_features(monkeypatch):
    from backtest import run_swing_v2_backtest as mod

    ticker = "000004.KS"
    df = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04"], utc=True
        ),
        "open": [100.0, 101.0, 101.0],
        "high": [101.0, 102.0, 115.0],
        "low": [99.0, 100.0, 100.0],
        "close": [100.0, 101.0, 112.0],
        "volume": [1_000_000.0, 1_000_000.0, 1_000_000.0],
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
            aux_features={
                "rvol_tier": 2, "obv_trend": 1, "macd_state": "golden_cross",
                "sma_aligned": True, "intraday_tier": 2, "supply_tier": 0,
                "dart_tier": 0, "rsi_golden": True, "adx_trend": False, "high52_tier": 0,
            },
        )

    monkeypatch.setattr(mod, "evaluate_candidate", fake_evaluate_candidate)

    df_trades, stats = backtest_swing_v2([ticker], start="2024-01-01", end="2024-01-05")
    assert stats["trades"] == 1
    row = df_trades.iloc[0]
    assert row["aux_features"] == {
        "rvol_tier": 2, "obv_trend": 1, "macd_state": "golden_cross",
        "sma_aligned": True, "intraday_tier": 2, "supply_tier": 0,
        "dart_tier": 0, "rsi_golden": True, "adx_trend": False, "high52_tier": 0,
    }

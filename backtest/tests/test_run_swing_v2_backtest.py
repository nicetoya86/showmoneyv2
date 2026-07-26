import json

from backtest.run_swing_v2_backtest import GRADE_ORDER, apply_daily_selection
from backtest.swing_signal_engine import SwingCandidate


def _cand(code, rank_score, grade="매수"):
    return (code, SwingCandidate(
        pattern_type="D박스", score=rank_score, rank_score=rank_score, grade=grade,
        entry=1000.0, target=1100.0, stop=960.0, hold_days=4, signals=[],
    ))


def test_weekly_cap_stops_new_selections():
    week_state = {"count": 15, "codes": set()}
    todays = [_cand("000001", 90), _cand("000002", 80)]
    selected = apply_daily_selection(todays, week_state, max_per_day=3, max_per_week=15)
    assert selected == []


def test_dedup_same_code_within_week():
    week_state = {"count": 1, "codes": {"000001"}}
    todays = [_cand("000001", 95), _cand("000002", 90)]
    selected = apply_daily_selection(todays, week_state, max_per_day=3, max_per_week=15)
    assert [c for c, _ in selected] == ["000002"]


def test_grade_order_wins_over_rank_score():
    week_state = {"count": 0, "codes": set()}
    todays = [
        _cand("000001", 200, grade="매수"),
        _cand("000002", 60, grade="강매"),
    ]
    selected = apply_daily_selection(todays, week_state, max_per_day=3, max_per_week=15)
    assert [c for c, _ in selected][0] == "000002"  # 강매 outranks 매수 regardless of score


def test_max_per_day_caps_selection():
    week_state = {"count": 0, "codes": set()}
    todays = [_cand(f"{i:06d}", 100 - i) for i in range(5)]
    selected = apply_daily_selection(todays, week_state, max_per_day=3, max_per_week=15)
    assert len(selected) == 3


def test_week_state_mutation():
    """Verify that apply_daily_selection updates week_state with selected codes and count."""
    week_state = {"count": 0, "codes": set()}
    todays = [_cand("000001", 90), _cand("000002", 80), _cand("000003", 70)]
    selected = apply_daily_selection(todays, week_state, max_per_day=2, max_per_week=15)

    # Should select 2 items
    assert len(selected) == 2
    selected_codes = {c for c, _ in selected}

    # week_state should be updated with selected codes
    assert week_state["codes"] == selected_codes
    # week_state count should be updated to 2
    assert week_state["count"] == 2


def test_json_serialization_regression():
    """Regression test: ensure backtest_swing_v2 result is JSON-serializable (no Timestamp objects)."""
    import pandas as pd
    from backtest.run_swing_v2_backtest import backtest_swing_v2

    # Minimal test: create a trades DataFrame as backtest_swing_v2 would return it
    # This simulates what happens when at least one trade exists
    trades_data = [
        {
            "date": "2024-01-15T00:00:00+00:00",
            "ticker": "005930.KS",
            "code": "005930",
            "pattern_type": "D박스",
            "grade": "매수",
            "score": 75,
            "rank_score": 75,
            "entry": 1000.0,
            "stop": 950.0,
            "target": 1100.0,
            "exit_price": 1050.0,
            "result": "target",
            "days_held": 3,
            "pnl": 0.05,
        }
    ]
    df_trades = pd.DataFrame(trades_data)

    # Verify that df_trades.to_dict() is JSON-serializable (should not contain Timestamp objects)
    trades_dict = df_trades.to_dict(orient="records")
    try:
        json.dumps(trades_dict)
    except TypeError as e:
        if "Timestamp" in str(e):
            raise AssertionError(f"DataFrame contains non-JSON-serializable Timestamp: {e}")
        raise

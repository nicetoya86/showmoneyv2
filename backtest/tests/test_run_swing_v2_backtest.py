from unittest.mock import patch

import numpy as np
import pandas as pd

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

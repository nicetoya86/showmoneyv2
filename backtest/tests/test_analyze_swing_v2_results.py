import pandas as pd

from backtest.analyze_swing_v2_results import analyze, regime_what_if


def _trades():
    return [
        {"date": "2024-01-02", "pattern_type": "D박스", "score": 65, "pnl": 0.10, "grade": "매수"},
        {"date": "2024-01-03", "pattern_type": "D박스", "score": 65, "pnl": -0.04, "grade": "매수"},
        {"date": "2024-01-04", "pattern_type": "C촉매", "score": 120, "pnl": 0.15, "grade": "강매"},
        {"date": "2024-01-05", "pattern_type": "A눌림목", "score": 95, "pnl": -0.03, "grade": "매도차익"},
    ]


def test_analyze_overall_and_breakdowns():
    result = analyze(_trades())
    assert result["overall"]["trades"] == 4
    assert result["overall"]["win_rate"] == 0.5
    assert result["by_pattern"]["D박스"]["trades"] == 2
    assert result["by_pattern"]["C촉매"]["win_rate"] == 1.0
    assert result["by_score_tier"]["60-89"]["trades"] == 2
    assert result["by_score_tier"]["90-109"]["trades"] == 1
    assert result["by_score_tier"]["110+"]["trades"] == 1


def test_regime_what_if_drops_neutral_sell_profit_grade():
    trades = _trades()
    regime_df = pd.DataFrame(
        {"regime_level": [1, 1, 1, 1]},
        index=[pd.Timestamp(d).date() for d in ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]],
    )
    result = regime_what_if(trades, regime_df)
    assert result["as_deployed"]["trades"] == 4
    # regime_level=1 blocks grade=='매도차익' (the 2024-01-05 trade) per the lost production rule
    assert result["if_gate_active"]["trades"] == 3


def test_regime_what_if_blocks_regime_level_2_non_strong_grade():
    """Tests the first blocking condition: regimeLevel>=2 and grade!='강매'."""
    trades = [
        {"date": "2024-01-02", "pattern_type": "D박스", "score": 65, "pnl": 0.10, "grade": "매수"},
        {"date": "2024-01-03", "pattern_type": "C촉매", "score": 120, "pnl": 0.15, "grade": "강매"},
        {"date": "2024-01-04", "pattern_type": "A눌림목", "score": 95, "pnl": -0.03, "grade": "매도차익"},
    ]
    regime_df = pd.DataFrame(
        {"regime_level": [2, 2, 0]},
        index=[pd.Timestamp(d).date() for d in ["2024-01-02", "2024-01-03", "2024-01-04"]],
    )
    result = regime_what_if(trades, regime_df)
    assert result["as_deployed"]["trades"] == 3
    # regime_level=2 blocks grade!='강매' (the 2024-01-02 trade), but '강매' survives the first condition
    # regime_level=0 on 2024-01-04 survives both conditions
    assert result["if_gate_active"]["trades"] == 2

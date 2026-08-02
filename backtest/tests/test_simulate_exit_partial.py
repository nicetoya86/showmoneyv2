import pytest
import pandas as pd

from backtest.simulate_exits import simulate_exit_partial


def _df(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def test_pretrigger_stop_before_2pct_ever_touched():
    df = _df([
        [100, 101, 99, 100],   # day0: no stop (low=99 > stop=95), no trigger (high=101 < 102)
        [100, 100, 94, 95],    # day1: low=94 <= stop(95) -> full stop-out
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=95.0, atr_pct=0.02, hold_days=5)
    assert r["result"] == "pretrigger_stop"
    assert r["exit_price"] == pytest.approx(95.0)
    assert r["days_held"] == 1
    assert r["tranches"] == [{"day_idx": 1, "weight": 1.0, "price": 95.0, "reason": "stop"}]


def test_pretrigger_timeout_never_triggers():
    df = _df([
        [100, 101, 99, 100],   # day0: no stop, no trigger
        [100, 101, 99, 99],    # day1: no stop, no trigger
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=90.0, atr_pct=0.02, hold_days=2)
    assert r["result"] == "pretrigger_timeout"
    assert r["exit_price"] == pytest.approx(99.0)
    assert r["days_held"] == 1
    assert r["tranches"] == [{"day_idx": 1, "weight": 1.0, "price": 99.0, "reason": "timeout"}]


def test_trigger_then_trailing_stop_before_4pct():
    df = _df([
        [100, 103, 99, 102],     # day0: high=103 >= trigger(102) -> 30% @ 102, running_high=103
        [102, 103.5, 100, 101],  # day1: trailing_level=103*0.98=100.94; low=100 <= 100.94 -> trail
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=90.0, atr_pct=0.02, hold_days=5)
    assert r["result"] == "trail"
    assert r["exit_price"] == pytest.approx(0.30 * 102.0 + 0.70 * 100.94)
    assert r["days_held"] == 1
    assert r["tranches"] == [
        {"day_idx": 0, "weight": 0.30, "price": 102.0, "reason": "trigger_2pct"},
        {"day_idx": 1, "weight": 0.70, "price": pytest.approx(100.94), "reason": "trail"},
    ]


def test_trigger_then_4pct_then_trailing_stop():
    df = _df([
        [100, 103, 99, 102],      # day0: trigger @102, running_high=103
        [102, 105, 101, 104],     # day1: trailing_level=103*0.98=100.94, low=101 no breach;
                                   #       high=105 >= 104 -> 30% @104, running_high=max(103,105)=105
        [104, 103, 102, 102.5],   # day2: trailing_level=105*0.98=102.9, low=102 <= 102.9 -> trail
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=90.0, atr_pct=0.02, hold_days=5)
    assert r["result"] == "target4_then_trail"
    expected_price = 0.30 * 102.0 + 0.30 * 104.0 + 0.40 * 102.9
    assert r["exit_price"] == pytest.approx(expected_price)
    assert r["days_held"] == 2
    pnl_pct = (r["exit_price"] - 100.0) / 100.0
    hand_computed_pnl_pct = 0.30 * 0.02 + 0.30 * 0.04 + 0.40 * 0.029
    assert pnl_pct == pytest.approx(hand_computed_pnl_pct)


def test_trigger_then_4pct_then_timeout():
    df = _df([
        [100, 103, 99, 102],     # day0: trigger @102, running_high=103
        [102, 105, 101, 104],    # day1: no trail breach (low=101>100.94); +4% @104, running_high=105
        [104, 103, 103, 103.2],  # day2 (=end, hold_days=3): trailing_level=105*0.98=102.9,
                                  #       low=103 > 102.9 -> no breach -> timeout at this close
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=90.0, atr_pct=0.02, hold_days=3)
    assert r["result"] == "target4_then_timeout"
    expected_price = 0.30 * 102.0 + 0.30 * 104.0 + 0.40 * 103.2
    assert r["exit_price"] == pytest.approx(expected_price)
    assert r["days_held"] == 2
    assert r["tranches"][-1] == {"day_idx": 2, "weight": pytest.approx(0.40), "price": 103.2, "reason": "timeout"}


def test_trigger_then_timeout_never_hits_4pct_or_trail():
    df = _df([
        [100, 103, 99, 102],       # day0: trigger @102, running_high=103
        [102, 103, 101, 102.5],    # day1: trailing_level=100.94, low=101 no breach; high=103<104 no +4%
        [102.5, 103.5, 101, 102.8],# day2 (=end, hold_days=3): trailing_level=100.94 (unchanged since
                                    #       running_high stayed 103 through day1's check), low=101 no breach;
                                    #       high=103.5<104 no +4% -> timeout at this close
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=90.0, atr_pct=0.02, hold_days=3)
    assert r["result"] == "trigger_then_timeout"
    expected_price = 0.30 * 102.0 + 0.70 * 102.8
    assert r["exit_price"] == pytest.approx(expected_price)
    assert r["days_held"] == 2
    assert r["tranches"] == [
        {"day_idx": 0, "weight": 0.30, "price": 102.0, "reason": "trigger_2pct"},
        {"day_idx": 2, "weight": pytest.approx(0.70), "price": 102.8, "reason": "timeout"},
    ]


def test_same_bar_tie_break_pretrigger_resolves_to_stop():
    df = _df([
        [100, 103, 94, 98],  # day0: high=103 >= trigger(102) AND low=94 <= stop(95) -- both true
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=95.0, atr_pct=0.02, hold_days=5)
    assert r["result"] == "pretrigger_stop"
    assert r["exit_price"] == pytest.approx(95.0)
    assert r["days_held"] == 0


def test_same_bar_tie_break_runner_resolves_to_trail_not_4pct():
    df = _df([
        [100, 103, 99, 102],   # day0: trigger @102, running_high=103
        [102, 105, 100, 101],  # day1: trailing_level=103*0.98=100.94; low=100<=100.94 (breach) AND
                                #       high=105>=104 (would-be +4%) -- both true, trail must win
    ])
    r = simulate_exit_partial(df, 0, entry=100.0, stop=90.0, atr_pct=0.02, hold_days=5)
    assert r["result"] == "trail"  # NOT target4_then_trail -- +4% must never have fired
    assert r["exit_price"] == pytest.approx(0.30 * 102.0 + 0.70 * 100.94)
    assert len(r["tranches"]) == 2
    assert r["tranches"][1]["reason"] == "trail"

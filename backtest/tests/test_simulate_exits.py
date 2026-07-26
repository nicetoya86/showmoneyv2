import pandas as pd

from backtest.simulate_exits import simulate_exit


def _df(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def test_hits_target_first():
    df = _df([
        [100, 101, 99, 100],
        [100, 112, 99, 105],  # high >= target(110)
        [105, 106, 104, 105],
    ])
    r = simulate_exit(df, 1, entry=100.0, stop=90.0, target=110.0, hold_days=5)
    assert r["result"] == "target"
    assert r["exit_price"] == 110.0
    assert r["days_held"] == 0


def test_hits_stop_first():
    df = _df([
        [100, 101, 99, 100],
        [100, 101, 85, 95],  # low <= stop(90)
    ])
    r = simulate_exit(df, 1, entry=100.0, stop=90.0, target=110.0, hold_days=5)
    assert r["result"] == "stop"
    assert r["exit_price"] == 90.0


def test_both_hit_same_day_is_conservative_stop():
    df = _df([
        [100, 101, 99, 100],
        [100, 115, 85, 100],  # both target and stop touched same bar
    ])
    r = simulate_exit(df, 1, entry=100.0, stop=90.0, target=110.0, hold_days=5)
    assert r["result"] == "stop"
    assert r["exit_price"] == 90.0


def test_timeout_exits_at_close_of_entry_day_when_hold_days_is_one():
    df = _df([
        [100, 101, 99, 100],
        [100, 105, 99, 103],
        [103, 106, 102, 104],
    ])
    r = simulate_exit(df, 1, entry=100.0, stop=50.0, target=200.0, hold_days=1)
    assert r["result"] == "timeout"
    assert r["exit_price"] == 103.0  # close of entry_idx itself — hold_days=1 counts the entry day
    assert r["days_held"] == 0


def test_timeout_clamps_to_last_row_when_data_runs_out():
    df = _df([
        [100, 101, 99, 100],
        [100, 105, 99, 103],
        [103, 106, 102, 104],
    ])
    r = simulate_exit(df, 0, entry=100.0, stop=50.0, target=200.0, hold_days=100)
    assert r["result"] == "timeout"
    assert r["exit_price"] == 104.0  # close of last available row (index 2)
    assert r["days_held"] == 2  # 0 to 2 = 2 days

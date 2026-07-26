from backtest.toss_liveprice import apply_toss_liveprice


def test_small_gap_is_left_as_is():
    # gap = (101 - 100) / 100 = 1%, below the 2% threshold -> no change at all
    r = apply_toss_liveprice(entry=100.0, target=110.0, stop=90.0, next_day_open=101.0)
    assert r.status == "as_is"
    assert r.entry == 100.0
    assert r.target == 110.0
    assert r.stop == 90.0


def test_gap_exactly_at_threshold_rebases():
    # gap = (102 - 100) / 100 = exactly 2% -> production uses >=, so this rebases
    r = apply_toss_liveprice(entry=100.0, target=110.0, stop=90.0, next_day_open=102.0)
    assert r.status == "rebased"
    assert r.entry == 102.0
    # original target_pct = 10%, stop_pct = 10% -> preserved on the new entry
    assert abs(r.target - 112.2) < 1e-9
    assert abs(r.stop - 91.8) < 1e-9


def test_gap_just_below_threshold_is_as_is():
    # gap = (101.9 - 100) / 100 = 1.9%, below 2% -> no rebase
    r = apply_toss_liveprice(entry=100.0, target=110.0, stop=90.0, next_day_open=101.9)
    assert r.status == "as_is"
    assert r.entry == 100.0


def test_downward_gap_beyond_threshold_rebases():
    # gap = (97 - 100) / 100 = -3%, |gap| >= 2% -> rebase (direction-agnostic)
    r = apply_toss_liveprice(entry=100.0, target=110.0, stop=90.0, next_day_open=97.0)
    assert r.status == "rebased"
    assert r.entry == 97.0
    assert abs(r.target - 106.7) < 1e-9
    assert abs(r.stop - 87.3) < 1e-9


def test_open_at_or_above_target_blocks_as_chasing():
    r = apply_toss_liveprice(entry=100.0, target=110.0, stop=90.0, next_day_open=110.0)
    assert r.status == "blocked_chasing"


def test_open_at_or_below_stop_blocks_as_stopped_out():
    r = apply_toss_liveprice(entry=100.0, target=110.0, stop=90.0, next_day_open=90.0)
    assert r.status == "blocked_stopped_out"


def test_chasing_block_takes_priority_over_stopped_out():
    # degenerate/impossible-in-practice inputs where target <= stop: chasing check runs first
    r = apply_toss_liveprice(entry=100.0, target=90.0, stop=95.0, next_day_open=90.0)
    assert r.status == "blocked_chasing"


def test_custom_gap_rebase_threshold():
    # with a wider 5% threshold, a 2% gap should NOT rebase
    r = apply_toss_liveprice(
        entry=100.0, target=110.0, stop=90.0, next_day_open=102.0, gap_rebase_threshold=0.05
    )
    assert r.status == "as_is"

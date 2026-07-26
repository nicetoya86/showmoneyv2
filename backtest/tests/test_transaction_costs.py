from backtest.transaction_costs import DEFAULT_ROUND_TRIP_COST_PCT, apply_round_trip_cost


def test_default_cost_is_subtracted():
    result = apply_round_trip_cost(0.05)
    assert abs(result - (0.05 - DEFAULT_ROUND_TRIP_COST_PCT)) < 1e-12


def test_default_cost_pct_is_twenty_bps():
    assert DEFAULT_ROUND_TRIP_COST_PCT == 0.002


def test_custom_cost_pct_overrides_default():
    result = apply_round_trip_cost(0.05, cost_pct=0.001)
    assert abs(result - 0.049) < 1e-12


def test_cost_can_flip_a_small_positive_pnl_negative():
    result = apply_round_trip_cost(0.001, cost_pct=0.002)
    assert result < 0

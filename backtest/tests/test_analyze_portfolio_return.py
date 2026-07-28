from backtest.analyze_portfolio_return import simulate_portfolio, cagr_and_mdd


def test_simulate_portfolio_round_robins_and_compounds_per_slot():
    trades = [
        {"date": "2020-01-01", "pnl": 0.10},
        {"date": "2020-01-02", "pnl": -0.20},
        {"date": "2020-01-03", "pnl": 0.10},
        {"date": "2020-01-04", "pnl": -0.20},
    ]
    curve = simulate_portfolio(trades, n_slots=2)
    equities = [e for _, e in curve]
    assert abs(equities[0] - 1.05) < 1e-12
    assert abs(equities[1] - 0.95) < 1e-12
    assert abs(equities[2] - 1.005) < 1e-12
    assert abs(equities[3] - 0.925) < 1e-12


def test_cagr_and_mdd_matches_hand_computed_values():
    curve = [
        ("2020-01-01", 1.05),
        ("2020-01-02", 0.95),
        ("2020-01-03", 1.005),
        ("2020-01-04", 0.925),
    ]
    final_equity, max_dd, years, cagr = cagr_and_mdd(
        curve, "2020-01-01T00:00:00Z", "2021-01-01T00:00:00Z"
    )
    assert abs(final_equity - 0.925) < 1e-12
    assert abs(max_dd - (0.925 - 1.05) / 1.05) < 1e-9
    assert abs(years - 366 / 365.25) < 1e-9
    assert abs(cagr - (0.925 ** (1.0 / years) - 1.0)) < 1e-12


def test_cagr_is_nan_when_equity_is_zero_or_negative():
    _, _, _, cagr = cagr_and_mdd(
        [("2020-01-01", 0.0)], "2020-01-01T00:00:00Z", "2021-01-01T00:00:00Z"
    )
    assert cagr != cagr  # NaN

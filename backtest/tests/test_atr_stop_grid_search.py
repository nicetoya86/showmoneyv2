from backtest.atr_stop_grid_search import (
    build_atr_grid,
    run_atr_grid_search,
    run_one_atr_config,
    select_best_atr_config,
)
from backtest.generate_signal_candidates import CachedCandidate


def _make_candidate(code, date, entry=100.0, hold_days=3, window=None):
    if window is None:
        window = {
            "open": [entry] * hold_days, "high": [entry] * hold_days,
            "low": [entry] * hold_days, "close": [entry] * hold_days,
        }
    return CachedCandidate(
        ticker=f"{code}.KS", code=code, date=date, entry=entry,
        pattern_type="E반등", score=110, rank_score=110, grade="매수",
        hold_days=hold_days,
        window_open=window["open"], window_high=window["high"],
        window_low=window["low"], window_close=window["close"],
    )


def test_atr_target_stop_value_pinned_hit_rate_and_pnl():
    day = "2024-01-02T00:00:00+00:00"
    # entry=100, atr_pct=0.02, target_mult=1.5 -> target=100*(1+1.5*0.02)=103
    # stop_mult=1.0 -> stop=100*(1-1*0.02)=98
    # window day0: high=104(>=103 target), low=99(>98 stop) -> hits target
    hit = _make_candidate(
        "000001", day, hold_days=3,
        window={
            "open": [100.0, 100.0, 100.0], "high": [104.0, 104.0, 104.0],
            "low": [99.0, 99.0, 99.0], "close": [103.5, 103.5, 103.5],
        },
    )
    atr_lookup = {("000001.KS", day): 0.02}
    result = run_one_atr_config(
        [hit], target_mult=1.5, stop_mult=1.0, atr_lookup=atr_lookup,
        start="2024-01-01", end="2024-01-08",  # exactly 7 days = 1.0 week
    )
    assert result["n_trades"] == 1
    assert result["hit_rate"] == 1.0
    assert result["trades_per_week"] == 1.0
    assert abs(result["avg_pnl"] - (0.03 - 0.002)) < 1e-9


def test_missing_atr_lookup_skips_candidate():
    day = "2024-01-02T00:00:00+00:00"
    c = _make_candidate("000001", day)
    result = run_one_atr_config(
        [c], target_mult=1.5, stop_mult=1.0, atr_lookup={},
        start="2024-01-01", end="2024-01-05",
    )
    assert result["n_trades"] == 0


def test_no_trades_returns_zeroed_result():
    result = run_one_atr_config(
        [], target_mult=1.5, stop_mult=1.0, atr_lookup={},
        start="2024-01-01", end="2024-01-08",
    )
    assert result["n_trades"] == 0
    assert result["hit_rate"] == 0.0
    assert result["trades_per_week"] == 0.0


def test_build_atr_grid_size():
    grid = build_atr_grid()
    assert len(grid) == 4 * 4  # target_mult x stop_mult == 16
    assert all(cell["target_mult"] >= 1.0 for cell in grid)


def test_select_best_atr_config_prefers_highest_cagr_among_qualifying():
    results = [
        {"target_mult": 1.0, "stop_mult": 0.5, "hit_rate": 0.92, "trades_per_week": 6,
         "cagr_15slot": 0.10, "avg_pnl": 0.01, "n_trades": 100},
        {"target_mult": 1.5, "stop_mult": 0.5, "hit_rate": 0.91, "trades_per_week": 6,
         "cagr_15slot": 0.20, "avg_pnl": 0.01, "n_trades": 100},
        {"target_mult": 3.0, "stop_mult": 2.0, "hit_rate": 0.85, "trades_per_week": 6,
         "cagr_15slot": 0.50, "avg_pnl": 0.01, "n_trades": 100},  # hit_rate < 0.90 -> excluded
    ]
    sel = select_best_atr_config(results)
    assert sel["status"] == "target_met"
    assert sel["config"]["target_mult"] == 1.5


def test_select_best_atr_config_fallback_when_none_qualify():
    results = [
        {"target_mult": 1.0, "stop_mult": 2.0, "hit_rate": 0.70, "trades_per_week": 6,
         "cagr_15slot": 0.05, "avg_pnl": 0.005, "n_trades": 100},
        {"target_mult": 2.0, "stop_mult": 1.0, "hit_rate": 0.80, "trades_per_week": 6,
         "cagr_15slot": 0.02, "avg_pnl": 0.004, "n_trades": 50},
        {"target_mult": 3.0, "stop_mult": 0.5, "hit_rate": 0.95, "trades_per_week": 2,
         "cagr_15slot": 0.30, "avg_pnl": 0.02, "n_trades": 10},  # fails freq floor
    ]
    sel = select_best_atr_config(results)
    assert sel["status"] == "target_not_met"
    assert sel["config"]["hit_rate"] == 0.80
    assert len(sel["fallback_top5"]) == 2
    assert sel["fallback_best_cagr"]["hit_rate"] == 0.95


def test_run_atr_grid_search_train_test_split():
    def make(code, date, entry=100.0):
        return CachedCandidate(
            ticker=f"{code}.KS", code=code, date=date, entry=entry,
            pattern_type="E반등", score=110, rank_score=110, grade="매수",
            hold_days=3,
            window_open=[entry, entry, entry], window_high=[entry * 1.05] * 3,
            window_low=[entry * 0.97] * 3, window_close=[entry] * 3,
        )

    train_day = "2024-06-30T00:00:00+00:00"
    test_day = "2024-07-01T00:00:00+00:00"
    train_c = make("000001", train_day)
    test_c = make("000002", test_day)
    atr_lookup = {("000001.KS", train_day): 0.02, ("000002.KS", test_day): 0.02}

    result = run_atr_grid_search(
        [train_c, test_c], atr_lookup=atr_lookup,
        train_start="2024-01-01", train_end="2024-06-30",
        test_start="2024-07-01", test_end="2024-12-31",
    )
    assert len(result["train_results"]) == 16
    assert result["test_result"]["n_trades"] in (0, 1)
    assert "selection" in result

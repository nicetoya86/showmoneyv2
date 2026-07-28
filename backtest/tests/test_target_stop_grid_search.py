from backtest.generate_signal_candidates import CachedCandidate
from backtest.target_stop_grid_search import (
    build_grid,
    run_grid_search,
    run_one_config,
    select_best_config,
)


def _make_candidate(
    code, date, score, pattern_type="C촉매", grade="매수", entry=100.0, hold_days=3, window=None
):
    if window is None:
        window = {
            "open": [entry] * hold_days, "high": [entry] * hold_days,
            "low": [entry] * hold_days, "close": [entry] * hold_days,
        }
    return CachedCandidate(
        ticker=f"{code}.KS", code=code, date=date, entry=entry,
        pattern_type=pattern_type, score=score, rank_score=score, grade=grade,
        hold_days=hold_days,
        window_open=window["open"], window_high=window["high"],
        window_low=window["low"], window_close=window["close"],
    )


def test_min_score_excludes_below_threshold():
    low = _make_candidate("000001", "2024-01-02T00:00:00+00:00", score=70)
    high = _make_candidate("000002", "2024-01-02T00:00:00+00:00", score=95)
    result = run_one_config(
        [low, high], target_pct=0.03, stop_pct=0.02, min_score=90,
        regime_gate=False, exclude_d_box=False, regime_lookup={},
        start="2024-01-01", end="2024-01-05",
    )
    assert result["n_trades"] == 1


def test_regime_gate_excludes_non_strong_grade_in_bear_regime():
    day = "2024-01-02T00:00:00+00:00"
    normal = _make_candidate("000001", day, score=95, grade="매수")
    strong = _make_candidate("000002", day, score=120, grade="강매")
    result = run_one_config(
        [normal, strong], target_pct=0.03, stop_pct=0.02, min_score=60,
        regime_gate=True, exclude_d_box=False,
        regime_lookup={"2024-01-02": 2},
        start="2024-01-01", end="2024-01-05",
    )
    assert result["n_trades"] == 1  # only the 강매 candidate survives the bear-regime gate


def test_regime_gate_off_keeps_both_candidates():
    day = "2024-01-02T00:00:00+00:00"
    normal = _make_candidate("000001", day, score=95, grade="매수")
    strong = _make_candidate("000002", day, score=120, grade="강매")
    result = run_one_config(
        [normal, strong], target_pct=0.03, stop_pct=0.02, min_score=60,
        regime_gate=False, exclude_d_box=False,
        regime_lookup={"2024-01-02": 2},
        start="2024-01-01", end="2024-01-05",
    )
    assert result["n_trades"] == 2


def test_exclude_d_box_removes_d_box_candidates():
    day = "2024-01-02T00:00:00+00:00"
    dbox = _make_candidate("000001", day, score=95, pattern_type="D박스")
    other = _make_candidate("000002", day, score=95, pattern_type="C촉매")
    result = run_one_config(
        [dbox, other], target_pct=0.03, stop_pct=0.02, min_score=60,
        regime_gate=False, exclude_d_box=True, regime_lookup={},
        start="2024-01-01", end="2024-01-05",
    )
    assert result["n_trades"] == 1


def test_hit_rate_trades_per_week_and_pnl_value_pinned():
    day = "2024-01-02T00:00:00+00:00"
    # entry=100 -> target_pct=0.03 => target=103; stop_pct=0.02 => stop=98
    # window: day0 high=104 (>=target), low=99 (>stop) -> hits target on day 0
    hit = _make_candidate(
        "000001", day, score=100, hold_days=3, entry=100.0,
        window={
            "open": [100.0, 100.0, 100.0], "high": [104.0, 104.0, 104.0],
            "low": [99.0, 99.0, 99.0], "close": [103.5, 103.5, 103.5],
        },
    )
    result = run_one_config(
        [hit], target_pct=0.03, stop_pct=0.02, min_score=60,
        regime_gate=False, exclude_d_box=False, regime_lookup={},
        start="2024-01-01", end="2024-01-08",  # exactly 7 days = 1.0 week
    )
    assert result["n_trades"] == 1
    assert result["hit_rate"] == 1.0
    assert result["trades_per_week"] == 1.0
    assert abs(result["avg_pnl"] - (0.03 - 0.002)) < 1e-9  # net of default 0.2% round-trip cost


def test_no_trades_returns_zeroed_result():
    result = run_one_config(
        [], target_pct=0.03, stop_pct=0.02, min_score=60,
        regime_gate=False, exclude_d_box=False, regime_lookup={},
        start="2024-01-01", end="2024-01-08",
    )
    assert result["n_trades"] == 0
    assert result["hit_rate"] == 0.0
    assert result["trades_per_week"] == 0.0


def test_build_grid_size():
    grid = build_grid()
    assert len(grid) == 6 * 6 * 3 * 2 * 2  # target_pct x stop_pct x min_score x regime x d_box == 432
    assert all(cell["target_pct"] >= 0.03 for cell in grid)  # 3% floor, never searched below


def test_select_best_config_prefers_highest_cagr_among_qualifying():
    results = [
        {"target_pct": 0.03, "stop_pct": 0.02, "min_score": 60, "regime_gate": False,
         "exclude_d_box": False, "hit_rate": 0.92, "trades_per_week": 6, "cagr_15slot": 0.10,
         "avg_pnl": 0.01, "n_trades": 100},
        {"target_pct": 0.04, "stop_pct": 0.02, "min_score": 60, "regime_gate": False,
         "exclude_d_box": False, "hit_rate": 0.91, "trades_per_week": 6, "cagr_15slot": 0.20,
         "avg_pnl": 0.01, "n_trades": 100},
        {"target_pct": 0.05, "stop_pct": 0.02, "min_score": 60, "regime_gate": False,
         "exclude_d_box": False, "hit_rate": 0.85, "trades_per_week": 6, "cagr_15slot": 0.50,
         "avg_pnl": 0.01, "n_trades": 100},  # hit_rate < 0.90 -> does not qualify
    ]
    sel = select_best_config(results)
    assert sel["status"] == "target_met"
    assert sel["config"]["target_pct"] == 0.04  # highest cagr among the two qualifying rows


def test_select_best_config_fallback_when_none_qualify():
    results = [
        {"target_pct": 0.03, "stop_pct": 0.04, "min_score": 60, "regime_gate": False,
         "exclude_d_box": False, "hit_rate": 0.70, "trades_per_week": 6, "cagr_15slot": 0.05,
         "avg_pnl": 0.005, "n_trades": 100},
        {"target_pct": 0.05, "stop_pct": 0.02, "min_score": 90, "regime_gate": True,
         "exclude_d_box": True, "hit_rate": 0.80, "trades_per_week": 6, "cagr_15slot": 0.02,
         "avg_pnl": 0.004, "n_trades": 50},
        {"target_pct": 0.10, "stop_pct": 0.01, "min_score": 110, "regime_gate": False,
         "exclude_d_box": False, "hit_rate": 0.95, "trades_per_week": 2, "cagr_15slot": 0.30,
         "avg_pnl": 0.02, "n_trades": 10},  # highest hit_rate AND cagr, but fails freq floor
    ]
    sel = select_best_config(results)
    assert sel["status"] == "target_not_met"
    # only rows 1 & 2 satisfy trades_per_week >= 5; row 2 has the higher hit_rate (0.80 > 0.70)
    assert sel["config"]["hit_rate"] == 0.80
    assert len(sel["fallback_top5"]) == 2
    # best cagr regardless of frequency floor is still surfaced separately
    assert sel["fallback_best_cagr"]["hit_rate"] == 0.95


def test_run_grid_search_train_test_split_and_selection(monkeypatch):
    def make(code, date, score=100, entry=100.0):
        return CachedCandidate(
            ticker=f"{code}.KS", code=code, date=date, entry=entry,
            pattern_type="C촉매", score=score, rank_score=score, grade="매수",
            hold_days=3,
            window_open=[entry, entry, entry], window_high=[entry * 1.05] * 3,
            window_low=[entry * 0.97] * 3, window_close=[entry] * 3,
        )

    train_candidates = [make("000001", "2024-06-30T00:00:00+00:00")]
    test_candidates = [make("000002", "2024-07-01T00:00:00+00:00")]

    result = run_grid_search(
        train_candidates + test_candidates,
        regime_lookup={},
        train_start="2024-01-01", train_end="2024-06-30",
        test_start="2024-07-01", test_end="2024-12-31",
    )
    assert len(result["train_results"]) == 432
    # the 2024-06-30 candidate is train-only, the 2024-07-01 candidate is test-only
    assert result["test_result"]["n_trades"] in (0, 1)
    assert "selection" in result


def test_required_tags_filters_out_untagged_candidates():
    day = "2024-01-02T00:00:00+00:00"
    tagged = _make_candidate("000001", day, score=95)
    untagged = _make_candidate("000002", day, score=95)
    tags_lookup = {
        ("000001.KS", day): {"trend_aligned": True},
        ("000002.KS", day): {"trend_aligned": False},
    }
    result = run_one_config(
        [tagged, untagged], target_pct=0.03, stop_pct=0.02, min_score=60,
        regime_gate=False, exclude_d_box=False, regime_lookup={},
        start="2024-01-01", end="2024-01-05",
        required_tags=frozenset({"trend_aligned"}), tags_lookup=tags_lookup,
    )
    assert result["n_trades"] == 1


def test_required_tags_empty_reproduces_unfiltered_behavior():
    day = "2024-01-02T00:00:00+00:00"
    a = _make_candidate("000001", day, score=95)
    b = _make_candidate("000002", day, score=95)
    result = run_one_config(
        [a, b], target_pct=0.03, stop_pct=0.02, min_score=60,
        regime_gate=False, exclude_d_box=False, regime_lookup={},
        start="2024-01-01", end="2024-01-05",
    )
    assert result["n_trades"] == 2


def test_run_grid_search_passes_required_tags_through():
    def make(code, date, score=100, entry=100.0):
        return CachedCandidate(
            ticker=f"{code}.KS", code=code, date=date, entry=entry,
            pattern_type="C촉매", score=score, rank_score=score, grade="매수",
            hold_days=3,
            window_open=[entry, entry, entry], window_high=[entry * 1.05] * 3,
            window_low=[entry * 0.97] * 3, window_close=[entry] * 3,
        )

    day = "2024-06-30T00:00:00+00:00"
    tagged = make("000001", day)
    untagged = make("000002", day)
    tags_lookup = {
        ("000001.KS", day): {"trend_aligned": True},
        ("000002.KS", day): {"trend_aligned": False},
    }
    result = run_grid_search(
        [tagged, untagged], regime_lookup={},
        train_start="2024-01-01", train_end="2024-06-30",
        test_start="2024-07-01", test_end="2024-12-31",
        required_tags=frozenset({"trend_aligned"}), tags_lookup=tags_lookup,
    )
    assert all(r["n_trades"] <= 1 for r in result["train_results"])

import pandas as pd

from backtest.candidate_signals import (
    compute_trend_alignment,
    compute_vol_contraction,
    build_sector_returns_by_date,
    compute_sector_strength,
    tag_candidates,
)
from backtest.generate_signal_candidates import CachedCandidate


def _ohlcv_df(dates, opens, highs, lows, closes):
    return pd.DataFrame({
        "timestamp_utc": dates,
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": [1_000_000.0] * len(closes),
    })


def _flat_ohlcv_df(dates, closes):
    return _ohlcv_df(dates, closes, closes, closes, closes)


def test_trend_alignment_true_for_steady_uptrend():
    dates = pd.bdate_range("2024-01-01", periods=65, tz="UTC")  # 13 weeks of business days
    closes = [100.0 + i for i in range(65)]
    df = _flat_ohlcv_df(dates, closes)
    assert compute_trend_alignment(df, len(df) - 1) is True


def test_trend_alignment_false_for_steady_downtrend():
    dates = pd.bdate_range("2024-01-01", periods=65, tz="UTC")
    closes = [200.0 - i for i in range(65)]
    df = _flat_ohlcv_df(dates, closes)
    assert compute_trend_alignment(df, len(df) - 1) is False


def test_trend_alignment_false_with_fewer_than_10_completed_weeks():
    dates = pd.bdate_range("2024-01-01", periods=20, tz="UTC")  # only 4 weeks of business days
    closes = [100.0 + i for i in range(20)]
    df = _flat_ohlcv_df(dates, closes)
    assert compute_trend_alignment(df, len(df) - 1) is False


def test_vol_contraction_true_when_tight_before_an_excluded_recent_breakout():
    dates = pd.bdate_range("2024-01-01", periods=80, tz="UTC")
    closes = [100.0] * 80
    # Tight range (high-low = 1.0) for bars 0..69 (covers the idx-60..idx-10 window);
    # a sharp breakout range (20.0) for the excluded most-recent 10 bars (70..79).
    highs = [100.5] * 70 + [110.0] * 10
    lows = [99.5] * 70 + [90.0] * 10
    df = _ohlcv_df(dates, closes, highs, lows, closes)
    assert compute_vol_contraction(df, len(df) - 1) is True


def test_vol_contraction_false_when_range_expands_into_the_pre_event_window():
    dates = pd.bdate_range("2024-01-01", periods=80, tz="UTC")
    closes = [100.0] * 80
    # Range grows monotonically across the whole series, including inside the pre-event
    # window itself -- the most recent pre-event point is near the window's max, not its
    # bottom 20th percentile.
    highs = [100.0 + 0.15 * i for i in range(80)]
    lows = [100.0 - 0.15 * i for i in range(80)]
    df = _ohlcv_df(dates, closes, highs, lows, closes)
    assert compute_vol_contraction(df, len(df) - 1) is False


def test_vol_contraction_false_with_insufficient_history():
    dates = pd.bdate_range("2024-01-01", periods=25, tz="UTC")
    closes = [100.0] * 25
    df = _flat_ohlcv_df(dates, closes)
    assert compute_vol_contraction(df, len(df) - 1) is False


def test_build_sector_returns_by_date_requires_min_sector_size():
    dates = pd.bdate_range("2024-01-01", periods=25, tz="UTC")
    date_strs = list(dates)

    sector_map = {}
    per_ticker_ohlcv = {}
    # Sector AAAAAA: 5 tickers, all flat then +10% in the last 5 bars -> qualifies.
    for i in range(5):
        code = f"AAA{i}"
        closes = [100.0] * 20 + [110.0] * 5
        per_ticker_ohlcv[f"{code}.KS"] = _flat_ohlcv_df(date_strs, closes)
        sector_map[code] = "AAAAAA"
    # Sector ZZZZZZ: only 2 tickers -> below min_sector_size, must not appear.
    for i in range(2):
        code = f"ZZZ{i}"
        closes = [100.0] * 20 + [90.0] * 5
        per_ticker_ohlcv[f"{code}.KS"] = _flat_ohlcv_df(date_strs, closes)
        sector_map[code] = "ZZZZZZ"

    result = build_sector_returns_by_date(sector_map, per_ticker_ohlcv, lookback=20, min_sector_size=5)
    last_date_key = dates[-1].date().isoformat()
    assert "AAAAAA" in result[last_date_key]
    assert abs(result[last_date_key]["AAAAAA"] - 0.10) < 1e-9
    assert "ZZZZZZ" not in result[last_date_key]


def test_compute_sector_strength_ranks_against_other_sectors():
    sector_returns_by_date = {
        "2024-01-30": {
            "S1": 0.20, "S2": 0.15, "S3": 0.10, "S4": 0.05, "S5": 0.02,
            "S6": 0.00, "S7": -0.02, "S8": -0.05, "S9": -0.08, "S10": -0.10,
        }
    }
    sector_map = {"CODE_TOP": "S3", "CODE_MID": "S4"}
    assert compute_sector_strength(
        sector_returns_by_date, sector_map, "CODE_TOP", "2024-01-30", top_frac=0.3,
    ) is True
    assert compute_sector_strength(
        sector_returns_by_date, sector_map, "CODE_MID", "2024-01-30", top_frac=0.3,
    ) is False


def test_compute_sector_strength_false_when_unmapped_or_below_min_sample():
    assert compute_sector_strength({}, {}, "ANY_CODE", "2024-01-30") is False
    sector_returns_by_date = {"2024-01-30": {"S1": 0.20}}
    # CODE's sector ("S9") isn't present that date -- either unmapped upstream or filtered
    # out by build_sector_returns_by_date's min_sector_size gate.
    assert compute_sector_strength(sector_returns_by_date, {"CODE": "S9"}, "CODE", "2024-01-30") is False


def test_tag_candidates_keys_by_ticker_and_date_and_fails_closed_when_untradeable():
    dates = pd.bdate_range("2024-01-01", periods=65, tz="UTC")
    closes = [100.0 + i for i in range(65)]
    df = _flat_ohlcv_df(dates, closes)
    candidate_date = dates[-1].isoformat()

    candidate = CachedCandidate(
        ticker="000001.KS", code="000001", date=candidate_date, entry=164.0,
        pattern_type="C촉매", score=100, rank_score=100, grade="매수", hold_days=3,
        window_open=[164.0], window_high=[165.0], window_low=[163.0], window_close=[164.0],
    )
    missing_df_candidate = CachedCandidate(
        ticker="999999.KQ", code="999999", date=candidate_date, entry=100.0,
        pattern_type="C촉매", score=100, rank_score=100, grade="매수", hold_days=3,
        window_open=[100.0], window_high=[101.0], window_low=[99.0], window_close=[100.0],
    )

    tags = tag_candidates(
        [candidate, missing_df_candidate],
        per_ticker_ohlcv={"000001.KS": df},
        sector_map={},
    )

    assert set(tags[("000001.KS", candidate_date)].keys()) == {
        "trend_aligned", "vol_contraction", "sector_strong",
    }
    assert tags[("999999.KQ", candidate_date)] == {
        "trend_aligned": False, "vol_contraction": False, "sector_strong": False,
    }

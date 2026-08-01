import numpy as np
import pandas as pd

from backtest import oversold_candidate_signals as mod
from backtest.generate_signal_candidates import CachedCandidate


def _make_df(close, high=None, low=None, volume=None):
    close = np.asarray(close, dtype="float64")
    n = len(close)
    return pd.DataFrame({
        "timestamp_utc": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
        "open": close,
        "high": high if high is not None else close * 1.01,
        "low": low if low is not None else close * 0.99,
        "close": close,
        "volume": volume if volume is not None else np.full(n, 1_000_000.0),
    })


def test_compute_volume_confirm_true_at_or_above_threshold():
    volume = np.full(26, 1_000_000.0)
    volume[25] = 2_000_000.0  # rvol = 2.0 >= 1.5
    df = _make_df(np.full(26, 100.0), volume=volume)
    assert mod.compute_volume_confirm(df, 25) is True


def test_compute_volume_confirm_false_below_threshold():
    volume = np.full(26, 1_000_000.0)  # rvol = 1.0 < 1.5
    df = _make_df(np.full(26, 100.0), volume=volume)
    assert mod.compute_volume_confirm(df, 25) is False


def test_compute_support_confluence_true_near_pivot_low():
    # descend 1000->900 over 30 bars, then ascend to 920 (2.2% above the 900 pivot low)
    desc = np.linspace(1000, 900, 30)
    asc = np.linspace(905, 920, 15)
    close = np.concatenate([desc, asc])
    idx = len(close) - 1
    df = _make_df(close)
    assert mod.compute_support_confluence(df, idx) is True


def test_compute_support_confluence_false_far_from_pivot_low():
    desc = np.linspace(1000, 900, 30)
    asc = np.linspace(905, 970, 15)  # 7.8% above the 900 pivot low -- outside 3% tolerance
    close = np.concatenate([desc, asc])
    idx = len(close) - 1
    df = _make_df(close)
    assert mod.compute_support_confluence(df, idx) is False


def test_compute_support_confluence_false_when_no_interior_pivot():
    # pure monotonic ascent -- no local low strictly lower than both neighborhoods
    close = np.linspace(900, 950, 45)
    idx = len(close) - 1
    df = _make_df(close)
    assert mod.compute_support_confluence(df, idx) is False


def test_compute_atr_pct_value_pinned():
    n = 20
    df = _make_df(np.full(n, 100.0), high=np.full(n, 101.0), low=np.full(n, 99.0))
    idx = n - 1
    atr_pct = mod.compute_atr_pct(df, idx)
    assert abs(atr_pct - 0.02) < 1e-9


def test_compute_atr_pct_nan_when_insufficient_history():
    df = _make_df(np.full(5, 100.0), high=np.full(5, 101.0), low=np.full(5, 99.0))
    assert np.isnan(mod.compute_atr_pct(df, 2))


def _candidate(ticker, code, date, entry=100.0):
    return CachedCandidate(
        ticker=ticker, code=code, date=date, entry=entry,
        pattern_type="E반등", score=110, rank_score=110, grade="매수", hold_days=5,
        window_open=[entry] * 5, window_high=[entry] * 5,
        window_low=[entry] * 5, window_close=[entry] * 5,
    )


def test_tag_candidates_oversold_maps_each_candidate():
    n = 26
    close = np.full(n, 100.0)
    volume = np.full(n, 1_000_000.0)
    volume[25] = 2_000_000.0
    df = _make_df(close, volume=volume)
    date = df["timestamp_utc"].iloc[25].isoformat()
    candidate = _candidate("000001.KS", "000001", date)

    tags = mod.tag_candidates_oversold([candidate], {"000001.KS": df}, sector_map={})
    key = ("000001.KS", date)
    assert key in tags
    assert tags[key]["volume_confirm"] is True
    assert tags[key]["sector_strong"] is False  # empty sector_map fails closed
    assert tags[key]["support_confluence"] is False  # flat price series has no pivot low


def test_tag_candidates_oversold_fails_closed_when_ticker_unknown():
    candidate = _candidate("999999.KS", "999999", "2024-01-26T00:00:00+00:00")
    tags = mod.tag_candidates_oversold([candidate], {}, sector_map={})
    key = ("999999.KS", "2024-01-26T00:00:00+00:00")
    assert tags[key] == {"volume_confirm": False, "sector_strong": False, "support_confluence": False}


def test_build_atr_pct_lookup_includes_only_locatable_candidates():
    n = 20
    df = _make_df(np.full(n, 100.0), high=np.full(n, 101.0), low=np.full(n, 99.0))
    date = df["timestamp_utc"].iloc[19].isoformat()
    found = _candidate("000001.KS", "000001", date)
    missing = _candidate("999999.KS", "999999", "2024-01-26T00:00:00+00:00")

    lookup = mod.build_atr_pct_lookup([found, missing], {"000001.KS": df})
    assert ("000001.KS", date) in lookup
    assert abs(lookup[("000001.KS", date)] - 0.02) < 1e-9
    assert ("999999.KS", "2024-01-26T00:00:00+00:00") not in lookup

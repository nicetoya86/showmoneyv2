import numpy as np
import pandas as pd

from backtest import generate_oversold_candidates as mod


def _build_df(flat_n, flat_level, rally_days, rally_step, decline_days, decline_step, bounce_close):
    """Builds a synthetic OHLCV DataFrame: flat history -> rally -> decline -> one bounce day
    (the last row, returned as `idx`). All price paths below were verified against the real
    backtest.indicators.rsi14/sma functions before being written into this test."""
    closes = [float(flat_level)] * flat_n
    for i in range(1, rally_days + 1):
        closes.append(flat_level + i * rally_step)
    last = closes[-1]
    for i in range(1, decline_days + 1):
        closes.append(last - i * decline_step)
    closes.append(bounce_close)
    close = np.array(closes, dtype="float64")
    high = close * 1.01
    low = close * 0.99
    openp = np.concatenate([[close[0]], close[:-1]])
    df = pd.DataFrame({
        "open": openp, "high": high, "low": low, "close": close,
        "volume": np.full(len(close), 2_000_000_000.0),
    })
    return df, len(close) - 1


def test_is_oversold_bounce_all_conditions_true():
    df, idx = _build_df(48, 950, 16, 15, 18, 13, 1067.2639)
    assert mod._is_oversold_bounce(df, idx) is True


def test_is_oversold_bounce_false_when_no_rsi_crossup():
    # RSI never crosses back up through 40 (bounce too small)
    df, idx = _build_df(45, 900, 18, 25, 22, 11, 1122.3227)
    assert mod._is_oversold_bounce(df, idx) is False


def test_is_oversold_bounce_false_when_no_oversold_depth():
    # RSI crosses up through 40, but never dipped to <=35 in the prior 5 bars
    df, idx = _build_df(38, 900, 19, 30, 18, 15, 1272.0)
    assert mod._is_oversold_bounce(df, idx) is False


def test_is_oversold_bounce_false_when_pullback_too_shallow():
    # only ~5% off the 20-day high, short of the required 8%
    df, idx = _build_df(49, 1100, 15, 10, 25, 9, 1148.0)
    assert mod._is_oversold_bounce(df, idx) is False


def test_is_oversold_bounce_false_when_below_sma60():
    # bounce day's close is still below the 60-day SMA (no uptrend context)
    df, idx = _build_df(49, 1000, 7, 25, 19, 15, 996.8)
    assert mod._is_oversold_bounce(df, idx) is False


def test_is_oversold_bounce_false_when_not_above_prior_day_high():
    # same price path as the all-true case, but the prior day had a long upper wick
    # (high raised well above the bounce day's close) so the breakout confirmation fails
    df, idx = _build_df(48, 950, 16, 15, 18, 13, 1067.2639)
    df.loc[idx - 1, "high"] = 1117.2639
    assert mod._is_oversold_bounce(df, idx) is False


def test_scan_oversold_candidates_caches_window_and_fields(monkeypatch):
    ticker = "000001.KS"
    df = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08",
             "2024-01-09", "2024-01-10", "2024-01-11"],
            utc=True,
        ),
        "open":   [100.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
        "high":   [101.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
        "low":    [99.0,  99.0,  100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        "close":  [100.0, 100.0, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5],
        "volume": [1_000_000.0] * 8,
    })

    monkeypatch.setattr(mod, "fetch_yahoo_chart", lambda spec: {"_fake_for": spec.ticker})
    monkeypatch.setattr(mod, "chart_to_ohlcv_daily", lambda data: (df.copy(), None))
    monkeypatch.setattr(mod, "fetch_supply_for_date", lambda trd_dd: {})
    monkeypatch.setattr(mod, "fetch_disclosures_for_date", lambda trd_dd, api_key: {})
    monkeypatch.setattr(mod, "_passes_base_filters", lambda df, idx, *, supply, dart_items: True)
    monkeypatch.setattr(mod, "_is_oversold_bounce", lambda df, idx: idx == 1)

    candidates, skipped = mod.scan_oversold_candidates([ticker], start="2024-01-01", end="2024-01-12")

    assert skipped == []
    assert len(candidates) == 1
    c = candidates[0]
    assert c.ticker == ticker
    assert c.code == "000001"
    assert c.date == "2024-01-03T00:00:00+00:00"
    assert c.entry == 100.0
    assert c.pattern_type == "E반등"
    assert c.score == 110
    assert c.rank_score == 110
    assert c.grade == "매수"
    assert c.hold_days == 5
    # entry_idx = idx(1) + 1 = 2; window is df.iloc[2:7] (HOLD_DAYS=5 rows, all exist)
    assert c.window_open == [101.0, 102.0, 103.0, 104.0, 105.0]
    assert c.window_high == [102.0, 103.0, 104.0, 105.0, 106.0]
    assert c.window_low == [100.0, 101.0, 102.0, 103.0, 104.0]
    assert c.window_close == [101.5, 102.5, 103.5, 104.5, 105.5]


def test_scan_oversold_candidates_skips_fetch_failure(monkeypatch):
    import requests

    def raise_fetch(spec):
        raise requests.exceptions.RequestException("boom")

    monkeypatch.setattr(mod, "fetch_yahoo_chart", raise_fetch)

    candidates, skipped = mod.scan_oversold_candidates(
        ["999999.KS"], start="2024-01-01", end="2024-01-10"
    )
    assert candidates == []
    assert skipped == [{"ticker": "999999.KS", "error": "boom"}]

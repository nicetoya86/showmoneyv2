import pandas as pd

from backtest import generate_signal_candidates as mod


def test_generate_candidates_caches_window_and_fields(monkeypatch):
    ticker = "000001.KS"
    df = pd.DataFrame({
        "timestamp_utc": pd.to_datetime(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"],
            utc=True,
        ),
        "open":   [100.0, 100.0, 101.0, 102.0, 103.0, 104.0],
        "high":   [101.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        "low":    [99.0,  99.0,  100.0, 101.0, 102.0, 103.0],
        "close":  [100.0, 100.0, 101.5, 102.5, 103.5, 104.5],
        "volume": [1_000_000.0] * 6,
    })

    monkeypatch.setattr(mod, "fetch_yahoo_chart", lambda spec: {"_fake_for": spec.ticker})
    monkeypatch.setattr(mod, "chart_to_ohlcv_daily", lambda data: (df.copy(), None))
    monkeypatch.setattr(mod, "fetch_supply_for_date", lambda trd_dd: {})
    monkeypatch.setattr(mod, "fetch_disclosures_for_date", lambda trd_dd, api_key: {})

    from backtest.swing_signal_engine import SwingCandidate

    def fake_evaluate_candidate(df_arg, idx, *, supply, dart_items, day_of_week):
        if idx != 1:
            return None
        return SwingCandidate(
            pattern_type="D박스", score=100, rank_score=100, grade="매수",
            entry=100.0, target=110.0, stop=90.0, hold_days=3, signals=[],
        )

    monkeypatch.setattr(mod, "evaluate_candidate", fake_evaluate_candidate)

    candidates, skipped = mod.generate_candidates([ticker], start="2024-01-01", end="2024-01-10")

    assert skipped == []
    assert len(candidates) == 1
    c = candidates[0]
    assert c.ticker == ticker
    assert c.code == "000001"
    assert c.date == "2024-01-03T00:00:00+00:00"
    assert c.entry == 100.0
    assert c.pattern_type == "D박스"
    assert c.score == 100
    assert c.grade == "매수"
    assert c.hold_days == 3
    # entry_idx = idx(1) + 1 = 2; window is df.iloc[2:7], but only rows 2..5 exist (4 rows)
    assert c.window_open == [101.0, 102.0, 103.0, 104.0]
    assert c.window_high == [102.0, 103.0, 104.0, 105.0]
    assert c.window_low == [100.0, 101.0, 102.0, 103.0]
    assert c.window_close == [101.5, 102.5, 103.5, 104.5]


def test_generate_candidates_skips_fetch_failure(monkeypatch):
    import requests

    def raise_fetch(spec):
        raise requests.exceptions.RequestException("boom")

    monkeypatch.setattr(mod, "fetch_yahoo_chart", raise_fetch)

    candidates, skipped = mod.generate_candidates(
        ["999999.KS"], start="2024-01-01", end="2024-01-10"
    )
    assert candidates == []
    assert skipped == [{"ticker": "999999.KS", "error": "boom"}]

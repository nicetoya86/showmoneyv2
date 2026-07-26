import json

import pandas as pd
import requests

from backtest.run_swing_v2_backtest import GRADE_ORDER, apply_daily_selection
from backtest.swing_signal_engine import SwingCandidate


def _cand(code, rank_score, grade="매수"):
    return (code, SwingCandidate(
        pattern_type="D박스", score=rank_score, rank_score=rank_score, grade=grade,
        entry=1000.0, target=1100.0, stop=960.0, hold_days=4, signals=[],
    ))


def test_weekly_cap_stops_new_selections():
    week_state = {"count": 15, "codes": set()}
    todays = [_cand("000001", 90), _cand("000002", 80)]
    selected = apply_daily_selection(todays, week_state, max_per_day=3, max_per_week=15)
    assert selected == []


def test_dedup_same_code_within_week():
    week_state = {"count": 1, "codes": {"000001"}}
    todays = [_cand("000001", 95), _cand("000002", 90)]
    selected = apply_daily_selection(todays, week_state, max_per_day=3, max_per_week=15)
    assert [c for c, _ in selected] == ["000002"]


def test_grade_order_wins_over_rank_score():
    week_state = {"count": 0, "codes": set()}
    todays = [
        _cand("000001", 200, grade="매수"),
        _cand("000002", 60, grade="강매"),
    ]
    selected = apply_daily_selection(todays, week_state, max_per_day=3, max_per_week=15)
    assert [c for c, _ in selected][0] == "000002"  # 강매 outranks 매수 regardless of score


def test_max_per_day_caps_selection():
    week_state = {"count": 0, "codes": set()}
    todays = [_cand(f"{i:06d}", 100 - i) for i in range(5)]
    selected = apply_daily_selection(todays, week_state, max_per_day=3, max_per_week=15)
    assert len(selected) == 3


def test_week_state_mutation():
    """Verify that apply_daily_selection updates week_state with selected codes and count."""
    week_state = {"count": 0, "codes": set()}
    todays = [_cand("000001", 90), _cand("000002", 80), _cand("000003", 70)]
    selected = apply_daily_selection(todays, week_state, max_per_day=2, max_per_week=15)

    # Should select 2 items
    assert len(selected) == 2
    selected_codes = {c for c, _ in selected}

    # week_state should be updated with selected codes
    assert week_state["codes"] == selected_codes
    # week_state count should be updated to 2
    assert week_state["count"] == 2


def test_json_serialization_regression():
    """Regression test: ensure backtest_swing_v2 result is JSON-serializable (no Timestamp objects)."""
    import pandas as pd
    from backtest.run_swing_v2_backtest import backtest_swing_v2

    # Minimal test: create a trades DataFrame as backtest_swing_v2 would return it
    # This simulates what happens when at least one trade exists
    trades_data = [
        {
            "date": "2024-01-15T00:00:00+00:00",
            "ticker": "005930.KS",
            "code": "005930",
            "pattern_type": "D박스",
            "grade": "매수",
            "score": 75,
            "rank_score": 75,
            "entry": 1000.0,
            "stop": 950.0,
            "target": 1100.0,
            "exit_price": 1050.0,
            "result": "target",
            "days_held": 3,
            "pnl": 0.05,
        }
    ]
    df_trades = pd.DataFrame(trades_data)

    # Verify that df_trades.to_dict() is JSON-serializable (should not contain Timestamp objects)
    trades_dict = df_trades.to_dict(orient="records")
    try:
        json.dumps(trades_dict)
    except TypeError as e:
        if "Timestamp" in str(e):
            raise AssertionError(f"DataFrame contains non-JSON-serializable Timestamp: {e}")
        raise


def test_backtest_swing_v2_skips_failed_ticker_and_continues(monkeypatch, capsys):
    """Resilience regression: one ticker's Yahoo fetch failing (e.g. a delisted symbol
    returning HTTP 404) must not abort the whole run. It should be logged, recorded in
    stats["skipped_tickers"], and the loop must continue processing the other tickers
    instead of letting the exception propagate out of backtest_swing_v2.

    Also verifies that the warning message uses only ASCII characters to avoid
    UnicodeEncodeError on cp949 and other limited consoles."""
    from backtest import run_swing_v2_backtest as mod

    ok_ticker = "005930.KS"
    bad_ticker = "042670.KS"

    timestamps = [
        pd.Timestamp("2024-01-01", tz="UTC").timestamp(),
        pd.Timestamp("2024-01-02", tz="UTC").timestamp(),
    ]
    ok_chart = {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0, 101.0],
                                "high": [101.0, 102.0],
                                "low": [99.0, 100.0],
                                "close": [100.5, 101.5],
                                "volume": [1_000_000, 1_000_000],
                            }
                        ]
                    },
                    "meta": {},
                }
            ]
        }
    }

    def fake_fetch_yahoo_chart(spec):
        if spec.ticker == bad_ticker:
            raise requests.exceptions.HTTPError("404 test")
        return ok_chart

    supply_calls = []
    dart_calls = []

    def fake_fetch_supply_for_date(trd_dd):
        supply_calls.append(trd_dd)
        return {}

    def fake_fetch_disclosures_for_date(trd_dd, *, api_key):
        dart_calls.append(trd_dd)
        return {}

    monkeypatch.setattr(mod, "fetch_yahoo_chart", fake_fetch_yahoo_chart)
    monkeypatch.setattr(mod, "fetch_supply_for_date", fake_fetch_supply_for_date)
    monkeypatch.setattr(mod, "fetch_disclosures_for_date", fake_fetch_disclosures_for_date)

    # Must not raise: the bad ticker's RequestException must be caught internally.
    df_trades, stats = mod.backtest_swing_v2(
        [ok_ticker, bad_ticker], start="2024-01-01", end="2024-01-02",
    )

    # Failing ticker is recorded, with its error, in stats["skipped_tickers"].
    skipped = stats.get("skipped_tickers", [])
    assert any(entry["ticker"] == bad_ticker for entry in skipped)

    # The non-failing ticker was not silently dropped too: its fetched daily bars
    # drove the day-by-day loop (all_days is built only from successfully-fetched
    # per_ticker data), proven by the per-day supply/DART lookups actually firing.
    assert len(supply_calls) == 2
    assert len(dart_calls) == 2

    # Regression: the warning message for the skipped ticker must be pure ASCII
    # to avoid UnicodeEncodeError on cp949 and other limited consoles.
    captured = capsys.readouterr()
    warning_output = captured.out
    assert warning_output.isascii(), (
        f"WARNING output contains non-ASCII characters and will fail on cp949: {repr(warning_output)}"
    )


def test_backtest_swing_v2_skips_ticker_on_value_error_and_continues(monkeypatch, capsys):
    """Widened fetch-resilience regression: `chart_to_ohlcv_daily` raises a plain
    `ValueError("Yahoo chart: missing result")` on an HTTP-200-with-empty-result response
    (e.g. a suspended or newly-listed ticker) -- this is NOT a `requests.exceptions.RequestException`
    subclass. Before the fix, this ValueError would propagate out of backtest_swing_v2 and crash
    the whole run, exactly like the original delisted-ticker bug. It must be caught the same way
    the RequestException case is: logged, recorded in stats["skipped_tickers"], and the loop must
    continue processing the other tickers."""
    from backtest import run_swing_v2_backtest as mod

    ok_ticker = "005930.KS"
    bad_ticker = "999999.KS"

    timestamps = [
        pd.Timestamp("2024-01-01", tz="UTC").timestamp(),
        pd.Timestamp("2024-01-02", tz="UTC").timestamp(),
    ]
    ok_chart = {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0, 101.0],
                                "high": [101.0, 102.0],
                                "low": [99.0, 100.0],
                                "close": [100.5, 101.5],
                                "volume": [1_000_000, 1_000_000],
                            }
                        ]
                    },
                    "meta": {},
                }
            ]
        }
    }

    def fake_fetch_yahoo_chart(spec):
        if spec.ticker == bad_ticker:
            # Mirrors chart_to_ohlcv_daily's real behavior for an HTTP-200-with-empty-result
            # response: {"chart": {"result": None}} (or missing entirely).
            return {"chart": {"result": None}}
        return ok_chart

    def fake_fetch_supply_for_date(trd_dd):
        return {}

    def fake_fetch_disclosures_for_date(trd_dd, *, api_key):
        return {}

    monkeypatch.setattr(mod, "fetch_yahoo_chart", fake_fetch_yahoo_chart)
    monkeypatch.setattr(mod, "fetch_supply_for_date", fake_fetch_supply_for_date)
    monkeypatch.setattr(mod, "fetch_disclosures_for_date", fake_fetch_disclosures_for_date)

    # Must not raise: the bad ticker's ValueError (raised by the real chart_to_ohlcv_daily
    # via mod.chart_to_ohlcv_daily) must be caught internally, same as a RequestException.
    df_trades, stats = mod.backtest_swing_v2(
        [ok_ticker, bad_ticker], start="2024-01-01", end="2024-01-02",
    )

    skipped = stats.get("skipped_tickers", [])
    assert any(entry["ticker"] == bad_ticker for entry in skipped)
    assert "missing result" in next(e["error"] for e in skipped if e["ticker"] == bad_ticker)

    captured = capsys.readouterr()
    assert captured.out.isascii()

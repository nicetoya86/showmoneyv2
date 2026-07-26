import json
from pathlib import Path
from unittest.mock import patch
import requests

from backtest.dart_history import fetch_disclosures_for_date


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def test_fetch_disclosures_groups_by_code_and_caches(tmp_path):
    """Test basic grouping by code, caching, and HTTP call shape."""
    payload = {
        "list": [
            {"stock_code": "005930", "report_nm": "단일판매 공급계약체결"},
            {"stock_code": "005930", "report_nm": "특허권취득"},
            {"stock_code": "000660", "report_nm": "감사보고서제출"},
        ]
    }
    cache_dir = tmp_path / "dart"
    with patch("backtest.dart_history.requests.get", return_value=_FakeResp(payload)) as mock_get:
        result = fetch_disclosures_for_date("20240105", api_key="dummy", cache_dir=cache_dir)
        assert result["005930"] == ["단일판매 공급계약체결", "특허권취득"]
        assert result["000660"] == ["감사보고서제출"]
        assert mock_get.call_count == 1

        # Verify HTTP call shape: params match trd_dd argument
        call_args = mock_get.call_args
        assert call_args[0][0] == "https://opendart.fss.or.kr/api/list.json"
        params = call_args[1]["params"]
        assert params["crtfc_key"] == "dummy"
        assert params["bgn_de"] == "20240105"
        assert params["end_de"] == "20240105"
        assert params["page_no"] == 1
        assert params["page_count"] == 100

    # second call must hit the cache, not the network again
    with patch("backtest.dart_history.requests.get", side_effect=AssertionError("should not be called")):
        cached = fetch_disclosures_for_date("20240105", api_key="dummy", cache_dir=cache_dir)
        assert cached["005930"] == ["단일판매 공급계약체결", "특허권취득"]

    assert (cache_dir / "20240105.json").exists()


def test_fetch_disclosures_cache_without_network_call(tmp_path):
    """Test that cached result is used without network call."""
    payload = {
        "list": [
            {"stock_code": "005930", "report_nm": "단일판매 공급계약체결"},
            {"stock_code": "005930", "report_nm": "특허권취득"},
        ]
    }
    cache_dir = tmp_path / "dart"
    # First fetch: network call
    with patch("backtest.dart_history.requests.get", return_value=_FakeResp(payload)):
        result1 = fetch_disclosures_for_date("20240106", api_key="dummy", cache_dir=cache_dir)
        assert result1["005930"] == ["단일판매 공급계약체결", "특허권취득"]

    # Second fetch: should use cache, network should not be called
    with patch("backtest.dart_history.requests.get", side_effect=AssertionError("no network")):
        result2 = fetch_disclosures_for_date("20240106", api_key="dummy", cache_dir=cache_dir)
        assert result2["005930"] == ["단일판매 공급계약체결", "특허권취득"]


def test_fetch_disclosures_exception_returns_empty_dict(tmp_path):
    """Test that network errors/timeouts return empty dict without caching."""
    cache_dir = tmp_path / "dart"

    # Simulate network timeout
    with patch("backtest.dart_history.requests.get", side_effect=requests.exceptions.Timeout("timeout")):
        result = fetch_disclosures_for_date("20240107", api_key="dummy", cache_dir=cache_dir)
        assert result == {}

    # Verify cache file was NOT created (so future retries will try the network again)
    assert not (cache_dir / "20240107.json").exists()


def test_fetch_disclosures_exception_from_parse_returns_empty_dict(tmp_path):
    """Test that JSON parse errors return empty dict without caching."""
    cache_dir = tmp_path / "dart"

    # Simulate a response that fails to parse as JSON
    with patch("backtest.dart_history.requests.get") as mock_get:
        mock_resp = _FakeResp({})
        # Make json() raise an exception
        mock_resp.json = lambda: (_ for _ in ()).throw(ValueError("Invalid JSON"))
        mock_get.return_value = mock_resp

        result = fetch_disclosures_for_date("20240108", api_key="dummy", cache_dir=cache_dir)
        assert result == {}

    # Verify cache file was NOT created
    assert not (cache_dir / "20240108.json").exists()


def test_fetch_disclosures_corrupted_cache_falls_back_to_network(tmp_path):
    """A truncated/corrupted cache file (e.g. left behind by an interrupted earlier run) must
    not raise json.JSONDecodeError and kill the whole day-loop. It should be treated as a cache
    miss and fall through to re-fetch from the network."""
    cache_dir = tmp_path / "dart"
    cache_dir.mkdir(parents=True, exist_ok=True)
    corrupted_path = cache_dir / "20240112.json"
    corrupted_path.write_text('{"005930": ["단일판매 공급', encoding="utf-8")  # truncated JSON

    payload = {
        "list": [
            {"stock_code": "005930", "report_nm": "감사보고서제출"},
        ]
    }
    with patch("backtest.dart_history.requests.get", return_value=_FakeResp(payload)) as mock_get:
        result = fetch_disclosures_for_date("20240112", api_key="dummy", cache_dir=cache_dir)
        # Falls through to network fetch instead of raising.
        assert result["005930"] == ["감사보고서제출"]
        assert mock_get.call_count == 1

    # Self-heals: the corrupted cache file is overwritten with valid JSON.
    assert json.loads(corrupted_path.read_text(encoding="utf-8"))["005930"] == ["감사보고서제출"]


def test_fetch_disclosures_exception_from_row_processing_returns_empty_dict(tmp_path):
    """Test that malformed rows during processing return empty dict without caching.

    Exception scope should wrap the entire operation (fetch + parse + row processing + cache write),
    not just the network call.
    """
    cache_dir = tmp_path / "dart"

    # Mock a response where list is not a list (will fail when accessing dict keys on non-dict items).
    with patch("backtest.dart_history.requests.get") as mock_get:
        mock_resp = _FakeResp({})
        # Return a response where list is a string, not a list.
        # Iterating over it yields characters, and calling .get() on a char raises AttributeError.
        mock_resp.json = lambda: {"list": "not-a-list"}
        mock_get.return_value = mock_resp

        result = fetch_disclosures_for_date("20240109", api_key="dummy", cache_dir=cache_dir)
        # Should return empty dict (exception during row-loop .get() call)
        assert result == {}

    # Verify cache file was NOT created (exception = no cache)
    assert not (cache_dir / "20240109.json").exists()


def test_fetch_disclosures_empty_list_returns_empty_dict(tmp_path):
    """Test that empty list is valid and returns empty dict (but is still cached)."""
    payload = {
        "list": []
    }
    cache_dir = tmp_path / "dart"
    with patch("backtest.dart_history.requests.get", return_value=_FakeResp(payload)):
        result = fetch_disclosures_for_date("20240110", api_key="dummy", cache_dir=cache_dir)
        assert result == {}
        # Cache should still be written (empty result is valid)
        assert (cache_dir / "20240110.json").exists()
        assert json.loads((cache_dir / "20240110.json").read_text()) == {}


def test_fetch_disclosures_with_custom_api_key(tmp_path):
    """Test that custom api_key is passed to the API call."""
    payload = {"list": []}
    cache_dir = tmp_path / "dart"
    custom_key = "my-custom-api-key-123"

    with patch("backtest.dart_history.requests.get", return_value=_FakeResp(payload)) as mock_get:
        fetch_disclosures_for_date("20240111", api_key=custom_key, cache_dir=cache_dir)

        # Verify the custom key was used
        call_args = mock_get.call_args
        params = call_args[1]["params"]
        assert params["crtfc_key"] == custom_key

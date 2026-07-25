import json
from pathlib import Path
from unittest.mock import patch
import requests

from backtest.krx_supply_history import fetch_supply_for_date


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def test_fetch_supply_for_date_parses_and_caches(tmp_path):
    """Test basic parsing, caching, and HTTP call shape."""
    payload = {
        "output": [
            {"ISU_SRT_CD": "005930", "FRGN_NETBUY_TRDVAL": "1,234,567", "ORG_NETBUY_TRDVAL": "-500,000"},
            {"ISU_SRT_CD": "000660", "FRGN_NETBUY_TRDVAL": "0", "ORG_NETBUY_TRDVAL": "600,000,000"},
        ]
    }
    cache_dir = tmp_path / "krx_supply"
    with patch("backtest.krx_supply_history.requests.post", return_value=_FakeResp(payload)) as mock_post:
        result = fetch_supply_for_date("20240105", cache_dir=cache_dir)
        assert result["005930"] == {"frgn": 1234567.0, "org": -500000.0}
        assert result["000660"] == {"frgn": 0.0, "org": 600000000.0}
        assert mock_post.call_count == 1

        # Verify HTTP call shape: URL and POST body
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
        data_body = call_args[1]["data"]
        assert "bld=dbms/MDC/STAT/standard/MDCSTAT02023" in data_body
        assert "mktId=ALL" in data_body
        assert "trdDd=20240105" in data_body

    # second call must hit the cache, not the network again
    with patch("backtest.krx_supply_history.requests.post", side_effect=AssertionError("should not be called")):
        cached = fetch_supply_for_date("20240105", cache_dir=cache_dir)
        assert cached["005930"]["frgn"] == 1234567.0

    assert (cache_dir / "20240105.json").exists()


def test_fetch_supply_for_date_fallback_to_outblock_1(tmp_path):
    """Test that OutBlock_1 is used when output key is missing."""
    payload = {
        # Note: no "output" key, only OutBlock_1
        "OutBlock_1": [
            {"ISU_SRT_CD": "005930", "FRGN_NETBUY_TRDVAL": "999,999", "ORG_NETBUY_TRDVAL": "111,111"},
        ]
    }
    cache_dir = tmp_path / "krx_supply"
    with patch("backtest.krx_supply_history.requests.post", return_value=_FakeResp(payload)):
        result = fetch_supply_for_date("20240106", cache_dir=cache_dir)
        assert result["005930"] == {"frgn": 999999.0, "org": 111111.0}

    assert (cache_dir / "20240106.json").exists()


def test_fetch_supply_for_date_exception_returns_empty_dict(tmp_path):
    """Test that network errors/timeouts return empty dict without caching."""
    cache_dir = tmp_path / "krx_supply"

    # Simulate network timeout
    with patch("backtest.krx_supply_history.requests.post", side_effect=requests.exceptions.Timeout("timeout")):
        result = fetch_supply_for_date("20240107", cache_dir=cache_dir)
        assert result == {}

    # Verify cache file was NOT created (so future retries will try the network again)
    assert not (cache_dir / "20240107.json").exists()


def test_fetch_supply_for_date_exception_from_parse_returns_empty_dict(tmp_path):
    """Test that JSON parse errors return empty dict without caching."""
    cache_dir = tmp_path / "krx_supply"

    # Simulate a response that fails to parse as JSON
    with patch("backtest.krx_supply_history.requests.post") as mock_post:
        mock_resp = _FakeResp({})
        # Make json() raise an exception
        mock_resp.json = lambda: (_ for _ in ()).throw(ValueError("Invalid JSON"))
        mock_post.return_value = mock_resp

        result = fetch_supply_for_date("20240108", cache_dir=cache_dir)
        assert result == {}

    # Verify cache file was NOT created
    assert not (cache_dir / "20240108.json").exists()


def test_fetch_supply_for_date_empty_output_does_not_fallback(tmp_path):
    """Test that output=[] does not fall back to OutBlock_1 (JS truthiness semantics).

    In JS, [] is truthy, so [] || OutBlock_1 returns [].
    In Python (without fix), [] is falsy, so [] or OutBlock_1 returns OutBlock_1.
    This test ensures Python now matches JS: presence checking via is not None.
    """
    payload = {
        "output": [],  # Empty but present
        "OutBlock_1": [
            {"ISU_SRT_CD": "005930", "FRGN_NETBUY_TRDVAL": "100", "ORG_NETBUY_TRDVAL": "200"},
        ]
    }
    cache_dir = tmp_path / "krx_supply"
    with patch("backtest.krx_supply_history.requests.post", return_value=_FakeResp(payload)):
        result = fetch_supply_for_date("20240109", cache_dir=cache_dir)
        # Should return empty dict (from empty output), not fallback to OutBlock_1
        assert result == {}
        # Cache should still be written (empty result is valid)
        assert (cache_dir / "20240109.json").exists()
        assert json.loads((cache_dir / "20240109.json").read_text()) == {}


def test_fetch_supply_for_date_malformed_row_returns_empty_dict(tmp_path):
    """Test that malformed rows during processing return empty dict without caching.

    Exception scope should wrap the entire row-processing loop, not just the network call.
    """
    cache_dir = tmp_path / "krx_supply"

    # Mock a response where rows is not a list (will fail when calling .get() on non-dict).
    with patch("backtest.krx_supply_history.requests.post") as mock_post:
        mock_resp = _FakeResp({})
        # Return a response where output is a string, not a list.
        # Iterating over it yields characters, and calling .get() on a char raises AttributeError.
        mock_resp.json = lambda: {"output": "not-a-list"}
        mock_post.return_value = mock_resp

        result = fetch_supply_for_date("20240110", cache_dir=cache_dir)
        # Should return empty dict (exception during row-loop .get() call)
        assert result == {}

    # Verify cache file was NOT created (exception = no cache)
    assert not (cache_dir / "20240110.json").exists()

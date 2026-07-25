import json
from pathlib import Path
from unittest.mock import patch

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

    # second call must hit the cache, not the network again
    with patch("backtest.krx_supply_history.requests.post", side_effect=AssertionError("should not be called")):
        cached = fetch_supply_for_date("20240105", cache_dir=cache_dir)
        assert cached["005930"]["frgn"] == 1234567.0

    assert (cache_dir / "20240105.json").exists()

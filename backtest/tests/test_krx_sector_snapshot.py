import json

from backtest.krx_sector_snapshot import fetch_sector_snapshot


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_sector_snapshot_parses_code_and_truncates_sector_to_6_chars(monkeypatch, tmp_path):
    payload = {
        "output": [
            {"ISU_SRT_CD": "000001", "IDX_IND_NM": "ABCDEFGHIJ"},
            {"ISU_SRT_CD": "000002", "SECT_TP_NM": "XYZW12"},
            {"ISU_SRT_CD": "", "IDX_IND_NM": "IGNORED_NO_CODE"},
        ]
    }
    monkeypatch.setattr(
        "backtest.krx_sector_snapshot.requests.post",
        lambda *a, **k: _FakeResp(payload),
    )
    result = fetch_sector_snapshot("20240102", cache_dir=tmp_path, min_sleep_s=0)
    assert result == {"000001": "ABCDEF", "000002": "XYZW12"}


def test_fetch_sector_snapshot_returns_empty_dict_on_request_failure(monkeypatch, tmp_path):
    def raise_error(*a, **k):
        raise Exception("boom")

    monkeypatch.setattr("backtest.krx_sector_snapshot.requests.post", raise_error)
    result = fetch_sector_snapshot("20240102", cache_dir=tmp_path, min_sleep_s=0)
    assert result == {}


def test_fetch_sector_snapshot_uses_disk_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "20240102.json"
    cache_path.write_text(json.dumps({"000009": "CACHED"}), encoding="utf-8")

    def fail_if_called(*a, **k):
        raise AssertionError("should not hit network when cache exists")

    monkeypatch.setattr("backtest.krx_sector_snapshot.requests.post", fail_if_called)
    result = fetch_sector_snapshot("20240102", cache_dir=tmp_path, min_sleep_s=0)
    assert result == {"000009": "CACHED"}

import json

from backtest.krx_sector_snapshot import fetch_sector_snapshot


class _FakeResp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


_LIST_HTML = """
<a href="/sise/sise_group_detail.naver?type=upjong&no=274">A</a>
<a href="/sise/sise_group_detail.naver?type=upjong&no=275">B</a>
"""


def _detail_html(codes):
    # Each code appears twice in the real page; dedupe while preserving order.
    parts = []
    for c in codes:
        parts.append(f'<a href="/item/main.naver?code={c}">x</a>')
        parts.append(f'<a href="/item/board.naver?code={c}">y</a>')
    return "\n".join(parts)


def _fake_get_factory(list_html, detail_by_no):
    def fake_get(url, headers=None, **kwargs):
        if "sise_group.naver" in url and "no=" not in url:
            return _FakeResp(list_html)
        for no, html in detail_by_no.items():
            if f"no={no}" in url:
                return _FakeResp(html)
        return _FakeResp("")

    return fake_get


def test_fetch_sector_snapshot_parses_groups_and_builds_code_to_group_mapping(monkeypatch, tmp_path):
    detail_by_no = {
        "274": _detail_html(["000001", "000002"]),
        "275": _detail_html(["033780"]),
    }
    monkeypatch.setattr(
        "backtest.krx_sector_snapshot.requests.get",
        _fake_get_factory(_LIST_HTML, detail_by_no),
    )
    result = fetch_sector_snapshot("20240102", cache_dir=tmp_path, min_sleep_s=0)
    assert result == {"000001": "274", "000002": "274", "033780": "275"}


def test_fetch_sector_snapshot_zero_groups_parsed_does_not_cache(monkeypatch, tmp_path):
    """If the list page yields zero group links (regex/markup mismatch, layout change,
    soft anti-bot response, ...), that's a failure, not "no sectors exist" - must not
    write an empty {} to the cache, so a later retry can still succeed."""
    monkeypatch.setattr(
        "backtest.krx_sector_snapshot.requests.get",
        _fake_get_factory("<html>no group links here</html>", {}),
    )
    result = fetch_sector_snapshot("20240105", cache_dir=tmp_path, min_sleep_s=0)
    assert result == {}
    assert not (tmp_path / "20240105.json").exists()


def test_fetch_sector_snapshot_returns_empty_dict_on_request_failure(monkeypatch, tmp_path):
    def raise_error(*a, **k):
        raise Exception("boom")

    monkeypatch.setattr("backtest.krx_sector_snapshot.requests.get", raise_error)
    result = fetch_sector_snapshot("20240102", cache_dir=tmp_path, min_sleep_s=0)
    assert result == {}


def test_fetch_sector_snapshot_uses_disk_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "20240102.json"
    cache_path.write_text(json.dumps({"000009": "999"}), encoding="utf-8")

    def fail_if_called(*a, **k):
        raise AssertionError("should not hit network when cache exists")

    monkeypatch.setattr("backtest.krx_sector_snapshot.requests.get", fail_if_called)
    result = fetch_sector_snapshot("20240102", cache_dir=tmp_path, min_sleep_s=0)
    assert result == {"000009": "999"}


def test_fetch_sector_snapshot_corrupted_cache_falls_back_to_network(monkeypatch, tmp_path):
    """A truncated/corrupted cache file must be treated as a cache miss and fall through
    to re-fetch from the network."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    corrupted_path = tmp_path / "20240104.json"
    corrupted_path.write_text('{"000001": "SECTOR', encoding="utf-8")  # truncated JSON

    detail_by_no = {"274": _detail_html(["000001"])}
    monkeypatch.setattr(
        "backtest.krx_sector_snapshot.requests.get",
        _fake_get_factory(_LIST_HTML, detail_by_no),
    )
    result = fetch_sector_snapshot("20240104", cache_dir=tmp_path, min_sleep_s=0)
    # Falls through to network fetch instead of raising.
    assert result == {"000001": "274"}

    # Self-heals: the corrupted cache file is overwritten with valid JSON.
    assert json.loads(corrupted_path.read_text(encoding="utf-8"))["000001"] == "274"

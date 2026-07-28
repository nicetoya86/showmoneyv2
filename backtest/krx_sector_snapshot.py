"""
Stock-code -> sector-classification snapshot, used by
backtest/candidate_signals.py's sector-relative-strength signal.

Sourced from Naver Finance's industry-group pages (finance.naver.com/sise/sise_group*),
not data.krx.co.kr: the KRX bldAttendant/getJsonData.cmd JSON API (used originally, and
still used by backtest/krx_supply_history.py) is gated behind an anti-bot/session-registration
flow that this environment's plain requests.post cannot pass (HTTP 400 "LOGOUT" even with
production's exact headers). Naver's HTML pages require no session dance - plain GETs work.

Because Naver's grouping has no historical `trdDd`/date parameter, this is a single current
snapshot, not true point-in-time history - `trd_dd` is kept only as the cache filename key
(same as before), so callers/signature are unchanged. This realizes, rather than introduces,
the "sector classification is a single static snapshot" limitation already accepted in the
design doc.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict

import requests

_LIST_URL = "https://finance.naver.com/sise/sise_group.naver?type=upjong"
_DETAIL_URL = "https://finance.naver.com/sise/sise_group_detail.naver?type=upjong&no={no}"
_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://finance.naver.com/",
    "Accept": "text/html",
    "Accept-Charset": "utf-8",
}
_GROUP_NO_RE = re.compile(r"sise_group_detail\.naver\?type=upjong&no=(\d+)")
_CODE_RE = re.compile(r"code=(\d{6})")


def fetch_sector_snapshot(
    trd_dd: str,
    *,
    cache_dir: Path = Path("backtest/cache/krx_sector"),
    min_sleep_s: float = 0.2,
) -> Dict[str, str]:
    """Stock code -> Naver industry-group number (as a string), e.g. "275".

    Not a true point-in-time historical snapshot: Naver's industry grouping has no
    date parameter, so this is always the *current* group snapshot, merely cached
    under the given `trd_dd` key (same cache-key contract as before).
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{trd_dd}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass

    try:
        resp = requests.get(_LIST_URL, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        group_nos = _GROUP_NO_RE.findall(resp.text)
        if min_sleep_s > 0:
            time.sleep(min_sleep_s)

        result: Dict[str, str] = {}
        for no in group_nos:
            detail_resp = requests.get(_DETAIL_URL.format(no=no), headers=_HEADERS, timeout=20)
            detail_resp.raise_for_status()
            codes = dict.fromkeys(_CODE_RE.findall(detail_resp.text))
            for code in codes:
                result[code] = no
            if min_sleep_s > 0:
                time.sleep(min_sleep_s)

        try:
            cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        return result
    except Exception:
        return {}

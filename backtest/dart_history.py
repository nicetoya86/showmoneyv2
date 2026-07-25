from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List

import requests

_URL = "https://opendart.fss.or.kr/api/list.json"


def fetch_disclosures_for_date(
    trd_dd: str,
    *,
    api_key: str,
    cache_dir: Path = Path("backtest/cache/dart"),
    min_sleep_s: float = 0.2,
) -> Dict[str, List[str]]:
    """Disclosure report names per stock code for one calendar day (market-wide, 1 call)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{trd_dd}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    try:
        params = {"crtfc_key": api_key, "bgn_de": trd_dd, "end_de": trd_dd, "page_no": 1, "page_count": 100}
        resp = requests.get(_URL, params=params, timeout=20)
        resp.raise_for_status()
        resp_data = resp.json() or {}
        items = resp_data.get("list") or []

        result: Dict[str, List[str]] = {}
        for item in items:
            code = str(item.get("stock_code") or "").strip()
            if not code:
                continue
            result.setdefault(code, []).append(str(item.get("report_nm") or "")[:40])

        # Try to cache the result, but don't fail if cache write fails.
        # Cache-write failure should not prevent returning successfully-fetched data.
        try:
            cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        except Exception:
            # Cache write failed, but data is valid; let caller get the result anyway.
            pass

        if min_sleep_s > 0:
            time.sleep(min_sleep_s)
        return result
    except Exception:
        # On network error, timeout, parse failure, or row-processing failure:
        # return empty dict without caching, allowing future retries.
        return {}

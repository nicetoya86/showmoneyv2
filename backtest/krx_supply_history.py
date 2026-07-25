from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict

import requests

_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://data.krx.co.kr",
    "Referer": "https://data.krx.co.kr/",
    "User-Agent": "Mozilla/5.0",
}


def _to_num(v) -> float:
    try:
        return float(str(v or "0").replace(",", ""))
    except ValueError:
        return 0.0


def fetch_supply_for_date(
    trd_dd: str,
    *,
    cache_dir: Path = Path("backtest/cache/krx_supply"),
    min_sleep_s: float = 0.2,
) -> Dict[str, Dict[str, float]]:
    """Foreign/institutional net-buy value per stock code for one KRX trading day (market-wide, 1 call)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{trd_dd}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    try:
        body = f"bld=dbms/MDC/STAT/standard/MDCSTAT02023&mktId=ALL&trdDd={trd_dd}&share=1&money=1&csvxls_isNo=false"
        resp = requests.post(_URL, headers=_HEADERS, data=body, timeout=20)
        resp.raise_for_status()
        resp_data = resp.json() or {}
        # Fall back to OutBlock_1 if output is missing/empty (matches production behavior)
        rows = resp_data.get("output") or resp_data.get("OutBlock_1") or []
    except Exception:
        # On network error, timeout, or parse failure: return empty dict without caching
        # This allows future retries for the same date rather than permanently caching failure
        return {}

    result: Dict[str, Dict[str, float]] = {}
    for row in rows:
        code = str(row.get("ISU_SRT_CD") or "").strip()
        if not code:
            continue
        result[code] = {
            "frgn": _to_num(row.get("FRGN_NETBUY_TRDVAL")),
            "org": _to_num(row.get("ORG_NETBUY_TRDVAL")),
        }

    cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    if min_sleep_s > 0:
        time.sleep(min_sleep_s)
    return result

"""
One-time KRX stock-code -> sector-classification snapshot, used by
backtest/candidate_signals.py's sector-relative-strength signal. Mirrors
backtest/krx_supply_history.py's request/cache/error-handling style exactly, and mirrors the
sector-code parsing already dead-code in production (src/swing-scanner.src.js:1017-1019:
`IDX_IND_NM || SECT_TP_NM`, first 6 characters).
"""
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


def fetch_sector_snapshot(
    trd_dd: str,
    *,
    cache_dir: Path = Path("backtest/cache/krx_sector"),
    min_sleep_s: float = 0.2,
) -> Dict[str, str]:
    """Stock code -> 6-char sector code, for one KRX trading day (market-wide, 1 call)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{trd_dd}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass

    try:
        body = f"bld=dbms/MDC/STAT/standard/MDCSTAT01501&mktId=ALL&trdDd={trd_dd}&share=1&money=1&csvxls_isNo=false"
        resp = requests.post(_URL, headers=_HEADERS, data=body, timeout=20)
        resp.raise_for_status()
        resp_data = resp.json() or {}
        rows = resp_data.get("output")
        if rows is None:
            rows = resp_data.get("OutBlock_1")
        if rows is None:
            rows = []

        result: Dict[str, str] = {}
        for row in rows:
            code = str(row.get("ISU_SRT_CD") or "").strip()
            if not code:
                continue
            sector = str(row.get("IDX_IND_NM") or row.get("SECT_TP_NM") or "").strip()[:6]
            if sector:
                result[code] = sector

        try:
            cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        if min_sleep_s > 0:
            time.sleep(min_sleep_s)
        return result
    except Exception:
        return {}

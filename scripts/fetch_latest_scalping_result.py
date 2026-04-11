"""
가장 최근 n8n Execution 중 'Scalping Scanner' 노드 출력값을 찾아 요약 출력합니다.

사용 방법
1) (장중) n8n에서 Scalping Scanner를 Execute Node로 실행 (입력: {"debugMode": true, "forceTest": false})
2) 터미널에서:
   python scripts/fetch_latest_scalping_result.py
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


WORKFLOW_ID = "ScHaeFdneOoH1ZNZ"
N8N_BASE_URL = "https://fastlane12.app.n8n.cloud/api/v1"
NODE = "Scalping Scanner"


def load_api_key() -> str:
    text = Path("export_n8n_executions.py").read_text(encoding="utf-8")
    m = re.search(r'^\s*API_KEY\s*=\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
    if not m:
        raise RuntimeError("API_KEY not found in export_n8n_executions.py")
    return m.group(1)


def headers(api_key: str) -> Dict[str, str]:
    return {"X-N8N-API-KEY": api_key, "Accept": "application/json"}


def iso_to_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def get_executions(api_key: str, limit: int = 120) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    while len(out) < limit:
        batch = min(100, limit - len(out))
        params: Dict[str, Any] = {"workflowId": WORKFLOW_ID, "limit": batch}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(f"{N8N_BASE_URL}/executions", headers=headers(api_key), params=params, timeout=60)
        r.raise_for_status()
        j = r.json() or {}
        data = j.get("data", []) or []
        if not data:
            break
        out.extend(data)
        cursor = j.get("nextCursor")
        if not cursor:
            break
    return out


def get_execution_detail(api_key: str, execution_id: str) -> Dict[str, Any]:
    r = requests.get(
        f"{N8N_BASE_URL}/executions/{execution_id}",
        headers=headers(api_key),
        params={"includeData": "true"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def pick_node_output(detail: Dict[str, Any], node_name: str) -> Optional[Dict[str, Any]]:
    run_data = ((detail.get("data") or {}).get("resultData") or {}).get("runData") or {}
    steps = run_data.get(node_name)
    if not isinstance(steps, list) or not steps:
        return None
    last = steps[-1] or {}
    main = ((last.get("data") or {}).get("main") or [])
    if not main or not isinstance(main[0], list) or not main[0]:
        return None
    item0 = main[0][0]
    if isinstance(item0, dict):
        j = item0.get("json")
        return j if isinstance(j, dict) else None
    return None


def main() -> None:
    api_key = load_api_key()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=2)

    executions = [
        ex
        for ex in get_executions(api_key, limit=200)
        if (iso_to_dt(ex.get("startedAt") or ex.get("createdAt")) or datetime(1970, 1, 1, tzinfo=timezone.utc)) >= cutoff
    ]

    for ex in executions:
        ex_id = str(ex.get("id"))
        detail = get_execution_detail(api_key, ex_id)
        out = pick_node_output(detail, NODE)
        if out is None:
            continue

        Path("debug_dump").mkdir(exist_ok=True)
        Path(f"debug_dump/latest_scalping_{ex_id}.json").write_text(
            json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print("FOUND execution:", ex_id, "mode:", detail.get("mode"), "status:", detail.get("status"))
        # 핵심만 요약
        keys = [
            "skipped",
            "reason",
            "ok",
            "totalUniverse",
            "candidates",
            "sent",
            "krxUniverseSource",
            "krxUniverseError",
            "excludedRisk",
            "riskCacheAt",
        ]
        summary = {k: out.get(k) for k in keys if k in out}
        print("output_summary:", json.dumps(summary, ensure_ascii=False))
        return

    print("NOT FOUND: recent execution with Scalping Scanner output. (먼저 n8n에서 Execute Node로 실행해 주세요.)")


if __name__ == "__main__":
    main()






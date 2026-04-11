"""
사용자가 n8n에서 'Daily Healthcheck'를 수동 실행한 뒤,
새로운 execution을 자동으로 감지하고 결과(krxStatus/krxCount 등)를 출력한다.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set

import requests


WORKFLOW_ID = "ScHaeFdneOoH1ZNZ"
N8N_BASE_URL = "https://fastlane12.app.n8n.cloud/api/v1"
TARGET_NODE = "Daily Healthcheck"


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


def get_executions(api_key: str, limit: int = 30) -> Dict[str, Any]:
    r = requests.get(
        f"{N8N_BASE_URL}/executions",
        headers=headers(api_key),
        params={"workflowId": WORKFLOW_ID, "limit": int(limit)},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


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
    start = datetime.now(timezone.utc)
    seen: Set[str] = set()

    print("Polling for a NEW execution containing:", TARGET_NODE)
    print("Start time (UTC):", start.isoformat())

    for _ in range(40):  # ~80 seconds
        data = get_executions(api_key, limit=30)
        exs = data.get("data", []) or []
        for ex in exs:
            ex_id = str(ex.get("id"))
            if ex_id in seen:
                continue
            seen.add(ex_id)

            started = iso_to_dt(ex.get("startedAt") or ex.get("createdAt"))
            if not started or started < start:
                continue

            # 후보: 막 실행된 execution만 detail 조회
            detail = get_execution_detail(api_key, ex_id)
            out = pick_node_output(detail, TARGET_NODE)
            if out is None:
                continue

            Path("debug_dump").mkdir(exist_ok=True)
            Path(f"debug_dump/manual_healthcheck_{ex_id}.json").write_text(
                json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print("\nFOUND execution:", ex_id)
            print("mode:", detail.get("mode"), "status:", detail.get("status"))
            print("startedAt:", detail.get("startedAt"))
            print("output:", json.dumps(out, ensure_ascii=False))
            return

        time.sleep(2)

    print("TIMEOUT: no new healthcheck execution found. Run the node again and retry.")


if __name__ == "__main__":
    main()






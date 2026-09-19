"""
라이브 n8n 워크플로우(ScHaeFdneOoH1ZNZ)에 "12:30 KST 장중 포지션 체크" 트리거 신규 추가.

배경: 기존 Daily Position Monitor는 16:00(장 마감 후) 1일 1회만 실행돼, 발송 당일
장중에 급등 후 반납하는 케이스(원익/흥구석유/금강철강 09-01~09-04)를 하루 늦게 잡는다.
같은 "Daily Position Monitor" 노드에 12:30 트리거를 하나 더 연결해 정오에 한 번 더
체크한다 (코드 쪽은 실행 시각<15시면 당일 분봉으로 장중 스냅샷을 만들어 같은 트레일링
로직을 태우도록 src/daily-position-monitor.src.js에 이미 반영/빌드 완료).

적용 내용
- 신규 노드 "Daily Position Monitor Trigger (12:30 KST)" (scheduleTrigger, cron `30 12 * * 1-5`)
  추가, 기존 16:00 트리거와 동일하게 "Daily Position Monitor" 노드로 연결.
- Daily Position Monitor 노드의 functionCode를 최신 Daily_Position_Monitor.js로 교체
  (장중 스냅샷 분기 포함 — 이 안에는 트레일링 본전-클램프 수정도 같이 들어있음. 두 수정이
  같은 파일이라 분리 배포 불가 — 이 스크립트를 적용하면 클램프 수정도 함께 반영됨).

주의:
- 여기서는 Swing Scanner(과열 선반영 차단 게이트)는 건드리지 않는다 — 그건 별도 결정 사항.
- API_KEY는 export_n8n_executions.py에서 읽는다.
- 실행 전 현재 라이브 워크플로우 JSON을 타임스탬프 백업 파일로 저장한다.
- PATCH가 아닌 PUT 사용.
- 기본은 DRY RUN. --apply 없이는 실제 반영 안 됨.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests

WORKFLOW_ID = "ScHaeFdneOoH1ZNZ"
N8N_BASE_URL = "https://fastlane12.app.n8n.cloud/api/v1"
ROOT = Path(r"D:\vibecording\showmoneyv2")

TARGET_NODE_NAME = "Daily Position Monitor"
EOD_TRIGGER_NAME = "Daily Position Monitor Trigger (16:00 KST)"
NEW_TRIGGER_NAME = "Daily Position Monitor Trigger (12:30 KST)"
CODE_FILE = "Daily_Position_Monitor.js"


def _load_api_key() -> str:
    text = (ROOT / "export_n8n_executions.py").read_text(encoding="utf-8")
    m = re.search(r'^\s*API_KEY\s*=\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
    if not m:
        raise RuntimeError("API_KEY를 export_n8n_executions.py에서 찾지 못했습니다.")
    return m.group(1)


def _headers(api_key: str) -> Dict[str, str]:
    return {"X-N8N-API-KEY": api_key, "Accept": "application/json"}


def _get_workflow(api_key: str) -> Dict[str, Any]:
    r = requests.get(f"{N8N_BASE_URL}/workflows/{WORKFLOW_ID}", headers=_headers(api_key), timeout=60)
    r.raise_for_status()
    return r.json()


def _update_workflow(api_key: str, workflow: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "name": workflow.get("name"),
        "nodes": workflow.get("nodes"),
        "connections": workflow.get("connections"),
        "settings": workflow.get("settings"),
    }
    r = requests.put(
        f"{N8N_BASE_URL}/workflows/{WORKFLOW_ID}",
        headers={**_headers(api_key), "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=60,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"n8n API update failed: http={r.status_code} body={r.text[:1200]}")
    return r.json()


def main() -> int:
    dry_run = "--apply" not in sys.argv

    api_key = _load_api_key()
    workflow = _get_workflow(api_key)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = ROOT / ".claude" / f"live_workflow_backup_{ts}.json"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"backed up live workflow to {backup_path}")

    nodes = workflow["nodes"]
    connections = workflow["connections"]

    target_node = next((n for n in nodes if n.get("name") == TARGET_NODE_NAME), None)
    if target_node is None:
        raise RuntimeError(f"'{TARGET_NODE_NAME}' 노드를 찾지 못했습니다.")

    # 1) functionCode 교체 (장중 스냅샷 분기 + 트레일링 클램프 포함된 최신 빌드)
    new_code = (ROOT / CODE_FILE).read_text(encoding="utf-8")
    old_len = len(target_node["parameters"]["functionCode"])
    target_node["parameters"]["functionCode"] = new_code
    print(f"{TARGET_NODE_NAME} functionCode replaced ({old_len} -> {len(new_code)} chars)")

    # 2) 12:30 트리거 노드 추가 (이미 있으면 스킵 — 재실행 안전)
    existing_new_trigger = next((n for n in nodes if n.get("name") == NEW_TRIGGER_NAME), None)
    if existing_new_trigger is not None:
        print(f"'{NEW_TRIGGER_NAME}' 이미 존재 — 노드 추가 스킵")
    else:
        eod_trigger = next((n for n in nodes if n.get("name") == EOD_TRIGGER_NAME), None)
        if eod_trigger is None:
            raise RuntimeError(f"기존 '{EOD_TRIGGER_NAME}' 노드를 찾지 못해 position/typeVersion을 참고할 수 없습니다.")
        base_pos = eod_trigger.get("position", [0, 0])
        new_trigger = {
            "parameters": {
                "rule": {
                    "interval": [
                        {"field": "cronExpression", "expression": "30 12 * * 1-5"}
                    ]
                }
            },
            "id": str(uuid.uuid4()),
            "name": NEW_TRIGGER_NAME,
            "type": eod_trigger.get("type", "n8n-nodes-base.scheduleTrigger"),
            "typeVersion": eod_trigger.get("typeVersion", 1.2),
            "position": [base_pos[0], base_pos[1] - 100],
        }
        nodes.append(new_trigger)
        print(f"'{NEW_TRIGGER_NAME}' 노드 추가 (cron: 30 12 * * 1-5)")

        # 3) 연결 추가: 새 트리거 -> Daily Position Monitor (기존 16:00 트리거와 동일한 연결 형태)
        connections[NEW_TRIGGER_NAME] = {
            "main": [[{"node": TARGET_NODE_NAME, "type": "main", "index": 0}]]
        }
        print(f"connections['{NEW_TRIGGER_NAME}'] -> '{TARGET_NODE_NAME}' 추가")

    if dry_run:
        print("DRY RUN - no PUT sent. Re-run with --apply to publish.")
        return 0

    result = _update_workflow(api_key, workflow)
    print(f"PUT applied. versionId={result.get('versionId')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
라이브 n8n 워크플로우(ScHaeFdneOoH1ZNZ)에 두 변경사항을 한 번에 반영하는 배포 스크립트.

적용 내용
- Daily Position Monitor: 신규 노드 2개 추가 (매 거래일 16:00 KST 트리거 + 보유종목
  재분석/급락경고 함수). docs/superpowers/plans/2026-08-15-position-monitor-shock-alert.md 참고.
- Swing Scanner: 기존 노드의 functionCode만 교체 — 주간 발송 한도(15건, 값 변경 없음) 도달 시
  1회성 안내 알림 추가. docs/superpowers/plans/2026-08-16-swing-scanner-weekly-cap-restore-plan.md 참고.

주의:
- 이 스크립트는 레포의 export_n8n_executions.py 에 있는 API_KEY를 읽어 사용합니다
  (메인 체크아웃, 즉 이 워크트리 밖에 있음 — 워크트리엔 시크릿을 복사하지 않음).
- 실행 전 현재 라이브 워크플로우 JSON을 타임스탬프 백업 파일로 저장합니다.
- PATCH가 아닌 PUT을 사용합니다 (이 n8n Cloud 인스턴스는 PATCH가 405).
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
MAIN_CHECKOUT = Path(r"D:\vibecording\showmoneyv2")
WORKTREE = Path(r"D:\vibecording\showmoneyv2\.claude\worktrees\position-monitor-shock-alert")


def _load_api_key() -> str:
    text = (MAIN_CHECKOUT / "export_n8n_executions.py").read_text(encoding="utf-8")
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
    backup_path = WORKTREE / ".superpowers" / "sdd" / f"live_workflow_backup_{ts}.json"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"backed up live workflow to {backup_path}")

    nodes = workflow["nodes"]
    connections = workflow["connections"]

    # ===== 1. Swing Scanner: functionCode 교체 =====
    swing_code = (WORKTREE / "swing_scanner_code.js").read_text(encoding="utf-8")
    swing_node = next((n for n in nodes if n.get("name") == "Swing Scanner"), None)
    if swing_node is None:
        raise RuntimeError("live workflow에서 'Swing Scanner' 노드를 찾지 못했습니다.")
    old_len = len(swing_node["parameters"]["functionCode"])
    swing_node["parameters"]["functionCode"] = swing_code
    print(f"Swing Scanner functionCode replaced ({old_len} -> {len(swing_code)} chars)")

    # ===== 2. Daily Position Monitor: 신규 노드 2개 추가 =====
    if any(n.get("name") == "Daily Position Monitor" for n in nodes):
        print("Daily Position Monitor node already present - skipping node add (idempotent re-run)")
    else:
        monitor_code = (WORKTREE / "Daily_Position_Monitor.js").read_text(encoding="utf-8")
        max_y = max((n.get("position", [0, 0])[1] for n in nodes), default=0)
        new_y = max_y + 240

        trigger_id = str(uuid.uuid4())
        function_id = str(uuid.uuid4())

        trigger_node = {
            "parameters": {
                "rule": {"interval": [{"field": "cronExpression", "expression": "0 16 * * 1-5"}]}
            },
            "id": trigger_id,
            "name": "Daily Position Monitor Trigger (16:00 KST)",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, new_y],
        }
        function_node = {
            "parameters": {"functionCode": monitor_code},
            "id": function_id,
            "name": "Daily Position Monitor",
            "type": "n8n-nodes-base.function",
            "typeVersion": 1,
            "position": [340, new_y],
        }
        nodes.append(trigger_node)
        nodes.append(function_node)
        connections["Daily Position Monitor Trigger (16:00 KST)"] = {
            "main": [[{"node": "Daily Position Monitor", "type": "main", "index": 0}]]
        }
        print(f"Daily Position Monitor trigger+function nodes added at y={new_y}")

    if dry_run:
        print("DRY RUN - no PUT sent. Re-run with --apply to publish.")
        return 0

    result = _update_workflow(api_key, workflow)
    print(f"PUT applied. versionId={result.get('versionId')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

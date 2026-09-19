"""
라이브 n8n 워크플로우(ScHaeFdneOoH1ZNZ)에 "Daily Position Monitor" 장중 체크 트리거를
4개 추가(10:00 / 11:00 / 13:30 / 14:30 KST).

배경: 09-19 주간 리포트에서 최고 +13~41% 찍고 손절가로 확정된 종목이 다수 확인됨
(한국비엔씨 최고+13.4%→확정-7.4%, 빛샘전자 최고+41.1%→확정-5.2% 등). 트레일링 스탑
로직(lib/trailingStop.js) 자체는 09-13에 이미 본전-플로어를 넣어 문제 없음 — 원인은
체크 빈도: 기존 트리거가 12:30/16:00 하루 2번뿐이라 그 사이 3.5시간 동안 급등 후
반납이 일어나면 갱신된(올라간) 손절가가 반영되기 전에 옛 손절가로 이미 손절 처리됨.
같은 "Daily Position Monitor" 노드에 10:00/11:00/13:30/14:30 트리거를 추가로 연결해
블라인드 구간을 최대 1.5시간으로 좁힌다.

코드 쪽은 이미 실행 시각<15시면 당일 분봉 스냅샷으로 트레일링을 태우도록 분기돼 있어
(src/daily-position-monitor.src.js isIntraday) 함수 코드 변경은 필요 없음 —
트리거 노드만 추가하면 된다.

적용 내용
- 신규 노드 4개(scheduleTrigger, cron `0 10 * * 1-5` / `0 11 * * 1-5` / `30 13 * * 1-5` /
  `30 14 * * 1-5`) 추가, 기존 12:30/16:00 트리거와 동일하게 "Daily Position Monitor" 노드로 연결.
- Daily Position Monitor 노드의 functionCode를 최신 Daily_Position_Monitor.js로 교체
  (재실행 안전 — 내용 동일해도 덮어씀).

주의:
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
REF_TRIGGER_NAME = "Daily Position Monitor Trigger (16:00 KST)"
CODE_FILE = "Daily_Position_Monitor.js"

NEW_TRIGGERS = [
    ("Daily Position Monitor Trigger (10:00 KST)", "0 10 * * 1-5"),
    ("Daily Position Monitor Trigger (11:00 KST)", "0 11 * * 1-5"),
    ("Daily Position Monitor Trigger (13:30 KST)", "30 13 * * 1-5"),
    ("Daily Position Monitor Trigger (14:30 KST)", "30 14 * * 1-5"),
]


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

    # 1) functionCode 교체 (최신 빌드로 갱신 — 재실행 안전)
    new_code = (ROOT / CODE_FILE).read_text(encoding="utf-8")
    old_len = len(target_node["parameters"]["functionCode"])
    target_node["parameters"]["functionCode"] = new_code
    print(f"{TARGET_NODE_NAME} functionCode replaced ({old_len} -> {len(new_code)} chars)")

    ref_trigger = next((n for n in nodes if n.get("name") == REF_TRIGGER_NAME), None)
    if ref_trigger is None:
        raise RuntimeError(f"기존 '{REF_TRIGGER_NAME}' 노드를 찾지 못해 position/typeVersion을 참고할 수 없습니다.")
    base_pos = ref_trigger.get("position", [0, 0])

    # 2) 신규 트리거 노드 추가 (이미 있으면 스킵 — 재실행 안전)
    for offset, (name, cron) in enumerate(NEW_TRIGGERS, start=1):
        existing = next((n for n in nodes if n.get("name") == name), None)
        if existing is not None:
            print(f"'{name}' 이미 존재 — 노드 추가 스킵")
            continue
        new_trigger = {
            "parameters": {
                "rule": {"interval": [{"field": "cronExpression", "expression": cron}]}
            },
            "id": str(uuid.uuid4()),
            "name": name,
            "type": ref_trigger.get("type", "n8n-nodes-base.scheduleTrigger"),
            "typeVersion": ref_trigger.get("typeVersion", 1.2),
            "position": [base_pos[0], base_pos[1] - 100 * (offset + 1)],
        }
        nodes.append(new_trigger)
        print(f"'{name}' 노드 추가 (cron: {cron})")

        connections[name] = {
            "main": [[{"node": TARGET_NODE_NAME, "type": "main", "index": 0}]]
        }
        print(f"connections['{name}'] -> '{TARGET_NODE_NAME}' 추가")

    if dry_run:
        print("DRY RUN - no PUT sent. Re-run with --apply to publish.")
        return 0

    result = _update_workflow(api_key, workflow)
    print(f"PUT applied. versionId={result.get('versionId')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

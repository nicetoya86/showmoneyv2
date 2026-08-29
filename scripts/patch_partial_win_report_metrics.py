"""
라이브 n8n 워크플로우(ScHaeFdneOoH1ZNZ)에 주간 리포트 승률/부분익절 분류 개선 반영.

적용 내용
- Weekly Reporter: 1차달성(partial_win)을 손절과 분리된 별도 섹션(🎯 부분익절)으로 유지하고
  목표달성률(완전 목표 완주만 인정) + 성공률(부분익절 포함, 보조 지표) 두 개를 함께 표시.
  부분익절/손절 라인에 실제 청산가 기준 확정 손익률(stopPct) 추가.
- Swing Scanner: 추천 저장 레코드에 patternType/signals(상위 3개) 추가 — 다음 리포트부터
  수익/손절 종목별 시그널 비교 가능.

주의:
- API_KEY는 이 레포에 이미 커밋돼 있는 export_n8n_executions.py에서 읽는다.
- 실행 전 현재 라이브 워크플로우 JSON을 타임스탬프 백업 파일로 저장한다.
- PATCH가 아닌 PUT을 사용한다 (이 n8n Cloud 인스턴스는 PATCH가 405).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests

WORKFLOW_ID = "ScHaeFdneOoH1ZNZ"
N8N_BASE_URL = "https://fastlane12.app.n8n.cloud/api/v1"
ROOT = Path(r"D:\vibecording\showmoneyv2")

NODE_FILE_MAP = {
    "Swing Scanner": "swing_scanner_code.js",
    "Weekly Reporter": "weekly_reporter_code.js",
}


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

    for node_name, file_name in NODE_FILE_MAP.items():
        node = next((n for n in nodes if n.get("name") == node_name), None)
        if node is None:
            raise RuntimeError(f"live workflow에서 '{node_name}' 노드를 찾지 못했습니다.")
        new_code = (ROOT / file_name).read_text(encoding="utf-8")
        old_len = len(node["parameters"]["functionCode"])
        node["parameters"]["functionCode"] = new_code
        print(f"{node_name} functionCode replaced ({old_len} -> {len(new_code)} chars)")

    if dry_run:
        print("DRY RUN - no PUT sent. Re-run with --apply to publish.")
        return 0

    result = _update_workflow(api_key, workflow)
    print(f"PUT applied. versionId={result.get('versionId')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

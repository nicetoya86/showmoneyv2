"""
라이브 n8n 워크플로우(ScHaeFdneOoH1ZNZ)의 Weekly Reporter 노드에 트레일링 본전-클램프만 반영.

배경: lib/trailingStop.js의 calcTrailingStop이 gain>=3% 티어에서 ATR-트레일이 본전 밑으로
못 내려가게 클램프됐다. Weekly Reporter는 이 함수를 그대로 인라인해서 손절일 재구성에 쓰므로,
Daily Position Monitor(실시간 갱신)와 Weekly Reporter(사후 재구성)가 서로 다른 트레일링
공식을 쓰면 리포트 판정이 실제 운영과 어긋난다 — 반드시 같이 배포해야 한다.

주의: Swing Scanner(과열 선반영 차단 게이트)는 이번 배포에서 제외 — 별도 결정 사항.
기본은 DRY RUN. --apply 없이는 반영 안 됨.
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
TARGET_NODE_NAME = "Weekly Reporter"
CODE_FILE = "weekly_reporter_code.js"


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

    node = next((n for n in workflow["nodes"] if n.get("name") == TARGET_NODE_NAME), None)
    if node is None:
        raise RuntimeError(f"'{TARGET_NODE_NAME}' 노드를 찾지 못했습니다.")

    new_code = (ROOT / CODE_FILE).read_text(encoding="utf-8")
    old_len = len(node["parameters"]["functionCode"])
    node["parameters"]["functionCode"] = new_code
    print(f"{TARGET_NODE_NAME} functionCode replaced ({old_len} -> {len(new_code)} chars)")

    if dry_run:
        print("DRY RUN - no PUT sent. Re-run with --apply to publish.")
        return 0

    result = _update_workflow(api_key, workflow)
    print(f"PUT applied. versionId={result.get('versionId')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

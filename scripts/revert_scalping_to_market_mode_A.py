"""
Scalping Scanner를 'A(오늘 장중 실행)' 기준으로 원복:
- forceRun(장외 강제 검증) 패치로 들어간 코드 제거
- 가장 안전한 방법: forceRun 적용 직전 백업 JSON에서 Scalping Scanner functionCode를 가져와
  현재 n8n 워크플로우에 그대로 덮어쓴다.

백업 파일:
- backups/n8n_workflow_ScHaeFdneOoH1ZNZ_20260105_161613_forceRun_before.json
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests


WORKFLOW_ID = "ScHaeFdneOoH1ZNZ"
N8N_BASE_URL = "https://fastlane12.app.n8n.cloud/api/v1"
BACKUP_PATH = Path("backups/n8n_workflow_ScHaeFdneOoH1ZNZ_20260105_161613_forceRun_before.json")

NODE_SCALPING = "Scalping Scanner"


def load_api_key() -> str:
    text = Path("export_n8n_executions.py").read_text(encoding="utf-8")
    m = re.search(r'^\s*API_KEY\s*=\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
    if not m:
        raise RuntimeError("API_KEY not found in export_n8n_executions.py")
    return m.group(1)


def headers(api_key: str) -> Dict[str, str]:
    return {"X-N8N-API-KEY": api_key, "Accept": "application/json"}


def get_workflow(api_key: str) -> Dict[str, Any]:
    r = requests.get(f"{N8N_BASE_URL}/workflows/{WORKFLOW_ID}", headers=headers(api_key), timeout=60)
    r.raise_for_status()
    return r.json()


def update_workflow(api_key: str, wf: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "name": wf.get("name"),
        "nodes": wf.get("nodes"),
        "connections": wf.get("connections"),
        "settings": wf.get("settings"),
    }
    r = requests.put(
        f"{N8N_BASE_URL}/workflows/{WORKFLOW_ID}",
        headers={**headers(api_key), "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=60,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"n8n API update failed: http={r.status_code} body={r.text[:1200]}")
    return r.json()


def find_node(nodes: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    for n in nodes:
        if n.get("name") == name:
            return n
    raise RuntimeError(f"Node not found: {name}")


def main() -> None:
    if not BACKUP_PATH.exists():
        raise RuntimeError(f"Backup not found: {BACKUP_PATH.as_posix()}")

    backup = json.loads(BACKUP_PATH.read_text(encoding="utf-8"))
    backup_nodes: List[Dict[str, Any]] = backup.get("nodes") or []
    backup_scalping = find_node(backup_nodes, NODE_SCALPING)
    backup_code = ((backup_scalping.get("parameters") or {}).get("functionCode")) or ""
    if not backup_code:
        raise RuntimeError("Backup scalping functionCode is empty")

    api_key = load_api_key()
    wf = get_workflow(api_key)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_revert_scalping_A_before.json").write_text(
        json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    nodes: List[Dict[str, Any]] = wf.get("nodes") or []
    scalping = find_node(nodes, NODE_SCALPING)
    scalping.setdefault("parameters", {})["functionCode"] = backup_code
    wf["nodes"] = nodes

    updated = update_workflow(api_key, wf)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_revert_scalping_A_after.json").write_text(
        json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("OK: reverted Scalping Scanner to market-mode(A).")


if __name__ == "__main__":
    main()






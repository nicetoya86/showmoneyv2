"""
상용 모드 전환:
- Scalping/Swing 자동 트리거 경로에서 debugMode를 강제로 true로 넣는 Set 노드를 OFF로 되돌림

현재 워크플로우 구조(요약)
- Cron Trigger -> "Scalping Config (테스트 모드)"(Set) -> "Scalping Scanner"
- Cron Trigger -> "Swing Config (테스트 모드)"(Set) -> "Swing Scanner"

상용 모드 목표
- debugMode: false
- forceTest: false

주의
- 이 스크립트는 n8n Cloud API(v1)로 워크플로우 JSON을 PUT 업데이트합니다.
- 실행 전/후 워크플로우 JSON을 backups/에 저장합니다.
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

NODE_SCALPING_SET = "Scalping Config (테스트 모드)"
NODE_SWING_SET = "Swing Config (테스트 모드)"
NODE_WEEKLY_SET = "Weekly Config (테스트 모드)"  # 보너스: 주간도 동일하게 끔(원치 않으면 건드리지 않아도 됨)


def _load_api_key() -> str:
    text = Path("export_n8n_executions.py").read_text(encoding="utf-8")
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


def _update_workflow(api_key: str, wf: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "name": wf.get("name"),
        "nodes": wf.get("nodes"),
        "connections": wf.get("connections"),
        "settings": wf.get("settings"),
    }
    r = requests.put(
        f"{N8N_BASE_URL}/workflows/{WORKFLOW_ID}",
        headers={**_headers(api_key), "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=60,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"n8n API update failed: http={r.status_code} body={r.text[:2000]}")
    return r.json()


def _find_node(nodes: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    for n in nodes:
        if n.get("name") == name:
            return n
    raise RuntimeError(f"노드를 찾지 못했습니다: {name}")


def _set_production_flags_on_set_node(node: Dict[str, Any]) -> bool:
    """
    n8n Set 노드 parameters 구조:
      parameters.values.boolean = [{"name":"forceTest"}, {"name":"debugMode","value":true}, ...]
    여기서 forceTest/debugMode를 false로 강제 설정.
    """
    params = node.get("parameters") or {}
    values = params.get("values") or {}
    booleans = values.get("boolean")
    if not isinstance(booleans, list):
        return False

    changed = False
    for b in booleans:
        if not isinstance(b, dict):
            continue
        if b.get("name") == "debugMode":
            if b.get("value") is not False:
                b["value"] = False
                changed = True
        if b.get("name") == "forceTest":
            # 기존에 value가 없을 수도 있어서 명시적으로 false를 넣음
            if b.get("value") is not False:
                b["value"] = False
                changed = True

    # 값이 아예 없으면 추가(안전)
    names = {str(b.get("name")) for b in booleans if isinstance(b, dict)}
    if "debugMode" not in names:
        booleans.append({"name": "debugMode", "value": False})
        changed = True
    if "forceTest" not in names:
        booleans.append({"name": "forceTest", "value": False})
        changed = True

    values["boolean"] = booleans
    params["values"] = values
    node["parameters"] = params
    return changed


def main() -> None:
    api_key = _load_api_key()
    wf = _get_workflow(api_key)
    nodes: List[Dict[str, Any]] = wf.get("nodes") or []

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_prodmode_before.json").write_text(
        json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    changed_nodes = []
    for name in (NODE_SCALPING_SET, NODE_SWING_SET, NODE_WEEKLY_SET):
        try:
            n = _find_node(nodes, name)
        except RuntimeError:
            continue
        if _set_production_flags_on_set_node(n):
            changed_nodes.append(name)

    if not changed_nodes:
        print("OK: already production mode (no changes).")
        return

    wf["nodes"] = nodes
    updated = _update_workflow(api_key, wf)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_prodmode_after.json").write_text(
        json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("OK: production mode applied to:", ", ".join(changed_nodes))


if __name__ == "__main__":
    main()





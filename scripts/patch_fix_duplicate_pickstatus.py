"""
Fix: remove duplicate `pickStatus` declaration inside Yahoo debug counters blocks.

증상
- n8n Function 노드 실행 시: "Identifier 'pickStatus' has already been declared"

원인
- Scalping Scanner / Swing Scanner 코드에 `pickStatus`가
  1) KRX stabilize 공통 유틸로 1회
  2) "Debug counters (Yahoo)" 섹션에서 다시 1회
  총 2회 선언되어 JS 문법 오류 발생

해결
- "Debug counters (Yahoo)" 섹션에 있는 중복 `pickStatus` 선언만 제거하고,
  기존(앞쪽) `pickStatus`를 그대로 재사용합니다.
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

NODE_SCALPING = "Scalping Scanner"
NODE_SWING = "Swing Scanner"


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


def _remove_duplicate_pickstatus_in_yahoo_debug(code: str) -> str:
    """
    Remove only the `const pickStatus = (e) => { ... };` inside:

      // ===== Debug counters (Yahoo) =====
      ...
      const pickStatus = (e) => { ... };
      // ===== /Debug counters (Yahoo) =====
    """
    pat = re.compile(
        r"(// ===== Debug counters \(Yahoo\) =====[\s\S]*?)\n"
        r"\s*const\s+pickStatus\s*=\s*\(e\)\s*=>\s*\{[\s\S]*?\n"
        r"\s*\};\n"
        r"(\s*// ===== /Debug counters \(Yahoo\) =====)",
        flags=re.MULTILINE,
    )
    if not pat.search(code):
        return code
    return pat.sub(r"\1\n\2", code, count=1)


def _assert_single_pickstatus(code: str, node_name: str) -> None:
    count = len(re.findall(r"\bconst\s+pickStatus\s*=\s*\(e\)\s*=>", code))
    if count != 1:
        raise RuntimeError(f"{node_name}: pickStatus 선언 개수가 1이 아닙니다. count={count}")


def main() -> None:
    api_key = _load_api_key()
    wf = _get_workflow(api_key)
    nodes: List[Dict[str, Any]] = wf.get("nodes") or []

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_pickstatus_before.json").write_text(
        json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    changed = 0
    for node_name in (NODE_SCALPING, NODE_SWING):
        n = _find_node(nodes, node_name)
        code = ((n.get("parameters") or {}).get("functionCode")) or ""
        code2 = _remove_duplicate_pickstatus_in_yahoo_debug(code)
        if code2 != code:
            changed += 1
        _assert_single_pickstatus(code2, node_name)
        n.setdefault("parameters", {})["functionCode"] = code2

    if changed == 0:
        print("OK: already fixed (no changes).")
        return

    wf["nodes"] = nodes
    updated = _update_workflow(api_key, wf)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_pickstatus_after.json").write_text(
        json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"OK: fixed duplicate pickStatus in {changed} node(s).")


if __name__ == "__main__":
    main()





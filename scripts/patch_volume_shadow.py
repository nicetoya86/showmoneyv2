"""
라이브 n8n 워크플로우(ScHaeFdneOoH1ZNZ)에 [SHADOW-2026-10-03] 반영 (volume5x-pattern-cap-shadow).

적용 내용 (노드 2개만 교체, 발송 로직 불변)
- Swing Scanner : weeklyRecommendations 레코드에 rvol 필드 추가
- Weekly Reporter: lib/shadowCohorts.js 인라인 + 리포트 하단 "Shadow 비교" 섹션 + store.shadowStats 저장

동작
- 기본은 DRY RUN: 라이브 노드 코드와 로컬 번들의 unified diff를 .claude/ 아래 파일로 저장하고
  +/- 줄 수와 hunk 시작줄을 출력한다(PUT 없음). 라이브가 로컬 직전 상태와 다르면(= 이번 변경 외의 diff가
  섞이면) 파일에서 확인할 수 있다.
- --apply 를 줄 때만 PUT. 적용 후 라이브를 다시 GET 해서 두 노드 코드가 로컬 번들과 100% 일치하는지 검증한다.
- 실행 전 라이브 워크플로우 JSON을 타임스탬프 백업(롤백 시 해당 노드 functionCode를 PUT으로 복원).

주의:
- API_KEY는 export_n8n_executions.py에서 읽는다.
- PATCH가 아닌 PUT을 사용한다 (이 n8n Cloud 인스턴스는 PATCH가 405).
- 사전: node scripts/build_deploy_bundle.js 로 번들 재생성 후 실행.
"""

from __future__ import annotations

import difflib
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


def _find_node(workflow: Dict[str, Any], node_name: str) -> Dict[str, Any]:
    node = next((n for n in workflow["nodes"] if n.get("name") == node_name), None)
    if node is None:
        raise RuntimeError(f"live workflow에서 '{node_name}' 노드를 찾지 못했습니다.")
    return node


def _norm(s: str) -> str:
    return s.replace("\r\n", "\n")


def main() -> int:
    dry_run = "--apply" not in sys.argv

    api_key = _load_api_key()
    workflow = _get_workflow(api_key)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = ROOT / ".claude" / f"live_workflow_backup_{ts}.json"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"backed up live workflow to {backup_path}")

    new_codes: Dict[str, str] = {}
    for node_name, file_name in NODE_FILE_MAP.items():
        node = _find_node(workflow, node_name)
        old_code = node["parameters"]["functionCode"]
        new_code = (ROOT / file_name).read_text(encoding="utf-8")
        new_codes[node_name] = new_code

        diff = list(difflib.unified_diff(
            _norm(old_code).splitlines(), _norm(new_code).splitlines(),
            fromfile=f"live:{node_name}", tofile=f"local:{file_name}", lineterm="", n=2,
        ))
        added = sum(1 for d in diff if d.startswith("+") and not d.startswith("+++"))
        removed = sum(1 for d in diff if d.startswith("-") and not d.startswith("---"))
        hunks = [d for d in diff if d.startswith("@@")]
        diff_path = ROOT / ".claude" / f"shadow_patch_diff_{node_name.replace(' ', '_')}_{ts}.txt"
        diff_path.write_text("\n".join(diff), encoding="utf-8")
        print(f"[{node_name}] {len(old_code)} -> {len(new_code)} chars | +{added} -{removed} lines | {len(hunks)} hunks")
        print(f"   diff saved: {diff_path}")
        for h in hunks[:12]:
            print(f"   {h}")

        if not dry_run:
            node["parameters"]["functionCode"] = new_code

    if dry_run:
        print("DRY RUN - no PUT sent. 위 diff가 이번 변경(shadow) 외의 hunk를 포함하는지 확인한 뒤 --apply 로 재실행.")
        return 0

    result = _update_workflow(api_key, workflow)
    print(f"PUT applied. versionId={result.get('versionId')}")

    # 적용 후 재조회 검증: 라이브 두 노드가 로컬 번들과 100% 일치해야 한다.
    live = _get_workflow(api_key)
    ok = True
    for node_name, new_code in new_codes.items():
        same = _norm(_find_node(live, node_name)["parameters"]["functionCode"]) == _norm(new_code)
        print(f"verify [{node_name}] live == local: {same}")
        ok = ok and same
    if not ok:
        print("VERIFY FAILED - 백업 JSON으로 롤백하세요:", backup_path)
        return 2
    print("VERIFY OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

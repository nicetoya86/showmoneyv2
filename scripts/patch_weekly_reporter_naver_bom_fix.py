"""
Weekly Reporter — Naver 응답 정규화(BOM/Buffer/문자열 JSON) 복원 패치

문제: 2026-07-25 주간 리포트가 "총추천 15건 │ 진입 0건 │ 승률 N/A"로 텅 비어서 발송됨.
원인: lib/naverClient.js 통합 과정에서 swing_scanner_code.js에만 있던
      Buffer/BOM/문자열 JSON 응답 처리(2026-03-30 naver_resp_normalize 패치)가
      Weekly Reporter 쪽에는 빠진 채로 배포되어 있었음(get_workflow로 실제 프로덕션
      코드를 확인해 재확인함) — Naver가 문자열/BOM 응답을 주면 전 종목이 no_data 처리됨.

이 스크립트는:
  1) 현재 배포된 워크플로우를 백업
  2) "Weekly Reporter" Function 노드의 코드를 로컬에서 재빌드된
     weekly_reporter_code.js(정규화 로직 복원 + 실패 로그 추가) 내용으로 교체
  3) 워크플로우를 업데이트
  4) 재조회로 실제 반영됐는지 검증

주의:
  - API 키는 하드코딩하지 않는다. 환경변수 N8N_API_KEY 에서 읽는다.
    (PowerShell/Bash에서 실행 시 1회성으로만 설정할 것 — 파일에 남기지 말 것)
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests

WORKFLOW_ID = "ScHaeFdneOoH1ZNZ"
N8N_BASE_URL = "https://fastlane12.app.n8n.cloud/api/v1"
TARGET_NODE_NAME = "Weekly Reporter"
NEW_CODE_PATH = Path("weekly_reporter_code.js")
MARKER = "2026-07-25 BUGFIX"


def _load_api_key() -> str:
    # 우선순위: 환경변수 N8N_API_KEY > export_n8n_executions.py (레포 공통 자격증명 저장소, git 제외됨)
    env_key = os.environ.get("N8N_API_KEY")
    if env_key:
        return env_key
    creds_path = Path("export_n8n_executions.py")
    if creds_path.exists():
        text = creds_path.read_text(encoding="utf-8")
        m = re.search(r'^\s*API_KEY\s*=\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
        if m:
            return m.group(1)
    raise RuntimeError(
        "N8N API 키를 찾지 못했습니다. 환경변수 N8N_API_KEY를 설정하거나 "
        "export_n8n_executions.py에 API_KEY를 채워주세요."
    )


def _headers(api_key: str) -> Dict[str, str]:
    return {"X-N8N-API-KEY": api_key, "Accept": "application/json"}


def _get_workflow(api_key: str, workflow_id: str) -> Dict[str, Any]:
    r = requests.get(f"{N8N_BASE_URL}/workflows/{workflow_id}", headers=_headers(api_key), timeout=60)
    r.raise_for_status()
    return r.json()


def _sanitize_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    # n8n API v1 PUT 스키마는 GET이 돌려주는 일부 필드(읽기 전용/신규 필드)를 거부한다
    # (실제로 400 "must NOT have additional properties"로 확인됨).
    cleaned = dict(settings or {})
    for key in ("availableInMCP", "binaryMode", "callerPolicy"):
        cleaned.pop(key, None)
    return cleaned


def _update_workflow(api_key: str, workflow_id: str, workflow: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "name": workflow.get("name"),
        "nodes": workflow.get("nodes"),
        "connections": workflow.get("connections"),
        "settings": _sanitize_settings(workflow.get("settings") or {}),
    }
    r = requests.put(
        f"{N8N_BASE_URL}/workflows/{workflow_id}",
        headers={**_headers(api_key), "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=60,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"n8n API update failed: http={r.status_code} body={r.text[:1200]}")
    return r.json()


def _find_node(nodes: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    for n in nodes:
        if n.get("name") == name:
            return n
    raise RuntimeError(f"노드를 찾지 못했습니다: {name}")


def main() -> None:
    api_key = _load_api_key()
    new_code = NEW_CODE_PATH.read_text(encoding="utf-8")
    if MARKER not in new_code:
        raise RuntimeError(f"{NEW_CODE_PATH}에 예상한 수정 마커({MARKER})가 없습니다 — 재빌드 여부를 확인하세요.")

    print("1) 현재 워크플로우 조회...")
    wf = _get_workflow(api_key, WORKFLOW_ID)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    before_path = f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_weekly_reporter_naver_bom_fix_before.json"
    Path(before_path).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   백업 완료: {before_path}")

    nodes: List[Dict[str, Any]] = wf.get("nodes") or []
    node = _find_node(nodes, TARGET_NODE_NAME)
    old_code = (node.get("parameters") or {}).get("functionCode") or ""
    if MARKER in old_code:
        print("   이미 패치 적용되어 있음 — 스킵.")
        return

    print(f"2) '{TARGET_NODE_NAME}' 노드 코드 교체 (길이 {len(old_code)} -> {len(new_code)})...")
    node.setdefault("parameters", {})["functionCode"] = new_code

    wf["nodes"] = nodes
    print("3) 워크플로우 업데이트 중...")
    updated = _update_workflow(api_key, WORKFLOW_ID, wf)

    after_path = f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_weekly_reporter_naver_bom_fix_after.json"
    Path(after_path).write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   패치 후 백업: {after_path}")

    print("4) 재조회로 검증...")
    verify = _get_workflow(api_key, WORKFLOW_ID)
    verify_node = _find_node(verify.get("nodes") or [], TARGET_NODE_NAME)
    verify_code = (verify_node.get("parameters") or {}).get("functionCode") or ""
    if MARKER not in verify_code:
        raise RuntimeError("검증 실패: 배포된 코드에 수정 마커가 없습니다.")

    print("OK: Weekly Reporter 노드에 Naver 응답 정규화 복원 패치가 정상 반영되었습니다.")
    print("Updated workflow name:", updated.get("name"))


if __name__ == "__main__":
    main()

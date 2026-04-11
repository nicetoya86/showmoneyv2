"""
Swing Scanner - Naver 응답 string 파싱 패치

문제: 2026-03-13 스윙 스캔에서 Naver OK/NoResult/Error: 0/1490/0 발생
원인: n8n HTTP 노드가 JSON 배열 대신 string으로 응답 반환 → !Array.isArray(resp) = true → 전 종목 NoResult

수정 내용:
  - httpDaily 내 [1차] fetchDaily 호출 직후 string 응답 자동 파싱 추가
  - httpDaily 내 [2차] fetchDaily 호출 직후 string 응답 자동 파싱 추가
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
PATCH_MARKER = "naver_string_parse_fix"


def _load_api_key_from_repo() -> str:
    text = Path("export_n8n_executions.py").read_text(encoding="utf-8")
    m = re.search(r'^\s*API_KEY\s*=\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
    if not m:
        raise RuntimeError("API_KEY를 export_n8n_executions.py에서 찾지 못했습니다.")
    return m.group(1)


def _headers(api_key: str) -> Dict[str, str]:
    return {"X-N8N-API-KEY": api_key, "Accept": "application/json"}


def _get_workflow(api_key: str, workflow_id: str) -> Dict[str, Any]:
    r = requests.get(f"{N8N_BASE_URL}/workflows/{workflow_id}", headers=_headers(api_key), timeout=60)
    r.raise_for_status()
    return r.json()


def _update_workflow(api_key: str, workflow_id: str, workflow: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "name": workflow.get("name"),
        "nodes": workflow.get("nodes"),
        "connections": workflow.get("connections"),
        "settings": workflow.get("settings"),
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


def _patch_naver_string_parse(old: str) -> str:
    """
    httpDaily 내 fetchDaily 응답이 string으로 오는 경우 자동 파싱하도록 패치.
    """
    if PATCH_MARKER in old:
        print("  이미 패치 적용됨, 스킵.")
        return old

    # [1차] fetchDaily 호출 후 rawSample 캡처 전에 string 파싱 삽입
    # 찾을 대상: rawSample 캡처 블록 바로 앞
    target_1 = (
        "      // 실제 응답 샘플 캡처 (비정상 응답 진단용, 첫 1건만)\n"
        "      if ((!Array.isArray(resp) || resp.length === 0) && !naverRawSample) {"
    )
    replacement_1 = (
        f"      // [{PATCH_MARKER}] string 응답 자동 파싱 (n8n이 JSON array 대신 string으로 반환하는 경우 방어)\n"
        "      if (typeof resp === 'string') { try { resp = JSON.parse(resp); } catch(_) { resp = []; } }\n"
        "\n"
        "      // 실제 응답 샘플 캡처 (비정상 응답 진단용, 첫 1건만)\n"
        "      if ((!Array.isArray(resp) || resp.length === 0) && !naverRawSample) {"
    )

    if target_1 not in old:
        raise RuntimeError("[1차] rawSample 캡처 블록을 찾지 못했습니다.")

    patched = old.replace(target_1, replacement_1, 1)

    # [2차] fetchDaily 호출 후 string 파싱 삽입
    # 찾을 대상: 2차 fetchDaily 호출 직후 블록 닫힘
    target_2 = (
        "        resp = await fetchDaily(code, startDateAlt, endDate);\n"
        "      }"
    )
    replacement_2 = (
        "        resp = await fetchDaily(code, startDateAlt, endDate);\n"
        "        if (typeof resp === 'string') { try { resp = JSON.parse(resp); } catch(_) { resp = []; } }\n"
        "      }"
    )

    if target_2 not in patched:
        raise RuntimeError("[2차] fetchDaily 호출 블록을 찾지 못했습니다.")

    patched = patched.replace(target_2, replacement_2, 1)

    return patched


def main() -> None:
    api_key = _load_api_key_from_repo()
    wf = _get_workflow(api_key, WORKFLOW_ID)

    # 백업
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    before_path = f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_naver_fix_before.json"
    Path(before_path).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"백업 완료: {before_path}")

    nodes: List[Dict[str, Any]] = wf.get("nodes") or []

    swing_node = _find_node(nodes, "Swing Scanner")
    swing_code = (swing_node.get("parameters") or {}).get("functionCode") or ""

    print("Swing Scanner 패치 적용 중...")
    patched_code = _patch_naver_string_parse(swing_code)
    swing_node.setdefault("parameters", {})["functionCode"] = patched_code

    wf["nodes"] = nodes
    updated = _update_workflow(api_key, WORKFLOW_ID, wf)

    after_path = f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_naver_fix_after.json"
    Path(after_path).write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"패치 후 백업: {after_path}")
    print("OK: Naver string parse 패치 적용 완료.")
    print("Updated workflow name:", updated.get("name"))


if __name__ == "__main__":
    main()

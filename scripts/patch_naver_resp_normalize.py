"""
Swing Scanner - Naver 응답 정규화 패치 (v2)

문제: 2026-03-30 스윙 스캔에서 Naver OK/NoResult/Error: 0/1348/0 재발생
원인: naver_string_parse_fix 가 이미 적용되어 있으나 아래 케이스 미처리:
  - 응답 string에 BOM(\uFEFF) 또는 앞뒤 공백 포함 시 JSON.parse 실패
  - Buffer 타입으로 응답이 올 경우 string 처리 미적용
  - n8n이 응답을 객체로 래핑할 경우 (body/data/result/chartPriceList)

수정 내용:
  - naver_string_parse_fix 를 _normalizeNaverResp() 헬퍼로 교체
  - BOM 제거 + trim 후 JSON.parse
  - Buffer 타입 → utf8 string 변환
  - 래핑 객체 처리 (body/data/result/chartPriceList 키 체크)
  - 1차/2차 fetchDaily 호출 모두 적용
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
NEW_MARKER = "naver_resp_normalize"


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


OLD_PATTERN = re.compile(
    r"// \[naver_string_parse_fix\].*?\n"
    r"      if \(typeof resp === 'string'\) \{ try \{ resp = JSON\.parse\(resp\); \} catch\(_\) \{ resp = \[\]; \} \}\n"
    r"\n"
    r"      // .*?\n"
    r"      if \(\(!Array\.isArray\(resp\) \|\| resp\.length === 0\) && !naverRawSample\) \{\n"
    r"        try \{ naverRawSample = JSON\.stringify\(resp\)\.slice\(0, 300\); \} catch\(_\) \{ naverRawSample = String\(resp\)\.slice\(0, 300\); \}\n"
    r"      \}\n"
    r"\n"
    r"      // \[2.*?\n"
    r"      if \(!Array\.isArray\(resp\) \|\| resp\.length === 0\) \{\n"
    r"        await sleep\(200\);\n"
    r"        const startKstAlt = new Date\(kstNow\.getTime\(\) - 180 \* 24 \* 3600000\);\n"
    r"        const startDateAlt = startKstAlt\.toISOString\(\)\.slice\(0, 10\)\.replace\(/-/g, ''\);\n"
    r"        resp = await fetchDaily\(code, startDateAlt, endDate\);\n"
    r"        if \(typeof resp === 'string'\) \{ try \{ resp = JSON\.parse\(resp\); \} catch\(_\) \{ resp = \[\]; \} \}\n"
    r"      \}",
    re.DOTALL,
)

NEW_CODE = (
    "// [naver_resp_normalize] 다양한 응답 형식 정규화 (Buffer, string BOM, 객체 래핑 등)\n"
    "      const _normalizeNaverResp = (r) => {\n"
    "        if (r === null || r === undefined) return [];\n"
    "        if (Buffer && Buffer.isBuffer(r)) r = r.toString('utf8');\n"
    "        if (typeof r === 'string') {\n"
    "          const cleaned = r.replace(/^\uFEFF/, '').trim(); // BOM 및 앞뒤 공백 제거\n"
    "          try { r = JSON.parse(cleaned); } catch(_) { return []; }\n"
    "        }\n"
    "        if (Array.isArray(r)) return r;\n"
    "        if (r && typeof r === 'object') {\n"
    "          // n8n이 응답을 객체로 래핑하는 경우 (body/data/result/chartPriceList 등)\n"
    "          if (Array.isArray(r.body)) return r.body;\n"
    "          if (Array.isArray(r.data)) return r.data;\n"
    "          if (Array.isArray(r.result)) return r.result;\n"
    "          if (Array.isArray(r.chartPriceList)) return r.chartPriceList;\n"
    "        }\n"
    "        return [];\n"
    "      };\n"
    "\n"
    "      // [1차] api.stock.naver.com (365일) - 응답 정규화 적용\n"
    "      resp = _normalizeNaverResp(resp);\n"
    "\n"
    "      // 실제 응답 샘플 캡처 (비정상 응답 진단용, 첫 1건만)\n"
    "      if ((!Array.isArray(resp) || resp.length === 0) && !naverRawSample) {\n"
    "        try { naverRawSample = JSON.stringify(resp).slice(0, 300); } catch(_) { naverRawSample = String(resp).slice(0, 300); }\n"
    "      }\n"
    "\n"
    "      // [2차] api.stock.naver.com (180일, 재시도)\n"
    "      if (!Array.isArray(resp) || resp.length === 0) {\n"
    "        await sleep(200);\n"
    "        const startKstAlt = new Date(kstNow.getTime() - 180 * 24 * 3600000);\n"
    "        const startDateAlt = startKstAlt.toISOString().slice(0, 10).replace(/-/g, '');\n"
    "        resp = _normalizeNaverResp(await fetchDaily(code, startDateAlt, endDate));\n"
    "      }"
)


def _patch_naver_resp_normalize(old: str) -> str:
    if NEW_MARKER in old:
        print("  이미 패치 적용됨, 스킵.")
        return old

    new_code, count = OLD_PATTERN.subn(NEW_CODE, old, count=1)
    if count == 0:
        raise RuntimeError("패치 대상 패턴을 찾지 못했습니다. 코드 구조가 변경되었을 수 있습니다.")

    print(f"  패턴 교체 완료 (1건). 코드 길이: {len(old)} → {len(new_code)}")
    return new_code


def main() -> None:
    api_key = _load_api_key_from_repo()
    wf = _get_workflow(api_key, WORKFLOW_ID)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    before_path = f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_naver_normalize_before.json"
    Path(before_path).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"백업 완료: {before_path}")

    nodes: List[Dict[str, Any]] = wf.get("nodes") or []
    swing_node = _find_node(nodes, "Swing Scanner")
    swing_code = (swing_node.get("parameters") or {}).get("functionCode") or ""

    print("Swing Scanner 패치 적용 중...")
    patched_code = _patch_naver_resp_normalize(swing_code)
    swing_node.setdefault("parameters", {})["functionCode"] = patched_code

    wf["nodes"] = nodes
    updated = _update_workflow(api_key, WORKFLOW_ID, wf)

    after_path = f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_naver_normalize_after.json"
    Path(after_path).write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"패치 후 백업: {after_path}")
    print("OK: Naver resp normalize 패치 적용 완료.")
    print("Updated workflow name:", updated.get("name"))


if __name__ == "__main__":
    main()

"""
Scalping Scanner에 'forceRun' 검증 모드 추가:

입력 예시(Execute Node 입력 JSON):
{
  "forceRun": true,
  "debugMode": true,
  "forceTest": false
}

동작
- forceRun=true이면 장/휴장/시간 체크를 무시하고,
  KRX 로드 + 캐시폴백 + 필터링(가격/거래대금/리스크 제외)까지만 수행한 뒤
  Yahoo 호출/텔레그램 발송 없이 요약 JSON을 반환.
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


def patch_code(code: str) -> str:
    if "forceRun" in code and "autofix_force_run_probe" in code:
        return code

    # 1) input 파싱 직후 forceRun 추가
    code = code.replace(
        "  const forceTest = !!input.forceTest;\n  const debugMode = !!input.debugMode;\n",
        "  const forceTest = !!input.forceTest;\n  const debugMode = !!input.debugMode;\n  const forceRun = !!input.forceRun; // autofix_force_run_probe\n",
        1,
    )

    # 2) 장/휴장 체크 블록 전체를 forceRun이면 스킵하도록 감싸기
    #    (if (!forceRun) { ... 기존 체크 ... })
    marker = "  // ===== 장/휴장 체크 =====\n"
    idx = code.find(marker)
    if idx < 0:
        raise RuntimeError("market check marker not found")

    # market check 구간 끝은 "중복 방지" 주석 바로 전으로 잡는다.
    end_marker = "  // ===== 중복 방지(최근 60분) =====\n"
    jdx = code.find(end_marker)
    if jdx < 0 or jdx <= idx:
        raise RuntimeError("duplicate window marker not found after market check")

    market_block = code[idx:jdx]
    wrapped = (
        "  // ===== 장/휴장 체크 =====\n"
        "  if (!forceRun) {\n"
        + "\n".join("  " + ln if ln.strip() else ln for ln in market_block.splitlines())  # indent one more level
        + "\n  }\n\n"
    )
    code = code[:idx] + wrapped + code[jdx:]

    # 3) ALL_TICKERS 계산 이후, Yahoo 호출 전에 forceRun이면 요약 반환
    #    앵커: if (ALL_TICKERS.length === 0) { ... } 블록 바로 뒤에 삽입
    pat_empty = re.compile(r"\n\s*if\s*\(ALL_TICKERS\.length\s*===\s*0\)\s*\{[\s\S]*?\n\s*\}\n", re.MULTILINE)
    m = pat_empty.search(code)
    if not m:
        raise RuntimeError("ALL_TICKERS empty block not found")

    insert = r"""

  // ===== autofix_force_run_probe: 야간/장외 강제 검증 모드 =====
  // forceRun=true이면 Yahoo 호출/텔레그램 발송 없이, KRX 로드/캐시폴백/필터링 결과만 리턴한다.
  if (forceRun) {
    const circuitUntil = (store.healthcheck && store.healthcheck.krx && store.healthcheck.krx.circuitUntil) || null;
    return [{
      json: {
        probe: true,
        today,
        timeStrNow,
        krxUniverseSource,
        krxUniverseError: krxUniverseError || null,
        krxErrMsg: krxErrMsg || null,
        krxErrStatus: (typeof krxErrStatus === 'number') ? krxErrStatus : (krxErrStatus ?? null),
        krxErrBodySample: krxErrBodySample || null,
        rowsCount: Array.isArray(rows) ? rows.length : null,
        filteredUniverse: ALL_TICKERS.length,
        excludedRisk,
        riskCacheAt,
        circuitUntil,
      }
    }];
  }
  // ===== /autofix_force_run_probe =====
"""

    code = code[: m.end()] + insert + code[m.end() :]
    return code


def main() -> None:
    api_key = load_api_key()
    wf = get_workflow(api_key)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_forceRun_before.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

    nodes: List[Dict[str, Any]] = wf.get("nodes") or []
    sc = find_node(nodes, NODE_SCALPING)
    code = (sc.get("parameters") or {}).get("functionCode") or ""
    sc.setdefault("parameters", {})["functionCode"] = patch_code(code)

    wf["nodes"] = nodes
    updated = update_workflow(api_key, wf)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_forceRun_after.json").write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK: forceRun probe patch applied.")


if __name__ == "__main__":
    main()






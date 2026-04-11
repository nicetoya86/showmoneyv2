"""
KRX 안정화 패치 후 생긴 문법/중복 문제를 정리하는 "수리" 스크립트.

증상(실제 확인됨)
- Scalping Scanner: `// ===== KRX 유니버스 로드 =====` + `let rows=[]`가 중복 삽입되어 문법 에러 가능
- Swing Scanner: KRX 로드 블록에 불필요한 들여쓰기/브레이스가 남아 문법 에러 가능

해결 방식
- 두 노드 모두:
  - `// ===== KRX 유니버스 로드 =====` ~ `// ===== autofix_krx_cache:` 사이를
    "정상 KRX 로드 블록"으로 강제 치환(앵커 기반)
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


KRX_LOAD_BLOCK = """// ===== KRX 유니버스 로드 =====
  let rows = [];
  let krxErrMsg = null;
  let krxErrStatus = null;
  let krxErrBodySample = null;

  if (isCircuitActive()) {
    krxErrMsg = 'circuit_active';
  } else {
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const headers = {
          'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
          Origin: 'https://data.krx.co.kr',
          Referer: 'https://data.krx.co.kr/contents/MDC/CM/MDI/mdiLoader/index.cmd',
          'X-Requested-With': 'XMLHttpRequest',
          'User-Agent': 'Mozilla/5.0',
        };
        const trdDd = `${kst.getUTCFullYear()}${String(kst.getUTCMonth() + 1).padStart(2, '0')}${String(kst.getUTCDate()).padStart(2, '0')}`;
        const body = `bld=dbms/MDC/STAT/standard/MDCSTAT01501&mktId=ALL&trdDd=${trdDd}&share=1&money=1&csvxls_isNo=false`;
        const r = await http({ method: 'POST', url: 'https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd', headers, body, json: true });
        rows = (r && (r.output || r.OutBlock_1 || [])) || [];
        if (rows.length > 0) {
          noteKrx({ ok: true, source: 'live', rows: rows.length, trdDd });
          break;
        }
      } catch (e) {
        krxErrMsg = String(e?.message || e);
        krxErrStatus = pickStatus(e);
        krxErrBodySample = pickBodySample(e);
        if (attempt === 2) {
          noteKrx({ ok: false, source: 'live', rows: 0, error: krxErrMsg, status: krxErrStatus, bodySample: krxErrBodySample });
        }
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
    }
  }
"""


def repair_between_anchors(code: str, node_name: str) -> str:
    a = "// ===== KRX 유니버스 로드 ====="
    b = "// ===== autofix_krx_cache:"
    if a not in code or b not in code:
        raise RuntimeError(f"[{node_name}] anchors not found (a={a in code}, b={b in code})")

    # a부터 b 직전까지 치환
    pat = re.compile(r"// ===== KRX 유니버스 로드 =====[\s\S]*?(?=\n\s*// ===== autofix_krx_cache:)", re.MULTILINE)
    if not pat.search(code):
        raise RuntimeError(f"[{node_name}] cannot locate section between anchors")
    return pat.sub(KRX_LOAD_BLOCK, code, count=1)


def main() -> None:
    api_key = load_api_key()
    wf = get_workflow(api_key)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_repair_before.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

    nodes: List[Dict[str, Any]] = wf.get("nodes") or []

    for node_name in (NODE_SCALPING, NODE_SWING):
        n = find_node(nodes, node_name)
        code = (n.get("parameters") or {}).get("functionCode") or ""
        fixed = repair_between_anchors(code, node_name)
        n.setdefault("parameters", {})["functionCode"] = fixed

    wf["nodes"] = nodes
    updated = update_workflow(api_key, wf)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_repair_after.json").write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK: repaired KRX load sections.")


if __name__ == "__main__":
    main()






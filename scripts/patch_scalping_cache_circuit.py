"""
Scalping Scanner의 autofix_krx_cache 블록에
- 서킷 브레이커(openCircuit)
- 마지막 상태 기록(noteKrx)
를 추가하여, Scalping만 실행되어도 KRX 장애를 스스로 흡수하도록 보강합니다.
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


def main() -> None:
    api_key = load_api_key()
    wf = get_workflow(api_key)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_scalping_cache_before.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

    nodes: List[Dict[str, Any]] = wf.get("nodes") or []
    sc = find_node(nodes, NODE_SCALPING)
    code = (sc.get("parameters") or {}).get("functionCode") or ""

    if "noteKrx({ ok:" in code and "openCircuit(" in code and "autofix_krx_cache" in code:
        print("OK: already patched.")
        return

    pat = re.compile(
        r"(// ===== autofix_krx_cache: KRX 장애 시 캐시 폴백 =====[\s\S]*?)(\n\s*// ===== /autofix_krx_cache =====)",
        re.MULTILINE,
    )
    m = pat.search(code)
    if not m:
        raise RuntimeError("autofix_krx_cache block not found in Scalping Scanner")

    insert = r"""

  // (추가) scalping에서도 KRX 장애를 서킷/기록으로 남김
  try {
    const reason = krxUniverseError || krxErrMsg || 'live_failed';
    if (krxUniverseSource !== 'live') openCircuit(reason, krxErrStatus, krxErrBodySample);
    noteKrx({
      ok: (krxUniverseSource === 'live'),
      source: krxUniverseSource,
      rows: Array.isArray(rows) ? rows.length : 0,
      error: reason,
      status: krxErrStatus,
      bodySample: krxErrBodySample,
    });
  } catch (e) {}
"""

    code2 = code[: m.end(1)] + insert + m.group(2) + code[m.end(2) :]
    sc.setdefault("parameters", {})["functionCode"] = code2

    wf["nodes"] = nodes
    updated = update_workflow(api_key, wf)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_scalping_cache_after.json").write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK: patched scalping cache circuit.")


if __name__ == "__main__":
    main()






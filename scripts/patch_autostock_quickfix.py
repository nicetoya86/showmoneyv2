"""
Autostock (n8n) 빠른 안정화 패치 스크립트

적용 내용
- Refresh Risk Blacklist (KRX+KIND): 예외 방어 + 실패 시 기존 캐시 유지 + 텔레그램 경보
- Scalping Scanner / Swing Scanner: KRX 유니버스 캐시 저장 + KRX 실패 시 캐시 폴백 + 실패 이유를 명확히 기록/경보
- Swing Watchdog (09:12): 09:10 트리거 누락 시 09:12에 스윙 스캐너 백업 실행 + 경보

주의:
- 이 스크립트는 레포의 export_n8n_executions.py 에 있는 API_KEY를 읽어 사용합니다.
- 실행 전/후 워크플로우 JSON을 로컬에 백업합니다.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests


WORKFLOW_ID = "ScHaeFdneOoH1ZNZ"
N8N_BASE_URL = "https://fastlane12.app.n8n.cloud/api/v1"


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
    """
    n8n Cloud API v1: PUT /workflows/{id}
    (현재 환경에서는 PATCH가 405(Method Not Allowed)라 PUT을 사용합니다.)
    """
    # 안전하게 주요 필드만 보냅니다.
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
        # 서버가 기대하는 필드/형식이 다를 수 있어, 에러 본문을 보여줘야 빠르게 수정 가능
        raise RuntimeError(f"n8n API update failed: http={r.status_code} body={r.text[:1200]}")
    return r.json()


def _find_node(nodes: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    for n in nodes:
        if n.get("name") == name:
            return n
    raise RuntimeError(f"노드를 찾지 못했습니다: {name}")


def _ensure_cron_node(nodes: List[Dict[str, Any]], connections: Dict[str, Any], *, name: str, cron: str, pos: Tuple[int, int]) -> None:
    if any(n.get("name") == name for n in nodes):
        return
    nodes.append(
        {
            "parameters": {"triggerTimes": {"item": [{"mode": "custom", "cronExpression": cron}]}},
            "id": f"autofix-{re.sub(r'[^a-z0-9]+','-', name.lower())[:40]}",
            "name": name,
            "type": "n8n-nodes-base.cron",
            "typeVersion": 1,
            "position": list(pos),
        }
    )
    connections.setdefault(name, {"main": [[]]})


def _ensure_function_node(nodes: List[Dict[str, Any]], connections: Dict[str, Any], *, name: str, code: str, pos: Tuple[int, int]) -> None:
    if any(n.get("name") == name for n in nodes):
        return
    nodes.append(
        {
            "parameters": {"functionCode": code},
            "id": f"autofix-{re.sub(r'[^a-z0-9]+','-', name.lower())[:40]}",
            "name": name,
            "type": "n8n-nodes-base.function",
            "typeVersion": 1,
            "position": list(pos),
        }
    )
    connections.setdefault(name, {"main": [[]]})


def _connect(connections: Dict[str, Any], src: str, dst: str) -> None:
    conns = connections.setdefault(src, {})
    main = conns.setdefault("main", [])
    if not main:
        main.append([])
    # 첫 번째 output만 사용
    if not any(c.get("node") == dst for c in main[0]):
        main[0].append({"node": dst, "type": "main", "index": 0})


def _patch_risk_blacklist_code(old: str) -> str:
    # 어떤 형태의 오류(split 포함)가 나더라도 전체 노드가 죽지 않게 try/catch로 감싼다.
    if "riskLastError" in old and "SAFE GUARD" in old:
        return old

    wrapper = r"""const BOT = '8366696724:AAHROcjGoQEn9BziD-sYdAu3ZuaolwtkgLE';
const CHAT = '523002062';
const NL = String.fromCharCode(10);

// ===== SAFE GUARD (autofix) =====
async function notify(text) {
  try {
    await http({
      method: 'POST',
      url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
      json: true,
      body: { chat_id: CHAT, text },
    });
  } catch (e) {}
}

const prev = {
  riskCodes: Array.isArray(store.blacklist?.riskCodes) ? store.blacklist.riskCodes.slice() : null,
  riskUpdatedAt: store.blacklist?.riskUpdatedAt || null,
};

try {
"""
    suffix = r"""
} catch (e) {
  const msg = e?.message ? String(e.message) : String(e);
  store.blacklist.riskLastError = { at: new Date().toISOString(), message: msg };
  // 기존 값 유지
  if (prev.riskCodes) store.blacklist.riskCodes = prev.riskCodes;
  if (prev.riskUpdatedAt) store.blacklist.riskUpdatedAt = prev.riskUpdatedAt;
  await notify('🚨 [리스크 블랙리스트 갱신 실패]' + NL + msg);
  return [{ json: { ok: false, error: msg, riskUpdatedAt: store.blacklist.riskUpdatedAt || null } }];
}
// ===== /SAFE GUARD (autofix) =====
"""

    # store/http 초기화 이후에 wrapper를 삽입해야 한다.
    marker = "const http = async"
    idx = old.find(marker)
    if idx < 0:
        raise RuntimeError("risk blacklist code에서 http 선언을 찾지 못했습니다.")
    # http 선언 블록 끝(세미콜론) 뒤에 삽입
    # 간단히 첫 줄 끝 다음에 삽입 (위 wrapper는 http를 참조하므로 http 선언 뒤여야 함)
    lines = old.splitlines(True)
    out: List[str] = []
    inserted = False
    for ln in lines:
        out.append(ln)
        if (not inserted) and ln.lstrip().startswith("const http = async"):
            # 다음 줄까지 포함될 수 있으니, 세미콜론이 나올 때까지 기다린다.
            continue
        if (not inserted) and "const http" in "".join(out[-3:]) and ";" in ln:
            out.append(wrapper + "\n")
            inserted = True
    if not inserted:
        # fallback: http 선언 바로 다음에 삽입
        text = old.replace(marker, marker + "\n" + wrapper, 1)
        return text + "\n" + suffix

    # 마지막 return 앞에 suffix를 넣는다(try 블록 닫기)
    text2 = "".join(out)
    # 가장 마지막 "return [" 이전에 suffix를 삽입(안전)
    m = re.search(r"\nreturn\s+\[", text2)
    if not m:
        # 그냥 끝에 닫기
        return text2 + "\n" + suffix
    return text2[: m.start()] + "\n" + suffix + "\n" + text2[m.start() :]


def _inject_krx_cache(old: str, kind: str) -> str:
    """
    Scalping/Swing 스캐너에 KRX 유니버스 캐시 저장 + 실패 시 캐시 폴백을 삽입.
    """
    if "krxUniverseCache" in old and "autofix_krx_cache" in old:
        return old

    # KRX rows 로드 직후( rows = ... ) 다음에 붙일 수 있는 위치를 찾는다.
    # 각 스캐너는 `let rows = []; for (let attempt ...` 블록이 존재한다.
    m = re.search(r"// ===== KRX 유니버스 로드 =====\n\s*let rows = \[\];", old)
    if not m:
        # swing scanner는 다른 형태일 수 있음
        m = re.search(r"\n\s*let rows = \[\];\n\s*\n\s*for \(let attempt = 0; attempt < 3; attempt\+\+\)", old)
    if not m:
        raise RuntimeError(f"[{kind}] rows 로드 블록을 찾지 못했습니다.")

    # rows 로드가 끝난 뒤 `const NAME = {}` 이전에 삽입(스캘핑) 또는 `for (let i = 0; i < rows.length; i++)` 이전(swing)
    insert_after_pattern = r"\n\s*const NAME = \{\};"
    pos = re.search(insert_after_pattern, old)
    if not pos:
        # swing은 const NAME이 더 뒤에 있을 수 있음(이미 존재)
        pos = re.search(r"\n\s*for \(let i = 0; i < rows\.length; i\+\+\)", old)
    if not pos:
        raise RuntimeError(f"[{kind}] 캐시 삽입 지점을 찾지 못했습니다.")

    block = r"""

  // ===== autofix_krx_cache: KRX 장애 시 캐시 폴백 =====
  const trdDd = `${kst.getUTCFullYear()}${String(kst.getUTCMonth() + 1).padStart(2, '0')}${String(kst.getUTCDate()).padStart(2, '0')}`;
  let krxUniverseSource = 'live';
  let krxUniverseError = null;

  try {
    if (Array.isArray(rows) && rows.length > 0) {
      // 최소 필드만 캐싱(용량 절약)
      store.krxUniverseCache = {
        trdDd,
        fetchedAt: now.toISOString(),
        rows: rows.slice(0, 4000).map((r) => ({
          ISU_SRT_CD: String(r?.ISU_SRT_CD || ''),
          ISU_ABBRV: String(r?.ISU_ABBRV || r?.ISU_NM || ''),
          ISU_NM: String(r?.ISU_NM || ''),
          MKT_NM: String(r?.MKT_NM || ''),
          TDD_CLSPRC: String(r?.TDD_CLSPRC || '0'),
          ACC_TRDVAL: String(r?.ACC_TRDVAL || '0'),
        })),
      };
    } else {
      const cache = store.krxUniverseCache;
      if (cache && Array.isArray(cache.rows) && cache.rows.length > 0) {
        rows = cache.rows;
        krxUniverseSource = 'cache';
      } else {
        krxUniverseSource = 'none';
      }
    }
  } catch (e) {
    krxUniverseError = String(e?.message || e);
  }
  // ===== /autofix_krx_cache =====
"""

    # store 변수가 존재해야 하므로, store 선언 뒤쪽에서만 유효.
    if "const store = this.getWorkflowStaticData('global');" not in old:
        raise RuntimeError(f"[{kind}] store 선언을 찾지 못했습니다.")

    patched = old[: pos.start()] + block + old[pos.start() :]

    # 유니버스 0 처리 구간에서 "정상 0"과 "데이터 소스 실패 0"을 구분하고 경보를 강화한다.
    # 기존: reason: 'KRX universe empty after filters' 등을 더 구체화
    patched = patched.replace(
        "reason: 'KRX universe empty after filters'",
        "reason: (krxUniverseSource === 'cache') ? 'KRX live failed -> used cache, but universe empty after filters' : 'KRX universe empty after filters'",
    )

    # 반환 JSON에 krxUniverseSource/krxUniverseError 포함(디버그용)
    patched = patched.replace(
        "themeCacheAt,",
        "themeCacheAt,\n      krxUniverseSource,\n      krxUniverseError,\n",
    ) if "themeCacheAt," in patched else patched

    return patched


def _patch_swing_scanner(old: str) -> str:
    # 하루 1회 실행 락 + watchdog 실행 시 표시
    if "swingLastRunDate" in old and "autofix_swing_guard" in old:
        return old

    marker = "const store = this.getWorkflowStaticData('global');"
    if marker not in old:
        raise RuntimeError("Swing Scanner: store 선언을 찾지 못했습니다.")

    guard = r"""

  // ===== autofix_swing_guard: 하루 1회 실행 + Watchdog 백업 =====
  if (!store.swingMeta) store.swingMeta = {};
  if (store.swingMeta.lastRunDate === today) {
    return [{ json: { skipped: true, reason: 'already_ran_today', today, timeStrNow } }];
  }
  // 락을 먼저 잡아(중복 실행 방지) 스캔을 진행
  store.swingMeta.lastRunDate = today;
  store.swingMeta.lastRunAt = now.toISOString();
  store.swingMeta.lastRunBy = input && input.watchdog ? 'watchdog_09_12' : 'cron_09_10';
  // ===== /autofix_swing_guard =====
"""
    return old.replace(marker, marker + guard, 1)


def _swing_watchdog_code() -> str:
    return r"""const run = async function () {
  const BOT = '8366696724:AAHROcjGoQEn9BziD-sYdAu3ZuaolwtkgLE';
  const CHAT = '523002062';
  const NL = String.fromCharCode(10);
  const http = async (o) => await this.helpers.httpRequest(Object.assign({ timeout: 30000 }, o));

  const store = this.getWorkflowStaticData('global');
  if (!store.swingMeta) store.swingMeta = {};

  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const today = `${kst.getUTCFullYear()}-${String(kst.getUTCMonth() + 1).padStart(2, '0')}-${String(kst.getUTCDate()).padStart(2, '0')}`;

  // 이미 오늘 스윙이 실행됐으면 아무것도 하지 않음
  if (store.swingMeta.lastRunDate === today) return [];

  // 경보 + 09:12에 백업 실행
  const msg =
    '⚠️ [스윙 백업 실행] 09:10 트리거 누락 감지' + NL +
    `- date: ${today}` + NL +
    `- action: run Swing Scanner at 09:12`;
  try {
    await http({
      method: 'POST',
      url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
      json: true,
      body: { chat_id: CHAT, text: msg },
    });
  } catch (e) {}

  // swing scanner로 넘길 입력
  return [{ json: { watchdog: true, debugMode: true, forceTest: false } }];
};
return run();"""


def main() -> None:
    api_key = _load_api_key_from_repo()
    wf = _get_workflow(api_key, WORKFLOW_ID)

    # 백업
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_before.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

    nodes: List[Dict[str, Any]] = wf.get("nodes") or []
    connections: Dict[str, Any] = wf.get("connections") or {}

    # 1) Risk blacklist guard
    risk_node = _find_node(nodes, "Refresh Risk Blacklist (KRX+KIND)")
    risk_code = (risk_node.get("parameters") or {}).get("functionCode") or ""
    risk_node.setdefault("parameters", {})["functionCode"] = _patch_risk_blacklist_code(risk_code)

    # 2) KRX cache fallback (scalping + swing)
    scalping_node = _find_node(nodes, "Scalping Scanner")
    scalping_code = (scalping_node.get("parameters") or {}).get("functionCode") or ""
    scalping_node.setdefault("parameters", {})["functionCode"] = _inject_krx_cache(scalping_code, "scalping")

    swing_node = _find_node(nodes, "Swing Scanner")
    swing_code = (swing_node.get("parameters") or {}).get("functionCode") or ""
    swing_code = _inject_krx_cache(swing_code, "swing")
    swing_code = _patch_swing_scanner(swing_code)
    swing_node.setdefault("parameters", {})["functionCode"] = swing_code

    # 3) Swing watchdog (09:12)
    cron_name = "Swing Watchdog Trigger (09:12)"
    fn_name = "Swing Watchdog + Backup"
    _ensure_cron_node(nodes, connections, name=cron_name, cron="12 9 * * 1-5", pos=(752, 1648))
    _ensure_function_node(nodes, connections, name=fn_name, code=_swing_watchdog_code(), pos=(1056, 1648))
    _connect(connections, cron_name, fn_name)
    _connect(connections, fn_name, "Swing Scanner")

    wf["nodes"] = nodes
    wf["connections"] = connections

    updated = _update_workflow(api_key, WORKFLOW_ID, wf)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_after.json").write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")

    print("OK: workflow updated.")
    print("Updated workflow name:", updated.get("name"))


if __name__ == "__main__":
    main()



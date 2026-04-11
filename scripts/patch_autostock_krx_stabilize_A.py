"""
선택 A(빠른 안정화): KRX 400/장애에 대한 근본 대응 패치

목표
- Daily Healthcheck / Scalping Scanner / Swing Scanner:
  - KRX 호출 실패 원인(HTTP status, 메시지, 응답 body 일부) 저장
  - 짧은 재시도 + 서킷 브레이커(일정 시간 동안 live 호출 중단 후 캐시 사용)
  - 캐시 폴백(이미 있던 autofix_krx_cache를 "정상 위치"로 정리)
  - 텔레그램 경고는 하루 1회로 제한(스팸 방지)
- Refresh Risk Blacklist (KRX+KIND):
  - 이전 패치로 깨진 `const http = async` 구문을 정상화(노드가 아예 실행되게 복구)

주의
- 이 스크립트는 export_n8n_executions.py의 API_KEY를 사용합니다.
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

NODE_HEALTHCHECK = "Daily Healthcheck"
NODE_SCALPING = "Scalping Scanner"
NODE_SWING = "Swing Scanner"
NODE_RISK = "Refresh Risk Blacklist (KRX+KIND)"

STAB_MARKER = "autofix_krx_stabilize_v1"


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
        raise RuntimeError(f"n8n API update failed: http={r.status_code} body={r.text[:1200]}")
    return r.json()


def _find_node(nodes: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    for n in nodes:
        if n.get("name") == name:
            return n
    raise RuntimeError(f"노드를 찾지 못했습니다: {name}")


def _insert_helper_after_store(code: str) -> str:
    if STAB_MARKER in code:
        return code

    helper = r"""

  // ===== autofix_krx_stabilize_v1 =====
  // KRX 장애를 "기록 + 폴백 + 스팸 없는 경고"로 흡수하기 위한 공통 유틸
  if (!store.healthcheck) store.healthcheck = {};
  if (!store.healthcheck.krx) store.healthcheck.krx = {};
  if (!store.healthcheck.krx.alerts) store.healthcheck.krx.alerts = {};
  const hcKrx = store.healthcheck.krx;

  const pickStatus = (e) => {
    const s = e?.statusCode ?? e?.response?.statusCode ?? e?.response?.status ?? e?.httpCode ?? e?.cause?.statusCode;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  };

  const pickBodySample = (e) => {
    try {
      const b = e?.response?.body;
      if (!b) return null;
      const t = (typeof b === 'string') ? b : (Buffer.isBuffer(b) ? b.toString('utf8') : JSON.stringify(b));
      return String(t).slice(0, 400);
    } catch (err) {
      return null;
    }
  };

  const isCircuitActive = () => {
    try {
      if (!hcKrx.circuitUntil) return false;
      const until = new Date(hcKrx.circuitUntil).getTime();
      return Number.isFinite(until) && until > now.getTime() && hcKrx.circuitDate === today;
    } catch (e) {
      return false;
    }
  };

  const openCircuit = (reason, status, bodySample) => {
    const minutes = 30; // 30분 동안 live 호출 중단
    const until = new Date(now.getTime() + minutes * 60 * 1000).toISOString();
    hcKrx.circuitDate = today;
    hcKrx.circuitUntil = until;
    hcKrx.circuitReason = String(reason || 'unknown');
    hcKrx.lastFailAt = now.toISOString();
    hcKrx.lastFailStatus = status ?? null;
    hcKrx.lastFailBodySample = bodySample ?? null;
  };

  const noteKrx = (meta) => {
    hcKrx.last = Object.assign({ at: now.toISOString(), date: today }, meta || {});
  };

  const notifyOncePerDay = async (key, text) => {
    const k = String(key || 'default');
    if (hcKrx.alerts[k] === today) return false;
    try {
      await http({
        method: 'POST',
        url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
        json: true,
        body: { chat_id: CHAT, text },
      });
      hcKrx.alerts[k] = today;
      return true;
    } catch (e) {
      return false;
    }
  };
  // ===== /autofix_krx_stabilize_v1 =====
"""

    marker = "const store = this.getWorkflowStaticData('global');"
    if marker not in code:
        return code
    return code.replace(marker, marker + helper, 1)


def _patch_krx_load_block(code: str, *, node_kind: str) -> str:
    """
    KRX 유니버스 로드 블록을 다음으로 교체:
    - 서킷 브레이커 체크
    - 재시도 중 마지막 에러/상태/본문 일부 수집
    - 실패 시 openCircuit + noteKrx
    """

    # 1) (권장) 주석 + rows 선언 + attempt loop
    pat = re.compile(
        r"// ===== KRX 유니버스 로드 =====\s*\n"
        r"\s*let rows = \[\];\s*\n"
        r"\s*let [^\n]*?\n"  # 가끔 err 변수가 앞에 올 수도 있어 느슨하게
        r"[\s\S]*?"
        r"\n\s*for\s*\(let attempt\s*=\s*0;\s*attempt\s*<\s*3;\s*attempt\+\+\)\s*\{\s*\n"
        r"[\s\S]*?\n\s*\}\s*\n",
        re.MULTILINE,
    )

    # 2) (Swing 등) rows 선언 + attempt loop (주석 없음)
    if not pat.search(code):
        pat = re.compile(
            r"\n\s*let rows = \[\];\s*\n"
            r"\s*\n\s*for\s*\(let attempt\s*=\s*0;\s*attempt\s*<\s*3;\s*attempt\+\+\)\s*\{\s*\n"
            r"[\s\S]*?\n\s*\}\s*\n",
            re.MULTILINE,
        )

    # 3) (가장 느슨) attempt loop만 있고 내부에 getJsonData가 존재
    if not pat.search(code):
        pat = re.compile(
            r"\n\s*for\s*\(let attempt\s*=\s*0;\s*attempt\s*<\s*3;\s*attempt\+\+\)\s*\{\s*\n"
            r"[\s\S]*?getJsonData\.cmd[\s\S]*?\n\s*\}\s*\n",
            re.MULTILINE,
        )
        if not pat.search(code):
            raise RuntimeError(f"[{node_kind}] KRX load block을 찾지 못했습니다.")

    repl = r"""// ===== KRX 유니버스 로드 =====
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

    code2 = pat.sub("\n  " + repl.replace("\n", "\n  ") + "\n", code, count=1)
    return code2


def _remove_all_krx_cache_blocks(code: str) -> str:
    return re.sub(
        r"\n\s*// ===== autofix_krx_cache: KRX 장애 시 캐시 폴백 =====[\s\S]*?// ===== /autofix_krx_cache =====\s*\n",
        "\n",
        code,
        flags=re.MULTILINE,
    )


def _insert_krx_cache_block_after_load_loop(code: str) -> str:
    """
    Swing에서 깨져 들어간 autofix_krx_cache를 정리하고, KRX 로드 루프 다음에 정상 위치로 삽입.
    """
    if "autofix_krx_cache" in code:
        # 이미 정상 위치에 있을 수도 있으니 일단 제거 후 재삽입
        code = _remove_all_krx_cache_blocks(code)

    # KRX load loop 끝(위에서 교체한 블록) 직후에 붙인다.
    anchor = "  // ===== KRX 유니버스 로드 ====="
    idx = code.find(anchor)
    if idx < 0:
        raise RuntimeError("KRX load anchor not found for cache insert.")

    # 교체된 블록은 noteKrx(...) 이후 "\n"로 끝남. 그 뒤(바로 다음 줄) 위치를 찾기 위해
    # 다음으로 나오는 빈 줄 1개 이후를 기준으로 삽입한다.
    m = re.search(r"// ===== KRX 유니버스 로드 =====[\s\S]*?\n\n", code)
    if not m:
        raise RuntimeError("KRX load block end not found for cache insert.")

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
        krxUniverseError = krxErrMsg || 'live_failed_used_cache';
      } else {
        krxUniverseSource = 'none';
        krxUniverseError = krxErrMsg || 'live_failed_no_cache';
      }
    }
  } catch (e) {
    krxUniverseError = String(e?.message || e);
  }

  // live가 실패했고 캐시로도 못 살리면 서킷을 연다(스팸 방지 + 차단 악화 방지)
  if (krxUniverseSource !== 'live') {
    openCircuit(krxUniverseError, krxErrStatus, krxErrBodySample);
  }
  noteKrx({ ok: (krxUniverseSource === 'live'), source: krxUniverseSource, rows: Array.isArray(rows) ? rows.length : 0, error: krxUniverseError, status: krxErrStatus, bodySample: krxErrBodySample });
  // ===== /autofix_krx_cache =====
"""

    return code[: m.end()] + block + "\n" + code[m.end() :]


def _patch_empty_universe_alert(code: str, *, node_kind: str) -> str:
    """
    KRX 유니버스가 0일 때 텔레그램 경고를 하루 1회로 제한하고,
    healthcheck에 실패 상세를 남기도록 수정.
    """
    if "notifyOncePerDay('krx_universe_empty'" in code:
        return code

    if node_kind == "scalping":
        # scalping은 이미 유니버스 0 처리 로직이 있음(ok:false return)
        # 그 직전에 live 실패/캐시 없음일 때만 하루 1회 경고를 추가
        marker = "if (ALL_TICKERS.length === 0) {"
        if marker not in code:
            return code
        inject = r"""if (ALL_TICKERS.length === 0) {
    // KRX가 죽어서 유니버스가 비었을 가능성이 높을 때(특히 cache도 없을 때) 하루 1회만 경고
    if (krxUniverseSource === 'none') {
      const msg =
        '⚠️ [KRX 장애] 단타 유니버스 0 (cache 없음)' + NL +
        `- KST: ${today} ${timeStrNow}` + NL +
        `- err: ${krxUniverseError || 'unknown'}` + NL +
        `- status: ${krxErrStatus ?? 'null'}`;
      await notifyOncePerDay('krx_universe_empty', msg);
    }
"""
        return code.replace(marker, inject, 1)

    # swing은 기존에 즉시 텔레그램 경고 + error return이 있음 -> 하루 1회 제한으로 변경
    pat = re.compile(
        r"\n\s*if\s*\(ALL_TICKERS\.length\s*===\s*0\)\s*\{\s*\n[\s\S]*?return\s+\[\{\s*json:\s*\{\s*error:\s*'Failed to load KRX universe'\s*\}\s*\}\];\s*\n\s*\}\s*\n",
        re.MULTILINE,
    )
    if not pat.search(code):
        return code

    repl = r"""
  if (ALL_TICKERS.length === 0) {
    const msg =
      '⚠️ [KRX 장애] 스윙 유니버스 0' + NL +
      `- KST: ${today} ${timeStrNow}` + NL +
      `- source: ${krxUniverseSource || 'unknown'}` + NL +
      `- err: ${krxUniverseError || 'unknown'}` + NL +
      `- status: ${krxErrStatus ?? 'null'}`;
    await notifyOncePerDay('krx_universe_empty', msg);
    return [{ json: { ok: false, error: 'Failed to load KRX universe', krxUniverseSource, krxUniverseError, krxErrStatus } }];
  }
"""
    return pat.sub("\n" + repl + "\n", code, count=1)


def _patch_daily_healthcheck(code: str) -> str:
    # helper 삽입 후, KRX 체크에 서킷브레이커/상세 기록을 추가
    # KRX try/catch 블록을 좀 더 풍부하게 교체한다.
    pat = re.compile(
        r"\n\s*// \(선택\) KRX 데이터 접근 가능 여부를 같이 점검[\s\S]*?\n\s*} catch \(e\) \{\n\s*krxStatus = '에러: '[\s\S]*?\n\s*}\n",
        re.MULTILINE,
    )
    if not pat.search(code):
        return code

    repl = r"""

  // (선택) KRX 데이터 접근 가능 여부를 같이 점검
  let krxStatus = '미확인';
  let krxCount = 0;
  let krxErrStatus = null;
  let krxErrBodySample = null;

  if (isCircuitActive()) {
    krxStatus = `서킷 활성(circuitUntil=${hcKrx.circuitUntil})`;
  } else {
    try {
      const headers = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': 'https://data.krx.co.kr',
        'Referer': 'https://data.krx.co.kr/contents/MDC/CM/MDI/mdiLoader/index.cmd',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0',
      };
      const trdDd = `${kst.getUTCFullYear()}${String(kst.getUTCMonth() + 1).padStart(2,'0')}${String(kst.getUTCDate()).padStart(2,'0')}`;
      const body = `bld=dbms/MDC/STAT/standard/MDCSTAT01501&mktId=ALL&trdDd=${trdDd}&share=1&money=1&csvxls_isNo=false`;
      const r = await http({ method: 'POST', url: 'https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd', headers, body, json: true });
      const rows = (r && (r.output || r.OutBlock_1 || [])) || [];
      krxCount = rows.length;
      krxStatus = (krxCount > 0) ? `성공 (${krxCount}개)` : '0건 (휴일/지연/차단 가능)';
      noteKrx({ ok: (krxCount > 0), source: 'healthcheck', rows: krxCount, trdDd });
    } catch (e) {
      const msg = String(e && e.message ? e.message : e);
      krxErrStatus = pickStatus(e);
      krxErrBodySample = pickBodySample(e);
      krxStatus = '에러: ' + msg;
      openCircuit(msg, krxErrStatus, krxErrBodySample);
      noteKrx({ ok: false, source: 'healthcheck', rows: 0, error: msg, status: krxErrStatus, bodySample: krxErrBodySample });
    }
  }
"""
    return pat.sub(repl + "\n", code, count=1)


def _repair_risk_blacklist_http(code: str) -> str:
    # 깨진 형태:
    # const http = async
    # ...
    # try {
    #  (o) =>
    #   await this.helpers.httpRequest(...)
    # );
    # ...
    code2 = code
    code2 = code2.replace(
        "const http = async\n",
        "const http = async (o) => await this.helpers.httpRequest(Object.assign({ timeout: 30000 }, o));\n\n",
    )

    # try { 바로 다음에 붙은 잘못된 람다 덩어리를 제거
    code2 = re.sub(
        r"try\s*\{\s*\n\s*\(o\)\s*=>\s*\n\s*await this\.helpers\.httpRequest\([\s\S]*?\);\s*\n",
        "try {\n",
        code2,
        flags=re.MULTILINE,
        count=1,
    )

    return code2


def main() -> None:
    api_key = _load_api_key()
    wf = _get_workflow(api_key)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_krxA_before.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

    nodes: List[Dict[str, Any]] = wf.get("nodes") or []

    # Daily Healthcheck
    hc = _find_node(nodes, NODE_HEALTHCHECK)
    hc_code = (hc.get("parameters") or {}).get("functionCode") or ""
    hc_code = _insert_helper_after_store(hc_code)
    hc_code = _patch_daily_healthcheck(hc_code)
    hc.setdefault("parameters", {})["functionCode"] = hc_code

    # Scalping
    sc = _find_node(nodes, NODE_SCALPING)
    sc_code = (sc.get("parameters") or {}).get("functionCode") or ""
    sc_code = _insert_helper_after_store(sc_code)
    sc_code = _patch_krx_load_block(sc_code, node_kind="scalping")
    # scalping은 기존 autofix_krx_cache 블록이 이미 있음 -> 그 블록이 krxErr*를 참조하지 않으므로 최소 수정:
    # cache 블록에서 openCircuit/noteKrx를 추가로 하고 싶지만, 큰 덩어리 교체는 리스크라 우선 'empty alert 하루 1회'만 추가
    sc_code = _patch_empty_universe_alert(sc_code, node_kind="scalping")
    sc.setdefault("parameters", {})["functionCode"] = sc_code

    # Swing (깨진 krx_cache 위치를 정리하고, KRX load를 안정화)
    sw = _find_node(nodes, NODE_SWING)
    sw_code = (sw.get("parameters") or {}).get("functionCode") or ""
    sw_code = _insert_helper_after_store(sw_code)
    sw_code = _remove_all_krx_cache_blocks(sw_code)
    # rows 선언이 없다면 NAME/ALL_TICKERS 선언 다음에 추가(방어)
    if "let rows = [];" not in sw_code:
        sw_code = re.sub(r"(const SEEN_CODES = new Set\(\);\s*\n)", r"\1  let rows = [];\n", sw_code, count=1)
    sw_code = _patch_krx_load_block(sw_code, node_kind="swing")
    sw_code = _insert_krx_cache_block_after_load_loop(sw_code)
    sw_code = _patch_empty_universe_alert(sw_code, node_kind="swing")
    sw.setdefault("parameters", {})["functionCode"] = sw_code

    # Risk blacklist: syntax repair
    risk = _find_node(nodes, NODE_RISK)
    risk_code = (risk.get("parameters") or {}).get("functionCode") or ""
    risk_code = _repair_risk_blacklist_http(risk_code)
    risk.setdefault("parameters", {})["functionCode"] = risk_code

    wf["nodes"] = nodes

    updated = _update_workflow(api_key, wf)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_krxA_after.json").write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK: KRX stabilize(A) applied.")


if __name__ == "__main__":
    main()



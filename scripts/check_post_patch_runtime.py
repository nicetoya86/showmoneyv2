"""
패치 적용 후 실제 실행(Executions)에서 동작이 정상인지 점검하는 리포트 생성기

확인 포인트
- Daily Healthcheck: krxStatus/krxCount 및 circuit 관련 메시지 여부
- Scalping/Swing: totalUniverse/candidates/sent 및 KRX 장애 시에도 0으로 죽지 않는지(간접 확인)
- Refresh Risk Blacklist: 실행이 성공/실패인지(문법 오류 복구 확인)

출력
- 콘솔에 최근 실행 요약
- debug_dump/post_patch_report.json 에 구조화된 결과 저장
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


WORKFLOW_ID = "ScHaeFdneOoH1ZNZ"
N8N_BASE_URL = "https://fastlane12.app.n8n.cloud/api/v1"

NODES_TO_CHECK = [
    "Daily Healthcheck",
    "Scalping Scanner",
    "Swing Scanner",
    "Refresh Risk Blacklist (KRX+KIND)",
]


def load_api_key() -> str:
    text = Path("export_n8n_executions.py").read_text(encoding="utf-8")
    m = re.search(r'^\s*API_KEY\s*=\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
    if not m:
        raise RuntimeError("API_KEY not found in export_n8n_executions.py")
    return m.group(1)


def headers(api_key: str) -> Dict[str, str]:
    return {"X-N8N-API-KEY": api_key, "Accept": "application/json"}


def iso_to_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    # Ensure timezone-aware
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def to_kst(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    return dt.astimezone(timezone(timedelta(hours=9)))


def get_executions(api_key: str, limit: int = 400) -> List[Dict[str, Any]]:
    """
    /executions는 한 번에 100개 제한이 있을 수 있어 nextCursor로 페이지네이션.
    """
    out: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    while len(out) < limit:
        batch = min(100, limit - len(out))
        params: Dict[str, Any] = {"workflowId": WORKFLOW_ID, "limit": int(batch)}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(
            f"{N8N_BASE_URL}/executions",
            headers=headers(api_key),
            params=params,
            timeout=60,
        )
        r.raise_for_status()
        j = r.json() or {}
        data = j.get("data", []) or []
        if not data:
            break
        out.extend(data)
        cursor = j.get("nextCursor")
        if not cursor:
            break
    return out


def get_execution_detail(api_key: str, execution_id: str) -> Dict[str, Any]:
    r = requests.get(
        f"{N8N_BASE_URL}/executions/{execution_id}",
        headers=headers(api_key),
        params={"includeData": "true"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def pick_node_last_output(run_data: Dict[str, Any], node_name: str) -> Optional[Dict[str, Any]]:
    """
    runData[nodeName] 는 실행 스텝 배열.
    마지막 스텝의 data.main[0][0].json을 반환(없으면 None)
    """
    steps = run_data.get(node_name)
    if not isinstance(steps, list) or not steps:
        return None
    step = steps[-1]
    data = (step or {}).get("data") or {}
    main = data.get("main")
    if not isinstance(main, list) or not main:
        return None
    out0 = main[0]
    if not isinstance(out0, list) or not out0:
        return None
    first = out0[0] or {}
    j = first.get("json")
    return j if isinstance(j, dict) else None


def pick_node_status(run_data: Dict[str, Any], node_name: str) -> Optional[str]:
    steps = run_data.get(node_name)
    if not isinstance(steps, list) or not steps:
        return None
    step = steps[-1] or {}
    return step.get("executionStatus") or step.get("status")  # compat


def summarize_execution(ex: Dict[str, Any], detail: Dict[str, Any]) -> Dict[str, Any]:
    started = iso_to_dt(ex.get("startedAt") or ex.get("createdAt"))
    stopped = iso_to_dt(ex.get("stoppedAt"))
    started_kst = to_kst(started)
    stopped_kst = to_kst(stopped)

    data = (detail or {}).get("data") or {}
    run_data = ((data.get("resultData") or {}).get("runData")) or {}

    node_summaries: Dict[str, Any] = {}
    for n in NODES_TO_CHECK:
        out = pick_node_last_output(run_data, n)
        st = pick_node_status(run_data, n)
        node_summaries[n] = {"status": st, "output": out}

    # 핵심 값만 뽑아 상단에 올림
    health = node_summaries.get("Daily Healthcheck", {}).get("output") or {}
    scalping = node_summaries.get("Scalping Scanner", {}).get("output") or {}
    swing = node_summaries.get("Swing Scanner", {}).get("output") or {}
    risk = node_summaries.get("Refresh Risk Blacklist (KRX+KIND)", {}).get("output") or {}

    return {
        "id": str(ex.get("id")),
        "status": ex.get("status"),
        "mode": ex.get("mode"),
        "startedAtKst": started_kst.isoformat() if started_kst else None,
        "stoppedAtKst": stopped_kst.isoformat() if stopped_kst else None,
        "healthcheck": {
            "krxStatus": health.get("krxStatus"),
            "krxCount": health.get("krxCount"),
            "today": health.get("today"),
        }
        if health
        else None,
        "scalping": {
            "totalUniverse": scalping.get("totalUniverse"),
            "candidates": scalping.get("candidates"),
            "sent": scalping.get("sent"),
            "ok": scalping.get("ok"),
            "reason": scalping.get("reason"),
            "error": scalping.get("error"),
        }
        if scalping
        else None,
        "swing": {
            "totalUniverse": swing.get("totalUniverse"),
            "candidates": swing.get("candidates"),
            "sent": swing.get("sent"),
            "ok": swing.get("ok"),
            "error": swing.get("error"),
            "reason": swing.get("reason"),
            "skipped": swing.get("skipped"),
        }
        if swing
        else None,
        "risk": {
            "ok": risk.get("ok"),
            "riskCodesCount": risk.get("riskCodesCount"),
            "error": risk.get("error"),
        }
        if risk
        else None,
        "nodes": node_summaries,
    }


def main() -> None:
    api_key = load_api_key()
    executions = get_executions(api_key, limit=400)
    # 최근 24시간만
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    executions = [
        ex
        for ex in executions
        if (iso_to_dt(ex.get("startedAt") or ex.get("createdAt")) or datetime(1970, 1, 1, tzinfo=timezone.utc)) >= cutoff
    ]

    results: List[Dict[str, Any]] = []
    for ex in executions:
        ex_id = str(ex.get("id"))
        try:
            detail = get_execution_detail(api_key, ex_id)
            results.append(summarize_execution(ex, detail))
        except Exception as e:
            results.append({"id": ex_id, "status": ex.get("status"), "error": str(e)})

    Path("debug_dump").mkdir(exist_ok=True)
    out_path = Path("debug_dump/post_patch_report.json")
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK: saved {len(results)} items -> {out_path.as_posix()}")
    # 콘솔 요약(최신 10개)
    for row in results[:10]:
        print("-" * 60)
        print("id:", row.get("id"), "status:", row.get("status"), "mode:", row.get("mode"))
        print("startedAtKst:", row.get("startedAtKst"))
        hc = row.get("healthcheck") or {}
        if hc:
            print("health.krxStatus:", hc.get("krxStatus"), "krxCount:", hc.get("krxCount"))
        sc = row.get("scalping") or {}
        if sc:
            print("scalping.totalUniverse:", sc.get("totalUniverse"), "candidates:", sc.get("candidates"), "sent:", sc.get("sent"), "ok:", sc.get("ok"), "reason:", sc.get("reason"), "error:", sc.get("error"))
        sw = row.get("swing") or {}
        if sw:
            print("swing.totalUniverse:", sw.get("totalUniverse"), "candidates:", sw.get("candidates"), "sent:", sw.get("sent"), "ok:", sw.get("ok"), "skipped:", sw.get("skipped"), "reason:", sw.get("reason"), "error:", sw.get("error"))
        rk = row.get("risk") or {}
        if rk:
            print("risk.ok:", rk.get("ok"), "riskCodesCount:", rk.get("riskCodesCount"), "error:", rk.get("error"))


if __name__ == "__main__":
    main()



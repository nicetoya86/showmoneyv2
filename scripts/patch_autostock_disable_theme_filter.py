"""
Autostock: 네이버 테마주(Theme) 기반 필터를 완전 제거하는 패치

적용 내용
- Scalping Scanner / Swing Scanner:
  - themeSet을 항상 빈 Set으로 설정(테마 코드로 종목 제외하지 않음)
  - themeSet.has(...)로 제외하는 로직 제거
- Blacklist Theme Refresh (Sun 08:30) + Refresh Theme Blacklist (Naver):
  - 더 이상 테마 필터를 쓰지 않으므로 두 노드를 disabled=true로 비활성화(불필요한 네이버 크롤링 방지)

주의:
- export_n8n_executions.py 의 API_KEY를 사용합니다.
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


def _disable_node(node: Dict[str, Any]) -> None:
    node["disabled"] = True


def _disable_theme_filter_in_scanner(code: str, kind: str) -> str:
    original = code

    # 1) themeFilterMode/themeSet 선언이 있으면 themeSet을 무조건 빈 Set으로
    # 예: const themeFilterMode = ...; const themeSet = (...)? new Set(): new Set(...)
    code = re.sub(
        r"\n\s*const\s+themeFilterMode\s*=\s*.*?;\s*\n\s*const\s+themeSet\s*=\s*.*?;\s*\n",
        "\n  // theme filter disabled (autofix)\n  const themeSet = new Set();\n",
        code,
        flags=re.DOTALL,
        count=1,
    )

    # 2) themeSet이 단순 선언 형태면 교체
    code = re.sub(
        r"\n\s*const\s+themeSet\s*=\s*new Set\\(\\(bl\\.themeCodes\\s*\\|\\|\\s*\\[\\]\\)\\.map\\(String\\)\\)\\s*;\s*\n",
        "\n  // theme filter disabled (autofix)\n  const themeSet = new Set();\n",
        code,
        flags=re.DOTALL,
        count=1,
    )

    # 3) 실제 제외 로직 제거: if (themeSet.has(rc)) { excludedTheme++; continue; }
    # 줄 단위로 깔끔히 제거 (현재 코드 형태: if (themeSet.has(rc)) { excludedTheme++; continue; })
    code = re.sub(
        r"^[ \t]*if\s*\(\s*themeSet\.has\(rc\)\s*\)\s*\{\s*excludedTheme\+\+;\s*continue;\s*\}\s*$",
        "    // theme filter disabled (autofix)",
        code,
        flags=re.MULTILINE,
    )

    if code == original:
        # 이미 제거돼 있거나 구조가 달라서 손댈 곳이 없을 수 있음
        return code
    return code


def main() -> None:
    api_key = _load_api_key()
    wf = _get_workflow(api_key)

    # 백업
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    Path("backups").mkdir(exist_ok=True)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_theme_off_before.json").write_text(
        json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    nodes: List[Dict[str, Any]] = wf.get("nodes") or []

    # 스캐너 코드 패치
    scalping = _find_node(nodes, "Scalping Scanner")
    swing = _find_node(nodes, "Swing Scanner")

    s_code = (scalping.get("parameters") or {}).get("functionCode") or ""
    w_code = (swing.get("parameters") or {}).get("functionCode") or ""

    scalping.setdefault("parameters", {})["functionCode"] = _disable_theme_filter_in_scanner(s_code, "scalping")
    swing.setdefault("parameters", {})["functionCode"] = _disable_theme_filter_in_scanner(w_code, "swing")

    # 테마 수집 노드 비활성화(불필요한 네이버 호출 방지)
    try:
        _disable_node(_find_node(nodes, "Blacklist Theme Refresh (Sun 08:30)"))
    except RuntimeError:
        pass
    try:
        _disable_node(_find_node(nodes, "Refresh Theme Blacklist (Naver)"))
    except RuntimeError:
        pass

    wf["nodes"] = nodes

    updated = _update_workflow(api_key, wf)
    Path(f"backups/n8n_workflow_{WORKFLOW_ID}_{ts}_theme_off_after.json").write_text(
        json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("OK: theme filter disabled.")


if __name__ == "__main__":
    main()



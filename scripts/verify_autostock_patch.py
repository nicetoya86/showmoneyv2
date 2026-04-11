"""
Autostock 워크플로우 패치 적용 여부 검증 스크립트
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import requests


WORKFLOW_ID = "ScHaeFdneOoH1ZNZ"
N8N_BASE_URL = "https://fastlane12.app.n8n.cloud/api/v1"


def load_api_key() -> str:
    text = Path("export_n8n_executions.py").read_text(encoding="utf-8")
    m = re.search(r'^\s*API_KEY\s*=\s*"([^"]+)"\s*$', text, flags=re.MULTILINE)
    if not m:
        raise RuntimeError("API_KEY not found in export_n8n_executions.py")
    return m.group(1)


def main() -> None:
    api_key = load_api_key()
    headers = {"X-N8N-API-KEY": api_key, "Accept": "application/json"}
    wf = requests.get(f"{N8N_BASE_URL}/workflows/{WORKFLOW_ID}", headers=headers, timeout=60).json()

    node_by_name = {n.get("name"): n for n in (wf.get("nodes") or [])}
    conns = wf.get("connections") or {}

    def has_node(name: str) -> bool:
        return name in node_by_name

    def has_marker(node: str, marker: str) -> bool:
        n = node_by_name.get(node) or {}
        code = ((n.get("parameters") or {}).get("functionCode")) or ""
        return marker in code

    print("workflow_name:", wf.get("name"))
    print("watchdog_cron:", has_node("Swing Watchdog Trigger (09:12)"))
    print("watchdog_fn:", has_node("Swing Watchdog + Backup"))
    print("watchdog_cron_conn:", json.dumps(conns.get("Swing Watchdog Trigger (09:12)"), ensure_ascii=False)[:300])
    print("watchdog_fn_conn:", json.dumps(conns.get("Swing Watchdog + Backup"), ensure_ascii=False)[:300])
    print("risk_guard:", has_marker("Refresh Risk Blacklist (KRX+KIND)", "SAFE GUARD (autofix)"))
    print("scalping_krx_cache:", has_marker("Scalping Scanner", "autofix_krx_cache"))
    print("swing_krx_cache:", has_marker("Swing Scanner", "autofix_krx_cache"))
    print("swing_guard:", has_marker("Swing Scanner", "autofix_swing_guard"))


if __name__ == "__main__":
    main()






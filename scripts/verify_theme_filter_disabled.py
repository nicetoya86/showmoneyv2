"""
테마(네이버) 기반 종목 필터 제거 적용 여부 검증
"""

from __future__ import annotations

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
    node_by = {n.get("name"): n for n in (wf.get("nodes") or [])}

    def code_of(name: str) -> str:
        n = node_by.get(name) or {}
        return ((n.get("parameters") or {}).get("functionCode")) or ""

    scalping = code_of("Scalping Scanner")
    swing = code_of("Swing Scanner")

    theme_cron = node_by.get("Blacklist Theme Refresh (Sun 08:30)") or {}
    theme_fn = node_by.get("Refresh Theme Blacklist (Naver)") or {}

    print("scalping_has_themeFilterMode:", "themeFilterMode" in scalping)
    print("swing_has_themeFilterMode:", "themeFilterMode" in swing)
    print("scalping_has_themeSet_has:", "themeSet.has(" in scalping)
    print("swing_has_themeSet_has:", "themeSet.has(" in swing)
    print("theme_cron_disabled:", theme_cron.get("disabled"))
    print("theme_fn_disabled:", theme_fn.get("disabled"))


if __name__ == "__main__":
    main()






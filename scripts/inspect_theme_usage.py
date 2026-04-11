"""
Scalping/Swing Scanner 코드에서 themeSet.has(...)가 실제로 어떤 형태로 남아있는지
주변 컨텍스트를 출력해 확인하는 도구.
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


def get_code(node_name: str) -> str:
    api_key = load_api_key()
    headers = {"X-N8N-API-KEY": api_key, "Accept": "application/json"}
    wf = requests.get(f"{N8N_BASE_URL}/workflows/{WORKFLOW_ID}", headers=headers, timeout=60).json()
    for n in wf.get("nodes") or []:
        if n.get("name") == node_name:
            return ((n.get("parameters") or {}).get("functionCode")) or ""
    raise RuntimeError(f"Node not found: {node_name}")


def show_context(code: str, needle: str, radius: int = 240) -> None:
    idx = code.find(needle)
    if idx < 0:
        print("NOT FOUND:", needle)
        return
    start = max(0, idx - radius)
    end = min(len(code), idx + radius)
    snippet = code[start:end]
    print(snippet.replace("\n", "\\n"))


def main() -> None:
    for node in ["Scalping Scanner", "Swing Scanner"]:
        code = get_code(node)
        print("===", node, "===")
        print("has themeSet.has:", "themeSet.has(" in code)
        show_context(code, "themeSet.has(")


if __name__ == "__main__":
    main()






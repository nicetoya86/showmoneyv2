"""
n8n Cloud에 올라간 워크플로우에서 특정 노드의 functionCode를 로컬 파일로 덤프.
PowerShell 인용 문제를 피하기 위해 별도 스크립트로 제공.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import requests


WORKFLOW_ID = "ScHaeFdneOoH1ZNZ"
N8N_BASE_URL = "https://fastlane12.app.n8n.cloud/api/v1"

TARGET_NODES = [
    "Daily Healthcheck",
    "Scalping Scanner",
    "Swing Scanner",
    "Refresh Risk Blacklist (KRX+KIND)",
    "Swing Watchdog + Backup",
]


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
    nodes: List[Dict[str, Any]] = wf.get("nodes") or []
    node_by = {n.get("name"): n for n in nodes}

    out_dir = Path("debug_dump")
    out_dir.mkdir(exist_ok=True)
    (out_dir / "workflow_meta.json").write_text(
        json.dumps({"id": wf.get("id"), "name": wf.get("name"), "updatedAt": wf.get("updatedAt")}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for name in TARGET_NODES:
        n = node_by.get(name)
        if not n:
            (out_dir / f"{name}.missing.txt").write_text("MISSING\n", encoding="utf-8")
            continue
        code = ((n.get("parameters") or {}).get("functionCode")) or ""
        meta = {"name": n.get("name"), "id": n.get("id"), "type": n.get("type"), "disabled": n.get("disabled", False)}
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("_")
        (out_dir / f"{safe}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / f"{safe}.js").write_text(code, encoding="utf-8")
    print("OK: dumped to debug_dump/")


if __name__ == "__main__":
    main()






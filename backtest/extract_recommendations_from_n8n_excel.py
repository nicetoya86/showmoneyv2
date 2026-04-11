from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests


def _env(name: str) -> Optional[str]:
    v = os.environ.get(name)
    return v.strip() if v and v.strip() else None


def _pick_time_kst(row: pd.Series) -> str:
    # expects export_n8n_executions.py output column
    return str(row.get("시작 시간 (KST)", "") or row.get("startedAt", "") or "")


def _fetch_execution(
    base_url: str,
    api_key: str,
    execution_id: str,
    *,
    timeout_s: int = 25,
) -> Dict[str, Any]:
    headers = {"X-N8N-API-KEY": api_key, "Accept": "application/json"}
    url = f"{base_url.rstrip('/')}/executions/{execution_id}"
    r = requests.get(url, headers=headers, params={"includeData": "true"}, timeout=timeout_s)
    r.raise_for_status()
    return r.json()


def _extract_sent(run_data: Dict[str, Any], node_name: str) -> List[str]:
    """
    Extract json.sentTickers from n8n runData for a node.
    Works with the existing pattern used in fetch_recommendations.py.
    """
    if node_name not in run_data:
        return []
    out: List[str] = []
    node_data = run_data[node_name]
    for output in node_data:
        data = output.get("data") or {}
        main = data.get("main") or []
        for items in main:
            for item in items:
                j = item.get("json") or {}
                sent = j.get("sentTickers") or []
                for t in sent:
                    if t and t not in out:
                        out.append(str(t))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True, help="Excel file from export_n8n_executions.py")
    ap.add_argument("--out", default="recommendations_export.json", help="Output JSON file")
    ap.add_argument("--base-url", default=_env("N8N_BASE_URL") or "https://fastlane12.app.n8n.cloud/api/v1")
    ap.add_argument("--api-key", default=_env("N8N_API_KEY") or "")
    ap.add_argument("--max", type=int, default=200, help="Max executions to inspect")
    ap.add_argument("--sleep-ms", type=int, default=200, help="Sleep between API calls (ms)")
    ap.add_argument("--days", type=int, default=14, help="Only include executions within last N days (by KST start time)")
    args = ap.parse_args()

    if not args.api_key:
        raise SystemExit(
            "N8N API 키가 필요합니다. 환경변수 N8N_API_KEY를 설정하거나 --api-key로 전달하세요."
        )

    df = pd.read_excel(args.excel)
    if "실행 ID" not in df.columns:
        raise SystemExit("엑셀에 '실행 ID' 컬럼이 없습니다. export_n8n_executions.py로 추출한 파일이 맞는지 확인해주세요.")

    # recent filter (KST)
    if args.days and args.days > 0 and "시작 시간 (KST)" in df.columns:
        df["_kst"] = pd.to_datetime(df["시작 시간 (KST)"], errors="coerce")
        cutoff = datetime.now() - timedelta(days=int(args.days))
        df = df[df["_kst"].notna() & (df["_kst"] >= cutoff)]

    df = df.sort_values("시작 시간 (KST)", ascending=False) if "시작 시간 (KST)" in df.columns else df
    df = df.head(int(args.max))

    results: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        execution_id = str(row["실행 ID"])
        try:
            data = _fetch_execution(args.base_url, args.api_key, execution_id)
            run_data = ((data.get("data") or {}).get("resultData") or {}).get("runData") or {}

            scalping = _extract_sent(run_data, "Scalping Scanner")
            swing = _extract_sent(run_data, "Swing Scanner")
            if not scalping and not swing:
                continue

            results.append(
                {
                    "executionId": execution_id,
                    "startedAtKST": _pick_time_kst(row),
                    "scalpingTickers": scalping,
                    "swingTickers": swing,
                }
            )
        except Exception as e:
            results.append({"executionId": execution_id, "error": str(e)})
        time.sleep(max(0.0, float(args.sleep_ms) / 1000.0))

    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out} (items={len(results)})")


if __name__ == "__main__":
    main()


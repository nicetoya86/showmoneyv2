import argparse
import json
from typing import Any, Dict, List


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    ap.add_argument("substring")
    args = ap.parse_args()

    with open(args.json_path, "r", encoding="utf-8") as f:
        data: Dict[str, Any] = json.load(f)

    nodes: List[Dict[str, Any]] = data.get("nodes", [])
    hits = []

    for n in nodes:
        params = n.get("parameters") or {}
        for key in ("functionCode", "jsCode"):
            code = params.get(key)
            if isinstance(code, str) and args.substring in code:
                hits.append((n.get("name"), n.get("type"), key, len(code)))

    print("hits", len(hits))
    for name, typ, key, ln in hits:
        print(f"- {name} | {typ} | {key} | len={ln}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())








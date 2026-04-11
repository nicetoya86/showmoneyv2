import argparse
import json
import os
import re
from typing import List, Dict, Any, Tuple


DESIRED_2026: List[str] = [
    "2026-01-01",
    "2026-02-16",
    "2026-02-17",
    "2026-02-18",
    "2026-03-01",
    "2026-03-02",
    "2026-05-05",
    "2026-05-24",
    "2026-05-25",
    "2026-06-03",
    "2026-06-06",
    "2026-08-15",
    "2026-08-17",
    "2026-09-24",
    "2026-09-25",
    "2026-09-26",
    "2026-10-03",
    "2026-10-05",
    "2026-10-09",
    "2026-12-25",
]


DATE_RE = re.compile(r"'(\d{4}-\d{2}-\d{2})'")
HOLIDAYS_DECL_RE = re.compile(r"const\s+HOLIDAYS\s*=\s*\[(.*?)\];", re.DOTALL)


def uniq_keep_order(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in seq:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def rebuild_holidays_const_keep_2025(code: str) -> Tuple[str, bool]:
    """
    For nodes that already have `const HOLIDAYS = [...]`:
    - Keep existing non-2026 dates as-is (practically: 2025 list)
    - Replace ALL 2026 dates with exactly DESIRED_2026 (user-provided only)
    """
    m = HOLIDAYS_DECL_RE.search(code)
    if not m:
        return code, False

    existing = DATE_RE.findall(m.group(1))
    keep_non_2026 = [d for d in existing if not d.startswith("2026-")]
    rebuilt = uniq_keep_order(keep_non_2026 + DESIRED_2026)
    arr = ",".join([f"'{d}'" for d in rebuilt])
    new_decl = f"const HOLIDAYS = [{arr}];"
    new_code = code[: m.start()] + new_decl + code[m.end() :]
    return new_code, True


def insert_after_first_line_containing(code: str, needle: str, insert_block: str) -> Tuple[str, bool]:
    lines = code.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            lines.insert(i + 1, insert_block.rstrip("\n"))
            return "\n".join(lines), True
    return code, False


def ensure_weekly_reporter_skips_on_holiday(code: str) -> Tuple[str, bool]:
    if "Holiday (KRX closed)" in code:
        return code, False

    block = (
        "  const today = `${kst.getUTCFullYear()}-${String(kst.getUTCMonth()+1).padStart(2,'0')}-${String(kst.getUTCDate()).padStart(2,'0')}`;\n"
        "  if (HOLIDAYS.includes(today)) return [{ json: { skipped: true, reason: 'Holiday (KRX closed)', today } }];"
    )

    # Insert right after `const kst = ...;`
    return insert_after_first_line_containing(code, "const kst =", block)


def ensure_healthcheck_skips_on_holiday(code: str) -> Tuple[str, bool]:
    if "HOLIDAYS_2026" in code:
        return code, False

    arr = ",".join([f"'{d}'" for d in DESIRED_2026])
    block = (
        f"  const HOLIDAYS_2026 = [{arr}];\n"
        "  if (HOLIDAYS_2026.includes(today)) {\n"
        "    return [{ json: { skipped: true, reason: 'Holiday (KRX closed)', today, timeKst } }];\n"
        "  }"
    )

    # Insert right after `const timeKst = ...;`
    return insert_after_first_line_containing(code, "const timeKst =", block)


def ensure_scalping_node_skips_on_holiday(code: str) -> Tuple[str, bool]:
    if "HOLIDAYS_2026" in code or "Holiday (KRX closed)" in code:
        return code, False

    arr = ",".join([f"'{d}'" for d in DESIRED_2026])
    block = (
        f"const HOLIDAYS_2026 = [{arr}];\n"
        "const nowKrx = new Date();\n"
        "const kstKrx = new Date(nowKrx.getTime() + 9*60*60*1000);\n"
        "const todayKrx = `${kstKrx.getUTCFullYear()}-${String(kstKrx.getUTCMonth()+1).padStart(2,'0')}-${String(kstKrx.getUTCDate()).padStart(2,'0')}`;\n"
        "if (HOLIDAYS_2026.includes(todayKrx)) {\n"
        "  return [{ json: { skipped: true, reason: 'Holiday (KRX closed)', today: todayKrx } }];\n"
        "}\n"
    )

    # Prefer inserting after blacklist init line
    code2, ok = insert_after_first_line_containing(code, "if (!store.blacklist) store.blacklist = {};", block)
    if ok:
        return code2, True

    # Fallback: insert at top
    return block + "\n" + code, True


def find_node(nodes: List[Dict[str, Any]], name: str) -> Dict[str, Any] | None:
    for n in nodes:
        if n.get("name") == name:
            return n
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="Input n8n workflow JSON path")
    ap.add_argument(
        "--output",
        help="Output path (default: add ' + Holidays2026' before .json)",
        default=None,
    )
    args = ap.parse_args()

    input_path = args.input
    if not os.path.exists(input_path):
        raise SystemExit(f"Input file not found: {input_path}")

    if args.output:
        output_path = args.output
    else:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base} + Holidays2026{ext or '.json'}"

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    if not isinstance(nodes, list):
        raise SystemExit("Invalid workflow JSON: nodes is not a list")

    touched = []

    # 1) Swing Scanner: replace HOLIDAYS 2026 portion only (keep existing 2025)
    swing = find_node(nodes, "Swing Scanner")
    if swing and isinstance(swing.get("parameters", {}).get("functionCode"), str):
        code = swing["parameters"]["functionCode"]
        new_code, changed = rebuild_holidays_const_keep_2025(code)
        if changed:
            swing["parameters"]["functionCode"] = new_code
            touched.append("Swing Scanner (HOLIDAYS updated)")

    # 2) Weekly Reporter: extend HOLIDAYS + add skip-on-holiday for trigger day (e.g., 2026-09-26)
    weekly = find_node(nodes, "Weekly Reporter")
    if weekly and isinstance(weekly.get("parameters", {}).get("functionCode"), str):
        code = weekly["parameters"]["functionCode"]
        code, changed1 = rebuild_holidays_const_keep_2025(code)
        code, changed2 = ensure_weekly_reporter_skips_on_holiday(code)
        if changed1 or changed2:
            weekly["parameters"]["functionCode"] = code
            touched.append("Weekly Reporter (HOLIDAYS updated + holiday skip)")

    # 3) Daily Healthcheck: add holiday skip (user requested)
    health = find_node(nodes, "Daily Healthcheck")
    if health and isinstance(health.get("parameters", {}).get("functionCode"), str):
        code = health["parameters"]["functionCode"]
        code, changed = ensure_healthcheck_skips_on_holiday(code)
        if changed:
            health["parameters"]["functionCode"] = code
            touched.append("Daily Healthcheck (holiday skip)")

    # 4) Scalping Scanner (단타 노드): add holiday skip (user requested)
    scalping = find_node(nodes, "Scalping Scanner")
    if scalping and isinstance(scalping.get("parameters", {}).get("functionCode"), str):
        code = scalping["parameters"]["functionCode"]
        code, changed = ensure_scalping_node_skips_on_holiday(code)
        if changed:
            scalping["parameters"]["functionCode"] = code
            touched.append("Scalping Scanner (holiday skip)")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("OK: wrote", output_path)
    if touched:
        print("Updated nodes:")
        for t in touched:
            print("-", t)
    else:
        print("No changes were applied (nodes not found or already updated).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())








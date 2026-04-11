import json
from pathlib import Path

p = Path(r"D:\vibecording\showmoneyv2\Autostock Complete (v2.1 - 09_10 Start) + Blacklist + Holidays2026 (UserDates) + FixedScalpingTheme.json")
wf = json.loads(p.read_text(encoding="utf-8"))

nodes = wf.get("nodes", [])
if isinstance(nodes, dict):
    nodes = list(nodes.values())

scalping = None
refresh_theme = None
for n in nodes:
    name = str(n.get("name", ""))
    if name == "Scalping Scanner":
        scalping = n
    if ("refresh" in name.lower()) and ("theme" in name.lower()):
        refresh_theme = n

out_dir = p.parent

def dump_node(n, filename):
    if not n:
        print("missing", filename)
        return
    fc = ((n.get("parameters") or {}).get("functionCode")) or ""
    meta = {"id": n.get("id"), "name": n.get("name"), "type": n.get("type")}
    (out_dir / filename).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n\n" + fc, encoding="utf-8")
    print("wrote", filename, "len", len(fc))

dump_node(scalping, "dump_scalping_scanner.txt")
dump_node(refresh_theme, "dump_refresh_theme.txt")

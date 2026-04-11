import json
from datetime import datetime

SCALPING_NODES = [
    'Scalping Trigger (10',
    'Scalping Scanner',
    'Scalping Config',
    'Holiday Gate (Scalping Trigger)',
]

with open('swing_scanner_code.js', 'r', encoding='utf-8') as f:
    swing_code = f.read()

with open('workflow_FINAL_20260221_001629.json', 'r', encoding='utf-8') as f:
    wf = json.load(f)

disabled_nodes = []
swing_updated = 0

for node in wf.get('nodes', []):
    name = node.get('name', '')

    is_scalping = any(kw in name for kw in SCALPING_NODES)
    if is_scalping:
        node['disabled'] = True
        disabled_nodes.append(name)

    if name == 'Swing Scanner' and 'functionCode' in node.get('parameters', {}):
        node['parameters']['functionCode'] = swing_code
        swing_updated += 1

ts = datetime.now().strftime('%Y%m%d_%H%M%S')
out = 'workflow_SWING_ONLY_' + ts + '.json'
with open(out, 'w', encoding='utf-8') as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)

print('Disabled scalping nodes:', len(disabled_nodes))
for n in disabled_nodes:
    print(' -', n)
print('Swing scanner updated:', swing_updated)
print('Output:', out)

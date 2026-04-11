import json
import os
from datetime import datetime

BASE_JSON = 'workflow_SWING_ONLY_20260308_174332.json'
WEEKLY_JS = 'weekly_reporter_code.js'

# Load workflow
with open(BASE_JSON, encoding='utf-8') as f:
    wf = json.load(f)

# Load new weekly reporter code
with open(WEEKLY_JS, encoding='utf-8') as f:
    new_code = f.read()

nodes = wf.get('nodes', [])
updated = 0

for node in nodes:
    if node.get('name') == 'Weekly Reporter':
        params = node.setdefault('parameters', {})
        if 'functionCode' in params:
            params['functionCode'] = new_code
            updated += 1
        elif 'jsCode' in params:
            params['jsCode'] = new_code
            updated += 1
        else:
            # Try both
            params['functionCode'] = new_code
            updated += 1
        print(f'Updated: {node["name"]}')

if updated == 0:
    print('ERROR: Weekly Reporter node not found!')
    exit(1)

ts = datetime.now().strftime('%Y%m%d_%H%M%S')
out_file = f'workflow_WEEKLY_UPDATED_{ts}.json'

with open(out_file, 'w', encoding='utf-8') as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)

print(f'Output: {out_file}')
print(f'Nodes updated: {updated}')

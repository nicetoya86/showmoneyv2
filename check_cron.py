import json
with open(r'C:\Users\nicet\.cursor\projects\d-vibecording-showmoneyv2\agent-tools\eda2e3a4-baba-4919-92c9-d97d5dbcd328.txt', encoding='utf-8') as f:
    wf = json.load(f)
nodes = wf.get('nodes', [])
print('=== Trigger / Cron 노드 목록 ===')
for n in nodes:
    nt = n.get('type','')
    nm = n.get('name','')
    if any(k in nt.lower() for k in ['cron','schedule','trigger']) or any(k in nm.lower() for k in ['trigger','cron','schedule']):
        params = n.get('parameters',{})
        disabled = n.get('disabled', False)
        status = 'OFF' if disabled else 'ON '
        print(f'[{status}] {nm}')
        print(f'       type: {nt}')
        for key in ['rule','cronExpression','triggerTimes','pollTimes','interval']:
            val = params.get(key)
            if val:
                print(f'       {key}: {json.dumps(val, ensure_ascii=False)}')
        print()

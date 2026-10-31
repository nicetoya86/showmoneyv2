// 라이브 n8n workflow staticData.global을 읽기 전용 GET으로 가져와 상태 저장소 state.json에 시드. env: STATE_PAT
const fs = require('fs');
const { getState, snap, commit } = require('../runner/state');
(async () => {
  const key = fs.readFileSync(__dirname + '/../export_n8n_executions.py', 'utf8').match(/^\s*API_KEY\s*=\s*"([^"]+)"/m)[1];
  const r = await fetch('https://fastlane12.app.n8n.cloud/api/v1/workflows/ScHaeFdneOoH1ZNZ', { headers: { 'X-N8N-API-KEY': key } });
  if (!r.ok) throw new Error('n8n GET ' + r.status);
  const g = ((await r.json()).staticData || {}).global;
  if (!g || typeof g !== 'object') throw new Error('no staticData.global');
  const cur = await getState();
  const { keys } = await commit(snap(cur.data), g, 'seed');
  console.log('seeded keys:', Object.keys(g).length, 'bytes:', JSON.stringify(g).length, 'changed:', keys.length);
})().catch((e) => { console.error('seed err', String(e.message).slice(0, 100)); process.exit(1); });

// 러너 로컬 검증: GitHub Contents API만 인메모리 모킹, 나머지는 실제 fetch. node scripts/verify_runner.js <job>
const assert = require('assert');
let blob = Buffer.from(JSON.stringify({ a: { n: 1 }, keep: [1, 2, 3] })).toString('base64'), sha = 's1', puts = 0;
const realFetch = global.fetch;
global.fetch = async (url, o = {}) => {
  if (!/api\.github\.com/.test(url)) return realFetch(url, o);
  const res = (st, b) => ({ status: st, ok: st < 300, json: async () => b });
  if ((o.method || 'GET') === 'GET') return res(200, { content: blob, sha });
  const b = JSON.parse(o.body);
  if (b.sha !== sha) return res(409, {});
  if (puts++ === 0) { // 첫 PUT 직전 다른 잡이 먼저 커밋한 상황 재현 -> 409 후 재시도 병합 확인
    blob = Buffer.from(JSON.stringify({ a: { n: 1 }, keep: [1, 2, 3], other: 'x' })).toString('base64'); sha = 's2'; return res(409, {});
  }
  blob = b.content; sha = 's' + puts; return res(200, {});
};
process.env.STATE_PAT = 't'; process.env.BOT = '1:' + 'A'.repeat(30); process.env.CHAT = '1'; process.env.DART = 'd';
process.argv[2] = process.argv[2] || 'healthcheck';
process.on('exit', () => {
  const d = JSON.parse(Buffer.from(blob, 'base64').toString());
  console.error('final keys:', Object.keys(d).join(','), 'puts:', puts);
  assert(d.keep && d.other === 'x', 'merge must keep other job keys');
});
require('../runner/run.js');

/**
 * market-state-shadow 설계 2절 재현 점검(참고용, 게이트 아님):
 * 라이브 추천 124건(2026-10-02~16)에 같은 분류 함수로 mkt/mstate를 역산해 새 코호트 건수를 출력한다.
 * Run: node scripts/check_market_state_backfill.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { msClassify } = require('../lib/marketState');
const { shadowStateSelect } = require('../lib/shadowCohorts');

const fx = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'index_2026.json'), 'utf8'));
const recs = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'recs_2026-10-02_16.json'), 'utf8'));
const cache = new Map();
const stateFor = (mkt, date) => {
  const compact = date.replace(/-/g, '');
  const prev = [...fx[mkt]].reverse().find((b) => b.d < compact); // 직전 거래일 봉(백필이라 신선도는 자명)
  const key = mkt + date;
  if (!cache.has(key)) cache.set(key, msClassify(fx[mkt], date, prev ? prev.d : ''));
  return cache.get(key);
};
const tagged = recs.map((r) => {
  const mkt = String(r.ticker).endsWith('.KS') ? 'KOSPI' : 'KOSDAQ'; // 입력 순서 = 발송 순서
  const s = stateFor(mkt, r.date);
  return Object.assign({}, r, { mkt, mstate: s.state, mstateAsOf: s.asOfBar });
});
const expect = { ALL: 124, STATE_BLOCK: 18, STATE_PAT: 30, STATE_CAP: 18, STATE_CAP_BEST: 18, STATE_ALL: 13 };
const got = { ALL: tagged.length };
for (const n of Object.keys(expect).filter((k) => k !== 'ALL')) got[n] = shadowStateSelect(tagged, n).length;
const dist = {};
for (const r of tagged) dist[r.mkt + ':' + r.mstate] = (dist[r.mkt + ':' + r.mstate] || 0) + 1;
console.log('상태 분포:', JSON.stringify(dist));
for (const n of Object.keys(expect)) console.log(n.padEnd(15), '기대', expect[n], '실제', got[n], got[n] === expect[n] ? 'OK' : 'MISMATCH');

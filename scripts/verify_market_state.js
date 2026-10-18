/**
 * Self-check for lib/marketState.js (market-state-shadow, design §3, §8).
 * Run: node scripts/verify_market_state.js [--sensitivity]
 */
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { MS_CFG, msClassify, msFetchIndexBars } = require('../lib/marketState');

// 합성 봉: closes 배열(오래된→최신), 마지막 봉 날짜 endD('yyyyMMdd'), 하루씩 거슬러 올라가는 달력일(주말 무시 — 합성용)
const ymd = (dt) => dt.toISOString().slice(0, 10).replace(/-/g, '');
const mk = (closes, endD) => {
  const end = new Date(`${endD.slice(0, 4)}-${endD.slice(4, 6)}-${endD.slice(6, 8)}T00:00:00Z`);
  return closes.map((c, i) => ({ d: ymd(new Date(end.getTime() - (closes.length - 1 - i) * 86400000)), c }));
};
const ramp = (n, from, to) => Array.from({ length: n }, (_, i) => from + ((to - from) * i) / (n - 1));
const flat = (n, v) => Array.from({ length: n }, () => v);
const TODAY = '2026-10-07', PREV = '20261006';
const cls = (closes, endD) => msClassify(mk(closes, endD || PREV), TODAY, PREV);

// 1. 경계값 — CRASH (r5 -5.0% 정확히, dd20 -8.0% 정확히)
assert.strictEqual(cls([...flat(66, 100), 95]).state, 'CRASH');             // r5=-5.0%
assert.notStrictEqual(cls([...flat(66, 100), 95.01]).state, 'CRASH');       // r5=-4.99%, dd20=-4.99%
assert.strictEqual(cls([...flat(55, 100), ...flat(11, 92)]).state, 'CRASH');           // dd20=-8.0% (r5=0)
assert.notStrictEqual(cls([...flat(55, 100), ...flat(11, 92.1)]).state, 'CRASH');       // dd20=-7.9%
// 2. SURGE / UP / FLAT / DOWN
assert.strictEqual(cls([...flat(46, 100), ...ramp(20, 100, 108)]).state, 'SURGE'); // r20=+8.0%, MA 위
assert.strictEqual(cls([...flat(46, 100), ...ramp(20, 100, 107.9)]).state, 'UP');  // r20=+7.9%
assert.strictEqual(cls([...flat(46, 100), ...ramp(20, 100, 101.9)]).state, 'FLAT'); // r20=+1.9% (UP 아님)
assert.strictEqual(cls(flat(66, 100)).state, 'FLAT');                               // c==MA → DOWN/UP 아님
assert.strictEqual(cls([...flat(46, 100), ...ramp(20, 100, 97)]).state, 'DOWN');    // c<MA20,MA60, 낙폭 -3%
// 3. 우선순위: CRASH 조건이 DOWN 조건과 동시에 충족돼도 CRASH
assert.strictEqual(cls([...flat(50, 100), ...ramp(16, 100, 98), 96, 94, 92, 90, 88]).state, 'CRASH');
// 4. 봉 수: 60개 → UNKNOWN, 61개 → 판정
assert.strictEqual(cls(flat(60, 100)).state, 'UNKNOWN');
assert.strictEqual(cls(flat(61, 100)).state, 'FLAT');
// 5. 신선도: 마지막 봉 != expectedPrev → UNKNOWN ; 당일 진행 봉(date==today)은 무시
assert.strictEqual(msClassify(mk(flat(66, 100), '20261005'), TODAY, PREV).state, 'UNKNOWN');
const withToday = mk(flat(66, 100), PREV).concat([{ d: '20261007', c: 50 }]); // 오늘 급락 봉이 섞여 있어도
assert.strictEqual(msClassify(withToday, TODAY, PREV).state, 'FLAT');
assert.strictEqual(msClassify(withToday, TODAY, PREV).asOfBar, PREV);
// 6. 종가 0/NaN 봉 제외: 제외 후 61개 미만이면 UNKNOWN, 이상이면 판정
const zeroBars = (n) => { const b = mk(flat(n, 100), PREV); b[10].c = 0; b[20].c = NaN; return b; };
assert.strictEqual(msClassify(zeroBars(62), TODAY, PREV).state, 'UNKNOWN'); // 62-2=60
assert.strictEqual(msClassify(zeroBars(63), TODAY, PREV).state, 'FLAT');    // 63-2=61
// 7. 연휴: 마지막 봉 10/02, today 10/06(10/05 대체휴일), expectedPrev 20261002 → 정상 판정
assert.strictEqual(msClassify(mk(flat(66, 100), '20261002'), '2026-10-06', '20261002').state, 'FLAT');
// 8. 입력이 비정상(null/빈 배열)이어도 던지지 않는다
assert.strictEqual(msClassify(null, TODAY, PREV).state, 'UNKNOWN');
assert.strictEqual(msClassify([], TODAY, PREV).state, 'UNKNOWN');

// 9. 실데이터 회귀 — 분석(reg4.py)의 "봉 날짜 기준 상태"와 동일해야 함
const fx = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'index_2026.json'), 'utf8'));
const real = (mkt, today, prev) => msClassify(fx[mkt], today, prev).state;
assert.strictEqual(real('KOSPI', '2026-10-06', '20261002'), 'UP');
assert.strictEqual(real('KOSDAQ', '2026-10-06', '20261002'), 'SURGE');
assert.strictEqual(real('KOSDAQ', '2026-10-07', '20261006'), 'SURGE');
assert.strictEqual(real('KOSPI', '2026-10-12', '20261008'), 'DOWN');
assert.strictEqual(real('KOSPI', '2026-10-13', '20261012'), 'CRASH');
assert.strictEqual(real('KOSDAQ', '2026-10-13', '20261012'), 'CRASH');

// 10. msFetchIndexBars — 주입 http: throw / 빈 문자열 / BOM+JSON 문자열 / 정상 배열 / 네이버 빈 응답+야후 폴백
(async () => {
  const naverRows = [{ localDate: '20261002', closePrice: '7003.74' }, { localDate: '20261001', closePrice: 6971.35 }];
  const asc = [{ d: '20261001', c: 6971.35 }, { d: '20261002', c: 7003.74 }];
  assert.deepStrictEqual(await msFetchIndexBars(async () => { throw new Error('boom'); }, 'KOSPI', '2026-10-06'), []);
  assert.deepStrictEqual(await msFetchIndexBars(async () => '', 'KOSPI', '2026-10-06'), []);
  assert.deepStrictEqual(await msFetchIndexBars(async () => '﻿' + JSON.stringify(naverRows), 'KOSPI', '2026-10-06'), asc);
  assert.deepStrictEqual(await msFetchIndexBars(async () => ({ body: naverRows }), 'KOSPI', '2026-10-06'), asc);
  const yahoo = { chart: { result: [{ timestamp: [1759276800, 1759363200], indicators: { quote: [{ close: [6971.35, 7003.74] }] } }] } };
  const viaYahoo = await msFetchIndexBars(async (o) => (String(o.url).includes('yahoo') ? yahoo : []), 'KOSPI', '2026-10-06');
  assert.strictEqual(viaYahoo.length, 2);
  assert.strictEqual(viaYahoo[1].c, 7003.74);

  if (process.argv.includes('--sensitivity')) {
    // 경계값 ±1%p 민감도 — 표만 출력(판정은 사람). 대상: 픽스처 지수, 마지막 봉 직전까지 매일.
    const variants = { base: MS_CFG };
    for (const k of ['crashR5', 'crashDd20', 'surgeR20', 'upR20']) {
      variants[k + ' +1pp'] = Object.assign({}, MS_CFG, { [k]: MS_CFG[k] + 0.01 });
      variants[k + ' -1pp'] = Object.assign({}, MS_CFG, { [k]: MS_CFG[k] - 0.01 });
    }
    for (const mkt of ['KOSPI', 'KOSDAQ']) {
      console.log(`\n[${mkt}] 상태 분포 (일수)`);
      for (const [name, cfg] of Object.entries(variants)) {
        const cnt = {};
        for (let i = 61; i < fx[mkt].length; i++) {
          const s = msClassify(fx[mkt].slice(0, i), 'x', fx[mkt][i - 1].d, cfg).state;
          cnt[s] = (cnt[s] || 0) + 1;
        }
        console.log(name.padEnd(16), JSON.stringify(cnt));
      }
    }
  }
  console.log('verify_market_state: ALL PASS');
})().catch((e) => { console.error(e); process.exit(1); });

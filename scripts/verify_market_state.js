/**
 * Self-check for lib/marketState.js (market-state-shadow, design §3, §8).
 * Run: node scripts/verify_market_state.js [--sensitivity]
 */
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { MS_CFG, msClassify, msFetchIndexBars, msLoadStates } = require('../lib/marketState');

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

  // 11. msLoadStates — 하루 1회 캐시, UNKNOWN은 캐시하지 않고 재시도, 예외 전파 없음
  const naverFmt = (bars) => bars.map((b) => ({ localDate: b.d, closePrice: String(b.c) }));
  const mkHttp = (rows) => { const h = async () => { h.calls++; return rows; }; h.calls = 0; return h; };
  const good = mkHttp(naverFmt(mk(flat(80, 100), PREV)));
  const store = {};
  const ok1 = await msLoadStates(good, store, TODAY, PREV);
  assert.strictEqual(ok1.KOSPI.state, 'FLAT');
  assert.strictEqual(ok1.KOSDAQ.state, 'FLAT');
  assert.strictEqual(store.marketStateCache.date, TODAY);
  const callsAfterFirst = good.calls;
  const ok2 = await msLoadStates(good, store, TODAY, PREV);          // 같은 날 재호출 → 캐시 히트
  assert.strictEqual(good.calls, callsAfterFirst);
  assert.strictEqual(ok2.KOSDAQ.state, 'FLAT');
  const tomorrow = await msLoadStates(good, store, '2026-10-08', '20261007'); // 날짜가 바뀌면 캐시 무효 → 재조회(봉이 오래돼 UNKNOWN)
  assert.ok(good.calls > callsAfterFirst);
  assert.strictEqual(tomorrow.KOSPI.state, 'UNKNOWN');
  const stale = mkHttp(naverFmt(mk(flat(80, 100), '20261002')));      // 마지막 봉이 expectedPrev가 아님
  const st2 = {};
  assert.strictEqual((await msLoadStates(stale, st2, TODAY, PREV)).KOSPI.state, 'UNKNOWN');
  const c1 = stale.calls;
  await msLoadStates(stale, st2, TODAY, PREV);
  assert.ok(stale.calls > c1, 'UNKNOWN은 캐시하지 않고 다음 호출에서 재시도');
  const boom = async () => { throw new Error('network down'); };
  const rb = await msLoadStates(boom, {}, TODAY, PREV);               // 예외 전파 없음
  assert.strictEqual(rb.KOSPI.state, 'UNKNOWN');
  assert.strictEqual(rb.KOSDAQ.state, 'UNKNOWN');
  const noStore = await msLoadStates(good, undefined, TODAY, PREV);   // store 없어도 동작
  assert.strictEqual(noStore.KOSPI.state, 'FLAT');

  // 11b. 발송 경로 보호(리뷰 지적): 두 시장 조회는 동시에, 응답이 없어도 timeoutMs 안에 반환
  const slow = async () => { slow.calls++; await new Promise((r) => setTimeout(r, 120)); return naverFmt(mk(flat(80, 100), PREV)); };
  slow.calls = 0;
  const t0 = Date.now();
  const rs = await msLoadStates(slow, {}, TODAY, PREV);
  assert.strictEqual(rs.KOSPI.state, 'FLAT');
  assert.ok(Date.now() - t0 < 220, `두 시장 조회는 병렬이어야 함 (elapsed ${Date.now() - t0}ms)`);
  const hang = () => new Promise(() => {});                          // 영원히 응답 없음
  const t1 = Date.now();
  const rh = await msLoadStates(hang, {}, TODAY, PREV, { timeoutMs: 60 });
  assert.ok(Date.now() - t1 < 500, `timeoutMs 내 반환 (elapsed ${Date.now() - t1}ms)`);
  assert.strictEqual(rh.KOSPI.state, 'UNKNOWN');
  assert.strictEqual(rh.KOSDAQ.state, 'UNKNOWN');
  let seenTimeout = null;
  await msFetchIndexBars(async (o) => { seenTimeout = o.timeout; return []; }, 'KOSPI', TODAY);
  assert.ok(seenTimeout > 0 && seenTimeout <= 10000, 'http 호출에 짧은 개별 timeout을 건다(스캐너 기본 45s 덮어쓰기)');

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
  // 12. 소스 배선: 스캐너가 상태 필드 4개를 기록하고 조회는 try/catch 안에 있다(발송 경로 보호)
  const scanner = fs.readFileSync(path.join(__dirname, '../src/swing-scanner.src.js'), 'utf8');
  assert.ok(/require\('\.\.\/lib\/marketState'\)/.test(scanner), 'scanner lib require');
  assert.ok(/try \{ msStates = await msLoadStates\(http, store, today, getPrevTradingDay\(today\)\); \} catch/.test(scanner), 'scanner try/catch');
  for (const f of ['mkt:', 'mstate:', 'mstateAsOf:', 'sentAt: Date.now()']) assert.ok(scanner.includes(f), 'scanner field ' + f);
  console.log('verify_market_state: ALL PASS');
})().catch((e) => { console.error(e); process.exit(1); });

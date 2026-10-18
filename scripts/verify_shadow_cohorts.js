/**
 * Self-check for lib/shadowCohorts.js (volume5x-pattern-cap-shadow, design §7).
 * Run: node scripts/verify_shadow_cohorts.js
 */
'use strict';
const assert = require('assert');
const {
  SHADOW_CFG, shadowIsComposite, shadowSelect, shadowStats, computeShadowCohorts, shadowGate,
  shadowStateSelect, computeShadowStateCohorts, shadowStateGate, shadowStateSummary, shadowFormatStateSection,
  SHADOW_STATE_COHORTS, SHADOW_STATE_GATE_COHORTS,
} = require('../lib/shadowCohorts');

const rec = (o) => Object.assign({
  date: '2026-10-01', patternType: 'C촉매', score: 100, signals: ['촉매이벤트'], rvol: 6,
  result: 'loss', targetPct: 0.10, stopPct: -0.04, finalReturn: 0, expiredForced: false,
}, o);

// 1. 복합 판정 + NOCOMP
const comp = rec({ signals: ['박스권돌파', '촉매이벤트', '복합C+D'] });
const plain = rec({});
assert.strictEqual(shadowIsComposite(comp), true);
assert.strictEqual(shadowIsComposite(plain), false);
assert.strictEqual(shadowIsComposite({}), false); // signals 없음
assert.deepStrictEqual(shadowSelect([comp, plain], 'NOCOMP'), [plain]);

// 2. 캡 look-ahead 방지: 1순위가 holding이어도 선정에는 포함, 통계에서만 제외
const d1 = rec({ patternType: 'D박스', score: 90, result: 'holding' });
const c1 = rec({ patternType: 'C촉매', score: 200, result: 'win' });
const c2 = rec({ patternType: 'C촉매', score: 150, result: 'loss' });
const a1 = rec({ patternType: 'A눌림목', score: 300, result: 'win' });
const sel = shadowSelect([a1, c2, d1, c1], 'CAP2');
assert.deepStrictEqual(sel, [d1, c1]); // D(holding) → C(score 200); C(150), A 제외
const st = shadowStats(sel, 'CAP2');
assert.strictEqual(st.n, 2);
assert.strictEqual(st.closed, 1); // holding 제외
assert.strictEqual(st.win, 1);

// 3. 우선순위 D>C>B>A, 동순위 score 내림차순, 날짜별 독립
const day2 = rec({ date: '2026-10-02', patternType: 'A눌림목', score: 50 });
const sel3 = shadowSelect([rec({ patternType: 'B지지선', score: 80 }), rec({ patternType: 'D박스', score: 70 }),
  rec({ patternType: 'D박스', score: 95 }), day2], 'CAP2');
assert.deepStrictEqual(sel3.map((r) => r.patternType + r.score), ['D박스95', 'D박스70', 'A눌림목50']);

// 4. NOCOMP+CAP2: 복합 먼저 제외 후 캡 → 복합이 슬롯을 차지하지 않음
const compD = rec({ patternType: 'D박스', score: 500, signals: ['박스권돌파', '촉매이벤트', '복합C+D'] });
const sel4 = shadowSelect([compD, c1, c2], 'NOCOMP+CAP2');
assert.deepStrictEqual(sel4, [c1, c2]);

// 5. rvol null/누락 혼재: RVOL5 제외 + missing 카운트, 타 코호트 불변
const all5 = [rec({ rvol: 8 }), rec({ rvol: 4.9 }), rec({ rvol: null }), rec({ rvol: undefined }), rec({ rvol: 5 })];
const co5 = computeShadowCohorts(all5);
assert.strictEqual(co5.RVOL5.n, 2); // 8, 5 (경계 포함)
assert.strictEqual(co5.RVOL5.missing, 2);
assert.strictEqual(co5.ALL.n, 5);
assert.strictEqual(co5.NOCOMP.n, 5);

// 6. avgRet: win=targetPct, 만기청산 win=finalReturn, partial/loss=stopPct
const s6 = shadowStats([
  rec({ result: 'win', targetPct: 0.10 }),
  rec({ result: 'win', targetPct: 0.10, expiredForced: true, finalReturn: 0.02 }),
  rec({ result: 'partial_win', stopPct: 0.01 }),
  rec({ result: 'loss', stopPct: -0.04 }),
], 'x');
assert.strictEqual(s6.closed, 4);
assert.strictEqual(s6.win, 2);
assert.strictEqual(s6.part, 1);
assert.strictEqual(s6.loss, 1);
assert.strictEqual(s6.winPct, 50);
assert.strictEqual(s6.wpPct, 75);
assert.strictEqual(s6.avgRet, +((0.10 + 0.02 + 0.01 - 0.04) / 4 * 100).toFixed(2)); // 2.25

// 7. 빈 입력 / 이월만 있는 입력 / undefined
for (const bad of [[], undefined, null, [rec({ carryOver: true })]]) {
  const c = computeShadowCohorts(bad);
  assert.strictEqual(c.ALL.n, 0);
  assert.strictEqual(c.ALL.closed, 0);
  assert.strictEqual(c.ALL.winPct, 0);
  assert.strictEqual(c.CAP2.n, 0);
}

// 8. shadowGate: n<30 또는 주 수<3 → 불통과 / 충족 시 통과
const wk = (allWin, allClosed, cWin, cClosed, cAvg, allAvg) => ({
  ALL: { win: allWin, closed: allClosed, winPct: +(100 * allWin / allClosed).toFixed(1), avgRet: allAvg },
  NOCOMP: { win: cWin, closed: cClosed, winPct: +(100 * cWin / cClosed).toFixed(1), avgRet: cAvg },
  CAP2: { win: 0, closed: 0, winPct: 0, avgRet: 0 }, 'NOCOMP+CAP2': { win: 0, closed: 0, winPct: 0, avgRet: 0 },
  RVOL5: { win: 0, closed: 0, winPct: 0, avgRet: 0 },
});
const g1 = shadowGate({ '2026-10-05': wk(10, 40, 12, 30, 2, 1) });
assert.strictEqual(g1.NOCOMP.passN, true);      // 30 >= 30
assert.strictEqual(g1.NOCOMP.passWeeks, false); // 1주 < 3주
const g3 = shadowGate({
  '2026-10-05': wk(10, 40, 12, 30, 2, 1),   // 30% vs 40% (+10) 양
  '2026-10-12': wk(10, 40, 11, 30, 2, 1),   // 25% vs 36.7% 양
  '2026-10-19': wk(10, 40, 7, 30, 0.5, 1),  // 25% vs 23.3% 평균 하락 → 음
});
assert.strictEqual(g3.NOCOMP.weeks, 3);
assert.strictEqual(g3.NOCOMP.weeksPositive, 2);
assert.strictEqual(g3.NOCOMP.passWeeks, true);
assert.strictEqual(g3.NOCOMP.passN, true);      // 90 확정
assert.strictEqual(g3.NOCOMP.passGain, true);   // 풀링 승률 차 +4%p 이상
assert.strictEqual(g3.CAP2.passN, false);
assert.deepStrictEqual(shadowGate(undefined).NOCOMP, { closedTotal: 0, weeks: 0, weeksPositive: 0, pooledWinGain: 0, passN: false, passWeeks: false, passGain: false });

// 9. 불변성: 입력 변형 없음
const input = [rec({ patternType: 'A눌림목', score: 10 }), rec({ patternType: 'D박스', score: 5 }), comp];
const snapshot = JSON.parse(JSON.stringify(input));
computeShadowCohorts(input);
assert.deepStrictEqual(JSON.parse(JSON.stringify(input)), snapshot);

// 10. 소스 배선 확인(하네스 통합 점검은 별도: 예외 주입 시 섹션만 생략되고 리포트 정상 발송 확인됨)
const fs = require('fs');
const path = require('path');
const scanner = fs.readFileSync(path.join(__dirname, '../src/swing-scanner.src.js'), 'utf-8');
const reporter = fs.readFileSync(path.join(__dirname, '../src/weekly-reporter.src.js'), 'utf-8');
assert.ok(/rvol: Number\.isFinite\(selected\[i\]\.rvolVal\) \? \+selected\[i\]\.rvolVal\.toFixed\(2\) : null,/.test(scanner), 'scanner rvol 기록');
assert.ok(/require\('\.\.\/lib\/shadowCohorts'\)/.test(reporter), 'reporter lib require');
assert.ok(/try \{\s*const sh = computeShadowCohorts\(details\);[\s\S]*?\} catch \(e\) \{\s*logger\.warning\('shadow cohorts failed'/.test(reporter), 'reporter shadow try/catch');


// ===== market-state-shadow (design §5, §6) =====
const S = (o) => rec(Object.assign({ mkt: 'KOSDAQ', mstate: 'UP', sentAt: 1 }, o));
assert.deepStrictEqual(SHADOW_STATE_COHORTS, ['STATE_BLOCK', 'STATE_PAT', 'STATE_CAP', 'STATE_CAP_BEST', 'STATE_ALL']);
assert.deepStrictEqual(SHADOW_STATE_GATE_COHORTS, ['STATE_BLOCK', 'STATE_PAT', 'STATE_CAP', 'STATE_ALL']);

// 11. STATE_BLOCK: SURGE·CRASH 제외, 나머지·UNKNOWN 통과
const blk = shadowStateSelect(['SURGE', 'CRASH', 'UP', 'FLAT', 'DOWN', 'UNKNOWN'].map((s) => S({ mstate: s })), 'STATE_BLOCK');
assert.deepStrictEqual(blk.map((r) => r.mstate), ['UP', 'FLAT', 'DOWN', 'UNKNOWN']);

// 12. STATE_PAT: SURGE×전체, CRASH×D, DOWN×A 제외 / CRASH×C, DOWN×B, UNKNOWN×D 통과
const patIn = [S({ mstate: 'SURGE', patternType: 'C촉매' }), S({ mstate: 'CRASH', patternType: 'D박스' }),
  S({ mstate: 'CRASH', patternType: 'C촉매' }), S({ mstate: 'DOWN', patternType: 'A눌림목' }),
  S({ mstate: 'DOWN', patternType: 'B지지선' }), S({ mstate: 'UNKNOWN', patternType: 'D박스' })];
assert.deepStrictEqual(shadowStateSelect(patIn, 'STATE_PAT').map((r) => r.mstate + r.patternType),
  ['CRASHC촉매', 'DOWNB지지선', 'UNKNOWND박스']);

// 13. STATE_CAP: (일자, 시장, 상태) 버킷 선착순
const surge3 = [S({ mstate: 'SURGE', sentAt: 30, name: 'late' }), S({ mstate: 'SURGE', sentAt: 10, name: 'early' }), S({ mstate: 'SURGE', sentAt: 20, name: 'mid' })];
assert.deepStrictEqual(shadowStateSelect(surge3, 'STATE_CAP').map((r) => r.name), ['early']); // SURGE 상한 1, sentAt 최소
const up4 = [1, 2, 3, 4].map((i) => S({ mkt: 'KOSPI', mstate: 'UP', sentAt: i, name: 'u' + i }));
assert.deepStrictEqual(shadowStateSelect(up4, 'STATE_CAP').map((r) => r.name), ['u1', 'u2', 'u3']); // UP 상한 3
assert.deepStrictEqual(shadowStateSelect([S({ mstate: 'CRASH' }), S({ mstate: 'CRASH' })], 'STATE_CAP'), []); // CRASH 0
assert.strictEqual(shadowStateSelect([1, 2, 3, 4, 5].map((i) => S({ mstate: 'UNKNOWN', sentAt: i })), 'STATE_CAP').length, 5); // UNKNOWN 상한 없음
const noSent = [S({ mstate: 'SURGE', sentAt: undefined, name: 'a' }), S({ mstate: 'SURGE', sentAt: undefined, name: 'b' })];
assert.deepStrictEqual(shadowStateSelect(noSent, 'STATE_CAP').map((r) => r.name), ['a']); // sentAt 없으면 입력 순서
const twoMk = [S({ mkt: 'KOSPI', mstate: 'SURGE', name: 'k1' }), S({ mkt: 'KOSDAQ', mstate: 'SURGE', name: 'q1' }),
  S({ mkt: 'KOSDAQ', mstate: 'SURGE', date: '2026-10-02', name: 'q2' })];
assert.deepStrictEqual(shadowStateSelect(twoMk, 'STATE_CAP').map((r) => r.name), ['k1', 'q1', 'q2']); // 시장·일자별 독립

// 14. STATE_CAP_BEST: 같은 버킷에서 D>C>B>A, 점수 — 선착순과 달라지는 입력
const bestIn = [S({ mstate: 'SURGE', sentAt: 1, patternType: 'A눌림목', score: 300, name: 'A' }), S({ mstate: 'SURGE', sentAt: 2, patternType: 'D박스', score: 50, name: 'D' })];
assert.deepStrictEqual(shadowStateSelect(bestIn, 'STATE_CAP').map((r) => r.name), ['A']);
assert.deepStrictEqual(shadowStateSelect(bestIn, 'STATE_CAP_BEST').map((r) => r.name), ['D']);

// 15. STATE_ALL = BLOCK → PAT → CAP
const allIn = [S({ mstate: 'SURGE', name: 's' }), S({ mstate: 'CRASH', patternType: 'D박스', name: 'c' }),
  S({ mstate: 'DOWN', patternType: 'A눌림목', name: 'da' }), S({ mstate: 'DOWN', patternType: 'B지지선', sentAt: 1, name: 'db1' }),
  S({ mstate: 'DOWN', patternType: 'B지지선', sentAt: 2, name: 'db2' })].concat([1, 2, 3, 4].map((i) => S({ mstate: 'UP', sentAt: i, name: 'u' + i })));
assert.deepStrictEqual(shadowStateSelect(allIn, 'STATE_ALL').map((r) => r.name), ['db1', 'u1', 'u2', 'u3']);

// 16. look-ahead 방지: holding도 슬롯 점유, 통계에서만 제외
const hold = [S({ mstate: 'SURGE', sentAt: 1, result: 'holding' }), S({ mstate: 'SURGE', sentAt: 2, result: 'win' })];
const hsel = shadowStateSelect(hold, 'STATE_CAP');
assert.strictEqual(hsel.length, 1);
assert.strictEqual(hsel[0].result, 'holding');
assert.strictEqual(shadowStats(hsel, 'x').closed, 0);

// 17. 입력 변형 없음
const snap2 = JSON.parse(JSON.stringify(allIn));
shadowStateSelect(allIn, 'STATE_ALL');
assert.deepStrictEqual(JSON.parse(JSON.stringify(allIn)), snap2);

// 18. computeShadowStateCohorts: mstate 비문자열·carryOver 제외, 제외분 집계
const dets = [S({ mstate: 'SURGE', result: 'loss', stopPct: -0.04 }), S({ mstate: 'SURGE', result: 'loss', stopPct: -0.04 }),
  S({ mstate: 'UP', result: 'win', targetPct: 0.10 }), S({ mstate: 'FLAT', result: 'partial_win', stopPct: 0.02 }),
  S({ mstate: null, result: 'loss' }), S({ mstate: undefined, result: 'loss' }),
  S({ mstate: 'UP', result: 'win', carryOver: true }), S({ mstate: 'UP', result: 'holding' })];
const sc = computeShadowStateCohorts(dets);
assert.strictEqual(sc.ALLS.n, 5);
assert.strictEqual(sc.ALLS.closed, 4);
assert.strictEqual(sc.STATE_BLOCK.n, 3);
assert.strictEqual(sc.STATE_BLOCK.closed, 2);
assert.strictEqual(sc.STATE_BLOCK.sumRet, 12);        // (10% + 2%) %p
assert.strictEqual(sc.STATE_BLOCK.excludedClosed, 2);
assert.strictEqual(sc.STATE_BLOCK.excludedSum, -8);
for (const name of SHADOW_STATE_COHORTS) assert.strictEqual(sc[name].closed + sc[name].excludedClosed, sc.ALLS.closed, name);
assert.strictEqual(computeShadowStateCohorts([]).ALLS.n, 0);
assert.strictEqual(computeShadowStateCohorts([]).STATE_ALL.closed, 0);
assert.strictEqual(computeShadowStateCohorts(undefined).ALLS.n, 0);

// 19. shadowStateGate: 정보주 판정·제외분 평균·ALLS 없는 주 건너뜀·빈 입력
const sw = (allN, allClosed, allWin, allAvg, cN, cClosed, cWin, cAvg, exClosed, exSum) => ({
  ALLS: { n: allN, closed: allClosed, win: allWin, winPct: allClosed ? 100 * allWin / allClosed : 0, avgRet: allAvg },
  STATE_BLOCK: { n: cN, closed: cClosed, win: cWin, winPct: cClosed ? 100 * cWin / cClosed : 0, avgRet: cAvg, excludedClosed: exClosed, excludedSum: exSum },
});
assert.strictEqual(shadowStateGate({ w1: sw(40, 40, 8, -1, 35, 35, 8, -0.8, 5, -6) }).STATE_BLOCK.informativeWeeks, 0); // 제외 5 < ceil(40*.15)=6
assert.strictEqual(shadowStateGate({ w1: sw(40, 40, 8, -1, 34, 34, 8, -0.8, 6, -7) }).STATE_BLOCK.informativeWeeks, 1); // 제외 6 >= 6
assert.strictEqual(shadowStateGate({ w1: sw(20, 20, 4, -1, 15, 15, 4, -0.8, 5, -6) }).STATE_BLOCK.informativeWeeks, 1); // 하한 5
assert.strictEqual(shadowStateGate({ old: { ALL: { n: 9 }, NOCOMP: { n: 5 } } }).STATE_BLOCK.informativeWeeks, 0);      // ALLS 없는 과거 주
const gz = shadowStateGate(undefined);
for (const name of SHADOW_STATE_GATE_COHORTS) {
  assert.strictEqual(gz[name].closedTotal, 0);
  assert.strictEqual(gz[name].passN, false);
  assert.strictEqual(gz[name].passWeeks, false);
  assert.strictEqual(gz[name].passEffect, false);
}
const goodW = () => sw(60, 60, 6, -1.5, 40, 12, 3, 0.5, 20, -20);   // 승률 10%→25%, 평균 -1.5→+0.5, 제외분 평균 -1%p
const g4 = shadowStateGate({ a: goodW(), b: goodW(), c: goodW() }).STATE_BLOCK;
assert.strictEqual(g4.informativeWeeks, 3);
assert.strictEqual(g4.weeksPositive, 3);
assert.strictEqual(g4.closedTotal, 36);
assert.strictEqual(g4.passN, true);
assert.strictEqual(g4.passWeeks, true);
assert.strictEqual(g4.passEffect, true);
const badEx = () => sw(60, 60, 6, -1.5, 40, 12, 3, 0.5, 20, 10);    // 제외분 평균이 +이면 좋은 종목을 걷어낸 것
assert.strictEqual(shadowStateGate({ a: badEx(), b: badEx(), c: badEx() }).STATE_BLOCK.passEffect, false);
assert.strictEqual(shadowStateGate({ a: goodW(), b: goodW() }).STATE_BLOCK.passWeeks, false); // 정보주 2 < 3

// 20. shadowStateSummary: 일자·시장별 최빈 상태, mstate 없는 추천 무시
const sm = shadowStateSummary([S({ date: '2026-10-06', mstate: 'SURGE' }), S({ date: '2026-10-06', mstate: 'SURGE' }),
  S({ date: '2026-10-06', mstate: 'UNKNOWN' }), S({ date: '2026-10-12', mstate: 'CRASH' }), S({ date: '2026-10-12', mstate: null }),
  S({ date: '2026-10-06', mkt: 'KOSPI', mstate: 'UP' })]);
assert.deepStrictEqual(sm.KOSDAQ, [{ date: '2026-10-06', state: 'SURGE', n: 3 }, { date: '2026-10-12', state: 'CRASH', n: 1 }]);
assert.deepStrictEqual(sm.KOSPI, [{ date: '2026-10-06', state: 'UP', n: 1 }]);

// 21. shadowFormatStateSection: 빈 데이터·표본 적음·줄 수
const noRec = shadowFormatStateSection(computeShadowStateCohorts([]), shadowStateGate({}), shadowStateSummary([]));
assert.ok(noRec.includes('상태 기록 없음'));
const fmtOut = shadowFormatStateSection(sc, shadowStateGate({ w: sc }), shadowStateSummary(dets));
assert.ok(fmtOut.includes('🌡️ 시장상태 Shadow'));
assert.ok(fmtOut.includes('※표본 적음'));            // closed < 5
assert.ok(fmtOut.split('\n').filter(Boolean).length <= 12);
assert.ok(shadowFormatStateSection(computeShadowStateCohorts([S({ result: 'holding' })]), shadowStateGate({}), shadowStateSummary([])).includes('데이터 없음'));

// 22. 회귀: 기존 코호트 키 집합은 변하지 않는다
assert.deepStrictEqual(Object.keys(computeShadowCohorts([rec({})])).sort(), ['ALL', 'CAP2', 'NOCOMP', 'NOCOMP+CAP2', 'RVOL5']);

// 설정 상수 sanity
assert.strictEqual(SHADOW_CFG.dayCap, 2);
assert.strictEqual(SHADOW_CFG.rvolMin, 5);

console.log('verify_shadow_cohorts: OK');

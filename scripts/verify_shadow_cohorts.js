/**
 * Self-check for lib/shadowCohorts.js (volume5x-pattern-cap-shadow, design §7).
 * Run: node scripts/verify_shadow_cohorts.js
 */
'use strict';
const assert = require('assert');
const {
  SHADOW_CFG, shadowIsComposite, shadowSelect, shadowStats, computeShadowCohorts, shadowGate,
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

// 설정 상수 sanity
assert.strictEqual(SHADOW_CFG.dayCap, 2);
assert.strictEqual(SHADOW_CFG.rvolMin, 5);

console.log('verify_shadow_cohorts: OK');

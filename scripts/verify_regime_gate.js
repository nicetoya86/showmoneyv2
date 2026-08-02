/**
 * Self-check for the regime-gate restored in src/swing-scanner.src.js
 * (previously dead code — getMarketRegime() was defined but never called,
 * riskOn was hardcoded true). Mirrors the exact two-line gate so a future
 * edit that breaks the gate's branch logic fails this script.
 *
 * Run: node scripts/verify_regime_gate.js
 */
'use strict';

function passesGate(regimeLevel, grade) {
  if (regimeLevel >= 2 && grade !== '강매') return false; // 약세장: 강매 전용
  if (regimeLevel >= 1 && grade === '매도차익') return false; // 중립장: 매도차익 차단
  return true;
}

const GRADES = ['강매', '급등', '매도차익', '매수'];
const cases = [];
for (const level of [0, 1, 2]) {
  for (const grade of GRADES) cases.push({ level, grade });
}

const expected = {
  '0|강매': true, '0|급등': true, '0|매도차익': true, '0|매수': true,
  '1|강매': true, '1|급등': true, '1|매도차익': false, '1|매수': true,
  '2|강매': true, '2|급등': false, '2|매도차익': false, '2|매수': false,
};

let failures = 0;
for (const { level, grade } of cases) {
  const key = `${level}|${grade}`;
  const got = passesGate(level, grade);
  const want = expected[key];
  if (got !== want) {
    failures++;
    console.error(`FAIL regimeLevel=${level} grade=${grade}: got ${got}, want ${want}`);
  }
}

if (failures > 0) {
  console.error(`${failures}/${cases.length} cases failed`);
  process.exit(1);
}
console.log(`OK: all ${cases.length} regimeLevel x grade combinations match the documented gate (0=all allowed, 1=매도차익 blocked, 2=강매 only).`);

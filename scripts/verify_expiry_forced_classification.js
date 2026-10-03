/**
 * Self-check for [FIX-2026-09-26] src/weekly-reporter.src.js 만기청산 강제 판정:
 * 보유기간이 다 지나도록 목표/손절 어느 쪽도 안 걸린 포지션('expired')을 방치하지 않고,
 * 만기 시점 종가(finalClose)를 진입가와 비교해 win/loss로 강제 확정해야 한다.
 * 소스 텍스트 기반 검증(로직이 스캐너/리포터 클로저 안에 있어 단위함수 분리 전까지는
 * 정규식으로 방향/부호만 확인 — verify_scoring_reweight_2026-09-26.js와 동일 패턴).
 *
 * Run: node scripts/verify_expiry_forced_classification.js
 */
'use strict';
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, '../src/weekly-reporter.src.js'), 'utf-8');

let failures = 0;
const assert = (label, cond) => { if (!cond) { failures++; console.error(`FAIL ${label}`); } };

// ---- expiredForced 플래그가 'expired' 상태에서만 세워짐 ----
assert(
  "expiredForced는 result==='expired'에서만 true",
  /const expiredForced = \(result === 'expired'\);/.test(src)
);

// ---- 만기 종가 >= 진입가면 win, 아니면 loss (부호/방향 확인) ----
assert(
  '만기청산 판정: finalClose >= entry -> win, 아니면 loss',
  /result = finalClose >= r\.entry \? 'win' : 'loss';/.test(src)
);

// ---- stopForPct: 만기청산이면 finalClose를 청산가로 사용(이론상 손절가 아님) ----
assert(
  'stopForPct가 expiredForced일 때 finalClose 사용',
  /const stopForPct = expiredForced \? finalClose/.test(src)
);

// ---- 리포트 표기: 실제 목표/손절 도달과 구분되는 "만기청산" 태그가 양쪽 리스트에 있어야 함 ----
assert('수익 리스트에 만기청산 태그 존재', /if \(d\.expiredForced\) line \+= ' │ 만기청산 │ 확정 ' \+ pct\(d\.finalReturn\);/.test(src));
assert('손절 리스트에 만기청산 태그 존재', /if \(d\.expiredForced\) line \+= ' │ 만기청산';/.test(src));

// ---- details에 expiredForced 필드가 실제로 전달됨 ----
assert(
  'details.push에 expiredForced 포함',
  /details\.push\(\{ \.\.\.r, result, maxReturn, finalReturn, exitDate, hitTargetDay, hitTarget1Day, hitStopDay, targetPct, stopPct, expiredForced \}\);/.test(src)
);

if (failures > 0) {
  console.error(`\n${failures} FAILURE(S)`);
  process.exit(1);
}
console.log('OK: expiry-forced win/loss classification verified');

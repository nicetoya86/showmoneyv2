/**
 * Self-check for [FIX-2026-09-05] swing-scanner.src.js bear-regime circuit breaker:
 * regimeLevel>=2(약세장)일 땐 회차당 발송 수를 MAX_STOCK_PER_SEND(3)에서
 * MAX_STOCK_PER_SEND_BEAR(1)로 줄인다. regimeLevel 0/1은 기존 그대로 3건 유지
 * (2026-08-18 "주간 발송 한도 완전 제거" 요청을 규정과 무관하게 뒤집지 않도록,
 * 이 서킷브레이커는 regimeLevel>=2일 때만 작동한다).
 *
 * Mirrors the maxStockPerSend selection from src/swing-scanner.src.js.
 *
 * Run: node scripts/verify_bear_regime_circuit_breaker.js
 */
'use strict';

const MAX_STOCK_PER_SEND = 3;
const MAX_STOCK_PER_SEND_BEAR = 1;

let failures = 0;
const assertEq = (label, got, want) => {
  if (got !== want) { failures++; console.error(`FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); }
};

function maxStockPerSend(regimeLevel) {
  return regimeLevel >= 2 ? MAX_STOCK_PER_SEND_BEAR : MAX_STOCK_PER_SEND;
}

assertEq('강세(regimeLevel=0) -> 기존 cap 3 유지', maxStockPerSend(0), 3);
assertEq('중립(regimeLevel=1) -> 기존 cap 3 유지', maxStockPerSend(1), 3);
assertEq('약세(regimeLevel=2) -> circuit breaker cap 1', maxStockPerSend(2), 1);
assertEq('regimeLevel 정의 밖 값(방어적 폴백)도 >=2면 cap 1', maxStockPerSend(3), 1);

// deduped.slice(0, cap) 동작 자체도 확인 — 후보가 cap보다 적으면 그대로 다 나가야 함
const deduped = [{ code: 'A' }, { code: 'B' }, { code: 'C' }, { code: 'D' }];
assertEq('약세장, 후보 4개 -> 1개만 선정', deduped.slice(0, maxStockPerSend(2)).length, 1);
assertEq('강세장, 후보 4개 -> 3개 선정(기존 동작 유지)', deduped.slice(0, maxStockPerSend(0)).length, 3);
assertEq('강세장, 후보 2개(< cap) -> 2개 다 선정', deduped.slice(0, 2).slice(0, maxStockPerSend(0)).length, 2);

if (failures > 0) {
  console.error(`\n${failures} FAILURE(S)`);
  process.exit(1);
}
console.log('OK — bear-regime circuit breaker cap selection passes');

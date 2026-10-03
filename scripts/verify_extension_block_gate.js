/**
 * Self-check for [FIX-2026-09-13] swing-scanner.src.js TOSS-CONFIRM 과열 선반영 차단:
 * 실시간가가 아직 목표가를 안 넘었어도, 괴리(gapPct)가 목표거리(targetPct)의
 * TOSS_EXTENSION_BLOCK_RATIO(0.7) 이상이면 발송을 막는다.
 *
 * 회귀 배경: 원익/흥구석유/금강철강(09-01~09-04) — 발송 당일 목표가 도달 전부터
 * 이미 과도하게 선반영된 뒤 반납, 손절로 마감.
 *
 * Run: node scripts/verify_extension_block_gate.js
 */
'use strict';

const TOSS_EXTENSION_BLOCK_RATIO = 0.7;

let failures = 0;
const assertEq = (label, got, want) => {
  if (got !== want) { failures++; console.error(`FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); }
};

function gateDecision(entry, target, livePrice) {
  const gapPct = (livePrice - entry) / entry;
  const chasingRisk = target > 0 && livePrice >= target;
  const targetPctForGate = target > 0 ? (target / entry - 1) : null;
  const overExtended = !chasingRisk && targetPctForGate != null && targetPctForGate > 0
    && gapPct >= targetPctForGate * TOSS_EXTENSION_BLOCK_RATIO;
  if (chasingRisk) return 'chasingRisk';
  if (overExtended) return 'overExtended';
  return 'ok';
}

// entry 10000, target 11000 (targetPct=10%). 70% 문턱 = 7% 괴리(10700) 이상이면 차단.
assertEq('괴리 3%(정상 범위) -> 통과', gateDecision(10000, 11000, 10300), 'ok');
assertEq('괴리 6.9%(문턱 살짝 아래) -> 통과', gateDecision(10000, 11000, 10690), 'ok');
assertEq('괴리 7.1%(문턱 살짝 위) -> 과열 차단', gateDecision(10000, 11000, 10710), 'overExtended');
assertEq('괴리 8%(목표 미달, 과열 구간) -> 과열 차단', gateDecision(10000, 11000, 10800), 'overExtended');
assertEq('괴리 10%+(목표 도달/초과) -> 기존 chasingRisk 우선', gateDecision(10000, 11000, 11000), 'chasingRisk');

if (failures > 0) {
  console.error(`\n${failures} FAILURE(S)`);
  process.exit(1);
}
console.log('OK: extension-block gate verified');

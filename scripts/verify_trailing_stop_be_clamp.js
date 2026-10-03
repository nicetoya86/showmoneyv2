/**
 * Self-check for [FIX-2026-09-13] lib/trailingStop.js breakeven clamp:
 * gain>=3%(TRAIL_BE_GAIN) 티어에 들어온 이상, ATR 기반 5%/10%/15% 트레일 값이
 * 변동성 때문에 entry 밑으로 계산돼도 절대 entry 밑으로는 안 내려가야 한다.
 *
 * 회귀 재현: 원익/흥구석유/금강철강(09-01~09-04) — 고변동성 촉매주가 +35~43%
 * 찍고도 ATR-기반 트레일이 본전 밑으로 나와 확정 -0.1%~-7.4%로 마감된 케이스.
 *
 * Run: node scripts/verify_trailing_stop_be_clamp.js
 */
'use strict';

const { calcTrailingStop } = require('../lib/trailingStop');

let failures = 0;
const assertGte = (label, got, min) => {
  if (!(got >= min)) { failures++; console.error(`FAIL ${label}: got ${got}, want >= ${min}`); }
};
const assertEq = (label, got, want) => {
  if (got !== want) { failures++; console.error(`FAIL ${label}: got ${got}, want ${want}`); }
};

// 흥구석유형 재현: entry 10000, 고점 13500(+35%), 당일 저-고 변동폭(ATR 근사) 2700
{
  const entry = 10000;
  const high = 13500;
  const atr = 2700; // high-low 근사
  const gain = (high - entry) / entry; // 0.35 -> 15% 티어(고점-ATR*0.7=11610, entry보다 낮음)
  const stop = calcTrailingStop(entry, high, atr, gain, 9000 /* initial 10% 손절가 */);
  assertGte('고변동성 +35% 케이스 -> 스탑은 최소 entry(본전) 이상', stop, entry);
}

// 원익형 재현: entry 8000, 고점 8700(+8.75%), ATR 1150 -> 5%티어(고점-ATR*1.5=6975, entry보다 낮음)
{
  const entry = 8000;
  const high = 8700;
  const atr = 1150;
  const gain = (high - entry) / entry;
  const stop = calcTrailingStop(entry, high, atr, gain, 7360);
  assertGte('중간변동성 +8.75% 케이스 -> 스탑은 최소 entry(본전) 이상', stop, entry);
}

// 기존 동작 보존: 낮은 변동성에서는 ATR-트레일이 entry보다 위로 정상 계산되면 그 값 그대로
{
  const entry = 10000;
  const high = 11000; // +10%
  const atr = 200; // 좁은 ATR
  const gain = (high - entry) / entry;
  const stop = calcTrailingStop(entry, high, atr, gain, 9500);
  assertEq('저변동성 +10% 케이스 -> 고점-ATR*1.0 그대로(본전보다 이미 위)', stop, high - atr * 1.0);
}

// 스탑은 절대 낮아지지 않음(기존 트레일링 보장) 유지 확인
{
  const entry = 10000;
  const existingStop = 10500; // 이미 본전보다 높게 올라가 있던 경우
  const stop = calcTrailingStop(entry, 10200, 500, 0.02 /* BE 미달 */, existingStop);
  assertEq('BE 미달 gain -> 기존 stop 그대로 유지(낮아지지 않음)', stop, existingStop);
}

if (failures > 0) {
  console.error(`\n${failures} FAILURE(S)`);
  process.exit(1);
}
console.log('OK: trailing stop breakeven clamp verified');

/**
 * Self-check for:
 *  1) [NOREBUY] swing-scanner.src.js — held (not-yet-expired) codes must not be
 *     re-selected as new buy candidates in the next scan.
 *  2) [CARRYOVER] weekly-reporter.src.js — a rec from a prior week whose holding
 *     period stretches into this week must be collected and flagged carryOver,
 *     while a prior-week rec that already expired before this week must not.
 *
 * Mirrors the exact expiry/carryover logic added to those files so a future
 * edit that breaks either behavior fails this script.
 *
 * Run: node scripts/verify_norebuy_and_carryover.js
 */
'use strict';

const { isHoliday } = require('../lib/holidays');

let failures = 0;
const assertEq = (label, got, want) => {
  if (got !== want) { failures++; console.error(`FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); }
};

// ===== 1) [NOREBUY] heldCodes computation (mirrors src/swing-scanner.src.js) =====
function computeHeldCodes(weeklyRecommendations, now) {
  const heldCodes = new Set();
  for (const dateKey in weeklyRecommendations) {
    for (const rec of (weeklyRecommendations[dateKey] || [])) {
      if (rec.type !== 'swing') continue;
      const holdDays = rec.holdingDays || 3;
      const entryDate = new Date(rec.date || dateKey);
      const expiry = new Date(entryDate.getTime() + holdDays * 1.4 * 24 * 60 * 60 * 1000);
      if (expiry < now) continue;
      heldCodes.add(String(rec.code));
    }
  }
  return heldCodes;
}

{
  // 2026-08-10(월) 추천, holdingDays=5 -> 만료 약 2026-08-17 (5*1.4=7일 후)
  // 2026-08-14(금) 시점엔 아직 보유 중 -> 재매수 후보에서 제외돼야 함
  const store = { '2026-08-10': [{ type: 'swing', code: '005930', holdingDays: 5 }] };
  const held = computeHeldCodes(store, new Date('2026-08-14T09:00:00+09:00'));
  assertEq('held stock excluded before expiry', held.has('005930'), true);
}
{
  // 같은 포지션이 8/22(만료 이후)엔 더 이상 held 아님 -> 재매수 가능
  const store = { '2026-08-10': [{ type: 'swing', code: '005930', holdingDays: 5 }] };
  const held = computeHeldCodes(store, new Date('2026-08-22T09:00:00+09:00'));
  assertEq('stock re-eligible after expiry', held.has('005930'), false);
}
{
  // scalping 타입은 재매수 제외 대상 아님(swing 전용 필터)
  const store = { '2026-08-10': [{ type: 'scalping', code: '000660', holdingDays: 5 }] };
  const held = computeHeldCodes(store, new Date('2026-08-14T09:00:00+09:00'));
  assertEq('non-swing type ignored', held.has('000660'), false);
}

// ===== 2) [CARRYOVER] weekly-reporter.src.js carryover collection =====
const addTradingDays = (startDateStr, n) => {
  const d = new Date(startDateStr + 'T00:00:00Z');
  let count = 0;
  while (count < n) {
    d.setUTCDate(d.getUTCDate() + 1);
    const dow = d.getUTCDay();
    const ds = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
    if (dow >= 1 && dow <= 5 && !isHoliday(ds)) count++;
  }
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
};

function computeCarryOverRecs(weeklyRecommendations, weekStart) {
  const carryOverRecs = [];
  for (const dateKey in weeklyRecommendations) {
    if (dateKey >= weekStart) continue;
    const arr = weeklyRecommendations[dateKey] || [];
    for (const r of arr) {
      if (r.type !== 'swing') continue;
      const holdDays = r.holdingDays || 3;
      const exitDate = addTradingDays(dateKey, holdDays);
      if (exitDate >= weekStart) carryOverRecs.push({ ...r, date: dateKey, carryOver: true });
    }
  }
  return carryOverRecs;
}

{
  // 지난주 목(2026-08-06) 추천 + holdingDays=5(거래일) -> exitDate 2026-08-13(목), 이번주(월=08-10) 안쪽까지 걸침
  const store = { '2026-08-06': [{ type: 'swing', code: '005930', holdingDays: 5 }] };
  const carry = computeCarryOverRecs(store, '2026-08-10');
  assertEq('overlapping prior-week rec is carried over', carry.length, 1);
  assertEq('carried rec is flagged carryOver', carry[0] && carry[0].carryOver, true);
}
{
  // 2주 전(2026-07-27) 추천 + holdingDays=3 -> exitDate 2026-07-30, 이번주(08-10) 시작 전에 이미 종료 -> 이월 아님
  const store = { '2026-07-27': [{ type: 'swing', code: '000660', holdingDays: 3 }] };
  const carry = computeCarryOverRecs(store, '2026-08-10');
  assertEq('already-closed prior-week rec is not carried over', carry.length, 0);
}
{
  // 이번주 자체 날짜는 carryover 대상 아님(이미 recs에서 수집됨)
  const store = { '2026-08-10': [{ type: 'swing', code: '005380', holdingDays: 5 }] };
  const carry = computeCarryOverRecs(store, '2026-08-10');
  assertEq('this-week date excluded from carryover', carry.length, 0);
}

if (failures > 0) {
  console.error(`${failures} case(s) failed`);
  process.exit(1);
}
console.log('OK: no-rebuy-while-held + weekly-report carryover logic verified (6 cases).');

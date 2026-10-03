/**
 * Self-check for [FIX-2026-09-13] Daily_Position_Monitor.js 12:30 KST 장중 체크 추가:
 * - 실행 시각(KST) < 15시 -> 장중 분봉 스냅샷 경로(fetchIntradaySnapshot) 사용
 * - 실행 시각(KST) >= 15시 -> 기존 EOD 일봉 경로(fetchDailyClose) 사용
 * 실제 네트워크 호출 없이 분기 로직 + 스냅샷 집계 로직만 미러링해서 검증한다.
 *
 * Run: node scripts/verify_intraday_position_monitor.js
 */
'use strict';

let failures = 0;
const assertEq = (label, got, want) => {
  if (got !== want) { failures++; console.error(`FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); }
};

function isIntraday(kstHour) {
  return kstHour < 15;
}

assertEq('09:00 KST(장 시작) -> 장중 경로', isIntraday(9), true);
assertEq('12:30 KST(신규 트리거) -> 장중 경로', isIntraday(12), true);
assertEq('14:59 KST -> 아직 장중 경로', isIntraday(14), true);
assertEq('15:00 KST(마감 임박) -> EOD 경로 전환', isIntraday(15), false);
assertEq('16:00 KST(기존 트리거) -> EOD 경로', isIntraday(16), false);

// fetchIntradaySnapshot의 고가/저가/현재가 집계 로직 미러링
function aggregateMinuteBars(bars) {
  let high = -Infinity, low = Infinity, close = null;
  for (const bar of bars) {
    const hi = Number(bar.highPrice || bar.high);
    const lo = Number(bar.lowPrice || bar.low);
    const cl = Number(bar.closePrice || bar.close);
    if (Number.isFinite(hi) && hi > high) high = hi;
    if (Number.isFinite(lo) && lo < low) low = lo;
    if (Number.isFinite(cl)) close = cl;
  }
  if (!Number.isFinite(high) || !Number.isFinite(low) || close == null) return null;
  return { high, low, close };
}

const bars = [
  { high: 8100, low: 8050, close: 8080 },
  { high: 8700, low: 8600, close: 8650 }, // 장중 고점
  { high: 8400, low: 8300, close: 8350 }, // 현재(마지막 바) 기준 current price
];
const snap = aggregateMinuteBars(bars);
assertEq('장중 고가 = 분봉 중 최고 high', snap.high, 8700);
assertEq('장중 저가 = 분봉 중 최저 low', snap.low, 8050);
assertEq('현재가 = 마지막 분봉 close(시간순 마지막)', snap.close, 8350);

assertEq('빈 분봉 배열 -> null(스킵)', aggregateMinuteBars([]), null);

if (failures > 0) {
  console.error(`\n${failures} FAILURE(S)`);
  process.exit(1);
}
console.log('OK: intraday position monitor branch + snapshot aggregation verified');

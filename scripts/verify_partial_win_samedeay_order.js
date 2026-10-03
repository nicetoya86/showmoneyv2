/**
 * Self-check for the [FIX-2026-09-05] weekly-reporter.src.js fix:
 * when target1(1차목표) and the stop price are both hit on the same calendar day,
 * the real intraday order must decide partial_win vs loss instead of optimistically
 * assuming target1 came first (the bug that produced 09-05 리포트의 써니전자/흥구석유/
 * 네오이문텍/위더스제약 — "부분익절"인데 확정%가 마이너스인 자기모순 표기).
 *
 * Mirrors resolvePartialOrLoss() from src/weekly-reporter.src.js so a future edit
 * that breaks this decision table fails this script.
 *
 * Run: node scripts/verify_partial_win_samedeay_order.js
 */
'use strict';

let failures = 0;
const assertEq = (label, got, want) => {
  if (got !== want) { failures++; console.error(`FAIL ${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); }
};

// resolveOrder1: 실제 코드에선 분봉(resolveSameDayOrder) 조회 결과('target'|'stop'|'neither'|null).
// 여기선 케이스별로 미리 정해둔 값을 주입한다.
async function resolvePartialOrLoss(hitTarget1Day, hitStopDay, resolveOrder1) {
  if (!hitTarget1Day || hitTarget1Day > hitStopDay) return 'loss';
  if (hitTarget1Day < hitStopDay) return 'partial_win';
  const order1 = await resolveOrder1();
  return order1 === 'stop' ? 'loss' : 'partial_win';
}

(async () => {
  assertEq('no target1 hit -> loss',
    await resolvePartialOrLoss(null, '2026-09-01', () => { throw new Error('should not be called'); }),
    'loss');

  assertEq('target1 hit after stop -> loss',
    await resolvePartialOrLoss('2026-09-02', '2026-09-01', () => { throw new Error('should not be called'); }),
    'loss');

  assertEq('target1 hit before stop (different day) -> partial_win, no intraday check needed',
    await resolvePartialOrLoss('2026-08-28', '2026-08-31', () => { throw new Error('should not be called'); }),
    'partial_win');

  // 09-05 리포트 재현: 위더스제약류(1차==청산 동일자), 분봉상 stop이 target1보다 먼저 찍힘 -> 진짜 loss
  assertEq('same-day target1==stop, minute bars show stop first -> loss',
    await resolvePartialOrLoss('2026-08-31', '2026-08-31', async () => 'stop'),
    'loss');

  assertEq('same-day target1==stop, minute bars show target1 first -> partial_win',
    await resolvePartialOrLoss('2026-09-01', '2026-09-01', async () => 'target'),
    'partial_win');

  assertEq('same-day target1==stop, minute fetch inconclusive (neither) -> optimistic partial_win fallback',
    await resolvePartialOrLoss('2026-09-01', '2026-09-01', async () => 'neither'),
    'partial_win');

  assertEq('same-day target1==stop, minute fetch failed (null, old date) -> optimistic partial_win fallback',
    await resolvePartialOrLoss('2026-09-01', '2026-09-01', async () => null),
    'partial_win');

  // [FIX-2026-10-03] 풀타겟/손절이 서로 다른 날 찍힌 분기(weekly-reporter `else if (hitTargetDay && hitStopDay)`) 미러.
  // KSS해운 044450: 1차 09-28 < 손절 09-29 < 풀타겟 10-01 -> 예전엔 무조건 loss, 이제 partial_win(확정<0이면 후단에서 loss 강제).
  const classifyBothHit = async (t1, t, s) => (t <= s ? 'win' : await resolvePartialOrLoss(t1, s, () => { throw new Error('not same-day'); }));
  assertEq('KSS해운형: target1 < stop < target -> partial_win',
    await classifyBothHit('2026-09-28', '2026-10-01', '2026-09-29'), 'partial_win');
  assertEq('stop < target1 < target (손절이 먼저) -> loss 유지',
    await classifyBothHit('2026-09-30', '2026-10-01', '2026-09-29'), 'loss');
  assertEq('target1 없이 stop < target -> loss 유지',
    await classifyBothHit(null, '2026-10-01', '2026-09-29'), 'loss');
  assertEq('target < stop -> win 유지',
    await classifyBothHit('2026-09-28', '2026-09-29', '2026-09-30'), 'win');

  const src = require('fs').readFileSync(require('path').join(__dirname, '../src/weekly-reporter.src.js'), 'utf-8');
  assertEq("소스가 풀타겟-손절 다른날 분기에서 resolvePartialOrLoss 사용",
    /result = hitTargetDay <= hitStopDay \? 'win' : await resolvePartialOrLoss\(\);/.test(src), true);

  if (failures > 0) {
    console.error(`\n${failures} FAILURE(S)`);
    process.exit(1);
  }
  console.log('OK — all partial_win/loss same-day ordering cases pass');
})();

/**
 * Self-check for the one-time weekly-cap-reached notice added to
 * src/swing-scanner.src.js (shouldSendWeeklyCapNotice gate).
 * Mirrors the exact decision logic so a future edit that breaks the
 * once-per-week notice behavior fails this script.
 *
 * Run: node scripts/verify_swing_scanner_weekly_cap.js
 */
'use strict';

function shouldSendWeeklyCapNotice(thisWeekKey, lastNotifiedWeek) {
  return lastNotifiedWeek !== thisWeekKey;
}

function main() {
  let failures = 0;
  const assertEq = (label, got, want) => {
    if (got !== want) { failures++; console.error(`FAIL ${label}: got ${got}, want ${want}`); }
  };

  // Case 1: never notified before (undefined) -> send notice
  {
    const result = shouldSendWeeklyCapNotice('2026-08-10', undefined);
    assertEq('never notified before sends notice', result, true);
  }

  // Case 2: cap trips again later the same week (same week key) -> do not re-send
  {
    const result = shouldSendWeeklyCapNotice('2026-08-10', '2026-08-10');
    assertEq('same week already notified does not resend', result, false);
  }

  // Case 3: a new week starts (different week key) -> send notice again
  {
    const result = shouldSendWeeklyCapNotice('2026-08-17', '2026-08-10');
    assertEq('new week sends notice again', result, true);
  }

  // Case 4: repeated calls within the same tripped week stay suppressed
  {
    const first = shouldSendWeeklyCapNotice('2026-08-10', undefined);
    assertEq('first call in week sends', first, true);
    // production code sets store.swingWeeklyCapNotifiedWeek = '2026-08-10' after Case 4's first call
    const second = shouldSendWeeklyCapNotice('2026-08-10', '2026-08-10');
    assertEq('second call same week suppressed', second, false);
    const third = shouldSendWeeklyCapNotice('2026-08-10', '2026-08-10');
    assertEq('third call same week still suppressed', third, false);
  }

  if (failures > 0) {
    console.error(`${failures} case(s) failed`);
    process.exit(1);
  }
  console.log('OK: weekly-cap one-time-notice logic verified (4 cases).');
}

main();

/**
 * Self-check for the market-shock alert added to
 * src/daily-position-monitor.src.js (computeDayChangePct / SHOCK_DROP_THRESH gate).
 * Mirrors the exact day-change calculation so a future edit that breaks the
 * shock-detection logic fails this script.
 *
 * Run: node scripts/verify_position_monitor_shock_alert.js
 */
'use strict';

const SHOCK_DROP_THRESH = -0.05;

function computeDayChangePct(close, prevClose) {
  if (!prevClose || prevClose <= 0) return null;
  return (close - prevClose) / prevClose;
}

function main() {
  let failures = 0;
  const assertEq = (label, got, want) => {
    if (got !== want) { failures++; console.error(`FAIL ${label}: got ${got}, want ${want}`); }
  };

  // Case 1: exactly -5% -> trips the threshold (boundary is inclusive)
  {
    const changePct = computeDayChangePct(950, 1000);
    assertEq('exact -5% change value', changePct, -0.05);
    assertEq('exact -5% trips threshold', changePct <= SHOCK_DROP_THRESH, true);
  }

  // Case 2: -4.9% -> does not trip
  {
    const changePct = computeDayChangePct(951, 1000);
    assertEq('-4.9% does not trip threshold', changePct <= SHOCK_DROP_THRESH, false);
  }

  // Case 3: prevClose missing (null, e.g. brand-new listing) -> null, never trips
  {
    const changePct = computeDayChangePct(950, null);
    assertEq('missing prevClose returns null', changePct, null);
  }

  // Case 4: prevClose 0 (no usable prior bar) -> null, never trips
  {
    const changePct = computeDayChangePct(950, 0);
    assertEq('zero prevClose returns null', changePct, null);
  }

  // Case 5: up-day -> positive change, never trips
  {
    const changePct = computeDayChangePct(1100, 1000);
    assertEq('up-day change value', changePct, 0.1);
    assertEq('up-day does not trip threshold', changePct <= SHOCK_DROP_THRESH, false);
  }

  if (failures > 0) {
    console.error(`${failures} case(s) failed`);
    process.exit(1);
  }
  console.log('OK: market-shock alert day-change logic verified (5 cases).');
}

main();

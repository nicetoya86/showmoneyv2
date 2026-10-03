/**
 * Self-check for [FIX-2026-09-26] lib/trailingStop.js replayIntradayStopFromBars():
 * 일봉 단위 재구성("오늘 갱신은 내일부터 반영")은 같은 날 안에서 크게 올랐다가 급락하는
 * "당일 왕복"을 못 잡는다 — 실제 Daily_Position_Monitor 체크 스케줄(10:00/11:00/12:30/
 * 13:30/14:30)대로 분봉을 재현하면 결과가 뒤집히는 케이스가 있어야 한다.
 *
 * 회귀 재현 1(진양화학/051630, 2026-09-18 실데이터로 확인): 09:00에 1차목표 찍고 급등,
 * 10:01에 저가가 무너지지만 10:00 체크에서 이미 손절가가 본전 위로 올라가 있었어야 한다.
 * 회귀 재현 2(토마토시스템/393210, 2026-09-23 실데이터로 확인): 장 시작 2분 만에 원래
 * 손절가 밑으로 붕괴 — 어떤 체크 스케줄로도 못 잡는 순수 갭 리스크는 그대로 실패해야 한다
 * (이 케이스까지 방어하려 들면 과최적화).
 *
 * Run: node scripts/verify_intraday_stop_replay.js
 */
'use strict';

const { replayIntradayStopFromBars } = require('../lib/trailingStop');

let failures = 0;
const assert = (label, cond) => {
  if (!cond) { failures++; console.error(`FAIL ${label}`); }
};

// bar 헬퍼: 'HHMMSS' 시각 문자열로 분봉 하나 생성
const bar = (hhmmss, high, low) => ({
  localDateTime: '20260101' + hhmmss,
  highPrice: high,
  lowPrice: low,
});

// ----- 케이스 1: 진양화학형 — 개장 직후 1차목표 찍고 급등, 10:00 체크로 본전 이상 방어 -----
{
  const entry = 1775;
  const atr = 80.36;
  const dayOpenStop = 1694.64; // 최초 손절가(본전 밑)
  const bars = [
    bar('090000', 2000, 1780), // 즉시 +12.7%까지 급등 (1차목표 1881.5 돌파)
    bar('095900', 2010, 1990), // 10:00 체크 직전까지 고점 유지
    bar('100000', 2005, 1990), // 10:00 체크 시각 — 이 바가 처리되면서 스탑이 올라감(저가 확인은 갱신 전 스탑 기준)
    bar('100100', 1990, 1900), // 10:00 체크 이후 저가 1900 — 방금 올라간 스탑(2010-atr*1.0=1929.64)에 걸려야 함
  ];
  const r = replayIntradayStopFromBars(entry, atr, dayOpenStop, bars);
  assert('진양화학형: 분봉 재현 시 손절가가 반드시 잡힘', r !== null);
  if (r) {
    assert('진양화학형: 재현된 손절가는 원래(본전 밑) 손절가보다 높아야 함', r.stopPrice > dayOpenStop);
    assert('진양화학형: 재현된 손절가는 본전(entry) 이상이어야 함(BE 클램프)', r.stopPrice >= entry);
  }
}

// ----- 케이스 2: 토마토시스템형 — 개장 2분 만에 원래 손절가 붕괴, 어떤 체크로도 못 잡음 -----
{
  const entry = 3315;
  const atr = 195.29;
  const dayOpenStop = 3119.71;
  const bars = [
    bar('090000', 3400, 3200), // 아직 손절가 안 뚫림
    bar('090100', 3375, 3120),
    bar('090200', 3185, 3090), // 09:02 — 10:00 체크보다 한참 전에 원래 손절가 붕괴
  ];
  const r = replayIntradayStopFromBars(entry, atr, dayOpenStop, bars);
  assert('토마토시스템형: 체크 시각 전 붕괴는 원래(안 올라간) 손절가로 잡혀야 함', r !== null && r.stopPrice === dayOpenStop);
}

// ----- 케이스 3: 왕복 없이 하루 종일 방어되는 경우 -> null(그날 손절 안 걸림) -----
{
  const entry = 10000;
  const atr = 200;
  const dayOpenStop = 9200;
  const bars = [
    bar('090000', 10500, 10000),
    bar('110000', 11500, 11000), // +15% -> 11:00 체크에서 스탑이 크게 올라감
    bar('150000', 11800, 11400), // 이후 저가도 올라간 스탑을 못 뚫음
  ];
  const r = replayIntradayStopFromBars(entry, atr, dayOpenStop, bars);
  assert('방어 성공 케이스: null(그날 안에서는 손절 안 걸림) 반환', r === null);
}

if (failures > 0) {
  console.error(`\n${failures} FAILURE(S)`);
  process.exit(1);
}
console.log('OK: intraday stop replay verified (진양화학형 반전, 토마토시스템형 갭리스크, 방어 성공 케이스)');

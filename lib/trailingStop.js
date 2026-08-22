// 트레일링 스탑 계산 — Daily_Position_Monitor(실시간 갱신)와 weekly_reporter(사후 재구성)가
// 동일한 로직을 공유해야 리포트의 손절일 판정이 실제 운영 동작과 일치한다.
const TRAIL_BE_GAIN   = 0.03;   // 수익률 3% 이상: 손절→진입가(본전)
const TRAIL_5_GAIN    = 0.05;   // 수익률 5% 이상: 손절→고점−ATR×1.5
const TRAIL_10_GAIN   = 0.10;   // 수익률 10% 이상: 손절→고점−ATR×1.0
const TRAIL_15_GAIN   = 0.15;   // 수익률 15% 이상: 손절→고점−ATR×0.7
const TRAIL_MULT_5    = 1.5;
const TRAIL_MULT_10   = 1.0;
const TRAIL_MULT_15   = 0.7;

function getAtr(atrAbs, currentHigh, currentLow, currentClose) {
  if (atrAbs && Number.isFinite(atrAbs) && atrAbs > 0) return atrAbs;
  // atrAbs 없을 때: 당일 고-저 범위로 근사
  return Math.max(currentHigh - currentLow, currentClose * 0.02);
}

// currentGain은 장중 고가 기준으로 넘겨야 한다([A안 2026-08-22] 종가 기준으로 게이팅하면
// 장중 목표가 터치 후 종가가 밀릴 때 본전 스탑이 전혀 발동하지 않는 문제가 있었음).
function calcTrailingStop(entry, currentHigh, atr, currentGain, existingStop) {
  let newStop = existingStop;

  if (currentGain >= TRAIL_15_GAIN) {
    newStop = currentHigh - atr * TRAIL_MULT_15;
  } else if (currentGain >= TRAIL_10_GAIN) {
    newStop = currentHigh - atr * TRAIL_MULT_10;
  } else if (currentGain >= TRAIL_5_GAIN) {
    newStop = currentHigh - atr * TRAIL_MULT_5;
  } else if (currentGain >= TRAIL_BE_GAIN) {
    newStop = entry; // 본전 스탑
  }

  // 스탑은 절대 낮아지지 않음 (트레일링)
  return Math.max(newStop, existingStop);
}

module.exports = {
  TRAIL_BE_GAIN, TRAIL_5_GAIN, TRAIL_10_GAIN, TRAIL_15_GAIN,
  TRAIL_MULT_5, TRAIL_MULT_10, TRAIL_MULT_15,
  getAtr, calcTrailingStop,
};

// 트레일링 스탑 계산 — Daily_Position_Monitor(실시간 갱신)와 weekly_reporter(사후 재구성)가
// 동일한 로직을 공유해야 리포트의 손절일 판정이 실제 운영 동작과 일치한다.
// [FIX-2026-10-03] 본전 상향 기준 3% → 6%(≈1차목표 target1=목표×0.6). 3%에서 본전으로 올리면 단기 눌림에 걸려
// 이후 목표까지 간 종목을 털어내는 비용이 보호 효과(175/470건이 실제 손절 회피)와 거의 상쇄되고 약간 순손해였다
// (백테스트 2,686건 일봉 재현: 6%가 4개 연도 전부 개선 +0.03pp/건, 라이브 분봉 79건 +0.11pp; 둘 다 95% CI가 0 포함 —
// ponytail: 효과가 작고 통계적으로 확정 아님, 주간 리포트의 부분익절/BE청산 비율로 계속 점검).
// 6%로 두는 이유: 1차목표 도달 후 손실 없음(partial_win 불변식, weekly-reporter)을 유지하면서 BE 조기발동만 줄이기 위함.
const TRAIL_BE_GAIN   = 0.06;   // 수익률 6% 이상: 손절→진입가(본전) 이상
const TRAIL_5_GAIN    = 0.05;   // 수익률 5% 이상: 손절→고점−ATR×1.5 (BE 게이트 6% 안에서만 적용되므로 사실상 6%~10% 구간)
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

  if (currentGain >= TRAIL_BE_GAIN) {
    if (currentGain >= TRAIL_15_GAIN) {
      newStop = currentHigh - atr * TRAIL_MULT_15;
    } else if (currentGain >= TRAIL_10_GAIN) {
      newStop = currentHigh - atr * TRAIL_MULT_10;
    } else if (currentGain >= TRAIL_5_GAIN) {
      newStop = currentHigh - atr * TRAIL_MULT_5;
    }
    // [2026-09-13] ATR 변동성이 클 때 "고점-ATR×배수"가 본전보다 낮게 나올 수 있음
    // (원익/흥구석유/금강철강 09-01~09-04 케이스: +35~43% 찍고 확정 -0.1~-7.4%로 마감).
    // gain>=3% 티어에 들어온 이상 본전 밑으로는 절대 안 내려가도록 하한을 건다.
    newStop = Math.max(newStop, entry);
  }

  // 스탑은 절대 낮아지지 않음 (트레일링)
  return Math.max(newStop, existingStop);
}

// Daily_Position_Monitor의 실제 체크 스케줄(2026-09-19 cadence tightening, commit 878c54e).
// weekly_reporter의 일봉 단위 재구성("오늘 갱신은 내일부터 반영")은 같은 날 안에서 큰 상승 후
// 급락하는 "당일 왕복"을 못 잡는다 — 실제로는 이 체크 시각마다 트레일링이 올라갔을 것이므로
// 분봉으로 재현해야 그날의 진짜 손절가/시각이 나온다.
const INTRADAY_CHECK_TIMES = ['100000', '110000', '123000', '133000', '143000'];

// [FIX-2026-09-26] 순수 함수 — 분봉 배열을 받아 그날의 실제 체크 스케줄대로 트레일링을
// 재현한다(I/O 없음, 테스트 용이). minuteBars는 { localDateTime:'yyyyMMddHHmmss', highPrice,
// lowPrice } 형태로 시간순 정렬돼 있다고 가정(Naver 분봉 API 응답 그대로).
// 반환: 그날 안에서 실제로 손절가에 닿으면 { stopPrice, stopTime } — 못 닿으면(트레일링이
// 먼저 올라가 방어됨) null.
function replayIntradayStopFromBars(entry, atrAbs, dayOpenStop, minuteBars, checkTimes) {
  checkTimes = checkTimes || INTRADAY_CHECK_TIMES;
  let maxHighSoFar = entry;
  let runningStop = dayOpenStop;
  let checkIdx = 0;
  for (const bar of minuteBars) {
    const t = String(bar.localDateTime).slice(8, 14); // 'HHMMSS'
    const hi = Number(bar.highPrice);
    const lo = Number(bar.lowPrice);
    if (hi > maxHighSoFar) maxHighSoFar = hi;
    if (runningStop > 0 && lo <= runningStop) {
      return { stopPrice: runningStop, stopTime: t };
    }
    while (checkIdx < checkTimes.length && t >= checkTimes[checkIdx]) {
      const gain = (maxHighSoFar - entry) / entry;
      const atr = getAtr(atrAbs, maxHighSoFar, lo, hi);
      runningStop = calcTrailingStop(entry, maxHighSoFar, atr, gain, runningStop);
      checkIdx++;
    }
  }
  return null;
}

module.exports = {
  TRAIL_BE_GAIN, TRAIL_5_GAIN, TRAIL_10_GAIN, TRAIL_15_GAIN,
  TRAIL_MULT_5, TRAIL_MULT_10, TRAIL_MULT_15,
  INTRADAY_CHECK_TIMES,
  getAtr, calcTrailingStop, replayIntradayStopFromBars,
};

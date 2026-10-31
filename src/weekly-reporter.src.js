const { isHoliday, isWeekend } = require('../lib/holidays');
const { pct, sleep } = require('../lib/format');
const { createTelegram } = require('../lib/telegramClient');
const { createNaverClient } = require('../lib/naverClient');
const { getAtr, calcTrailingStop, TRAIL_BE_GAIN, replayIntradayStopFromBars } = require('../lib/trailingStop');
// (번들러는 한 줄짜리 require만 인라인한다 — 다중 줄로 쪼개지 말 것)
const { computeShadowCohorts, shadowGate, computeShadowStateCohorts, shadowStateGate, shadowStateSummary, shadowFormatStateSection } = require('../lib/shadowCohorts');

const run = async function () {
  const BOT = SECRETS.BOT;
  const CHAT = SECRETS.CHAT;
  const http = async (o) => await this.helpers.httpRequest(Object.assign({ timeout: 30000 }, o));
  const NL = String.fromCharCode(10);
  const telegram = createTelegram(http, BOT, CHAT);
  const naver = createNaverClient(http);

  // ===== Logger initialization (n8n sandbox safe) =====
  let logger;
  try {
    const JsonLogger = require('./lib/logger');
    logger = new JsonLogger('weekly_reporter');
  } catch (e) {
    logger = { info:()=>{}, error:()=>{}, warning:()=>{}, debug:()=>{}, generateRequestId:(p)=>`${p}_${Date.now()}` };
  }
  const requestId = logger.generateRequestId('REPORT');
  logger.info('Weekly reporter started', { phase: 'initialization' }, requestId);

  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const today = `${kst.getUTCFullYear()}-${String(kst.getUTCMonth() + 1).padStart(2, '0')}-${String(kst.getUTCDate()).padStart(2, '0')}`;

  const todayDow = kst.getUTCDay();
  if (!isWeekend(todayDow) && isHoliday(today)) return [{ json: { skipped: true, reason: 'Holiday', today } }];

  // 마지막 완료된 거래일 (토요일/장중 실행 시 Naver API가 비거래일 endDate에 빈 배열 반환 방지)
  const getPrevTradingDay = () => {
    let d = new Date(Date.now() + 9 * 3600000 - 24 * 3600000);
    for (let i = 0; i < 10; i++) {
      const dow = d.getUTCDay();
      const ds = d.toISOString().slice(0, 10);
      if (dow >= 1 && dow <= 5 && !isHoliday(ds)) return ds;
      d = new Date(d.getTime() - 24 * 3600000);
    }
    return new Date(Date.now() + 9 * 3600000 - 24 * 3600000).toISOString().slice(0, 10);
  };
  const prevTradingDay = getPrevTradingDay(); // 토요일 실행 시 금요일, 장중 실행 시 전일

  // N 거래일 후 날짜 계산 (주말/공휴일 제외)
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

  // 지난 주 거래일 목록 (토요일 트리거 기준: 직전 월~금)
  const getWeekDates = (ref) => {
    const dates = [];
    const d = new Date(ref + 'T00:00:00Z');
    const dow = d.getUTCDay(); // 6=토
    const daysToFri = (dow === 6) ? 1 : (dow + 2); // Sat→1, Sun→2, Mon→3 ... Fri→7 (last week)
    const friday = new Date(d.getTime() - daysToFri * 24 * 60 * 60 * 1000);
    const monday = new Date(friday.getTime() - 4 * 24 * 60 * 60 * 1000);
    for (let i = 0; i < 5; i++) {
      const cur = new Date(monday.getTime() + i * 24 * 60 * 60 * 1000);
      const wd = cur.getUTCDay();
      const ds = `${cur.getUTCFullYear()}-${String(cur.getUTCMonth() + 1).padStart(2, '0')}-${String(cur.getUTCDate()).padStart(2, '0')}`;
      if (wd >= 1 && wd <= 5 && !isHoliday(ds)) dates.push(ds);
    }
    return dates;
  };

  const input = (items && items[0] && items[0].json) || {};
  const forceTest = !!input.forceTest;
  if (forceTest) {
    const msg = '[주간 스윙 리포트 테스트] 시스템 정상 작동 - ' + kst.toISOString().slice(0, 16).replace('T', ' ') + ' KST';
    try { await telegram.send(msg); } catch (e) {}
    return [{ json: { testSent: true } }];
  }

  const store = this.getWorkflowStaticData('global');
  if (!store.weeklyRecommendations) store.weeklyRecommendations = {};
  const weekDates = getWeekDates(today);
  if (weekDates.length === 0) return [{ json: { skipped: true, reason: 'No trading days this week' } }];

  // 이번 주 스윙 추천 수집 (scalping 제외 - swing 전용)
  const recs = [];
  for (const ds of weekDates) {
    const arr = store.weeklyRecommendations[ds] || [];
    for (const r of arr) {
      if (r.type === 'swing') recs.push({ ...r, date: ds });
    }
  }

  // [CARRYOVER] 지난주 이전 추천 중 보유기간이 이번 주까지 걸쳐있는 종목 별도 수집
  // (예: 지난주 목요일 추천 + holdingDays=5 → 이번주 초까지 보유 중인 케이스)
  const carryOverRecs = [];
  for (const dateKey in store.weeklyRecommendations) {
    if (dateKey >= weekDates[0]) continue; // 이번 주 이후는 위에서 이미 처리됨
    const arr = store.weeklyRecommendations[dateKey] || [];
    for (const r of arr) {
      if (r.type !== 'swing') continue;
      const holdDays = r.holdingDays || 3;
      const exitDate = addTradingDays(dateKey, holdDays);
      if (exitDate >= weekDates[0]) carryOverRecs.push({ ...r, date: dateKey, carryOver: true });
    }
  }

  if (recs.length === 0 && carryOverRecs.length === 0) {
    const msg = '[주간 스윙 리포트]' + NL +
      '📅 ' + weekDates[0] + ' ~ ' + weekDates[weekDates.length - 1] + NL + NL +
      '이번 주 스윙 추천 없음';
    try { await telegram.send(msg); } catch (e) {}
    return [{ json: { sent: true, count: 0 } }];
  }

  const allRecs = recs.concat(carryOverRecs);

  // [BUGFIX-2026-07-19] 거래 자체가 없던 날(상한가 잠김 등) 판별 — Naver 일봉 API는
  // 이런 날 open/high/low/volume을 전부 0으로 반환하는데, 이를 그대로 두면
  // "저가 0 <= 진입가/손절가"가 항상 참이 되어 실제로 닿지 않은 가격을 도달했다고
  // 오판정하는 버그가 생긴다 (2026-07-13~18 주간 리포트 QA에서 한성기업/003680 확인).
  const isTradedDay = (day) => Number(day.accumulatedTradingVolume) > 0;

  // [BUGFIX-2026-07-19] 목표가/손절가가 같은 날짜에 함께 도달하면 일봉만으로는 선후관계를
  // 알 수 없어 "목표가 먼저"로 낙관 판정하던 버그(동화약품/000020 2026-07-16 케이스로 확인:
  // 실제로는 09:01에 이미 목표가 초과 후 급락, 15:13에 진입가·손절가가 동시에 찍힘).
  // 분봉으로 실제 진입 체결 시각 이후 목표가/손절가 중 무엇이 먼저 찍혔는지 재확인한다.
  // 분봉 조회 실패 시(오래된 날짜 등) 기존 일봉 기준 로직으로 안전하게 폴백한다.
  const resolveSameDayOrder = async (code, dateStr, entry, target, stop) => {
    const minuteData = await naver.fetchMinute(code, dateStr);
    if (!minuteData) return null;
    let entryTime = null;
    for (const bar of minuteData) {
      if (Number(bar.lowPrice) <= entry) { entryTime = bar.localDateTime; break; }
    }
    if (!entryTime) return null; // 분봉상 진입 체결 확인 불가 → 폴백
    let targetTime = null;
    let stopTime = null;
    for (const bar of minuteData) {
      if (bar.localDateTime < entryTime) continue;
      if (!targetTime && target && Number(bar.highPrice) >= target) targetTime = bar.localDateTime;
      if (!stopTime && stop && Number(bar.lowPrice) <= stop) stopTime = bar.localDateTime;
    }
    if (targetTime && stopTime) return targetTime <= stopTime ? 'target' : 'stop';
    if (targetTime) return 'target';
    if (stopTime) return 'stop';
    return 'neither';
  };

  // [FIX-2026-09-26] 일봉 단위 재구성은 "오늘 갱신은 내일부터 반영"으로 단순화돼 있어(아래
  // day-loop 주석 참고), 같은 날 안에서 크게 올랐다가 반납하는 "당일 왕복"의 실제 손절가를
  // 못 잡는다 — 진양화학(051630, 09-18) 케이스로 확인: 09:00에 1차목표 찍고 급락했는데,
  // 일봉 모델은 원래(안 올라간) 손절가로 하루 종일 비교해 확정 -4.5%로 잡았다. 실제로는
  // Daily_Position_Monitor의 체크 스케줄(10:00 등)이 그 사이에 손절가를 본전 위로 올려서,
  // 분봉으로 재현하면 확정이 오히려 +9%대 플러스로 뒤집힌다. 이 함수는 그 재현을 위해
  // 분봉을 가져오기만 하고, 실제 재현 계산은 lib/trailingStop.js의 순수 함수에 위임한다.
  // 호출 비용 때문에(분봉 API 1회 추가) 당일 고가가 트레일링 티어(3%+)에 진입한 "왕복 후보일"
  // 에서만 호출한다(day-loop 참고).
  const replayIntradayStop = async (code, dateStr, entry, atrAbs, dayOpenStop) => {
    const minuteData = await naver.fetchMinute(code, dateStr);
    if (!minuteData || minuteData.length === 0) return undefined; // 분봉 없음 → 폴백 신호
    return replayIntradayStopFromBars(entry, atrAbs, dayOpenStop, minuteData);
  };

  // ===== 성과 평가: 매수가 진입 여부 + 목표가/손절가 도달 여부 =====
  const details = [];
  let wins = 0;
  let partialWins = 0;
  let losses = 0;
  let notEntered = 0;

  for (const r of allRecs) {
    try {
      const holdDays = r.holdingDays || 3;
      const exitDate = addTradingDays(r.date, holdDays);
      // exitDate가 미래인 경우 prevTradingDay 사용 (비거래일 endDate → Naver API 빈배열 방지)
      const endCheck = exitDate <= today ? exitDate : prevTradingDay;

      const startStr = r.date.replace(/-/g, '');
      const endStr = endCheck.replace(/-/g, '');

      const data = await naver.fetchDaily(r.code, startStr, endStr);

      if (!data) {
        // [2026-07-25] no_data는 종목별 데이터 부재뿐 아니라 Naver 응답 파싱 실패(BOM/Buffer 등)로도
        // 발생할 수 있다 — 원인 추적을 위해 반드시 로그를 남긴다(과거엔 조용히 리포트에서만 빠졌음).
        logger.warning('naver fetchDaily returned no data', { code: r.code, date: r.date, startStr, endStr }, requestId);
        details.push({ ...r, result: 'no_data', maxReturn: 0, finalReturn: 0, exitDate });
        await sleep(400);
        continue;
      }

      // 추천일 ~ exitDate 범위 필터
      const recDateStr = r.date.replace(/-/g, '');
      const exitDateStr = exitDate.replace(/-/g, '');
      const relevant = data.filter((d) => d.localDate >= recDateStr && d.localDate <= exitDateStr);

      // W-002 수정: relevant 비어있으면 데이터 없음으로 처리 (not_entered 오판정 방지)
      if (relevant.length === 0) {
        details.push({ ...r, result: 'no_data', maxReturn: 0, finalReturn: 0, exitDate });
        await sleep(400);
        continue;
      }

      // ===== 매수가 진입 여부 확인 =====
      // [FIX-2026-09-19] 예전엔 "추천 매수가(r.entry)에 저가(low)가 도달"해야 진입으로 쳤음(지정가
      // 리밋 대기 모델). 그런데 실제 발송 문구(swing-scanner.src.js entryNote)는 모든 케이스에서
      // "현재가 기준 즉시 진입" 또는 "실시간 체결가 기준 즉시 진입"이지 "눌림목 대기"가 아니다 —
      // entry 자체가 이미 발송 시점의 (거의) 체결 가능가다(TOSS-LIVEPRICE 재계산 포함). 그런데도
      // 리포트만 지정가 대기 모델로 판정하다 보니, 눌림 없이 쭉 오른 강한 종목일수록 "매수 미도달"로
      // 잘못 분류돼 최고 성과 종목이 통계에서 통째로 빠지는 문제가 09-19 리포트에서 3주 연속 확인됨
      // (샌즈랩/라온시큐어/한국첨단소재 등 이후최고 +48~56%). 문구와 판정 모델을 일치시켜 즉시
      // 체결로 취급한다 — 매수가 미설정(데이터 이상)일 때만 기존처럼 예외 처리.
      const entryHit = true; // 즉시진입 모델 — 항상 진입으로 간주

      // 매수가 미진입 → 리포트 제외
      if (!entryHit) {
        notEntered++;
        details.push({ ...r, result: 'not_entered', maxReturn: 0, finalReturn: 0, exitDate });
        await sleep(400);
        continue;
      }

      let result = exitDate > today ? 'holding' : 'expired';
      let maxHigh = r.entry || 0;
      let finalClose = r.entry || 0;
      let hitTargetDay = null;
      let hitTarget1Day = null;
      let hitStopDay = null;
      let stopAtHitDay = null; // hitStopDay 당일 장 시작 시점에 실제로 걸려 있던 stop (분봉 재확인용)

      // [FIX-2026-08-22] 손절일은 "지금 시점의(이미 트레일링으로 올라간) stop"을 과거 저가에
      // 소급 적용하지 않고, entry일부터 day-by-day로 Daily_Position_Monitor와 동일한 트레일링을
      // 재현하며 그날그날의 stop과 비교한다 — 그래야 급등 후 반납한 종목이 "랠리 시작 전에 이미
      // 손절됐다"는 식으로 잘못 앞당겨 판정되지 않는다(target 도달일보다 먼저 찍혀 win이 loss로
      // 뒤집히는 오분류의 원인이었음). initialStop이 없는 과거 레코드는 현재 stop으로 폴백한다.
      // 실제 운영에서 트레일링은 "그날 장이 끝난 뒤" 갱신되므로, 그날 저가는 "전날까지 갱신된
      // stop"과 비교한 다음에(순서 중요) 그날 고가/이득으로 다음날 stop을 갱신해야 한다.
      let runningStop = (r.initialStop != null ? r.initialStop : r.stop) || 0;

      for (const day of relevant) {
        const high = Number(day.highPrice);
        const low = Number(day.lowPrice);
        finalClose = Number(day.closePrice);
        // [BUGFIX-2026-07-19] 거래 없던 날(0값)은 고가/저가 도달판정에서 제외.
        // finalClose는 halt 당일에도 유효한(직전가 고정) 값이라 continue 이전에 갱신한다.
        if (!isTradedDay(day)) continue;
        if (high > maxHigh) maxHigh = high;
        if (!hitTargetDay && r.target && high >= r.target) {
          hitTargetDay = day.localDate.slice(0, 4) + '-' + day.localDate.slice(4, 6) + '-' + day.localDate.slice(6, 8);
        }
        if (!hitTarget1Day && r.target1 && high >= r.target1) {
          hitTarget1Day = day.localDate.slice(0, 4) + '-' + day.localDate.slice(4, 6) + '-' + day.localDate.slice(6, 8);
        }
        if (!hitStopDay && runningStop > 0 && low <= runningStop) {
          const dayStr = day.localDate.slice(0, 4) + '-' + day.localDate.slice(4, 6) + '-' + day.localDate.slice(6, 8);
          // [FIX-2026-09-26] 당일 왕복 후보: 그날 고가가 이미 본전 트레일링 티어(TRAIL_BE_GAIN, 현재 6%+)에
          // 진입했다면, "오늘 갱신은 내일부터"라는 단순화 때문에 실제보다 낮은(안 올라간)
          // 스탑으로 오판정할 수 있다 — 분봉으로 그날의 진짜 체크-스케줄 트레일링을 재현한다.
          const dayHighGain = r.entry > 0 ? (high - r.entry) / r.entry : 0;
          if (dayHighGain >= TRAIL_BE_GAIN) {
            const replay = await replayIntradayStop(r.code, dayStr, r.entry, r.atrAbs, runningStop);
            await sleep(300);
            if (replay === undefined) {
              // 분봉 조회 실패 → 기존처럼 일봉 기준(보수적) 폴백
              hitStopDay = dayStr;
              stopAtHitDay = runningStop;
            } else if (replay !== null) {
              hitStopDay = dayStr;
              stopAtHitDay = replay.stopPrice;
            }
            // replay === null: 체크 스케줄대로면 그날 안에서는 실제로 손절 안 걸림 — 다음날로 이월.
          } else {
            hitStopDay = dayStr;
            stopAtHitDay = runningStop;
          }
        }
        if (r.entry > 0 && runningStop > 0) {
          const tierGain = (high - r.entry) / r.entry;
          const atr = getAtr(r.atrAbs, high, low, finalClose);
          runningStop = calcTrailingStop(r.entry, high, atr, tierGain, runningStop);
        }
      }

      // [FIX-2026-09-05] target1(1차목표)과 손절가가 같은 날 찍히면, 풀타겟 케이스와 동일하게
      // 일봉만으로는 선후관계가 불명확한데도 "target1 먼저"로 낙관 판정해 partial_win으로 잘못
      // 분류하던 버그. 그날 장중에 손절가가 target1보다 먼저 찍혔다면 1차목표조차 못 찍은 loss다
      // (09-05 주간 리포트에서 써니전자/흥구석유/네오이문텍/위더스제약 4종목이 1차=청산 당일인데
      // 확정%가 마이너스로 나온 게 이 케이스 — partial_win인데 확정 손실이라는 자기모순 표기).
      // 풀타겟 분봉재확인(resolveSameDayOrder)과 같은 함수를 target1 가격으로 재사용한다.
      const resolvePartialOrLoss = async () => {
        if (!hitTarget1Day || hitTarget1Day > hitStopDay) return 'loss';
        if (hitTarget1Day < hitStopDay) return 'partial_win';
        const order1 = await resolveSameDayOrder(r.code, hitTarget1Day, r.entry, r.target1, stopAtHitDay);
        await sleep(300);
        return order1 === 'stop' ? 'loss' : 'partial_win'; // neither/null → 기존처럼 낙관 폴백
      };

      // 목표/손절 중 먼저 도달한 것 기준 판정
      // partial_win: 1차 목표 달성 후 손절 (이익 실현 일부)
      if (hitTargetDay && hitStopDay && hitTargetDay === hitStopDay) {
        // [BUGFIX-2026-07-19] 같은 날 동시 도달 — 일봉만으로는 선후관계 불명, 분봉으로 재확인
        const order = await resolveSameDayOrder(r.code, hitTargetDay, r.entry, r.target, stopAtHitDay);
        await sleep(300);
        if (order === 'target') result = 'win';
        else if (order === 'neither' || order === 'stop') result = await resolvePartialOrLoss();
        else result = 'win'; // 분봉 조회 실패(null) 시 기존 로직대로 낙관적 폴백
      } else if (hitTargetDay && hitStopDay) {
        // [FIX-2026-10-03] 풀타겟이 손절보다 "늦게" 찍힌 경우(손절 먼저)도 무조건 loss가 아니다 —
        // 그 전에 1차목표를 먼저 찍고 본전 이상 트레일링 스탑에서 청산됐다면 부분익절이다
        // (KSS해운 044450: 1차 09-28 → +6.0% 청산 09-29 → 이후 풀타겟 10-01인데 손절로 분류됨).
        // 1차목표 선후 판정은 resolvePartialOrLoss가 담당(target1 없으면/손절 뒤면 loss, 확정<0이면 아래서 loss 강제).
        result = hitTargetDay <= hitStopDay ? 'win' : await resolvePartialOrLoss();
      } else if (hitTargetDay) {
        result = 'win';
      } else if (hitStopDay) {
        result = await resolvePartialOrLoss();
      }

      // [FIX-2026-09-26] 보유기간(holdingDays)이 다 지나도록 목표/손절 어느 쪽도 안 걸린
      // 경우 — 예전엔 'expired' 상태로 남아 win/partial/loss 어디에도 안 잡히고 보유
      // 섹션에 방치됐다(성과 통계에서 통째로 빠짐). 만기 시점 종가(보유하던 가격)를
      // 진입가와 비교해 이익이면 수익, 손실이면 손절로 확정 판정한다.
      const expiredForced = (result === 'expired');
      if (expiredForced && r.entry > 0) {
        result = finalClose >= r.entry ? 'win' : 'loss';
      }

      const maxReturn = r.entry > 0 ? (maxHigh - r.entry) / r.entry : 0;
      const finalReturn = r.entry > 0 ? (finalClose - r.entry) / r.entry : 0;
      const targetPct = (r.entry > 0 && r.target > 0) ? (r.target / r.entry - 1) : 0;
      // 실제로 손절이 걸렸다면 그 시점의 stop(stopAtHitDay)을, 만기청산이면 만기 종가를,
      // 그 외엔 현재 stop을 기준으로 한다.
      const stopForPct = expiredForced ? finalClose
        : hitStopDay && stopAtHitDay != null ? stopAtHitDay : r.stop;
      const stopPct = (r.entry > 0 && stopForPct > 0) ? (stopForPct / r.entry - 1) : 0;

      // [FIX-2026-09-26] 부분익절(partial_win)은 설계상 손실이면 안 된다(트레일링 본전 상향
      // 덕분 — 위 replayIntradayStop이 대부분의 "당일 왕복" 케이스를 이미 바로잡는다). 그래도
      // 체크 시각 사이의 순간 갭다운(예: 토마토시스템 393210 09-23, 개장 2분만에 손절가 붕괴)
      // 처럼 어떤 체크로도 못 잡는 극단적 케이스가 남을 수 있다 — 그런 잔여 케이스까지
      // "부분익절"로 표기하면 주간 리포트 성공률(부분포함) 지표가 왜곡된다. 최종 확정이
      // 손실이면 손절로 재분류해 불변식을 코드로 강제한다.
      if (result === 'partial_win' && stopPct < 0) result = 'loss';

      if (result === 'win') wins++;
      else if (result === 'partial_win') partialWins++;
      else if (result === 'loss') losses++;

      details.push({ ...r, result, maxReturn, finalReturn, exitDate, hitTargetDay, hitTarget1Day, hitStopDay, targetPct, stopPct, expiredForced });
    } catch (e) {
      logger.error('weekly reporter position evaluation failed', { code: r.code, date: r.date, error: e && e.message }, requestId);
      details.push({ ...r, result: 'error', maxReturn: 0, finalReturn: 0, exitDate: '' });
    }
    await sleep(400);
  }

  // 매수 진입 종목만 평가 대상
  const entered = details.filter((d) => d.result !== 'not_entered' && d.result !== 'no_data' && d.result !== 'error');
  // [2026-08-29, 2026-09-26 갱신] 목표달성률 = 최종 목표 100% 완주(win)만 인정. 1차달성
  // (partial_win)은 "덜 번 것"이지 손실이 아니어야 한다 — 트레일링 로직상(lib/trailingStop.js
  // TRAIL_BE_GAIN=6%, 2026-10-03에 3%에서 상향 — 1차목표 target1(=target*0.6, 약 6%)과 맞춤) target1에 닿으면 손절선이 본전 이상으로 올라가는 게 설계
  // 의도다. 다만 일봉 재구성만으로는 "당일 왕복"을 못 잡아 이 불변식이 깨지는 경우가 있었고
  // (진양화학 051630 09-18 등), replayIntradayStop(분봉 기반 체크스케줄 재현) + stopPct<0
  // 강제 재분류(위 day-loop/판정부 참고)로 바로잡았다. 그래도 남는 partial_win은 손절
  // 리스트에 합치지 않고 별도 섹션(🎯 부분익절)으로 유지하되, 헤드라인 달성률 분자에서는
  // 제외한다(완주 못 했다는 사실은 그대로 보여줘야 함). 분모(evaluated)는 기존대로
  // win+partial_win+loss — [FIX-2026-09-26] 'expired'(보유기간 만료까지 목표/손절 모두
  // 미도달)는 이제 위 day-loop 직후에서 만기 종가 기준으로 win/loss로 강제 확정되므로
  // (expiredForced) 이 시점엔 실질적으로 남지 않는다(진입가가 0인 이상 케이스만 예외).
  const evaluated = entered.filter((d) => d.result === 'win' || d.result === 'partial_win' || d.result === 'loss');
  const winRate = evaluated.length > 0 ? wins / evaluated.length : 0;
  // 성공률(부분포함): 부분익절을 손실 아닌 성공으로 잡는 보조 지표 — 목표달성률과 나란히 표기.
  const successRate = evaluated.length > 0 ? (wins + partialWins) / evaluated.length : 0;
  const enteredCount = entered.length;

  // 섹션별 분류
  const winList = details.filter((d) => d.result === 'win');
  const partialWinList = details.filter((d) => d.result === 'partial_win');
  const lossList = details.filter((d) => d.result === 'loss');
  // [CARRYOVER] 보유 종목은 이번주 신규 추천분과 지난주 이월분을 분리해서 리포트
  const holdListAll = details.filter((d) => d.result === 'holding' || d.result === 'expired');
  const holdList = holdListAll.filter((d) => !d.carryOver);
  const holdListCarry = holdListAll.filter((d) => d.carryOver);

  // Log report statistics for QA tracing
  logger.info('Weekly report generated', {
    reportDate: today,
    totalPositions: details.length,
    wins: wins,
    partialWins: partialWins,
    losses: losses,
    holding: holdListAll.length,
    winRate: (winRate * 100).toFixed(1) + '%',
    successRate: (successRate * 100).toFixed(1) + '%',
    enteredCount: enteredCount
  }, requestId);

  // 각 섹션 내 수익률 기준 정렬
  winList.sort((a, b) => (b.maxReturn || 0) - (a.maxReturn || 0));
  holdList.sort((a, b) => (b.maxReturn || 0) - (a.maxReturn || 0));
  holdListCarry.sort((a, b) => (b.maxReturn || 0) - (a.maxReturn || 0));
  lossList.sort((a, b) => (a.maxReturn || 0) - (b.maxReturn || 0));
  partialWinList.sort((a, b) => (b.stopPct || 0) - (a.stopPct || 0));

  // ===== 깨진 종목명 보완: Naver API로 재조회 =====
  const isGarbled = (s) => !s || !/^[가-힣ᄀ-ᇿ㄰-㆏㈀-㈟！-ﾟ一-鿿 -~]+$/.test(s);
  const allCodes = [...new Set(details.map((d) => d.code))];
  for (const code of allCodes) {
    const cached = store.naverNames && store.naverNames[code];
    if (cached && cached !== code && !isGarbled(cached)) continue;
    const stored = details.find((d) => d.code === code)?.name;
    if (stored && stored !== code && !isGarbled(stored)) continue;
    try {
      const nr = await http({
        method: 'GET',
        url: 'https://m.stock.naver.com/api/stock/' + code + '/basic',
        json: true,
        headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.naver.com/', 'Accept-Language': 'ko-KR,ko;q=0.9' },
      });
      const nm = nr && (nr.stockName || nr.itemName || nr.name || nr.symbolName);
      if (nm && nm !== code && !isGarbled(nm)) {
        if (!store.naverNames) store.naverNames = {};
        store.naverNames[code] = nm;
      }
    } catch (e) {}
    await sleep(300);
  }

  const resolveName = (d) => {
    const cached = store.naverNames && store.naverNames[d.code];
    if (cached && cached !== d.code && !isGarbled(cached)) return cached;
    if (d.name && d.name !== d.code && !isGarbled(d.name)) return d.name;
    return d.code;
  };

  // HELPER-01: 날짜 단축 (2026-03-25 → 03-25)
  const shortDate = (ds) => (ds && ds.length >= 7) ? ds.slice(5) : (ds || '');
  // [CARRYOVER] 지난주 이월 종목 표시 태그
  const carryTag = (d) => d.carryOver ? '[이월] ' : '';

  // ===== 메시지 구성 =====
  let msg = '[주간 스윙 성과 리포트]' + NL +
    '📅 ' + weekDates[0] + ' ~ ' + weekDates[weekDates.length - 1] + NL +
    '━━━━━━━━━━━━━━━━━━━━' + NL +
    '총추천 ' + recs.length + '건' + (carryOverRecs.length > 0 ? ' (+이월 ' + carryOverRecs.length + '건)' : '') +
    ' │ 진입 ' + enteredCount + '건 │ 목표달성률 ' + (evaluated.length > 0 ? (winRate * 100).toFixed(0) + '%' : 'N/A') +
    ' (부분포함 ' + (evaluated.length > 0 ? (successRate * 100).toFixed(0) + '%' : 'N/A') + ')' + NL +
    '✅ 목표 ' + wins + '건 │ 🎯 부분익절 ' + partialWins + '건 │ ❌ 손절 ' + losses + '건 │ 🔄 보유 ' + holdList.length + '건' + NL +
    '━━━━━━━━━━━━━━━━━━━━' + NL;

  // ✅ 수익 종목
  if (winList.length > 0) {
    msg += NL + '✅ 수익 (' + winList.length + '건)' + NL;
    for (const d of winList) {
      const name = resolveName(d);
      const typeTag = d.isETF === false ? '[단일종목]' : d.isETF ? '[ETF]' : '';
      let line = carryTag(d) + typeTag + name + '(' + (d.code || '') + ') │ ' + shortDate(d.date);
      if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) line += ' │ 최고 ' + pct(d.maxReturn);
      if (d.hitTargetDay) line += ' │ ' + shortDate(d.hitTargetDay);
      // [FIX-2026-09-26] 목표가를 실제로 찍은 win과 구분 — 보유기간 만료 시점 종가가
      // 진입가보다 높아서 수익으로 확정된 경우 표시(목표 미완주였다는 사실을 숨기지 않음).
      if (d.expiredForced) line += ' │ 만기청산 │ 확정 ' + pct(d.finalReturn);
      if (d.grade) line += ' │ ' + d.grade;
      if (d.score) line += ' │ ' + d.score + '점';
      if (d.patternType) line += ' │ ' + d.patternType;
      if (d.signals && d.signals.length) line += ' │ ' + d.signals.join(',');
      msg += line + NL;
    }
  }

  // 🎯 1차 목표 달성 후 손절 (부분 수익 — 손실 아님, 목표달성률 분자에서만 제외)
  if (partialWinList.length > 0) {
    msg += NL + '🎯 부분익절 (' + partialWinList.length + '건, 목표 미완주)' + NL;
    for (const d of partialWinList) {
      const name = resolveName(d);
      const typeTag = d.isETF === false ? '[단일종목]' : d.isETF ? '[ETF]' : '';
      let line = carryTag(d) + typeTag + name + '(' + (d.code || '') + ') │ ' + shortDate(d.date);
      if (d.hitTarget1Day) line += ' │ 1차 ' + shortDate(d.hitTarget1Day);
      if (d.hitStopDay) line += ' │ 청산 ' + shortDate(d.hitStopDay);
      if (Number.isFinite(d.stopPct)) line += ' │ 확정 ' + pct(d.stopPct);
      if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) line += ' │ 최고 ' + pct(d.maxReturn);
      if (d.grade) line += ' │ ' + d.grade;
      if (d.score) line += ' │ ' + d.score + '점';
      if (d.patternType) line += ' │ ' + d.patternType;
      if (d.signals && d.signals.length) line += ' │ ' + d.signals.join(',');
      msg += line + NL;
    }
  }

  // 🔄 보유 종목
  if (holdList.length > 0) {
    msg += NL + '🔄 보유 (' + holdList.length + '건)' + NL;
    for (const d of holdList) {
      const name = resolveName(d);
      let line = name + '(' + (d.code || '') + ') │ ' + shortDate(d.date);
      if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) line += ' │ 최고 ' + pct(d.maxReturn);
      if (d.result === 'holding' && d.exitDate) line += ' │ 예정일 ' + shortDate(d.exitDate);
      if (d.result === 'expired') line += ' │ 보유예정일 ' + shortDate(d.exitDate || d.date);
      if (d.score) line += ' │ ' + d.score + '점';
      msg += line + NL;
    }
  }

  // 📌 이월 보유 종목 — 지난주 이전 추천, 보유기간 때문에 이번 주까지 보유 중
  if (holdListCarry.length > 0) {
    msg += NL + '📌 이월 보유 (전주 추천, ' + holdListCarry.length + '건)' + NL;
    for (const d of holdListCarry) {
      const name = resolveName(d);
      let line = name + '(' + (d.code || '') + ') │ ' + shortDate(d.date);
      if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) line += ' │ 최고 ' + pct(d.maxReturn);
      if (d.result === 'holding' && d.exitDate) line += ' │ 예정일 ' + shortDate(d.exitDate);
      if (d.result === 'expired') line += ' │ 보유예정일 ' + shortDate(d.exitDate || d.date);
      if (d.score) line += ' │ ' + d.score + '점';
      msg += line + NL;
    }
  }

  // ❌ 손절 종목 (진짜 손실 — 1차 목표조차 못 찍고 손절가 도달)
  if (lossList.length > 0) {
    msg += NL + '❌ 손절 (' + lossList.length + '건)' + NL;
    for (const d of lossList) {
      const name = resolveName(d);
      const typeTag = d.isETF === false ? '[단일종목]' : d.isETF ? '[ETF]' : '';
      let line = carryTag(d) + typeTag + name + '(' + (d.code || '') + ') │ ' + shortDate(d.date);
      if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) line += ' │ 최고 ' + pct(d.maxReturn);
      if (Number.isFinite(d.stopPct)) line += ' │ 확정 ' + pct(d.stopPct);
      if (d.hitStopDay) line += ' │ 손절 ' + shortDate(d.hitStopDay);
      // [FIX-2026-09-26] 실제로 손절가를 찍은 게 아니라 보유기간 만료 시점 종가가
      // 진입가보다 낮아서 손절로 확정된 경우 표시.
      if (d.expiredForced) line += ' │ 만기청산';
      if (d.grade) line += ' │ ' + d.grade;
      if (d.score) line += ' │ ' + d.score + '점';
      if (d.patternType) line += ' │ ' + d.patternType;
      if (d.signals && d.signals.length) line += ' │ ' + d.signals.join(',');
      msg += line + NL;
    }
    // [QI-5] 손절 카운터 갱신 — 당일 손절 카운트를 store에 기록
    // (스캐너가 다음 실행 시 이 값을 읽어 당일 발송 억제 여부 결정)
    try {
      if (!store.intradayStopCount) store.intradayStopCount = {};
      for (const d of lossList) {
        const stopDay = d.hitStopDay || d.date;
        if (!store.intradayStopCount[stopDay]) store.intradayStopCount[stopDay] = 0;
        store.intradayStopCount[stopDay]++;
      }
    } catch(e) {}
  }

  // 매수 미진입 종목 + [QI-4] 미도달 이후 추적 (2026-05-09)
  const notEnteredList = details.filter((d) => d.result === 'not_entered');
  const missedOpportunities = []; // 미도달 후 상승 종목
  if (notEnteredList.length > 0) {
    // 미도달 종목의 이후 3거래일 가격 추적
    for (const d of notEnteredList) {
      try {
        const trackEnd = addTradingDays(d.date, 3);
        const trackEndCheck = trackEnd <= today ? trackEnd : prevTradingDay;
        const startStr = addTradingDays(d.date, 1).replace(/-/g, '');
        const endStr = trackEndCheck.replace(/-/g, '');
        if (startStr > endStr) continue;
        const trackData = await naver.fetchDaily(d.code, startStr, endStr);
        await sleep(300);
        if (!trackData || trackData.length === 0) continue;
        const postHigh = Math.max(...trackData.map(r => Number(r.highPrice) || 0));
        const postLow  = Math.min(...trackData.map(r => Number(r.lowPrice) || Infinity));
        const postReturn = d.entry > 0 ? (postHigh - d.entry) / d.entry : 0;
        // 미도달 후 3일 이내 +3% 이상 상승 → 기회 손실로 분류
        if (postReturn >= 0.03) {
          missedOpportunities.push({ ...d, postReturn, postHigh });
        }
      } catch(e) { /* 추적 실패 무시 */ }
    }

    msg += NL + '⚪ 매수 미도달 (' + notEnteredList.length + '건)' + NL;
    for (const d of notEnteredList) {
      const name = resolveName(d);
      msg += carryTag(d) + name + '(' + (d.code || '') + ') │ ' + shortDate(d.date) + NL;
    }
  }

  // [QI-4] 미도달 후 상승 섹션 — 진입가 재검토 시그널
  if (missedOpportunities.length > 0) {
    msg += NL + '⚡ 미도달 후 상승 (진입가 재검토 권장)' + NL;
    for (const d of missedOpportunities) {
      const name = resolveName(d);
      msg += name + '(' + (d.code || '') + ') │ ' + shortDate(d.date) + ' │ 이후최고 +' + (d.postReturn * 100).toFixed(1) + '%' + NL;
    }
    // 미도달+이후상승 건수를 store에 누적 (3주 연속 발생 시 경고)
    try {
      if (!store.missedEntryHistory) store.missedEntryHistory = [];
      store.missedEntryHistory.push({ week: weekDates[0], count: missedOpportunities.length });
      store.missedEntryHistory = store.missedEntryHistory.slice(-6); // 최근 6주만 보관
      const recentHighMiss = store.missedEntryHistory.slice(-3).filter(h => h.count >= 2).length;
      if (recentHighMiss >= 3) {
        msg += '⚠️ 3주 연속 미도달+상승 다수 — 진입가를 시가(오픈가) 기준으로 전환 검토 필요' + NL;
      }
    } catch(e) {}
  }

  // [SHADOW-2026-10-03] 발송 불변 — "복합 제외 / 일 2건 패턴캡 / 거래량 5x(참고)" 가상 코호트를
  // 실발송과 나란히 비교한다(docs/02-design/features/volume5x-pattern-cap-shadow.design.md).
  // 계산 실패는 이 섹션만 생략한다(기존 리포트·저장 로직에 영향 없음).
  try {
    const sh = computeShadowCohorts(details);
    if (!store.shadowStats) store.shadowStats = {};
    store.shadowStats[weekDates[0]] = sh;
    const shWeeks = Object.keys(store.shadowStats).sort();
    while (shWeeks.length > 12) delete store.shadowStats[shWeeks.shift()]; // 최근 12주만 보관
    const gate = shadowGate(store.shadowStats);
    const fmt = (label, s) => {
      const base = label + ' 확정 ' + s.closed;
      if (!s.closed) return base + ' │ 데이터 없음';
      const diff = s.winPct - sh.ALL.winPct;
      return base + ' │ 승 ' + s.winPct.toFixed(0) + '%' + (label === '실발송' ? ' │ 부분포함 ' + s.wpPct.toFixed(0) + '%' : '') +
        ' │ 평균 ' + (s.avgRet >= 0 ? '+' : '') + s.avgRet.toFixed(2) + '%' +
        (label !== '실발송' ? ' (승률 ' + (diff >= 0 ? '+' : '') + diff.toFixed(0) + '%p)' : '') +
        (s.closed < 5 ? ' ※표본 적음' : '');
    };
    msg += NL + '🔬 Shadow 비교 (발송 불변 · 이번 주 신규 확정 기준)' + NL +
      fmt('실발송', sh.ALL) + NL +
      fmt('복합제외', sh.NOCOMP) + NL +
      fmt('일2건캡', sh.CAP2) + NL +
      fmt('복합제외+캡', sh['NOCOMP+CAP2']) + NL +
      fmt('5x+(참고)', sh.RVOL5) + (sh.RVOL5.missing ? ' (rvol 미기록 ' + sh.RVOL5.missing + '건 제외)' : '') + NL +
      '게이트(배포 후 ' + shWeeks.length + '주): 복합제외 확정 ' + gate.NOCOMP.closedTotal + '/30 · 주별 방향 ' +
      gate.NOCOMP.weeksPositive + '/' + gate.NOCOMP.weeks + NL;
  } catch (e) {
    logger.warning('shadow cohorts failed', { error: e && e.message }, requestId);
  }

  // [SHADOW-2026-10-19] 시장상태 shadow(market-state-shadow) — 발송 불변. 위 Shadow 블록과 독립된 try/catch라 한쪽이 실패해도
  // 다른 쪽·기존 리포트에는 영향이 없다. 통계는 같은 주 객체(store.shadowStats[weekStart])에 병합 저장한다.
  try {
    const ss = computeShadowStateCohorts(details);
    if (!store.shadowStats) store.shadowStats = {};
    store.shadowStats[weekDates[0]] = Object.assign(store.shadowStats[weekDates[0]] || {}, ss);
    const sg = shadowStateGate(store.shadowStats);
    msg += NL + shadowFormatStateSection(ss, sg, shadowStateSummary(details.filter((d) => !d.carryOver))) + NL;
  } catch (e) {
    logger.warning('market state shadow failed', { error: e && e.message }, requestId);
  }

  msg += NL + '⚠️ 본 리포트는 참고용이며 투자 결과에 책임지지 않습니다.';

  // Telegram 4096자 초과 시 분리 전송
  const TELE_LIMIT = 4000;
  const chunks = [];
  if (msg.length <= TELE_LIMIT) {
    chunks.push(msg);
  } else {
    let remaining = msg;
    while (remaining.length > 0) {
      if (remaining.length <= TELE_LIMIT) { chunks.push(remaining); break; }
      let cut = remaining.lastIndexOf(NL, TELE_LIMIT);
      if (cut <= 0) cut = TELE_LIMIT;
      chunks.push(remaining.slice(0, cut));
      remaining = remaining.slice(cut).replace(/^\n/, '');
    }
  }

  for (let ci = 0; ci < chunks.length; ci++) {
    try {
      await telegram.send(chunks[ci]);
    } catch (e) {}
    if (ci < chunks.length - 1) await sleep(500);
  }

  // Log report completion
  logger.info('Weekly report sent', {
    reportDate: today,
    messageChunks: chunks.length,
    totalChars: msg.length,
    positions: recs.length,
    enteredCount: enteredCount
  }, requestId);

  return [{ json: { sent: true, count: recs.length, enteredCount, wins, losses, winRate } }];
};
return run();

// Daily_Position_Monitor.js
// n8n Function node — 16:00 KST(장 마감 후) + 12:30 KST(장중, 신규) 두 트리거가 같은 노드를 공유
// 목적: store.weeklyRecommendations의 활성 포지션에 트레일링 스탑 적용
//       스탑 레벨 상승 시 Telegram 알림 발송
// [FIX-2026-09-13] 장중(12:30) 실행 시 네이버 일봉 API는 당일 미완성 봉을 못 주므로(장 마감
// 15:30 전엔 "오늘"이 아직 어제로 조회됨), 원익/흥구석유/금강철강처럼 발송 당일 장중에
// 급등 후 반납하는 케이스를 16:00 EOD 체크만으론 하루 늦게 잡는다. 실행 시각이 15:00 KST
// 이전이면 당일 분봉으로 장중 스냅샷(고가/저가/현재가)을 만들어 같은 트레일링 로직에 넣는다.
// 트레일링은 절대 낮아지지 않으므로(calcTrailingStop의 Math.max) 하루 2번 실행해도 안전 —
// 12:30에 올라간 스탑을 16:00이 되돌리는 일은 없고, 오후장에 더 오르면 16:00이 이어서 올린다.
const { pct, to0 } = require('../lib/format');
const { createTelegram } = require('../lib/telegramClient');
const { createNaverClient } = require('../lib/naverClient');
const { isHoliday } = require('../lib/holidays');
const { getAtr, calcTrailingStop } = require('../lib/trailingStop');

const BOT  = SECRETS.BOT;
const CHAT = SECRETS.CHAT;

const NL = '\n';

const store = this.getWorkflowStaticData('global');
const http = async (o) => await this.helpers.httpRequest(Object.assign({ timeout: 30000 }, o));
const telegram = createTelegram(http, BOT, CHAT);
const naver = createNaverClient(http);

// ===== KST 기준 오늘 날짜 =====
const now = new Date();
const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
const today = `${kst.getUTCFullYear()}-${String(kst.getUTCMonth() + 1).padStart(2, '0')}-${String(kst.getUTCDate()).padStart(2, '0')}`;

if (isHoliday(today)) {
  return [{ json: { skipped: true, reason: 'Holiday', today } }];
}

// ===== 네이버 일봉 데이터 조회 (장 마감 후 — 오늘 봉이 확정된 상태) =====
async function fetchDailyClose(code) {
  const kstNow = new Date(Date.now() + 9 * 3600000);
  const ed = kstNow.toISOString().slice(0, 10).replace(/-/g, '') + '235959';
  const sdDate = new Date(kstNow.getTime() - 10 * 24 * 3600000);
  const sd = sdDate.toISOString().slice(0, 10).replace(/-/g, '') + '000000';
  const items = await naver.fetchDaily(code, sd, ed);
  if (!items) return null;
  // 오름차순 정렬 기준 마지막 항목이 최신, 그 앞이 전일
  const latest = items[items.length - 1];
  const prev = items.length >= 2 ? items[items.length - 2] : null;
  return {
    close: Number(latest.closePrice || latest.close),
    high:  Number(latest.highPrice  || latest.high),
    low:   Number(latest.lowPrice   || latest.low),
    prevClose: prev ? Number(prev.closePrice || prev.close) : null,
    latestDate: latest.localDate,
  };
}

// ===== [12:30 장중 스냅샷] 오늘 분봉으로 고가/저가/현재가 근사 =====
// 일봉 API는 장중엔 오늘 봉을 안 주므로(마감 전 미확정), 오늘 분봉을 모아 흉내낸다.
// high/low는 "지금까지의" 장중 고저 — 오후장에 더 갱신되면 16:00 fetchDailyClose가 마저 잡는다.
async function fetchIntradaySnapshot(code, todayStr) {
  const minuteData = await naver.fetchMinute(code, todayStr);
  if (!minuteData || !minuteData.length) return null;

  let high = -Infinity, low = Infinity, close = null;
  for (const bar of minuteData) {
    const hi = Number(bar.highPrice || bar.high);
    const lo = Number(bar.lowPrice || bar.low);
    const cl = Number(bar.closePrice || bar.close);
    if (Number.isFinite(hi) && hi > high) high = hi;
    if (Number.isFinite(lo) && lo < low) low = lo;
    if (Number.isFinite(cl)) close = cl; // 분봉은 시간순 — 마지막 유효값이 현재가
  }
  if (!Number.isFinite(high) || !Number.isFinite(low) || close == null) return null;

  // 전일종가는 분봉만으론 알 수 없어 일봉(어제까지)으로 별도 조회
  const kstNow = new Date(Date.now() + 9 * 3600000);
  const sdDate = new Date(kstNow.getTime() - 10 * 24 * 3600000);
  const sd = sdDate.toISOString().slice(0, 10).replace(/-/g, '') + '000000';
  const ydEnd = new Date(kstNow.getTime() - 24 * 3600000).toISOString().slice(0, 10).replace(/-/g, '') + '235959';
  const dailyItems = await naver.fetchDaily(code, sd, ydEnd);
  const prevItem = dailyItems && dailyItems.length ? dailyItems[dailyItems.length - 1] : null;

  return {
    close, high, low,
    prevClose: prevItem ? Number(prevItem.closePrice || prevItem.close) : null,
    latestDate: todayStr.replace(/-/g, ''),
  };
}

// ===== 급락 감지 (트레일링 스탑 도달 여부와 무관하게, 전일 종가 대비 급락 시 즉시 경고) =====
const SHOCK_DROP_THRESH = -0.05; // 당일 종가가 전일 종가 대비 -5% 이상 하락 시 트리거

function computeDayChangePct(close, prevClose) {
  if (!prevClose || prevClose <= 0) return null;
  return (close - prevClose) / prevClose;
}

// ===== 활성 포지션 수집 =====
const weeklyRecs = store.weeklyRecommendations || {};
const allDates = Object.keys(weeklyRecs).sort();

const activePositions = [];
for (const dateKey of allDates) {
  for (const rec of (weeklyRecs[dateKey] || [])) {
    if (rec.type !== 'swing') continue;
    // 만료 여부 확인 (보유 기간 초과 시 스킵)
    const holdDays = rec.holdingDays || 3;
    const entryDate = new Date(rec.date || dateKey);
    const expiry = new Date(entryDate.getTime() + holdDays * 1.4 * 24 * 60 * 60 * 1000); // 거래일 근사
    if (expiry < now) continue;
    activePositions.push(rec);
  }
}

if (!activePositions.length) {
  return [{ json: { message: '활성 포지션 없음', today, checked: 0 } }];
}

// ===== 실행 시각으로 장중/장마감 판단 =====
// 트리거가 둘(12:30/16:00)이라 "어느 트리거가 쐈는지"를 노드에서 구분하는 대신, 더 단순하게
// 실행 시각(15:00 KST 기준, KRX 정규장 마감 15:30보다 앞당겨 여유를 둠)으로 분기한다.
const kstHour = kst.getUTCHours(); // kst = now+9h 로 이미 KST로 shift된 Date
const isIntraday = kstHour < 15;

// ===== 각 포지션 처리 =====
const alerts = [];
let updated = 0;
let shockCount = 0;

for (const rec of activePositions) {
  const candle = isIntraday
    ? await fetchIntradaySnapshot(rec.code, today)
    : await fetchDailyClose(rec.code);
  if (!candle) continue;

  const { close, high, low, prevClose, latestDate } = candle;
  const entry = rec.entry;
  if (!entry || entry <= 0) continue;

  const currentGain = (close - entry) / entry;
  // [A안 2026-08-22] 트레일링 티어 판정은 종가 대신 장중 고가 기준으로 변경.
  // 종가 기준이면 장중 1차목표(고가 기준) 터치 후 종가가 밀릴 때 본전 스탑이
  // 전혀 발동하지 않아 초기 손절가(최대 -8%)가 그대로 남는 문제가 있었음.
  const tierGain = (high - entry) / entry;
  const atr = getAtr(rec.atrAbs, high, low, close);
  const oldStop = rec.stop || 0;

  const newStop = calcTrailingStop(entry, high, atr, tierGain, oldStop);

  // 스탑 레벨 의미있게 상승했을 때만 알림 (최소 0.3% 이상 상승)
  const stopRaised = newStop > oldStop * 1.003;

  if (stopRaised) {
    // store 업데이트
    rec.stop = newStop;
    updated++;

    const gainPct = pct(currentGain);
    const oldStopPct = entry > 0 ? pct((oldStop - entry) / entry) : 'N/A';
    const newStopPct = entry > 0 ? pct((newStop - entry) / entry) : 'N/A';

    const tag = isIntraday ? '[장중 12:30] ' : '';
    alerts.push(
      tag + '[🛡️ 스탑 상향] ' + (rec.name || rec.code) + '(' + rec.code + ')' + NL +
      '현재가: ' + to0(close) + '원 (' + gainPct + ')' + NL +
      '손절가: ' + to0(oldStop) + '원(' + oldStopPct + ') → ' + to0(newStop) + '원(' + newStopPct + ')' + NL +
      'ATR: ' + to0(atr) + '원'
    );
  }

  // 급락 경고: 트레일링 스탑 도달 여부와 무관하게, 전일 종가 대비 급락 시 즉시 알림
  // (오늘 봉이 아직 안 올라온 경우 — 휴장일 지연 등 — 오래된 등락을 오늘 급락으로 오판하지 않도록 가드)
  const latestDateFormatted = latestDate ? `${latestDate.slice(0,4)}-${latestDate.slice(4,6)}-${latestDate.slice(6,8)}` : null;
  const dayChangePct = computeDayChangePct(close, prevClose);
  if (latestDateFormatted === today && dayChangePct !== null && dayChangePct <= SHOCK_DROP_THRESH) {
    shockCount++;
    const tag = isIntraday ? '[장중 12:30] ' : '';
    alerts.push(
      tag + '[⚠️ 급락 경고] ' + (rec.name || rec.code) + '(' + rec.code + ')' + NL +
      '전일종가 대비: ' + pct(dayChangePct) + NL +
      '현재가: ' + to0(close) + '원 │ 진입가 대비: ' + pct(currentGain) + NL +
      '시장 변동성 확대 — 포지션 재검토 권장'
    );
  }
}

// ===== Telegram 알림 발송 =====
for (const alertMsg of alerts) {
  try {
    await telegram.send(alertMsg);
    await new Promise((r) => setTimeout(r, 500));
  } catch {
    // 알림 실패는 무시
  }
}

// store 반영 (n8n Globals 노드가 있다면 별도 Set 노드로 저장 필요)
// store.weeklyRecommendations는 이미 참조로 수정됨

return [{
  json: {
    today,
    checkType: isIntraday ? 'intraday-1230' : 'eod-1600',
    activePositions: activePositions.length,
    updated,
    shockAlerts: shockCount,
    alertsSent: alerts.length,
    message: (updated > 0 || shockCount > 0)
      ? `스탑 상향 ${updated}건, 급락 경고 ${shockCount}건 알림 발송`
      : '스탑 상향/급락 없음 (모든 포지션 정상)',
  }
}];

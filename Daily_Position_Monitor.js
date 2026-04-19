// Daily_Position_Monitor.js
// n8n Function node — 장 마감 후 실행 (16:00 KST)
// 목적: store.weeklyRecommendations의 활성 포지션에 트레일링 스탑 적용
//       스탑 레벨 상승 시 Telegram 알림 발송

const BOT  = $env.TELEGRAM_BOT_TOKEN;
const CHAT = $env.TELEGRAM_CHAT_ID;

const NL = '\n';

// ===== 트레일링 스탑 배수 상수 =====
const TRAIL_BE_GAIN   = 0.03;   // 수익률 3% 이상: 손절→진입가(본전)
const TRAIL_5_GAIN    = 0.05;   // 수익률 5% 이상: 손절→고점−ATR×1.5
const TRAIL_10_GAIN   = 0.10;   // 수익률 10% 이상: 손절→고점−ATR×1.0
const TRAIL_15_GAIN   = 0.15;   // 수익률 15% 이상: 손절→고점−ATR×0.7
const TRAIL_MULT_5    = 1.5;
const TRAIL_MULT_10   = 1.0;
const TRAIL_MULT_15   = 0.7;

const store = $node["Globals"].json.store || {};
const http = async (o) => await this.helpers.httpRequest(Object.assign({ timeout: 30000 }, o));

const to0 = (v) => Math.round(v).toLocaleString('ko-KR');
const pct = (v) => (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%';

// ===== Logger initialization (Zero Script QA) =====
const JsonLogger = require('./lib/logger');
const logger = new JsonLogger('position_monitor');
const requestId = logger.generateRequestId('MONITOR');
logger.info('Position monitor started', { phase: 'initialization' }, requestId);

// ===== KST 기준 오늘 날짜 =====
const now = new Date();
const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
const today = `${kst.getUTCFullYear()}-${String(kst.getUTCMonth() + 1).padStart(2, '0')}-${String(kst.getUTCDate()).padStart(2, '0')}`;

// ===== 네이버 일봉 데이터 조회 =====
async function fetchDailyClose(code) {
  try {
    // swing_scanner_code.js와 동일한 API 사용 (api.stock.naver.com/chart/domestic)
    const kstNow = new Date(Date.now() + 9 * 3600000);
    const ed = kstNow.toISOString().slice(0, 10).replace(/-/g, '') + '235959';
    const sdDate = new Date(kstNow.getTime() - 10 * 24 * 3600000);
    const sd = sdDate.toISOString().slice(0, 10).replace(/-/g, '') + '000000';
    const url = `https://api.stock.naver.com/chart/domestic/item/${code}/day?startDateTime=${sd}&endDateTime=${ed}`;
    const res = await http({
      method: 'GET', url, json: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://finance.naver.com/',
        'Accept': 'application/json', 'Accept-Language': 'ko-KR,ko;q=0.9',
      },
      encoding: 'utf8',
    });
    // 응답 정규화 (swing_scanner_code.js _normalizeNaverResp 패턴)
    let items = Array.isArray(res) ? res
      : (res && (res.body || res.data || res.result || res.chartPriceList || []));
    if (!Array.isArray(items) || !items.length) return null;
    // 오름차순 정렬 기준 마지막 항목이 최신
    const latest = items[items.length - 1];
    return {
      close: Number(latest.closePrice || latest.close),
      high:  Number(latest.highPrice  || latest.high),
      low:   Number(latest.lowPrice   || latest.low),
    };
  } catch {
    return null;
  }
}

// ===== ATR 계산 (보관된 atrAbs 사용, 없으면 근사치) =====
function getAtr(rec, currentHigh, currentLow, currentClose) {
  if (rec.atrAbs && Number.isFinite(rec.atrAbs) && rec.atrAbs > 0) return rec.atrAbs;
  // atrAbs 없을 때: 현재 고-저 범위로 근사
  return Math.max(currentHigh - currentLow, currentClose * 0.02);
}

// ===== 트레일링 스탑 계산 =====
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
    activePositions.push({ ...rec, dateKey });
  }
}

if (!activePositions.length) {
  logger.info('No active positions found', {
    today,
    message: '활성 포지션 없음'
  }, requestId);
  return [{ json: { message: '활성 포지션 없음', today, checked: 0 } }];
}

logger.info(`Position monitoring started`, {
  today,
  activePositions: activePositions.length,
  positions: activePositions.map(p => `${p.code}(${p.grade})`).join(',')
}, requestId);

// ===== 각 포지션 처리 =====
const alerts = [];
let updated = 0;

for (const rec of activePositions) {
  const candle = await fetchDailyClose(rec.code);
  if (!candle) continue;

  const { close, high, low } = candle;
  const entry = rec.entry;
  if (!entry || entry <= 0) continue;

  const currentGain = (close - entry) / entry;
  const atr = getAtr(rec, high, low, close);
  const oldStop = rec.stop || 0;

  const newStop = calcTrailingStop(entry, high, atr, currentGain, oldStop);

  // 스탑 레벨 의미있게 상승했을 때만 알림 (최소 0.3% 이상 상승)
  const stopRaised = newStop > oldStop * 1.003;

  if (stopRaised) {
    // store 업데이트
    rec.stop = newStop;
    updated++;

    const gainPct = pct(currentGain);
    const oldStopPct = entry > 0 ? pct((oldStop - entry) / entry) : 'N/A';
    const newStopPct = entry > 0 ? pct((newStop - entry) / entry) : 'N/A';

    // Log stop update for QA tracing
    logger.info(`Stop level raised: ${rec.code}`, {
      code: rec.code,
      ticker: rec.ticker,
      grade: rec.grade,
      currentPrice: close,
      gain: gainPct,
      oldStop: oldStop.toFixed(0),
      newStop: newStop.toFixed(0),
      atr: atr.toFixed(0)
    }, requestId);

    alerts.push(
      '[🛡️ 스탑 상향] ' + (rec.name || rec.code) + '(' + rec.code + ')' + NL +
      '현재가: ' + to0(close) + '원 (' + gainPct + ')' + NL +
      '손절가: ' + to0(oldStop) + '원(' + oldStopPct + ') → ' + to0(newStop) + '원(' + newStopPct + ')' + NL +
      'ATR: ' + to0(atr) + '원'
    );
  }
}

// ===== Telegram 알림 발송 =====
for (const alertMsg of alerts) {
  try {
    await http({
      method: 'POST',
      url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
      json: true,
      body: { chat_id: CHAT, text: alertMsg },
    });
    await new Promise((r) => setTimeout(r, 500));
  } catch {
    // 알림 실패는 무시
  }
}

// store 반영 (n8n Globals 노드가 있다면 별도 Set 노드로 저장 필요)
// store.weeklyRecommendations는 이미 참조로 수정됨

// Log monitoring completion
logger.info('Position monitoring completed', {
  today,
  activePositions: activePositions.length,
  updated: updated,
  alertsSent: alerts.length
}, requestId);

return [{
  json: {
    today,
    activePositions: activePositions.length,
    updated,
    alertsSent: alerts.length,
    message: updated > 0
      ? `스탑 상향 ${updated}건 알림 발송`
      : '스탑 상향 없음 (모든 포지션 정상)',
  }
}];

const run = async function () {
  const BOT = '8366696724:AAHROcjGoQEn9BziD-sYdAu3ZuaolwtkgLE';
  const CHAT = '523002062';
  const MIN_PRICE = 1000;
  const MIN_INTRADAY_TURNOVER = 3000000000; // 30억 KRW (rate-limiting 방지)
  const MIN_SCORE = 80;         // 매수 등급 점수 기준 (발송은 차단, 스코어링 기준으로만 유지)
  const RELAX_SCORE = 60;       // 관심 등급 점수 기준 (50→60 상향, 저품질 차단)
  const MIN_DAILY_PICKS = 0;    // filler 채움 비활성화 — 0건이어도 발송 안 함 (품질 우선)
  // (PMAT_STRICT, PMAT_RELAX 제거 — HITALK 모델 제거로 불필요)

  const ACCOUNT_KRW = 10000000;
  const RISK_PCT_PER_TRADE = 0.005;
  const ATR_WINDOW = 14;
  const ATR_STOP_MULT = 1.9;
  const ATR_TARGET_MULT = 2.8;        // 강매 등급 전용 목표 배수 (5거래일 보유)
  const ATR_TARGET_MULT_NORMAL = 2.0; // 급등·기타 등급 목표 배수 (2026-04-18 개선: 목표 도달률 향상)
  const CAP_STOP_PCT = 0.10;
  const CAP_TARGET_PCT = 0.25;
  const MAX_INTRADAY_SENDS = 4;
  const HOLIDAYS = ['2025-01-01','2025-01-28','2025-01-29','2025-01-30','2025-03-01','2025-03-03','2025-05-05','2025-05-06','2025-06-06','2025-08-15','2025-10-03','2025-10-06','2025-10-07','2025-10-08','2025-10-09','2025-12-25','2026-01-01','2026-02-16','2026-02-17','2026-02-18','2026-03-01','2026-03-02','2026-05-05','2026-05-24','2026-05-25','2026-06-03','2026-06-06','2026-07-17','2026-08-15','2026-08-17','2026-09-24','2026-09-25','2026-09-26','2026-10-03','2026-10-05','2026-10-09','2026-12-25'];
  const DUPLICATE_WINDOW_MINUTES = 4320; // 3일 (스윙 보유기간 반영, 동일 종목 재추천 방지)
  const STOP_NEW_ALERTS_HOUR = 15;
  const STOP_NEW_ALERTS_MINUTE = 20;
  const MIN_AVG5_VOLUME = 30000; // 최소 5일 평균 거래량 (저유동성 종목 제외)

  // ===== 단기 고수익 포착 상수 (2026-04-11 개선) =====
  const MIN_TARGET_PCT = 0.05;   // 최소 목표 수익률 3%→5% (저수익 종목 차단)
  const MIN_RR_RATIO = 1.5;      // 최소 Risk:Reward 비율
  const RSI_MIN_ENTRY = 45;      // RSI 하한 (모멘텀 부족 차단)
  const RSI_MAX_ENTRY = 80;      // RSI 상한 (일반 종목)
  const RSI_SURGE_MAX = 90;      // RSI 상한 완화 (급등 후보 전용)
  const ADX_TREND_MIN = 20;      // ADX 최소 추세 강도 (횡보장 차단)
  const RVOL_GRADE_C = 1.5;      // C-grade: 1.5x
  const RVOL_GRADE_B = 2.0;      // B-grade: 2.0x
  const RVOL_GRADE_A = 3.0;      // A-grade: 3.0x (최고품질)
  // ===== /단기 고수익 포착 상수 =====
  // ===== 실증 데이터 기반 개선 상수 (2026-03-29, 3504건 분석) =====
  const SCORE_STRONG = 120;       // 강매 등급 점수 기준
  const HOLD_STRONG = 5;          // 강매 등급 보유 기간 10→5거래일 (단기화)
  const HOLD_NORMAL = 6;          // 매수 등급 보유 기간 (발송 차단이므로 실질 미사용)
  const HOLD_WEAK = 2;            // 완화 통과 종목 보유 기간 (거래일)
  const HOLD_SHORTTRADE = 3;      // 매도차익 등급 보유 기간 (거래일) (2026-04-18 개선: 2→3, 목표 도달 시간 확보)
  const TARGET1_PCT = 0.07;       // 1차 목표 비율 (데이터 5~10% 구간 중앙값 7%)
  const ATR_TARGET_SHORT = 1.5;   // 매도차익 등급 목표 배수 (ATR 1.5x)
  const DOW_BONUS_THU = 3;        // 목요일 rankScore 보너스
  const DOW_BONUS_WED = 2;        // 수요일 rankScore 보너스
  const DOW_PENALTY_FRI = 5;      // 금요일 rankScore 패널티
  // ===== /실증 데이터 기반 개선 상수 =====
  // ===== 급등 모멘텀 포착 상수 =====
  const SURGE_DAILY_CHANGE = 0.05;  // 급등 최소 당일 변화율 (+5%)
  const SURGE_RVOL_MIN    = 5.0;    // 급등 최소 RVOL (5x)
  const SURGE_SCORE_BONUS = 50;     // 급등 조건 충족 시 추가 점수
  const CONSEC_UP_BONUS   = 15;     // 2일+ 연속 양봉 거래량 확대 보너스
  const NEW_HIGH52W_BONUS = 40;     // 52주 신고가 돌파 보너스
  const HOLD_SURGE        = 3;      // 급등 등급 보유 기간 (거래일) (2026-04-18 개선: 2→3, 목표 도달 시간 확보)
  const SCORE_SURGE       = 100;    // 급등 등급 점수 기준
  // ===== HIGH IMPACT 정밀 지표 상수 =====
  const VOL_TREND_5_60_B  = 2.0;    // 5/60일 거래량 비율 B등급
  const VOL_TREND_5_60_A  = 3.0;    // 5/60일 거래량 비율 A등급
  const PRICE_FROM_LOW_BONUS = 20;  // 52주 저점 반등 보너스
  const INTRADAY_STR_MIN  = 0.6;    // 당일 강도 하한 (범위 상단 60%+)
  const INTRADAY_STR_BONUS = 10;    // 당일 강도 보너스
  const SECTOR_MOMENTUM_BONUS = 10; // 동일 업종 2개+ 동시 강세 보너스
  // ===== /급등·HIGH IMPACT 상수 =====

  const http = async (o) => await this.helpers.httpRequest(Object.assign({ timeout: 45000 }, o));

  const sma = (arr, w) => {
    const out = new Array(arr.length).fill(NaN);
    if (arr.length < w) return out;
    let sum = 0;
    for (let i = 0; i < arr.length; i++) {
      const v = Number(arr[i]);
      sum += (Number.isFinite(v) ? v : 0);
      if (i >= w) {
        const old = Number(arr[i - w]);
        sum -= (Number.isFinite(old) ? old : 0);
      }
      if (i >= w - 1) out[i] = sum / w;
    }
    return out;
  };

  const ema = (arr, w) => {
    const out = new Array(arr.length).fill(NaN);
    const k = 2 / (w + 1);
    let prev = NaN;
    for (let i = 0; i < arr.length; i++) {
      const v = Number(arr[i]);
      if (!Number.isFinite(v)) continue;
      if (!Number.isFinite(prev)) { out[i] = v; prev = v; continue; }
      out[i] = v * k + prev * (1 - k);
      prev = out[i];
    }
    return out;
  };

  const calcRSI14 = (closeD, idx) => {
    const period = 14;
    const start = Math.max(0, idx - period * 3);
    const slice = closeD.slice(start, idx + 1);
    if (slice.length < period + 1) return NaN;
    let gains = 0; let losses = 0;
    for (let i = 1; i <= period; i++) {
      const d = Number(slice[i]) - Number(slice[i - 1]);
      if (d > 0) gains += d; else losses -= d;
    }
    let avgGain = gains / period;
    let avgLoss = losses / period;
    for (let i = period + 1; i < slice.length; i++) {
      const d = Number(slice[i]) - Number(slice[i - 1]);
      avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period;
      avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period;
    }
    if (avgLoss === 0) return 100;
    return 100 - 100 / (1 + avgGain / avgLoss);
  };

  const calcADX = (highD, lowD, closeD, idx, period = 14) => {
    const need = period * 3 + 2;
    const start = Math.max(0, idx - need);
    const hi = highD.slice(start, idx + 1).map(Number);
    const lo = lowD.slice(start, idx + 1).map(Number);
    const cl = closeD.slice(start, idx + 1).map(Number);
    const n = hi.length;
    if (n < period + 2) return { adx: NaN, plusDI: NaN, minusDI: NaN };

    const plusDM = []; const minusDM = []; const tr = [];
    for (let i = 1; i < n; i++) {
      const upMove = hi[i] - hi[i - 1];
      const downMove = lo[i - 1] - lo[i];
      plusDM.push(upMove > downMove && upMove > 0 ? upMove : 0);
      minusDM.push(downMove > upMove && downMove > 0 ? downMove : 0);
      const trVal = Math.max(hi[i] - lo[i], Math.abs(hi[i] - cl[i - 1]), Math.abs(lo[i] - cl[i - 1]));
      tr.push(trVal);
    }

    const smooth = (arr) => {
      let s = arr.slice(0, period).reduce((a, b) => a + b, 0);
      const out = [s];
      for (let i = period; i < arr.length; i++) {
        s = s - s / period + arr[i];
        out.push(s);
      }
      return out;
    };

    const sTR = smooth(tr); const sPDM = smooth(plusDM); const sMDM = smooth(minusDM);
    const dx = [];
    for (let i = 0; i < sTR.length; i++) {
      if (sTR[i] === 0) { dx.push(0); continue; }
      const pdi = (sPDM[i] / sTR[i]) * 100;
      const mdi = (sMDM[i] / sTR[i]) * 100;
      const sum = pdi + mdi;
      dx.push(sum === 0 ? 0 : (Math.abs(pdi - mdi) / sum) * 100);
    }
    if (dx.length < period) return { adx: NaN, plusDI: NaN, minusDI: NaN };
    let adxVal = dx.slice(0, period).reduce((a, b) => a + b, 0) / period;
    for (let i = period; i < dx.length; i++) {
      adxVal = (adxVal * (period - 1) + dx[i]) / period;
    }
    const lastI = sTR.length - 1;
    const plusDI = sTR[lastI] > 0 ? (sPDM[lastI] / sTR[lastI]) * 100 : 0;
    const minusDI = sTR[lastI] > 0 ? (sMDM[lastI] / sTR[lastI]) * 100 : 0;
    return { adx: adxVal, plusDI, minusDI };
  };

  const calcAtrAbs = (highD, lowD, idx, w) => {
    const i = Math.max(0, Math.min(idx, highD.length - 1));
    const start = Math.max(0, i - w);
    const seg = [];
    for (let k = start; k < i; k++) {
      const hi = Number(highD[k]);
      const lo = Number(lowD[k]);
      if (Number.isFinite(hi) && Number.isFinite(lo)) seg.push(Math.max(0, hi - lo));
    }
    if (!seg.length) return NaN;
    return seg.reduce((a, b) => a + b, 0) / seg.length;
  };

  // ===== Stock Skills: MACD / Bollinger Bands / OBV =====
  // [Stock.md Step 3] MACD(12/26/9) — 모멘텀 신호 (골든크로스, 히스토그램 방향)
  const calcMACD = (closeD, idx) => {
    const nan = { macd: NaN, signal: NaN, hist: NaN, histPrev: NaN, goldenCross: false };
    const start = Math.max(0, idx - 26 * 4);
    const slice = closeD.slice(start, idx + 1);
    if (slice.length < 35) return nan; // slow(26) + signal(9)
    const fastEmaArr = ema(slice, 12);
    const slowEmaArr = ema(slice, 26);
    const macdLine = fastEmaArr.map((v, i) =>
      (Number.isFinite(v) && Number.isFinite(slowEmaArr[i])) ? v - slowEmaArr[i] : NaN);
    const macdValid = macdLine.filter(Number.isFinite);
    if (macdValid.length < 9) return nan;
    const signalArr = ema(macdValid, 9);
    const n = Math.min(macdValid.length, signalArr.length);
    if (n < 2) return nan;
    const lastMacd = macdValid[n - 1];
    const lastSignal = signalArr[n - 1];
    const prevMacd = macdValid[n - 2];
    const prevSignal = signalArr[n - 2];
    return {
      macd: lastMacd, signal: lastSignal,
      hist: lastMacd - lastSignal,
      histPrev: prevMacd - prevSignal,
      goldenCross: prevMacd < prevSignal && lastMacd >= lastSignal,
    };
  };

  // [Stock.md Step 4] Bollinger Bands(20, 2.0) — 변동성 스퀴즈 돌파 감지
  const calcBB = (closeD, idx, period = 20, nbdev = 2.0) => {
    const nan = { upper: NaN, middle: NaN, lower: NaN, width: NaN, zScore: NaN };
    const end = idx + 1;
    const start = Math.max(0, end - period);
    const slice = closeD.slice(start, end).map(Number).filter(Number.isFinite);
    if (slice.length < period) return nan;
    const mean = slice.reduce((a, b) => a + b, 0) / slice.length;
    const std = Math.sqrt(slice.reduce((a, b) => a + (b - mean) ** 2, 0) / slice.length);
    if (std === 0) return nan;
    const upper = mean + nbdev * std;
    const lower = mean - nbdev * std;
    const curr = Number(closeD[idx]);
    const width = mean > 0 ? (upper - lower) / mean : NaN;
    const zScore = (curr - mean) / std;
    return { upper, middle: mean, lower, width, zScore };
  };

  // [Stock.md Step 4] OBV — 수급 확인 (가격-거래량 다이버전스 탐지)
  // QA FIX: SMA5>SMA20은 장기 상승주에서 항상 true → OBV 기울기(최근 10일 변화율)로 교체
  const calcOBV = (closeD, volD, idx) => {
    const n = Math.min(closeD.length, volD.length, idx + 1);
    if (n < 20) return { obvTrend: 0 };
    let obv = 0;
    const obvArr = [];
    for (let i = 0; i < n; i++) {
      if (i > 0) {
        const d = Number(closeD[i]) - Number(closeD[i - 1]);
        if (d > 0) obv += Number(volD[i]) || 0;
        else if (d < 0) obv -= Number(volD[i]) || 0;
      }
      obvArr.push(obv);
    }
    // 기울기 방식: 최근 5일 OBV 평균 vs 5~10일 전 OBV 평균 비교 (단기 수급 방향)
    const recentOBV = obvArr.slice(-5).reduce((a, b) => a + b, 0) / 5;
    const prevOBV   = obvArr.slice(-10, -5).reduce((a, b) => a + b, 0) / 5;
    if (prevOBV === 0) return { obvTrend: 0 };
    const obvSlope = (recentOBV - prevOBV) / Math.abs(prevOBV);
    // 0.5% 이상 상승 → 수급 확인, -0.5% 이하 하락 → 수급 이탈
    if (obvSlope > 0.005) return { obvTrend: 1 };
    if (obvSlope < -0.005) return { obvTrend: -1 };
    return { obvTrend: 0 };
  };
  // ===== /Stock Skills =====

  const calcQty = (accountKrw, riskPct, entry, stop) => {
    const acct = Number(accountKrw) || 0;
    const rp = Number(riskPct) || 0;
    const e = Number(entry) || 0;
    const s = Number(stop) || 0;
    const perShareRisk = e - s;
    if (!(acct > 0 && rp > 0 && e > 0 && perShareRisk > 0)) return 0;
    const riskAmt = acct * rp;
    const q = Math.floor(riskAmt / perShareRisk);
    return Math.max(0, Math.min(q, 100000));
  };

  const detectCupAndHandle = (close, high, low, idx) => {
    const MIN_CUP_DAYS = 30; const MAX_CUP_DAYS = 80;
    const MIN_HANDLE_DAYS = 5; const MAX_HANDLE_DAYS = 20;
    const MAX_CUP_DEPTH = 0.35;
    const MIN_HANDLE_RETRACEMENT = 0.05; const MAX_HANDLE_RETRACEMENT = 0.20;
    const HANDLE_FLATNESS = 0.10;

    if (idx < MIN_CUP_DAYS + MIN_HANDLE_DAYS) return { detected: false };

    const endCup = idx - MIN_HANDLE_DAYS;
    const startCup = Math.max(0, endCup - MAX_CUP_DAYS);
    const cupSegment = close.slice(startCup, endCup);
    if (cupSegment.length < MIN_CUP_DAYS) return { detected: false };

    const leftRim = Math.max(...cupSegment.slice(0, 5));
    const bottom = Math.min(...cupSegment);
    const rightRim = Math.max(...cupSegment.slice(-5));

    const cupDepth = (leftRim - bottom) / leftRim;
    if (cupDepth > MAX_CUP_DEPTH) return { detected: false };

    const rimsAligned = Math.abs(leftRim - rightRim) / leftRim < 0.05;
    if (!rimsAligned) return { detected: false };

    const midIdx = Math.floor(cupSegment.length / 2);
    const leftLow = Math.min(...cupSegment.slice(0, midIdx));
    const rightLow = Math.min(...cupSegment.slice(midIdx));
    const isUShape = Math.abs(leftLow - rightLow) / Math.max(leftLow, rightLow) < 0.10;
    if (!isUShape) return { detected: false };

    const handleSegment = close.slice(endCup, idx);
    if (handleSegment.length < MIN_HANDLE_DAYS || handleSegment.length > MAX_HANDLE_DAYS) return { detected: false };

    const handleHigh = Math.max(...handleSegment);
    const handleLow = Math.min(...handleSegment);
    const handleRetracement = (handleHigh - handleLow) / handleHigh;
    if (handleRetracement < MIN_HANDLE_RETRACEMENT || handleRetracement > MAX_HANDLE_RETRACEMENT) return { detected: false };

    const handleRange = (handleHigh - handleLow) / handleHigh;
    if (handleRange > HANDLE_FLATNESS) return { detected: false };

    return { detected: true, leftRim, rightRim, bottom, handleHigh, handleLow, cupDepth, handleRetracement };
  };

  // KOSPI(%5EKS11=KOSPI), KOSDAQ(%5EKQ11=KOSDAQ) 지수 종가 배열 반환
  // fetchDailyFchart는 아래에 선언되지만 실제 호출 시점(Line ~1233)에는 이미 선언됨
  const fetchDailyClose = async (encodedTicker) => {
    try {
      const symbolMap = { '%5EKS11': 'KOSPI', '%5EKQ11': 'KOSDAQ' };
      const symbol = symbolMap[encodedTicker] || encodedTicker;
      const resp = await fetchDailyFchart(symbol, 120);
      if (!resp || !resp.length) return [];
      return resp.map(d => d.closePrice);
    } catch(e) { return []; }
  };

  const getMarketRegime = async (store, today) => {
    if (!store.regimeCache) store.regimeCache = {};
    if (store.regimeCache.date === today && store.regimeCache.riskOn !== undefined) return store.regimeCache;
    let riskOn = true;
    let ks = null;
    let kq = null;
    try {
      const [ksClose, kqClose] = await Promise.all([fetchDailyClose('%5EKS11'), fetchDailyClose('%5EKQ11')]);
      const ks20 = sma(ksClose, 20); const ks60 = sma(ksClose, 60);
      const kq20 = sma(kqClose, 20); const kq60 = sma(kqClose, 60);
      const iKs = ksClose.length - 1; const iKq = kqClose.length - 1;
      ks = (Number.isFinite(ks20[iKs]) && Number.isFinite(ks60[iKs])) ? (ks20[iKs] > ks60[iKs]) : null;
      kq = (Number.isFinite(kq20[iKq]) && Number.isFinite(kq60[iKq])) ? (kq20[iKq] > kq60[iKq]) : null;
      if (ks === false || kq === false) riskOn = false;
    } catch (e) {
      riskOn = true;
    }
    store.regimeCache = { date: today, riskOn, ksUp: ks, kqUp: kq, at: new Date().toISOString() };
    return store.regimeCache;
  };

  const input = (items && items[0] && items[0].json) || {};
  const forceTest = !!input.forceTest;
  const store = this.getWorkflowStaticData('global');  // forceTest 이전 선언 (holidayWarnSent 참조 보장)

  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const timeStrNow = String(kst.getUTCHours()).padStart(2, '0') + ':' + String(kst.getUTCMinutes()).padStart(2, '0');

  const NL = String.fromCharCode(10);
  const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  // 종목명 깨짐 감지: 한글·ASCII·한자 이외의 문자(깨진 EUC-KR 바이트)가 포함된 경우 true
  const isGarbled = (s) => s && !/^[\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F\u3200-\u321F\uFF01-\uFF9F\u4E00-\u9FFF\u0020-\u007E]+$/.test(s);

  if (forceTest) {
    const msg = '[스윙 스캔 테스트] 시스템 정상 작동' + NL + '시간: ' + kst.toISOString().slice(0, 16).replace('T', ' ') + ' KST';
    try {
      const res = await http({
        method: 'POST',
        url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
        json: true,
        body: { chat_id: CHAT, text: msg },
      });
      return [{ json: { testSent: true, telegramResponse: res } }];
    } catch (e) {
      return [{ json: { testSent: false, error: e.message, stack: e.stack } }];
    }
  }

  const d = kst.getUTCDay();
  const h = kst.getUTCHours();
  const m = kst.getUTCMinutes();

  if (!(d >= 1 && d <= 5)) return [{ json: { skipped: true, reason: 'Weekend' } }];

  const today = `${kst.getUTCFullYear()}-${String(kst.getUTCMonth() + 1).padStart(2, '0')}-${String(kst.getUTCDate()).padStart(2, '0')}`;
  if (HOLIDAYS.includes(today)) return [{ json: { skipped: true, reason: 'Holiday (KRX closed)' } }];
  // HOLIDAYS 만료 경고 (마지막 등록 공휴일: 2026-12-25 → 2027년 이후 공휴일 미적용)
  if (today > '2026-12-25' && !store.holidayWarnSent) {
    store.holidayWarnSent = true;
    try { await http({ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage', json: true, body: { chat_id: CHAT, text: '⚠️ [설정 필요] HOLIDAYS 배열이 2026년까지만 등록되어 있습니다. swing_scanner_code.js 상단 HOLIDAYS 상수에 2027년 공휴일을 추가해주세요.' } }); } catch(e) {}
  }

  if (h < 9) return [{ json: { skipped: true, reason: 'Before market open' } }];
  if (h === 9 && m < 30) return [{ json: { skipped: true, reason: 'Too early - daily data not ready before 09:30' } }];

  if (h > STOP_NEW_ALERTS_HOUR || (h === STOP_NEW_ALERTS_HOUR && m >= STOP_NEW_ALERTS_MINUTE)) {
    return [{ json: { skipped: true, reason: 'Too close to market close' } }];
  }
  if (h >= 16) return [{ json: { skipped: true, reason: 'After market close' } }];

  // store는 Line 333에서 이미 선언됨 (forceTest 이전)
  if (!store.swingMeta) store.swingMeta = {};
  store.swingMeta.lastRunAt = now.toISOString();
  store.swingMeta.lastRunDate = today;

  if (store.swingMeta._lastFullFinish && (Date.now() - store.swingMeta._lastFullFinish) < 90000) {
    return [{ json: { skipped: true, reason: 'Queue backed up - fast drain' } }];
  }

  if (!store.swingSent) store.swingSent = {};
  if (!store.weeklyRecommendations) store.weeklyRecommendations = {};
  const cutoffDate = new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000);
  const cutoffStr = `${cutoffDate.getFullYear()}-${String(cutoffDate.getMonth()+1).padStart(2,'0')}-${String(cutoffDate.getDate()).padStart(2,'0')}`;
  for (const dateKey in store.weeklyRecommendations) {
    if (dateKey < cutoffStr) delete store.weeklyRecommendations[dateKey];
  }
  if (!store.weeklyRecommendations[today]) store.weeklyRecommendations[today] = [];

  const cleanOldHistory = () => {
    const cutoff = now.getTime() - DUPLICATE_WINDOW_MINUTES * 60 * 1000;
    for (const ticker in store.swingSent) {
      if (store.swingSent[ticker] < cutoff) delete store.swingSent[ticker];
    }
  };
  cleanOldHistory();

  const bl = store.blacklist || {};
  const riskSet = new Set((bl.riskCodes || []).map(String));
  const themeFilterMode = String(bl.themeFilterMode || 'off').toLowerCase();
  const themeSet = (themeFilterMode === 'off') ? new Set() : new Set((bl.themeCodes || []).map(String));
  let excludedRisk = 0;
  let excludedTheme = 0;
  const riskCacheAt = bl.riskUpdatedAt || null;
  const themeCacheAt = bl.themeUpdatedAt || null;

  const to0 = (n) => Math.round(Number(n) || 0).toLocaleString('ko-KR');
  const getCode = (sym) => {
    const v = String(sym);
    if (v.endsWith('.KS') || v.endsWith('.KQ')) return v.slice(0, -3);
    return v;
  };
  const normalize = (s) => String(s || '').trim();
  const pct = (r) => (r * 100).toFixed(1) + '%';


  const NAME = {};
  const ALL_TICKERS = [];
  const SEEN_CODES = new Set();
  let rows = [];
  let krxUniverseSource = 'live';
  let krxUniverseError = null;

  const trdDd = `${kst.getUTCFullYear()}${String(kst.getUTCMonth() + 1).padStart(2, '0')}${String(kst.getUTCDate()).padStart(2, '0')}`;

  if (!store.krxState) store.krxState = {};
  const ks = store.krxState;
  const nowMs = now.getTime();
  const circuitUntilMs = ks.circuitUntil ? new Date(ks.circuitUntil).getTime() : 0;
  const isFirstScan = (h === 9 && m >= 10 && m < 15);
  const circuitActive = !!(circuitUntilMs && circuitUntilMs > nowMs && ks.circuitDate === today && !isFirstScan);
  if (isFirstScan && ks.circuitUntil) {
    delete ks.circuitUntil;
    delete ks.circuitDate;
  }

  const openCircuit = (reason) => {
    const until = new Date(nowMs + 15 * 60 * 1000).toISOString();
    ks.circuitDate = today;
    ks.circuitUntil = until;
    ks.lastFailAt = new Date(nowMs).toISOString();
    ks.lastFailReason = String(reason || 'unknown');
  };

  if (store.krxUniverseCache && store.krxUniverseCache.trdDd === trdDd && Array.isArray(store.krxUniverseCache.rows) && store.krxUniverseCache.rows.length) {
    rows = store.krxUniverseCache.rows;
    krxUniverseSource = 'cache';
  } else {
    krxUniverseSource = 'naver';

    let _iconv = null;
    try { _iconv = require('iconv-lite'); } catch(e) {}
    const fetchText = async (url) => {
      if (_iconv) {
        // Naver sise 페이지는 EUC-KR 인코딩 → iconv-lite로 정확히 디코딩
        const raw = await http({
          method: 'GET', url,
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://finance.naver.com/', 'Accept': 'text/html'
          },
          json: false, encoding: null
        });
        const buf = Buffer.isBuffer(raw) ? raw : Buffer.from(String(raw || ''), 'binary');
        return _iconv.decode(buf, 'euc-kr');
      }
      // iconv-lite 없을 때 utf8 폴백 (한글 깨질 수 있음)
      const raw = await http({
        method: 'GET', url,
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
          'Referer': 'https://finance.naver.com/', 'Accept': 'text/html', 'Accept-Charset': 'utf-8'
        },
        json: false, encoding: 'utf8'
      });
      if (Buffer.isBuffer(raw)) return raw.toString('utf8');
      return String(raw ?? '');
    };

    const extractCodeNamePairs = (html) => {
      const out = [];
      const re = new RegExp('/item/main\\.naver\\?code=(\\d{6})[^>]*>([^<]{1,60})<', 'g');
      let m;
      while ((m = re.exec(html))) {
        out.push([m[1], String(m[2] || '').trim()]);
      }
      return out;
    };

    const codeSet = new Set();
    const naverRows = [];
    const MAX_PAGES = 40; // 상위 40 pages (~2000종목/시장) — 전체 시장 커버 (KOSDAQ ~1600종목)

    const fetchAllFromMarket = async (sosok, mktNm) => {
      let consecutiveErrors = 0;
      for (let p = 1; p <= MAX_PAGES; p++) {
        try {
          const url = `https://finance.naver.com/sise/sise_market_sum.naver?sosok=${sosok}&page=${p}`;
          const html = await fetchText(url);
          const pairs = extractCodeNamePairs(html);
          if (!pairs || pairs.length === 0) break;
          consecutiveErrors = 0; // 성공 시 오류 카운터 초기화
          let newStocks = 0;
          for (const [c, nm] of pairs) {
            if (!c || codeSet.has(c)) continue;
            codeSet.add(c);
            naverRows.push({
              ISU_SRT_CD: c, ISU_ABBRV: nm || c, ISU_NM: nm || c, MKT_NM: mktNm,
              TDD_CLSPRC: String(MIN_PRICE),
              ACC_TRDVAL: String(MIN_INTRADAY_TURNOVER),
            });
            newStocks++;
          }
          if (newStocks === 0) break;
          await new Promise((r) => setTimeout(r, 100 + Math.floor(Math.random() * 50)));
        } catch (e) {
          consecutiveErrors++;
          if (consecutiveErrors >= 3) break; // 연속 3회 실패 시 rate-limit으로 판단, 조기 종료
          await new Promise((r) => setTimeout(r, 500));
        }
      }
    };

    try {
      await fetchAllFromMarket(0, 'KOSPI');
      await fetchAllFromMarket(1, 'KOSDAQ');
      rows = naverRows;
      if (rows.length > 0) {
        krxUniverseSource = 'naver';
        // Naver 종목명을 별도 저장 (KRX 인코딩 깨짐 방지용 — KRX가 캐시 덮어써도 보존)
        // 기존 이름을 유지하고 새 이름만 추가/갱신 (오늘 Naver에서 누락된 종목도 이전 이름 보존)
        if (store.naverNamesDate !== today) {
          if (!store.naverNames) store.naverNames = {};
          // 이전 세션에서 저장된 깨진 항목 정리 (깨진 이름이 캐시에 남아 재사용되는 문제 방지)
          for (const k of Object.keys(store.naverNames)) {
            if (isGarbled(store.naverNames[k])) delete store.naverNames[k];
          }
          let validNmCount = 0;
          for (const nr of rows) {
            const c = String(nr.ISU_SRT_CD || '');
            const n = String(nr.ISU_ABBRV || nr.ISU_NM || '').trim();
            if (c && n && n !== c && !isGarbled(n)) { store.naverNames[c] = n; validNmCount++; }
          }
          // 유효 이름이 충분할 때만 "오늘 완료" 표시 → 깨진 경우 다음 실행에서 재시도
          if (validNmCount >= 100) store.naverNamesDate = today;
          // naverNames 크기 상한 (3000개 초과 시 절반 정리 — 메모리 누수 방지)
          const nmKeys = Object.keys(store.naverNames);
          if (nmKeys.length > 3000) {
            for (let ki = 0; ki < Math.floor(nmKeys.length / 2); ki++) delete store.naverNames[nmKeys[ki]];
          }
        }
        store.krxUniverseCache = {
          trdDd, fetchedAt: new Date(nowMs).toISOString(), source: 'naver',
          rows: rows.slice(0, 5000).map((x) => ({
            ISU_SRT_CD: String(x?.ISU_SRT_CD || ''), ISU_ABBRV: String(x?.ISU_ABBRV || ''),
            ISU_NM: String(x?.ISU_NM || ''), MKT_NM: String(x?.MKT_NM || ''),
            TDD_CLSPRC: String(x?.TDD_CLSPRC || '0'), ACC_TRDVAL: String(x?.ACC_TRDVAL || '0'),
          })),
        };
      } else {
        krxUniverseError = 'Naver returned 0 rows';
      }
    } catch (e) {
      krxUniverseError = String(e?.message || e);
    }
  }

  if (circuitActive) {
    krxUniverseSource = 'circuit';
    krxUniverseError = ks.lastFailReason || 'circuit_active';
  } else {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const headers = {
          'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
          Origin: 'https://data.krx.co.kr',
          Referer: 'https://data.krx.co.kr/contents/MDC/CM/MDI/mdiLoader/index.cmd',
          'X-Requested-With': 'XMLHttpRequest',
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
        };
        const body = `bld=dbms/MDC/STAT/standard/MDCSTAT01501&mktId=ALL&trdDd=${trdDd}&share=1&money=1&csvxls_isNo=false`;
        const r = await http({ method: 'POST', url: 'https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd', headers, body, json: true });
        rows = (r && (r.output || r.OutBlock_1 || [])) || [];
        if (rows.length > 0) {
          krxUniverseSource = 'live';
          store.krxUniverseCache = {
            trdDd, fetchedAt: new Date(nowMs).toISOString(),
            rows: rows.slice(0, 5000).map((x) => {
              const c = String(x?.ISU_SRT_CD || '');
              // KRX는 EUC-KR 인코딩 문제로 종목명이 깨질 수 있음 → Naver 이름 우선 사용
              const naverNm = store.naverNames && store.naverNames[c];
              const krxNm = String(x?.ISU_ABBRV || x?.ISU_NM || '');
              return {
                ISU_SRT_CD: c,
                ISU_ABBRV: naverNm || krxNm,
                ISU_NM: naverNm || String(x?.ISU_NM || ''),
                MKT_NM: String(x?.MKT_NM || ''),
                TDD_CLSPRC: String(x?.TDD_CLSPRC || '0'),
                ACC_TRDVAL: String(x?.ACC_TRDVAL || '0'),
              };
            }),
          };
          break;
        }
      } catch (e) {
        krxUniverseError = String(e?.message || e);
        if (attempt === 1) {
          openCircuit(krxUniverseError);
          krxUniverseSource = 'live_failed';
        }
        await new Promise((resolve) => setTimeout(resolve, 1200 + Math.floor(Math.random() * 600)));
      }
    }
  }

  // naver fallback (sise_quant: sorted by turnover, top 3 pages)
  if (!rows || rows.length === 0) {
    const fetchText = async (url) => {
      const raw = await http({
        method: 'GET', url,
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
          'Referer': 'https://finance.naver.com/', 'Accept': 'text/html', 'Accept-Charset': 'utf-8'
        },
        json: false, encoding: 'utf8'
      });
      if (Buffer.isBuffer(raw)) return raw.toString('utf8');
      return String(raw ?? '');
    };

    const extractCodeNamePairs = (html) => {
      const out = [];
      const re = new RegExp('/item/main\\.naver\\?code=(\\d{6})[^>]*>([^<]{1,60})<', 'g');
      let m;
      while ((m = re.exec(html))) {
        out.push([m[1], String(m[2] || '').trim()]);
      }
      return out;
    };

    const MAX_PAGES = 3;
    const codeSet = new Set();
    const naverRows = [];
    const addFromMarket = async (sosok, mktNm) => {
      for (let p = 1; p <= MAX_PAGES; p++) {
        try {
          const url = `https://finance.naver.com/sise/sise_quant.nhn?sosok=${sosok}&page=${p}`;
          const html = await fetchText(url);
          const pairs = extractCodeNamePairs(html);
          if (!pairs || pairs.length === 0) break;
          let added = 0;
          for (const [c, nm] of pairs) {
            if (!c || codeSet.has(c)) continue;
            codeSet.add(c);
            naverRows.push({
              ISU_SRT_CD: c, ISU_ABBRV: nm || c, ISU_NM: nm || c, MKT_NM: mktNm,
              TDD_CLSPRC: String(MIN_PRICE),
              ACC_TRDVAL: String(MIN_INTRADAY_TURNOVER),
            });
            added++;
          }
          if (added === 0) break;
        } catch (e) {
          await new Promise((r) => setTimeout(r, 500));
        }
        await new Promise((r) => setTimeout(r, 120 + Math.floor(Math.random() * 120)));
      }
    };

    try {
      await addFromMarket(0, 'KOSPI');
      await addFromMarket(1, 'KOSDAQ');
      rows = naverRows;
      if (rows.length > 0) krxUniverseSource = 'naver_fallback';
    } catch (e) {
      krxUniverseError = String(e?.message || e);
    }
  }

  store.sectorMap = {}; // 매 실행마다 초기화 — stale 섹터 데이터 방지

  for (let i = 0; i < rows.length; i++) {
    const row = rows[i] || {};
    const rc = normalize(String(row.ISU_SRT_CD || ''));
    const nm = (store.naverNames && store.naverNames[rc]) || String(row.ISU_ABBRV || row.ISU_NM || '').trim();
    const mkt = String(row.MKT_NM || '').toLowerCase();

    if (mkt.includes('konex') || mkt.includes('코넥스')) continue;

    const price = Number((row.TDD_CLSPRC || '0').replace(/,/g, ''));
    const turnover = Number((row.ACC_TRDVAL || '0').replace(/,/g, ''));

    if (!rc || !nm) continue;
    if (SEEN_CODES.has(rc)) continue;
    SEEN_CODES.add(rc);

    if (riskSet.has(rc)) { excludedRisk++; continue; }
    if (themeSet.has(rc)) { excludedTheme++; continue; }

    if (price < MIN_PRICE) continue;
    if (turnover < MIN_INTRADAY_TURNOVER) continue;

    NAME[rc] = isGarbled(nm) ? rc : nm;
    // 섹터 모멘텀 감지용 업종코드 저장 (IDX_IND_NM 앞 6자리 or SECT_TP_NM)
    const sectorCode = String(row.IDX_IND_NM || row.SECT_TP_NM || '').trim().slice(0, 6);
    if (sectorCode) store.sectorMap[rc] = sectorCode;
    let suffix = '.KS';
    if (mkt.includes('kosdaq') || mkt.includes('코스닥')) suffix = '.KQ';
    ALL_TICKERS.push(rc + suffix);
  }

  if (ALL_TICKERS.length === 0) {
    if (!store.swingAlerts) store.swingAlerts = {};
    const msg = '[시스템 경고] KRX 종목 데이터 로드 실패' + NL + kst.toISOString().slice(0, 16).replace('T', ' ') + ' KST';
    store.swingAlerts.noHitDate = today;
    try {
      await http({ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage', json: true, body: { chat_id: CHAT, text: msg } });
    } catch (e) {}
    return [{ json: { error: 'Failed to load KRX universe' } }];
  }

  // ===== API / Cache Setup =====
  let naverOkCount = 0;
  let naverNoResultCount = 0;
  let naverErrorCount = 0;
  const naverErrorByStatus = {};
  const naverErrorSamples = [];
  let naverRawSample = null; // Naver 실제 응답 진단용 (비정상 응답 첫 1건 캡처)
  const pickStatus = (e) => {
    const s = e?.statusCode ?? e?.response?.statusCode ?? e?.response?.status ?? e?.httpCode ?? e?.cause?.statusCode;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  };

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const dayKey = today; // today와 동일한 KST 날짜 — 이중 계산 제거
  // n8n static data 중첩 객체 변경 보장: 최상위 키 재할당
  if (!store.naverCache || store.naverCache.dayKey !== dayKey) {
    store.naverCache = { daily: {}, dayKey };
  }
  const naverCache = store.naverCache;
  const getCached = (bucket, key, maxAgeMs) => {
    const v = bucket[key];
    if (!v) return null;
    if (Date.now() - v.at > maxAgeMs) return null;
    return v.data;
  };
  const setCached = (bucket, key, data) => { bucket[key] = { at: Date.now(), data }; };

  // Naver chart API v1: api.stock.naver.com (YYYYMMDDHHMMSS 형식)
  const fetchDaily = async (code, startDate, endDate) => {
    // 날짜를 YYYYMMDDHHMMSS 형식으로 변환 (8자리면 000000 추가)
    const sd = startDate.length === 8 ? startDate + '000000' : startDate;
    const ed = endDate.length === 8 ? endDate + '235959' : endDate;
    const url = `https://api.stock.naver.com/chart/domestic/item/${code}/day?startDateTime=${sd}&endDateTime=${ed}`;
    return await http({
      method: 'GET', url, json: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://finance.naver.com/',
        'Accept': 'application/json', 'Accept-Charset': 'utf-8', 'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8'
      },
      encoding: 'utf8'
    });
  };

  // Naver chart API v2: fchart.stock.naver.com (대체 소스, 텍스트 파싱)
  const fetchDailyFchart = async (code, count) => {
    const url = `https://fchart.stock.naver.com/sise.nhn?symbol=${code}&timeframe=day&count=${count}&requestType=0`;
    const raw = await http({
      method: 'GET', url, json: false,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://finance.naver.com/',
        'Accept': 'text/plain,*/*', 'Accept-Charset': 'utf-8'
      },
      encoding: 'utf8'
    });
    const text = Buffer.isBuffer(raw) ? raw.toString('utf8') : String(raw || '');
    // 응답 형식: ...^20260226|시가|고가|저가|종가|거래량^...
    const rows = text.split('^').map(s => s.trim()).filter(s => /^\d{8}\|/.test(s));
    if (!rows.length) return null;
    return rows.map(row => {
      const p = row.split('|');
      return {
        localDate: p[0], openPrice: Number(p[1]), highPrice: Number(p[2]),
        lowPrice: Number(p[3]), closePrice: Number(p[4]), accumulatedTradingVolume: Number(p[5] || 0)
      };
    }).filter(r => r.closePrice > 0 && /^\d{8}$/.test(r.localDate));
  };

  // 전일 거래일 날짜 계산 (주말/공휴일 제외) — 장중 당일을 endDate로 쓰면 Naver API가 빈 배열 반환
  const getPrevTradingDay = () => {
    let d = new Date(Date.now() + 9 * 3600000 - 24 * 3600000);
    for (let i = 0; i < 10; i++) {
      const dow = d.getUTCDay();
      const ds = d.toISOString().slice(0, 10);
      if (dow >= 1 && dow <= 5 && !HOLIDAYS.includes(ds)) return ds.replace(/-/g, '');
      d = new Date(d.getTime() - 24 * 3600000);
    }
    return new Date(Date.now() + 9 * 3600000 - 24 * 3600000).toISOString().slice(0, 10).replace(/-/g, '');
  };
  const prevTradingDay = getPrevTradingDay(); // e.g. '20260226'

  // 응답 배열을 chart 포맷으로 변환
  const respToChart = (resp, t) => {
    const timestamps = resp.map(d => new Date(d.localDate.slice(0,4) + '-' + d.localDate.slice(4,6) + '-' + d.localDate.slice(6,8)).getTime() / 1000);
    const opens = resp.map(d => d.openPrice);
    const highs = resp.map(d => d.highPrice);
    const lows = resp.map(d => d.lowPrice);
    const closes = resp.map(d => d.closePrice);
    const volumes = resp.map(d => d.accumulatedTradingVolume);
    return { chart: { result: [{ meta: { symbol: t, currency: 'KRW', regularMarketPrice: closes[closes.length - 1] }, timestamp: timestamps, indicators: { quote: [{ open: opens, high: highs, low: lows, close: closes, volume: volumes }] } }], error: null } };
  };

  const httpDaily = async (t) => {
    const code = t.replace(/\.KS$/, '').replace(/\.KQ$/, '');
    const cached = getCached(naverCache.daily, code, 60 * 60 * 1000);
    if (cached) return cached;
    try {
      const kstNow = new Date(Date.now() + 9 * 3600000);
      // endDate = 전일 거래일 (당일 장중 날짜 사용 시 Naver API 빈 배열 반환 방지)
      const endDate = prevTradingDay;
      const startKst = new Date(kstNow.getTime() - 365 * 24 * 3600000);
      const startDate = startKst.toISOString().slice(0, 10).replace(/-/g, '');

      // [1차] api.stock.naver.com (365일)
      let resp = await fetchDaily(code, startDate, endDate);

      // [naver_resp_normalize] 다양한 응답 형식 정규화 (Buffer, string BOM, 객체 래핑 등)
      const _normalizeNaverResp = (r) => {
        if (r === null || r === undefined) return [];
        if (Buffer && Buffer.isBuffer(r)) r = r.toString('utf8');
        if (typeof r === 'string') {
          const cleaned = r.replace(/^\uFEFF/, '').trim(); // BOM 및 앞뒤 공백 제거
          try { r = JSON.parse(cleaned); } catch(_) { return []; }
        }
        if (Array.isArray(r)) return r;
        if (r && typeof r === 'object') {
          // n8n이 응답을 객체로 래핑하는 경우 (body/data/result/chartPriceList 등)
          if (Array.isArray(r.body)) return r.body;
          if (Array.isArray(r.data)) return r.data;
          if (Array.isArray(r.result)) return r.result;
          if (Array.isArray(r.chartPriceList)) return r.chartPriceList;
        }
        return [];
      };

      // [1차] api.stock.naver.com (365일) - 응답 정규화 적용
      resp = _normalizeNaverResp(resp);

      // 실제 응답 샘플 캡처 (비정상 응답 진단용, 첫 1건만) - 원본 타입/값 기록
      if ((!Array.isArray(resp) || resp.length === 0) && !naverRawSample) {
        try { naverRawSample = JSON.stringify(resp).slice(0, 300); } catch(_) { naverRawSample = String(resp).slice(0, 300); }
      }

      // [2차] api.stock.naver.com (180일, 재시도)
      if (!Array.isArray(resp) || resp.length === 0) {
        await sleep(200);
        const startKstAlt = new Date(kstNow.getTime() - 180 * 24 * 3600000);
        const startDateAlt = startKstAlt.toISOString().slice(0, 10).replace(/-/g, '');
        resp = _normalizeNaverResp(await fetchDaily(code, startDateAlt, endDate));
      }

      // [3차] fchart.stock.naver.com (대체 API 폴백)
      if (!Array.isArray(resp) || resp.length === 0) {
        await sleep(300);
        const fchartResp = await fetchDailyFchart(code, 300);
        if (fchartResp && fchartResp.length > 0) {
          const chart = respToChart(fchartResp, t);
          setCached(naverCache.daily, code, chart);
          return chart;
        }
      }

      if (!Array.isArray(resp) || resp.length === 0) {
        if (cached) return cached;
        return { chart: { result: null, error: { description: 'No data from Naver' } } };
      }
      const chart = respToChart(resp, t);
      setCached(naverCache.daily, code, chart);
      return chart;
    } catch (e) {
      const status = e?.statusCode ?? e?.response?.statusCode ?? e?.response?.status;
      if (status === 400 || status === 404) {
        const emptyResult = { chart: { result: null, error: { description: `Invalid code: ${status}` } } };
        setCached(naverCache.daily, code, emptyResult);
        return emptyResult;
      }
      if (cached) return cached;
      return { chart: { result: null, error: { description: String(e?.message || e) } } };
    }
  };

  // ===== SCANNING: Daily-Only Pass (rate-limiting 방지) =====
  const candidates = [];
  const BATCH_SIZE = 10;
  const BATCH_DELAY_MS = 600; // Naver API rate-limiting 방지

  const _EXEC_START = Date.now();
  const _MAX_EXEC_MS = 9 * 60 * 1000; // 9분 제한

  for (let i = 0; i < ALL_TICKERS.length; i += BATCH_SIZE) {
    if (Date.now() - _EXEC_START > _MAX_EXEC_MS) break;

    const batch = ALL_TICKERS.slice(i, i + BATCH_SIZE);
    await Promise.all(batch.map(async (t) => {
      try {
        if (store.swingSent[t]) return;

        const cDaily = await httpDaily(t);
        const errDaily = cDaily?.chart?.error?.description;
        const noDataDaily = errDaily && String(errDaily).includes('No data from Naver');

        if (errDaily && !noDataDaily) {
          naverErrorCount++;
          if (naverErrorSamples.length < 3) {
            naverErrorSamples.push({ ticker: t, intra: null, daily: errDaily });
          }
        }

        const rDaily = cDaily?.chart?.result?.[0];
        if (!rDaily) { naverNoResultCount++; return; }
        naverOkCount++;

        const qD = rDaily.indicators?.quote?.[0] || {};
        const rawClose = (qD.close  || []).map(Number);
        const rawHigh  = (qD.high   || []).map(Number);
        const rawLow   = (qD.low    || []).map(Number);
        const rawVol   = (qD.volume || []).map(Number);
        const rawOpen  = (qD.open   || []).map(Number); // intradayStrength 계산용
        // closeD/highD/lowD/volD/openD를 동일 기준 인덱스로 정렬
        const validIdx = rawClose.map((_, i) => i).filter(i => rawClose[i] > 0 && rawHigh[i] > 0 && rawLow[i] > 0);
        const closeD = validIdx.map(i => rawClose[i]);
        const highD  = validIdx.map(i => rawHigh[i]);
        const lowD   = validIdx.map(i => rawLow[i]);
        const volD   = validIdx.map(i => (Number.isFinite(rawVol[i]) ? Math.max(0, rawVol[i]) : 0));
        const openD  = validIdx.map(i => (rawOpen[i] > 0 ? rawOpen[i] : rawClose[i])); // 시가 없으면 종가 fallback

        if (closeD.length < 60) return;

        const dIdx = closeD.length - 1;
        const currentPrice = closeD[dIdx]; // 전일 종가 (daily-only)
        const prevClose = closeD[dIdx - 1] || currentPrice;
        const dailyChange = prevClose > 0 ? (currentPrice / prevClose - 1) : 0;

        if (currentPrice < MIN_PRICE) return;

        // 최소 거래량 체크 (저유동성 제외)
        const avg5Vol = volD.slice(Math.max(0, dIdx - 5), dIdx).reduce((a, b) => a + b, 0) / 5;
        if (avg5Vol < MIN_AVG5_VOLUME) return;

        const sma20_d = sma(closeD, 20);
        const sma60_d = sma(closeD, 60);

        // ===== 사전 계산: 새 지표 =====

        // [1] RVOL 상대 거래량 계산 (RSI 예외 판단을 위해 RSI 앞으로 이동)
        const vol20Avg = volD.slice(Math.max(0, dIdx - 20), dIdx).reduce((a, b) => a + b, 0) / Math.min(20, dIdx);
        const rvolVal = vol20Avg > 0 ? volD[dIdx] / vol20Avg : 0;
        if (rvolVal < 1.0) return; // D-grade: 평균 미달 거래량 → 노이즈 차단

        // 급등 후보 판별 플래그 (RSI 예외·정배열 예외에 공통 사용)
        const isSurgeCandidate = dailyChange >= SURGE_DAILY_CHANGE && rvolVal >= SURGE_RVOL_MIN;

        // [2] RSI14 필터 — 급등 후보는 RSI 90까지 허용, 일반은 80 유지
        const rsi14Val = calcRSI14(closeD, dIdx);
        if (Number.isFinite(rsi14Val)) {
          if (rsi14Val < RSI_MIN_ENTRY) return; // 모멘텀 부족 차단
          if (isSurgeCandidate && rsi14Val > RSI_SURGE_MAX) return; // 급등 후보: RSI 90 상한
          if (!isSurgeCandidate && rsi14Val > RSI_MAX_ENTRY) return; // 일반: RSI 80 상한 유지
        }

        // [3] ADX(14) 추세 강도 필터
        const adxResult = calcADX(highD, lowD, closeD, dIdx, 14);
        if (Number.isFinite(adxResult.adx) && adxResult.adx < ADX_TREND_MIN) return; // 횡보장 차단

        // [4] EMA5/EMA10 계산 (단기 정배열용)
        const ema5 = ema(closeD, 5);
        const ema10 = ema(closeD, 10);

        // [5] 52주 고점/저점 근접도 (PTH / priceFromLow)
        const high252 = Math.max(...highD.slice(Math.max(0, dIdx - 252), dIdx + 1).map(Number));
        const low252  = Math.min(...lowD.slice(Math.max(0, dIdx - 252), dIdx + 1).map(Number));
        const pth = high252 > 0 ? currentPrice / high252 : 0;
        const priceFromLow = low252 > 0 ? (currentPrice / low252 - 1) : 0; // 52주 저점 대비 반등률

        // [6] 5일/60일 거래량 비율 (수급 지속성)
        const volAvg5  = volD.slice(Math.max(0, dIdx - 5),  dIdx).reduce((a, b) => a + b, 0) / Math.min(5, dIdx);
        const volAvg60 = volD.slice(Math.max(0, dIdx - 60), dIdx).reduce((a, b) => a + b, 0) / Math.min(60, dIdx);
        const volTrend5_60 = volAvg60 > 0 ? volAvg5 / volAvg60 : 0;

        // [7] 당일 장 마감 강도 (intradayStrength)
        const dayRange = highD[dIdx] - lowD[dIdx];
        const intradayStrength = dayRange > 0 ? (closeD[dIdx] - openD[dIdx]) / dayRange : 0;

        // ===== 스코어링 =====
        let score = 0;
        const signals = [];

        // 필수 조건: 일봉 정배열 (SMA20 > SMA60) — 급등 후보는 예외 허용
        const dailyUptrend = sma20_d[dIdx] > sma60_d[dIdx];
        if (!dailyUptrend && !isSurgeCandidate) return; // 급등 조건 충족 시 정배열 예외
        if (dailyUptrend) {
          score += 15;
          signals.push('일봉정배열');
        }

        // 20일 박스권 돌파
        const recent20High = Math.max(...highD.slice(Math.max(0, dIdx - 20), dIdx));
        if (currentPrice > recent20High) {
          score += 35;
          signals.push('박스권돌파(20일)');
        }

        // N자형 눌림목
        const recent10High = Math.max(...highD.slice(Math.max(0, dIdx - 10), dIdx));
        if (recent10High > currentPrice * 1.15 && Math.abs(currentPrice - sma20_d[dIdx]) / currentPrice < 0.03) {
          score += 40;
          signals.push('N자형눌림목');
        }

        // 컵앤핸들 패턴
        const cupHandle = detectCupAndHandle(closeD, highD, lowD, dIdx);
        if (cupHandle.detected) {
          score += 40;
          signals.push('컵핸들');
        }

        // [NEW-1] RVOL 등급 점수 (Reddit: A-grade 53.5% 승률)
        if (rvolVal >= RVOL_GRADE_A) {
          score += 25;
          signals.push('거래량급증(A)');
        } else if (rvolVal >= RVOL_GRADE_B) {
          score += 20;
          signals.push('거래량급증(B)');
        } else if (rvolVal >= RVOL_GRADE_C) {
          score += 10;
          signals.push('거래량증가(C)');
        }

        // [NEW-2] ADX 추세 강도 보너스
        if (Number.isFinite(adxResult.adx) && adxResult.adx > 25 && adxResult.plusDI > adxResult.minusDI) {
          score += 10;
          signals.push('강추세(ADX)');
        }

        // [NEW-3] RSI 모멘텀 구간 보너스 (65-75 = 강한 상승 모멘텀)
        if (Number.isFinite(rsi14Val) && rsi14Val >= 65 && rsi14Val <= 75) {
          score += 10;
          signals.push('RSI모멘텀');
        }

        // [NEW-4] 52주 신고가 돌파 / 근접도 보너스 (PTH)
        // (2026-04-18 개선: 신고가 근접 점수 하향 — 저항선 위 물량 있는 종목 과대평가 방지)
        if (currentPrice >= high252) {
          score += NEW_HIGH52W_BONUS; // +40: 진짜 신고가 돌파 (저항선 없음)
          signals.push('52주신고가돌파');
        } else if (pth >= 0.95) {
          score += 15; // 25→15: 저항선 5% 이내 위험 반영
          signals.push('신고가근접(PTH)');
        } else if (pth >= 0.90) {
          score += 8;  // 15→8: 저항선 10% 이내 위험 반영
          signals.push('52주고점근접');
        }

        // [HIGH-1] 52주 저점 대비 반등률 (priceFromLow)
        if (priceFromLow >= 1.0) {
          score += PRICE_FROM_LOW_BONUS; // +20: 저점 대비 +100% 이상 반등 중
          signals.push('저점반등(100%+)');
        } else if (priceFromLow >= 0.30) {
          score += 10;
          signals.push('저점반등(30%+)');
        }

        // [HIGH-2] 5/60일 거래량 비율 — 수급 지속성
        if (volTrend5_60 >= VOL_TREND_5_60_A) {
          score += 20;
          signals.push('수급집중(A)');
        } else if (volTrend5_60 >= VOL_TREND_5_60_B) {
          score += 10;
          signals.push('수급집중(B)');
        }

        // [HIGH-3] 당일 장 마감 강도
        if (intradayStrength >= INTRADAY_STR_MIN) {
          score += INTRADAY_STR_BONUS; // +10
          signals.push('장마감강세');
        }

        // [NEW-5] EMA 단기 정배열 (EMA5 > EMA10 > SMA20)
        if (Number.isFinite(ema5[dIdx]) && Number.isFinite(ema10[dIdx]) &&
            ema5[dIdx] > ema10[dIdx] && ema10[dIdx] > sma20_d[dIdx]) {
          score += 15;
          signals.push('단기정배열(EMA)');
        }

        // ===== Stock Skills 보강 지표 =====
        // [STOCK-1] MACD 모멘텀 신호 (골든크로스 / 히스토그램 방향)
        const macdResult = calcMACD(closeD, dIdx);
        if (macdResult.goldenCross) {
          score += 15;
          signals.push('MACD골든크로스');
        } else if (Number.isFinite(macdResult.hist) && macdResult.hist > 0) {
          if (Number.isFinite(macdResult.histPrev) && macdResult.hist > macdResult.histPrev) {
            score += 10;
            signals.push('MACD모멘텀↑');
          } else {
            score += 5;
            signals.push('MACD양호');
          }
        } else if (Number.isFinite(macdResult.hist) && Number.isFinite(macdResult.histPrev) &&
                   macdResult.hist < 0 && macdResult.histPrev < 0) {
          score -= 10; // 지속 하락 모멘텀 패널티
        }

        // [STOCK-2] Bollinger Bands — 스퀴즈 돌파 / 모멘텀 구간
        // QA FIX: 스퀴즈 판정 강화 — 5일 전 폭이 10일 전보다 좁았어야(압축) 진짜 스퀴즈
        const bbNow   = calcBB(closeD, dIdx);
        const bbPrev5 = calcBB(closeD, Math.max(0, dIdx - 5));
        const bbPrev10 = calcBB(closeD, Math.max(0, dIdx - 10));
        if (Number.isFinite(bbNow.width) && Number.isFinite(bbPrev5.width) && bbPrev5.width > 0) {
          const isSqueeze = Number.isFinite(bbPrev10.width) && bbPrev5.width < bbPrev10.width; // 압축 확인
          if (bbNow.width > bbPrev5.width * 1.3 && isSqueeze) {
            // 압축 후 폭발: 진짜 스퀴즈 돌파
            score += 15;
            signals.push('BB스퀴즈돌파');
          } else if (Number.isFinite(bbNow.zScore) && bbNow.zScore >= 0.3 && bbNow.zScore <= 1.5) {
            // 중심선~상단 사이 (모멘텀 우호 구간)
            score += 8;
            signals.push('BB모멘텀구간');
          }
        }

        // [STOCK-3] OBV 수급 확인 (가격-거래량 다이버전스 탐지)
        const obvResult = calcOBV(closeD, volD, dIdx);
        if (obvResult.obvTrend === 1) {
          score += 20;
          signals.push('OBV수급확인');
        } else if (obvResult.obvTrend === -1) {
          score -= 10; // 수급 없는 상승 → 경고
          signals.push('OBV수급불일치');
        }

        // [STOCK-4] SMA5 완전 정배열 (5 > 20 > 60)
        const sma5_d = sma(closeD, 5);
        if (Number.isFinite(sma5_d[dIdx]) && sma5_d[dIdx] > sma20_d[dIdx]) {
          score += 5;
          signals.push('완전정배열(5>20>60)');
        }

        // [STOCK-5] 복합 확인 신호 — MACD 골든크로스 + 정배열 + OBV 수급 동시 충족
        if (macdResult.goldenCross && dailyUptrend && obvResult.obvTrend === 1) {
          score += 10;
          signals.push('복합확인신호');
        }
        // ===== /Stock Skills 보강 지표 =====

        // [HIGH-4] 연속 상승 패턴 — 2일+ 연속 양봉 & 거래량 확대
        {
          let consecUp = 0;
          let volExpanding = true;
          for (let ci = dIdx - 2; ci <= dIdx; ci++) {
            if (ci > 0 && closeD[ci] > closeD[ci - 1]) consecUp++;
            else { consecUp = 0; break; }
            if (ci > 0 && volD[ci] < volD[ci - 1]) volExpanding = false;
          }
          if (consecUp >= 2 && volExpanding) {
            score += CONSEC_UP_BONUS; // +15
            signals.push(`연속상승(${consecUp}일)`);
          }
        }

        if (score < RELAX_SCORE) return;

        // 등급 판정 (기술 점수 기반 5단계 분류)
        // 강매:   score≥120 → 고강도 기술 신호 (5거래일 보유)
        // 급등:   score≥100 & +5% & RVOL≥5x → 테마 모멘텀 급등 (2거래일)
        // 매도차익: +2% & RVOL A등급 → 단기 급등 포착 (2거래일)
        // 매수:   score≥80  → 표준 스윙 (발송 차단)
        // 관심:   score≥60  → 미발송
        const strictPass = score >= MIN_SCORE;
        const relaxedPass = score >= RELAX_SCORE;
        if (!strictPass) signals.push('완화');

        const isStrong    = score >= SCORE_STRONG;
        const isSurge     = !isStrong && score >= SCORE_SURGE
                            && dailyChange >= SURGE_DAILY_CHANGE
                            && rvolVal >= SURGE_RVOL_MIN;
        const isShortTrade = !isStrong && !isSurge && strictPass
                            && dailyChange >= 0.02 && rvolVal >= RVOL_GRADE_A;
        const grade = isStrong      ? '강매'
                    : isSurge       ? '급등'
                    : isShortTrade  ? '매도차익'
                    : strictPass    ? '매수'
                    : '관심';
        if (grade === '관심' || grade === '매수') return; // 관심·매수 등급 미발송
        // [OBV-01] 수급 필수 조건 (강매 제외) — 2026-04-18 개선
        // OBV 수급 확인 OR RVOL A등급(3x+) 중 하나 必 — 실제 매수세 없는 패턴 종목 차단
        const hasSupply = (obvResult.obvTrend === 1) || (rvolVal >= RVOL_GRADE_A);
        if (!hasSupply && grade !== '강매') return;
        // 요일별 rankScore 보정 (d = kst.getUTCDay(), 상단에서 선언됨)
        const dowAdj = (d === 4) ? DOW_BONUS_THU     // 목요일 +3
                     : (d === 3) ? DOW_BONUS_WED     // 수요일 +2
                     : (d === 5) ? -DOW_PENALTY_FRI  // 금요일 -5
                     : 0;
        const rankScore = score + dowAdj;

        const atrAbs = calcAtrAbs(highD, lowD, dIdx, ATR_WINDOW);
        let stop = currentPrice - atrAbs * ATR_STOP_MULT;
        // TARGET-01: 등급별 목표 배수 분기 — 2026-04-18 개선 (강매만 2.8x, 나머지 2.0x)
        const targetMult = (grade === '강매')     ? ATR_TARGET_MULT        // 강매: ATR×2.8 (5거래일)
                         : (grade === '매도차익') ? ATR_TARGET_SHORT       // 매도차익: ATR×1.5
                         : ATR_TARGET_MULT_NORMAL;                          // 급등·기타: ATR×2.0
        let target = currentPrice + atrAbs * targetMult;
        const stopCap = currentPrice * (1 - CAP_STOP_PCT);
        const targetCap = currentPrice * (1 + CAP_TARGET_PCT);
        if (Number.isFinite(stopCap)) stop = Math.max(stop, stopCap);
        if (Number.isFinite(targetCap)) target = Math.min(target, targetCap);

        // [NEW-6] 3% 최저 목표가 보장 + R:R 1.5 필터
        target = Math.max(target, currentPrice * (1 + MIN_TARGET_PCT));
        const rr = (stop > 0 && currentPrice > stop) ? (target - currentPrice) / (currentPrice - stop) : 0;
        if (rr < MIN_RR_RATIO) return; // 불리한 R:R 차단

        // 1차 목표가: 데이터 5~10% 구간(41.6%) 기반, 모든 등급 공통
        // target보다 작을 때만 유효 (저변동성 종목에서 target1 > target 역전 방지)
        const target1Raw = currentPrice * (1 + TARGET1_PCT);
        const target1 = target1Raw < target ? target1Raw : null;

        const rg = await getMarketRegime(store, today);
        const riskOn = !!(rg && rg.riskOn);
        const sizeFactor = riskOn ? 1.0 : 0.5;
        const qty = calcQty(ACCOUNT_KRW, RISK_PCT_PER_TRADE * sizeFactor, currentPrice, stop);

        const code = normalize(getCode(t));
        const name = NAME[code] || code;
        const mkt = t.endsWith('.KS') ? 'KOSPI' : 'KOSDAQ';

        candidates.push({
          ticker: t, code, name, market: mkt,
          entry: currentPrice, target, target1, stop,
          score, signals, dailyChange, currentPrice, prevClose,
          timeStr: timeStrNow, type: '스윙',
          rankScore, atrAbs, rvolVal, riskOn, qty, strictPass, relaxedPass, grade,
        });
      } catch (e) {
        naverErrorCount++;
        const st = pickStatus(e);
        const key = String(st || 'ERR');
        naverErrorByStatus[key] = (naverErrorByStatus[key] || 0) + 1;
        if (naverErrorSamples.length < 3) {
          naverErrorSamples.push({ ticker: t, status: st, message: (e?.message || String(e)).slice(0, 180) });
        }
      }
    }));
    await sleep(BATCH_DELAY_MS); // Rate-limiting 방지 딜레이
  }

  // 스캔 완료 후 per-stock 캐시 제거 (1,500종목 × ~20KB = ~30MB 메모리 누적 방지)
  // _lastFullFinish 가드로 재실행이 차단되므로 캐시 재사용 가능성 없음
  if (store.naverCache) store.naverCache.daily = {};

  // ===== 에러/경고 알림 =====
  // swingSent skip 종목은 fetch 자체를 안 하므로 실제 fetch 수 기준으로 비교
  const totalFetched = naverOkCount + naverNoResultCount + naverErrorCount;
  const noResultAll = (totalFetched > 0 && naverOkCount === 0 && naverNoResultCount === totalFetched);
  const alertHour = kst.getUTCHours();
  const alertMin = kst.getUTCMinutes();
  const isMarketTimeForAlert = (alertHour > 9 || (alertHour === 9 && alertMin >= 5)) &&
                               (alertHour < 15 || (alertHour === 15 && alertMin < 25));
  if (noResultAll && isMarketTimeForAlert) {
    if (!store.naverAlerts) store.naverAlerts = {};
    if (store.naverAlerts.noResultAllDate !== today) {
      const rawInfo = naverRawSample ? naverRawSample.slice(0, 200) : 'null';
      const msg =
        '⚠️ [데이터 경고] Naver 응답이 전 종목 빈 결과' + NL +
        `- KST: ${today} ${timeStrNow}` + NL +
        `- universe: ${ALL_TICKERS.length}` + NL +
        `- Naver OK/NoResult/Error: ${naverOkCount}/${naverNoResultCount}/${naverErrorCount}` + NL +
        `- prevTradingDay: ${prevTradingDay}` + NL +
        `- rawSample: ${rawInfo}`;
      try { await http({ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage', json: true, body: { chat_id: CHAT, text: msg } }); } catch (e) {}
      store.naverAlerts.noResultAllDate = today;
    }
  }
  if (naverErrorCount > 0) {
    if (!store.naverAlerts) store.naverAlerts = {};
    const last = Number(store.naverAlerts.lastErrorAt || 0);
    const nowMs2 = Date.now();
    if (nowMs2 - last > 30 * 60 * 1000) {
      const sample = (naverErrorSamples && naverErrorSamples.length) ? JSON.stringify(naverErrorSamples.slice(0, 2)) : 'none';
      const msg =
        '⚠️ [데이터 오류] 스캔 중 에러 발생' + NL +
        `- KST: ${today} ${timeStrNow}` + NL +
        `- Naver OK/NoResult/Error: ${naverOkCount}/${naverNoResultCount}/${naverErrorCount}` + NL +
        `- sample: ${sample}`;
      try { await http({ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage', json: true, body: { chat_id: CHAT, text: msg } }); } catch (e) {}
      store.naverAlerts.lastErrorAt = nowMs2;
    }
  }

  // ===== 후보 선정 =====
  candidates.sort((a, b) => (b.rankScore || b.score) - (a.rankScore || a.score));

  // 섹터 동반 강세 보너스 — 동일 업종 2개+ 동시 강세 시 rankScore +10
  if (store.sectorMap) {
    const sectorCounts = {};
    for (const c of candidates) {
      const sc = store.sectorMap[c.code];
      if (sc) sectorCounts[sc] = (sectorCounts[sc] || 0) + 1;
    }
    for (const c of candidates) {
      const sc = store.sectorMap[c.code];
      if (sc && sectorCounts[sc] >= 2) {
        c.rankScore = (c.rankScore || c.score) + SECTOR_MOMENTUM_BONUS;
        if (!c.signals.includes('섹터동반강세')) c.signals.push(`섹터동반강세(${sectorCounts[sc]}종목)`);
      }
    }
    // 섹터 보너스 반영 후 재정렬
    candidates.sort((a, b) => (b.rankScore || b.score) - (a.rankScore || a.score));
  }

  // 단기 고수익 등급만 선발 — 강매/급등/매도차익 3등급 한정, filler 없음
  const FAST_GRADES = new Set(['강매', '급등', '매도차익']);
  const selected = candidates
    .filter((c) => FAST_GRADES.has(c.grade))
    .slice(0, MAX_INTRADAY_SENDS);
  // MIN_DAILY_PICKS=0: 0건이면 알림 없이 정상 종료

  const sent = [];
  let sendFailCount = 0;
  const sendFailSamples = [];

  const send = async (c) => {
    const kstNow = new Date(Date.now() + 9 * 60 * 60 * 1000);
    const timeStr = String(kstNow.getUTCHours()).padStart(2, '0') + ':' + String(kstNow.getUTCMinutes()).padStart(2, '0');

    // 종목명 보완: 이름이 코드와 같거나 깨진 경우 naverNames 또는 Naver API로 재조회
    let displayName = c.name;
    if (displayName === c.code || isGarbled(displayName)) {
      const cachedName = store.naverNames && store.naverNames[c.code];
      if (cachedName && cachedName !== c.code && !isGarbled(cachedName)) {
        displayName = cachedName;
      } else {
        try {
          const nr = await http({
            method: 'GET',
            url: 'https://m.stock.naver.com/api/stock/' + c.code + '/basic',
            json: true,
            headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.naver.com/', 'Accept-Language': 'ko-KR,ko;q=0.9' },
          });
          const nm = nr && (nr.stockName || nr.itemName || nr.name || nr.symbolName);
          if (nm && nm !== c.code && !isGarbled(nm)) {
            displayName = nm;
            if (!store.naverNames) store.naverNames = {};
            store.naverNames[c.code] = nm;
          }
        } catch (e) {}
      }
    }
    // 모든 복구 시도 실패 시 코드 번호로 대체 (깨진 이름 대신 코드가 표시되는 것이 낫다)
    if (isGarbled(displayName)) displayName = c.code;

    const dailyChangeText = Number.isFinite(c.dailyChange) ? ' (전일 대비 ' + pct(c.dailyChange) + ')' : '';

    const gradePrefix = (c.grade === '강매')     ? '[★강매] '
                      : (c.grade === '급등')     ? '[🚀급등] '
                      : (c.grade === '매도차익') ? '[⚡단기] '
                      : (c.grade === '관심')     ? '[관심] '
                      : '';
    const target1Line = Number.isFinite(c.target1)
      ? '- 1차 목표: ' + to0(c.target1) + '원 (+' + pct(c.target1 / c.entry - 1) + ')' + NL
      : '';
    const msg =
      gradePrefix + '[스윙 포착] ' + c.market + ' | ' + displayName + '(' + c.code + ')' + NL +
      '등급: ' + (c.grade || '매수') + NL +
      '기준가: ' + to0(c.entry) + '원' + dailyChangeText + NL +
      '- 매수가: ' + to0(c.entry) + '원 (전일종가 기준, 시초가 확인 필수)' + NL +
      target1Line +
      '- 최종 목표: ' + to0(c.target) + '원 (+' + pct(c.target / c.entry - 1) + ')' + NL +
      '- 손절가: ' + to0(c.stop) + '원 (-' + pct(1 - c.stop / c.entry) + ')' + NL +
      'ATR(14): ' + (Number.isFinite(c.atrAbs) ? (to0(c.atrAbs) + '원') : 'N/A') + NL +
      '- 점수: ' + c.score + '점' + NL +
      '핵심 시그널: ' + (c.signals.slice(0, 3).join(', ') || 'N/A');

    try {
      await http({
        method: 'POST',
        url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
        json: true,
        body: { chat_id: CHAT, text: msg },
      });
      return { entry: c.entry, target: c.target, target1: c.target1, stop: c.stop, resolvedName: displayName };
    } catch (e) {
      sendFailCount++;
      if (sendFailSamples.length < 3) sendFailSamples.push({ ticker: c.ticker, message: String(e?.message || e) });
      return null;
    }
  };

  for (let i = 0; i < selected.length; i++) {
    const res = await send(selected[i]);
    if (res) {
      store.swingSent[selected[i].ticker] = now.getTime();

      const today2 = `${kst.getUTCFullYear()}-${String(kst.getUTCMonth() + 1).padStart(2, '0')}-${String(kst.getUTCDate()).padStart(2, '0')}`;
      if (!store.weeklyRecommendations) store.weeklyRecommendations = {};
      if (!store.weeklyRecommendations[today2]) store.weeklyRecommendations[today2] = [];

      // 보유 기간 동적 계산 (단기화: 강매→5일, 급등→2일, 매도차익→2일)
      const holdDays = (selected[i].grade === '강매')     ? HOLD_STRONG     // 5거래일
                     : (selected[i].grade === '급등')     ? HOLD_SURGE      // 2거래일
                     : (selected[i].grade === '매도차익') ? HOLD_SHORTTRADE // 2거래일
                     : HOLD_WEAK;

      store.weeklyRecommendations[today2].push({
        type: 'swing', subType: selected[i].type,
        ticker: selected[i].ticker, code: selected[i].code, name: res.resolvedName || selected[i].name,
        entry: res.entry, target: res.target, target1: res.target1, stop: res.stop,
        atrAbs: selected[i].atrAbs,
        holdingDays: holdDays, score: selected[i].score, grade: selected[i].grade,
      });

      sent.push(selected[i].ticker);
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  if (sendFailCount > 0) {
    if (!store.telegramAlerts) store.telegramAlerts = {};
    const last = Number(store.telegramAlerts.swingSendFailAt || 0);
    const nowMs3 = Date.now();
    if (nowMs3 - last > 30 * 60 * 1000) {
      const sample = (sendFailSamples && sendFailSamples.length) ? JSON.stringify(sendFailSamples.slice(0, 2)) : 'none';
      const msg = '⚠️ [발송 오류] 스윙 알림 전송 실패' + NL +
        `- KST: ${today} ${timeStrNow}` + NL +
        `- failCount: ${sendFailCount}` + NL +
        `- sample: ${sample}`;
      try { await http({ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage', json: true, body: { chat_id: CHAT, text: msg } }); } catch (e) {}
      store.telegramAlerts.swingSendFailAt = nowMs3;
    }
  }

  if (selected.length === 0) {
    if (!store.swingAlerts) store.swingAlerts = {};
    if (store.swingAlerts.noHitDate === today) return [{ json: { skipped: true, reason: 'No hit (already notified today)' } }];
    const msg =
      '[스윙 스캔 완료] 추천 종목 없음' + NL +
      '- 분석 종목(필터 후): ' + ALL_TICKERS.length + '개' + NL +
      '- 후보: ' + candidates.length + '개' + NL +
      '- 제외(리스크): ' + excludedRisk + '개' + NL +
      '- 제외(테마): ' + excludedTheme + '개' + NL +
      '- Naver OK/NoResult/Error: ' + naverOkCount + '/' + naverNoResultCount + '/' + naverErrorCount + NL +
      '- KST: ' + today + ' ' + timeStrNow;
    try {
      await http({ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage', json: true, body: { chat_id: CHAT, text: msg } });
    } catch (e) {}
    store.swingAlerts.noHitDate = today;
  }

  store.swingMeta._lastFullFinish = Date.now();
  return [{
    json: {
      scanTime: kst.toISOString(),
      totalUniverse: ALL_TICKERS.length,
      candidates: candidates.length,
      sent: sent.length,
      sentTickers: sent,
      excludedRisk, excludedTheme,
      riskCacheAt, themeCacheAt,
      naverOkCount, naverNoResultCount, naverErrorCount,
      naverErrorByStatus, naverErrorSamples,
    },
  }];
};

return run();

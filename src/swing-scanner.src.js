const { HOLIDAYS } = require('../lib/holidays');
const { to0, sleep } = require('../lib/format');
const { createTelegram } = require('../lib/telegramClient');
const { createTossClient } = require('../lib/tossClient');
const run = async function () {
  const BOT = '8366696724:AAHROcjGoQEn9BziD-sYdAu3ZuaolwtkgLE';
  const CHAT = '523002062';
  const MIN_INTRADAY_TURNOVER = 3000000000; // 30억 KRW
  const MIN_PRICE = 1000;                   // 최소 주가 (프레임워크 — KRX API 필터)
  const ETF_EXCLUDE_KEYWORDS = [            // ETF/펀드/리츠 제외 키워드 (2026-07-01)
    'KODEX','TIGER','KBSTAR','HANARO','ACE','ARIRANG','SOL','TIMEFOLIO','KOSEF',
    '리츠','펀드',
  ];
  const DUPLICATE_WINDOW_MINUTES = 480;
  const DART_API_KEY = '34a9b090d2a7b1ee689a240fef68667d36b389e7';
  const ALERT_START_HOUR   = 9;
  const ALERT_START_MINUTE = 0;
  const STOP_NEW_ALERTS_HOUR = 13;    // 전체 종료 (A/B/D 패턴)
  const STOP_NEW_ALERTS_MINUTE = 0;
  const STOP_C_HOUR = 11;             // 패턴C(촉매) 전용 종료 시각
  const STOP_C_MINUTE = 30;           // 패턴C는 11:30 이후 추격 위험
  const MAX_STOCK_PER_SEND   = 3;    // 1회 최대 발송 종목 수

  const INTRADAY_STOP_THRESH = 2;    // 당일 손절 카운터: 2회 이상 손절 시 당일 신규 발송 억제
  const MAX_SCAN_RUNTIME_MS = 20 * 60 * 1000; // 실행 중 락 최대 유지 시간(비정상 종료 시 락 고착 방지용 자동 해제)
  // getMarketRegime 함수용 상수 (초기화 — 새 조건에서 regime 사용 시 재정의)
  const REGIME_SMA_FAST    = 5;
  const REGIME_YEST_DOWN   = -0.015;
  const REGIME_GAP_DOWN    = -0.007;
  const NASDAQ_DOWN_THRESH = -0.01;
  const SP500_DOWN_THRESH  = -0.007;
  const VIX_HIGH_THRESH    = 25;

  // ===== 진입 신호 상수 — 30종목 복기 기반 v1.0 =====
  const MIN_SCORE_FINAL        = 90; // 60-89 구간이 유일한 순손실 구간으로 확인돼(-0.69%/trade, n=40) 상향 (docs/03-analysis/swing-algorithm-profitability-review.analysis.md #5)
  const MIN_TURNOVER_ALGO      = 5_000_000_000;
  const SCORE_STRONG_FINAL     = 110;
  const MIN_RR_RATIO_FINAL     = 1.5;
  const PA_VOL_MULT     = 3.0;
  const PA_PRICE_MOVE   = 0.05;
  const PA_DAYS_MIN     = 1;
  const PA_DAYS_MAX     = 10;
  const PA_PULLBACK_MAX = 0.15;
  const PA_PULLBACK_MIN = 0.03;
  const PB_CORR_MIN   = 0.20;
  const PB_CORR_MAX   = 0.50;
  const PB_LEVEL_PROX = 0.08;
  const PC_VOL_MULT   = 5.0;
  const PC_PRICE_MIN  = 0.05;
  const PC_STR_MIN    = 0.50;
  const PD_VOL_MULT   = 2.5;
  const PD_BREAK_MIN  = 0.02;
  const PD_DAYS       = 25;
  // ===== /진입 신호 상수 =====

  // ===== Logger initialization (Zero Script QA) =====
  // n8n Function 노드 샌드박스에서 로컬 파일 require 불가 → try/catch로 안전 처리
  // 로컬 환경(개발/테스트)에서는 lib/logger.js 사용, n8n 실행 시 no-op fallback
  let logger;
  try {
    const JsonLogger = require('./lib/logger');
    logger = new JsonLogger('swing_scanner');
  } catch (e) {
    logger = { info:()=>{}, error:()=>{}, warning:()=>{}, debug:()=>{}, generateRequestId:(p)=>`${p}_${Date.now()}` };
  }
  const requestId = logger.generateRequestId('SCAN');
  logger.info('Swing scanner started', { phase: 'initialization' }, requestId);

  const http = async (o) => await this.helpers.httpRequest(Object.assign({ timeout: 45000 }, o));
  const telegram = createTelegram(http, BOT, CHAT);

  // ===== TODO: 종목 분류 헬퍼 =====
  // 필요한 경우 여기에 새 헬퍼 함수를 추가하세요.
  // ===== /TODO =====

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

  // [REGIME-OPT3] KOSPI/KOSDAQ OHLC 반환 — 당일 갭 감지용 (2026-05-02)
  // [BUGFIX-2026-05-07] Naver fchart 지수 미반환 시 Yahoo Finance fallback 추가
  const fetchDailyOHLC = async (encodedTicker) => {
    try {
      const symbolMap = { '%5EKS11': 'KOSPI', '%5EKQ11': 'KOSDAQ' };
      const symbol = symbolMap[encodedTicker] || encodedTicker;
      let raw = await fetchDailyFchart(symbol, 120);

      // Fallback: Naver fchart이 지수 OHLC를 반환하지 못할 경우 Yahoo Finance 사용
      if (!raw || !raw.length) {
        try {
          const yUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${encodedTicker}?interval=1d&range=6mo`;
          const yResp = await http({
            method: 'GET', url: yUrl, json: true,
            headers: { 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json' },
          });
          const yResult = yResp?.chart?.result?.[0];
          if (yResult) {
            const timestamps = yResult.timestamp || [];
            const q = yResult.indicators?.quote?.[0] || {};
            raw = timestamps.map((ts, i) => ({
              localDate: new Date(ts * 1000).toISOString().slice(0, 10).replace(/-/g, ''),
              openPrice:  Number((q.open   || [])[i]) || 0,
              highPrice:  Number((q.high   || [])[i]) || 0,
              lowPrice:   Number((q.low    || [])[i]) || 0,
              closePrice: Number((q.close  || [])[i]) || 0,
              accumulatedTradingVolume: Number((q.volume || [])[i]) || 0,
            })).filter(r => r.closePrice > 0 && /^\d{8}$/.test(r.localDate));
          }
        } catch(_) { /* Yahoo fallback 실패 → 빈 배열 반환 */ }
      }

      if (!raw || !raw.length) return [];
      return raw.map(d => ({
        date:  d.localDate,
        open:  d.openPrice  > 0 ? d.openPrice  : d.closePrice,
        high:  d.highPrice  > 0 ? d.highPrice  : d.closePrice,
        low:   d.lowPrice   > 0 ? d.lowPrice   : d.closePrice,
        close: d.closePrice,
      }));
    } catch(e) { return []; }
  };

  // [MACRO-A] 나스닥 전일 수익률 + VIX + S&P500선물 조회 (Yahoo Finance, 당일 1회 캐싱, 2026-05-17)
  const fetchMacroIndicators = async (store, todayStr) => {
    if (store.macroCache && store.macroCache.date === todayStr) return store.macroCache;
    let nasdaqChg = null, vixLevel = null, esFutChg = null;
    try {
      const [nasdaqResp, vixResp, esFutResp] = await Promise.all([
        http({ method: 'GET', url: 'https://query1.finance.yahoo.com/v8/finance/chart/%5EIXIC?interval=1d&range=5d', json: true, headers: { 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json' } }),
        http({ method: 'GET', url: 'https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=5d',  json: true, headers: { 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json' } }),
        // S&P500 E-mini 선물: 5분봉으로 실시간 레벨 조회 (09:00 KST 한국장 개장 전 야간선물 반영)
        http({ method: 'GET', url: 'https://query1.finance.yahoo.com/v8/finance/chart/ES%3DF?interval=5m&range=1d',  json: true, headers: { 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json' } }),
      ]);
      const nasdaqCloses = (nasdaqResp?.chart?.result?.[0]?.indicators?.quote?.[0]?.close || []).filter(v => Number.isFinite(v));
      if (nasdaqCloses.length >= 2) nasdaqChg = nasdaqCloses[nasdaqCloses.length - 1] / nasdaqCloses[nasdaqCloses.length - 2] - 1;
      const vixCloses = (vixResp?.chart?.result?.[0]?.indicators?.quote?.[0]?.close || []).filter(v => Number.isFinite(v));
      if (vixCloses.length >= 1) vixLevel = vixCloses[vixCloses.length - 1];
      // ES=F: 현재 선물 가격 vs 전일 종가(chartPreviousClose) → 야간 변화율 계산
      const esPrevClose = esFutResp?.chart?.result?.[0]?.meta?.chartPreviousClose;
      const esCloses    = (esFutResp?.chart?.result?.[0]?.indicators?.quote?.[0]?.close || []).filter(v => Number.isFinite(v));
      if (Number.isFinite(esPrevClose) && esPrevClose > 0 && esCloses.length > 0) {
        esFutChg = esCloses[esCloses.length - 1] / esPrevClose - 1;
      }
    } catch (e) { /* 매크로 데이터 로드 실패 → null 유지, 차단 없이 통과 */ }
    const result = { date: todayStr, nasdaqChg, vixLevel, esFutChg };
    store.macroCache = result;
    return result;
  };

  // [DATA-FIX] 예상 전거래일 계산 — 데이터 신선도 검증용 (2026-06-03)
  const getPrevTradingDay = (todayStr) => {
    let d = new Date(todayStr + 'T00:00:00Z');
    for (let i = 0; i < 10; i++) {
      d = new Date(d.getTime() - 86400000);
      const ds = d.toISOString().slice(0, 10);
      if (d.getUTCDay() >= 1 && d.getUTCDay() <= 5 && !HOLIDAYS.includes(ds))
        return ds.replace(/-/g, ''); // 'YYYYMMDD'
    }
    return null;
  };

  // [REGIME-OPT3] 3단계 Regime + 당일 갭 감지 (2026-05-02 개선)
  // [DATA-FIX] 전거래일 기준 갭 계산 + KOSPI/KOSDAQ 독립 레짐 (2026-06-03)
  // regimeLevel: 0=강세(전 등급 허용), 1=중립(매도차익 차단), 2=약세(강매 전용)
  const getMarketRegime = async (store, today) => {
    if (!store.regimeCache) store.regimeCache = {};
    if (store.regimeCache.date === today && store.regimeCache.regimeLevel !== undefined)
      return store.regimeCache;

    let ksRegimeLevel = 0, kqRegimeLevel = 0;
    let ks = null, kq = null, ksUpFast = null, kqUpFast = null;
    let ksGap = 0, kqGap = 0, ksGapSource = 'none', kqGapSource = 'none';
    let ksDataFresh = true, kqDataFresh = true;

    try {
      const [ksOHLC, kqOHLC] = await Promise.all([
        fetchDailyOHLC('%5EKS11'),
        fetchDailyOHLC('%5EKQ11'),
      ]);
      if (!ksOHLC.length || !kqOHLC.length) throw new Error('empty OHLC');

      const iKs = ksOHLC.length - 1;
      const iKq = kqOHLC.length - 1;
      const ksClose = ksOHLC.map(d => d.close);
      const kqClose = kqOHLC.map(d => d.close);

      // SMA20 vs SMA60 (중장기 추세)
      const ks20 = sma(ksClose, 20); const ks60 = sma(ksClose, 60);
      const kq20 = sma(kqClose, 20); const kq60 = sma(kqClose, 60);
      ks = (Number.isFinite(ks20[iKs]) && Number.isFinite(ks60[iKs]))
           ? ks20[iKs] > ks60[iKs] : null;
      kq = (Number.isFinite(kq20[iKq]) && Number.isFinite(kq60[iKq]))
           ? kq20[iKq] > kq60[iKq] : null;

      // SMA5 vs SMA20 (단기 모멘텀 — 회복 중 흔들림 감지)
      const ks5 = sma(ksClose, REGIME_SMA_FAST);
      const kq5 = sma(kqClose, REGIME_SMA_FAST);
      ksUpFast = Number.isFinite(ks5[iKs]) ? ks5[iKs] > ks20[iKs] : null;
      kqUpFast = Number.isFinite(kq5[iKq]) ? kq5[iKq] > kq20[iKq] : null;

      // [DATA-FIX] 갭 계산: 예상 전거래일 기준으로 데이터 신선도 검증 (2026-06-03)
      const todayStr = today.replace(/-/g, '');
      const expectedPrev = getPrevTradingDay(today); // 예: '20260601' (today='2026-06-02'일 때)

      const calcIndexGap = (ohlc, iLast) => {
        const lastDate = ohlc[iLast]?.date;
        if (lastDate === todayStr && iLast >= 1) {
          // 장 중: 당일 시가 vs 전일 종가
          const g = ohlc[iLast-1].close > 0 ? (ohlc[iLast].open / ohlc[iLast-1].close - 1) : 0;
          return { gap: g, source: 'today', fresh: true };
        }
        if (expectedPrev) {
          const idx = ohlc.findIndex(d => d.date === expectedPrev);
          if (idx >= 1) {
            // 장 전: 예상 전거래일 데이터 정상 확인
            const g = ohlc[idx-1].close > 0 ? (ohlc[idx].close / ohlc[idx-1].close - 1) : 0;
            return { gap: g, source: 'yesterday', fresh: true };
          }
          // 데이터 지연: 기대한 전거래일이 OHLC에 없음 → stale 표시
          if (iLast >= 1) {
            const g = ohlc[iLast-1].close > 0 ? (ohlc[iLast].close / ohlc[iLast-1].close - 1) : 0;
            return { gap: g, source: 'stale(' + lastDate + ')', fresh: false };
          }
        }
        if (iLast >= 1) {
          const g = ohlc[iLast-1].close > 0 ? (ohlc[iLast].close / ohlc[iLast-1].close - 1) : 0;
          return { gap: g, source: 'yesterday', fresh: true };
        }
        return { gap: 0, source: 'none', fresh: false };
      };

      const ksGapR = calcIndexGap(ksOHLC, iKs);
      const kqGapR = calcIndexGap(kqOHLC, iKq);
      ksGap = ksGapR.gap; ksGapSource = ksGapR.source; ksDataFresh = ksGapR.fresh;
      kqGap = kqGapR.gap; kqGapSource = kqGapR.source; kqDataFresh = kqGapR.fresh;

      // ── KOSPI 레짐 독립 판정 ──
      if (ks === false) {
        ksRegimeLevel = 2;
      } else if (ksUpFast === false) {
        ksRegimeLevel = 1;
      }
      const ksThresh = ksGapR.source === 'today' ? REGIME_GAP_DOWN : REGIME_YEST_DOWN;
      if (ksGap < ksThresh) ksRegimeLevel = Math.max(ksRegimeLevel, 2);

      // ── KOSDAQ 레짐 독립 판정 ──
      if (kq === false) {
        kqRegimeLevel = 2;
      } else if (kqUpFast === false) {
        kqRegimeLevel = 1;
      }
      const kqThresh = kqGapR.source === 'today' ? REGIME_GAP_DOWN : REGIME_YEST_DOWN;
      if (kqGap < kqThresh) kqRegimeLevel = Math.max(kqRegimeLevel, 2);

    } catch (e) {
      ksRegimeLevel = 0; kqRegimeLevel = 0; // 데이터 오류 시 차단 없이 통과 (보수적 fallback)
    }

    // ── [MACRO-A] 매크로 지표: 나스닥 + VIX + S&P500선물 — KOSPI/KOSDAQ 동일 적용 (2026-05-17) ──
    let nasdaqChg = null, vixLevel = null, esFutChg = null, macroAdj = 0;
    try {
      const macro = await fetchMacroIndicators(store, today);
      nasdaqChg = macro.nasdaqChg;
      vixLevel  = macro.vixLevel;
      esFutChg  = macro.esFutChg;
      const extMarketBear = (Number.isFinite(nasdaqChg) && nasdaqChg < NASDAQ_DOWN_THRESH) ||
                            (Number.isFinite(esFutChg)  && esFutChg  < SP500_DOWN_THRESH);
      if (extMarketBear)                                             macroAdj++;
      if (Number.isFinite(vixLevel) && vixLevel > VIX_HIGH_THRESH)  macroAdj++;
      ksRegimeLevel = Math.min(2, ksRegimeLevel + macroAdj);
      kqRegimeLevel = Math.min(2, kqRegimeLevel + macroAdj);
    } catch (e) { /* 매크로 적용 실패 → 기존 regimeLevel 유지 */ }
    // ── /MACRO-A ──

    const regimeLevel = Math.max(ksRegimeLevel, kqRegimeLevel); // 전체 레짐 (하위 호환)
    const riskOn = regimeLevel < 2;
    store.regimeCache = {
      date: today, riskOn, regimeLevel,
      ksRegimeLevel, kqRegimeLevel,
      ksUp: ks, kqUp: kq, ksUpFast, kqUpFast,
      ksGap: (ksGap * 100).toFixed(2) + '%',
      kqGap: (kqGap * 100).toFixed(2) + '%',
      ksGapSource, kqGapSource,
      ksDataFresh, kqDataFresh,
      nasdaqChg: Number.isFinite(nasdaqChg) ? (nasdaqChg * 100).toFixed(2) + '%' : 'N/A',
      vixLevel:  Number.isFinite(vixLevel)  ? vixLevel.toFixed(1)              : 'N/A',
      esFutChg:  Number.isFinite(esFutChg)  ? (esFutChg * 100).toFixed(2) + '%' : 'N/A',
      macroAdj,
      at: new Date().toISOString(),
    };
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
      const res = await telegram.send(msg);
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
    try { await telegram.send('⚠️ [설정 필요] HOLIDAYS 배열이 2026년까지만 등록되어 있습니다. swing_scanner_code.js 상단 HOLIDAYS 상수에 2027년 공휴일을 추가해주세요.'); } catch(e) {}
  }

  if (h < ALERT_START_HOUR || (h === ALERT_START_HOUR && m < ALERT_START_MINUTE)) {
    return [{ json: { skipped: true, reason: 'Before alert start time (before 09:00 KST)' } }];
  }

  if (h > STOP_NEW_ALERTS_HOUR || (h === STOP_NEW_ALERTS_HOUR && m >= STOP_NEW_ALERTS_MINUTE)) {
    return [{ json: { skipped: true, reason: 'Too close to market close' } }];
  }
  if (h >= 16) return [{ json: { skipped: true, reason: 'After market close' } }];

  // store는 Line 333에서 이미 선언됨 (forceTest 이전)
  if (!store.swingMeta) store.swingMeta = {};
  store.swingMeta.lastRunAt = now.toISOString();
  store.swingMeta.lastRunDate = today;

  // [NODUP-3] 실행 중 락 — 이전 스캔이 아직 끝나지 않았으면 새 트리거를 스킵한다.
  // 근본 원인: 1분 간격 cron인데 실제 스캔은 Naver rate-limit 때문에 수 분~9분+ 걸려
  // 겹쳐 실행되고, 그 사이 동일 종목이 두 실행에서 각각 발송돼 중복 알림이 발생했다.
  // 기존 _lastFullFinish(완료 후 90초 차단)는 "실행 중"이 아니라 "완료 시각"만 봐서
  // 진행 중인 겹침 실행을 막지 못했다. _runningSince로 진행 중 여부를 직접 추적하고,
  // MAX_SCAN_RUNTIME_MS를 넘기면 락이 고착된 것으로 보고 자동 해제한다.
  //
  // [NODUP-3-FIX] 락 해제는 반드시 이 함수의 모든 return 경로에서 이루어져야 한다 —
  // 락 획득(아래) 이후에도 위클리 한도/KRX 유니버스 로드 실패/오늘 히트 없음 등 정상적인
  // 조기 종료 경로가 있는데, 그 경로들이 락을 풀지 않으면 다음 트리거가 최대
  // MAX_SCAN_RUNTIME_MS(20분)까지 "Previous scan still running"으로 계속 막히고,
  // _lastFullFinish도 갱신되지 않아 Backup Watchdog이 "정상 실행 안 됨"으로 오탐한다.
  if (store.swingMeta._runningSince && (Date.now() - store.swingMeta._runningSince) < MAX_SCAN_RUNTIME_MS) {
    return [{ json: { skipped: true, reason: 'Previous scan still running' } }];
  }
  store.swingMeta._runningSince = Date.now();

  if (!store.swingSent) store.swingSent = {};
  if (!store.weeklyRecommendations) store.weeklyRecommendations = {};
  // [NODUP-2] 당일 발송 Set — 날짜 기반 완전 차단 (레이스 컨디션 방어)
  if (!store.swingSentToday) store.swingSentToday = {};
  const cutoffDate = new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000);
  const cutoffStr = `${cutoffDate.getFullYear()}-${String(cutoffDate.getMonth()+1).padStart(2,'0')}-${String(cutoffDate.getDate()).padStart(2,'0')}`;
  for (const dateKey in store.weeklyRecommendations) {
    if (dateKey < cutoffStr) delete store.weeklyRecommendations[dateKey];
  }
  for (const dateKey in store.swingSentToday) {
    if (dateKey < cutoffStr) delete store.swingSentToday[dateKey];
  }
  if (!store.swingSentToday[today]) store.swingSentToday[today] = [];
  if (!store.weeklyRecommendations[today]) store.weeklyRecommendations[today] = [];

  // [NOREBUY] 이미 보유 중인(만료 안 된) 종목은 재매수 후보에서 제외
  // — daily-position-monitor.src.js와 동일한 만료 판정(holdingDays*1.4일)을 재사용해
  //   "보유기간 넘어 다음주까지 들고 있는" 종목도 계속 제외 대상으로 잡는다.
  const heldCodes = new Set();
  for (const dateKey in store.weeklyRecommendations) {
    for (const rec of (store.weeklyRecommendations[dateKey] || [])) {
      if (rec.type !== 'swing') continue;
      const holdDays = rec.holdingDays || 3;
      const entryDate = new Date(rec.date || dateKey);
      const expiry = new Date(entryDate.getTime() + holdDays * 1.4 * 24 * 60 * 60 * 1000);
      if (expiry < now) continue;
      heldCodes.add(String(rec.code));
    }
  }

  // ===== [TOSS-CONFIRM] 임계값 튜닝용 상세 로그 저장소 (2026-07-14) =====
  // tossConfirm() 평가마다 원본 지표·임계값·API 성공여부까지 기록 — 실거래 운영 중
  // 스킵 사유/비율 분포를 나중에 분석해 TOSS_ASK_BID_BLOCK_RATIO, TOSS_WEAK_BUY_RATIO_C 튜닝
  if (!store.tossConfirmLog) store.tossConfirmLog = {};
  for (const dateKey in store.tossConfirmLog) {
    if (dateKey < cutoffStr) delete store.tossConfirmLog[dateKey];
  }
  if (!store.tossConfirmLog[today]) store.tossConfirmLog[today] = [];

  // ===== [SCAN-LOG] 상세 스캔 로그 초기화 (2026-05-17) =====
  if (!store.scanLog) store.scanLog = [];
  const _log = {
    runId: requestId,
    date: today, startKst: timeStrNow, startAt: now.toISOString(),
    regime: {}, macro: {},
    rejected: { regime: 0, surge: 0, rr: 0, score: 0, duplicate: 0, weekly: 0, other: 0 },
    topCandidates: [], sent: [], stats: {},
    finishedAt: null,
  };
  // ===== /SCAN-LOG 초기화 =====

  const cleanOldHistory = () => {
    const cutoff = now.getTime() - DUPLICATE_WINDOW_MINUTES * 60 * 1000;
    for (const ticker in store.swingSent) {
      if (store.swingSent[ticker] < cutoff) delete store.swingSent[ticker];
    }
  };
  cleanOldHistory();

  const bl = store.blacklist || {};
  const riskSet = new Set((bl.riskCodes || []).map(String));
  const themeFilterMode = String(bl.themeFilterMode || 'on').toLowerCase(); // 2026-04-19: 기본값 'on' 활성화
  const themeSet = (themeFilterMode === 'off') ? new Set() : new Set((bl.themeCodes || []).map(String));
  let excludedRisk = 0;
  let excludedTheme = 0;
  const riskCacheAt = bl.riskUpdatedAt || null;
  const themeCacheAt = bl.themeUpdatedAt || null;

  // [REMOVED 2026-08-22] 외국인/기관 순매수 + 프로그램 매매 방향 로딩(KRX MDCSTAT02023/05401)을
  // 여기서 시도했었으나, data.krx.co.kr가 이 서버에서 항상 실패해(라이브 staticData 확인 결과
  // supplyCache/programCache가 한 번도 채워진 적 없음) 관련 필터·점수보너스·경고문구가 전부
  // no-op였고, 캐싱 조건도 절대 만족 못 해서 스캔마다(하루 ~15회) 실패할 API를 계속 재호출만
  // 하고 있었다. 대체 데이터 소스 없이는 복구 불가 판단 — 죽은 코드 제거.
  const supCacheKey = today.replace(/-/g, '');

  // ===== 당일 공시 목록 로딩 (DART OpenAPI, 당일 1회 캐싱) =====
  let dartToday = {};
  if (store.dartCache && store.dartCache.trdDd === supCacheKey) {
    dartToday = store.dartCache.map || {};
  } else if (DART_API_KEY) {
    try {
      const dartUrl = `https://opendart.fss.or.kr/api/list.json?crtfc_key=${DART_API_KEY}&bgn_de=${supCacheKey}&end_de=${supCacheKey}&page_no=1&page_count=100`;
      const dartR = await http({ method: 'GET', url: dartUrl, json: true });
      const dartList = (dartR && dartR.list) || [];
      for (const item of dartList) {
        const sc = String(item.stock_code || '').trim();
        if (!sc) continue;
        if (!dartToday[sc]) dartToday[sc] = [];
        dartToday[sc].push(String(item.report_nm || '').slice(0, 40));
      }
      store.dartCache = { trdDd: supCacheKey, map: dartToday };
    } catch (e) { /* DART 로딩 실패 → 공시 필터 스킵 */ }
  }
  // ===== /당일 공시 목록 로딩 =====

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
        const krxRows = (r && (r.output || r.OutBlock_1 || [])) || [];
        if (krxRows.length > 0) {
          rows = krxRows;
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
          const url = `https://finance.naver.com/sise/sise_quant.naver?sosok=${sosok}&page=${p}`;
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
    // [ETF-1] KRX MKT_NM 기반 ETF/ETN/ELW 시장 제외 (2026-07-01)
    if (mkt.includes('etf') || mkt.includes('etn') || mkt.includes('elw')) continue;

    const price = Number((row.TDD_CLSPRC || '0').replace(/,/g, ''));
    const turnover = Number((row.ACC_TRDVAL || '0').replace(/,/g, ''));

    if (!rc || !nm) continue;
    if (SEEN_CODES.has(rc)) continue;
    SEEN_CODES.add(rc);

    if (riskSet.has(rc)) { excludedRisk++; continue; }
    if (themeSet.has(rc)) { excludedTheme++; continue; }

    // [ETF-2] ETF 브랜드명·펀드·리츠 제외 (2026-07-01, 전 종목 적용)
    if (ETF_EXCLUDE_KEYWORDS.some(kw => nm.includes(kw))) continue;

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
      await telegram.send(msg);
    } catch (e) {}
    store.swingMeta._runningSince = null; // [NODUP-3-FIX] 조기 종료 경로도 락 해제
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
  const getNaverPrevDay = () => {
    let d = new Date(Date.now() + 9 * 3600000 - 24 * 3600000);
    for (let i = 0; i < 10; i++) {
      const dow = d.getUTCDay();
      const ds = d.toISOString().slice(0, 10);
      if (dow >= 1 && dow <= 5 && !HOLIDAYS.includes(ds)) return ds.replace(/-/g, '');
      d = new Date(d.getTime() - 24 * 3600000);
    }
    return new Date(Date.now() + 9 * 3600000 - 24 * 3600000).toISOString().slice(0, 10).replace(/-/g, '');
  };
  const prevTradingDay = getNaverPrevDay(); // e.g. '20260226'

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
        if (store.swingSent[t]) { _log.rejected.duplicate++; return; }
        // [NODUP-2] 당일 발송 Set 체크 — 동시 실행 레이스 컨디션 방어
        const _rc = t.replace(/\.(KS|KQ)$/, '');
        if (store.swingSentToday[today] && store.swingSentToday[today].includes(_rc)) { _log.rejected.duplicate++; return; }
        // [NOREBUY] 이미 보유 중인 종목은 재매수 후보에서 제외
        if (heldCodes.has(_rc)) { _log.rejected.duplicate++; return; }

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

        // ===== 알고리즘: 30종목 복기 기반 진입 신호 v1.0 =====

        // ---- 사전 지표 계산 ----
        const sma20_d = sma(closeD, 20);
        const sma60_d = sma(closeD, 60);
        const vol20Avg = volD.slice(Math.max(0, dIdx - 20), dIdx).reduce((a, b) => a + b, 0) / Math.min(20, dIdx);
        const rvolVal  = vol20Avg > 0 ? volD[dIdx] / vol20Avg : 0;
        const rsi14Val = calcRSI14(closeD, dIdx);
        const adxResult = calcADX(highD, lowD, closeD, dIdx, 14);
        const high252   = Math.max(...highD.slice(Math.max(0, dIdx - 252), dIdx + 1).map(Number));
        const low252    = Math.min(...lowD.slice(Math.max(0, dIdx - 252), dIdx + 1).map(Number));
        const pth            = high252 > 0 ? currentPrice / high252 : 0;
        const priceFromLow   = low252  > 0 ? (currentPrice / low252 - 1) : 0;
        const dayRange       = highD[dIdx] - lowD[dIdx];
        const intradayStrength = dayRange > 0 ? (closeD[dIdx] - openD[dIdx]) / dayRange : 0;
        const macdResult = calcMACD(closeD, dIdx);
        const obvResult  = calcOBV(closeD, volD, dIdx);
        const supCode = normalize(getCode(t));
        const dartItems = dartToday[supCode] || [];

        // ---- [F] 기초 필터 ----
        if (currentPrice * (volD[dIdx] || 0) < MIN_TURNOVER_ALGO) return;
        if (rvolVal < 1.0) return;
        if (Number.isFinite(rsi14Val) && rsi14Val < 40) return;
        if (dartItems.length > 0 && /소송|횡령|배임|감사의견|불성실|조회/.test(dartItems.join(' '))) return;

        // ---- [P] 패턴 감지 변수 ----
        let eventIdx = dIdx;
        for (let vi = Math.max(0, dIdx - 15); vi <= dIdx; vi++) {
          if (volD[vi] > volD[eventIdx]) eventIdx = vi;
        }
        const eventVolMult   = vol20Avg > 0 ? volD[eventIdx] / vol20Avg : 0;
        const eventDaysAgo   = dIdx - eventIdx;
        const eventDayChange = (eventIdx > 0 && closeD[eventIdx - 1] > 0)
                               ? (closeD[eventIdx] / closeD[eventIdx - 1] - 1) : 0;
        const eventHighSince = eventIdx <= dIdx
                               ? Math.max(...highD.slice(eventIdx, dIdx + 1)) : currentPrice;
        const pullbackFromEvent = eventHighSince > 0 ? (currentPrice / eventHighSince - 1) : 0;

        const high60    = Math.max(...highD.slice(Math.max(0, dIdx - 60), dIdx + 1));
        const corrPct60 = high60 > 0 ? (currentPrice / high60 - 1) : 0;

        const pastSlice    = closeD.slice(Math.max(0, dIdx - 50), Math.max(1, dIdx - 20));
        const pastAvgPrice = pastSlice.length > 0
                             ? pastSlice.reduce((a, b) => a + b, 0) / pastSlice.length : 0;
        const proxToPast   = pastAvgPrice > 0 ? Math.abs(currentPrice / pastAvgPrice - 1) : 1;

        const box25High = Math.max(...highD.slice(Math.max(0, dIdx - PD_DAYS), dIdx));

        const isPatternA = (
          eventVolMult   >= PA_VOL_MULT    &&
          eventDayChange >= PA_PRICE_MOVE  &&
          eventDaysAgo   >= PA_DAYS_MIN    &&
          eventDaysAgo   <= PA_DAYS_MAX    &&
          pullbackFromEvent <= -PA_PULLBACK_MIN &&
          pullbackFromEvent >= -PA_PULLBACK_MAX &&
          rvolVal >= 1.2 &&
          dailyChange >= -0.03
        );
        const isPatternB = (
          corrPct60 <= -PB_CORR_MIN  &&
          corrPct60 >= -PB_CORR_MAX  &&
          proxToPast <= PB_LEVEL_PROX &&
          dailyChange >= 0.0         &&
          rvolVal >= 1.5             &&
          Number.isFinite(rsi14Val) && rsi14Val >= 40 && rsi14Val <= 72
        );
        const isPatternC = (
          rvolVal      >= PC_VOL_MULT  &&
          dailyChange  >= PC_PRICE_MIN &&
          intradayStrength >= PC_STR_MIN &&
          Number.isFinite(rsi14Val) && rsi14Val <= 82
        );
        const isPatternD = (
          currentPrice > box25High   &&
          rvolVal >= PD_VOL_MULT     &&
          dailyChange >= PD_BREAK_MIN &&
          sma20_d[dIdx] > sma60_d[dIdx]
        );

        if (!isPatternA && !isPatternB && !isPatternC && !isPatternD) return;

        // ---- [시간 게이트] 패턴C: 11:30 이후 추격 차단 ----
        if (isPatternC && !isPatternA && !isPatternB && !isPatternD) {
          if (h > STOP_C_HOUR || (h === STOP_C_HOUR && m >= STOP_C_MINUTE)) return;
        }

        // ---- [S] 스코어링 ----
        let score = 0;
        const signals = [];

        if (isPatternC) { score += 60; signals.push('촉매이벤트'); }
        if (isPatternA) { score += 50; signals.push('급등후눌림목'); }
        if (isPatternB) { score += 45; signals.push('지지선반등'); }
        if (isPatternD) { score += 40; signals.push('박스권돌파'); }
        if (isPatternA && isPatternB) { score += 15; signals.push('복합A+B'); }
        if (isPatternC && isPatternD) { score += 10; signals.push('복합C+D'); }

        if      (rvolVal >= 8.0) { score += 25; signals.push('거래량8x+'); }
        else if (rvolVal >= 5.0) { score += 18; signals.push('거래량5x'); }
        else if (rvolVal >= 3.0) { score += 12; signals.push('거래량3x'); }
        else if (rvolVal >= 2.0) { score +=  6; signals.push('거래량2x'); }

        if      (obvResult.obvTrend ===  1) { score += 20; signals.push('OBV수급↑'); }
        else if (obvResult.obvTrend === -1) { score -=  8; }

        if (macdResult.goldenCross) {
          score += 15; signals.push('MACD골든크로스');
        } else if (Number.isFinite(macdResult.hist) && macdResult.hist > 0) {
          if (Number.isFinite(macdResult.histPrev) && macdResult.hist > macdResult.histPrev) {
            score += 10; signals.push('MACD↑');
          }
        } else if (Number.isFinite(macdResult.hist) && Number.isFinite(macdResult.histPrev)
                   && macdResult.hist < 0 && macdResult.histPrev < 0 && !isPatternC) {
          return;
        }

        if (sma20_d[dIdx] > sma60_d[dIdx]) { score += 15; signals.push('일봉정배열'); }
        if      (intradayStrength >= 0.7) { score += 12; signals.push('장마감강세'); }
        else if (intradayStrength >= 0.5) { score +=  6; signals.push('장마감양호'); }

        if (dartItems.length > 0) {
          if (/계약체결|특허|인허가|수주|투자유치|증자/.test(dartItems.join(' '))) {
            score += 20; signals.push('긍정공시');
          } else { score += 5; signals.push('당일공시'); }
        }

        if (Number.isFinite(rsi14Val) && rsi14Val >= 50 && rsi14Val <= 70) { score += 8; signals.push('RSI골든존'); }
        if (Number.isFinite(adxResult.adx) && adxResult.adx >= 20 && adxResult.plusDI > adxResult.minusDI) {
          score += 10; signals.push('ADX추세↑');
        }
        if      (currentPrice >= high252) { score += 25; signals.push('52주신고가'); }
        else if (pth >= 0.95)             { score += 10; signals.push('신고가근접'); }

        if (score < MIN_SCORE_FINAL) return;

        // ---- [G2] 등급 판정 ----
        const isStrong     = score >= SCORE_STRONG_FINAL;
        const isSurge      = isPatternC && rvolVal >= 8.0 && dailyChange >= 0.08;
        const isShortTrade = !isStrong && !isSurge && isPatternC && rvolVal >= 5.0;
        const grade = isStrong ? '강매' : isSurge ? '급등' : isShortTrade ? '매도차익' : '매수';

        // ---- [REGIME-FIX] 시장 단계별 진입 차단 (2026-05-02 도입분 복원) ----
        const rg = await getMarketRegime(store, today);
        const regimeLevel = rg?.regimeLevel ?? 0;
        const riskOn = regimeLevel < 2;
        if (regimeLevel >= 2 && grade !== '강매') return; // 약세장: 강매 전용
        if (regimeLevel >= 1 && grade === '매도차익') return; // 중립장: 매도차익 차단

        // ---- [T] 목표가·손절가 ----
        const atrAbs = calcAtrAbs(highD, lowD, dIdx, 14);
        const atrPct = atrAbs / currentPrice;
        let targetPct, stopPct;
        if (isStrong) {
          // 강매(110점+)는 패턴과 무관하게 전용 프로파일 적용 (docs/01-plan/features/showmoneyv2.plan.md §6)
          targetPct = Math.max(0.10, atrPct * 1.9); stopPct = Math.max(0.04, atrPct * 1.0);
        } else if (isPatternC) {
          targetPct = Math.max(0.10, atrPct * 1.8); stopPct = Math.max(0.04, atrPct * 0.9);
        } else if (isPatternA) {
          targetPct = Math.max(Math.abs(pullbackFromEvent) * 1.3 + 0.03, atrPct * 1.6, 0.08);
          stopPct   = Math.max(0.04, atrPct * 0.9);
        } else if (isPatternB) {
          targetPct = Math.max(Math.abs(corrPct60) * 0.45, 0.10, atrPct * 1.5);
          stopPct   = Math.max(0.05, atrPct * 1.0);
        } else {
          targetPct = Math.max(0.10, atrPct * 1.5); stopPct = Math.max(0.04, atrPct * 0.8);
        }
        targetPct = Math.min(targetPct, 0.30);
        stopPct   = Math.min(stopPct,   0.08);

        let target = currentPrice * (1 + targetPct);
        let stop   = currentPrice * (1 - stopPct);
        const rrCheck = (target - currentPrice) / Math.max(currentPrice - stop, 1);
        if (rrCheck < MIN_RR_RATIO_FINAL) return;

        const target1   = currentPrice * (1 + targetPct * 0.6);
        const dowAdj    = (d === 4) ? 3 : (d === 3) ? 2 : (d === 5) ? -5 : 0;
        const rankScore = score + dowAdj;
        const code = normalize(getCode(t));
        const name = NAME[code] || code;
        const mkt  = t.endsWith('.KS') ? 'KOSPI' : 'KOSDAQ';

        // ===== /알고리즘 =====

        candidates.push({
          ticker: t, code, name, market: mkt,
          entry: currentPrice, target, target1, stop,
          score, signals, dailyChange, currentPrice, prevClose,
          timeStr: timeStrNow, type: '스윙',
          rankScore, atrAbs, rvolVal, riskOn, grade,
          patternType: isPatternC ? 'C촉매' : isPatternA ? 'A눌림목' : isPatternB ? 'B지지선' : 'D박스',
          isETF: false,
        });

        // Log grade assignment for QA tracing
        logger.info(`Stock grade assigned: ${t}`, {
          ticker: t, code, grade, score: rankScore,
          target: target.toFixed(0), stop: stop.toFixed(0),
          rvolVal: rvolVal.toFixed(2), dailyChange: (dailyChange * 100).toFixed(1) + '%',
          signals: signals.slice(0, 3).join(',')
        }, requestId);
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
  // _runningSince 락으로 겹침 실행이 차단되므로 캐시 재사용 가능성 없음
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
      try { await telegram.send(msg); } catch (e) {}
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
      try { await telegram.send(msg); } catch (e) {}
      store.naverAlerts.lastErrorAt = nowMs2;
    }
  }

  // ===== 후보 선정 =====
  candidates.sort((a, b) => (b.rankScore || b.score) - (a.rankScore || a.score));

  // ===== 선정 필터 =====
  const SEND_GRADES = new Set(['강매', '급등', '매도차익', '매수']);
  const qualified = candidates.filter(c => SEND_GRADES.has(c.grade));
  const thisWeekDates = (() => {
    const dates = [];
    const ref = new Date(today + 'T00:00:00Z');
    const dow2 = ref.getUTCDay();
    const daysToMon = dow2 === 0 ? 6 : dow2 - 1;
    const mon = new Date(ref.getTime() - daysToMon * 86400000);
    for (let i = 0; i < 7; i++) {
      const cur = new Date(mon.getTime() + i * 86400000);
      const ds = cur.toISOString().slice(0, 10);
      if (cur.getUTCDay() >= 1 && cur.getUTCDay() <= 5 && !HOLIDAYS.includes(ds)) dates.push(ds);
    }
    return dates;
  })();
  const sentThisWeek = new Set(
    thisWeekDates.flatMap(dt => (store.weeklyRecommendations[dt] || []).map(r => r.code))
  );
  const deduped = qualified.filter(c => !sentThisWeek.has(c.code));
  const gradeOrder = { '강매': 4, '급등': 3, '매도차익': 2, '매수': 1 };
  deduped.sort((a, b) => {
    const gDiff = (gradeOrder[b.grade] || 0) - (gradeOrder[a.grade] || 0);
    return gDiff !== 0 ? gDiff : (b.rankScore || 0) - (a.rankScore || 0);
  });
  const selected = deduped.slice(0, MAX_STOCK_PER_SEND);
  // ===== /선정 필터 =====
  // MIN_DAILY_PICKS=0: 0건이면 알림 없이 정상 종료

  const sent = [];
  let sendFailCount = 0;
  const sendFailSamples = [];

  // ===== [TOSS-CONFIRM] 발송 직전 토스 실시간 데이터로 최종 확인 (2026-07-14) =====
  // 참고: developers.tossinvest.com (orderbook/trades/price-limits/stocks.warnings)
  // Fail-Safe: store.tossApiKey 없거나 호출 실패 시 항상 통과 — 기존 발송 로직을 막지 않는다.
  // 선정된 소수 후보(최대 MAX_STOCK_PER_SEND건)에만 호출하므로 rate limit 영향 미미.
  const TOSS_CONFIRM_TIMEOUT = 6000;
  const TOSS_ASK_BID_BLOCK_RATIO = 1.5; // 매도잔량이 매수잔량의 1.5배 넘으면 발송 보류
  const TOSS_WEAK_BUY_RATIO_C = 0.4;    // 패턴C 한정: 실시간 매수체결비율 40% 미만이면 발송 보류
  const TOSS_GAP_REBASE_THRESHOLD = 0.02; // 실시간가-전일종가 괴리가 2% 이상이면 실시간가로 매수가 재계산

  const _tossApiKey = () => store.tossApiKey || '';

  const toss = createTossClient(http, _tossApiKey(), { timeout: TOSS_CONFIRM_TIMEOUT });

  // VI_STATIC/VI_DYNAMIC/VI_STATIC_AND_DYNAMIC 활성 여부 (startDate~endDate 구간에 오늘 포함, endDate null=미해제)
  const isViActive = (warnings) => {
    if (!Array.isArray(warnings)) return false;
    const today = new Date(Date.now() + 9 * 60 * 60 * 1000).toISOString().slice(0, 10);
    return warnings.some((w) => {
      if (!/^VI_/.test((w && w.warningType) || '')) return false;
      const started = !w.startDate || w.startDate <= today;
      const notEnded = !w.endDate || w.endDate >= today;
      return started && notEnded;
    });
  };

  // 체결 tick rule 근사치: Toss trades 응답엔 매수/매도 구분 필드가 없어 직전 체결가 대비
  // 상승 체결 비중으로 매수세를 추정한다(공식 미제공 항목의 근사치임을 명시).
  const estimateBuyRatio = (trades) => {
    if (!Array.isArray(trades) || trades.length < 2) return null;
    let buyVol = 0, totalVol = 0;
    for (let i = 1; i < trades.length; i++) {
      const p0 = Number(trades[i - 1].price), p1 = Number(trades[i].price);
      const v1 = Number(trades[i].volume) || 0;
      if (!Number.isFinite(p0) || !Number.isFinite(p1) || v1 <= 0) continue;
      totalVol += v1;
      if (p1 >= p0) buyVol += v1;
    }
    return totalVol > 0 ? buyVol / totalVol : null;
  };

  // 튜닝용 상세 기록 저장 + 구조화 로그 발행 (항상 호출 — 통과/차단 모두 기록)
  const logTossConfirm = (c, record) => {
    const entry = Object.assign({
      time: new Date(Date.now() + 9 * 60 * 60 * 1000).toISOString(),
      ticker: c.ticker, code: c.code, grade: c.grade, patternType: c.patternType,
      thresholds: { askBidBlockRatio: TOSS_ASK_BID_BLOCK_RATIO, weakBuyRatioC: TOSS_WEAK_BUY_RATIO_C },
    }, record);
    store.tossConfirmLog[today].push(entry);
    logger.info(`Toss confirm evaluated: ${c.ticker}`, entry, requestId);
  };

  const tossConfirm = async (c) => {
    const info = {
      checked: false, viActive: false,
      bidAskRatio: null, askTotal: null, bidTotal: null,
      buyRatio: null, buySampleCount: 0,
      upperLimitPct: null,
      livePrice: null, gapPct: null, rebased: false, originalEntry: null,
    };
    if (!_tossApiKey()) return { ok: true, info }; // Fail-Safe: 키 미설정 시 평가 자체를 스킵(로그 없음)

    const [warnings, orderbook, trades, priceLimits] = await Promise.all([
      toss.fetchWarnings(c.code),
      toss.fetchOrderbook(c.code),
      toss.fetchTrades(c.code, 50),
      toss.fetchPriceLimits(c.code),
    ]);
    info.checked = true;
    const apiOk = { warnings: warnings != null, orderbook: orderbook != null, trades: trades != null, priceLimits: priceLimits != null };

    // ---- 지표는 항상 전부 계산 (어떤 조건이 차단했는지와 무관하게 튜닝용 원본 값 확보) ----
    info.viActive = isViActive(warnings);

    let askTotal = null, bidTotal = null;
    if (orderbook && Array.isArray(orderbook.asks) && Array.isArray(orderbook.bids)) {
      askTotal = orderbook.asks.reduce((s, a) => s + (Number(a.volume) || 0), 0);
      bidTotal = orderbook.bids.reduce((s, b) => s + (Number(b.volume) || 0), 0);
      info.askTotal = askTotal;
      info.bidTotal = bidTotal;
      if (askTotal > 0 || bidTotal > 0) info.bidAskRatio = bidTotal / Math.max(askTotal, 1);
    }

    const buyRatio = estimateBuyRatio(trades);
    info.buyRatio = buyRatio;
    info.buySampleCount = Array.isArray(trades) ? trades.length : 0;

    if (priceLimits && Number.isFinite(Number(priceLimits.upperLimitPrice)) && c.entry > 0) {
      info.upperLimitPct = (Number(priceLimits.upperLimitPrice) - c.entry) / c.entry;
    }

    // ===== [TOSS-LIVEPRICE] 실시간 체결가 기준 추격매수 차단 + 매수가 재계산 (2026-07-19) =====
    // 배경: c.entry는 전일 종가(currentPrice = closeD[dIdx])로 계산되는데, 발송 시점(09:10)엔
    // 이미 시가부터 갭업해 진입가가 실전에서 체결 불가능한 경우가 확인됨(2026-07-13~18
    // 주간 리포트 QA — 한성기업/003680, 동화약품/000020). 이미 확보 중인 Toss 실시간
    // 체결(trades)/호가(orderbook)로 현재가를 구해 (1) 이미 목표가를 넘어선 추격 상황이면
    // 발송을 막고, (2) 괴리가 유의미하면 매수가/목표가/손절가를 실시간가 기준으로 재계산한다.
    let livePrice = null;
    if (Array.isArray(trades) && trades.length > 0) {
      const p = Number(trades[trades.length - 1].price);
      if (Number.isFinite(p) && p > 0) livePrice = p;
    }
    if (livePrice == null && orderbook && Array.isArray(orderbook.asks) && Array.isArray(orderbook.bids) && orderbook.asks[0] && orderbook.bids[0]) {
      const bestAsk = Number(orderbook.asks[0].price), bestBid = Number(orderbook.bids[0].price);
      if (Number.isFinite(bestAsk) && Number.isFinite(bestBid) && bestAsk > 0 && bestBid > 0) livePrice = (bestAsk + bestBid) / 2;
    }
    // [정책 결정-2026-07-19] "체결 불가능한 가격 승리 방지"를 패턴 예외 없이 전 패턴에
    // 동일 적용한다. 패턴C(촉매)는 원래 모멘텀 추격형 설계이지만, 그렇다고 이미 목표가를
    // 넘겼거나 이미 손절가 밑으로 꺼진 "실전에서 재현 불가능한 신호"까지 보내는 건 별개
    // 문제다(2026-07-13~18 QA의 한성기업/003680, 동화약품/000020이 둘 다 이 케이스).
    // 패턴별 예외를 두지 않고 모든 패턴에 동일한 실시간가 검증을 적용한다.
    let gapPct = null, chasingRisk = false, alreadyStoppedOut = false;
    if (livePrice != null && c.entry > 0) {
      gapPct = (livePrice - c.entry) / c.entry;
      if (c.target > 0 && livePrice >= c.target) chasingRisk = true;
      if (c.stop > 0 && livePrice <= c.stop) alreadyStoppedOut = true;
    }
    info.livePrice = livePrice;
    info.gapPct = gapPct;

    // ---- 차단 판정 (우선순위: VI > 실시간가 추격위험/이미 손절권 > 호가매도우위 > 패턴C 매수체결비율저조) ----
    let ok = true, reason = null;
    if (info.viActive) {
      ok = false; reason = 'VI 발동 중';
    } else if (chasingRisk) {
      ok = false; reason = '실시간가가 이미 목표가 초과(추격매수 위험, 괴리 ' + (gapPct * 100).toFixed(1) + '%)';
    } else if (alreadyStoppedOut) {
      ok = false; reason = '실시간가가 이미 손절가 이하(발송 전 셋업 무효화, 괴리 ' + (gapPct * 100).toFixed(1) + '%)';
    } else if (askTotal != null && bidTotal != null && askTotal > bidTotal * TOSS_ASK_BID_BLOCK_RATIO) {
      ok = false; reason = '호가 매도우위(매도잔량이 매수잔량의 ' + TOSS_ASK_BID_BLOCK_RATIO + '배 이상)';
    } else if (c.patternType === 'C촉매' && buyRatio != null && buyRatio < TOSS_WEAK_BUY_RATIO_C) {
      ok = false; reason = '실시간 매수체결비율 저조(' + (buyRatio * 100).toFixed(0) + '%)';
    }

    // ---- 발송이 확정된 경우에만, 괴리가 유의미하면 실시간가로 매수가/목표가/손절가 재계산 ----
    // (%비율 targetPct/stopPct는 전일종가 기준 ATR로 이미 계산돼 있으므로 그 비율만 유지)
    if (ok && livePrice != null && gapPct != null && Math.abs(gapPct) >= TOSS_GAP_REBASE_THRESHOLD) {
      const targetPct = c.target / c.entry - 1;
      const stopPct = 1 - c.stop / c.entry;
      const target1Pct = Number.isFinite(c.target1) ? (c.target1 / c.entry - 1) : null;
      info.rebased = true;
      info.originalEntry = c.entry;
      c.entry = livePrice;
      c.target = livePrice * (1 + targetPct);
      c.stop = livePrice * (1 - stopPct);
      if (target1Pct != null) c.target1 = livePrice * (1 + target1Pct);
    }

    logTossConfirm(c, { ok, reason, apiOk, info });
    return { ok, reason, info };
  };
  // ===== /TOSS-CONFIRM =====

  // ===== [INTRADAY-STOP-BREAKER] 당일 손절 서킷브레이커 =====
  // 오늘 이미 보낸 추천 중 실시간가가 손절가 이하로 내려간 종목 수를 세어,
  // INTRADAY_STOP_THRESH(2) 이상이면 당일 신규 발송을 억제한다(장이 안 좋은 날
  // 계속 새 매수 신호를 보내는 것을 막기 위함). tossConfirm()과 동일한
  // fail-safe 패턴(Toss API 키 미설정 시 스킵) 및 실시간가 조회 로직을 재사용한다.
  const countTodayStopOuts = async (todayKey) => {
    if (!_tossApiKey()) return 0; // Fail-Safe: 키 미설정 시 체크 자체를 스킵
    const todays = (store.weeklyRecommendations && store.weeklyRecommendations[todayKey]) || [];
    let stopCount = 0;
    for (const rec of todays) {
      try {
        const [orderbook, trades] = await Promise.all([
          toss.fetchOrderbook(rec.code),
          toss.fetchTrades(rec.code, 5),
        ]);
        let livePrice = null;
        if (Array.isArray(trades) && trades.length > 0) {
          const p = Number(trades[trades.length - 1].price);
          if (Number.isFinite(p) && p > 0) livePrice = p;
        }
        if (livePrice == null && orderbook && Array.isArray(orderbook.asks) && Array.isArray(orderbook.bids) && orderbook.asks[0] && orderbook.bids[0]) {
          const bestAsk = Number(orderbook.asks[0].price), bestBid = Number(orderbook.bids[0].price);
          if (Number.isFinite(bestAsk) && Number.isFinite(bestBid) && bestAsk > 0 && bestBid > 0) livePrice = (bestAsk + bestBid) / 2;
        }
        if (livePrice != null && Number.isFinite(rec.stop) && livePrice <= rec.stop) stopCount++;
      } catch (e) {
        // 라이브가 조회 실패 종목은 카운트에서 제외 (네트워크 오류로 신규 발송 전체를 막지 않기 위함)
      }
    }
    return stopCount;
  };
  // ===== /INTRADAY-STOP-BREAKER =====

  const getHoldDays = (c) => {
    return (c.grade === '강매')          ? 5
         : (c.grade === '급등')          ? 2
         : (c.patternType === 'C촉매')   ? 2
         : (c.patternType === 'A눌림목') ? 3
         : (c.patternType === 'B지지선') ? 5
         : (c.patternType === 'D박스')   ? 4
         : 3;
  };

  const send = async (c) => {
    // tossConfirm() 내부에서 이미 store.tossConfirmLog + logger.info로 상세 기록을 남긴다
    const confirm = await tossConfirm(c);
    if (!confirm.ok) return null;
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

    const alertH = kstNow.getUTCHours();
    const alertM = kstNow.getUTCMinutes();
    const isOpenWindow = (alertH === 9 && alertM <= 10);
    // [TOSS-LIVEPRICE] 실시간가로 재계산된 경우 매수가 자체가 이미 체결 가능한 현재가이므로 문구도 그에 맞춘다
    const entryNote = confirm.info.rebased
      ? timeStr + ' 실시간 체결가 기준 즉시 진입'
      : isOpenWindow
        ? '09:00~09:10 시초가 체결 확인 후 진입'
        : timeStr + ' 현재가 기준 즉시 진입';

    const typeLabel = c.isETF ? 'ETF' : '단일종목';
    const gradePrefix = (c.grade === '강매')     ? '[★강매] '
                      : (c.grade === '급등')     ? '[🚀급등] '
                      : (c.grade === '매도차익') ? '[⚡단기] '
                      : (c.grade === '관심')     ? '[관심] '
                      : '';
    const target1Line = Number.isFinite(c.target1)
      ? '- 1차 목표: ' + to0(c.target1) + '원 (+' + pct(c.target1 / c.entry - 1) + ')' + NL
      : '';
    const atrPct = Number.isFinite(c.atrAbs) && c.entry > 0 ? (c.atrAbs / c.entry * 100) : 2.0;
    const trailingPct = Math.max(1.0, Math.min(atrPct, 3.0));
    const holdDays = getHoldDays(c);
    const tossInfo = confirm.info;
    const tossConfirmLine = tossInfo.checked
      ? ('실시간 확인(Toss): 호가매수비 ' + (Number.isFinite(tossInfo.bidAskRatio) ? tossInfo.bidAskRatio.toFixed(2) : 'N/A') +
         ' · 체결매수비 ' + (Number.isFinite(tossInfo.buyRatio) ? (tossInfo.buyRatio * 100).toFixed(0) + '%' : 'N/A') +
         (Number.isFinite(tossInfo.upperLimitPct) ? ' · 상한가 ' + pct(tossInfo.upperLimitPct) + ' 남음' : '') +
         (tossInfo.rebased ? ' · ⚠️매수가 재계산(전일종가→실시간가 ' + pct(tossInfo.gapPct) + ')' : '') + NL)
      : '';
    const msg =
      gradePrefix + '[스윙] ' + c.market + '(' + typeLabel + ') | ' + displayName + '(' + c.code + ')' + NL +
      '등급: ' + (c.grade || '매수') + NL +
      '기준가: ' + to0(c.entry) + '원' + dailyChangeText + NL +
      '- 매수가: ' + to0(c.entry) + '원 (' + entryNote + ')' + NL +
      '- 보유기간: 최대 ' + holdDays + '거래일 (목표가/손절가 도달 시 조기 청산)' + NL +
      target1Line +
      '- 최종 목표: ' + to0(c.target) + '원 (+' + pct(c.target / c.entry - 1) + ')' + NL +
      '- 손절가: ' + to0(c.stop) + '원 (-' + pct(1 - c.stop / c.entry) + ')' + NL +
      '- 트레일링: +2% 도달시 고점 -' + trailingPct.toFixed(1) + '% 이동' + NL +
      '📊 분할청산: 1차(30%) +2% / 2차(30%) +4% / 잔여(40%) 트레일링' + NL +
      'ATR(14): ' + (Number.isFinite(c.atrAbs) ? (to0(c.atrAbs) + '원') : 'N/A') + NL +
      '- 점수: ' + c.score + '점' + NL +
      tossConfirmLine +
      '핵심 시그널: ' + (c.signals.slice(0, 3).join(', ') || 'N/A');

    try {
      await telegram.send(msg);
      return { entry: c.entry, target: c.target, target1: c.target1, stop: c.stop, resolvedName: displayName };
    } catch (e) {
      sendFailCount++;
      if (sendFailSamples.length < 3) sendFailSamples.push({ ticker: c.ticker, message: String(e?.message || e) });
      logger.error(`Failed to send notification: ${c.ticker}`, {
        ticker: c.ticker,
        grade: c.grade,
        error: String(e?.message || e).slice(0, 200)
      }, requestId);
      return null;
    }
  };

  const todayStopCount = await countTodayStopOuts(today);
  const intradayStopBreakerTripped = todayStopCount >= INTRADAY_STOP_THRESH;
  if (intradayStopBreakerTripped) {
    logger.info('Intraday stop-loss circuit breaker tripped — suppressing new sends today', {
      todayStopCount, threshold: INTRADAY_STOP_THRESH,
    }, requestId);
  }

  for (let i = 0; i < selected.length; i++) {
    // [INTRADAY-STOP-BREAKER] 당일 손절 2회 이상 시 신규 발송 억제
    if (intradayStopBreakerTripped) break;
    // [NODUP-2] send 직전 재확인 — 동시 실행 레이스 컨디션 최후 방어
    if (store.swingSentToday[today] && store.swingSentToday[today].includes(selected[i].code)) continue;
    const res = await send(selected[i]);
    if (res) {
      store.swingSent[selected[i].ticker] = now.getTime();
      // [NODUP-2] 당일 발송 Set에 즉시 기록
      if (!store.swingSentToday[today]) store.swingSentToday[today] = [];
      store.swingSentToday[today].push(selected[i].code);

      // Log successful notification send
      logger.info(`Stock notification sent: ${selected[i].ticker}`, {
        ticker: selected[i].ticker,
        grade: selected[i].grade,
        entry: res.entry.toFixed(0),
        target: res.target.toFixed(0),
        stop: res.stop.toFixed(0),
        rankScore: selected[i].rankScore
      }, requestId);

      const today2 = `${kst.getUTCFullYear()}-${String(kst.getUTCMonth() + 1).padStart(2, '0')}-${String(kst.getUTCDate()).padStart(2, '0')}`;
      if (!store.weeklyRecommendations) store.weeklyRecommendations = {};
      if (!store.weeklyRecommendations[today2]) store.weeklyRecommendations[today2] = [];

      const holdDays = getHoldDays(selected[i]);

      store.weeklyRecommendations[today2].push({
        type: 'swing', subType: selected[i].type,
        ticker: selected[i].ticker, code: selected[i].code, name: res.resolvedName || selected[i].name,
        entry: res.entry, target: res.target, target1: res.target1, stop: res.stop,
        // initialStop: 트레일링으로 절대 덮어쓰지 않는 최초 손절가 스냅샷.
        // weekly-reporter가 손절일을 사후 재구성할 때 이 값을 시드로 써야
        // "이미 트레일링으로 올라간 현재 stop"을 과거 저가에 소급 적용하는 오판정을 피한다.
        initialStop: res.stop,
        atrAbs: selected[i].atrAbs,
        holdingDays: holdDays, score: selected[i].score, grade: selected[i].grade,
        isETF: !!selected[i].isETF, // [QI] ETF vs 단일종목 구분 태그
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
      try { await telegram.send(msg); } catch (e) {}
      store.telegramAlerts.swingSendFailAt = nowMs3;
    }
  }

  if (selected.length === 0) {
    if (!store.swingAlerts) store.swingAlerts = {};
    if (store.swingAlerts.noHitDate === today) {
      store.swingMeta._runningSince = null; // [NODUP-3-FIX] 조기 종료 경로도 락 해제
      return [{ json: { skipped: true, reason: 'No hit (already notified today)' } }];
    }
    const msg =
      '[스윙 스캔 완료] 추천 종목 없음' + NL +
      '- 분석 종목(필터 후): ' + ALL_TICKERS.length + '개' + NL +
      '- 후보: ' + candidates.length + '개' + NL +
      '- 제외(리스크): ' + excludedRisk + '개' + NL +
      '- 제외(테마): ' + excludedTheme + '개' + NL +
      '- Naver OK/NoResult/Error: ' + naverOkCount + '/' + naverNoResultCount + '/' + naverErrorCount + NL +
      '- KST: ' + today + ' ' + timeStrNow;
    try {
      await telegram.send(msg);
    } catch (e) {}
    store.swingAlerts.noHitDate = today;
  }

  // ===== [SCAN-LOG] 상세 로그 최종화 및 저장 (2026-05-17) =====
  try {
    const rg0 = store.regimeCache || {};
    _log.regime = { level: rg0.regimeLevel ?? 0, ksUp: rg0.ksUp, kqUp: rg0.kqUp };
    _log.macro  = { nasdaqChg: rg0.nasdaqChg, esFutChg: rg0.esFutChg, vixLevel: rg0.vixLevel, macroAdj: rg0.macroAdj };
    _log.topCandidates = candidates.slice(0, 10).map(c => ({
      ticker: c.ticker, name: c.name, grade: c.grade,
      score: c.score, rankScore: c.rankScore,
      rvol: c.rvolVal != null ? +c.rvolVal.toFixed(2) : null,
      dailyChange: +(c.dailyChange * 100).toFixed(2),
      entry: +c.entry.toFixed(0), target: +c.target.toFixed(0), stop: +c.stop.toFixed(0),
      signals: (c.signals || []).slice(0, 6), isETF: !!c.isETF,
    }));
    _log.sent  = sent.slice();
    const tossEvalsToday = store.tossConfirmLog[today] || [];
    _log.stats = {
      universe: ALL_TICKERS.length, candidates: candidates.length,
      sentCount: sent.length, excludedRisk, excludedTheme,
      naverOk: naverOkCount, naverNoResult: naverNoResultCount, naverErr: naverErrorCount,
      tossConfirmChecked: tossEvalsToday.length,
      tossConfirmBlocked: tossEvalsToday.filter(e => !e.ok).length,
    };
    _log.finishedAt = new Date().toISOString();
    store.scanLog.unshift(_log);
    if (store.scanLog.length > 20) store.scanLog.length = 20;
  } catch (_e) { /* 로그 저장 실패 무시 */ }
  // ===== /SCAN-LOG =====

  // ===== [TOSS-RISK] 리스크 블랙리스트 토스 API 연동용 1차 필터 통과 종목 저장 (2026-07-10) =====
  // Risk Blacklist Updater 노드가 다음날 08:30 갱신 시 이 목록으로 토스 /warnings 호출 대상을 한정한다.
  // 참고: docs/02-design/features/risk-blacklist-toss-api.design.md §2.2
  try {
    store.lastFilteredUniverse = {
      symbols: ALL_TICKERS.map((t) => t.slice(0, 6)),
      updatedAt: new Date().toISOString(),
    };
  } catch (_e) { /* 저장 실패는 무시 — Risk Blacklist Updater가 Fail-Safe로 스킵 처리 */ }
  // ===== /TOSS-RISK =====

  store.swingMeta._lastFullFinish = Date.now();
  store.swingMeta._runningSince = null; // [NODUP-3] 락 해제 — 다음 트리거부터 재실행 허용

  // Log scan completion
  logger.info('Swing scanner completed', {
    scanTime: kst.toISOString(),
    totalUniverse: ALL_TICKERS.length,
    candidates: candidates.length,
    sent: sent.length,
    sentTickers: sent.slice(0, 10).join(','),
    excludedRisk, excludedTheme,
    naverApiStats: {
      ok: naverOkCount,
      noResult: naverNoResultCount,
      error: naverErrorCount
    }
  }, requestId);

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

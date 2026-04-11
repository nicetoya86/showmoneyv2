const run = async function () {
  const BOT = '8366696724:AAHROcjGoQEn9BziD-sYdAu3ZuaolwtkgLE';
  const CHAT = '523002062';
  const MIN_PRICE = 1000;
  const MIN_INTRADAY_TURNOVER = 1000000000;
  const MIN_SCORE = 70;
  const RELAX_SCORE = 50;
  const MIN_DAILY_PICKS = 2;
  const PMAT_STRICT = 0.60;
  const PMAT_RELAX = 0.60;

  // ===== Risk/Regime Layer (conservative) =====
  const ACCOUNT_KRW = 10000000;
  const RISK_PCT_PER_TRADE = 0.005;
  const ATR_WINDOW = 14;
  const ATR_STOP_MULT = 1.9;
  const ATR_TARGET_MULT = 2.8;
  const CAP_STOP_PCT = 0.10;
  const CAP_TARGET_PCT = 0.25;
  const REGIME_RANGE = '6mo';
  const REGIME_INTERVAL = '1d';
  // ===== /Risk/Regime Layer =====
  const MAX_INTRADAY_SENDS = 4;
  const HOLIDAYS = ['2025-01-01','2025-01-28','2025-01-29','2025-01-30','2025-03-01','2025-03-03','2025-05-05','2025-05-06','2025-06-06','2025-08-15','2025-10-03','2025-10-06','2025-10-07','2025-10-08','2025-10-09','2025-12-25','2026-01-01','2026-02-16','2026-02-17','2026-02-18','2026-03-01','2026-03-02','2026-05-05','2026-05-24','2026-05-25','2026-06-03','2026-06-06','2026-08-15','2026-08-17','2026-09-24','2026-09-25','2026-09-26','2026-10-03','2026-10-05','2026-10-09','2026-12-25'];
  const DUPLICATE_WINDOW_MINUTES = 60;
  const STOP_NEW_ALERTS_HOUR = 15;
  const STOP_NEW_ALERTS_MINUTE = 20;

  const http = async (o) => await this.helpers.httpRequest(Object.assign({ timeout: 45000 }, o));

  const sma = (arr, w) => {
    const out = new Array(arr.length).fill(NaN);
    if (arr.length < w) return out;
    let sum = 0;
    for (let i=0;i<arr.length;i++){
      const v = Number(arr[i]);
      sum += (Number.isFinite(v) ? v : 0);
      if (i >= w) {
        const old = Number(arr[i-w]);
        sum -= (Number.isFinite(old) ? old : 0);
      }
      if (i >= w-1) out[i] = sum / w;
    }
    return out;
  };

  const calcAtrAbs = (highD, lowD, idx, w) => {
    const i = Math.max(0, Math.min(idx, highD.length - 1));
    const start = Math.max(0, i - w);
    const seg = [];
    for (let k=start; k<i; k++) {
      const hi = Number(highD[k]);
      const lo = Number(lowD[k]);
      if (Number.isFinite(hi) && Number.isFinite(lo)) seg.push(Math.max(0, hi - lo));
    }
    if (!seg.length) return NaN;
    const s = seg.reduce((a,b)=>a+b,0);
    return s / seg.length;
  };

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

    return {
      detected: true,
      leftRim, rightRim, bottom, handleHigh, handleLow,
      cupDepth, handleRetracement
    };
  };

  const fetchDailyClose = async (encodedTicker) => { return []; };

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
  const debugMode = !!input.debugMode;

  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const timeStrNow = String(kst.getUTCHours()).padStart(2, '0') + ':' + String(kst.getUTCMinutes()).padStart(2, '0');

  const NL = String.fromCharCode(10);
  const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // [TEST MODE]
  if (forceTest) {
    const msg = '[스윙 스캔 테스트] 시스템 정상 작동' + NL + '시간: ' + kst.toISOString().slice(0, 16).replace('T', ' ') + ' KST';
    try {
      const res = await http({
        method: 'POST',
        url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
        json: true,
        body: { chat_id: CHAT, text: msg, parse_mode: 'HTML' },
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

  if (h < 9) return [{ json: { skipped: true, reason: 'Before market open' } }];
  if (h === 9 && m < 8) return [{ json: { skipped: true, reason: 'Too early - before 09:08' } }];

  // 장 마감 근접 시 신규 알림 중단
  if (h > STOP_NEW_ALERTS_HOUR || (h === STOP_NEW_ALERTS_HOUR && m >= STOP_NEW_ALERTS_MINUTE)) {
    return [{ json: { skipped: true, reason: 'Too close to market close' } }];
  }
  if (h >= 16) return [{ json: { skipped: true, reason: 'After market close' } }];

  const store = this.getWorkflowStaticData('global');
  if (!store.swingMeta) store.swingMeta = {};
  store.swingMeta.lastRunAt = now.toISOString();
  store.swingMeta.lastRunDate = today;

  // [PERF] Queue 적체 방지
  if (store.swingMeta._lastFullFinish && (Date.now() - store.swingMeta._lastFullFinish) < 90000) {
    return [{ json: { skipped: true, reason: 'Queue backed up - fast drain' } }];
  }

  if (!store.swingSent) store.swingSent = {};
  if (!store.weeklyRecommendations) store.weeklyRecommendations = {};
  // [FIX] Memory leak: clean old dates (keep last 14 days only)
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

  // ===== Blacklist (risk/theme) cached in staticData =====
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

  // ===== HiTalk Setup Models (auto) =====
  const HITALK_UP_MODEL = {"name":"SETUP_UP(단타=급등)","feature_cols":["daily_change","uptrend","rsi14","breakout20","breakout_ratio","breakout60","breakout60_ratio","volume_surge","volume_surge5","volume_surge60","volume_trend_5_20","volatility","atr14","ret5","ret20","dist_sma20","dist_sma60","trend_strength","price"],"scaler":{"mean":[0.03941112323492713,0.5543478260869565,56.545286976615934,0.16897233201581027,0.9125539688024894,0.09387351778656126,0.8444209313001051,7.859869097035799,9.808710474152516,7.407255525593385,1.1741009201441042,0.09152603600351632,0.052841022855268954,0.06693993755172249,0.09917903036869001,0.06651846479725247,0.09049245314562593,0.007006514477785763,35568.01663811122],"scale":[0.08766529491393103,0.49703753761624325,16.889372083821293,0.3747274783478637,0.11615516943446853,0.2916526709031452,0.1404641448755363,28.625067611054348,36.39775002735151,24.425783867182986,0.8121668721832151,0.07127136375745106,0.02481501386636216,0.13977010898417583,0.24293659705155204,0.13241135669408638,0.19540197393809716,0.13715305283752963,95896.01749780211]},"coef":[0.7562683117443777,0.3626442429601983,0.2795871935673176,0.11570148366611886,0.5328372190930989,-0.49562171518787235,-0.0133555000485831,-0.5147492810327007,0.935863691546091,-0.36162297177444197,-0.014914088687825148,1.0185496067021869,0.5814560310633664,0.7469841752968425,-0.5127443495874868,0.6227061707667483,-0.3418990371124205,0.25010246627460375,-1.104266379894277],"intercept":-0.6993095468699385,"meta":{"generatedAt":"2025-12-21T05:54:03.827639Z","rows":1266,"pos":373,"neg":893,"skipped":120,"seed":42,"neg_per_pos":2,"top_turnover":800,"max_days":120},"metrics":{"auc":0.9353445065176909,"report":{"0":{"precision":0.94375,"recall":0.8435754189944135,"f1-score":0.8908554572271387,"support":179.0},"1":{"precision":0.7021276595744681,"recall":0.88,"f1-score":0.7810650887573964,"support":75.0},"accuracy":0.8543307086614174,"macro avg":{"precision":0.822938829787234,"recall":0.8617877094972067,"f1-score":0.8359602729922675,"support":254.0},"weighted avg":{"precision":0.8724048207404926,"recall":0.8543307086614174,"f1-score":0.8584370413404038,"support":254.0}},"confusion_matrix":[[151,28],[9,66]]}};
  const HITALK_MAT_MODEL = {"name":"SETUP_MAT(스윙=재료)","feature_cols":["daily_change","uptrend","rsi14","breakout20","breakout_ratio","breakout60","breakout60_ratio","volume_surge","volume_surge5","volume_surge60","volume_trend_5_20","volatility","atr14","ret5","ret20","dist_sma20","dist_sma60","trend_strength","price"],"scaler":{"mean":[0.021672322309040985,0.6102292768959435,55.54906409815424,0.12698412698412698,0.9044426261918556,0.08465608465608465,0.848404316977533,5.05730837028303,5.9870278883417605,4.935397521137353,1.1624705759072649,0.07390376416270977,0.05358470180620499,0.05517713949198958,0.09110163225026832,0.05955020351996882,0.10858486882914639,0.028491179406826692,41330.92297557044],"scale":[0.07289730273067968,0.487698171531324,16.441425165154502,0.3329551898952858,0.10843488516735644,0.2783692367823469,0.13045534095275263,19.32527938335188,25.39394540728067,18.221408853875058,0.7277593184242444,0.05890488709896314,0.026258386597653047,0.1318396349850443,0.20362394914749846,0.12413112586273757,0.19332765113378547,0.09773438561870854,74861.23768223941]},"coef":[0.6717596961119858,0.6762207689163452,0.39355856590519267,-0.09228167232586969,0.9053624709907248,-0.11319441378647066,-0.0015877478707488962,-0.08994121562855331,0.2922226931482804,-0.36171544831150043,0.2305227581635665,0.31550222939058603,1.374909565887536,0.4119961022129777,-0.7485519331679408,0.7716839454271054,-1.0245614606852167,0.0714910196773468,-0.1523532626149339],"intercept":-0.3607035788307738,"meta":{"generatedAt":"2025-12-21T05:54:03.859639Z","rows":709,"pos":208,"neg":501,"skipped":59,"seed":42,"neg_per_pos":2,"top_turnover":800,"max_days":120},"metrics":{"auc":0.8185714285714285,"report":{"0":{"precision":0.8837209302325582,"recall":0.76,"f1-score":0.8172043010752689,"support":100.0},"1":{"precision":0.5714285714285714,"recall":0.7619047619047619,"f1-score":0.6530612244897959,"support":42.0},"accuracy":0.7605633802816901,"macro avg":{"precision":0.7275747508305648,"recall":0.7609523809523809,"f1-score":0.7351327627825324,"support":142.0},"weighted avg":{"precision":0.7913527677694071,"recall":0.7605633802816901,"f1-score":0.7686549403950586,"support":142.0}},"confusion_matrix":[[76,24],[10,32]]}};
  const HITALK_SETUP_CFG = {"UP":{"targetRate":0.10550000000000001,"stopRate":0.055,"threshold":0.93},"MAT":{"targetRate":0.14155,"stopRate":0.08,"threshold":0.95}};
  const hitalkSigmoid = (x) => 1 / (1 + Math.exp(-x));
  const hitalkDot = (w, x) => { let s = 0; for (let i = 0; i < w.length; i++) s += w[i] * x[i]; return s; };
  const hitalkStandardize = (model, featArr) => {
    const mu = model.scaler.mean;
    const sc = model.scaler.scale;
    const x = new Array(featArr.length);
    for (let i = 0; i < featArr.length; i++) x[i] = ((Number(featArr[i]) || 0) - (mu[i] || 0)) / (((sc[i] || 1) || 1));
    return x;
  };
  const hitalkPredictBin = (model, featArr) => {
    const x = hitalkStandardize(model, featArr);
    const z = hitalkDot(model.coef, x) + (model.intercept || 0);
    return hitalkSigmoid(z);
  };
  const hitalkSma = (arr, w) => {
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
  const hitalkRsi14 = (close) => {
    const p = 14;
    const out = new Array(close.length).fill(NaN);
    if (close.length < p + 1) return out;
    const up = [];
    const dn = [];
    for (let i = 1; i < close.length; i++) {
      const d = Number(close[i]) - Number(close[i - 1]);
      up.push(Math.max(d, 0));
      dn.push(Math.max(-d, 0));
    }
    const au = hitalkSma([NaN].concat(up), p);
    const ad = hitalkSma([NaN].concat(dn), p);
    for (let i = 0; i < close.length; i++) {
      if (!Number.isFinite(au[i]) || !Number.isFinite(ad[i])) continue;
      const rs = (ad[i] === 0) ? 999 : (au[i] / ad[i]);
      out[i] = 100 - 100 / (1 + rs);
    }
    return out;
  };
  const hitalkFeaturesFromDaily = (closeD, highD, lowD, volD, idx) => {
    const n = closeD.length;
    const i = Math.max(0, Math.min(idx, n - 1));
    const close = Number(closeD[i]);
    const prev = i > 0 ? Number(closeD[i - 1]) : NaN;
    const daily_change = (Number.isFinite(prev) && prev > 0 && close > 0) ? (close / prev - 1) : 0;
    const sma20 = hitalkSma(closeD, 20);
    const sma60 = hitalkSma(closeD, 60);
    const uptrend = (Number.isFinite(sma20[i]) && Number.isFinite(sma60[i]) && sma20[i] > sma60[i]) ? 1 : 0;
    const rsi = hitalkRsi14(closeD);
    const rsi14 = Number.isFinite(rsi[i]) ? rsi[i] : 50;
    const start20 = Math.max(0, i - 20);
    const start60 = Math.max(0, i - 60);
    const prev20 = (i - start20 >= 1) ? Math.max.apply(null, highD.slice(start20, i).map(Number)) : NaN;
    const prev60 = (i - start60 >= 1) ? Math.max.apply(null, highD.slice(start60, i).map(Number)) : NaN;
    const breakout20 = (Number.isFinite(prev20) && close > prev20) ? 1 : 0;
    const breakout_ratio = (Number.isFinite(prev20) && prev20 > 0 && close > 0) ? (close / prev20) : 1;
    const breakout60 = (Number.isFinite(prev60) && close > prev60) ? 1 : 0;
    const breakout60_ratio = (Number.isFinite(prev60) && prev60 > 0 && close > 0) ? (close / prev60) : 1;
    const v20 = volD.slice(start20, i).map(Number).filter(Number.isFinite);
    const vavg20 = v20.length ? (v20.reduce((a, b) => a + b, 0) / v20.length) : NaN;
    const vtoday = Number(volD[i]);
    const volume_surge = (Number.isFinite(vavg20) && vavg20 > 0 && Number.isFinite(vtoday)) ? (vtoday / vavg20) : 1;
    const v5 = volD.slice(Math.max(0, i - 5), i).map(Number).filter(Number.isFinite);
    const v60 = volD.slice(start60, i).map(Number).filter(Number.isFinite);
    const vavg5 = v5.length ? (v5.reduce((a, b) => a + b, 0) / v5.length) : NaN;
    const vavg60 = v60.length ? (v60.reduce((a, b) => a + b, 0) / v60.length) : NaN;
    const volume_surge5 = (Number.isFinite(vavg5) && vavg5 > 0 && Number.isFinite(vtoday)) ? (vtoday / vavg5) : 1;
    const volume_surge60 = (Number.isFinite(vavg60) && vavg60 > 0 && Number.isFinite(vtoday)) ? (vtoday / vavg60) : 1;
    const volume_trend_5_20 = (Number.isFinite(vavg5) && Number.isFinite(vavg20) && vavg20 > 0) ? (vavg5 / vavg20) : 1;
    const hi = Number(highD[i]);
    const lo = Number(lowD[i]);
    const hl = (Number.isFinite(hi) && Number.isFinite(lo)) ? (hi - lo) : 0;
    const volatility = (close > 0) ? (hl / close) : 0;
    const retN = (n) => {
      const j = i - n;
      const cj = j >= 0 ? Number(closeD[j]) : NaN;
      return (Number.isFinite(cj) && cj > 0 && close > 0) ? (close / cj - 1) : 0;
    };
    const ret5 = retN(5);
    const ret20 = retN(20);
    const dist_sma20 = (Number.isFinite(sma20[i]) && sma20[i] > 0 && close > 0) ? (close / sma20[i] - 1) : 0;
    const dist_sma60 = (Number.isFinite(sma60[i]) && sma60[i] > 0 && close > 0) ? (close / sma60[i] - 1) : 0;
    const trend_strength = (Number.isFinite(sma20[i]) && Number.isFinite(sma60[i]) && close > 0) ? ((sma20[i] - sma60[i]) / close) : 0;
    const start14 = Math.max(0, i - 14);
    const hl14 = highD.slice(start14, i).map((x, k) => Number(x) - Number(lowD[start14 + k]));
    const hl14f = hl14.filter(Number.isFinite);
    const atr14 = (hl14f.length && close > 0) ? ((hl14f.reduce((a, b) => a + b, 0) / hl14f.length) / close) : 0;
    const price = close;

    return {
      daily_change, uptrend, rsi14,
      breakout20, breakout_ratio, breakout60, breakout60_ratio,
      volume_surge, volume_surge5, volume_surge60, volume_trend_5_20,
      volatility, atr14, ret5, ret20, dist_sma20, dist_sma60, trend_strength, price
    };
  };
  const hitalkScoreSetups = (closeD, highD, lowD, volD, idx) => {
    const feats = hitalkFeaturesFromDaily(closeD, highD, lowD, volD, idx);
    const featArr = HITALK_UP_MODEL.feature_cols.map((k) => Number(feats[k]) || 0);
    const pUP = hitalkPredictBin(HITALK_UP_MODEL, featArr);
    const pMAT = hitalkPredictBin(HITALK_MAT_MODEL, featArr);
    return { pUP, pMAT };
  };
  // ===== /HiTalk Setup Models =====

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
  // Auto-reset circuit at first scan (09:10) to ensure fresh start
  const isFirstScan = (h === 9 && m >= 10 && m < 15);
  const circuitActive = !!(circuitUntilMs && circuitUntilMs > nowMs && ks.circuitDate === today && !isFirstScan);
  if (isFirstScan && ks.circuitUntil) {
    // Reset circuit breaker at first scan of the day
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

  // cache-first
  if (store.krxUniverseCache && store.krxUniverseCache.trdDd === trdDd && Array.isArray(store.krxUniverseCache.rows) && store.krxUniverseCache.rows.length) {
    rows = store.krxUniverseCache.rows;
    krxUniverseSource = 'cache';
  } else {
    // Fetch full stock list from Naver Finance (all KOSPI + KOSDAQ stocks)
    krxUniverseSource = 'naver';

    const fetchText = async (url) => {
      const raw = await http({
        method: 'GET',
        url,
        headers: { 
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 
          'Referer': 'https://finance.naver.com/',
          'Accept': 'text/html',
          'Accept-Charset': 'utf-8'
        },
        json: false,
        encoding: 'utf8'
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
    const MAX_PAGES = 30; // Fetch all pages to get complete list

    const fetchAllFromMarket = async (sosok, mktNm) => {
      for (let p = 1; p <= MAX_PAGES; p++) {
        try {
          const url = `https://finance.naver.com/sise/sise_market_sum.naver?sosok=${sosok}&page=${p}`;
          const html = await fetchText(url);
          const pairs = extractCodeNamePairs(html);
          
          if (!pairs || pairs.length === 0) {
            break; // No more pages
          }
          
          let newStocks = 0;
          for (const [c, nm] of pairs) {
            if (!c || codeSet.has(c)) continue;
            codeSet.add(c);
            naverRows.push({
              ISU_SRT_CD: c,
              ISU_ABBRV: nm || c,
              ISU_NM: nm || c,
              MKT_NM: mktNm,
              TDD_CLSPRC: String(MIN_PRICE),
              ACC_TRDVAL: String(MIN_INTRADAY_TURNOVER),
            });
            newStocks++;
          }
          
          if (newStocks === 0) {
            break; // No new stocks, end of list
          }
          
          await new Promise((r) => setTimeout(r, 100 + Math.floor(Math.random() * 50)));
        } catch (e) {
          // Page error, continue to next
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
        // Cache the full universe for the day
        store.krxUniverseCache = {
          trdDd,
          fetchedAt: new Date(nowMs).toISOString(),
          source: 'naver',
          rows: rows.slice(0, 5000).map((x) => ({
            ISU_SRT_CD: String(x?.ISU_SRT_CD || ''),
            ISU_ABBRV: String(x?.ISU_ABBRV || ''),
            ISU_NM: String(x?.ISU_NM || ''),
            MKT_NM: String(x?.MKT_NM || ''),
            TDD_CLSPRC: String(x?.TDD_CLSPRC || '0'),
            ACC_TRDVAL: String(x?.ACC_TRDVAL || '0'),
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
    // limited live attempt
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
            trdDd,
            fetchedAt: new Date(nowMs).toISOString(),
            rows: rows.slice(0, 5000).map((x) => ({
              ISU_SRT_CD: String(x?.ISU_SRT_CD || ''),
              ISU_ABBRV: String(x?.ISU_ABBRV || x?.ISU_NM || ''),
              ISU_NM: String(x?.ISU_NM || ''),
              MKT_NM: String(x?.MKT_NM || ''),
              TDD_CLSPRC: String(x?.TDD_CLSPRC || '0'),
              ACC_TRDVAL: String(x?.ACC_TRDVAL || '0'),
            })),
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

  // naver fallback
  if (!rows || rows.length === 0) {
    const fetchText = async (url) => {
      const raw = await http({
        method: 'GET',
        url,
        headers: { 
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 
          'Referer': 'https://finance.naver.com/',
          'Accept': 'text/html',
          'Accept-Charset': 'utf-8'
        },
        json: false,
        encoding: 'utf8'
      });
      if (Buffer.isBuffer(raw)) return raw.toString('utf8');
      return String(raw ?? '');
    };

    const extractCodeNamePairs = (html) => {
      const out = [];
      const re = new RegExp('/item/main\.naver\?code=(\d{6})[^>]*>([^<]{1,60})<', 'g');
      let m;
      while ((m = re.exec(html))) out.push([m[1], String(m[2] || '').trim()]);
      return out;
    };

    const MAX_PAGES = 3;
    const codeSet = new Set();
    const naverRows = [];
    const addFromMarket = async (sosok, mktNm) => {
      for (let p = 1; p <= MAX_PAGES; p++) {
        const url = `https://finance.naver.com/sise/sise_quant.nhn?sosok=${sosok}&page=${p}`;
        const html = await fetchText(url);
        const pairs = extractCodeNamePairs(html);
        for (const [c, nm] of pairs) {
          if (!c || codeSet.has(c)) continue;
          codeSet.add(c);
          naverRows.push({
            ISU_SRT_CD: c,
            ISU_ABBRV: nm || c,
            ISU_NM: nm || c,
            MKT_NM: mktNm,
            TDD_CLSPRC: String(MIN_PRICE),
            ACC_TRDVAL: String(MIN_INTRADAY_TURNOVER),
          });
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


  for (let i = 0; i < rows.length; i++) {
    const row = rows[i] || {};
    const rc = normalize(String(row.ISU_SRT_CD || ''));
    const nm = String(row.ISU_ABBRV || row.ISU_NM || '').trim();
    const mkt = String(row.MKT_NM || '').toLowerCase();

    if (mkt.includes('konex') || mkt.includes('코넥스')) continue;

    const price = Number((row.TDD_CLSPRC || '0').replace(/,/g, ''));
    const turnover = Number((row.ACC_TRDVAL || '0').replace(/,/g, ''));

    if (!rc || !nm) continue;
    if (SEEN_CODES.has(rc)) continue;
    SEEN_CODES.add(rc);

    // 선제 제외: 리스크/테마 종목
    if (riskSet.has(rc)) { excludedRisk++; continue; }
    if (themeSet.has(rc)) { excludedTheme++; continue; }

    if (price < MIN_PRICE) continue;
    if (turnover < MIN_INTRADAY_TURNOVER) continue;

    NAME[rc] = nm;
    let suffix = '.KS';
    if (mkt.includes('kosdaq') || mkt.includes('코스닥')) suffix = '.KQ';
    ALL_TICKERS.push(rc + suffix);
  }

  if (ALL_TICKERS.length === 0) {
    if (!store.swingAlerts) store.swingAlerts = {};
    const msg = '[시스템 경고] KRX 종목 데이터 로드 실패' + NL + kst.toISOString().slice(0, 16).replace('T', ' ') + ' KST';
    store.swingAlerts.noHitDate = today;
    try {
      await http({
        method: 'POST',
        url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
        json: true,
        body: { chat_id: CHAT, text: msg },
      });
    } catch (e) {}
    return [{ json: { error: 'Failed to load KRX universe' } }];
  }

  // (sma 중복 선언 제거됨 - 상단의 sma 사용)

  // ===== Debug counters (Yahoo) =====
  let naverOkCount = 0;
  let naverNoResultCount = 0;
  let naverErrorCount = 0;
  const naverErrorByStatus = {};
  const naverErrorSamples = [];
  const pickStatus = (e) => {
    const s = e?.statusCode ?? e?.response?.statusCode ?? e?.response?.status ?? e?.httpCode ?? e?.cause?.statusCode;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  };
  // ===== /Debug counters (Yahoo) =====


  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const dayKey = new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 10);
  const naverCache = store.naverCache || (store.naverCache = { intra: {}, daily: {}, dayKey: null });
  if (naverCache.dayKey !== dayKey) {
    naverCache.intra = {};
    naverCache.daily = {};
    naverCache.dayKey = dayKey;
  }
  const getCached = (bucket, key, maxAgeMs) => {
    const v = bucket[key];
    if (!v) return null;
    if (Date.now() - v.at > maxAgeMs) return null;
    return v.data;
  };
  const setCached = (bucket, key, data) => {
    bucket[key] = { at: Date.now(), data };
  };

  const fetchIntra = async (code, pageSize) => {
    const url = `https://m.stock.naver.com/api/stock/${code}/price?pageSize=${pageSize}&page=1`;
    return await http({
      method: 'GET',
      url,
      json: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://finance.naver.com/',
        'Accept': 'application/json',
        'Accept-Charset': 'utf-8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8'
      },
      encoding: 'utf8'
    });
  };

  const httpIntra = async (t) => {
    const code = t.replace(/\.KS$/, '').replace(/\.KQ$/, '');
    const cached = getCached(naverCache.intra, code, 30 * 60 * 1000);
    if (cached) return cached; // [PERF] Cache-first: API 호출 생략
    try {
      let resp = await fetchIntra(code, 60);
      if (!Array.isArray(resp) || resp.length === 0) {
        await sleep(200);
        resp = await fetchIntra(code, 120);
      }
      if (!Array.isArray(resp) || resp.length === 0) {
        if (cached) return cached;
        return { chart: { result: null, error: { description: 'No intraday data from Naver' } } };
      }
      const timestamps = resp.map(d => new Date(d.localTradedAt).getTime() / 1000);
      const opens = resp.map(d => parseFloat(String(d.openPrice || '0').replace(/,/g, '')));
      const highs = resp.map(d => parseFloat(String(d.highPrice || '0').replace(/,/g, '')));
      const lows = resp.map(d => parseFloat(String(d.lowPrice || '0').replace(/,/g, '')));
      const closes = resp.map(d => parseFloat(String(d.closePrice || '0').replace(/,/g, '')));
      const volumes = resp.map(d => parseInt(String(d.accumulatedTradingVolume || '0').replace(/,/g, ''), 10));
      const chart = { chart: { result: [{ meta: { symbol: t, currency: 'KRW', regularMarketPrice: closes[0] }, timestamp: timestamps.reverse(), indicators: { quote: [{ open: opens.reverse(), high: highs.reverse(), low: lows.reverse(), close: closes.reverse(), volume: volumes.reverse() }] } }], error: null } };
      setCached(naverCache.intra, code, chart);
      return chart;
    } catch (e) {
    // [FIX] 400/404 error fast-fail
    const status = e?.statusCode ?? e?.response?.statusCode ?? e?.response?.status;
    if (status === 400 || status === 404) {
      const emptyResult = { chart: { result: null, error: { description: `Invalid code: ${status}` } } };
      setCached(naverCache.intra, code, emptyResult);
      return emptyResult;
    }
      if (cached) return cached;
      return { chart: { result: null, error: { description: String(e?.message || e) } } };
    }
  };

  const fetchDaily = async (code, startDate, endDate) => {
    const url = `https://api.stock.naver.com/chart/domestic/item/${code}/day?startDateTime=${startDate}&endDateTime=${endDate}`;
    return await http({
      method: 'GET',
      url,
      json: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://finance.naver.com/',
        'Accept': 'application/json',
        'Accept-Charset': 'utf-8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8'
      },
      encoding: 'utf8'
    });
  };

  const httpDaily = async (t) => {
    const code = t.replace(/\.KS$/, '').replace(/\.KQ$/, '');
    const cached = getCached(naverCache.daily, code, 60 * 60 * 1000); // [PERF] 60min TTL
    if (cached) return cached; // [PERF] Cache-first: API 호출 생략
    try {
      const kst = new Date(Date.now() + 9 * 3600000);
      const endDate = kst.toISOString().slice(0, 10).replace(/-/g, '');
      const startKst = new Date(kst.getTime() - 365 * 24 * 3600000);
      const startDate = startKst.toISOString().slice(0, 10).replace(/-/g, '');
      let resp = await fetchDaily(code, startDate, endDate);
      if (!Array.isArray(resp) || resp.length === 0) {
        await sleep(200);
        const startKstAlt = new Date(kst.getTime() - 180 * 24 * 3600000);
        const startDateAlt = startKstAlt.toISOString().slice(0, 10).replace(/-/g, '');
        resp = await fetchDaily(code, startDateAlt, endDate);
      }
      if (!Array.isArray(resp) || resp.length === 0) {
        if (cached) return cached;
        return { chart: { result: null, error: { description: 'No data from Naver' } } };
      }
      const timestamps = resp.map(d => new Date(d.localDate.slice(0,4) + '-' + d.localDate.slice(4,6) + '-' + d.localDate.slice(6,8)).getTime() / 1000);
      const opens = resp.map(d => d.openPrice);
      const highs = resp.map(d => d.highPrice);
      const lows = resp.map(d => d.lowPrice);
      const closes = resp.map(d => d.closePrice);
      const volumes = resp.map(d => d.accumulatedTradingVolume);
      const chart = { chart: { result: [{ meta: { symbol: t, currency: 'KRW', regularMarketPrice: closes[closes.length - 1] }, timestamp: timestamps, indicators: { quote: [{ open: opens, high: highs, low: lows, close: closes, volume: volumes }] } }], error: null } };
      setCached(naverCache.daily, code, chart);
      return chart;
    } catch (e) {
    // [FIX] 400/404 error fast-fail
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

  const candidates = [];
  const BATCH_SIZE = 20; // 최적화: 병렬 처리 효율화

  // [PERF] Execution Time Guard: 8분 초과 시 중단
  const _EXEC_START = Date.now();
  const _MAX_EXEC_MS = 8 * 60 * 1000;
  let _batchCount = 0;
  for (let i = 0; i < ALL_TICKERS.length; i += BATCH_SIZE) {
    if (Date.now() - _EXEC_START > _MAX_EXEC_MS) break;
    _batchCount++;
    const batch = ALL_TICKERS.slice(i, i + BATCH_SIZE);
    await Promise.all(
      batch.map(async (t) => {
        try {
          if (store.swingSent[t]) return;
          if (store.scalpingSent && store.scalpingSent[t]) return;

          const [cIntra, cDaily] = await Promise.all([httpIntra(t), httpDaily(t)]);
        const errIntra = cIntra?.chart?.error?.description;
        const errDaily = cDaily?.chart?.error?.description;
        const noDataIntra = errIntra && String(errIntra).includes('No intraday data');
        const noDataDaily = errDaily && String(errDaily).includes('No data from Naver');
        if ((errIntra || errDaily) && !(noDataIntra || noDataDaily)) {
          naverErrorCount++;
          if (naverErrorSamples.length < 3) {
            naverErrorSamples.push({ ticker: t, intra: errIntra || null, daily: errDaily || null });
          }
        }
          const rIntra = cIntra && cIntra.chart && cIntra.chart.result && cIntra.chart.result[0];
          const rDaily = cDaily && cDaily.chart && cDaily.chart.result && cDaily.chart.result[0];
          if (!rIntra || !rDaily) { naverNoResultCount++; return; }
        naverOkCount++;

          const qI = (rIntra.indicators && rIntra.indicators.quote && rIntra.indicators.quote[0]) || {};
          const qD = (rDaily.indicators && rDaily.indicators.quote && rDaily.indicators.quote[0]) || {};

          const close30m = (qI.close || []).map(Number).filter((v) => v > 0);
          const closeD = (qD.close || []).map(Number).filter((v) => v > 0);
          const highD = (qD.high || []).map(Number).filter((v) => v > 0);
          const lowD = (qD.low || []).map(Number).filter((v) => v > 0);
          const volD = (qD.volume || []).map(Number).filter((v) => v >= 0);

          if (close30m.length < 30 || closeD.length < 60) return;

          let lastIdx = (qI.close || []).length - 1;
          while (lastIdx >= 0 && !(Number((qI.close || [])[lastIdx]) > 0)) lastIdx--;
          const currentPrice = Number((qI.close || [])[lastIdx] || close30m[close30m.length - 1]);

          const tsDaily = (rDaily.timestamp || []).map((t) => {
            const d = new Date(t * 1000 + 9 * 60 * 60 * 1000);
            return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
          });

          const idxToday = tsDaily.indexOf(today);
          const prevClose = idxToday > 0 ? closeD[idxToday - 1] : closeD[closeD.length - 2] || closeD[closeD.length - 1];
          const dailyChange = currentPrice / prevClose - 1;

          if (currentPrice < MIN_PRICE) return;

          const sma20_d = sma(closeD, 20);
          const sma60_d = sma(closeD, 60);
          const dIdx = closeD.length - 1;

          let score = 0;
          const signals = [];

          const dailyUptrend = sma20_d[dIdx] > sma60_d[dIdx];
          if (!dailyUptrend) return;
          score += 15;
          signals.push('일봉정배열');

          const recent20High = Math.max(...highD.slice(dIdx - 20, dIdx));
          const boxBreakout = currentPrice > recent20High;
          if (boxBreakout) {
            score += 35;
            signals.push('박스권돌파(20일)');
          }

          const recent10High = Math.max(...highD.slice(dIdx - 10, dIdx));
          const nPattern = recent10High > currentPrice * 1.15 && Math.abs(currentPrice - sma20_d[dIdx]) / currentPrice < 0.03;
          if (nPattern) {
            score += 40;
            signals.push('N자형눌림목');
          }

          const cupHandle = detectCupAndHandle(closeD, highD, lowD, dIdx);
          if (cupHandle.detected) {
            score += 40;
            signals.push('컵핸들');
          }

          if (score < RELAX_SCORE) return;

          const type = '스윙';
          const entry = currentPrice;

          // HiTalk setup scoring (MAT=스윙/재료 스타일)
          const featIdx = Math.max(60, Math.min(idxToday >= 0 ? idxToday : dIdx, closeD.length - 1));
          const idxUse = featIdx;
          const setup = hitalkScoreSetups(closeD, highD, lowD, volD, featIdx);
          const pMAT = setup.pMAT;

          if (pMAT < PMAT_RELAX) return;

          const targetRate = Math.min(HITALK_SETUP_CFG.MAT.targetRate, 0.25);
          const stopRate = Math.min(HITALK_SETUP_CFG.MAT.stopRate, 0.10);
          const predType = '재료';
          const predProb = pMAT;
          const rankScore = pMAT * 100 + score;
          const strictPass = (pMAT >= PMAT_STRICT) && (score >= MIN_SCORE);
          const relaxedPass = (pMAT >= PMAT_RELAX) && (score >= RELAX_SCORE);
          if (!strictPass) signals.push('완화');

          const atrAbs = calcAtrAbs(highD, lowD, idxUse, ATR_WINDOW);
          let stop = entry - atrAbs * ATR_STOP_MULT;
          let target = entry + atrAbs * ATR_TARGET_MULT;
          const stopCap = entry * (1 - CAP_STOP_PCT);
          const targetCap = entry * (1 + CAP_TARGET_PCT);
          if (Number.isFinite(stopCap)) stop = Math.max(stop, stopCap);
          if (Number.isFinite(targetCap)) target = Math.min(target, targetCap);

          const rg = await getMarketRegime(store, today);
          const riskOn = !!(rg && rg.riskOn);
          const sizeFactor = riskOn ? 1.0 : 0.5;
          const qty = calcQty(ACCOUNT_KRW, RISK_PCT_PER_TRADE * sizeFactor, entry, stop);

          const code = normalize(getCode(t));
          const name = NAME[code] || code;
          const mkt = t.endsWith('.KS') ? 'KOSPI' : 'KOSDAQ';

          candidates.push({
            ticker: t,
            code,
            name,
            market: mkt,
            entry,
            target,
            stop,
            score,
            signals,
            dailyChange,
            currentPrice,
            prevClose,
            timeStr: timeStrNow,
            type,
            predType,
            predProb,
            rankScore,
            atrAbs,
            riskOn,
            qty,
            strictPass,
            relaxedPass,
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
      })
    );
  }

  const noResultAll = (ALL_TICKERS.length > 0 && naverNoResultCount === ALL_TICKERS.length);
  // 장 시간 체크: 09:05 ~ 15:25 KST에만 경고 발송 (장외 시간 빈 결과는 정상)
  const alertHour = kst.getUTCHours();
  const alertMin = kst.getUTCMinutes();
  const isMarketTimeForAlert = (alertHour > 9 || (alertHour === 9 && alertMin >= 5)) && 
                               (alertHour < 15 || (alertHour === 15 && alertMin < 25));
  if (noResultAll && isMarketTimeForAlert) {
    if (!store.naverAlerts) store.naverAlerts = {};
    if (store.naverAlerts.noResultAllDate !== today) {
      const msg =
        '⚠️ [데이터 경고] Naver 응답이 전 종목 빈 결과' + NL +
        `- KST: ${today} ${timeStrNow}` + NL +
        `- universe: ${ALL_TICKERS.length}` + NL +
        `- Naver OK/NoResult/Error: ${naverOkCount}/${naverNoResultCount}/${naverErrorCount}`;
      try { await http({ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage', json: true, body: { chat_id: CHAT, text: msg } }); } catch (e) {}
      store.naverAlerts.noResultAllDate = today;
    }
  }
  if (naverErrorCount > 0) {
    if (!store.naverAlerts) store.naverAlerts = {};
    const last = Number(store.naverAlerts.lastErrorAt || 0);
    const nowMs = Date.now();
    if (nowMs - last > 30 * 60 * 1000) {
      const sample = (naverErrorSamples && naverErrorSamples.length) ? JSON.stringify(naverErrorSamples.slice(0, 2)) : 'none';
      const msg =
        '⚠️ [데이터 오류] 스캔 중 에러 발생' + NL +
        `- KST: ${today} ${timeStrNow}` + NL +
        `- Naver OK/NoResult/Error: ${naverOkCount}/${naverNoResultCount}/${naverErrorCount}` + NL +
        `- sample: ${sample}`;
      try { await http({ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage', json: true, body: { chat_id: CHAT, text: msg } }); } catch (e) {}
      store.naverAlerts.lastErrorAt = nowMs;
    }
  }

  candidates.sort((a, b) => (b.rankScore || b.score) - (a.rankScore || a.score));
  const strictSelected = candidates.filter((c) => c.strictPass).slice(0, MAX_INTRADAY_SENDS);
  const selected = strictSelected;
  if (selected.length < MIN_DAILY_PICKS) {
    const need = Math.min(MIN_DAILY_PICKS - selected.length, MAX_INTRADAY_SENDS - selected.length);
    if (need > 0) {
      const used = new Set(selected.map((x) => x.ticker));
      const fillers = candidates.filter((c) => !used.has(c.ticker) && c.relaxedPass).slice(0, need);
      for (const f of fillers) selected.push(f);
    }
  }
  const sent = [];
  let sendFailCount = 0;
  const sendFailSamples = [];

  const send = async (c) => {
    const kstNow = new Date(Date.now() + 9 * 60 * 60 * 1000);
    const timeStr = String(kstNow.getUTCHours()).padStart(2, '0') + ':' + String(kstNow.getUTCMinutes()).padStart(2, '0');

    const entryNow = c.currentPrice;
    const targetNow = c.target;
    const stopNow = c.stop;

    const dailyChangeNow = c.prevClose && c.prevClose > 0 ? entryNow / c.prevClose - 1 : null;
    const dailyChangeText = Number.isFinite(dailyChangeNow) ? ' (전일 대비 ' + pct(dailyChangeNow) + ')' : '';

    const msg =
      '[장중 스윙 포착] ' + c.market + ' | ' + esc(c.name) + ' (' + c.code + ')' + NL +
      '포착 시각: ' + timeStr + ' KST' + NL +
      '예측유형: ' + (c.predType || 'N/A') + (c.predProb ? ' (' + Math.round(c.predProb * 100) + '%)' : '') + NL +
      '현재가: ' + to0(entryNow) + '원' + dailyChangeText + NL +
      '- 매수가: ' + to0(entryNow) + '원' + NL +
      '- 목표가: ' + to0(targetNow) + '원 (+' + pct(targetNow / entryNow - 1) + ')' + NL +
      '- 손절가: ' + to0(stopNow) + '원 (-' + pct(1 - stopNow / entryNow) + ')' + NL +
      '레짐: ' + (c.riskOn ? '양호' : '주의(사이징 50%)') + NL +
      'ATR(14): ' + (Number.isFinite(c.atrAbs) ? (to0(c.atrAbs) + '원') : 'N/A') + NL +
      '권장수량: ' + (c.qty ? (to0(c.qty) + '주 (약 ' + to0(c.qty * entryNow) + '원)') : '0주(계좌/리스크 설정 확인)') + NL +
      '- 점수: ' + c.score + '점' + NL +
      '핵심 시그널: ' + (c.signals.slice(0, 3).join(', ') || 'N/A') + NL +
      '면책: 본 알림은 정보 제공 목적이며 투자 손익은 본인 책임입니다.';

    try {
      await http({
        method: 'POST',
        url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
        json: true,
        body: { chat_id: CHAT, text: msg, parse_mode: 'HTML' },
      });
      return { entry: entryNow, target: targetNow, stop: stopNow };
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
  // [FIX] Memory leak: clean old dates (keep last 14 days only)
  const cutoffDate = new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000);
  const cutoffStr = `${cutoffDate.getFullYear()}-${String(cutoffDate.getMonth()+1).padStart(2,'0')}-${String(cutoffDate.getDate()).padStart(2,'0')}`;
  for (const dateKey in store.weeklyRecommendations) {
    if (dateKey < cutoffStr) delete store.weeklyRecommendations[dateKey];
  }
      if (!store.weeklyRecommendations[today2]) store.weeklyRecommendations[today2] = [];

      store.weeklyRecommendations[today2].push({
        type: 'swing',
        subType: selected[i].type,
        ticker: selected[i].ticker,
        code: selected[i].code,
        name: selected[i].name,
        entry: res.entry,
        target: res.target,
        stop: res.stop,
        holdingDays: 1,
        score: selected[i].score,
      });

      sent.push(selected[i].ticker);
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  if (sendFailCount > 0) {
    if (!store.telegramAlerts) store.telegramAlerts = {};
    const last = Number(store.telegramAlerts.swingSendFailAt || 0);
    const nowMs = Date.now();
    if (nowMs - last > 30 * 60 * 1000) {
      const sample = (sendFailSamples && sendFailSamples.length) ? JSON.stringify(sendFailSamples.slice(0, 2)) : 'none';
      const msg = '⚠️ [발송 오류] 스윙 알림 전송 실패' + NL +
        `- KST: ${today} ${timeStrNow}` + NL +
        `- failCount: ${sendFailCount}` + NL +
        `- sample: ${sample}`;
      try { await http({ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage', json: true, body: { chat_id: CHAT, text: msg } }); } catch (e) {}
      store.telegramAlerts.swingSendFailAt = nowMs;
    }
  }

  if (selected.length === 0) {
    if (!store.swingAlerts) store.swingAlerts = {};
    if (store.swingAlerts.noHitDate === today) return [{ json: { skipped: true, reason: 'No hit (already notified today)' } }];
    const msg =
      '[디버그] 스캔 완료 (발견: 0건)' + NL +
      '- 총 분석 종목(필터 후): ' + ALL_TICKERS.length + '개' + NL +
      '- 1차 후보: ' + candidates.length + '개' + NL +
      '- 제외(리스크): ' + excludedRisk + '개' + NL +
      '- 제외(테마): ' + excludedTheme + '개' + NL +
      '- riskCacheAt: ' + (riskCacheAt || 'null') + NL +
      '- themeCacheAt: ' + (themeCacheAt || 'null') + NL +
      '- Naver OK/NoResult/Error: ' + naverOkCount + '/' + naverNoResultCount + '/' + naverErrorCount + NL +
      '- Naver err status: ' + (Object.keys(naverErrorByStatus).slice(0,4).map(k=>k+':' + naverErrorByStatus[k]).join(', ') || 'none') + NL +
      '- 시각: ' + timeStrNow + ' KST';

    try {
      await http({
        method: 'POST',
        url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
        json: true,
        body: { chat_id: CHAT, text: msg },
      });
    } catch (e) {}
    store.swingAlerts.noHitDate = today;
  }

  store.swingMeta._lastFullFinish = Date.now(); // [PERF] Queue 적체 방지용
  return [
    {
      json: {
        scanTime: kst.toISOString(),
        totalUniverse: ALL_TICKERS.length,
        candidates: candidates.length,
        sent: sent.length,
        sentTickers: sent,
        excludedRisk,
        excludedTheme,
        riskCacheAt,
        themeCacheAt,
        naverOkCount,
        naverNoResultCount,
        naverErrorCount,
        naverErrorByStatus,
        naverErrorSamples,
      },
    },
  ];
};

return run();
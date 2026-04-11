const run = async function () {
  const BOT = '8366696724:AAHROcjGoQEn9BziD-sYdAu3ZuaolwtkgLE';
  const CHAT = '523002062';
  const MIN_PRICE = 1000;
  const MIN_INTRADAY_TURNOVER = 1000000000;
  const MIN_SCORE = 70;
  const MAX_INTRADAY_SENDS = 6;
  const HOLIDAYS = ['2025-01-01','2025-01-28','2025-01-29','2025-01-30','2025-03-01','2025-03-03','2025-05-05','2025-05-06','2025-06-06','2025-08-15','2025-10-03','2025-10-06','2025-10-07','2025-10-08','2025-10-09','2025-12-25','2026-01-01','2026-02-16','2026-02-17','2026-02-18','2026-03-01','2026-03-02','2026-04-30','2026-05-05','2026-05-25','2026-06-06','2026-08-15','2026-09-24','2026-09-25','2026-09-26','2026-10-03','2026-10-05','2026-12-25'];
  const DUPLICATE_WINDOW_MINUTES = 60;
  const STOP_NEW_ALERTS_HOUR = 15;
  const STOP_NEW_ALERTS_MINUTE = 20;
  const http = async (o) => await this.helpers.httpRequest(Object.assign({ timeout: 30000 }, o));
  const input = items && items[0] && items[0].json || {};
  const forceTest = !!input.forceTest;
  const debugMode = !!input.debugMode;
  const now = new Date();
  const kst = new Date(now.getTime() + 9*60*60*1000);
  const NL = String.fromCharCode(10);
  const esc = (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  if (forceTest) {
    let krxStatus = '미확인';
    let krxCount = 0;
    const timeInfo = 'Server: ' + now.toISOString() + '\nKST: ' + kst.toISOString().replace('T', ' ').slice(0, 19);
    
    try {
        const headers={ 'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8', 'Origin':'https://data.krx.co.kr', 'Referer':'https://data.krx.co.kr/contents/MDC/CM/MDI/mdiLoader/index.cmd', 'X-Requested-With':'XMLHttpRequest', 'User-Agent':'Mozilla/5.0' };
        const todayStr = `${kst.getUTCFullYear()}${String(kst.getUTCMonth()+1).padStart(2,'0')}${String(kst.getUTCDate()).padStart(2,'0')}`;
        const body=`bld=dbms/MDC/STAT/standard/MDCSTAT01501&mktId=ALL&trdDd=${todayStr}&share=1&money=1&csvxls_isNo=false`;
        const r = await http({ method:'POST', url:'https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd', headers, body, json:true });
        const rows = (r && (r.output || r.OutBlock_1 || [])) || [];
        krxCount = rows.length;
        krxStatus = krxCount > 0 ? '성공 (' + krxCount + '개)' : '실패 (0건/휴일가능성)';
    } catch (e) {
        krxStatus = '에러: ' + e.message;
    }
    
    const msg = '[진단 모드] 시스템 점검 결과\n' 
        + '⏰ 시간 설정: ' + (timeInfo.includes('KST') ? '정상' : '확인 필요') + '\n' + timeInfo + '\n'
        + '📊 KRX 데이터: ' + krxStatus + '\n'
        + '📡 텔레그램: 정상 발송됨';
        
    try { await http({ method:'POST', url:'https://api.telegram.org/bot'+BOT+'/sendMessage', json:true, body:{ chat_id:CHAT, text:msg } }); } 
    catch(e) { return [{ json: { testSent: false, error: e.message } }]; }
    
    return [{ json: { testSent: true, krxStatus, timeInfo } }];
  }
  const d = kst.getUTCDay(); const h = kst.getUTCHours(); const m = kst.getUTCMinutes();
  if (!(d >= 1 && d <= 5)) return [{ json: { skipped: true, reason: 'Weekend' } }];
  const today = `${kst.getUTCFullYear()}-${String(kst.getUTCMonth()+1).padStart(2,'0')}-${String(kst.getUTCDate()).padStart(2,'0')}`;
  if (HOLIDAYS.includes(today)) return [{ json: { skipped: true, reason: 'Holiday (KRX closed)' } }];
  if (h < 9) return [{ json: { skipped: true, reason: 'Before market open' } }];
  if (h === 9 && m < 10) return [{ json: { skipped: true, reason: 'Market open volatility (09:00-09:10)' } }];
  if (h >= 16) return [{ json: { skipped: true, reason: 'After market close' } }];
  if (h > STOP_NEW_ALERTS_HOUR || (h === STOP_NEW_ALERTS_HOUR && m >= STOP_NEW_ALERTS_MINUTE)) {
    return [{ json: { skipped: true, reason: 'Too close to market close' } }];
  }
  const store = this.getWorkflowStaticData('global');
  if (!store.scalpingSent) store.scalpingSent = {};
  if (!store.weeklyRecommendations) store.weeklyRecommendations = {};
  if (!store.weeklyRecommendations[today]) store.weeklyRecommendations[today] = [];
  const cleanOldHistory = () => {
    const cutoff = now.getTime() - DUPLICATE_WINDOW_MINUTES * 60 * 1000;
    for (const ticker in store.scalpingSent) { if (store.scalpingSent[ticker] < cutoff) delete store.scalpingSent[ticker]; }
  };
  cleanOldHistory();
  const to0 = (n) => Math.round(Number(n) || 0).toLocaleString('ko-KR');
  const getCode = (sym)=>{ const v=String(sym); if(v.endsWith('.KS')||v.endsWith('.KQ')) return v.slice(0,-3); return v; };
  const normalize = (s)=> String(s||'').trim();
  const pct = (r)=> ((r*100).toFixed(1) + '%');
  // ===== HiTalk Setup Models (auto) =====
  const HITALK_UP_MODEL = {"name":"SETUP_UP(단타=급등)","feature_cols":["daily_change","uptrend","rsi14","breakout20","breakout_ratio","breakout60","breakout60_ratio","volume_surge","volume_surge5","volume_surge60","volume_trend_5_20","volatility","atr14","ret5","ret20","dist_sma20","dist_sma60","trend_strength","price"],"scaler":{"mean":[0.03941112323492713,0.5543478260869565,56.545286976615934,0.16897233201581027,0.9125539688024894,0.09387351778656126,0.8444209313001051,7.859869097035799,9.808710474152516,7.407255525593385,1.1741009201441042,0.09152603600351632,0.052841022855268954,0.06693993755172249,0.09917903036869001,0.06651846479725247,0.09049245314562593,0.007006514477785763,35568.01663811122],"scale":[0.08766529491393103,0.49703753761624325,16.889372083821293,0.3747274783478637,0.11615516943446853,0.2916526709031452,0.1404641448755363,28.625067611054348,36.39775002735151,24.425783867182986,0.8121668721832151,0.07127136375745106,0.02481501386636216,0.13977010898417583,0.24293659705155204,0.13241135669408638,0.19540197393809716,0.13715305283752963,95896.01749780211]},"coef":[0.7562683117443777,0.3626442429601983,0.2795871935673176,0.11570148366611886,0.5328372190930989,-0.49562171518787235,-0.0133555000485831,-0.5147492810327007,0.935863691546091,-0.36162297177444197,-0.014914088687825148,1.0185496067021869,0.5814560310633664,0.7469841752968425,-0.5127443495874868,0.6227061707667483,-0.3418990371124205,0.25010246627460375,-1.104266379894277],"intercept":-0.6993095468699385,"meta":{"generatedAt":"2025-12-21T05:54:03.827639Z","rows":1266,"pos":373,"neg":893,"skipped":120,"seed":42,"neg_per_pos":2,"top_turnover":800,"max_days":120},"metrics":{"auc":0.9353445065176909,"report":{"0":{"precision":0.94375,"recall":0.8435754189944135,"f1-score":0.8908554572271387,"support":179.0},"1":{"precision":0.7021276595744681,"recall":0.88,"f1-score":0.7810650887573964,"support":75.0},"accuracy":0.8543307086614174,"macro avg":{"precision":0.822938829787234,"recall":0.8617877094972067,"f1-score":0.8359602729922675,"support":254.0},"weighted avg":{"precision":0.8724048207404926,"recall":0.8543307086614174,"f1-score":0.8584370413404038,"support":254.0}},"confusion_matrix":[[151,28],[9,66]]}};
  const HITALK_MAT_MODEL = {"name":"SETUP_MAT(스윙=재료)","feature_cols":["daily_change","uptrend","rsi14","breakout20","breakout_ratio","breakout60","breakout60_ratio","volume_surge","volume_surge5","volume_surge60","volume_trend_5_20","volatility","atr14","ret5","ret20","dist_sma20","dist_sma60","trend_strength","price"],"scaler":{"mean":[0.021672322309040985,0.6102292768959435,55.54906409815424,0.12698412698412698,0.9044426261918556,0.08465608465608465,0.848404316977533,5.05730837028303,5.9870278883417605,4.935397521137353,1.1624705759072649,0.07390376416270977,0.05358470180620499,0.05517713949198958,0.09110163225026832,0.05955020351996882,0.10858486882914639,0.028491179406826692,41330.92297557044],"scale":[0.07289730273067968,0.487698171531324,16.441425165154502,0.3329551898952858,0.10843488516735644,0.2783692367823469,0.13045534095275263,19.32527938335188,25.39394540728067,18.221408853875058,0.7277593184242444,0.05890488709896314,0.026258386597653047,0.1318396349850443,0.20362394914749846,0.12413112586273757,0.19332765113378547,0.09773438561870854,74861.23768223941]},"coef":[0.6717596961119858,0.6762207689163452,0.39355856590519267,-0.09228167232586969,0.9053624709907248,-0.11319441378647066,-0.0015877478707488962,-0.08994121562855331,0.2922226931482804,-0.36171544831150043,0.2305227581635665,0.31550222939058603,1.374909565887536,0.4119961022129777,-0.7485519331679408,0.7716839454271054,-1.0245614606852167,0.0714910196773468,-0.1523532626149339],"intercept":-0.3607035788307738,"meta":{"generatedAt":"2025-12-21T05:54:03.859639Z","rows":709,"pos":208,"neg":501,"skipped":59,"seed":42,"neg_per_pos":2,"top_turnover":800,"max_days":120},"metrics":{"auc":0.8185714285714285,"report":{"0":{"precision":0.8837209302325582,"recall":0.76,"f1-score":0.8172043010752689,"support":100.0},"1":{"precision":0.5714285714285714,"recall":0.7619047619047619,"f1-score":0.6530612244897959,"support":42.0},"accuracy":0.7605633802816901,"macro avg":{"precision":0.7275747508305648,"recall":0.7609523809523809,"f1-score":0.7351327627825324,"support":142.0},"weighted avg":{"precision":0.7913527677694071,"recall":0.7605633802816901,"f1-score":0.7686549403950586,"support":142.0}},"confusion_matrix":[[76,24],[10,32]]}};
  const HITALK_SETUP_CFG = {"UP":{"targetRate":0.10550000000000001,"stopRate":0.055,"threshold":0.93},"MAT":{"targetRate":0.14155,"stopRate":0.08,"threshold":0.95}};
  const hitalkSigmoid = (x)=> 1/(1+Math.exp(-x));
  const hitalkDot = (w, x)=>{ let s=0; for(let i=0;i<w.length;i++) s += w[i]*x[i]; return s; };
  const hitalkStandardize = (model, featArr)=>{
    const mu = model.scaler.mean;
    const sc = model.scaler.scale;
    const x = new Array(featArr.length);
    for(let i=0;i<featArr.length;i++) x[i] = ((Number(featArr[i])||0) - (mu[i]||0)) / ((sc[i]||1) || 1);
    return x;
  };
  const hitalkPredictBin = (model, featArr)=>{
    const x = hitalkStandardize(model, featArr);
    const z = hitalkDot(model.coef, x) + (model.intercept || 0);
    return hitalkSigmoid(z);
  };
  // feature functions (same as training)
  const hitalkSma = (arr, w)=>{
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
  const hitalkRsi14 = (close)=>{
    const p = 14;
    const out = new Array(close.length).fill(NaN);
    if (close.length < p+1) return out;
    const up=[]; const dn=[];
    for (let i=1;i<close.length;i++){
      const d = Number(close[i]) - Number(close[i-1]);
      up.push(Math.max(d,0)); dn.push(Math.max(-d,0));
    }
    const au = hitalkSma([NaN].concat(up), p);
    const ad = hitalkSma([NaN].concat(dn), p);
    for(let i=0;i<close.length;i++){
      if(!Number.isFinite(au[i]) || !Number.isFinite(ad[i])) continue;
      const rs = (ad[i]===0)?999:(au[i]/ad[i]);
      out[i] = 100 - 100/(1+rs);
    }
    return out;
  };
  const hitalkFeaturesFromDaily = (closeD, highD, lowD, volD, idx)=>{
    const n = closeD.length;
    const i = Math.max(0, Math.min(idx, n-1));
    const close = Number(closeD[i]);
    const prev = i>0 ? Number(closeD[i-1]) : NaN;
    const daily_change = (Number.isFinite(prev)&&prev>0&&close>0)?(close/prev-1):0;
    const sma20 = hitalkSma(closeD,20);
    const sma60 = hitalkSma(closeD,60);
    const uptrend = (Number.isFinite(sma20[i])&&Number.isFinite(sma60[i])&&sma20[i]>sma60[i])?1:0;
    const rsi = hitalkRsi14(closeD);
    const rsi14 = Number.isFinite(rsi[i]) ? rsi[i] : 50;
    const start20 = Math.max(0,i-20);
    const start60 = Math.max(0,i-60);
    const prev20 = (i-start20>=1)?Math.max.apply(null, highD.slice(start20,i).map(Number)) : NaN;
    const prev60 = (i-start60>=1)?Math.max.apply(null, highD.slice(start60,i).map(Number)) : NaN;
    const breakout20 = (Number.isFinite(prev20)&&close>prev20)?1:0;
    const breakout_ratio = (Number.isFinite(prev20)&&prev20>0&&close>0)?(close/prev20):1;
    const breakout60 = (Number.isFinite(prev60)&&close>prev60)?1:0;
    const breakout60_ratio = (Number.isFinite(prev60)&&prev60>0&&close>0)?(close/prev60):1;
    const v20 = volD.slice(start20,i).map(Number).filter(Number.isFinite);
    const vavg20 = v20.length?(v20.reduce((a,b)=>a+b,0)/v20.length):NaN;
    const vtoday = Number(volD[i]);
    const volume_surge = (Number.isFinite(vavg20)&&vavg20>0&&Number.isFinite(vtoday))?(vtoday/vavg20):1;
    const v5 = volD.slice(Math.max(0,i-5),i).map(Number).filter(Number.isFinite);
    const v60 = volD.slice(start60,i).map(Number).filter(Number.isFinite);
    const vavg5 = v5.length?(v5.reduce((a,b)=>a+b,0)/v5.length):NaN;
    const vavg60 = v60.length?(v60.reduce((a,b)=>a+b,0)/v60.length):NaN;
    const volume_surge5 = (Number.isFinite(vavg5)&&vavg5>0&&Number.isFinite(vtoday))?(vtoday/vavg5):1;
    const volume_surge60 = (Number.isFinite(vavg60)&&vavg60>0&&Number.isFinite(vtoday))?(vtoday/vavg60):1;
    const volume_trend_5_20 = (Number.isFinite(vavg5)&&Number.isFinite(vavg20)&&vavg20>0)?(vavg5/vavg20):1;
    const hi = Number(highD[i]); const lo = Number(lowD[i]);
    const hl = (Number.isFinite(hi)&&Number.isFinite(lo))?(hi-lo):0;
    const volatility = (close>0)?(hl/close):0;
    const retN=(n)=>{ const j=i-n; const cj=j>=0?Number(closeD[j]):NaN; return (Number.isFinite(cj)&&cj>0&&close>0)?(close/cj-1):0; };
    const ret5 = retN(5);
    const ret20 = retN(20);
    const dist_sma20 = (Number.isFinite(sma20[i])&&sma20[i]>0&&close>0)?(close/sma20[i]-1):0;
    const dist_sma60 = (Number.isFinite(sma60[i])&&sma60[i]>0&&close>0)?(close/sma60[i]-1):0;
    const trend_strength = (Number.isFinite(sma20[i])&&Number.isFinite(sma60[i])&&close>0)?((sma20[i]-sma60[i])/close):0;
    const start14 = Math.max(0,i-14);
    const hl14 = highD.slice(start14,i).map((x,k)=> Number(x) - Number(lowD[start14+k]));
    const hl14f = hl14.filter(Number.isFinite);
    const atr14 = (hl14f.length&&close>0)?((hl14f.reduce((a,b)=>a+b,0)/hl14f.length)/close):0;
    const price = close;
    return {
      daily_change, uptrend, rsi14,
      breakout20, breakout_ratio, breakout60, breakout60_ratio,
      volume_surge, volume_surge5, volume_surge60, volume_trend_5_20,
      volatility, atr14, ret5, ret20, dist_sma20, dist_sma60, trend_strength, price
    };
  };
  const hitalkScoreSetups = (closeD, highD, lowD, volD, idx)=>{
    const feats = hitalkFeaturesFromDaily(closeD, highD, lowD, volD, idx);
    const featArr = HITALK_UP_MODEL.feature_cols.map(k => Number(feats[k]) || 0);
    const pUP = hitalkPredictBin(HITALK_UP_MODEL, featArr);
    const pMAT = hitalkPredictBin(HITALK_MAT_MODEL, featArr);
    return { pUP, pMAT };
  };
  // ===== /HiTalk Setup Models =====

  const NAME = {};
  const ALL_TICKERS = [];
  const SEEN_CODES = new Set();
  let rows = [];
  for(let attempt=0; attempt<3; attempt++) {
    try {
      const headers={ 'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8', 'Origin':'https://data.krx.co.kr', 'Referer':'https://data.krx.co.kr/contents/MDC/CM/MDI/mdiLoader/index.cmd', 'X-Requested-With':'XMLHttpRequest', 'User-Agent':'Mozilla/5.0' };
      const todayStr = `${kst.getUTCFullYear()}${String(kst.getUTCMonth()+1).padStart(2,'0')}${String(kst.getUTCDate()).padStart(2,'0')}`;
      const body=`bld=dbms/MDC/STAT/standard/MDCSTAT01501&mktId=ALL&trdDd=${todayStr}&share=1&money=1&csvxls_isNo=false`;
      const r = await http({ method:'POST', url:'https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd', headers, body, json:true });
      rows = (r && (r.output || r.OutBlock_1 || [])) || [];
      if (rows.length > 0) break;
    } catch(e) {
      if (attempt === 2) console.log('KRX Load Failed: ' + e.message);
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
  }

  for (let i=0;i<rows.length;i++){
    const row = rows[i] || {};
    const rc = normalize(String(row.ISU_SRT_CD || ''));
    const nm = String(row.ISU_ABBRV || row.ISU_NM || '').trim();
    const mkt = String(row.MKT_NM || '').toLowerCase();
    
    if (mkt.includes('konex') || mkt.includes('코넥스')) continue;

    const price = Number((row.TDD_CLSPRC || '0').replace(/,/g,''));
    const turnover = Number((row.ACC_TRDVAL || '0').replace(/,/g,''));
    
    if (!rc || !nm) continue;
    if (SEEN_CODES.has(rc)) continue;
    SEEN_CODES.add(rc);

    if (price < MIN_PRICE) continue;
    if (turnover < MIN_INTRADAY_TURNOVER) continue;

    NAME[rc] = nm;
    let suffix = '.KS';
    if (mkt.includes('kosdaq') || mkt.includes('코스닥')) suffix = '.KQ';
    ALL_TICKERS.push(rc + suffix);
  }
  
  if (ALL_TICKERS.length === 0) {
    const msg = '⚠️ [시스템 경고] KRX 종목 데이터 로드 실패\\n' + kst.toISOString().slice(0,16).replace('T',' ') + ' KST';
    try { await http({ method:'POST', url:'https://api.telegram.org/bot'+BOT+'/sendMessage', json:true, body:{ chat_id:CHAT, text:msg } }); } catch(e) {}
    return [{ json: { error: 'Failed to load KRX universe' } }];
  }

  const sma = (arr, w) => arr.map((_, i) => { if (i < w - 1) return NaN; let s = 0; for (let k = i - w + 1; k <= i; k++) s += arr[k]; return s / w; });
  const ema = (arr, p) => { const k = 2 / (p + 1); const out = []; for (let i = 0; i < arr.length; i++) { if (i === 0) { out.push(arr[i]); continue; } const prev = out[i - 1]; out.push(prev + k * (arr[i] - prev)); } return out; };
  const rsi = (close, p = 14) => { const up = [], dn = []; for (let i = 1; i < close.length; i++) { const d = close[i] - close[i - 1]; up.push(Math.max(d, 0)); dn.push(Math.max(-d, 0)); } const ma = (a) => a.map((_, i) => i < p - 1 ? NaN : (a.slice(i - p + 1, i + 1).reduce((s, v) => s + v, 0) / p)); const au = ma(up), ad = ma(dn); const out = [NaN]; for (let i = 0; i < au.length; i++) { const rs = (ad[i] || 0) === 0 ? 999 : au[i] / ad[i]; out.push(100 - 100 / (1 + rs)); } return out; };
  const bb = (arr, per = 20, std = 2) => { const m = sma(arr, per); const s = arr.map((_, i) => { if (i < per - 1) return NaN; const win = arr.slice(i - per + 1, i + 1); const mu = m[i]; const v = win.reduce((x, v) => x + Math.pow(v - mu, 2), 0) / per; return Math.sqrt(v); }); return { lower: m.map((v, i) => isNaN(v) ? NaN : v - std * s[i]), mid: m, upper: m.map((v, i) => isNaN(v) ? NaN : v + std * s[i]) }; };
  const vwap = (high, low, close, vol) => { const out = []; let cumVP = 0, cumV = 0; for (let i = 0; i < close.length; i++) { const typ = (high[i] + low[i] + close[i]) / 3; cumVP += typ * vol[i]; cumV += vol[i]; out.push(cumV === 0 ? NaN : cumVP / cumV); } return out; };
  const httpIntra = async (t)=> await http({ method: 'GET', url: 'https://query1.finance.yahoo.com/v8/finance/chart/' + t + '?range=3mo&interval=30m', json: true });
  const httpDaily = async (t)=> await http({ method: 'GET', url: 'https://query1.finance.yahoo.com/v8/finance/chart/' + t + '?range=1y&interval=1d', json: true });
  const candidates = [];
  const BATCH_SIZE = 30;
  for (let i=0; i<ALL_TICKERS.length; i+=BATCH_SIZE){
    const batch = ALL_TICKERS.slice(i, i+BATCH_SIZE);
    await Promise.all(batch.map(async (t) => {
      try {
        if (store.scalpingSent[t]) return;
        if (store.swingSent && store.swingSent[t]) return;

        const [cIntra, cDaily] = await Promise.all([httpIntra(t), httpDaily(t)]);
        const rIntra = cIntra && cIntra.chart && cIntra.chart.result && cIntra.chart.result[0];
        const rDaily = cDaily && cDaily.chart && cDaily.chart.result && cDaily.chart.result[0];
        if (!rIntra || !rDaily) return;
        const qI = (rIntra.indicators && rIntra.indicators.quote && rIntra.indicators.quote[0]) || {};
        const qD = (rDaily.indicators && rDaily.indicators.quote && rDaily.indicators.quote[0]) || {};
        const close30m = (qI.close || []).map(Number).filter(v => v>0);
        const high30m = (qI.high || []).map(Number).filter(v => v>0);
        const low30m  = (qI.low || []).map(Number).filter(v => v>0);
        const vol30m  = (qI.volume || []).map(Number).filter(v => v>=0);
        const closeD  = (qD.close || []).map(Number).filter(v => v>0);
        const volD    = (qD.volume || []).map(Number).filter(v => v>=0);
        const highD   = (qD.high || []).map(Number).filter(v => v>0);
        const lowD    = (qD.low || []).map(Number).filter(v => v>0);
        if (close30m.length < 30 || closeD.length < 60) return;
        const tsIntra = (rIntra.timestamp || []);
        let lastIdx = (qI.close || []).length - 1;
        while (lastIdx >= 0 && !(Number((qI.close || [])[lastIdx]) > 0)) lastIdx--;
        const currentPrice = Number((qI.close || [])[lastIdx] || close30m[close30m.length - 1]);
        const tsDaily = (rDaily.timestamp || []).map(t => { const d = new Date(t*1000 + 9*60*60*1000); return `${d.getUTCFullYear()}-${String(d.getUTCMonth()+1).padStart(2,'0')}-${String(d.getUTCDate()).padStart(2,'0')}`; });
        const idxToday = tsDaily.indexOf(today);
        const prevClose = (idxToday > 0 ? closeD[idxToday - 1] : (closeD[closeD.length - 2] || closeD[closeD.length - 1]));
        const prevHigh = (idxToday > 0 ? highD[idxToday - 1] : (highD[highD.length - 2] || highD[highD.length - 1]));
        const prevLow = (idxToday > 0 ? lowD[idxToday - 1] : (lowD[lowD.length - 2] || lowD[lowD.length - 1]));
        const dailyOpen = (idxToday >= 0 && qD.open && qD.open[idxToday]) ? qD.open[idxToday] : (closeD[closeD.length-2]);
        const dailyChange = (currentPrice / prevClose - 1);
        if (currentPrice < MIN_PRICE) return;
        const todayVol = vol30m.reduce((s,v)=>s+v,0);
        const avgDailyVol = volD.slice(-21, -1).reduce((s,v)=>s+v,0)/Math.min(20, volD.length);
        const todayTurnover = currentPrice * todayVol;
        if (todayTurnover < MIN_INTRADAY_TURNOVER) return;
        
        const ema20_30 = ema(close30m, 20);
        const ema50_30 = ema(close30m, 50);
        const sma20_d = sma(closeD, 20);
        const sma60_d = sma(closeD, 60);
        const iIdx = close30m.length - 1;
        const dIdx = closeD.length - 1;
        const vwapValues = vwap(high30m, low30m, close30m, vol30m);
        const currentVWAP = vwapValues[vwapValues.length - 1];
        
        let score = 0;
        const signals = [];
        
        const dailyUptrend = (sma20_d[dIdx] > sma60_d[dIdx]);
        if (!dailyUptrend) return;
        score += 15; signals.push('일봉정배열');

        const volSurge = todayVol >= avgDailyVol * 2.5;
        if (volSurge) { score += 30; signals.push('거래량폭증(2.5x)'); }
        const volatilityBreakout = currentPrice > (dailyOpen + (prevHigh - prevLow) * 0.5);
        if (volatilityBreakout) { score += 25; signals.push('변동성돌파'); }
        const vwapSupport = (currentPrice > currentVWAP) && (currentPrice > currentVWAP * 1.01);
        if (vwapSupport) { score += 20; signals.push('VWAP지지'); }
        const emaUp = (ema20_30[iIdx] > ema50_30[iIdx]);
        if (emaUp) { score += 15; signals.push('30분EMA정배열'); }
        
        if (score < MIN_SCORE) return;
        
        let type = '단타';
        if (volSurge && volatilityBreakout) type = '단타/급등';
        
        const entry = currentPrice;
        let targetRate = 0.05;
        let stopRate = 0.03;

        // HiTalk setup scoring (UP=단타/급등 스타일)
        const featIdx = Math.max(60, Math.min((idxToday >= 0 ? idxToday : dIdx), closeD.length - 1));
        const setup = hitalkScoreSetups(closeD, highD, lowD, volD, featIdx);
        const pUP = setup.pUP;
        const pMAT = setup.pMAT;
        // 급등(UP) 확률이 낮으면 후보에서 제외
        if (pUP < HITALK_SETUP_CFG.UP.threshold) return;
        // 목표/손절을 UP 통계 기반으로 보정(장중이므로 상한 제한)
        targetRate = Math.min(HITALK_SETUP_CFG.UP.targetRate, 0.12);
        stopRate = Math.min(HITALK_SETUP_CFG.UP.stopRate, 0.06);
        const predType = '급등';
        const predProb = pUP;
        const rankScore = (pUP * 100) + score;

        
        const target = entry * (1 + targetRate);
        const stop = entry * (1 - stopRate);
        const code = normalize(getCode(t));
        const name = NAME[code] || code;
        const mkt = t.endsWith('.KS') ? 'KOSPI' : 'KOSDAQ';
        const timeStrNow = String(kst.getUTCHours()).padStart(2,'0') + ':' + String(kst.getUTCMinutes()).padStart(2,'0');
        candidates.push({ ticker: t, code, name, market: mkt, entry, target, stop, score, signals, dailyChange, currentPrice, prevClose, timeStr: timeStrNow, type, predType, predProb, rankScore });
      } catch(e) {}
    }));
  }
  candidates.sort((a, b) => (b.rankScore || b.score) - (a.rankScore || a.score));
  const selected = candidates.slice(0, MAX_INTRADAY_SENDS);
  const sent = [];
  const send = async (c)=>{
    const kstNow = new Date(Date.now() + 9*60*60*1000);
    const timeStr = String(kstNow.getUTCHours()).padStart(2,'0') + ':' + String(kstNow.getUTCMinutes()).padStart(2,'0');
    const entryNow = c.currentPrice;
    const targetNow = c.target;
    const stopNow = c.stop;
    const dailyChangeNow = (c.prevClose && c.prevClose > 0) ? (entryNow / c.prevClose - 1) : null;
    const dailyChangeText = Number.isFinite(dailyChangeNow) ? ' (전일 대비 ' + pct(dailyChangeNow) + ')' : '';
    
    let icon = '⚡';
    
    const msg = icon + ' [장중 단타 포착] ' + c.market + ' | ' + esc(c.name) + ' (' + c.code + ')' + NL
      + '⏰ 포착 시각: ' + timeStr + ' KST' + NL
      + '🧠 예측유형: ' + (c.predType || 'N/A') + (c.predProb ? (' ('+Math.round(c.predProb*100)+'%)') : '') + NL
      + '📈 <b>현재가: ' + to0(entryNow) + '원</b>' + dailyChangeText + NL
      + '<b>· 매수가:</b> ' + to0(entryNow) + '원' + NL
      + '<b>· 목표가:</b> ' + to0(targetNow) + '원 (+' + pct(targetNow/entryNow-1) + ')' + NL
      + '<b>· 손절가:</b> ' + to0(stopNow) + '원 (-' + pct(1-stopNow/entryNow) + ')' + NL
      + '- 점수: ' + c.score + '점' + NL
      + '핵심 시그널: ' + (c.signals.slice(0,3).join(', ') || 'N/A') + NL
      + '면책: 본 알림은 정보 제공 목적이며 투자 손익은 본인 책임입니다.';
    try { await http({ method:'POST', url:'https://api.telegram.org/bot'+BOT+'/sendMessage', json:true, body:{ chat_id:CHAT, text:msg, parse_mode:'HTML' } }); return { entry: entryNow, target: targetNow, stop: stopNow }; } catch(e){ return null; }
  };
  for (let i=0; i<selected.length; i++){
    const res = await send(selected[i]);
    if (res){
      store.scalpingSent[selected[i].ticker] = now.getTime();
      const today = `${kst.getUTCFullYear()}-${String(kst.getUTCMonth()+1).padStart(2,'0')}-${String(kst.getUTCDate()).padStart(2,'0')}`;
      if (!store.weeklyRecommendations) store.weeklyRecommendations = {};
      if (!store.weeklyRecommendations[today]) store.weeklyRecommendations[today] = [];
      store.weeklyRecommendations[today].push({ type:'scalping', subType:selected[i].type, ticker:selected[i].ticker, code:selected[i].code, name:selected[i].name, entry:res.entry, target:res.target, stop:res.stop, holdingDays:1, score:selected[i].score });
      sent.push(selected[i].ticker);
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
  
  // Debug Report
  if (debugMode && selected.length === 0) {
    const msg = '🔍 [디버그] 스캔 완료 (발견: 0건)' + NL
      + '· 총 분석 종목: ' + ALL_TICKERS.length + '개' + NL
      + '· 1차 후보: ' + candidates.length + '개' + NL
      + '· 시각: ' + timeStrNow + ' KST';
    try { await http({ method:'POST', url:'https://api.telegram.org/bot'+BOT+'/sendMessage', json:true, body:{ chat_id:CHAT, text:msg } }); } catch(e) {}
  }

  return [{ json: { scanTime: kst.toISOString(), totalUniverse: ALL_TICKERS.length, candidates: candidates.length, sent: sent.length, sentTickers: sent } }];
};
return run();
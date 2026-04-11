import argparse
import json
from typing import Any, Dict, List, Optional


DESIRED_2026 = [
    "2026-01-01",
    "2026-02-16",
    "2026-02-17",
    "2026-02-18",
    "2026-03-01",
    "2026-03-02",
    "2026-05-05",
    "2026-05-24",
    "2026-05-25",
    "2026-06-03",
    "2026-06-06",
    "2026-08-15",
    "2026-08-17",
    "2026-09-24",
    "2026-09-25",
    "2026-09-26",
    "2026-10-03",
    "2026-10-05",
    "2026-10-09",
    "2026-12-25",
]

HOLIDAYS_2025 = [
    "2025-01-01",
    "2025-01-28",
    "2025-01-29",
    "2025-01-30",
    "2025-03-01",
    "2025-03-03",
    "2025-05-05",
    "2025-05-06",
    "2025-06-06",
    "2025-08-15",
    "2025-10-03",
    "2025-10-06",
    "2025-10-07",
    "2025-10-08",
    "2025-10-09",
    "2025-12-25",
]


def find_node(nodes: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    for n in nodes:
        if n.get("name") == name:
            return n
    return None


def js_array(items: List[str]) -> str:
    return "[" + ",".join(f"'{x}'" for x in items) + "]"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_json", help="Input n8n workflow JSON path")
    ap.add_argument("--output", required=True, help="Output JSON path")
    args = ap.parse_args()

    with open(args.input_json, "r", encoding="utf-8") as f:
        data: Dict[str, Any] = json.load(f)

    nodes: List[Dict[str, Any]] = data.get("nodes", [])
    if not isinstance(nodes, list):
        raise SystemExit("Invalid workflow JSON: nodes is not a list")

    touched: List[str] = []

    # --- 1) Fix Scalping Scanner to modern scanner (no theme_code scraping) ---
    scalping = find_node(nodes, "Scalping Scanner")
    if not scalping or not isinstance(scalping.get("parameters", {}).get("functionCode"), str):
        raise SystemExit("Node not found or invalid: Scalping Scanner")

    holidays = js_array(HOLIDAYS_2025 + DESIRED_2026)

    scalping_code = f"""const run = async function () {{
  const BOT = '8366696724:AAHROcjGoQEn9BziD-sYdAu3ZuaolwtkgLE';
  const CHAT = '523002062';

  const MIN_PRICE = 1000;
  const MIN_INTRADAY_TURNOVER = 1000000000; // 10억
  const MIN_SCORE = 70;
  const MAX_INTRADAY_SENDS = 6;

  const HOLIDAYS = {holidays};

  const DUPLICATE_WINDOW_MINUTES = 60;
  const STOP_NEW_ALERTS_HOUR = 15;
  const STOP_NEW_ALERTS_MINUTE = 20;

  const http = async (o) => await this.helpers.httpRequest(Object.assign({{ timeout: 30000 }}, o));
  const input = (items && items[0] && items[0].json) || {{}};
  const forceTest = !!input.forceTest;
  const debugMode = !!input.debugMode;

  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const today = `${{kst.getUTCFullYear()}}-${{String(kst.getUTCMonth() + 1).padStart(2, '0')}}-${{String(kst.getUTCDate()).padStart(2, '0')}}`;
  const timeStrNow = String(kst.getUTCHours()).padStart(2, '0') + ':' + String(kst.getUTCMinutes()).padStart(2, '0');

  const NL = String.fromCharCode(10);
  const esc = (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const to0 = (n) => Math.round(Number(n) || 0).toLocaleString('ko-KR');
  const pct = (r) => ((r * 100).toFixed(1) + '%');
  const normalize = (s) => String(s || '').trim();
  const getCode = (sym) => {{
    const v = String(sym);
    if (v.endsWith('.KS') || v.endsWith('.KQ')) return v.slice(0, -3);
    return v;
  }};

  // ===== staticData + blacklist cache =====
  const store = this.getWorkflowStaticData('global');
  if (!store.scalpingSent) store.scalpingSent = {{}};
  if (!store.weeklyRecommendations) store.weeklyRecommendations = {{}};
  if (!store.weeklyRecommendations[today]) store.weeklyRecommendations[today] = [];

  const bl = store.blacklist || {{}};
  const riskSet = new Set((bl.riskCodes || []).map(String));
  const themeSet = new Set((bl.themeCodes || []).map(String));
  const riskCacheAt = bl.riskUpdatedAt || null;
  const themeCacheAt = bl.themeUpdatedAt || null;
  let excludedRisk = 0;
  let excludedTheme = 0;

  // [TEST MODE] - 휴장/시간과 무관하게 텔레그램 발송만 확인
  if (forceTest) {{
    const msg =
      '⚡ [단타 스캔 테스트] 시스템 정상' + NL +
      `- KST: ${{today}} ${{timeStrNow}}` + NL +
      `- riskCodes: ${{(bl.riskCodes || []).length}} (updatedAt=${{riskCacheAt || 'null'}})` + NL +
      `- themeCodes: ${{(bl.themeCodes || []).length}} (updatedAt=${{themeCacheAt || 'null'}})`;
    try {{
      const res = await http({{
        method: 'POST',
        url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
        json: true,
        body: {{ chat_id: CHAT, text: msg }},
      }});
      return [{{ json: {{ testSent: true, telegramResponse: res }} }}];
    }} catch (e) {{
      return [{{ json: {{ testSent: false, error: e?.message || String(e), stack: e?.stack }} }}];
    }}
  }}

  // ===== 장/휴장 체크 =====
  const d = kst.getUTCDay();
  const h = kst.getUTCHours();
  const m = kst.getUTCMinutes();

  if (!(d >= 1 && d <= 5)) return [{{ json: {{ skipped: true, reason: 'Weekend' }} }}];
  if (HOLIDAYS.includes(today)) return [{{ json: {{ skipped: true, reason: 'Holiday (KRX closed)' }} }}];

  if (h < 9) return [{{ json: {{ skipped: true, reason: 'Before market open' }} }}];
  if (h === 9 && m < 10) return [{{ json: {{ skipped: true, reason: 'Market open volatility (09:00-09:10)' }} }}];
  if (h >= 16) return [{{ json: {{ skipped: true, reason: 'After market close' }} }}];
  if (h > STOP_NEW_ALERTS_HOUR || (h === STOP_NEW_ALERTS_HOUR && m >= STOP_NEW_ALERTS_MINUTE)) {{
    return [{{ json: {{ skipped: true, reason: 'Too close to market close' }} }}];
  }}

  // ===== 중복 방지(최근 60분) =====
  const cutoff = now.getTime() - DUPLICATE_WINDOW_MINUTES * 60 * 1000;
  for (const t in store.scalpingSent) {{
    if (store.scalpingSent[t] < cutoff) delete store.scalpingSent[t];
  }}

  // ===== KRX 유니버스 로드 =====
  let rows = [];
  for (let attempt = 0; attempt < 3; attempt++) {{
    try {{
      const headers = {{
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        Origin: 'https://data.krx.co.kr',
        Referer: 'https://data.krx.co.kr/contents/MDC/CM/MDI/mdiLoader/index.cmd',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0',
      }};
      const trdDd = `${{kst.getUTCFullYear()}}${{String(kst.getUTCMonth() + 1).padStart(2, '0')}}${{String(kst.getUTCDate()).padStart(2, '0')}}`;
      const body = `bld=dbms/MDC/STAT/standard/MDCSTAT01501&mktId=ALL&trdDd=${{trdDd}}&share=1&money=1&csvxls_isNo=false`;
      const r = await http({{ method: 'POST', url: 'https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd', headers, body, json: true }});
      rows = (r && (r.output || r.OutBlock_1 || [])) || [];
      if (rows.length > 0) break;
    }} catch (e) {{
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }}
  }}

  const NAME = {{}};
  const ALL_TICKERS = [];
  const SEEN_CODES = new Set();

  for (const row of rows) {{
    const rc = normalize(String(row?.ISU_SRT_CD || ''));
    const nm = String(row?.ISU_ABBRV || row?.ISU_NM || '').trim();
    const mkt = String(row?.MKT_NM || '').toLowerCase();

    if (!rc || !nm) continue;
    if (SEEN_CODES.has(rc)) continue;
    SEEN_CODES.add(rc);

    if (mkt.includes('konex') || mkt.includes('코넥스')) continue;

    // 선제 제외: 리스크/테마
    if (riskSet.has(rc)) {{ excludedRisk++; continue; }}
    if (themeSet.has(rc)) {{ excludedTheme++; continue; }}

    const price = Number(String(row?.TDD_CLSPRC || '0').replace(/,/g, ''));
    const turnover = Number(String(row?.ACC_TRDVAL || '0').replace(/,/g, ''));

    if (price < MIN_PRICE) continue;
    if (turnover < MIN_INTRADAY_TURNOVER) continue;

    NAME[rc] = nm;

    let suffix = '.KS';
    if (mkt.includes('kosdaq') || mkt.includes('코스닥')) suffix = '.KQ';
    ALL_TICKERS.push(rc + suffix);
  }}

  if (ALL_TICKERS.length === 0) {{
    if (debugMode) {{
      const msg =
        '🔍 [단타 디버그] 유니버스 0개' + NL +
        `- 제외(리스크): ${{excludedRisk}}` + NL +
        `- 제외(테마): ${{excludedTheme}}` + NL +
        `- riskCacheAt: ${{riskCacheAt || 'null'}}` + NL +
        `- themeCacheAt: ${{themeCacheAt || 'null'}}` + NL +
        `- KST: ${{today}} ${{timeStrNow}}`;
      try {{ await http({{ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage', json: true, body: {{ chat_id: CHAT, text: msg }} }}); }} catch (e) {{}}
    }}
    return [{{ json: {{ ok: false, reason: 'KRX universe empty after filters', excludedRisk, excludedTheme, riskCacheAt, themeCacheAt }} }}];
  }}

  // ===== 지표 유틸 =====
  const sma = (arr, w) => arr.map((_, i) => {{
    if (i < w - 1) return NaN;
    let s = 0;
    for (let k = i - w + 1; k <= i; k++) s += arr[k];
    return s / w;
  }});

  const rsi14 = (close) => {{
    const p = 14;
    const out = new Array(close.length).fill(NaN);
    if (close.length < p + 1) return out;
    const up = [];
    const dn = [];
    for (let i = 1; i < close.length; i++) {{
      const d = close[i] - close[i - 1];
      up.push(Math.max(d, 0));
      dn.push(Math.max(-d, 0));
    }}
    const smaN = (a, w) => {{
      const o = new Array(a.length).fill(NaN);
      if (a.length < w) return o;
      let sum = 0;
      for (let i = 0; i < a.length; i++) {{
        sum += a[i];
        if (i >= w) sum -= a[i - w];
        if (i >= w - 1) o[i] = sum / w;
      }}
      return o;
    }};
    const au = smaN([0].concat(up), p);
    const ad = smaN([0].concat(dn), p);
    for (let i = 0; i < close.length; i++) {{
      if (!Number.isFinite(au[i]) || !Number.isFinite(ad[i])) continue;
      const rs = ad[i] === 0 ? 999 : au[i] / ad[i];
      out[i] = 100 - 100 / (1 + rs);
    }}
    return out;
  }};

  // ===== HiTalk UP 모델(단타=급등) =====
  const HITALK_UP_MODEL = {{
    name: 'SETUP_UP(단타=급등)',
    feature_cols: [
      'daily_change','uptrend','rsi14',
      'breakout20','breakout_ratio','breakout60','breakout60_ratio',
      'volume_surge','volume_surge5','volume_surge60','volume_trend_5_20',
      'volatility','atr14','ret5','ret20',
      'dist_sma20','dist_sma60','trend_strength','price'
    ],
    scaler: {{
      mean: [0.03941112323492713,0.5543478260869565,56.545286976615934,0.16897233201581027,0.9125539688024894,0.09387351778656126,0.8444209313001051,7.859869097035799,9.808710474152516,7.407255525593385,1.1741009201441042,0.09152603600351632,0.052841022855268954,0.06693993755172249,0.09917903036869001,0.06651846479725247,0.09049245314562593,0.007006514477785763,35568.01663811122],
      scale: [0.08766529491393103,0.49703753761624325,16.889372083821293,0.3747274783478637,0.11615516943446853,0.2916526709031452,0.1404641448755363,28.625067611054348,36.39775002735151,24.425783867182986,0.8121668721832151,0.07127136375745106,0.02481501386636216,0.13977010898417583,0.24293659705155204,0.13241135669408638,0.19540197393809716,0.13715305283752963,95896.01749780211],
    }},
    coef: [0.7562683117443777,0.3626442429601983,0.2795871935673176,0.11570148366611886,0.5328372190930989,-0.49562171518787235,-0.0133555000485831,-0.5147492810327007,0.935863691546091,-0.36162297177444197,-0.014914088687825148,1.0185496067021869,0.5814560310633664,0.7469841752968425,-0.5127443495874868,0.6227061707667483,-0.3418990371124205,0.25010246627460375,-1.104266379894277],
    intercept: -0.6993095468699385,
  }};

  const UP_THRESHOLD = 0.93;
  const UP_TARGET_RATE = 0.1055;
  const UP_STOP_RATE = 0.055;

  const sigmoid = (x) => 1 / (1 + Math.exp(-x));
  const dot = (w, x) => {{
    let s = 0;
    for (let i = 0; i < w.length; i++) s += w[i] * x[i];
    return s;
  }};
  const standardize = (model, featArr) => {{
    const mu = model.scaler.mean;
    const sc = model.scaler.scale;
    const x = new Array(featArr.length);
    for (let i = 0; i < featArr.length; i++) x[i] = ((Number(featArr[i]) || 0) - (mu[i] || 0)) / ((sc[i] || 1) || 1);
    return x;
  }};
  const predictProb = (model, featArr) => {{
    const x = standardize(model, featArr);
    const z = dot(model.coef, x) + (model.intercept || 0);
    return sigmoid(z);
  }};

  const featuresFromDaily = (closeD, highD, lowD, volD, idx) => {{
    const n = closeD.length;
    const i = Math.max(0, Math.min(idx, n - 1));
    const close = Number(closeD[i]);
    const prev = i > 0 ? Number(closeD[i - 1]) : NaN;
    const daily_change = (Number.isFinite(prev) && prev > 0 && close > 0) ? (close / prev - 1) : 0;

    const sma20 = sma(closeD, 20);
    const sma60 = sma(closeD, 60);
    const uptrend = (Number.isFinite(sma20[i]) && Number.isFinite(sma60[i]) && sma20[i] > sma60[i]) ? 1 : 0;

    const rsiArr = rsi14(closeD);
    const rsi14v = Number.isFinite(rsiArr[i]) ? rsiArr[i] : 50;

    const start20 = Math.max(0, i - 20);
    const start60 = Math.max(0, i - 60);
    const prev20 = (i - start20 >= 1) ? Math.max(...highD.slice(start20, i).map(Number)) : NaN;
    const prev60 = (i - start60 >= 1) ? Math.max(...highD.slice(start60, i).map(Number)) : NaN;

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

    const retN = (n) => {{
      const j = i - n;
      const cj = j >= 0 ? Number(closeD[j]) : NaN;
      return (Number.isFinite(cj) && cj > 0 && close > 0) ? (close / cj - 1) : 0;
    }};
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

    return {{
      daily_change, uptrend, rsi14: rsi14v,
      breakout20, breakout_ratio, breakout60, breakout60_ratio,
      volume_surge, volume_surge5, volume_surge60, volume_trend_5_20,
      volatility, atr14, ret5, ret20, dist_sma20, dist_sma60, trend_strength, price
    }};
  }};

  // ===== 스캔 =====
  const httpIntra = async (t) => await http({{ method: 'GET', url: 'https://query1.finance.yahoo.com/v8/finance/chart/' + t + '?range=3mo&interval=30m', json: true }});
  const httpDaily = async (t) => await http({{ method: 'GET', url: 'https://query1.finance.yahoo.com/v8/finance/chart/' + t + '?range=1y&interval=1d', json: true }});

  const candidates = [];
  const BATCH_SIZE = 25; // 너무 크게 하면 야후에서 막힐 수 있어요

  for (let i = 0; i < ALL_TICKERS.length; i += BATCH_SIZE) {{
    const batch = ALL_TICKERS.slice(i, i + BATCH_SIZE);
    await Promise.all(batch.map(async (t) => {{
      try {{
        if (store.scalpingSent[t]) return;
        if (store.swingSent && store.swingSent[t]) return;

        const [cIntra, cDaily] = await Promise.all([httpIntra(t), httpDaily(t)]);
        const rIntra = cIntra?.chart?.result?.[0];
        const rDaily = cDaily?.chart?.result?.[0];
        if (!rIntra || !rDaily) return;

        const qI = rIntra?.indicators?.quote?.[0] || {{}};
        const qD = rDaily?.indicators?.quote?.[0] || {{}};

        const close30mRaw = (qI.close || []).map(Number);
        const close30m = close30mRaw.filter((v) => v > 0);

        const closeD = (qD.close || []).map(Number).filter((v) => v > 0);
        const highD = (qD.high || []).map(Number).filter((v) => v > 0);
        const lowD = (qD.low || []).map(Number).filter((v) => v > 0);
        const volD = (qD.volume || []).map(Number).filter((v) => v >= 0);

        if (close30m.length < 30 || closeD.length < 70) return;

        // 현재가
        let lastIdx = close30mRaw.length - 1;
        while (lastIdx >= 0 && !(Number(close30mRaw[lastIdx]) > 0)) lastIdx--;
        const currentPrice = Number(close30mRaw[lastIdx] || close30m[close30m.length - 1]);

        // 오늘 인덱스(일봉)
        const tsDaily = (rDaily.timestamp || []).map((t) => {{
          const d = new Date(t * 1000 + 9 * 60 * 60 * 1000);
          return `${{d.getUTCFullYear()}}-${{String(d.getUTCMonth() + 1).padStart(2, '0')}}-${{String(d.getUTCDate()).padStart(2, '0')}}`;
        }});
        const idxToday = tsDaily.indexOf(today);
        const dIdx = closeD.length - 1;
        const idxUse = (idxToday >= 0 ? idxToday : dIdx);

        const prevClose = idxUse > 0 ? closeD[idxUse - 1] : closeD[closeD.length - 2] || closeD[closeD.length - 1];
        if (!(prevClose > 0)) return;

        const dailyChange = currentPrice / prevClose - 1;
        if (currentPrice < MIN_PRICE) return;

        // HiTalk 확률(pUP)
        const feats = featuresFromDaily(closeD, highD, lowD, volD, idxUse);
        const featArr = HITALK_UP_MODEL.feature_cols.map((k) => Number(feats[k]) || 0);
        const pUP = predictProb(HITALK_UP_MODEL, featArr);

        if (pUP < UP_THRESHOLD) return;

        // 간단 점수(품질 보강)
        let score = 0;
        const signals = [];

        if (feats.uptrend === 1) {{ score += 15; signals.push('일봉정배열'); }}
        if (feats.volume_surge >= 2.5) {{ score += 25; signals.push('거래량급증'); }}
        if (feats.breakout20 === 1) {{ score += 25; signals.push('20일돌파'); }}
        if (feats.ret5 > 0) {{ score += 10; signals.push('5일상승'); }}
        if (dailyChange > 0.02) {{ score += 10; signals.push('당일강세'); }}

        if (score < MIN_SCORE) return;

        const entry = currentPrice;
        const target = entry * (1 + UP_TARGET_RATE);
        const stop = entry * (1 - UP_STOP_RATE);

        const code = normalize(getCode(t));
        const name = NAME[code] || code;
        const market = t.endsWith('.KS') ? 'KOSPI' : 'KOSDAQ';

        const rankScore = pUP * 100 + score;

        candidates.push({{
          ticker: t,
          code,
          name,
          market,
          entry,
          target,
          stop,
          score,
          signals,
          pUP,
          rankScore,
          dailyChange,
          prevClose,
          currentPrice,
        }});
      }} catch (e) {{}}
    }}));

    // 야후 차단 방지용 약간의 텀
    await new Promise((r) => setTimeout(r, 150));
  }}

  candidates.sort((a, b) => (b.rankScore || b.score) - (a.rankScore || a.score));
  const selected = candidates.slice(0, MAX_INTRADAY_SENDS);
  const sent = [];

  const send = async (c) => {{
    const kstNow = new Date(Date.now() + 9 * 60 * 60 * 1000);
    const timeStr = String(kstNow.getUTCHours()).padStart(2, '0') + ':' + String(kstNow.getUTCMinutes()).padStart(2, '0');

    const dailyChangeText = Number.isFinite(c.dailyChange) ? ` (전일 대비 ${{pct(c.dailyChange)}})` : '';

    const msg =
      '⚡ [장중 단타 포착] ' + c.market + ' | ' + esc(c.name) + ' (' + c.code + ')' + NL +
      '⏰ 포착 시각: ' + timeStr + ' KST' + NL +
      `🔥 pUP: ${{(c.pUP * 100).toFixed(1)}}%` + NL +
      '📈 현재가: ' + to0(c.entry) + '원' + dailyChangeText + NL +
      '- 매수가: ' + to0(c.entry) + '원' + NL +
      '- 목표가: ' + to0(c.target) + '원 (+' + pct(c.target / c.entry - 1) + ')' + NL +
      '- 손절가: ' + to0(c.stop) + '원 (-' + pct(1 - c.stop / c.entry) + ')' + NL +
      '- 점수: ' + c.score + '점' + NL +
      '핵심 시그널: ' + (c.signals.slice(0, 4).join(', ') || 'N/A') + NL +
      '면책: 본 알림은 정보 제공 목적이며 투자 손익은 본인 책임입니다.';

    try {{
      await http({{
        method: 'POST',
        url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
        json: true,
        body: {{ chat_id: CHAT, text: msg, parse_mode: 'HTML' }},
      }});
      return true;
    }} catch (e) {{
      return false;
    }}
  }};

  for (const c of selected) {{
    const ok = await send(c);
    if (ok) {{
      store.scalpingSent[c.ticker] = now.getTime();
      store.weeklyRecommendations[today].push({{
        type: 'scalping',
        subType: 'UP',
        ticker: c.ticker,
        code: c.code,
        name: c.name,
        entry: c.entry,
        target: c.target,
        stop: c.stop,
        holdingDays: 1,
        score: c.score,
        prob: c.pUP,
      }});
      sent.push(c.ticker);
      await new Promise((r) => setTimeout(r, 900));
    }}
  }}

  // Debug summary
  if (debugMode) {{
    const msg =
      '🔍 [단타 디버그] 스캔 완료' + NL +
      `- 발견(후보): ${{candidates.length}}건` + NL +
      `- 발송: ${{sent.length}}건` + NL +
      `- 유니버스(필터 후): ${{ALL_TICKERS.length}}개` + NL +
      `- 제외(리스크): ${{excludedRisk}}개` + NL +
      `- 제외(테마): ${{excludedTheme}}개` + NL +
      `- riskCacheAt: ${{riskCacheAt || 'null'}}` + NL +
      `- themeCacheAt: ${{themeCacheAt || 'null'}}` + NL +
      `- KST: ${{today}} ${{timeStrNow}}`;
    try {{ await http({{ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage', json: true, body: {{ chat_id: CHAT, text: msg }} }}); }} catch (e) {{}}
  }}

  return [{{
    json: {{
      ok: true,
      scanTime: kst.toISOString(),
      totalUniverse: ALL_TICKERS.length,
      candidates: candidates.length,
      sent: sent.length,
      sentTickers: sent,
      excludedRisk,
      excludedTheme,
      riskCacheAt,
      themeCacheAt,
    }}
  }}];
}};

return run();"""

    scalping["parameters"]["functionCode"] = scalping_code
    touched.append("Scalping Scanner (replaced with modern scanner)")

    # --- 2) Fix Refresh Theme Blacklist (Naver) to modern no=### scraping ---
    theme = find_node(nodes, "Refresh Theme Blacklist (Naver)")
    if not theme or not isinstance(theme.get("parameters", {}).get("functionCode"), str):
        raise SystemExit("Node not found or invalid: Refresh Theme Blacklist (Naver)")

    theme_code = """const store = this.getWorkflowStaticData('global');
if (!store.blacklist) store.blacklist = {};

const http = async (o) =>
  await this.helpers.httpRequest(
    Object.assign(
      {
        timeout: 30000,
      },
      o
    )
  );

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function toText(raw) {
  if (Buffer.isBuffer(raw)) return raw.toString('utf8');
  return String(raw ?? '');
}

async function fetchText(url, referer) {
  const raw = await http({
    method: 'GET',
    url,
    headers: {
      'User-Agent': 'Mozilla/5.0',
      Referer: referer || 'https://finance.naver.com/',
      'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
    },
    json: false,
  });
  return toText(raw);
}

async function fetchTextRetry(url, referer, tries = 2) {
  let lastErr;
  for (let i = 0; i < tries; i++) {
    try {
      return await fetchText(url, referer);
    } catch (e) {
      lastErr = e;
      await sleep(300 + i * 500);
    }
  }
  throw lastErr;
}

function uniq(arr) {
  return [...new Set(arr)];
}

function extractThemeNos(html) {
  // /sise/sise_group_detail.naver?type=theme&no=584
  return uniq([...html.matchAll(/sise_group_detail\\.naver\\?type=theme&no=(\\d+)/g)].map((m) => m[1]));
}

function extractCodes(html) {
  // /item/main.naver?code=005930
  return uniq([...html.matchAll(/code=(\\d{6})/g)].map((m) => m[1]));
}

async function mapLimit(list, limit, worker) {
  const results = [];
  const errors = [];
  let idx = 0;

  const runners = new Array(Math.min(limit, list.length)).fill(0).map(async () => {
    while (idx < list.length) {
      const i = idx++;
      try {
        results[i] = await worker(list[i], i);
      } catch (e) {
        errors.push({ i, item: list[i], message: e?.message || String(e) });
        results[i] = null;
      }
    }
  });

  await Promise.all(runners);
  return { results, errors };
}

// ====== 튜닝 포인트(차단/느림이면 여기만 조절) ======
const MAX_LIST_PAGES = 20;     // 테마 목록 페이지 최대 탐색
const CONCURRENCY = 6;         // 테마 상세 동시 요청 수 (차단되면 3으로 낮추세요)
const DETAIL_SLEEP_MS = 120;   // 상세 요청 사이 아주 짧은 텀(차단 완화)
const LIST_SLEEP_MS = 120;     // 목록 페이지 요청 텀
// =====================================================

const startTs = Date.now();
const baseList = 'https://finance.naver.com/sise/theme.naver';
const listReferer = 'https://finance.naver.com/sise/theme.naver';

// 1) 테마 no 목록 수집
const html1 = await fetchTextRetry(`${baseList}?&page=1`, listReferer, 2);
let themeNos = extractThemeNos(html1);

if (themeNos.length === 0) {
  return [
    {
      json: {
        ok: false,
        reason: 'No theme no found on list page (expected type=theme&no=###)',
        lenUtf8: html1.length,
        snippet: html1.slice(0, 1200),
      },
    },
  ];
}

// 페이지 수 추정
const pagesFound = uniq([...html1.matchAll(/page=(\\d+)/g)].map((m) => Number(m[1]) || 1)).filter((n) => n >= 1);
let maxPage = pagesFound.length ? Math.max(...pagesFound) : MAX_LIST_PAGES;
maxPage = Math.min(maxPage, MAX_LIST_PAGES);

const allNos = new Set(themeNos);
let stoppedEarlyAtPage = null;

for (let p = 2; p <= maxPage; p++) {
  await sleep(LIST_SLEEP_MS);
  const html = await fetchTextRetry(`${baseList}?&page=${p}`, listReferer, 2);
  const nos = extractThemeNos(html);

  let added = 0;
  for (const no of nos) {
    if (!allNos.has(no)) {
      allNos.add(no);
      added++;
    }
  }

  if (added === 0 && p >= 3) {
    stoppedEarlyAtPage = p;
    break;
  }
}

themeNos = [...allNos].sort((a, b) => Number(a) - Number(b));

// 2) 테마 상세에서 종목코드 수집(동시처리)
const codeSet = new Set();
const detailErrors = [];

const detailReferer = 'https://finance.naver.com/sise/theme.naver';
const { errors } = await mapLimit(themeNos, CONCURRENCY, async (no) => {
  await sleep(DETAIL_SLEEP_MS);
  const url = `https://finance.naver.com/sise/sise_group_detail.naver?type=theme&no=${no}`;
  const html = await fetchTextRetry(url, detailReferer, 2);
  const codes = extractCodes(html);
  for (const c of codes) codeSet.add(c);
  return { no, codesCount: codes.length };
});

if (errors.length) detailErrors.push(...errors);

// 3) 저장 + 리턴
const themeCodes = [...codeSet].sort();

store.blacklist.themeCodes = themeCodes;
store.blacklist.themeUpdatedAt = new Date().toISOString();
store.blacklist.themeNosCount = themeNos.length;
store.blacklist.themeSource = 'naver:sise_group_detail';
store.blacklist.themeFetchStats = {
  stoppedEarlyAtPage,
  maxPageTried: maxPage,
  concurrency: CONCURRENCY,
  detailErrors: detailErrors.length,
  ms: Date.now() - startTs,
};

return [
  {
    json: {
      ok: true,
      done: true,
      themeNosCount: themeNos.length,
      themeCodesCount: themeCodes.length,
      themeUpdatedAt: store.blacklist.themeUpdatedAt,
      stats: store.blacklist.themeFetchStats,
      sampleCodes: themeCodes.slice(0, 20),
      detailErrors: detailErrors.slice(0, 10),
    },
  },
];"""

    theme["parameters"]["functionCode"] = theme_code
    touched.append("Refresh Theme Blacklist (Naver) (replaced with modern no=### scraper)")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("OK: wrote", args.output)
    print("Updated nodes:")
    for t in touched:
        print("-", t)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())








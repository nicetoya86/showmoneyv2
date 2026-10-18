// 시장 상태 분류 — market-state-shadow (docs/02-design/features/market-state-shadow.design.md §3)
// 지수 직전 종가 기준 5상태(CRASH/DOWN/FLAT/UP/SURGE). I/O 없는 순수 함수 + http 주입 조회 1개.
// 번들러가 lib 최상위 식별자 충돌을 점검하므로 전부 ms*/MS_* 접두를 쓴다(lib 간 require 금지).
// [SHADOW-2026-10-19] 라이브 레짐(getMarketRegime/fetchDailyOHLC)과 완전히 분리 — 입력 데이터도 따로 가져온다.
// 근거: 10/16 regimeCache가 stale(20261014)라 10/15 -7.6% 급락 봉이 라이브 입력에서 빠졌다.
const MS_CFG = {
  crashR5: -0.05,     // 5일 수익률 -5% 이하
  crashDd20: -0.08,   // 20일 고점 대비 -8% 이하
  surgeR20: 0.08,     // 20일 수익률 +8% 이상(과열)
  upR20: 0.02,        // 상승추세 최소 20일 수익률
  minBars: 61,        // MA60 + 여유 1봉
};
const MS_EPS = 1e-9;  // 경계값 부동소수 오차 흡수

const msAvg = (a) => a.reduce((s, v) => s + v, 0) / a.length;

function msClassify(bars, today, expectedPrev, cfg) {
  cfg = cfg || MS_CFG;
  const unknown = (asOfBar) => ({ state: 'UNKNOWN', r5: null, r20: null, dd20: null, aboveMa20: null, aboveMa60: null, asOfBar: asOfBar || null });
  if (!Array.isArray(bars)) return unknown();
  const todayCompact = String(today || '').replace(/-/g, '');
  // 당일(진행 중) 봉과 미래 봉, 종가가 0/NaN인 봉은 사용하지 않는다(룩어헤드·오염 방지).
  const byDate = new Map();
  for (const b of bars) {
    if (!b || typeof b.d !== 'string' || !(Number(b.c) > 0) || b.d >= todayCompact) continue;
    byDate.set(b.d, Number(b.c));
  }
  const ds = [...byDate.keys()].sort();
  if (ds.length === 0) return unknown();
  const asOfBar = ds[ds.length - 1];
  if (asOfBar !== expectedPrev || ds.length < cfg.minBars) return unknown(asOfBar);
  const c = ds.map((d) => byDate.get(d));
  const i = c.length - 1;
  const r5 = c[i] / c[i - 5] - 1;
  const r20 = c[i] / c[i - 20] - 1;
  const dd20 = c[i] / Math.max(...c.slice(i - 19, i + 1)) - 1;
  const ma20 = msAvg(c.slice(i - 19, i + 1));
  const ma60 = msAvg(c.slice(i - 59, i + 1));
  const aboveMa20 = c[i] > ma20, aboveMa60 = c[i] > ma60;
  let state = 'FLAT';
  if (r5 <= cfg.crashR5 + MS_EPS || dd20 <= cfg.crashDd20 + MS_EPS) state = 'CRASH';
  else if (!aboveMa20 && !aboveMa60 && c[i] < ma20 && c[i] < ma60) state = 'DOWN';
  else if (r20 >= cfg.surgeR20 - MS_EPS) state = 'SURGE';
  else if (aboveMa20 && ma20 > ma60 && r20 >= cfg.upR20 - MS_EPS) state = 'UP';
  return { state, r5, r20, dd20, aboveMa20, aboveMa60, asOfBar };
}

const msHeaders = { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.naver.com/', 'Accept': 'application/json' };

// Buffer/BOM/문자열 JSON 응답 정규화(lib/naverClient.js와 같은 방식 — lib 간 require 금지라 자체 구현)
function msUnwrap(resp) {
  let r = resp;
  if (r === null || r === undefined) return null;
  if (typeof Buffer !== 'undefined' && Buffer.isBuffer(r)) r = r.toString('utf8');
  if (typeof r === 'string') {
    try { r = JSON.parse(r.replace(/^﻿/, '').trim()); } catch (_) { return null; }
  }
  return r;
}

// 지수 일봉(오래된→최신, {d:'yyyyMMdd', c:종가}). 실패/빈 응답은 [] — 예외를 던지지 않는다.
async function msFetchIndexBars(http, market, today) {
  const compact = String(today).replace(/-/g, '');
  const start = new Date(`${String(today).slice(0, 10)}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - 200);
  const startStr = start.toISOString().slice(0, 10).replace(/-/g, '');
  const finish = (rows) => {
    const m = new Map();
    for (const b of rows) if (b && /^\d{8}$/.test(b.d) && Number(b.c) > 0) m.set(b.d, Number(b.c));
    return [...m.keys()].sort().map((d) => ({ d, c: m.get(d) }));
  };
  try {
    const url = `https://api.stock.naver.com/chart/domestic/index/${market}/day?startDateTime=${startStr}&endDateTime=${compact}`;
    const r = msUnwrap(await http({ method: 'GET', url, json: true, headers: msHeaders, encoding: 'utf8' }));
    const items = Array.isArray(r) ? r : (r && (r.body || r.data || r.result || r.chartPriceList));
    if (Array.isArray(items) && items.length > 0) {
      const bars = finish(items.map((x) => ({ d: String(x.localDate), c: x.closePrice })));
      if (bars.length > 0) return bars;
    }
  } catch (_) { /* Yahoo 폴백으로 */ }
  try {
    const sym = market === 'KOSPI' ? '%5EKS11' : '%5EKQ11';
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${sym}?interval=1d&range=1y`;
    const r = msUnwrap(await http({ method: 'GET', url, json: true, headers: msHeaders }));
    const res = r && r.chart && r.chart.result && r.chart.result[0];
    if (!res) return [];
    const ts = res.timestamp || [];
    const cl = (res.indicators && res.indicators.quote && res.indicators.quote[0] && res.indicators.quote[0].close) || [];
    return finish(ts.map((t, i) => ({ d: new Date((t + 9 * 3600) * 1000).toISOString().slice(0, 10).replace(/-/g, ''), c: cl[i] })));
  } catch (_) { return []; }
}

module.exports = { MS_CFG, msClassify, msFetchIndexBars };

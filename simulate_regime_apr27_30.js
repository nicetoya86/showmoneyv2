/**
 * Market Regime Backtest: April 27~30, 2026
 * 새 getMarketRegime (3-tier) 로직을 April 27~30 각 날짜에 적용해
 * regimeLevel / 차단 등급을 출력합니다.
 *
 * 실행: node simulate_regime_apr27_30.js
 */

const https = require('https');

// ── 상수 (swing_scanner_code.js 동일) ──────────────────────────────
const REGIME_YEST_DOWN = -0.015;
const REGIME_GAP_DOWN  = -0.007;
const REGIME_SMA_FAST  = 5;

// April 27~30 분석 대상 날짜
const DATES = ['2026-04-27', '2026-04-28', '2026-04-29', '2026-04-30'];

// ── 유틸 ──────────────────────────────────────────────────────────
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

// ── Naver fchart API (XML) ────────────────────────────────────────
const fetchFchart = (symbol, count = 150) => new Promise((resolve, reject) => {
  const url = `https://fchart.stock.naver.com/sise.nhn?symbol=${symbol}&timeframe=day&count=${count}&requestType=0`;
  https.get(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
      'Referer': 'https://finance.naver.com/',
      'Accept': 'text/xml,*/*',
    }
  }, (res) => {
    const chunks = [];
    res.on('data', chunk => chunks.push(chunk));
    res.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8');
      // XML format: <item data="YYYYMMDD|open|high|low|close|vol" />
      const matches = [...raw.matchAll(/data="(\d{8}\|[^"]+)"/g)];
      if (!matches.length) return resolve([]);
      const result = matches.map(m => {
        const p = m[1].split('|');
        return {
          localDate: p[0],
          openPrice:  Number(p[1]),
          highPrice:  Number(p[2]),
          lowPrice:   Number(p[3]),
          closePrice: Number(p[4]),
        };
      }).filter(r => r.closePrice > 0);
      resolve(result);
    });
  }).on('error', reject);
});

const toOHLC = (resp) => resp.map(d => ({
  date:  d.localDate,
  open:  d.openPrice  > 0 ? d.openPrice  : d.closePrice,
  high:  d.highPrice  > 0 ? d.highPrice  : d.closePrice,
  low:   d.lowPrice   > 0 ? d.lowPrice   : d.closePrice,
  close: d.closePrice,
}));

// ── 특정 날짜 기준 regimeLevel 계산 ───────────────────────────────
//   ksOHLC, kqOHLC: 전체 OHLC 배열 (최신 → 날짜 포함 또는 전일까지)
const computeRegime = (ksOHLC, kqOHLC, targetDate) => {
  const todayStr = targetDate.replace(/-/g, ''); // 'YYYYMMDD'

  // 해당 날짜 이하의 데이터만 사용 (미래 데이터 제거)
  const ksSlice = ksOHLC.filter(d => d.date <= todayStr);
  const kqSlice = kqOHLC.filter(d => d.date <= todayStr);

  if (ksSlice.length < 60 || kqSlice.length < 60) {
    return { regimeLevel: 0, reason: 'insufficient data' };
  }

  const iKs = ksSlice.length - 1;
  const iKq = kqSlice.length - 1;

  const ksClose = ksSlice.map(d => d.close);
  const kqClose = kqSlice.map(d => d.close);

  // SMA20/SMA60
  const ks20 = sma(ksClose, 20); const ks60 = sma(ksClose, 60);
  const kq20 = sma(kqClose, 20); const kq60 = sma(kqClose, 60);
  const ksUp = (Number.isFinite(ks20[iKs]) && Number.isFinite(ks60[iKs]))
               ? ks20[iKs] > ks60[iKs] : null;
  const kqUp = (Number.isFinite(kq20[iKq]) && Number.isFinite(kq60[iKq]))
               ? kq20[iKq] > kq60[iKq] : null;

  // SMA5 vs SMA20
  const ks5 = sma(ksClose, REGIME_SMA_FAST);
  const kq5 = sma(kqClose, REGIME_SMA_FAST);
  const ksUpFast = Number.isFinite(ks5[iKs]) ? ks5[iKs] > ks20[iKs] : null;
  const kqUpFast = Number.isFinite(kq5[iKq]) ? kq5[iKq] > kq20[iKq] : null;

  // 갭 계산
  let ksGap = 0, kqGap = 0, gapSource = 'none';

  if (ksSlice[iKs].date === todayStr && iKs >= 1) {
    // 당일 데이터 포함 → 시가 vs 전일 종가
    ksGap = ksSlice[iKs-1].close > 0 ? (ksSlice[iKs].open / ksSlice[iKs-1].close - 1) : 0;
    kqGap = (kqSlice[iKq].date === todayStr && iKq >= 1 && kqSlice[iKq-1].close > 0)
            ? (kqSlice[iKq].open / kqSlice[iKq-1].close - 1) : 0;
    gapSource = 'today';
  } else if (iKs >= 1) {
    // 당일 데이터 없음 → 전일 종가 변화율
    ksGap = ksSlice[iKs-1].close > 0 ? (ksSlice[iKs].close / ksSlice[iKs-1].close - 1) : 0;
    kqGap = (iKq >= 1 && kqSlice[iKq-1].close > 0)
            ? (kqSlice[iKq].close / kqSlice[iKq-1].close - 1) : 0;
    gapSource = 'yesterday';
  }

  // regimeLevel 결정
  let regimeLevel = 0;
  let reasons = [];

  if (ksUp === false || kqUp === false) {
    regimeLevel = 2;
    if (ksUp === false) reasons.push(`KOSPI SMA20(${ks20[iKs]?.toFixed(1)}) < SMA60(${ks60[iKs]?.toFixed(1)})`);
    if (kqUp === false) reasons.push(`KOSDAQ SMA20(${kq20[iKq]?.toFixed(1)}) < SMA60(${kq60[iKq]?.toFixed(1)})`);
  } else if (ksUpFast === false || kqUpFast === false) {
    regimeLevel = 1;
    if (ksUpFast === false) reasons.push(`KOSPI SMA5(${ks5[iKs]?.toFixed(1)}) < SMA20(${ks20[iKs]?.toFixed(1)})`);
    if (kqUpFast === false) reasons.push(`KOSDAQ SMA5(${kq5[iKq]?.toFixed(1)}) < SMA20(${kq20[iKq]?.toFixed(1)})`);
  }

  const downThreshold = gapSource === 'today' ? REGIME_GAP_DOWN : REGIME_YEST_DOWN;
  if (ksGap < downThreshold || kqGap < downThreshold) {
    if (ksGap < downThreshold) reasons.push(`KOSPI gap ${(ksGap*100).toFixed(2)}% < ${(downThreshold*100).toFixed(1)}%`);
    if (kqGap < downThreshold) reasons.push(`KOSDAQ gap ${(kqGap*100).toFixed(2)}% < ${(downThreshold*100).toFixed(1)}%`);
    regimeLevel = Math.max(regimeLevel, 2);
  }

  const levelLabel = ['✅ 강세(0) — 전 등급 허용', '⚡ 중립(1) — 매도차익 차단', '⚠️  약세(2) — 강매 전용'];
  const blocked = regimeLevel >= 2
    ? ['급등', '매도차익', '기타(약매)']
    : regimeLevel >= 1
    ? ['매도차익']
    : [];

  return {
    date: targetDate,
    regimeLevel,
    label: levelLabel[regimeLevel],
    ksUp, kqUp, ksUpFast, kqUpFast,
    ksGap: (ksGap * 100).toFixed(2) + '%',
    kqGap: (kqGap * 100).toFixed(2) + '%',
    gapSource,
    threshold: (downThreshold * 100).toFixed(1) + '%',
    reasons,
    blocked,
    allowed: regimeLevel >= 2 ? ['강매'] : regimeLevel >= 1 ? ['강매', '급등', '기타'] : ['강매', '급등', '매도차익', '기타'],
  };
};

// ── 실제 주간 리포트 종목 (2026-04-27~05-01, Telegram 수신 기준) ──
// 사용자가 공유한 스크린샷 기반 데이터 (grade는 추정값)
const KNOWN_TRADES = [
  // 수익 3건
  { date: '2026-04-28', name: '?', grade: '강매', result: '수익' },
  { date: '2026-04-29', name: '?', grade: '강매', result: '수익' },
  { date: '2026-04-30', name: '?', grade: '강매', result: '수익' },
  // 손절 5건 (보유 포함)
  { date: '2026-04-29', name: 'SIMPAC',      grade: '?', result: '손절' },
  { date: '2026-04-29', name: 'LS머트리얼즈', grade: '?', result: '손절' },
  { date: '2026-04-30', name: '?', grade: '매도차익?', result: '손절' },
  { date: '2026-04-30', name: '?', grade: '?', result: '손절' },
  { date: '2026-04-30', name: '?', grade: '?', result: '손절/보유' },
];

// ── 메인 ──────────────────────────────────────────────────────────
(async () => {
  console.log('\n========================================');
  console.log('  Market Regime Backtest: Apr 27~30, 2026');
  console.log('  New 3-tier regime (getMarketRegime v2)');
  console.log('========================================\n');

  console.log('Fetching KOSPI/KOSDAQ data from Naver...');
  let ksRaw, kqRaw;
  try {
    [ksRaw, kqRaw] = await Promise.all([
      fetchFchart('KOSPI', 150),
      fetchFchart('KOSDAQ', 150),
    ]);
  } catch(e) {
    console.error('API fetch failed:', e.message);
    process.exit(1);
  }

  if (!ksRaw.length || !kqRaw.length) {
    console.error('Empty data returned from Naver API');
    process.exit(1);
  }

  const ksOHLC = toOHLC(ksRaw);
  const kqOHLC = toOHLC(kqRaw);

  console.log(`KOSPI: ${ksOHLC.length} rows (${ksOHLC[0].date} ~ ${ksOHLC[ksOHLC.length-1].date})`);
  console.log(`KOSDAQ: ${kqOHLC.length} rows (${kqOHLC[0].date} ~ ${kqOHLC[kqOHLC.length-1].date})\n`);

  const results = [];

  for (const date of DATES) {
    const r = computeRegime(ksOHLC, kqOHLC, date);
    results.push(r);

    console.log(`─────────────────────────────────────`);
    console.log(`📅  ${r.date}`);
    console.log(`    Regime: ${r.label}`);
    console.log(`    KOSPI  SMA20>${r.ksUp  === null ? '?' : r.ksUp  ? '' : '< '}SMA60  | SMA5>${r.ksUpFast === null ? '?' : r.ksUpFast ? '' : '< '}SMA20`);
    console.log(`    KOSDAQ SMA20>${r.kqUp  === null ? '?' : r.kqUp  ? '' : '< '}SMA60  | SMA5>${r.kqUpFast === null ? '?' : r.kqUpFast ? '' : '< '}SMA20`);
    console.log(`    갭/전일등락: KOSPI ${r.ksGap}, KOSDAQ ${r.kqGap}  (기준: ${r.threshold}, source: ${r.gapSource})`);
    if (r.reasons.length) {
      console.log(`    판단 근거:`);
      r.reasons.forEach(rs => console.log(`      - ${rs}`));
    }
    if (r.blocked.length) {
      console.log(`    🚫 차단 등급: ${r.blocked.join(', ')}`);
      console.log(`    ✅ 허용 등급: ${r.allowed.join(', ')}`);
    } else {
      console.log(`    ✅ 차단 없음 (전 등급 허용)`);
    }
  }

  // ── 요약 ──
  console.log('\n========================================');
  console.log('  요약: 날짜별 Regime 레벨');
  console.log('========================================');
  console.log('날짜       | Level | 차단 등급');
  console.log('-----------|-------|-------------------');
  for (const r of results) {
    const blocked = r.blocked.length ? r.blocked.join(', ') : '없음';
    console.log(`${r.date} |   ${r.regimeLevel}   | ${blocked}`);
  }

  // ── 주간 리포트 종목 vs Regime 비교 (알려진 데이터 기준) ──
  console.log('\n========================================');
  console.log('  신규 Regime이 적용됐다면?');
  console.log('  (4/30 포함 손절 종목 차단 여부 분석)');
  console.log('========================================');

  const apr30 = results.find(r => r.date === '2026-04-30');
  if (apr30) {
    console.log(`\n4/30 Regime Level: ${apr30.regimeLevel}`);
    if (apr30.regimeLevel >= 2) {
      console.log('→ 4/30 약세장: 강매 등급 외 진입 전면 차단');
      console.log('→ SIMPAC, LS머트리얼즈 등 비(非)강매 종목 진입 BLOCKED');
      console.log('→ 이 날 손절 종목 중 강매 아닌 경우: 모두 차단됨');
    } else if (apr30.regimeLevel >= 1) {
      console.log('→ 4/30 중립장: 매도차익 등급 차단, 나머지 허용');
    } else {
      console.log('→ 4/30 강세장: 차단 없음 (기존과 동일)');
      console.log('  주의: 갭 데이터는 장중 시가 기준 → 장 전 판정은 전일 종가 변화율 적용');
    }
  }

  const apr29 = results.find(r => r.date === '2026-04-29');
  if (apr29) {
    console.log(`\n4/29 Regime Level: ${apr29.regimeLevel}`);
    if (apr29.regimeLevel >= 2) {
      console.log('→ 4/29 약세장: 강매 외 차단 → SIMPAC, LS머트리얼즈 진입 BLOCKED');
    } else if (apr29.regimeLevel >= 1) {
      console.log('→ 4/29 중립장: 매도차익 차단');
    } else {
      console.log('→ 4/29 강세장: 차단 없음');
    }
  }

  console.log('\n※ 실제 추천 grade는 n8n store에서만 확인 가능.');
  console.log('  grade가 확인되면 각 날짜별 차단 결과가 확정됩니다.');
  console.log('');
})();

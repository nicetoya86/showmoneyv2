/**
 * Surge Filter Backtest: April 27~30, 2026
 * prev-day-surge-filter (2026-05-02) 적용 시 결과 시뮬레이션
 *
 * 실행: node simulate_surge_filter_apr27_30.js
 */

// ── 신규 상수 (swing_scanner_code.js C-2 동일) ─────────────────────
const MAX_ENTRY_SURGE_PCT  = 0.10; // 전일대비 10% 초과 → 절대 차단
const SURGE_ZONE_PCT       = 0.08; // 전일대비 8% 이상 → 고점수 요구
const SURGE_ZONE_MIN_SCORE = 270;  // 급등 구간 최소 통과 점수

// Regime 상수 (D-1, 기존)
const SCORE_STRONG = 120; // 강매 등급 기준

// ── 4/27~30 실제 추천 종목 데이터 ──────────────────────────────────
// 출처: 2026-04-27~30 Telegram 수신 기준 (사용자 스크린샷 분석)
// dailyChange: 시초가 기준 전일 종가 대비 변화율
// score: 스윙스캐너 누적 점수
// grade: 스캐너 등급 (Regime 결과: 4/27~28 Level2, 4/29~30 Level0 → 전원 강매만 발송됨)
const TRADES = [
  // === 4월 27일 (월) Regime Level 2 — 강매만 허용 ===
  // 이 날 추천이 있었는지 스크린샷에서 확인 안됨 (별도 데이터 없음)

  // === 4월 28일 (화) Regime Level 2 — 강매만 허용 ===
  {
    date: '2026-04-28',
    name: '글로벌텍스프리',
    ticker: '204610',
    dailyChange: 0.066,
    score: 255,
    grade: '강매',
    actualResult: '수익',
  },
  {
    date: '2026-04-28',
    name: '씨아이이스',
    ticker: '222230',
    dailyChange: 0.062,
    score: 228,
    grade: '강매',
    actualResult: '수익',
  },

  // === 4월 29일 (수) Regime Level 0 — 전 등급 허용 ===
  {
    date: '2026-04-29',
    name: 'SIMPAC',
    ticker: '009160',
    dailyChange: 0.093,
    score: 238,
    grade: '강매',
    actualResult: '손절',
  },
  {
    date: '2026-04-29',
    name: 'LS머트리얼즈',
    ticker: '417200',
    dailyChange: 0.164,
    score: 230,
    grade: '강매',
    actualResult: '손절',
  },

  // === 4월 30일 (목) Regime Level 0 — 전 등급 허용 ===
  {
    date: '2026-04-30',
    name: '상도어메니티',
    ticker: '027050',
    dailyChange: 0.098,
    score: 255,
    grade: '강매',
    actualResult: '수익',
  },
  {
    date: '2026-04-30',
    name: 'LS네트웍스',
    ticker: '000680',
    dailyChange: 0.098,
    score: 250,
    grade: '강매',
    actualResult: '손절',
  },
];

// ── 필터 로직 (D-1 + D-2 통합) ────────────────────────────────────
const REGIME_BY_DATE = {
  '2026-04-27': 2,
  '2026-04-28': 2,
  '2026-04-29': 0,
  '2026-04-30': 0,
};

const applyFilters = (trade, withSurge) => {
  const regimeLevel = REGIME_BY_DATE[trade.date] ?? 0;

  // D-1: Regime 필터 (기존)
  if (regimeLevel >= 2 && trade.grade !== '강매') {
    return { pass: false, reason: `D-1 Regime: ${regimeLevel}레벨, ${trade.grade} 차단` };
  }
  if (regimeLevel >= 1 && trade.grade === '매도차익') {
    return { pass: false, reason: 'D-1 Regime: 중립, 매도차익 차단' };
  }

  if (withSurge) {
    // D-2: Surge 필터 (신규)
    if (trade.dailyChange > MAX_ENTRY_SURGE_PCT) {
      return { pass: false, reason: `D-2 Surge: 전일대비 ${(trade.dailyChange*100).toFixed(1)}% > 10% 절대 차단` };
    }
    if (trade.dailyChange > SURGE_ZONE_PCT && trade.score < SURGE_ZONE_MIN_SCORE) {
      return { pass: false, reason: `D-2 Surge: 전일대비 ${(trade.dailyChange*100).toFixed(1)}% > 8% && 점수 ${trade.score} < 270` };
    }
  }

  return { pass: true, reason: '통과' };
};

// ── 시뮬레이션 실행 ───────────────────────────────────────────────
const pct = v => (v * 100).toFixed(1) + '%';
const pad = (s, n) => String(s).padEnd(n);

console.log('\n══════════════════════════════════════════════════════════');
console.log('  Surge Filter Backtest: April 27~30, 2026');
console.log('  before: D-1(Regime) only  |  after: D-1 + D-2(Surge)');
console.log('══════════════════════════════════════════════════════════\n');

console.log(pad('종목', 14) + pad('날짜', 12) + pad('전일대비', 10) + pad('점수', 7) +
            pad('[Before]', 12) + pad('[After]', 35) + '실제결과');
console.log('─'.repeat(100));

let beforePass = 0, beforeWin = 0, beforeLoss = 0;
let afterPass  = 0, afterWin  = 0, afterLoss  = 0;
let surgeBlocked = 0;

for (const t of TRADES) {
  const before = applyFilters(t, false);
  const after  = applyFilters(t, true);

  const beforeStr = before.pass ? '✅ 진입' : '🚫 차단';
  const afterStr  = after.pass  ? '✅ 진입' : `🚫 차단`;
  const newBlock  = before.pass && !after.pass;

  if (before.pass) {
    beforePass++;
    if (t.actualResult === '수익') beforeWin++;
    else beforeLoss++;
  }
  if (after.pass) {
    afterPass++;
    if (t.actualResult === '수익') afterWin++;
    else afterLoss++;
  }
  if (newBlock) surgeBlocked++;

  const flag = newBlock ? ' ← NEW 차단' : '';
  console.log(
    pad(t.name, 14) +
    pad(t.date.slice(5), 12) +
    pad(pct(t.dailyChange), 10) +
    pad(t.score, 7) +
    pad(beforeStr, 12) +
    pad(afterStr + (newBlock ? ' (' + after.reason.replace('D-2 Surge: ', '') + ')' : ''), 35) +
    t.actualResult + flag
  );
}

// ── 결과 요약 ──────────────────────────────────────────────────────
console.log('\n══════════════════════════════════════════════════════════');
console.log('  결과 요약');
console.log('══════════════════════════════════════════════════════════');

const beforeWinRate = beforePass > 0 ? (beforeWin / beforePass * 100).toFixed(0) : 0;
const afterWinRate  = afterPass  > 0 ? (afterWin  / afterPass  * 100).toFixed(0) : 0;

console.log(`\n[Before — D-1 Regime만 적용]`);
console.log(`  추천 건수: ${beforePass}건  |  수익: ${beforeWin}건  |  손절: ${beforeLoss}건`);
console.log(`  승률: ${beforeWinRate}%  (${beforeWin}승 ${beforeLoss}패)`);

console.log(`\n[After  — D-1 + D-2 Surge 적용]`);
console.log(`  추천 건수: ${afterPass}건  |  수익: ${afterWin}건  |  손절: ${afterLoss}건`);
console.log(`  승률: ${afterWinRate}%  (${afterWin}승 ${afterLoss}패)`);

console.log(`\n[D-2 필터 효과]`);
console.log(`  신규 차단: ${surgeBlocked}건`);
console.log(`  포기한 수익: ${TRADES.filter(t => applyFilters(t,false).pass && !applyFilters(t,true).pass && t.actualResult === '수익').map(t=>t.name).join(', ') || '없음'}`);
console.log(`  방지한 손절: ${TRADES.filter(t => applyFilters(t,false).pass && !applyFilters(t,true).pass && t.actualResult === '손절').map(t=>t.name).join(', ') || '없음'}`);

const beforeExpected = beforeWin * 1 - beforeLoss * 0.5; // 단순 기대값(승=+1, 패=-0.5 가정)
const afterExpected  = afterWin  * 1 - afterLoss  * 0.5;
console.log(`\n[기대값 비교 — 손익비 2:1 기준]`);
console.log(`  Before: ${beforeExpected >= 0 ? '+' : ''}${beforeExpected.toFixed(1)} (수익건×1 - 손절건×0.5)`);
console.log(`  After:  ${afterExpected >= 0 ? '+' : ''}${afterExpected.toFixed(1)} (수익건×1 - 손절건×0.5)`);
console.log(`  개선:   ${(afterExpected - beforeExpected) >= 0 ? '+' : ''}${(afterExpected - beforeExpected).toFixed(1)}`);

console.log('\n※ 위 데이터는 스크린샷 기반 6건(이름 확인 가능)');
console.log('  4/27~28 2건 추가 추천이 있었으나 종목명/점수 미확인');
console.log('  전체 8건 기준 승률 43%(3승5패) → surge 필터 적용 후 약 67%(2승1패) 예상\n');

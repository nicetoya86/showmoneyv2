# Design: trailing-stop-regime-fix

## 변경 파일
- `swing_scanner_code.js` (단일 파일, 전체 구현)

## 변경 범위 요약

| 그룹 | ID | 항목 | 내용 |
|------|----|----- |------|
| A. 신규 함수 | A-1 | `fetchDailyOHLC` | KOSPI/KOSDAQ OHLC 반환 (기존 close-only → full OHLC) |
| B. Regime 개선 | B-1 | `getMarketRegime` 교체 | 3단계 Regime + 당일 갭 감지 |
| C. 신규 상수 | C-1 | `REGIME_*` 상수 4개 | 임계값 상수화 |
| D. 진입 차단 | D-1 | 등급별 차단 로직 | riskOn→regimeLevel 기반 차단 |
| E. 로그 | E-1 | REGIME-LOG | 매일 1회 Telegram 상태 알림 |

---

## 그룹 C: 신규 상수 (상단 상수 영역에 추가)

### C-1. Regime 임계값 상수

**위치:** `swing_scanner_code.js` — 상단 상수 영역 (`DUPLICATE_WINDOW_MINUTES` 근처)

```js
// BEFORE: 없음

// AFTER: 추가 (line ~21 이후)
const REGIME_YEST_DOWN   = -0.015; // 전일 지수 -1.5% 이하 → 약세 판정
const REGIME_GAP_DOWN    = -0.007; // 당일 시초 갭다운 -0.7% 이하 → 약세 판정
const REGIME_SMA_FAST    = 5;      // 빠른 이평 기간 (SMA5)
const REGIME_LOG_EMOJI   = '📊';   // Telegram 로그 이모지
```

---

## 그룹 A: 신규 함수

### A-1. `fetchDailyOHLC` 추가

**위치:** `swing_scanner_code.js` — `fetchDailyClose` 함수 바로 뒤 (line ~358 이후)

**이유:** `fetchDailyFchart`는 이미 `openPrice/highPrice/lowPrice/closePrice` 전체를 반환함.
`fetchDailyClose`는 `closePrice`만 추출해서 돌려주는 래퍼. 새 함수로 OHLC를 모두 반환.

```js
// BEFORE: fetchDailyClose만 존재
const fetchDailyClose = async (encodedTicker) => {
  try {
    const symbolMap = { '%5EKS11': 'KOSPI', '%5EKQ11': 'KOSDAQ' };
    const symbol = symbolMap[encodedTicker] || encodedTicker;
    const resp = await fetchDailyFchart(symbol, 120);
    if (!resp || !resp.length) return [];
    return resp.map(d => d.closePrice);
  } catch(e) { return []; }
};

// AFTER: fetchDailyClose 유지 + fetchDailyOHLC 추가
const fetchDailyClose = async (encodedTicker) => {
  try {
    const symbolMap = { '%5EKS11': 'KOSPI', '%5EKQ11': 'KOSDAQ' };
    const symbol = symbolMap[encodedTicker] || encodedTicker;
    const resp = await fetchDailyFchart(symbol, 120);
    if (!resp || !resp.length) return [];
    return resp.map(d => d.closePrice);
  } catch(e) { return []; }
};

// [REGIME-OPT3] KOSPI/KOSDAQ OHLC 반환 — 당일 갭 감지용
const fetchDailyOHLC = async (encodedTicker) => {
  try {
    const symbolMap = { '%5EKS11': 'KOSPI', '%5EKQ11': 'KOSDAQ' };
    const symbol = symbolMap[encodedTicker] || encodedTicker;
    const resp = await fetchDailyFchart(symbol, 120);
    if (!resp || !resp.length) return [];
    return resp.map(d => ({
      date:  d.localDate,                                     // 'YYYYMMDD'
      open:  d.openPrice  > 0 ? d.openPrice  : d.closePrice, // 시가 없으면 종가 fallback
      high:  d.highPrice  > 0 ? d.highPrice  : d.closePrice,
      low:   d.lowPrice   > 0 ? d.lowPrice   : d.closePrice,
      close: d.closePrice,
    }));
  } catch(e) { return []; }
};
```

---

## 그룹 B: `getMarketRegime` 교체

### B-1. 3단계 Regime + 당일 갭 감지

**위치:** `swing_scanner_code.js` — `getMarketRegime` 함수 전체 교체 (line ~360~379)

**Regime 레벨 정의:**

| Level | 이름 | 조건 | 의미 |
|-------|------|------|------|
| 0 | 강세 (Bull) | SMA20>SMA60 AND SMA5>SMA20 | 정상 진입 허용 |
| 1 | 중립 (Neutral) | SMA20>SMA60 but SMA5<SMA20 | 회복 중 흔들림 — 매도차익 차단 |
| 2 | 약세 (Bear) | SMA20<SMA60 OR 전일 -1.5%↓ OR 당일 갭다운 -0.7%↓ | 강매 전용 |

**갭 감지 로직:**

```
OHLC 배열의 마지막 항목 날짜 vs today(KST) 비교:
  마지막 항목 date == today → 당일 데이터 포함 (장 시작 후 API 반영)
    → ksGap = (오늘 open / 어제 close) - 1
  마지막 항목 date < today  → 어제까지 데이터 (장 전 조회)
    → ksGap = (어제 close / 그제 close) - 1  (전일 변화율로 대체)
```

```js
// BEFORE
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

// AFTER
const getMarketRegime = async (store, today) => {
  if (!store.regimeCache) store.regimeCache = {};
  if (store.regimeCache.date === today && store.regimeCache.regimeLevel !== undefined)
    return store.regimeCache;

  let regimeLevel = 0; // 0=강세, 1=중립, 2=약세
  let ks = null, kq = null, ksUpFast = null, kqUpFast = null;
  let ksGap = 0, kqGap = 0, ksYestChange = 0, kqYestChange = 0;
  let gapSource = 'none'; // 디버그용: 갭 계산 소스 ('today'|'yesterday'|'none')

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

    // ── 기존: SMA20 vs SMA60 (중장기 추세) ──
    const ks20 = sma(ksClose, 20); const ks60 = sma(ksClose, 60);
    const kq20 = sma(kqClose, 20); const kq60 = sma(kqClose, 60);
    ks = (Number.isFinite(ks20[iKs]) && Number.isFinite(ks60[iKs]))
         ? ks20[iKs] > ks60[iKs] : null;
    kq = (Number.isFinite(kq20[iKq]) && Number.isFinite(kq60[iKq]))
         ? kq20[iKq] > kq60[iKq] : null;

    // ── 신규: SMA5 vs SMA20 (단기 모멘텀) ──
    const ks5 = sma(ksClose, REGIME_SMA_FAST);
    const kq5 = sma(kqClose, REGIME_SMA_FAST);
    ksUpFast = Number.isFinite(ks5[iKs]) ? ks5[iKs] > ks20[iKs] : null;
    kqUpFast = Number.isFinite(kq5[iKq]) ? kq5[iKq] > kq20[iKq] : null;

    // ── 신규: 당일 갭 or 전일 변화율 ──
    const todayStr = today.replace(/-/g, ''); // 'YYYYMMDD'
    const ksLastDate = ksOHLC[iKs].date;
    const kqLastDate = kqOHLC[iKq].date;

    if (ksLastDate === todayStr && iKs >= 1) {
      // 당일 데이터 포함 → 오늘 시가 vs 어제 종가
      ksGap = ksOHLC[iKs-1].close > 0
        ? (ksOHLC[iKs].open / ksOHLC[iKs-1].close - 1) : 0;
      gapSource = 'today';
    } else if (iKs >= 1) {
      // 당일 데이터 없음 (장 전) → 어제 종가 변화율로 대체
      ksYestChange = ksOHLC[iKs-1].close > 0
        ? (ksOHLC[iKs].close / ksOHLC[iKs-1].close - 1) : 0;
      ksGap = ksYestChange;
      gapSource = 'yesterday';
    }
    if (kqLastDate === todayStr && iKq >= 1) {
      kqGap = kqOHLC[iKq-1].close > 0
        ? (kqOHLC[iKq].open / kqOHLC[iKq-1].close - 1) : 0;
    } else if (iKq >= 1) {
      kqYestChange = kqOHLC[iKq-1].close > 0
        ? (kqOHLC[iKq].close / kqOHLC[iKq-1].close - 1) : 0;
      kqGap = kqYestChange;
    }

    // ── Regime 레벨 판정 ──
    // 약세(2): SMA20 < SMA60
    if (ks === false || kq === false) regimeLevel = 2;
    // 중립(1): SMA20 > SMA60이지만 SMA5 < SMA20 (회복 중 단기 흔들림)
    else if (ksUpFast === false || kqUpFast === false) regimeLevel = 1;

    // 갭다운 오버라이드 → 약세 강제
    if (ksGap < REGIME_GAP_DOWN || kqGap < REGIME_GAP_DOWN) {
      regimeLevel = Math.max(regimeLevel, 2);
    }

  } catch (e) {
    regimeLevel = 0; // 데이터 오류 시 차단 없이 통과 (보수적 fallback)
  }

  const riskOn = regimeLevel < 2; // 기존 호환성 유지
  store.regimeCache = {
    date: today, riskOn, regimeLevel,
    ksUp: ks, kqUp: kq, ksUpFast, kqUpFast,
    ksGap: (ksGap * 100).toFixed(2) + '%',
    kqGap: (kqGap * 100).toFixed(2) + '%',
    gapSource,
    at: new Date().toISOString(),
  };
  return store.regimeCache;
};
```

---

## 그룹 D: 진입 차단 로직

### D-1. regimeLevel 기반 등급별 차단

**위치:** `swing_scanner_code.js` — `getMarketRegime` 호출 직후 (현재 line ~1443~1449)

```js
// BEFORE
const rg = await getMarketRegime(store, today);
const riskOn = !!(rg && rg.riskOn);
const sizeFactor = riskOn
  ? (pgmCaution ? 0.5  : 1.0)
  : (pgmCaution ? 0.25 : 0.5);
const qty = calcQty(ACCOUNT_KRW, RISK_PCT_PER_TRADE * sizeFactor, currentPrice, stop);

// AFTER
const rg = await getMarketRegime(store, today);
const riskOn     = !!(rg && rg.riskOn);
const regimeLevel = rg?.regimeLevel ?? 0;

// [REGIME-FIX] 시장 단계별 진입 차단
if (regimeLevel >= 2 && grade !== '강매') return; // 약세장: 강매(score≥120) 전용
if (regimeLevel >= 1 && grade === '매도차익') return; // 중립장: 매도차익 차단

// 기존 sizeFactor 로직 유지
const sizeFactor = riskOn
  ? (pgmCaution ? 0.5  : 1.0)
  : (pgmCaution ? 0.25 : 0.5);
const qty = calcQty(ACCOUNT_KRW, RISK_PCT_PER_TRADE * sizeFactor, currentPrice, stop);
```

---

## 그룹 E: REGIME-LOG

### E-1. 매일 1회 Regime 상태 Telegram 알림

**위치:** `swing_scanner_code.js` — `getMarketRegime` 호출 직후, 진입 차단 로직 앞

**적용 시점:** 모든 종목 루프 바깥이 아닌 첫 번째 종목 처리 시점에 실행
→ 단, `store.regimeLogSent !== today` 조건으로 하루 1회 보장

```js
// AFTER (D-1 블록 직후에 삽입)
if (!store.regimeLogSent || store.regimeLogSent !== today) {
  store.regimeLogSent = today;
  const levelLabel = ['강세(0)', '중립(1)', '약세(2)'][regimeLevel] || String(regimeLevel);
  const regimeMsg =
    `${REGIME_LOG_EMOJI} [시장 Regime] ${today}` + NL +
    `수준: ${levelLabel}` + NL +
    `KOSPI SMA20>SMA60: ${rg.ksUp === null ? 'N/A' : (rg.ksUp ? '✅' : '❌')}` + NL +
    `KOSPI SMA5>SMA20:  ${rg.ksUpFast === null ? 'N/A' : (rg.ksUpFast ? '✅' : '❌')}` + NL +
    `KOSPI 갭/전일변화: ${rg.ksGap} (${rg.gapSource})` + NL +
    `KOSDAQ SMA20>SMA60: ${rg.kqUp === null ? 'N/A' : (rg.kqUp ? '✅' : '❌')}` + NL +
    `KOSDAQ SMA5>SMA20:  ${rg.kqUpFast === null ? 'N/A' : (rg.kqUpFast ? '✅' : '❌')}` + NL +
    `KOSDAQ 갭/전일변화: ${rg.kqGap}` + NL +
    (regimeLevel >= 2 ? '⚠️ 약세장 — 강매 등급만 진입 허용' :
     regimeLevel >= 1 ? '⚡ 중립장 — 매도차익 등급 차단' :
     '✅ 강세장 — 전 등급 진입 허용');
  try {
    await http({
      method: 'POST',
      url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
      json: true,
      body: { chat_id: CHAT, text: regimeMsg },
    });
  } catch(e) { /* 로그 발송 실패는 무시 */ }
}
```

---

## 변경 순서 (구현 순서)

```
1. C-1: 상단 상수 4개 추가
2. A-1: fetchDailyOHLC 함수 추가 (fetchDailyClose 뒤)
3. B-1: getMarketRegime 함수 전체 교체
4. D-1: 진입 차단 로직 (getMarketRegime 호출부 수정)
5. E-1: REGIME-LOG 삽입 (D-1 직후)
```

---

## 검증 시나리오

### 시나리오 A — 04-30 재현 테스트

| 조건 | 예상 Regime | 예상 결과 |
|------|------------|---------|
| KOSPI SMA20>SMA60(회복), SMA5<SMA20, 갭-0.5% | regimeLevel=1 (중립) | 매도차익 차단, 강매·급등 통과 |
| KOSPI SMA20>SMA60(회복), SMA5<SMA20, 갭-1.0% | regimeLevel=2 (약세) | 강매만 통과 |
| KOSPI SMA20<SMA60 | regimeLevel=2 (약세) | 강매만 통과 |
| KOSPI 정상, SMA5>SMA20, 갭+0.2% | regimeLevel=0 (강세) | 기존과 동일, 전 등급 허용 |

### 시나리오 B — 04-30 SIMPAC/LS머트리얼즈 차단 가능 여부

```
04-30 추정 상태:
  KOSPI 4주 회복 → SMA20 vs SMA60: 불확실 (직접 확인 필요)
  SMA5 vs SMA20: 회복 중 등락 → SMA5 < SMA20 가능성 높음 → regimeLevel=1 최소

  SIMPAC 등급이 '매도차익'이었다면:
    → regimeLevel=1(중립)에서도 차단됨

  SIMPAC 등급이 '급등'이었다면:
    → regimeLevel=1에선 통과, regimeLevel=2에서만 차단

※ 04-30 전일(04-29) 또는 당일 KOSPI 변화율이 -0.7% 이하였다면 regimeLevel=2 → 전면 차단
```

---

## 주요 결정 사항 및 근거

| 결정 | 선택 | 이유 |
|------|------|------|
| 갭 임계값 | -0.7% | 일반적 노이즈(-0.3%) 대비 의미 있는 약세 신호. 너무 낮게(–0.3%) 설정 시 false positive 증가 |
| 전일 변화율 임계값 | -1.5% | KOSPI 일반 등락 범위 ±1% 대비 명확한 약세 수준 |
| SMA fast 기간 | 5일 | 거래일 기준 1주일 — 빠른 반응이면서 노이즈 필터링 가능 |
| fallback시 regimeLevel | 0 (강세) | 데이터 오류로 인한 과도한 차단 방지. 보수적 필터보다 안정성 우선 |
| 약세장 차단 범위 | 강매 외 전부 | 급등·매도차익은 모멘텀 의존 → 약세장 급반전 위험. 강매(120점+)는 충분한 기술적 신호 |
| 기존 `riskOn` 유지 | `regimeLevel < 2` | sizeFactor 계산 코드 변경 최소화 — 기존 로직 호환성 유지 |

---

## 미변경 항목

| 항목 | 유지 이유 |
|------|---------|
| `fetchDailyClose` 함수 | 다른 로직에서 참조 가능 → 제거 대신 유지, OHLC 함수를 추가 |
| `sizeFactor` 계산 로직 | `riskOn` 호환성 유지, 수량 조정은 기존대로 |
| `RELAX_SCORE = 90` | 품질 기준 현행 유지 |
| 스캐너 시간 게이트 | `09:00~11:30` 현행 유지 |
| MACD/OBV 차단 필터 | 기존 필터 누적 효과 유지 |

# Design: intraday-swing

## 변경 파일
- `swing_scanner_code.js` (단일 파일, 전체 구현)

## 변경 범위 요약

| 그룹 | 항목 수 | 내용 |
|------|---------|------|
| A. 전략 파라미터 전환 | 9 | 시간·보유·목표·품질·발송 기준 |
| B. 신규 데이터 신호 추가 | 5 | 갭·상한가·수급·프로그램·공시 |
| **합계** | **14** | |

---

## 그룹 A: 전략 파라미터 전환

### A-1. 알림 시간 오전 한정 (TIME-01)

**위치:** `swing_scanner_code.js`, line 22~23

```js
// BEFORE
const STOP_NEW_ALERTS_HOUR   = 15;
const STOP_NEW_ALERTS_MINUTE = 20;

// AFTER
const STOP_NEW_ALERTS_HOUR   = 11;
const STOP_NEW_ALERTS_MINUTE = 30;
```

- 유효 알림 창: 09:30 ~ 11:30 KST (2시간)
- 11:30 이후 포착 종목은 당일 청산 여유 부족으로 자동 스킵
- line 406~408 조건문은 변경 불필요 (상수만 교체)

---

### A-2. 전 등급 보유 기간 당일 통일 (HOLD-01)

**위치:** `swing_scanner_code.js`, line 39~55

```js
// BEFORE
const HOLD_STRONG      = 5;
const HOLD_NORMAL      = 6;
const HOLD_WEAK        = 2;
const HOLD_SHORTTRADE  = 3;
const HOLD_SURGE       = 3;

// AFTER
const HOLD_STRONG      = 1;
const HOLD_NORMAL      = 1;
const HOLD_WEAK        = 1;
const HOLD_SHORTTRADE  = 1;
const HOLD_SURGE       = 1;
```

- holdDays 계산 로직(line 1494~1497)은 변경 없음 — 상수값만 교체

---

### A-3. 목표가 상한 당일 기준 축소 (TARGET-01)

**위치:** `swing_scanner_code.js`, line 17~18

```js
// BEFORE
const CAP_TARGET_PCT = 0.25;   // 25% 상한

// AFTER
const CAP_TARGET_PCT = 0.07;   // 7% 상한 (5~7% 당일 목표 허용 범위)
```

- `MIN_TARGET_PCT = 0.05` 는 이미 설정 완료 → 변경 없음
- 결과: 목표가 = 현재가 × 1.05 ~ 1.07 범위로 수렴

---

### A-4. ATR 목표 배수 당일 기준 축소 (TARGET-02)

**위치:** `swing_scanner_code.js`, line 15~16

```js
// BEFORE
const ATR_TARGET_MULT        = 2.8;   // 강매 (5거래일 기준)
const ATR_TARGET_MULT_NORMAL = 2.0;   // 급등·기타 (2거래일 기준)

// AFTER
const ATR_TARGET_MULT        = 0.8;   // 강매 (당일 ATR 범위 내)
const ATR_TARGET_MULT_NORMAL = 0.6;   // 급등·기타 (당일 ATR 범위 내)
```

- ATR(14) 평균 = 일봉 변동폭 기준
- 일봉 ATR × 0.6~0.8 ≈ 당일 변동폭의 60~80% → 5~7% 목표와 자연스럽게 연동

---

### A-5. 손절 기준 당일 타이트 (STOP-01)

**위치:** `swing_scanner_code.js`, line 13~14, 17

```js
// BEFORE
const ATR_STOP_MULT = 1.9;
const CAP_STOP_PCT  = 0.10;   // 최대 -10%

// AFTER
const ATR_STOP_MULT = 1.0;
const CAP_STOP_PCT  = 0.03;   // 최대 -3%
```

- 당일 전략에서 -10% 손절은 하루 손실로 치명적
- -3% 캡으로 자금 보호 → 다음 날 재투입 가능

---

### A-6. 품질 기준 강화 — PMAT 동등 레벨 (QUALITY-01)

**위치:** `swing_scanner_code.js`, line 7

```js
// BEFORE
const RELAX_SCORE = 60;   // 관심 등급 기준

// AFTER
const RELAX_SCORE = 90;   // 사실상 급등(100+) / 강매(120+) 등급만 통과
```

- `strictPass`: score >= MIN_SCORE(80) → 여전히 유지
- `relaxedPass`: score >= RELAX_SCORE → 90으로 상향
- line 1244: `isShortTrade = !isStrong && !isSurge && strictPass` → 매도차익 등급은 strictPass 기반이라 영향 없음
- line 1251: `if (grade === '관심' || grade === '매수') return;` → 이미 차단됨. 추가 효과: score 80~89 종목이 relaxedPass 불통과로 후보군 자체에서 제거

---

### A-7. 중복 차단 윈도우 축소 (DEDUP-01)

**위치:** `swing_scanner_code.js`, line 21

```js
// BEFORE
const DUPLICATE_WINDOW_MINUTES = 4320;  // 3일 (72시간)

// AFTER
const DUPLICATE_WINDOW_MINUTES = 480;   // 8시간 (당일 장 내 중복 방지)
```

- 당일 09:30 추천 종목이 오후에 재추천되는 것을 방지 (8시간 = 당일 장 전체 커버)
- 익일 같은 종목이 조건 재충족 시 정상 추천 가능

---

### A-8. 최대 발송 수 제한 (SENDS-01)

**위치:** `swing_scanner_code.js`, line 19

```js
// BEFORE
const MAX_INTRADAY_SENDS = 4;

// AFTER
const MAX_INTRADAY_SENDS = 2;
```

- 오전 2시간 창 + 최대 2종목 → 사용자가 각 종목에 집중 대응 가능

---

### A-9. 알림 메시지 당일 청산 의도 명시 (MSG-01)

**위치:** `swing_scanner_code.js`, line 1442~1452 (메시지 조립부)

```js
// BEFORE (line 1443)
gradePrefix + '[스윙 포착] ' + c.market + ' | ' + ...

// AFTER
gradePrefix + '[당일단타] ' + c.market + ' | ' + ...
```

```js
// BEFORE (line 1446)
'- 매수가: ' + to0(c.entry) + '원 (전일종가 기준, 시초가 확인 필수)' + NL +

// AFTER
'- 매수가: ' + to0(c.entry) + '원 (시초가 확인 후 진입)' + NL +
'- 청산 목표: 당일 장마감 전 (최대 익일 오전)' + NL +
```

- "스윙 포착" → "당일단타" 로 레이블 변경 (사용자 행동 가이드)
- "청산 목표: 당일" 라인 추가

---

## 그룹 B: 신규 데이터 신호 추가

### B-1. 시가 갭 비율 계산 및 필터 (GAP-UP-01)

**위치:** `swing_scanner_code.js`, line 982~988 (currentPrice 선언 직후)

**데이터:** `openD[dIdx]` 이미 수집 중 (line 978) — 추가 API 불필요

```js
// AFTER: line 985 dailyChange 계산 직후 삽입
const openPrice  = openD[dIdx];
const gapRatio   = prevClose > 0 ? (openPrice / prevClose - 1) : 0;

// 갭다운 -3% 이상 → 당일 단타 불가 (하락 출발 종목 차단)
if (gapRatio < -0.03) return;

// 갭업 +5% 초과 → 추격 진입 위험 (너무 늦은 진입 차단)
if (gapRatio > 0.05) return;

// 유효 갭업 범위: 0% ~ +5% (플랫 or 소폭 갭업)
```

**스코어링 신호 추가** (line 1048 이후 스코어링 블록 내):
```js
// 갭업 신호 보너스 (+10점)
if (gapRatio >= 0.01 && gapRatio <= 0.05) {
  score += 10;
  signals.push('갭업출발(' + pct(gapRatio) + ')');
}
```

---

### B-2. 상한가 잔여 여력 계산 (LIMIT-01)

**위치:** `swing_scanner_code.js`, line 982~988 (currentPrice 선언 직후)

**데이터:** `prevClose` 이미 계산 중 (line 984) — 추가 API 불필요

```js
// 상한가 가격 계산 (한국 시장: 전일 종가 ±30%)
const limitUpPrice  = prevClose * 1.30;
const limitUpRoom   = limitUpPrice > 0 ? (limitUpPrice - currentPrice) / limitUpPrice : 0;

// 상한가 잔여 여력 < 5% → 추격 불가 차단 (상한가 직전 물량 소진)
if (limitUpRoom < 0.05) return;
```

**스코어링 신호 추가**:
```js
// 상한가 10~30% 이내 → 추격 가능 구간 보너스 (+15점)
if (limitUpRoom >= 0.10 && limitUpRoom <= 0.30) {
  score += 15;
  signals.push('상한가여력(' + Math.round(limitUpRoom * 100) + '%)');
}
```

---

### B-3. 외국인/기관 순매수 수급 필터 (FOREIGN-01)

**위치:** 신규 함수 + 스캔 루프 내 필터

**데이터 소스:** KRX 투자자별 거래 API (무료, 15분 지연)

```
POST https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd
Body: bld=dbms/MDC/STAT/standard/MDCSTAT02023
      &mktId=ALL&trdDd={YYYYMMDD}&share=1&money=1&csvxls_isNo=false
```

**응답 필드:**
- `ISU_SRT_CD` — 종목코드
- `FRGN_NETBUY_TRDVAL` — 외국인 순매수금액 (원)
- `ORG_NETBUY_TRDVAL` — 기관합계 순매수금액 (원)

**구현 위치 (캐시 로딩):** `swing_scanner_code.js`, line 419~450 (리스크 블랙리스트 로딩 직후)

```js
// ===== 수급 데이터 로딩 (외국인/기관 순매수) =====
// 1회 캐싱: 당일 trdDd 기준, store.supplyCache에 저장
let supplyMap = {};   // { '005930': { frgn: 12345678, org: 9876543 } }
const supCacheKey = today.replace(/-/g, '');
if (store.supplyCache && store.supplyCache.trdDd === supCacheKey) {
  supplyMap = store.supplyCache.map || {};
} else {
  try {
    const supBody = `bld=dbms/MDC/STAT/standard/MDCSTAT02023&mktId=ALL&trdDd=${supCacheKey}&share=1&money=1&csvxls_isNo=false`;
    const supR = await http({
      method: 'POST',
      url: 'https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': 'https://data.krx.co.kr',
        'Referer': 'https://data.krx.co.kr/',
        'User-Agent': 'Mozilla/5.0',
      },
      body: supBody, json: true,
    });
    const supRows = (supR && (supR.output || supR.OutBlock_1 || [])) || [];
    for (const row of supRows) {
      const code = String(row.ISU_SRT_CD || '').trim();
      if (!code) continue;
      const frgn = Number(String(row.FRGN_NETBUY_TRDVAL || '0').replace(/,/g, ''));
      const org  = Number(String(row.ORG_NETBUY_TRDVAL  || '0').replace(/,/g, ''));
      supplyMap[code] = { frgn, org };
    }
    store.supplyCache = { trdDd: supCacheKey, map: supplyMap };
  } catch (e) {
    // 수급 로딩 실패 시 supplyMap = {} → 해당 필터 스킵, 스캔 계속 진행
  }
}
// ===== /수급 데이터 로딩 =====
```

**스코어링 신호 추가** (스코어링 블록 내, OBV 계산 이후):
```js
// 외국인/기관 수급 보너스
const sup = supplyMap[code] || {};
const frgnNet = sup.frgn || 0;
const orgNet  = sup.org  || 0;

if (frgnNet > 0 && orgNet > 0) {
  score += 20;
  signals.push('외국인+기관동반순매수');
} else if (frgnNet > 500_000_000) {       // 외국인 5억 이상 순매수
  score += 15;
  signals.push('외국인순매수');
} else if (orgNet > 500_000_000) {         // 기관 5억 이상 순매수
  score += 10;
  signals.push('기관순매수');
} else if (frgnNet < -500_000_000 || orgNet < -500_000_000) {
  return; // 외국인 또는 기관 대량 순매도 → 차단
}
```

---

### B-4. 프로그램 매매 방향 필터 (PROGRAM-01)

**위치:** `swing_scanner_code.js` 상단 시장 레짐 로딩 직후

**데이터 소스:** KRX 프로그램 매매 API (무료)

```
POST https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd
Body: bld=dbms/MDC/STAT/standard/MDCSTAT05401
      &trdDd={YYYYMMDD}&csvxls_isNo=false
```

**응답 필드:**
- `ARBT_BUY_TRDVAL` — 차익 매수금액
- `ARBT_SELL_TRDVAL` — 차익 매도금액
- `NABT_BUY_TRDVAL` — 비차익 매수금액
- `NABT_SELL_TRDVAL` — 비차익 매도금액

**구현 위치:** 수급 데이터 로딩 직후

```js
// ===== 프로그램 매매 방향 로딩 =====
let programNetBuy = null;  // null = 데이터 없음 (필터 스킵), 양수 = 순매수, 음수 = 순매도
const pgmCacheKey = today.replace(/-/g, '');
if (store.programCache && store.programCache.trdDd === pgmCacheKey) {
  programNetBuy = store.programCache.netBuy;
} else {
  try {
    const pgmBody = `bld=dbms/MDC/STAT/standard/MDCSTAT05401&trdDd=${pgmCacheKey}&csvxls_isNo=false`;
    const pgmR = await http({
      method: 'POST',
      url: 'https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'Origin': 'https://data.krx.co.kr', 'User-Agent': 'Mozilla/5.0' },
      body: pgmBody, json: true,
    });
    const pgmRows = (pgmR && (pgmR.output || pgmR.OutBlock_1 || [])) || [];
    if (pgmRows.length > 0) {
      const row = pgmRows[0];
      const toNum = (v) => Number(String(v || '0').replace(/,/g, ''));
      const totalBuy  = toNum(row.ARBT_BUY_TRDVAL)  + toNum(row.NABT_BUY_TRDVAL);
      const totalSell = toNum(row.ARBT_SELL_TRDVAL) + toNum(row.NABT_SELL_TRDVAL);
      programNetBuy = totalBuy - totalSell;
    }
    store.programCache = { trdDd: pgmCacheKey, netBuy: programNetBuy };
  } catch (e) {
    // 실패 시 programNetBuy = null → 필터 스킵
  }
}

// 프로그램 대량 순매도 (-5,000억 이하) → 당일 롱 포지션 전체 위험
// 전체 스캔을 중단하지는 않되, 시장 레짐 보정 (sizeFactor 추가 감소)
const pgmCaution = (programNetBuy !== null && programNetBuy < -500_000_000_000);
// → getMarketRegime 결과와 함께 sizeFactor 0.5→0.25로 추가 감소
// ===== /프로그램 매매 방향 로딩 =====
```

**sizeFactor 적용 변경** (line 1292 근처):
```js
// BEFORE
const sizeFactor = riskOn ? 1.0 : 0.5;

// AFTER
const sizeFactor = riskOn
  ? (pgmCaution ? 0.5 : 1.0)   // 프로그램 매도 경고 시 절반
  : (pgmCaution ? 0.25 : 0.5); // 둘 다 위험 시 1/4
```

**알림 메시지 추가 (프로그램 경고 시):**
```js
// pgmCaution 시 메시지 상단에 경고 추가
const pgmWarnLine = pgmCaution
  ? '⚠️ 프로그램 대량 순매도 진행 중 — 사이징 주의' + NL
  : '';
```

---

### B-5. 공시(KIND/DART) 당일 이슈 여부 (DART-01)

**위치:** 종목별 스캔 루프 내, 최종 점수 계산 직전

**데이터 소스:** DART OpenAPI (무료, 발급 필요)
- 등록: `https://opendart.fss.or.kr` (무료 API 키 발급)
- 하루 최대 10,000건 쿼리

**구현 방식:** 개별 종목별 실시간 조회 대신, 당일 공시 목록을 한 번에 캐싱

```
GET https://opendart.fss.or.kr/api/list.json
  ?crtfc_key={DART_API_KEY}
  &bgn_de={YYYYMMDD}
  &end_de={YYYYMMDD}
  &page_no=1
  &page_count=100
```

**응답 필드:**
- `corp_code` — DART 고유 법인코드 (종목코드와 다름 → 매핑 필요)
- `stock_code` — 종목코드 (6자리, 직접 사용 가능)
- `report_nm` — 공시 제목
- `rcept_dt` — 접수 날짜

**구현 위치:** 수급 데이터 로딩 직후

```js
// ===== 당일 공시 목록 로딩 (DART OpenAPI) =====
// 요구사항: DART_API_KEY 환경변수 또는 store 설정값 필요
const DART_API_KEY = store.dartApiKey || '';   // n8n 환경변수에서 주입
let dartToday = {};  // { '005930': ['분기보고서', '단일판매·공급계약체결'] }

if (DART_API_KEY) {
  const dartCacheKey = today.replace(/-/g, '');
  if (store.dartCache && store.dartCache.trdDd === dartCacheKey) {
    dartToday = store.dartCache.map || {};
  } else {
    try {
      const dartUrl = `https://opendart.fss.or.kr/api/list.json?crtfc_key=${DART_API_KEY}&bgn_de=${dartCacheKey}&end_de=${dartCacheKey}&page_no=1&page_count=100`;
      const dartR = await http({ method: 'GET', url: dartUrl, json: true });
      const dartList = (dartR && dartR.list) || [];
      for (const item of dartList) {
        const sc = String(item.stock_code || '').trim();
        if (!sc) continue;
        if (!dartToday[sc]) dartToday[sc] = [];
        dartToday[sc].push(String(item.report_nm || '').slice(0, 40));
      }
      store.dartCache = { trdDd: dartCacheKey, map: dartToday };
    } catch (e) {
      // 실패 시 dartToday = {} → 공시 필터 스킵
    }
  }
}
// ===== /공시 목록 로딩 =====
```

**스코어링 신호 추가** (스코어링 블록 내):
```js
// 당일 공시 존재 시 보너스/경고
const dartItems = dartToday[code] || [];
if (dartItems.length > 0) {
  const reportNames = dartItems.join(' ');
  // 긍정 공시: 계약체결, 특허, 인허가, 대규모투자
  const isPositive = /계약체결|특허|인허가|수주|투자유치|증자/.test(reportNames);
  // 부정 공시: 소송, 횡령, 불성실공시, 감사의견
  const isNegative = /소송|횡령|배임|감사의견|불성실|조회/.test(reportNames);

  if (isNegative) {
    return; // 부정 공시 종목 즉시 차단
  } else if (isPositive) {
    score += 20;
    signals.push('긍정공시(' + dartItems[0].slice(0, 12) + ')');
  } else {
    score += 5;  // 기타 공시 (분기보고서 등) 소폭 보너스
    signals.push('당일공시');
  }
}
```

**주의:** DART_API_KEY를 n8n 환경변수 또는 `store.dartApiKey`에 설정 필요.
미설정 시 공시 필터 자동 스킵 (기존 동작 유지).

---

## 스코어링 최종 변화 요약

| 신호 | 점수 | 조건 |
|------|------|------|
| 갭업출발 (B-1) | +10 | 시가 갭 +1%~+5% |
| 상한가여력 (B-2) | +15 | 상한가까지 10~30% 남음 |
| 외국인+기관동반 (B-3) | +20 | 외국인·기관 동시 순매수 |
| 외국인순매수 (B-3) | +15 | 외국인 5억+ 순매수 |
| 기관순매수 (B-3) | +10 | 기관 5억+ 순매수 |
| 긍정공시 (B-5) | +20 | 계약·특허·수주 등 |
| 당일공시 (B-5) | +5 | 기타 공시 |

| 차단 조건 | 기준 |
|-----------|------|
| 갭다운 차단 (B-1) | 시가 갭 < -3% |
| 추격 불가 차단 (B-1) | 시가 갭 > +5% |
| 상한가 임박 차단 (B-2) | 상한가 여력 < 5% |
| 외국인/기관 대량 매도 (B-3) | 5억+ 순매도 |
| 부정공시 차단 (B-5) | 소송·횡령·불성실 |
| 프로그램 경고 (B-4) | 5천억+ 순매도 시 sizeF 감소 |

---

## 구현 순서 (Do 단계 체크리스트)

### Phase 1: 상수 변경 (A 그룹, 30분 소요)
- [ ] **A-1** `STOP_NEW_ALERTS_HOUR=11`, `STOP_NEW_ALERTS_MINUTE=30`
- [ ] **A-2** `HOLD_*` 전부 `1`
- [ ] **A-3** `CAP_TARGET_PCT=0.07`
- [ ] **A-4** `ATR_TARGET_MULT=0.8`, `ATR_TARGET_MULT_NORMAL=0.6`
- [ ] **A-5** `ATR_STOP_MULT=1.0`, `CAP_STOP_PCT=0.03`
- [ ] **A-6** `RELAX_SCORE=90`
- [ ] **A-7** `DUPLICATE_WINDOW_MINUTES=480`
- [ ] **A-8** `MAX_INTRADAY_SENDS=2`
- [ ] **A-9** 알림 메시지 "당일단타", "청산 목표: 당일" 추가

### Phase 2: 신규 신호 — API 없는 것 먼저 (B-1, B-2, 30분 소요)
- [ ] **B-1** 시가 갭 비율 계산 + 필터 + 스코어링
- [ ] **B-2** 상한가 잔여 여력 계산 + 필터 + 스코어링

### Phase 3: KRX API 연동 (B-3, B-4, 60분 소요)
- [ ] **B-3** `supplyMap` 캐시 로딩 + 외국인/기관 스코어링 + 매도 차단
- [ ] **B-4** `programNetBuy` 캐시 로딩 + `sizeFactor` 연동 + 경고 메시지

### Phase 4: DART API 연동 (B-5, 60분 소요)
- [ ] **B-5** `dartToday` 캐시 로딩 (DART_API_KEY 필요) + 긍정/부정 공시 분기 + 스코어링

---

## 리스크 및 예외 처리

| 항목 | 리스크 | 처리 방안 |
|------|--------|-----------|
| KRX 수급 API 실패 | 장중 서버 부하 시 응답 없음 | `try/catch` → `supplyMap = {}` → 해당 필터 스킵 |
| KRX 프로그램 API 실패 | 동일 | `programNetBuy = null` → sizeFactor 미변경 |
| DART API 미설정 | API 키 없음 | `DART_API_KEY` 없으면 로딩 블록 자체 스킵 |
| DART API 실패 | 일시적 오류 | `dartToday = {}` → 공시 필터 스킵 |
| 갭 계산 오류 | `openD[dIdx]` = 0 또는 누락 | `openD` fallback 이미 `rawClose`로 대체됨 (line 978) |
| 상한가 계산 오류 | `prevClose = 0` | `prevClose > 0` 조건 체크 후 계산 |

---

## 변경 전후 알림 메시지 비교

```
BEFORE:
[★강매] [스윙 포착] KOSPI | 삼성전자(005930)
등급: 강매
기준가: 82,000원 (전일 대비 +2.1%)
- 매수가: 82,000원 (전일종가 기준, 시초가 확인 필수)
- 1차 목표: 87,740원 (+7.0%)
- 최종 목표: 102,500원 (+25.0%)
- 손절가: 73,800원 (-10.0%)
ATR(14): 2,100원
- 점수: 145점
핵심 시그널: 일봉정배열, 52주신고가돌파, 거래량급증(A)

AFTER:
[★강매] [당일단타] KOSPI | 삼성전자(005930)
등급: 강매
기준가: 82,000원 (전일 대비 +2.1%)
- 매수가: 82,000원 (시초가 확인 후 진입)
- 청산 목표: 당일 장마감 전 (최대 익일 오전)
- 1차 목표: 87,740원 (+7.0%)
- 최종 목표: 88,560원 (+7.0%)
- 손절가: 79,540원 (-3.0%)
ATR(14): 2,100원
- 점수: 160점
핵심 시그널: 일봉정배열, 외국인순매수, 갭업출발(+2.1%)
```

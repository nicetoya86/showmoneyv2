## Executive Summary

| Item | Detail |
|------|--------|
| Feature | swing-etf-dedup |
| Start Date | 2026-05-12 |
| Target Phase | Do |

| Perspective | Content |
|-------------|---------|
| Problem | 동일 ETF가 격주로 반복 추천되고, CORRELATION_GROUPS 미등록 동일지수 ETF(KODEX/TIGER KOSPI200 등)가 같은 주에 중복 발송됨 |
| Solution | ETF 정확 티커 14일 중복 차단 + 지수 추종 그룹 확장으로 모든 동일기초자산 ETF 1주 1건 제한 |
| UX Effect | 주간 리포트에 동일 ETF/동일지수 ETF 중복 없이 다양한 종목 노출 |
| Core Value | ETF 추천 다양성 보장 + 반복 중복으로 인한 집중 리스크 해소 |

---

# [Plan] swing-etf-dedup

## 1. 개요

### 1.1 문제 정의

`swing-quality-improvement` 개선 후에도 남아있는 ETF 중복 추천 패턴:

| 케이스 | 현재 상태 | 문제 |
|--------|-----------|------|
| 동일 ETF 티커 격주 반복 | `swingSent` 8시간 차단만 존재 | 다음 주 월요일에 동일 ETF 재추천 가능 |
| 동일지수 ETF 혼재 | `CORRELATION_GROUPS` 키워드 미등록 시 미차단 | KODEX KOSPI200 + TIGER 코스피200 동시 발송 가능 |
| 14일 데이터 미활용 | `weeklyRecommendations`에 14일 보관하지만 체크는 현재 주만 | 2주치 중복 방지 로직이 사실상 무력화 |

**현재 코드 흐름**:
```
thisWeekRecs = 이번 주(월~일) 발송 기록만
pickBest() → isCorrelationDuplicate(name, thisWeekRecs) → 이번 주만 체크
weeklyRecommendations → 14일 보관하지만 2번째 주 이후 체크 없음
```

### 1.2 근본 원인

1. **14일 윈도우 미활용**: `weeklyRecommendations`에 14일치 데이터가 있지만 `thisWeekRecs`는 현재 주만 수집
2. **정확 티커 중복 미차단**: `isCorrelationDuplicate`는 키워드 그룹 기반 → 정확히 같은 티커도 키워드 미등록 시 통과
3. **CORRELATION_GROUPS 불완전**: `코스피200` 키워드가 있어도 `코스피 200`(공백 포함), `KRX300`, `코스닥150` 등 누락

---

## 2. 개선 방향

### 개선 1: ETF 정확 티커 14일 중복 차단 (즉시 적용)

**대상**: `swing_scanner_code.js` — `pickBest()` 함수 내 ETF 필터링

**구현**:
```js
// 14일 윈도우 전체 발송 기록 (현재 weeklyRecommendations 14일 보관 활용)
const ALL_RECENT_RECS = Object.values(store.weeklyRecommendations)
  .flat()
  .filter(r => r && r.ticker);

// ETF 정확 티커 중복 체크
const isEtfTickerDuplicate = (ticker, recentRecs) => {
  return recentRecs.some(r => r.ticker === ticker);
};
```

**적용 위치**: `pickBest()` 내 ETF pool 필터링 시 추가

```js
const pickBest = (pool, maxPicks, isEtfPool = false) => {
  const picked = [];
  for (const c of pool) {
    if (picked.length >= maxPicks) break;
    const alreadySent = [...thisWeekRecs, ...picked];
    if (isCorrelationDuplicate(c.name, alreadySent)) continue;
    // [ETF-DEDUP-1] ETF는 14일 내 동일 티커 재추천 차단
    if (isEtfPool && isEtfTickerDuplicate(c.ticker, ALL_RECENT_RECS)) continue;
    picked.push(c);
  }
  return picked;
};
```

**호출 시 플래그 전달**:
```js
const selectedETF   = pickBest(etfCandidates,   etfSlots,   true);   // ETF: 14일 티커 체크
const selectedStock = pickBest(stockCandidates, stockSlots, false);  // 개별주: 기존 로직
```

**효과**: 지난 주에 추천된 `TIGER 2차전지TOP10` → 이번 주 재추천 불가

---

### 개선 2: CORRELATION_GROUPS 확장 (즉시 적용)

**대상**: `swing_scanner_code.js` — `CORRELATION_GROUPS` 상수

**현재 그룹 (5개)**:
```js
['삼성전자', '삼성그룹', '삼성'],
['차이나', '중국', 'china'],
['반도체', 'AI반도체', 'FACTSET', 'semiconductor'],
['나스닥', '미국나스닥', 'nasdaq'],
['코스피200', 'KRX300'],
```

**추가할 그룹 (7개)**:
```js
['코스피', 'kospi', 'KRX'],                             // 코스피 종합 지수 계열
['코스닥', 'kosdaq'],                                   // 코스닥 지수 계열
['2차전지', '배터리', 'battery', 'LG에너지', 'K배터리'],  // 배터리 테마
['바이오', '헬스케어', 'healthcare', 'bio'],            // 바이오/헬스케어 테마
['S&P500', 'sp500', 'S&P 500', '미국S&P'],             // S&P500 계열
['금', 'gold', 'GLD'],                                 // 금 원자재
['원유', 'oil', 'WTI', '에너지'],                       // 에너지/원유 계열
```

**결합 결과 (12개 그룹)**:
동일 지수/테마 ETF가 같은 주에 1건만 발송되도록 보장

---

### 개선 3: 상수 이름 변경 및 문서화

**대상**: `swing_scanner_code.js` — 상수 블록

```js
// ===== [ETF-DEDUP] ETF 중복 차단 개선 상수 (2026-05-12) =====
const ETF_DEDUP_WINDOW_DAYS = 14;   // ETF 정확 티커 중복 차단 기간 (weeklyRecommendations 보관 기간과 동일)
// CORRELATION_GROUPS 확장 → 12개 그룹 (기존 5개 + 신규 7개)
// ===== /ETF-DEDUP =====
```

---

## 3. 구현 범위

### 수정 파일

| 파일 | 수정 위치 | 수정 내용 |
|------|-----------|-----------|
| `swing_scanner_code.js` (n8n 노드 내 코드) | 상수 블록 `CORRELATION_GROUPS` | 7개 그룹 추가 |
| `swing_scanner_code.js` | 상수 블록 `CORRELATION_GROUPS` 아래 | `ETF_DEDUP_WINDOW_DAYS` 상수 추가 |
| `swing_scanner_code.js` | `isCorrelationDuplicate` 함수 아래 | `isEtfTickerDuplicate` 함수 추가 |
| `swing_scanner_code.js` | `pickBest()` 함수 | `isEtfPool` 파라미터 + ETF 티커 중복 체크 추가 |
| `swing_scanner_code.js` | `pickBest()` 호출부 | ETF 호출 시 `true` 플래그 전달 |

### n8n 워크플로우 반영

- 수정된 코드를 `autostock_showmoneyv2_*.json`의 해당 Code 노드에 반영
- 노드명: (현재 워크플로우의 Swing Scanner Code 노드)

---

## 4. 구현 순서

1. `CORRELATION_GROUPS` 상수에 7개 신규 그룹 추가
2. `ETF_DEDUP_WINDOW_DAYS = 14` 상수 추가
3. `ALL_RECENT_RECS` 변수 — `weeklyRecommendations` 전체 플랫맵 (상단 초기화 블록에 추가)
4. `isEtfTickerDuplicate(ticker, recentRecs)` 함수 추가
5. `pickBest(pool, maxPicks, isEtfPool = false)` 시그니처 변경 + 내부 필터 추가
6. `pickBest(etfCandidates, etfSlots, true)` 호출 수정
7. `swing_scanner_code.txt` 업데이트
8. n8n 워크플로우 JSON 업데이트 및 배포

---

## 5. 수용 기준 (Acceptance Criteria)

| # | 기준 | 검증 방법 |
|---|------|-----------|
| AC-1 | 지난 14일 이내 발송된 ETF 티커는 `pickBest()` ETF pool에서 제외됨 | 코드 리뷰: `isEtfTickerDuplicate` 호출 확인 |
| AC-2 | `CORRELATION_GROUPS`가 12개 그룹으로 확장됨 | 코드 리뷰: 상수 확인 |
| AC-3 | KODEX KOSPI200과 TIGER 코스피 ETF가 같은 주에 동시 추천되지 않음 | `코스피` 키워드 그룹 매칭 확인 |
| AC-4 | 2차전지 관련 ETF (TIGER 2차전지, ACE K배터리 등)가 같은 주 1건만 발송됨 | 로그 확인 |
| AC-5 | 개별주(isETF=false)는 기존 로직 그대로 동작 (14일 티커 차단 미적용) | 코드 리뷰 |
| AC-6 | `ALL_RECENT_RECS`가 `store.weeklyRecommendations` 전체(14일)를 기반으로 생성됨 | 코드 리뷰 |

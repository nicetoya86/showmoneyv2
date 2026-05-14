## Executive Summary

| Item | Detail |
|------|--------|
| Feature | swing-stock-only |
| Start Date | 2026-05-12 |
| Target Phase | Do |

| Perspective | Content |
|-------------|---------|
| Problem | 스윙 추천에 ETF가 포함되어 단일종목 포트폴리오 다양성이 낮고, 채권혼합·커버드콜 등 부적합 ETF 추천이 잦음 |
| Solution | ETF를 최종 선발 풀에서 완전 제외, 코스피·코스닥 단일종목만 추천 (하루 최대 2건) |
| UX Effect | 텔레그램 추천 종목이 모두 단일종목으로 구성, ETF 관련 손절·채권 리스크 소거 |
| Core Value | 스윙 전략 순도 향상 + 개별주 발굴 기회 극대화 |

---

# [Plan] swing-stock-only

## 1. 개요

### 1.1 문제 정의

| 지표 | 현재 | 문제 |
|------|------|------|
| ETF 선발 슬롯 | `MAX_ETF_PER_SEND = 1` | 하루 발송 2건 중 1건이 ETF에 배정됨 |
| 개별주 슬롯 | `MAX_STOCK_PER_SEND = 1` | 개별주는 절반 슬롯만 사용 |
| ETF 손절 비중 | 주간 3건 손절 중 ETF 비중 높음 | 채권혼합·커버드콜 ETF 부적합 진입 |
| 개별주 기회 누락 | ETF가 슬롯 점유 | 강한 모멘텀 개별주가 후순위로 밀림 |

### 1.2 요청 사항

> "종목 추천 조건에 ETF는 제외하고, 단일 종목만 추천할 수 있도록 반영해줘"

**목표**: ETF를 최종 선발(`pickBest`) 단계에서 완전 배제, 개별주만 추천

### 1.3 기존 흐름 vs 변경 후

**현재 흐름**:
```
qualifiedCandidates
  ├── etfCandidates  → pickBest(etfCandidates, etfSlots=1)   → selectedETF
  └── stockCandidates → pickBest(stockCandidates, stockSlots=1) → selectedStock
selected = [...selectedETF, ...selectedStock]  // 최대 2건 (ETF 1 + 개별주 1)
```

**변경 후 흐름**:
```
qualifiedCandidates
  └── stockCandidates (isETF=false 만) → pickBest(stockCandidates, MAX_STOCK_PER_SEND=2) → selected
selected = stockCandidates only  // 최대 2건 (개별주만)
```

---

## 2. 개선 방향 상세

### 개선 1: ETF 완전 제외 — 선발 풀 변경 (핵심)

**대상**: `swing_scanner_code.js` — 후보 선발 로직 (line ~1799)

**변경 전**:
```js
const etfCandidates   = qualifiedCandidates.filter(c =>  c.isETF);
const stockCandidates = qualifiedCandidates.filter(c => !c.isETF);

const etfSlots   = Math.min(MAX_ETF_PER_SEND,   Math.floor(remainingSlots / 2) || 1);
const stockSlots = Math.min(MAX_STOCK_PER_SEND,  remainingSlots - etfSlots);
const selectedETF   = pickBest(etfCandidates,   etfSlots);
const selectedStock = pickBest(stockCandidates, stockSlots);
const selected = [...selectedETF, ...selectedStock].slice(0, remainingSlots);
```

**변경 후**:
```js
// [STOCK-ONLY] ETF 완전 제외 — 개별주만 선발 (2026-05-12)
const stockCandidates = qualifiedCandidates.filter(c => !c.isETF);
const selected = pickBest(stockCandidates, remainingSlots);
```

**효과**:
- `remainingSlots`(최대 2) 전부 개별주에 배정
- ETF는 스코어링까지는 진행되지만 최종 선발에서 제외

---

### 개선 2: 상수 정리

**대상**: `swing_scanner_code.js` — 상수 블록 (`swing-quality-improvement` 상수)

| 상수 | 현재 값 | 변경 |
|------|---------|------|
| `MAX_ETF_PER_SEND` | `1` | `0` 으로 변경 (명시적 비활성화, 삭제보다 가독성 우선) |
| `MAX_STOCK_PER_SEND` | `1` | `2` 로 변경 (하루 최대 2건 개별주) |

```js
const MAX_ETF_PER_SEND   = 0;   // [STOCK-ONLY] ETF 추천 비활성화 (2026-05-12)
const MAX_STOCK_PER_SEND = 2;   // [STOCK-ONLY] 개별주 하루 최대 2건
```

**참고**: `ETF_EXCLUDE_KEYWORDS`, `ETF_PROVIDERS`, `isETFName()`, `ETF_SCORE_PENALTY` 등 ETF 관련 상수/함수는 **삭제하지 않음** — `isETF` 플래그 계산에 여전히 필요 (선발 단계 필터링 기준)

---

### 개선 3: 메시지 레이블 정리

**대상**: `swing_scanner_code.js` — 텔레그램 메시지 생성 (line ~1865)

**변경 전**:
```js
const typeLabel = c.isETF ? 'ETF' : '단일종목';
```

**변경 후**:
```js
const typeLabel = '단일종목';  // [STOCK-ONLY] ETF 제외 후 항상 단일종목
```

---

### 개선 4: `swing-etf-dedup` 플랜 대체

`docs/01-plan/features/swing-etf-dedup.plan.md` (2026-05-12 작성)은 본 플랜으로 **대체**됨.
- ETF를 완전 제외하면 ETF 중복 방지 로직은 불필요
- `CORRELATION_GROUPS` 확장(개선 2)은 **개별주 중복 방지** 목적으로 유지

---

## 3. 구현 범위

### 수정 위치 요약

| 파일 (n8n 노드 코드) | 위치 | 변경 내용 |
|---------------------|------|-----------|
| `swing_scanner_code.js` | 상수 블록 `MAX_ETF_PER_SEND` | `1 → 0` |
| `swing_scanner_code.js` | 상수 블록 `MAX_STOCK_PER_SEND` | `1 → 2` |
| `swing_scanner_code.js` | 선발 로직 (`etfCandidates` 분리) | 제거 후 `stockCandidates` 단일 풀로 통합 |
| `swing_scanner_code.js` | `etfSlots`, `stockSlots` 계산 | 제거, `remainingSlots` 직접 사용 |
| `swing_scanner_code.js` | `selectedETF`, `pickBest(etfCandidates)` 호출 | 제거 |
| `swing_scanner_code.js` | `typeLabel` 계산 | 고정값 `'단일종목'` |

### 수정하지 않는 것

| 항목 | 이유 |
|------|------|
| `isETFName()` 함수 | `isETF` 플래그 계산에 필요 (필터 기준) |
| `ETF_EXCLUDE_KEYWORDS` 상수 | 기존 QI-1 필터에서 사용 (완전 삭제 시 사이드이펙트 위험) |
| `ETF_PROVIDERS` 상수 | `isETFName()` 에서 참조 |
| `ETF_SCORE_PENALTY` 상수 | `finalRankScore` 계산 시 사용 (스코어링은 유지) |
| `CORRELATION_GROUPS` | 개별주 중복 방지 목적으로 유지 |
| `isETF` candidate 속성 | `weeklyRecommendations` 저장 태그로 유지 (분석용) |

---

## 4. 구현 순서

1. **상수 변경**: `MAX_ETF_PER_SEND = 0`, `MAX_STOCK_PER_SEND = 2`
2. **선발 로직 교체**: `etfCandidates` / `etfSlots` / `selectedETF` 제거, `stockCandidates` 단일 풀
3. **`typeLabel` 수정**: 고정값 `'단일종목'`
4. **`swing_scanner_code.txt` 업데이트**
5. **n8n 워크플로우 JSON 업데이트**: 해당 Code 노드에 수정 코드 반영

---

## 5. 수용 기준 (Acceptance Criteria)

| # | 기준 | 검증 방법 |
|---|------|-----------|
| AC-1 | `qualifiedCandidates`에 ETF가 포함되어도 `selected`에는 ETF(`isETF=true`)가 없음 | 코드 리뷰: `stockCandidates` 필터 확인 |
| AC-2 | 하루 추천이 최대 2건이며 모두 단일종목 | 코드 리뷰: `pickBest(stockCandidates, remainingSlots)` 확인 |
| AC-3 | 텔레그램 메시지의 `typeLabel`이 항상 `'단일종목'` | 코드 리뷰 |
| AC-4 | `MAX_ETF_PER_SEND = 0`, `MAX_STOCK_PER_SEND = 2` | 상수 확인 |
| AC-5 | `isETFName()`, `ETF_PROVIDERS`, `ETF_EXCLUDE_KEYWORDS` 함수/상수가 코드에 잔존 | 코드 리뷰 |
| AC-6 | 기존 개별주 필터(`STOCK_RSI_MAX=85`, `STOCK_ADX_MIN=15`, `STOCK_MIN_TURNOVER=50억`) 유지 | 코드 리뷰 |

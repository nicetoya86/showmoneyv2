## Executive Summary

| Item | Detail |
|------|--------|
| Feature | swing-quality-improvement |
| Start Date | 2026-05-09 |
| Target Phase | Do |

| Perspective | Content |
|-------------|---------|
| Problem | 주간 추천 8건 중 3건 손절(37.5%), ETF 채권혼합·커버드콜 필터 부재, 점수↑=손절 역상관, 단일종목 추천 미포함 |
| Solution | ETF 유형필터·상관관계 중복차단·스코어 재보정·미도달 추적·단일종목 균형 선발·주간 추천수 제한 |
| UX Effect | 주간 리포트 손절률 감소, ETF+코스피/코스닥 단일종목 혼합 포트폴리오 |
| Core Value | 수익 추천 확률 향상 + 다양한 종목군 커버로 기회 확대 |

---

# [Plan] swing-quality-improvement

## 1. 개요

### 1.1 문제 정의

2026-05-04 ~ 05-08 주간 리포트 분석 결과:

| 지표 | 값 | 문제 |
|------|-----|------|
| 총 추천 | 8건 | — |
| 매수 미도달 | 4건 (50%) | 지정가 역추세 진입 → 상승장에서 미체결 |
| 손절 | 3건 (진입 4건 중 75%) | 채권혼합ETF, 삼성 중복, 점수↑=손실 역상관 |
| ETF 독점 | 8건 전부 ETF | 코스피/코스닥 단일종목 기회 누락 |

**손절 3건 세부 원인:**
- `KODEX 삼성그룹밸류(240점)` — 당일 손절. 高점수=고위험 패턴
- `SOL 글로벌AI반도체탑픽액티브(230점)` — AI반도체 고베타, RSI 과매수 구간
- `KODEX 삼성전자채권혼합(225점)` — 채권 혼합으로 상승 변동성 상쇄, 스윙 부적합

### 1.2 근본 원인

1. **ETF 유형 미분류**: 채권혼합, 커버드콜, 배당혼합 ETF가 필터 없이 통과
2. **상관관계 무검사**: 동일주차에 삼성전자 관련 ETF 2개 동시 편입
3. **점수-수익 역상관**: 215점→수익, 225~240점→손절. 스코어링 모델 왜곡
4. **진입가 로직**: 역추세 지정가 설정 → 상승 모멘텀 환경서 50% 미도달
5. **단일종목 부재**: ETF 우세 필터(RSI 45~80, ADX≥20, SMA정배열)가 개별주 과도 차단
6. **추천수 미제한**: 주간 8건 분산 → 집중도 저하

---

## 2. 개선 방향 상세 (6+1)

### 개선 1: ETF 유형 필터 (즉시 적용)

**대상**: `swing_scanner_code.js` — 종목 필터링 루프 (line ~930)

**제외 유형**:
- 채권혼합: `채권혼합`, `채권형`, `혼합형`
- 커버드콜: `커버드콜`, `coveredcall`, `covered call`
- 배당혼합: `배당혼합`, `고배당혼합`
- 인버스/레버리지: `인버스`, `레버리지` (이미 고위험, 스윙 부적합)

**구현 위치**: ETF 이름 기반 제외 (종목명에 키워드 포함 시 건너뜀)

```js
const ETF_EXCLUDE_KEYWORDS = ['채권혼합', '채권형', '혼합형', '커버드콜', '배당혼합', '인버스', '레버리지'];
if (ETF_EXCLUDE_KEYWORDS.some(kw => nm.includes(kw))) continue;
```

**효과**: `KODEX 삼성전자채권혼합` 유형 사전 제거

---

### 개선 2: 상관관계 중복 차단 (즉시 적용)

**대상**: `swing_scanner_code.js` — 후보 선발 로직 (line ~1668)

**구현**: 발송 시점에 `store.weeklyRecommendations` 참조하여 당주 동일 기초자산 ETF 중복 차단

**차단 키워드 그룹**:
```js
const CORRELATION_GROUPS = [
  ['삼성전자', '삼성그룹', '삼성'], // 삼성 관련
  ['차이나', '중국'],              // 중국 관련
  ['반도체', 'AI반도체', 'FACTSET'], // 반도체 관련
  ['나스닥', '미국나스닥'],          // 나스닥 관련
];
```

**규칙**: 동일 그룹에서 주간 최대 1종목만 발송

---

### 개선 3: 스코어 역상관 보정 (즉시 적용)

**대상**: `swing_scanner_code.js` — 후보 선발 & 정렬 로직

**문제 패턴**: ETF의 SMA 정배열, OBV, BB 보너스가 과도하게 누적 → 고점수=저위험 개별주보다 ETF 편향

**보정 방법**:
1. ETF 감지: 발행사 키워드 기반 `isETF` 플래그 설정
2. ETF의 `rankScore`에 -15점 패널티 (개별주 대비 공정 경쟁)
3. 최소 스코어 기준 상향: `MIN_SCORE 80 → 100`
4. 당일 진입+손절 빈발 패턴 차단: 진입 당일 손절이 3회 이상인 등급 신호 → 해당 장세에서 진입 억제

**ETF 발행사 감지 패턴**:
```js
const ETF_PROVIDERS = ['KODEX', 'TIGER', 'KBSTAR', 'ACE', 'SOL', 'HANARO', 'TIME', 'ARIRANG', 'KOSEF', 'MASTER', 'TIMEFOLIO'];
const isETF = ETF_PROVIDERS.some(p => nm.toUpperCase().startsWith(p)) || nm.includes('ETF');
```

---

### 개선 4: 미도달 종목 추적 로직 추가

**대상**: `weekly_reporter_code.js` — 미도달 섹션 처리

**구현**: `not_entered` 종목에 대해 Naver API로 이후 가격 추적
- 추천일 이후 3거래일 가격 조회
- 미도달 후 가격이 매수가 대비 +N% 이상 이동했으면 `missed_opportunity`로 분류
- 주간 리포트에 `⚡ 미도달 후 상승` 섹션 추가 (진입가 재검토 시그널)

**진입가 적응 신호**: 미도달+이후상승이 3주 연속 발생 → 다음 주 진입가를 전일 종가 기준에서 시가(오픈 가격) 기준으로 변경 제안

---

### 개선 5: 당일 즉시 손절 억제 (즉시 적용)

**대상**: `swing_scanner_code.js` — regime 판단 & 알림 발송 로직

**추가 조건**: 
- 장 시작 후 30분 이내(09:00~09:30)에 이미 손절 신호 2회 이상 → 해당 일 신규 진입 억제
- `store.intradayStopCount[today]` 카운터 추적
- 카운터 ≥ 2 이면 그날 발송 없이 종료

**구현 위치**: 발송 루프 전 체크

---

### 개선 6: 주간 추천수 제한 (즉시 적용)

**대상**: `swing_scanner_code.js` — weeklyRecommendations 저장 시

**현황**: 주간 최대 10건 (5일 × 2건/일)
**변경**: 주간 5건 한도 (`MAX_WEEKLY_SENDS = 5`)

**구현**:
```js
const MAX_WEEKLY_SENDS = 5;
const thisWeekSends = weekDates.reduce((sum, d) => sum + (store.weeklyRecommendations[d]?.length || 0), 0);
if (thisWeekSends >= MAX_WEEKLY_SENDS) return; // 주간 한도 초과 시 발송 안 함
```

---

### 개선 7: 코스피/코스닥 단일종목 포함 (신규)

**대상**: `swing_scanner_code.js` — 후보 선발 로직

**문제 분석**: 현재 ETF가 모든 필터를 통과하는 이유:
- RSI 45~80 범위: ETF는 변동성이 낮아 범위 내 유지 용이
- ADX ≥ 20: ETF 추세가 안정적
- SMA 정배열: ETF는 매끄러운 이동평균선 유지

**개별주 포함 방법**:
1. `isETF` 플래그로 ETF / 개별주 분리
2. 후보에서 ETF 후보 / 개별주 후보를 각각 별도 선발
3. 발송: `ETF 최대 1건 + 개별주 최대 1건` (일일 최대 2건 유지)
4. 개별주 전용 완화 기준:
   - RSI 상한: 75 → 85 (상승 모멘텀 강한 개별주 허용)
   - ADX 최소: 20 → 15 (개별주는 종목 고유 추세로 판단)
   - SMA 정배열 예외 허용 조건 확장: `isSurgeCandidate` 외 `RSI ≥ 70 AND RVOL ≥ 3.0` 추가

**개별주 선발 조건 (추가)**:
- 최소 거래대금: 50억 이상 (ETF보다 상향, 유동성 보장)
- 52주 신고가 근접(PTH ≥ 0.85) OR 박스권 돌파 필수
- 정치 테마 블랙리스트 제외 (기존 `themeSet` 유지)

---

## 3. 구현 범위

### 수정 파일

| 파일 | 수정 내용 |
|------|-----------|
| `swing_scanner_code.js` | 개선 1,2,3,5,6,7 — 필터·선발·발송 로직 |
| `weekly_reporter_code.js` | 개선 4 — 미도달 추적, 리포트 섹션 추가 |

### 상수 추가/변경

```js
// ===== swing-quality-improvement 개선 상수 =====
const ETF_EXCLUDE_KEYWORDS = ['채권혼합', '채권형', '혼합형', '커버드콜', '배당혼합', '고배당혼합', '인버스', '레버리지'];
const ETF_PROVIDERS = ['KODEX', 'TIGER', 'KBSTAR', 'ACE', 'SOL', 'HANARO', 'TIME', 'ARIRANG', 'KOSEF', 'MASTER', 'TIMEFOLIO'];
const ETF_SCORE_PENALTY = 15;         // ETF rankScore 패널티
const MIN_SCORE_IMPROVED = 100;       // 개선된 최소 점수 기준 (80→100)
const MAX_WEEKLY_SENDS = 5;           // 주간 최대 추천 건수
const MAX_ETF_PER_SEND = 1;           // 1회 발송 ETF 최대 1건
const MAX_STOCK_PER_SEND = 1;         // 1회 발송 개별주 최대 1건
const INTRADAY_STOP_THRESHOLD = 2;    // 당일 손절 카운터 임계값
const STOCK_MIN_TURNOVER = 5_000_000_000; // 개별주 최소 거래대금 50억
const STOCK_RSI_MAX = 85;             // 개별주 RSI 상한 완화
const STOCK_ADX_MIN = 15;             // 개별주 ADX 최소 완화
const CORRELATION_GROUPS = [
  ['삼성전자', '삼성그룹', '삼성'],
  ['차이나', '중국'],
  ['반도체', 'AI반도체', 'FACTSET'],
  ['나스닥', '미국나스닥'],
  ['코스피200', 'KRX'],
];
// ===== /swing-quality-improvement 상수 =====
```

---

## 4. 구현 순서

1. **상수 추가** — 파일 상단 상수 블록
2. **ETF 감지 함수** — `isETFName(nm)` 헬퍼 추가
3. **ETF 유형 필터** — 종목 로딩 루프 내 적용
4. **개별주 기준 완화** — 필터 조건 분기 추가
5. **미도달 추적** — `weeklyRecommendations` not_entered 저장
6. **상관관계 차단** — 후보 선발 직전 주간 중복 체크
7. **스코어 보정** — rankScore 계산 시 ETF 패널티
8. **당일 손절 억제** — `intradayStopCount` 추가 및 체크
9. **주간 한도** — 발송 전 주간 누적 건수 체크
10. **선발 로직** — ETF/개별주 분리 선발
11. **weekly_reporter.js** — 미도달 추적 결과 섹션 추가

---

## 5. 수용 기준 (Acceptance Criteria)

| # | 기준 | 검증 방법 |
|---|------|-----------|
| AC-1 | `채권혼합`, `커버드콜` 이름 ETF는 후보에서 제외됨 | 코드 리뷰 |
| AC-2 | 동일주차 동일 상관그룹 ETF는 1건만 발송됨 | 코드 리뷰 |
| AC-3 | 코스피/코스닥 개별주가 주간 리포트에 최소 1건 이상 포함 가능 | 실행 로그 |
| AC-4 | ETF rankScore에 -15점 패널티 적용됨 | 코드 리뷰 |
| AC-5 | 주간 발송 누적이 5건 초과 시 발송 없음 | 코드 리뷰 |
| AC-6 | 미도달 종목의 이후 3일 가격이 weeklyRecommendations에 저장됨 | 코드 리뷰 |
| AC-7 | 당일 손절 카운터 ≥ 2면 신규 발송 없음 | 코드 리뷰 |

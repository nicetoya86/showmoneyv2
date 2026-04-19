# Plan: swing-macd-rsi-risk-filter

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | swing-macd-rsi-risk-filter |
| 기반 | swing-algorithm-improvement 완료 이후 추가 품질 개선 |
| 핵심 목표 | MACD/RSI 지표 강화 + 상장폐지·테마주 고위험 종목 필터 활성화 |
| 작성일 | 2026-04-19 |

### Value Delivered (4-Perspective)

| 관점 | 내용 |
|------|------|
| **Problem** | MACD/RSI가 점수 보너스에 그쳐 하락 모멘텀 종목 통과, 테마주 필터가 비활성화('off')되어 고위험 종목 포함 |
| **Solution** | MACD 히스토그램 방향 필터化 + RSI 상승 모멘텀 조건 추가 + 테마주 필터 활성화 + 상장폐지 위험 종목 조기 차단 |
| **Function UX Effect** | 주간 리포트 손절(❌) 종목 감소, 고위험 종목 배제로 포트폴리오 안정성 향상 |
| **Core Value** | 모멘텀 확인 + 위험 종목 제거로 추천 품질의 정밀도 제고 |

---

## 1. 현재 코드 현황 분석

### 1.1 MACD 현황

**위치:** `swing_scanner_code.js`, STOCK-1 섹션

```javascript
// 현재: 점수 보너스/패널티만 적용
if (macdResult.goldenCross)           score += 15;  // 골든크로스
else if (hist > 0 && hist > histPrev) score += 10;  // 모멘텀 상승
else if (hist > 0)                    score += 5;   // 단순 양호
else if (hist < 0 && histPrev < 0)    score -= 10;  // 지속 하락 패널티
```

**문제:**
- MACD 히스토그램이 음수(-) 이고 하락 중이어도 다른 점수가 높으면 통과
- 하락 모멘텀 종목이 패턴 점수(N자형+40, 박스권돌파+35)만으로 충분히 통과 가능
- `-10점` 패널티는 총점이 120~150점대일 때 사실상 무의미

### 1.2 RSI 현황

**위치:** `swing_scanner_code.js`, line 988~994

```javascript
// 현재: 범위 필터(45~80) + 보너스(65~75: +10)
if (rsi14Val < RSI_MIN_ENTRY) return;  // 45 미만 차단
if (rsi14Val > RSI_MAX_ENTRY) return;  // 80 초과 차단
if (rsi14Val >= 65 && rsi14Val <= 75)  score += 10;  // 골든존 보너스
```

**문제:**
- RSI 방향성 미확인 — RSI 60이지만 하락 중(70→60)인 종목과 상승 중(50→60)인 종목을 동일하게 처리
- RSI가 50 이하(하락 추세 구간)인 경우도 45 이상이면 통과

### 1.3 테마주 필터 현황

**위치:** `swing_scanner_code.js`, line 419~422

```javascript
const themeFilterMode = String(bl.themeFilterMode || 'off').toLowerCase(); // 기본값 'off'
const themeSet = (themeFilterMode === 'off') ? new Set() : new Set((bl.themeCodes || []));
```

**문제:**
- `themeFilterMode`가 `'off'`이면 `themeSet`이 빈 Set → **테마주 필터 완전 비활성화**
- `Refresh_Theme_Blacklist_Naver_ORIGINAL.js`가 주기적으로 `themeCodes`를 갱신하지만 사용 안 됨

### 1.4 상장폐지 위험 필터 현황

**위치:** `swing_scanner_code.js`, line 419~420, 719

```javascript
const riskSet = new Set((bl.riskCodes || []).map(String));  // Refresh 워크플로우가 갱신
if (riskSet.has(rc)) { excludedRisk++; continue; }          // 필터 적용
```

**현황:**
- 코드 자체는 정상 구현
- `Refresh_Risk_Blacklist_KRX_KIND_ORIGINAL.js`가 정상 실행 중이면 riskCodes 자동 갱신
- 추가 강화 포인트: 시가총액 기준 극소형주(penny stock), 관리종목 지정 조건

---

## 2. 갭 분석 (현재 vs 목표)

### GAP-01: MACD 히스토그램 하락 — 필수 차단 조건 미적용

- **현재:** `hist < 0 && histPrev < 0` → -10점 패널티 (통과 가능)
- **목표:** 강매 등급 제외 시 MACD 히스토그램이 **연속 하락 중**이면 차단
- **개선안:** MACD 필터 추가

```javascript
// 개선: MACD 히스토그램이 음수 + 하락 중이면 강매 제외 차단
const macdNegativeTrend = (Number.isFinite(macdResult.hist) && macdResult.hist < 0
                          && Number.isFinite(macdResult.histPrev) && macdResult.histPrev < 0);
// [점수 계산 후, RELAX_SCORE 통과 후 등급 판정 이전에 적용]
if (macdNegativeTrend && grade !== '강매') return; // 하락 모멘텀 차단
```

### GAP-02: RSI 방향성 미확인

- **현재:** RSI 값 범위만 확인 (45~80), 방향성 무시
- **목표:** RSI가 상승 중인 종목만 통과 (직전 5거래일 RSI 평균 대비 현재 RSI 우위)
- **개선안:** RSI 모멘텀 방향 체크 추가

```javascript
// RSI 5거래일 평균 대비 현재 RSI 확인 (상승 모멘텀 확인)
const rsi5DayAvg = calcRSI14 기준으로 5일 전 RSI와 비교
// RSI가 하락 중(현재 < 5일 전)이면 추가 점수 없음 or 필터
```

**구체적 구현 — RSI 방향성 상수 및 로직:**
```javascript
const RSI_RISING_BONUS = 10; // RSI가 상승 중이면 추가 점수 (기존 RSI보너스 대체)

// 5거래일 전 RSI 계산
const rsi5DayAgo = calcRSI14(closeD, Math.max(0, dIdx - 5));
const rsiRising = Number.isFinite(rsi5DayAgo) && rsi14Val > rsi5DayAgo;

// 기존 RSI 골든존(65~75) 보너스 → RSI 상승 중 조건으로 확장
if (Number.isFinite(rsi14Val)) {
  if (rsiRising && rsi14Val >= 50) score += RSI_RISING_BONUS;  // 상승 중 & 50 이상
  if (rsi14Val >= 65 && rsi14Val <= 75) score += 5;            // 골든존 추가 보너스 (축소)
}
```

### GAP-03: 테마주 필터 비활성화

- **현재:** `themeFilterMode = 'off'` (기본값) → 필터 미작동
- **목표:** 테마주 필터 활성화 → `themeFilterMode = 'on'`
- **개선안:** 기본값 변경

```javascript
// 현재
const themeFilterMode = String(bl.themeFilterMode || 'off').toLowerCase();

// 개선: 기본값 'on'으로 변경
const themeFilterMode = String(bl.themeFilterMode || 'on').toLowerCase();
```

**주의:** `Refresh_Theme_Blacklist_Naver_ORIGINAL.js` 워크플로우가 정상 실행 중이어야 `bl.themeCodes`가 채워짐. 워크플로우 비활성 시 `themeSet`이 비어 필터 미작동 → 안전함.

### GAP-04: 상장폐지 위험 종목 — 추가 안전장치

- **현재:** `riskSet` 필터 존재 (Refresh 워크플로우 의존)
- **목표:** Refresh 워크플로우가 실행 안 되더라도 기본 조건으로 고위험 종목 차단
- **개선안:** 상장폐지 위험 시그널 추가 조건

```javascript
// 추가 안전장치: 시가총액 극소형(거래대금 기반) + 연속 하한가 패턴 감지
// 거래대금은 이미 MIN_INTRADAY_TURNOVER (30억) 필터로 1차 차단됨
// 추가: 5일 연속 하락 + 거래량 급감 = 상장폐지 징후 패턴 탐지
const DELIST_CONSEC_DOWN = 5;   // 연속 하락일 기준
const DELIST_VOL_DROP = 0.3;    // 거래량 30% 이하로 급감

// 5일 연속 하락 + 거래량 급감 확인
let consecDown = 0;
for (let ci = dIdx - 4; ci <= dIdx; ci++) {
  if (ci > 0 && closeD[ci] < closeD[ci - 1]) consecDown++;
}
const recentVol = volD.slice(Math.max(0, dIdx - 3), dIdx + 1).reduce((a, b) => a + b, 0) / 4;
const prevVol = volD.slice(Math.max(0, dIdx - 8), dIdx - 3).reduce((a, b) => a + b, 0) / 5;
const volDropped = prevVol > 0 && (recentVol / prevVol) < DELIST_VOL_DROP;
if (consecDown >= DELIST_CONSEC_DOWN && volDropped) return; // 상장폐지 위험 패턴 차단
```

---

## 3. 개선 알고리즘 설계

### 3.1 변경 사항 요약

| # | 항목 | 현재 | 개선안 | 근거 |
|---|------|------|--------|------|
| 1 | MACD 필터 | -10점 패널티 | **강매 제외 시 연속 하락 → 차단** | 하락 모멘텀 종목 통과 방지 |
| 2 | RSI 방향성 | 범위 필터만 | **RSI 상승 중(5일 전 대비) + 보너스** | 방향성 없는 RSI 미반영 보완 |
| 3 | 테마주 필터 | 'off' (비활성) | **'on' (기본 활성화)** | Refresh 워크플로우 연동 |
| 4 | 상폐 위험 추가 | riskSet 필터만 | **연속 하락 + 거래량 급감 패턴 차단** | Refresh 미실행 시 보완 |

### 3.2 적용 위치 및 순서

```
swing_scanner_code.js 변경 위치:

1. 상수 영역 (상단):
   - RSI_RISING_BONUS = 10 추가
   - DELIST_CONSEC_DOWN = 5 추가
   - DELIST_VOL_DROP = 0.3 추가

2. line 421 (테마주 기본값):
   - 'off' → 'on'

3. RSI 점수 영역 (기존 RSI 골든존 보너스 대체):
   - 5일 전 RSI 계산 추가
   - rsiRising 조건으로 보너스 확장

4. STOCK-1 섹션 이후, 등급 판정 후 (grade 확인 후):
   - MACD 연속 하락 차단 조건 추가 (OBV-01 필터 바로 아래)

5. RSI 필터 영역 (line 988~994) 바로 아래:
   - 상폐 위험 패턴 차단 조건 추가
```

### 3.3 적용 후 스코어링 변화 예시

**시나리오 A — MACD 하락 중인 종목 (개선 후 차단)**
```
기존: score = 120 (패턴 점수) - 10 (MACD 하락) = 110점 → 발송
개선: score = 110점이지만 MACD 연속 하락 → grade 판정 후 차단 (강매 아니면 제외)
```

**시나리오 B — RSI 상승 중 (개선 후 더 높은 점수)**
```
기존: RSI = 62, 65~75 아님 → RSI 보너스 없음
개선: RSI 5일 전 = 55, 현재 = 62 (상승 중) + 50 이상 → +10점 보너스
```

**시나리오 C — 테마주 (개선 후 자동 차단)**
```
기존: themeFilterMode = 'off' → 테마주 통과
개선: themeFilterMode = 'on' → bl.themeCodes에 포함된 종목 자동 차단
```

---

## 4. 구현 범위 (Do 단계)

### 4.1 변경 파일
- `swing_scanner_code.js` — 주요 알고리즘 변경
- 워크플로우 JSON 재생성

### 4.2 변경 항목 체크리스트

- [x] **CONST-01**: RSI_RISING_BONUS, DELIST_CONSEC_DOWN, DELIST_VOL_DROP 상수 추가
- [x] **THEME-01**: themeFilterMode 기본값 'off' → 'on'
- [x] **RSI-01**: RSI 5일 방향성 체크 추가 + 보너스 조건 확장
- [x] **MACD-01**: MACD 연속 하락 → 강매 제외 차단 조건 추가
- [x] **DELIST-01**: 연속 하락 + 거래량 급감 패턴 차단 추가
- [x] **JSON-01**: 워크플로우 JSON 재생성 (workflow_FINAL_20260419_152529_swing_macd_rsi_risk_filter.json)

### 4.3 미변경 항목 (현행 유지)

| 항목 | 유지 이유 |
|------|-----------|
| RSI 범위 필터 (45~80) | 이미 적정 |
| ADX 최소 추세 강도 (20) | 현행 유지 |
| MACD 점수 보너스 (+15/+10/+5) | 필터 외 보너스는 유지 |
| riskSet 블랙리스트 필터 | 이미 작동 중 |

---

## 5. 리스크 및 제약

| 리스크 | 내용 | 대응 |
|--------|------|------|
| 테마주 필터 활성화로 추천 수 감소 | themeCodes에 정상 종목 포함 가능성 | Refresh 워크플로우 정확성 의존, 오탐 발생 시 'off' 복귀 |
| MACD 차단으로 유망 종목 미발송 | 단기 조정 중 좋은 종목도 차단 가능 | 강매 등급(OBV+RVOL 확인)은 예외 |
| 상폐 패턴이 정상 조정과 혼동 | 5일 하락 + 거래량 30% 급감은 일부 정상 종목도 해당 | 기준 완화 가능 (DELIST_CONSEC_DOWN = 4 or 5) |
| RSI 방향성 추가로 추천 감소 | 50 이상 조건으로 일부 차단 | 단기 추세 모멘텀 품질 향상 효과가 더 큼 |

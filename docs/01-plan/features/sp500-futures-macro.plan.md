## Executive Summary

| Item | Detail |
|------|--------|
| Feature | sp500-futures-macro |
| Start Date | 2026-05-17 |
| Target Phase | Do (구현 완료) |

| Perspective | Content |
|-------------|---------|
| Problem | 나스닥 전일 종가 기준 매크로 판단은 최대 16시간 전 정보 — 한국장 09:00 KST 시점의 실시간 미국 시장 방향성 반영 불가 |
| Solution | S&P500 E-mini 선물(ES=F) 5분봉 실시간 조회 추가, 나스닥과 OR 결합으로 외부 약세 신호 단일 카운트 |
| UX Effect | 매일 Telegram Regime 알림에 `S&P500선물(실시간):` 항목 추가 — 야간 선물 하락 시 ⚠️ 즉시 확인 가능 |
| Core Value | 전날 데이터가 아닌 당일 실시간 미국 선물 레벨로 Regime 판정 정확도 향상 |

---

# [Plan] sp500-futures-macro

## 1. 개요

### 1.1 문제 정의

기존 매크로 Regime 판정에서 사용하는 나스닥 지수(`^IXIC`)는 **전일 종가 기준**이다.

| 시나리오 | 기존 | 문제 |
|----------|------|------|
| 한국장 개장 09:00 KST | 나스닥 전일(-1% 체크) | 미국 장 마감(05:00 KST) 이후 4시간 경과, 선물 시장 방향 미반영 |
| 야간 미국 선물 급락 후 | 전일 종가 정상 → Regime=강세 허용 | 실제 야간 선물 -1.5% 하락했어도 경고 없이 추천 발송 |
| 미국 이벤트(FOMC, CPI) | 전일 종가만 참조 | 이벤트 직후 선물 반응을 당일 스캔에 반영 불가 |

S&P500 E-mini 선물(`ES=F`)은 거의 24시간 거래되므로, 09:00 KST 스캔 시점에서 **야간 선물 변화율**을 실시간으로 조회할 수 있다.

### 1.2 근본 원인

- 나스닥: 마지막 거래 ~ 한국 시장 개장 사이 **4~8시간 정보 공백**
- 선물 시장 반응(FOMC, 실적, 지정학 이슈)이 당일 스캔에 미반영
- S&P500 선물과 나스닥은 고상관이므로, 둘 다 독립 카운트 시 regimeLevel 과도 상승 위험

---

## 2. 개선 방향 상세

### 개선 1: ES=F 실시간 조회 (핵심)

**대상**: `swing_scanner_code.js` — `fetchMacroIndicators` 함수

**방식**: Yahoo Finance `/v8/finance/chart/ES%3DF?interval=5m&range=1d`
- `meta.chartPreviousClose` = 전일 정규세션 종가 (기준값)
- 5분봉 마지막 종가 = 현재 선물 레벨 (실시간)
- `esFutChg = 현재 / 전일종가 - 1` → 야간 변화율

**임계값**: `SP500_DOWN_THRESH = -0.007` (-0.7%)
- 나스닥(-1%)보다 민감하게 설정 (S&P500은 변동성 낮음)
- 야간 선물 -0.7% 이하 시 외부 약세 신호 발동

---

### 개선 2: OR 결합으로 중복 카운트 방지

**설계 원칙**: 나스닥과 ES=F는 고상관(r ≈ 0.95), 둘이 동시 트리거될 경우 macroAdj를 2 올리면 regimeLevel 과도 상승

**구현**:
```js
// 나스닥 전일 OR S&P500선물 실시간 중 하나라도 임계치 이하 → 단 +1
const extMarketBear = (nasdaqChg < -0.01) || (esFutChg < -0.007);
if (extMarketBear) macroAdj++;   // 최대 1회
if (vixLevel > 25) macroAdj++;  // VIX는 독립 신호 → 별도 +1
```

**조합별 동작**:
| 나스닥 | ES=F 선물 | VIX | macroAdj | 결과 |
|--------|-----------|-----|----------|------|
| 정상   | 정상      | 정상 | 0 | regimeLevel 유지 |
| 하락   | 정상      | 정상 | +1 | 중립 또는 약세 |
| 정상   | 하락      | 정상 | +1 | 중립 또는 약세 (실시간 선물 반영!) |
| 하락   | 하락      | 정상 | +1 | 중복 방지 — 과도 상승 차단 |
| 하락   | 하락      | 고VIX | +2 | 강한 약세 신호 |

---

### 개선 3: Telegram Regime 알림 업데이트

**추가 항목**:
```
S&P500선물(실시간): -0.82% ⚠️
```

**경고 조건**: `parseFloat(esFutChg) < -0.7` → ⚠️ 표시

---

## 3. 구현 범위

### 수정 파일

| 파일 | 수정 내용 |
|------|-----------|
| `swing_scanner_code.js` | 상수 추가, `fetchMacroIndicators` ES=F 조회, `getMarketRegime` OR 결합, Telegram 알림 |

### 상수 추가

```js
// ===== 매크로 경제 Regime 상수 (2026-05-17 방식A) =====
const NASDAQ_DOWN_THRESH = -0.01;  // 나스닥 전일 -1% 이하
const SP500_DOWN_THRESH  = -0.007; // S&P500 선물 -0.7% 이하 (실시간, 나스닥과 OR 조합)
const VIX_HIGH_THRESH    = 25;     // VIX 25 초과
```

### 변경 함수

| 함수 | 변경 내용 |
|------|-----------|
| `fetchMacroIndicators` | `Promise.all` 3개로 확장 (ES=F 추가), `esFutChg` 반환 |
| `getMarketRegime` | `extMarketBear` OR 결합 로직, `regimeCache.esFutChg` 필드 추가 |
| Telegram 알림 블록 | `S&P500선물(실시간):` 줄 추가 |

---

## 4. 구현 순서

1. `SP500_DOWN_THRESH` 상수 추가 (매크로 상수 블록)
2. `fetchMacroIndicators` — ES=F 5분봉 조회 + `chartPreviousClose` 기준 변화율 계산
3. `getMarketRegime` MACRO-A 블록 — `extMarketBear` OR 결합
4. `regimeCache` — `esFutChg` 필드 추가
5. Telegram 알림 — `S&P500선물(실시간):` 항목 + ⚠️ 경고

---

## 5. 수용 기준 (Acceptance Criteria)

| # | 기준 | 검증 방법 |
|---|------|-----------|
| AC-1 | `SP500_DOWN_THRESH = -0.007` 상수 정의됨 | 코드 리뷰 |
| AC-2 | `fetchMacroIndicators`가 ES=F 5분봉을 `interval=5m&range=1d`로 조회 | 코드 리뷰 |
| AC-3 | `chartPreviousClose` 기준 `esFutChg` 계산 후 반환값에 포함 | 코드 리뷰 |
| AC-4 | `extMarketBear = NASDAQ OR ES=F` OR 결합, macroAdj 단 1회 증가 | 코드 리뷰 |
| AC-5 | `regimeCache`에 `esFutChg` 필드 포함 | 코드 리뷰 |
| AC-6 | Telegram 알림에 `S&P500선물(실시간):` 항목 출력 | 코드 리뷰 |
| AC-7 | `-0.7%` 이하 시 ⚠️ 경고 표시 | 코드 리뷰 |
| AC-8 | ES=F 데이터 로드 실패 시 `esFutChg=null` 유지, 차단 없이 통과 | 코드 리뷰 |
| AC-9 | 기존 NASDAQ/VIX 판정 로직 영향 없음 | Gap 분석 |

---

## 6. 리스크 및 대응

| 리스크 | 가능성 | 대응 |
|--------|--------|------|
| Yahoo Finance ES=F 요청 실패 | 중 | try/catch + `null` fallback, 차단 없이 통과 |
| `Promise.all` 하나 실패 시 전체 null | 중 | 기존 동일 패턴, 외부 catch가 보수적 fallback 보장 |
| 5분봉 데이터 부재(거래 없는 시간대) | 저 | `esCloses.length > 0` 체크로 처리 |
| 나스닥+ES=F 동시 하락 시 과도 억제 | 저 | OR 결합으로 macroAdj 최대 +1 보장 |

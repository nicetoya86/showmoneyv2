## Executive Summary

| Item | Detail |
|------|--------|
| Feature | sp500-futures-macro |
| Start Date | 2026-05-17 |
| Updated | 2026-05-28 (설계 변경 반영) |
| Target Phase | Do (구현 완료) |

| Perspective | Content |
|-------------|---------|
| Problem | 나스닥·VIX 각각 독립 +1로 regimeLevel 과잉 상승 — 한국 강세장에서도 미국 지표 하나만 흔들리면 발송 차단 |
| Solution | **[설계 변경]** ES=F 미적용 → NASDAQ AND VIX 동시 약세일 때만 +1 (기존 각 독립 +1 폐기) |
| UX Effect | 한국 강세장에서 미국 지표 단독 약세로 인한 불필요한 발송 차단 해소 |
| Core Value | 과잉 차단 방지 + 진짜 위험 신호(나스닥+VIX 동시 약세) 집중 대응 |

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

## 2. 실제 구현된 설계 (2026-05-28 변경 확정)

> **설계 변경 이유**: ES=F 방식(나스닥 OR ES=F)은 두 지표가 높은 상관관계(r≈0.95)를 갖고
> 있어 OR 결합 시에도 실질적으로 나스닥 단독 트리거와 차이 없음.
> 반면 기존 "각각 독립 +1" 방식은 한국 시장이 강세임에도 나스닥 혼자 -1% 이하면
> regimeLevel이 올라가는 과잉 차단 문제가 있었음.
> → 나스닥+VIX **동시 약세**를 진짜 위험 신호로 재정의.

### 확정된 구현: NASDAQ AND VIX 동시 약세 → +1

```js
// FIX: 나스닥·VIX 독립 +1 → 동시 약세일 때만 +1 (한국 강세장에서 과잉 차단 방지)
const bothMacroWeak = Number.isFinite(nasdaqChg) && nasdaqChg < NASDAQ_DOWN_THRESH
                   && Number.isFinite(vixLevel)  && vixLevel  > VIX_HIGH_THRESH;
if (bothMacroWeak) macroAdj = 1;
regimeLevel = Math.min(2, regimeLevel + macroAdj);
```

**조합별 동작**:
| 나스닥 | VIX | macroAdj | 결과 |
|--------|-----|----------|------|
| 정상   | 정상 | 0 | regimeLevel 유지 |
| -1%+  | 정상 | 0 | 한국 강세면 발송 허용 |
| 정상   | 25+ | 0 | 한국 강세면 발송 허용 |
| -1%+  | 25+ | +1 | 진짜 위험 신호 → regimeLevel 상승 |

### 폐기된 설계: ES=F 실시간 조회

ES=F(S&P500 선물) 실시간 조회는 아래 이유로 구현하지 않기로 결정:
- 나스닥·ES=F 상관관계가 높아 추가 신호 가치 낮음
- 현재 NASDAQ AND VIX 방식이 더 명확한 위험 기준 제공
- 09:00 KST API 응답 지연 위험 감소

---

### Telegram 알림 (변경 없음)

기존 `나스닥 전일:` + `VIX:` + `매크로 Regime조정:` 3줄 유지.
(ES=F 항목 미추가)

---

## 3. 구현 범위

### 수정 파일

| 파일 | 수정 내용 |
|------|-----------|
| `autostock_showmoneyv2_20260527_integrated.json` | `getMarketRegime` MACRO-A 블록 변경 |

### 실제 구현된 상수

```js
// ===== 매크로 경제 Regime 상수 =====
const NASDAQ_DOWN_THRESH = -0.01; // 나스닥 전일 -1% 이하
const VIX_HIGH_THRESH    = 25;    // VIX 25 초과
// SP500_DOWN_THRESH 미사용 (ES=F 미구현)
```

### 변경된 함수

| 함수 | 변경 내용 |
|------|-----------|
| `getMarketRegime` | `bothMacroWeak` AND 결합 로직 (기존 각 독립 +1 → 동시 약세 시에만 +1) |
| `fetchMacroIndicators` | 변경 없음 (나스닥 + VIX 2개 유지, ES=F 미추가) |

---

## 4. 수용 기준 (Acceptance Criteria) — 변경 확정판

| # | 기준 | 상태 |
|---|------|------|
| AC-1 | `NASDAQ_DOWN_THRESH = -0.01`, `VIX_HIGH_THRESH = 25` 상수 정의됨 | ✅ |
| AC-2 | 나스닥 AND VIX 동시 약세일 때만 `macroAdj = 1` | ✅ |
| AC-3 | 나스닥 단독 약세 시 `macroAdj = 0` (한국 강세 보호) | ✅ |
| AC-4 | VIX 단독 고조 시 `macroAdj = 0` | ✅ |
| AC-5 | 매크로 데이터 로드 실패 시 기존 `regimeLevel` 유지 (차단 없이 통과) | ✅ |
| ~~AC-ES=F~~ | ~~ES=F 실시간 조회~~ | ❌ 설계 변경으로 폐기 |

---

## 5. 리스크 및 대응

| 리스크 | 가능성 | 대응 |
|--------|--------|------|
| 나스닥+VIX 기준이 너무 보수적 (진짜 위험 놓침) | 저 | 실증 데이터 축적 후 임계값 재검토 |
| Yahoo Finance 나스닥/VIX 조회 실패 | 중 | try/catch + 기존 regimeLevel 유지 |

# Plan: intraday-swing

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | intraday-swing |
| 기반 | swing-macd-rsi-risk-filter 완료 이후 전략 전환 |
| 핵심 목표 | 다일 보유 스윙 → 당일 매수/당일 매도(최대 1일) 전략 전환 + 추천 품질 집중화 |
| 작성일 | 2026-04-25 |

### Value Delivered (4-Perspective)

| 관점 | 내용 |
|------|------|
| **Problem** | 주간 43건 추천 중 수익 2건(4.6%) — 멀티데이 목표가(최대 25%)는 한국 시장 당일 달성 불가, 보유 31건 누적으로 자금 순환 불가 |
| **Solution** | 알림 시간 오전 한정 + 당일 청산 기준 목표가 5~7% + 품질 기준 강화로 적게 보내되 높은 적중률 |
| **Function UX Effect** | 1일 내 포지션 정리 → 매주 31건 보유 누적 제거, 하루 최대 2건 알림으로 집중 대응 가능 |
| **Core Value** | 자금 순환 속도 향상 + 추천 정확도 향상 → 동일 자본으로 더 많은 수익 기회 |

---

## 1. 현재 코드 현황 분석

### 1.1 알림 시간 게이트

**위치:** `swing_scanner_code.js`, line 22~23, 403~408

```javascript
// 현재: 09:30 ~ 15:20 KST 전 구간 알림
const STOP_NEW_ALERTS_HOUR = 15;
const STOP_NEW_ALERTS_MINUTE = 20;

if (h < 9) return [{ json: { skipped: true, reason: 'Before market open' } }];
if (h === 9 && m < 30) return [...];  // 09:30 이전 차단
if (h > STOP_NEW_ALERTS_HOUR || (h === STOP_NEW_ALERTS_HOUR && m >= STOP_NEW_ALERTS_MINUTE)) {
  return [{ json: { skipped: true, reason: 'Too close to market close' } }];
}
```

**문제:** 오후 3시 직전까지 알림이 발송되어, 당일 청산 시간이 수십 분밖에 남지 않은 종목도 추천됨.

---

### 1.2 보유 기간(Hold) 설정

**위치:** `swing_scanner_code.js`, line 39~55

```javascript
// 현재: 등급별 2~6 거래일 보유 기준
const HOLD_STRONG = 5;        // 강매 등급: 5거래일
const HOLD_NORMAL = 6;        // 매수 등급: 6거래일 (실질 미사용)
const HOLD_WEAK = 2;          // 완화 통과: 2거래일
const HOLD_SHORTTRADE = 3;    // 매도차익: 3거래일
const HOLD_SURGE = 3;         // 급등 등급: 3거래일
```

**문제:** 알림 메시지에 표시되는 "예정일"이 3~6거래일 후로 설정되어, 당일 청산 의도와 불일치. 사용자가 보유 기간을 길게 유지하는 원인.

---

### 1.3 목표가 상한(CAP)

**위치:** `swing_scanner_code.js`, line 17~18, 27

```javascript
// 현재: 목표 최대 25%, 최소 5%
const CAP_TARGET_PCT = 0.25;   // 목표가 상한 25%
const MIN_TARGET_PCT = 0.05;   // 목표가 하한 5% (이미 설정됨)
const ATR_TARGET_MULT = 2.8;         // 강매 등급 목표 배수
const ATR_TARGET_MULT_NORMAL = 2.0;  // 급등·기타 등급 목표 배수
```

**문제:** 목표가 상한 25%는 한국 시장에서 당일 달성 불가능. ATR×2.8은 5거래일 기준 배수로 당일 기준으로는 과도. 실제 당일 달성 가능 범위는 5~7%.

---

### 1.4 품질 필터 (PMAT 제거 이후)

**위치:** `swing_scanner_code.js`, line 6~9

```javascript
// 현재: 점수 기반 필터만 존재 (PMAT 제거됨)
const MIN_SCORE = 80;       // 발송은 차단, 스코어링 기준으로만 유지
const RELAX_SCORE = 60;     // 관심 등급 기준 (50→60 상향 완료)
const MIN_DAILY_PICKS = 0;  // filler 비활성화 — 0건이어도 발송 안 함 ✓
// (PMAT_STRICT, PMAT_RELAX 제거 — HITALK 모델 제거)
```

**문제:** PMAT 제거 이후 점수 기반 필터만 남은 상태. `RELAX_SCORE = 60` 이상이면 완화 통과 가능하여 저품질 종목이 포함될 수 있음.

---

### 1.5 중복 발송 방지 윈도우

**위치:** `swing_scanner_code.js`, line 21

```javascript
// 현재: 동일 종목 3일간 재추천 차단
const DUPLICATE_WINDOW_MINUTES = 4320; // 72시간 (3거래일)
```

**문제:** 당일 전략에서 3일 차단은 과도. 당일 이미 추천된 종목을 다음 날 다시 스캔하지 못함.

---

### 1.6 최대 발송 수

**위치:** `swing_scanner_code.js`, line 19

```javascript
const MAX_INTRADAY_SENDS = 4;  // 스캔당 최대 4종목
```

**문제:** 하루에 최대 4종목은 당일 집중 대응하기엔 과다. 1~2종목에 집중하는 것이 당일 전략에 유리.

---

## 2. 갭 분석 (현재 vs 목표)

### GAP-01: 알림 시간 — 오전 한정 필요

- **현재:** 09:30 ~ 15:20 전 구간 발송
- **목표:** 09:30 ~ 11:30 KST (오전 장 중 2시간으로 한정)
- **근거:** 11:30 이후 포착 종목은 당일 청산 여유 시간이 약 1시간 30분뿐, 목표가 5% 달성 불확실

### GAP-02: 보유 기간 — 당일 기준으로 통일

- **현재:** 강매 5일, 급등 3일, 매도차익 3일, 완화 2일
- **목표:** 전 등급 `1` (당일 또는 익일 조기 청산)
- **근거:** 다일 보유는 자금 순환 불가, 주간 보유 31건 누적 원인

### GAP-03: 목표가 상한 — 당일 달성 가능 수준으로 조정

- **현재:** `CAP_TARGET_PCT = 0.25` (25%), `ATR_TARGET_MULT = 2.8`
- **목표:** `CAP_TARGET_PCT = 0.07` (7%), `ATR_TARGET_MULT = 0.8` / `ATR_TARGET_MULT_NORMAL = 0.6`
- **근거:** 한국 시장 당일 5~7% 모멘텀이 달성 가능한 최대치, 25%는 스윙 기준

### GAP-04: 품질 기준 — PMAT 동등 수준 강화

- **현재:** `RELAX_SCORE = 60` (완화 통과 가능)
- **목표:** `RELAX_SCORE = 90` (급등 등급 100점 기준의 90%)
- **효과:** 사실상 급등(100점+) 또는 강매(120점+) 등급만 통과 → PMAT 0.72 수준의 품질 게이트

### GAP-05: 중복 차단 윈도우 — 당일 기준으로 단축

- **현재:** 4320분 (3일)
- **목표:** 480분 (8시간, 당일 장 내 중복 차단)
- **근거:** 다음 날 같은 종목이 다시 조건 충족하면 재추천 가능해야 함

### GAP-06: 발송 수 제한 — 집중도 향상

- **현재:** `MAX_INTRADAY_SENDS = 4`
- **목표:** `MAX_INTRADAY_SENDS = 2`
- **근거:** 당일 집중 대응을 위해 최대 2종목으로 제한, 분산 추천 방지

### GAP-07: 알림 메시지 — 당일 청산 의도 명시

- **현재:** "예정일: MM-DD" (멀티데이 보유 기준 날짜)
- **목표:** "청산 목표: 당일" 또는 "익일 조기 청산" 표기
- **근거:** 메시지가 보유 기간을 암시해 사용자 행동에 영향

---

## 3. 개선 알고리즘 설계

### 3.1 변경 사항 요약

| # | 항목 | 현재 | 개선안 | 근거 |
|---|------|------|--------|------|
| 1 | 알림 시간 상한 | 15:20 | **11:30** | 당일 청산 여유 시간 확보 |
| 2 | 보유 기간 (전 등급) | 2~6거래일 | **1 (당일)** | 자금 순환, 누적 보유 방지 |
| 3 | 목표가 상한 | 25% | **7%** | 당일 달성 가능 범위 |
| 4 | ATR 목표 배수 (강매) | 2.8 | **0.8** | 당일 변동폭 기준 |
| 5 | ATR 목표 배수 (기타) | 2.0 | **0.6** | 당일 변동폭 기준 |
| 6 | 완화 통과 기준 | 60점 | **90점** | PMAT 0.72 동등 품질 |
| 7 | 중복 차단 윈도우 | 4320분(3일) | **480분(8시간)** | 익일 재추천 허용 |
| 8 | 최대 발송 수 | 4 | **2** | 당일 집중 대응 |
| 9 | 알림 메시지 예정일 | "예정일: N일 후" | **"청산 목표: 당일"** | 의도 명확화 |

---

### 3.2 적용 위치 및 순서

```
swing_scanner_code.js 변경 위치:

1. 상수 영역 (상단, line 4~70):
   - STOP_NEW_ALERTS_HOUR: 15 → 11
   - STOP_NEW_ALERTS_MINUTE: 20 → 30
   - MAX_INTRADAY_SENDS: 4 → 2
   - DUPLICATE_WINDOW_MINUTES: 4320 → 480
   - CAP_TARGET_PCT: 0.25 → 0.07
   - ATR_TARGET_MULT: 2.8 → 0.8
   - ATR_TARGET_MULT_NORMAL: 2.0 → 0.6
   - RELAX_SCORE: 60 → 90
   - HOLD_STRONG: 5 → 1
   - HOLD_NORMAL: 6 → 1
   - HOLD_WEAK: 2 → 1
   - HOLD_SHORTTRADE: 3 → 1
   - HOLD_SURGE: 3 → 1

2. 알림 메시지 영역 (예정일 표기 부분):
   - holdingDays 기반 날짜 계산 → "당일" 고정 텍스트로 변경
```

---

### 3.3 손절 기준 조정

당일 전략에서는 손절도 좁게 설정해야 자금 회전이 빠르다.

| 항목 | 현재 | 개선 |
|------|------|------|
| `ATR_STOP_MULT` | 1.9 | **1.0** (당일 ATR 범위 내) |
| `CAP_STOP_PCT` | 10% | **3%** (당일 최대 손실 제한) |

---

### 3.4 변경 후 시나리오 비교

**시나리오 A — 기존 전략 (강매 등급 종목)**
```
목표가: +18% (ATR×2.8)  →  예정일: 5거래일 후
결과: 당일 +3% 수익에서 청산 안 함, 5일 후 원복 → 보유 누적
```

**시나리오 B — 개선 전략 (동일 종목)**
```
목표가: +6% (ATR×0.8, 최대 7% 캡)  →  청산 목표: 당일
결과: 당일 +3~6% 구간에서 청산 → 자금 순환
```

**시나리오 C — 품질 필터 강화 효과**
```
기존: RELAX_SCORE=60 → 완화 통과 종목 포함, 주간 43건 추천
개선: RELAX_SCORE=90 → 급등/강매 등급만 통과, 주간 5~10건 추천 예상
```

---

## 4. 구현 범위 (Do 단계)

### 4.1 변경 파일

- `swing_scanner_code.js` — 상수 변경 + 메시지 포맷 변경

### 4.2 변경 항목 체크리스트

- [ ] **TIME-01**: `STOP_NEW_ALERTS_HOUR = 11`, `STOP_NEW_ALERTS_MINUTE = 30`
- [ ] **HOLD-01**: `HOLD_STRONG/NORMAL/WEAK/SHORTTRADE/SURGE` 전부 `1`로 변경
- [ ] **TARGET-01**: `CAP_TARGET_PCT = 0.07`
- [ ] **TARGET-02**: `ATR_TARGET_MULT = 0.8`, `ATR_TARGET_MULT_NORMAL = 0.6`
- [ ] **STOP-01**: `ATR_STOP_MULT = 1.0`, `CAP_STOP_PCT = 0.03`
- [ ] **QUALITY-01**: `RELAX_SCORE = 90`
- [ ] **DEDUP-01**: `DUPLICATE_WINDOW_MINUTES = 480`
- [ ] **SENDS-01**: `MAX_INTRADAY_SENDS = 2`
- [ ] **MSG-01**: 알림 메시지 "예정일" → "청산 목표: 당일" 변경

### 4.3 미변경 항목

| 항목 | 유지 이유 |
|------|-----------|
| `MIN_TARGET_PCT = 0.05` | 이미 5% 설정 완료 |
| `MIN_DAILY_PICKS = 0` | 이미 강제 발송 비활성화 완료 |
| MACD/RSI 필터 | 직전 개선(swing-macd-rsi-risk-filter) 유지 |
| 거래량/RVOL 기준 | 현행 유지 |
| 리스크 블랙리스트 | 현행 유지 |
| `MIN_PRICE = 1000` | 현행 유지 |
| `MIN_INTRADAY_TURNOVER = 30억` | 현행 유지 |

---

## 5. 리스크 및 제약

| 리스크 | 내용 | 대응 |
|--------|------|------|
| 오전 알림 한정으로 추천 수 급감 | 11:30 이후 포착 종목 미발송 | 품질 향상 트레이드오프로 허용 |
| 목표가 7% 캡으로 강매 등급 목표 달성 불가 | 기존 ATR×2.8 대비 축소 | 당일 달성 가능성 우선, 7% 달성 시 이익 실현 |
| RELAX_SCORE 90으로 발송 0건인 날 증가 | 조건 충족 종목 없을 경우 | 의도된 설계 (없으면 보내지 않음) |
| 손절 3% 타이트로 노이즈 손절 가능성 | 장중 변동폭에 의해 손절가 터치 | RVOL 조건 강한 종목만 통과하므로 완화 |
| DUPLICATE_WINDOW 480분으로 당일 중복 가능성 | 오전 포착 종목이 오후 재포착될 수 있음 | STOP_NEW_ALERTS 11:30으로 오후 자동 차단 |

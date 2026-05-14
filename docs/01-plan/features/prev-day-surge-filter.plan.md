# prev-day-surge-filter Planning Document

> **Summary**: 전일 대비 급등 종목의 당일 진입을 억제해 과열 매수 손절 패턴을 제거
>
> **Project**: showmoneyv2 (Autostock Swing Scanner)
> **Author**: kevin
> **Date**: 2026-05-02
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 전일 대비 +8~16% 급등 상태에서 시초가 진입 후 장중 반전으로 -3% 손절 패턴이 반복됨. 4/27~30 분석 결과 SIMPAC(+9.3%), LS머트리얼즈(+16.4%), LS네트웍스(+9.8%) 모두 강매 등급이었지만 손절. |
| **Solution** | 전일대비 임계값 상수 추가 + 2단계 필터 (절대 상한 10% 초과 시 차단, 8% 이상 시 최소 점수 270점 요구). |
| **Function/UX Effect** | 과열 종목 진입 차단 → 손절 빈도 감소 → 승률 및 기대수익 향상. Telegram 발송 건수 소폭 감소 (품질 집중). |
| **Core Value** | 강매 등급이더라도 이미 과열된 종목은 추가 상승 여력이 부족하다는 원칙을 코드로 구현. |

---

## 1. Overview

### 1.1 Purpose

당일 스캔에서 강매 등급을 받은 종목이라도 **전일 종가 대비 이미 크게 상승한 상태** (시초가 기준 +8% 이상)에서는 진입을 억제한다. 이는 "좋은 신호지만 진입 타이밍이 나쁜" 케이스를 필터링하는 것이 목표다.

### 1.2 Background

**4/27~30 실증 분석 결과:**

| 종목 | 전일대비 | 점수 | 결과 |
|---|---|---|---|
| 상도어메니티 | +9.8% | 255점 | ✅ 수익 |
| LS네트웍스 | +9.8% | 250점 | ❌ 손절 |
| SIMPAC | +9.3% | 238점 | ❌ 손절 |
| LS머트리얼즈 | +16.4% | 230점 | ❌ 손절 |
| 글로벌텍스프리 | +6.6% | 255점 | ✅ 수익 (추정) |
| 씨아이이스 | +6.2% | 228점 | ✅ 수익 (추정) |

**패턴 분석:**
- 전일대비 +6~7%: 대체로 수익 (추가 상승 여력 존재)
- 전일대비 +9~10%: 혼재 (상도어메니티 수익 vs LS네트웍스·SIMPAC 손절)
- 전일대비 +15%+: 손실 확실 (LS머트리얼즈)

**손절 메커니즘:** 전일 급등 → 시초가 고점 → 차익 매물 쏟아짐 → 장중 -3% 손절가 도달. Regime 필터(강매 등급 필터)는 이 패턴을 차단할 수 없었음.

### 1.3 Related Documents

- 선행 작업: `docs/01-plan/features/trailing-stop-regime-fix.plan.md`
- 분석: `docs/03-analysis/trailing-stop-regime-fix.analysis.md`
- 시뮬레이션: `simulate_regime_apr27_30.js`

---

## 2. Scope

### 2.1 In Scope

- [x] **SURGE-01**: 전일대비 > 10% 시 진입 차단 (절대 상한)
- [x] **SURGE-02**: 전일대비 > 8% 시 최소 점수 270점 요구 (고품질 필터)
- [x] **SURGE-LOG-03**: 차단 사유 Telegram 로그 (월 1회 이상 발생 시)

### 2.2 Out of Scope

- 트레일링 스탑 실시간 구현 (별도 Feature)
- 전일대비 계산 로직 변경 (기존 데이터 활용)
- 장중 변동률 실시간 모니터링 (별도 검토 필요)
- 주간 리포터 소급 반영 (현재 진행 중인 실거래에만 적용)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | 근거 |
|----|-------------|----------|------|
| FR-01 | 전일대비 > 10%인 강매 신호 → 진입 차단 | High | LS머트리얼즈(+16.4%) 손절 방지 |
| FR-02 | 전일대비 8~10% 구간 + 점수 < 270 → 진입 차단 | High | LS네트웍스·SIMPAC 손절 방지 |
| FR-03 | 차단 조건 상수화 (하드코딩 금지) | Medium | 임계값 조정 용이성 |
| FR-04 | 차단 시 사유 포함 로그 (console/Telegram) | Low | 추후 튜닝 용이 |

### 3.2 Non-Functional Requirements

| Category | Criteria |
|----------|----------|
| 성능 | 기존 스캔 속도 영향 없음 (단순 조건 추가) |
| 호환성 | 기존 강매/급등/기타 등급 판정 로직 변경 없음 |
| 안전성 | 전일대비 계산 실패 시 → 차단하지 않고 통과 (보수적 fallback) |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `swing_scanner_code.js`에 2개 상수 추가 (SURGE-01, SURGE-02)
- [ ] 진입 차단 로직 2줄 추가 (D-2 위치: 기존 regime 차단 직후)
- [ ] 4/27~30 시뮬레이션 스크립트 재실행 시 LS머트리얼즈·SIMPAC 차단 확인

### 4.2 예상 효과 (4/27~30 기준)

| 적용 전 | 적용 후 (예상) |
|---|---|
| 8건 추천, 승률 43% (3승 5패) | 4~5건 추천, 승률 60~75% 예상 |
| LS머트리얼즈 +16.4% → 손절 | 차단 (진입 안 함) |
| SIMPAC +9.3% → 손절 | 차단 (점수 238 < 270) |
| LS네트웍스 +9.8% → 손절 | 차단 (점수 250 < 270) |
| 상도어메니티 +9.8% → 수익 | 차단 (점수 255 < 270) ← 1건 손실 |

> **트레이드오프:** 상도어메니티 수익 1건을 포기하는 대신 3건 손절 방지. 기대값 측면에서 명확히 유리.

---

## 5. 구현 명세

### 5.1 신규 상수 (C-2)

```javascript
// ===== 전일 급등 진입 억제 상수 (2026-05-02) =====
const MAX_ENTRY_SURGE_PCT   = 0.10;  // 전일대비 10% 초과 → 절대 차단
const SURGE_ZONE_PCT        = 0.08;  // 전일대비 8%+ 구간 시작
const SURGE_ZONE_MIN_SCORE  = 270;   // 급등 구간 최소 통과 점수
// ===== /전일 급등 진입 억제 상수 =====
```

### 5.2 전일대비 값 접근 방법

`swing_scanner_code.js` 스캔 루프 내부에서 `prevChangeRate`(또는 동등한 변수) 확인 필요.

현재 Telegram 메시지에 `(전일 대비 X.X%)` 표시 → 이미 계산된 값이 존재함.
→ Design 단계에서 해당 변수명 확인 후 재사용.

### 5.3 진입 차단 로직 (D-2) — Regime 차단 직후 삽입

```javascript
// [SURGE-FILTER] 전일 급등 종목 진입 억제 (2026-05-02)
const prevChange = (stock.prevChangeRate ?? 0); // 기존 계산값 재사용
if (prevChange > MAX_ENTRY_SURGE_PCT) return;   // 절대 상한: +10% 초과
if (prevChange > SURGE_ZONE_PCT && score < SURGE_ZONE_MIN_SCORE) return; // +8%+ 고점수 요구
```

---

## 6. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 상도어메니티 같은 고급등 후 추가 상승 케이스 차단 | Medium | Medium | 향후 백테스트로 임계값 재조정 (10%→12% 등) |
| 전일대비 변수명 불일치 | High | Low | Design 단계 코드 탐색으로 확정 |
| 너무 보수적 → 추천 건수 급감 | Medium | Low | SURGE_ZONE_PCT 를 0.10으로 상향 가능 |
| 갭상승 후 연속 강세 패턴 놓침 | Low | Low | 통계 축적 후 재평가 |

---

## 7. Architecture Considerations

- **Project Level**: Starter (단일 파일 수정, n8n 코드 노드)
- **수정 파일**: `swing_scanner_code.js` (상수 3개 + 조건 2줄)
- **영향 범위**: 당일단타 진입 필터 전용 (weekly reporter, healthcheck 무관)

---

## 8. Next Steps

1. [ ] `/pdca design prev-day-surge-filter` — 정확한 변수명 확인 + BEFORE/AFTER 코드 명세
2. [ ] `/pdca do prev-day-surge-filter` — `swing_scanner_code.js` 수정
3. [ ] 시뮬레이션 스크립트 재실행 → 차단 종목 확인
4. [ ] `/pdca analyze prev-day-surge-filter` — Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-02 | 4/27~30 실증 분석 기반 초안 | kevin |

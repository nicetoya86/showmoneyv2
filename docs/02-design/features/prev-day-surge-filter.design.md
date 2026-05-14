# prev-day-surge-filter Design Document

> **Summary**: 전일 급등 종목 진입 억제 — 상수 3개 추가 + 필터 2줄 삽입
>
> **Project**: showmoneyv2 (Autostock Swing Scanner)
> **Author**: kevin
> **Date**: 2026-05-02
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/prev-day-surge-filter.plan.md`

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 전일 급등(+9~16%) 종목이 강매 등급 통과 후 시초가 진입 → 차익매물로 장중 -3% 손절 반복. 4/27~30 기준 3건(SIMPAC·LS네트웍스·LS머트리얼즈) 해당 |
| **Solution** | `dailyChange` 기존 변수 재사용 + 상수 3개 + 필터 2줄(D-2). Regime 필터(D-1) 직후 삽입. 코드 변경 최소화 |
| **Function/UX Effect** | 4/27~30 기준 3건 손절 차단, 1건(상도어메니티) 수익 포기. 기대값 개선. Telegram 발송 건수 소폭 감소 |
| **Core Value** | 좋은 신호지만 타이밍이 나쁜 케이스를 코드로 명시적 제거 |

---

## 1. Architecture Overview

- **수정 파일**: `swing_scanner_code.js` (단일 파일)
- **수정 범위**: 상수 블록 C-2 (3줄) + 스캔 루프 내 D-2 필터 (3줄)
- **영향 없는 영역**: weekly reporter, healthcheck, grade 판정 로직, candidate 구조체

```
[Scan Loop per stock]
  → score, grade, dailyChange 계산 (line ~1163, ~1495)
  → D-1: Regime 필터 (line 1531–1532)  ← 기존
  → D-2: Surge 필터 (신규, line 1533–1535)  ← 여기 삽입
  → candidates.push() (line 1563)
```

---

## 2. Item Specifications

### C-2 — 신규 상수 3개

**위치**: `swing_scanner_code.js` line 26 직후 (REGIME 상수 블록 바로 다음)

**BEFORE** (line 22–26):
```javascript
// ===== Regime 임계값 상수 (2026-05-02 Option-3 개선) =====
const REGIME_YEST_DOWN = -0.015;
const REGIME_GAP_DOWN  = -0.007;
const REGIME_SMA_FAST  = 5;
// ===== /Regime 임계값 상수 =====
```

**AFTER**:
```javascript
// ===== Regime 임계값 상수 (2026-05-02 Option-3 개선) =====
const REGIME_YEST_DOWN = -0.015;
const REGIME_GAP_DOWN  = -0.007;
const REGIME_SMA_FAST  = 5;
// ===== /Regime 임계값 상수 =====
// ===== 전일 급등 진입 억제 상수 (2026-05-02) =====
const MAX_ENTRY_SURGE_PCT  = 0.10; // 전일대비 10% 초과 → 절대 차단
const SURGE_ZONE_PCT       = 0.08; // 전일대비 8% 이상 → 고점수 요구 구간 시작
const SURGE_ZONE_MIN_SCORE = 270;  // 급등 구간 최소 통과 점수
// ===== /전일 급등 진입 억제 상수 =====
```

| 상수 | 값 | 역할 |
|------|-----|------|
| `MAX_ENTRY_SURGE_PCT` | `0.10` | 전일대비 10% 초과 시 무조건 차단 |
| `SURGE_ZONE_PCT` | `0.08` | 전일대비 8% 이상이면 고품질 요구 구간 진입 |
| `SURGE_ZONE_MIN_SCORE` | `270` | 급등 구간에서 통과 허용되는 최소 점수 |

---

### D-2 — 진입 차단 필터

**위치**: line 1532 (D-1 마지막 줄) 직후 삽입

**변수 확인**:
- `dailyChange`: line 1163에서 계산 (`const dailyChange = prevClose > 0 ? (currentPrice / prevClose - 1) : 0;`)
- `score`: D-1 이전 이미 확정된 로컬 변수
- `dailyChange` 는 line 1566에서 `candidates.push({ ..., dailyChange, ... })` 로 전달됨
- D-2 삽입 지점은 candidates.push 이전이므로 로컬 변수 `dailyChange` 직접 사용

**BEFORE** (line 1530–1533):
```javascript
// [REGIME-FIX] 시장 단계별 진입 차단 (2026-05-02)
if (regimeLevel >= 2 && grade !== '강매') return; // 약세장: 강매(score≥120) 전용
if (regimeLevel >= 1 && grade === '매도차익') return; // 중립장: 매도차익 차단

const code = normalize(getCode(t));
```

**AFTER**:
```javascript
// [REGIME-FIX] 시장 단계별 진입 차단 (2026-05-02)
if (regimeLevel >= 2 && grade !== '강매') return; // 약세장: 강매(score≥120) 전용
if (regimeLevel >= 1 && grade === '매도차익') return; // 중립장: 매도차익 차단
// [SURGE-FILTER] 전일 급등 종목 진입 억제 (2026-05-02)
if (dailyChange > MAX_ENTRY_SURGE_PCT) return; // +10% 초과: 절대 차단
if (dailyChange > SURGE_ZONE_PCT && score < SURGE_ZONE_MIN_SCORE) return; // +8%+: 점수 270 미만 차단

const code = normalize(getCode(t));
```

**Fallback 동작**: `dailyChange`는 line 1163에서 `prevClose <= 0` 시 `0`으로 초기화됨 → 계산 실패 시 필터 미작동 (보수적 통과, FR-NFR-안전성 충족)

---

## 3. 4/27~30 검증 시나리오

D-2 적용 시 예상 결과:

| 종목 | 전일대비 | 점수 | D-2 판정 | 실제 결과 |
|------|---------|------|-----------|----------|
| 상도어메니티 | +9.8% | 255 | `> 8% && 255 < 270` → **차단** | ✅ 수익 (1건 포기) |
| LS네트웍스 | +9.8% | 250 | `> 8% && 250 < 270` → **차단** | ❌ 손절 방지 |
| SIMPAC | +9.3% | 238 | `> 8% && 238 < 270` → **차단** | ❌ 손절 방지 |
| LS머트리얼즈 | +16.4% | 230 | `> 10%` → **절대 차단** | ❌ 손절 방지 |
| 글로벌텍스프리 | +6.6% | 255 | `≤ 8%` → **통과** | ✅ 수익 유지 |
| 씨아이이스 | +6.2% | 228 | `≤ 8%` → **통과** | ✅ 수익 유지 |

**결과**: 손절 3건 차단, 수익 1건 포기 → 기대값 순개선

---

## 4. Non-Functional

| 항목 | 내용 |
|------|------|
| 성능 | 단순 산술 비교 2회 추가 — 실질 영향 없음 |
| 호환성 | `dailyChange` 기존 계산값 재사용. grade/score 로직 변경 없음 |
| 안전성 | `dailyChange = 0` fallback 이미 존재 (line 1163). 별도 방어 코드 불필요 |

---

## 5. Implementation Checklist

- [ ] **C-2**: `swing_scanner_code.js` line 26 직후 상수 블록 3줄 삽입
- [ ] **D-2**: line 1532 직후 필터 2줄 삽입
- [ ] 4/27~30 시나리오 수동 검증 (위 테이블 기준)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-02 | 초안 — 변수명 확인 후 BEFORE/AFTER 명세 완성 | kevin |

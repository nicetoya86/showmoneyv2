# Gap Analysis: swing-algorithm-improvement

## 분석 개요

| 항목 | 내용 |
|------|------|
| Feature | swing-algorithm-improvement |
| Plan 문서 | `docs/01-plan/features/swing-algorithm-improvement.plan.md` |
| Design 문서 | `docs/02-design/features/swing-algorithm-improvement.design.md` |
| 구현 파일 | `swing_scanner_code.js` |
| 분석 일자 | 2026-04-19 |
| 분석 기준 | Plan 섹션 5.1 (7개 항목) — Plan이 Design보다 우선 |

---

## 전체 결과

| 구분 | 결과 | 상태 |
|------|------|------|
| Plan vs 구현 일치율 | **100%** | PASS |
| **최종 Match Rate** | **100%** | **PASS** |

---

## Plan 섹션 5.1 항목별 검증 (7개 항목)

### 1. TARGET-01: ATR 목표 배수 분기

| 요건 (Plan) | 구현 (코드) | 상태 |
|-------------|------------|------|
| `ATR_TARGET_MULT_NORMAL = 2.0` 신규 상수 | Line 16: `const ATR_TARGET_MULT_NORMAL = 2.0;` | ✅ PASS |
| `ATR_TARGET_MULT = 2.8` 강매 전용 유지 | Line 15: 주석 "강매 등급 전용" | ✅ PASS |
| grade 분기: 강매→2.8x / 매도차익→1.5x / 급등·기타→2.0x | Lines 1233~1236: 3-way 분기 구현 | ✅ PASS |

```javascript
const targetMult = (grade === '강매')     ? ATR_TARGET_MULT        // 2.8
                 : (grade === '매도차익') ? ATR_TARGET_SHORT       // 1.5
                 : ATR_TARGET_MULT_NORMAL;                          // 2.0
```

---

### 2. HOLD-01a: HOLD_SURGE 2 → 3

| 요건 | 구현 | 상태 |
|------|------|------|
| 급등 보유기간 2 → 3거래일 | Line 55: `const HOLD_SURGE = 3;` (주석: "2026-04-18 개선: 2→3") | ✅ PASS |

---

### 3. HOLD-01b: HOLD_SHORTTRADE 2 → 3

| 요건 | 구현 | 상태 |
|------|------|------|
| 매도차익 보유기간 2 → 3거래일 | Line 42: `const HOLD_SHORTTRADE = 3;` (주석: "2026-04-18 개선: 2→3") | ✅ PASS |

---

### 4. OBV-01: 수급 필수 조건 추가

| 요건 | 구현 | 상태 |
|------|------|------|
| `hasSupply = (obvTrend===1) OR (rvolVal>=RVOL_GRADE_A)` | Line 1222: 정확히 구현 | ✅ PASS |
| `!hasSupply && grade !== '강매'` → 차단 | Line 1223: `if (!hasSupply && grade !== '강매') return;` | ✅ PASS |
| OBV 점수 보너스 (+20) 유지 | Lines 1157~1163: `score += 20` 유지 | ✅ PASS |

---

### 5. SCORE-01: 신고가 근접 점수 하향

| 요건 | 구현 | 상태 |
|------|------|------|
| pth ≥ 0.95: 25 → 15 | Line 1082: `score += 15;` (주석: "25→15") | ✅ PASS |
| pth ≥ 0.90: 15 → 8 | Line 1085: `score += 8;` (주석: "15→8") | ✅ PASS |
| 52주 신고가 돌파 (+40) 유지 | Line 1079: `score += NEW_HIGH52W_BONUS;` (=40) | ✅ PASS |

---

### 6. 요일 보정 — 기존 유지

| 요건 | 구현 | 상태 |
|------|------|------|
| 목요일 +3 | Line 1225: `DOW_BONUS_THU` (=3) | ✅ PASS |
| 수요일 +2 | Line 1226: `DOW_BONUS_WED` (=2) | ✅ PASS |
| 금요일 -5 | Line 1227: `-DOW_PENALTY_FRI` (=5) | ✅ PASS |
| rankScore 적용 | Line 1229: `const rankScore = score + dowAdj;` | ✅ PASS |

---

### 7. HOLD_STRONG=5 / SCORE_STRONG=120 — 기존 유지

| 요건 | 구현 | 상태 |
|------|------|------|
| HOLD_STRONG = 5 | Line 39: `const HOLD_STRONG = 5;` | ✅ PASS |
| SCORE_STRONG = 120 | Line 38: `const SCORE_STRONG = 120;` | ✅ PASS |

---

## Match Rate 계산

| 항목 | 서브항목 수 | PASS | FAIL |
|------|------------|------|------|
| TARGET-01 | 3 | 3 | 0 |
| HOLD-01a | 1 | 1 | 0 |
| HOLD-01b | 1 | 1 | 0 |
| OBV-01 | 3 | 3 | 0 |
| SCORE-01 | 3 | 3 | 0 |
| 요일 보정 | 4 | 4 | 0 |
| HOLD/SCORE_STRONG | 2 | 2 | 0 |
| **합계** | **17** | **17** | **0** |

**Match Rate: 17/17 = 100%**

---

## Design 문서 vs 구현 GAP 정보 (참고)

Design 문서는 4월 18일 Plan 업데이트 이전에 작성된 구버전으로, 다음 항목에서 현재 구현과 차이 있음.
단, Plan 문서가 우선이므로 이 항목들은 Code Defect가 아닌 **문서 부채(Documentation Debt)**임.

| # | Design 문서 | 현재 구현 | 비고 |
|---|-------------|-----------|------|
| 1 | ATR_TARGET_MULT = 2.8 유지 | ATR_TARGET_MULT_NORMAL = 2.0 추가 | Plan 우선 적용 |
| 2 | PMAT 기반 등급 판정 | PMAT 완전 제거됨 | HITALK 모델 제거 이후 |
| 3 | SCORE_STRONG = 100 | SCORE_STRONG = 120 | 코드가 먼저 업데이트됨 |
| 4 | OBV 필수 조건 없음 | hasSupply 필터 구현 | Plan 기반 신규 추가 |
| 5 | 신고가 근접 점수 원본 | 25→15, 15→8 하향 | Plan 기반 신규 추가 |
| 6 | 2단계 등급 (강매/매수) | 5단계 등급 시스템 | 코드가 진화 |

**권고:** Design 문서를 현재 구현 상태에 맞게 업데이트 (우선순위: 낮음)

---

## 미구현 항목

없음. 모든 Plan 요건 구현 완료.

---

## 결론

- **Match Rate: 100%** — Plan 요건 전항목 구현 완료
- 코드 변경 불필요
- 권장 다음 단계: `/pdca report swing-algorithm-improvement`

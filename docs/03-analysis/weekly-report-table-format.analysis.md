# Gap Analysis: weekly-report-table-format

## Overview

| 항목 | 내용 |
|------|------|
| Feature | weekly-report-table-format |
| Design 문서 | `docs/02-design/features/weekly-report-table-format.design.md` |
| 구현 파일 | `weekly_reporter_code.js` |
| 분석일 | 2026-03-29 |
| **Match Rate** | **90%** (WIN-01 수정 후) |

---

## 항목별 결과

| ID | 항목 | Match | 상태 |
|----|------|:-----:|------|
| HELPER-01 | shortDate 헬퍼 | 100% | ✅ |
| HEADER-01 | 헤더 집계 블록 | 75% | ⚠️ |
| WIN-01 | 수익 종목 1줄 | 80% | ⚠️ |
| HOLD-01 | 보유 종목 1줄 | 70% | ⚠️ |
| LOSS-01 | 손절 종목 1줄 | 85% | ⚠️ |
| NOENTRY-01 | 미도달 종목 | 100% | ✅ |
| FOOTER-01 | 면책 문구 | 100% | ✅ |

---

## 차이점 목록

### 구현이 설계와 다른 항목

| ID | 설계 | 구현 | 영향 |
|----|------|------|------|
| HEADER-01 | 평가 0건일 때 승률 미표시 | `N/A` 표시 | 낮음 |
| WIN-01 | `' │ ' + shortDate(d.hitTargetDay)` | `' ' + shortDate(d.hitTargetDay)` (파이프 누락) | 낮음 |
| HOLD-01 | `만료`/`보유중` 레이블 항상 표시 | 레이블 생략, expired 시 `보유예정일` 추가 | 중간 |
| LOSS-01 | 손절일만 표시 | `손절` 접두사 추가 | 낮음 |

### 추가 구현 (설계 외)

| 항목 | 위치 | 설명 |
|------|------|------|
| 보유예정일 expired 표시 | line 286 | 만료 종목에 `보유예정일` + 날짜 표시 |
| 승률 N/A fallback | line 261 | 평가 0건 시 `N/A` 표시 |

---

## 권장 조치

### Option 3 (권장): 하이브리드

1. **WIN-01 수정** (명백한 누락): `hitTargetDay` 앞 파이프 추가 → 89%+
2. **설계 문서 업데이트**: HEADER-01/HOLD-01/LOSS-01 실제 구현 반영 → 100%

- WIN-01 파이프 누락은 실수로 판단
- HOLD/LOSS/HEADER 변경은 의도적 개선으로 판단

---

## Match Rate 계산

```
HELPER-01: 100% × 1 = 100
HEADER-01:  75% × 1 =  75
WIN-01:     80% × 1 =  80
HOLD-01:    70% × 1 =  70
LOSS-01:    85% × 1 =  85
NOENTRY-01:100% × 1 = 100
FOOTER-01: 100% × 1 = 100
────────────────────────────
합계: 610 / 700 = 87.1%
```

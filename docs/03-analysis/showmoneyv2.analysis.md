# Design-Implementation Gap Analysis Report

**Feature:** showmoneyv2 — 30종목 복기 기반 스윙 스캐너 진입 신호 알고리즘 v1.0
**Plan:** `docs/01-plan/features/showmoneyv2.plan.md`
**Implementation:** `swing_scanner_code.js` / `cache/qa_Swing_Scanner.txt`
**Analysis Date:** 2026-06-03
**Match Rate:** 100%

---

## Executive Summary

| Item | Detail |
|------|--------|
| Feature | showmoneyv2 (30종목 복기 기반 진입 신호 v1.0) |
| Analysis Date | 2026-06-03 |
| Match Rate | **100%** (8/8 AC PASS) |
| AC Pass Rate | **8/8** |
| Status | ✅ 모든 계획 항목 구현 완료 |

QA Reference (`cache/qa_Swing_Scanner.txt`)와 production (`swing_scanner_code.js`)은 알고리즘 로직 전체 구간에서 byte-identical 확인.

---

## Acceptance Criteria 검증

| AC | 항목 | 결과 | 위치 |
|----|------|:----:|------|
| AC-1 | 4개 패턴(A/B/C/D) 독립 감지 | ✅ PASS | swing_scanner_code.js:1315-1344 |
| AC-2 | 기초 필터 5개(F1~F5) | ✅ PASS | :1286-1290 |
| AC-3 | score < 60 → return | ✅ PASS | :1399 |
| AC-4 | R:R < 1.5 → return | ✅ PASS | :1428 |
| AC-5 | patternType 필드 candidates에 포함 | ✅ PASS | :1446 |
| AC-6 | sentThisWeek 주간 중복 차단 | ✅ PASS | :1532-1535 |
| AC-7 | holdDays 패턴별 차등 | ✅ PASS | :1666-1672 |
| AC-8 | 복합 패턴(A+B)+15, (C+D)+10 | ✅ PASS | :1356-1357 |

---

## 상수 검증 (22개 전체 확인)

| 상수 그룹 | 검증 결과 |
|---------|:-------:|
| MIN_SCORE_FINAL=60, SCORE_STRONG_FINAL=110, MIN_RR_RATIO_FINAL=1.5 | ✅ |
| MIN_TURNOVER_ALGO=5_000_000_000 | ✅ |
| PA_*(3.0/0.05/1/10/0.15/0.03) | ✅ |
| PB_*(0.20/0.50/0.08) | ✅ |
| PC_*(5.0/0.05/0.50) | ✅ |
| PD_*(2.5/0.02/25) | ✅ |

---

## 스코어링 보너스 검증

| 항목 | Plan 정의 | 구현 | 검증 |
|------|---------|------|:---:|
| 거래량 8x+/5x/3x/2x | +25/+18/+12/+6 | 동일 | ✅ |
| OBV 수급↑ | +20 | 동일 | ✅ |
| 외국인+기관 동반 | +20 | 동일 | ✅ |
| 긍정공시 | +20 | 동일 | ✅ |
| 일봉정배열 | +15 | 동일 | ✅ |
| MACD 골든크로스 | +15 | 동일 | ✅ |
| ADX 추세↑ | +10 | 동일 | ✅ |
| RSI 골든존(50~70) | +8 | 동일 | ✅ |
| 장마감강세(≥70%) | +12 | 동일 | ✅ |
| 52주 신고가 | +25 | 동일 | ✅ |
| OBV수급↓ 패널티 | -8 | 동일 | ✅ |
| MACD 연속음수(비패턴C) | return | 동일 | ✅ |

---

## 목표가·손절가 검증

| 패턴 | Plan 정의 | 구현 | 검증 |
|------|---------|------|:---:|
| C 촉매 | target=max(10%,ATR×1.8), stop=max(4%,ATR×0.9) | 동일 | ✅ |
| A 눌림목 | target=max(눌림×1.3+3%,ATR×1.6,8%), stop=max(4%,ATR×0.9) | 동일 | ✅ |
| B 지지선 | target=max(조정×45%,10%,ATR×1.5), stop=max(5%,ATR×1.0) | 동일 | ✅ |
| D 박스 | target=max(10%,ATR×1.5), stop=max(4%,ATR×0.8) | 동일 | ✅ |
| 공통 캡 | target≤30%, stop≤8% | 동일 | ✅ |

---

## Plan 초과 구현 항목 (Gap 아님, 비충돌 개선)

| 타입 | 항목 | 비고 |
|------|------|------|
| 🟡 추가 | 외국인 단독+12 / 기관 단독+8 | Plan은 동반+20만 정의; 부분 점수 추가 |
| 🟡 추가 | 장마감양호+6 (강도≥50%) | Plan 기준(≥70%) 외 중간 단계 추가 |
| 🟡 추가 | 신고가근접+10 (pth≥0.95) | Plan 기준(신고가돌파+25) 외 근접 단계 추가 |
| 🟡 추가 | MACD↑ 중간 보너스+10 | Plan 골든크로스+15 외 MACD 상승 중 추가 |
| 🔵 참고 | 요일 보정(목+3/수+2/금-5) | rankScore 정렬에만 영향, 게이트 무관 |

→ 모두 Plan의 게이트·임계값과 충돌하지 않는 스코어 가산 개선

---

## 결론

구현이 Plan의 모든 Acceptance Criteria를 충족합니다.

**코드 변경 불필요.** Plan 문서 §3.2에 추가된 부분 점수 티어(외국인/기관 단독, 장마감양호, 신고가근접, MACD↑)와 §6 holdDays 등급 우선 로직을 반영하는 업데이트 권장 (선택사항).

**남은 미완료 항목 (코드 레벨 아님):**
1. n8n 워크플로우 JSON 업데이트 (배포)
2. QA 로그 실행 검증
3. 실전 1~2주 모니터링 후 파라미터 튜닝

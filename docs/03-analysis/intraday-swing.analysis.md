# Gap Analysis: intraday-swing

- **Feature**: intraday-swing (당일단타 전략)
- **Design**: `docs/02-design/features/intraday-swing.design.md`
- **Implementation**: `swing_scanner_code.js`
- **Date**: 2026-04-25
- **Analyst**: gap-detector agent

---

## Match Rate: 100% (14/14)

| 카테고리 | 점수 | 상태 |
|---------|:----:|:----:|
| Group A — 파라미터 변경 (9항목) | 9/9 | OK |
| Group B — 신규 데이터 시그널 (5항목) | 5/5 | OK |
| **합계** | **14/14** | **PASS** |

---

## 구현 확인 항목

### Group A — 전략 파라미터 전환 (9/9)

| ID | 설계 명세 | 구현 위치 | 결과 |
|----|----------|----------|:----:|
| A-1 | `STOP_NEW_ALERTS_HOUR=11`, `_MINUTE=30` | lines 22-23 | OK |
| A-2 | `HOLD_STRONG/NORMAL/WEAK/SHORTTRADE/SURGE = 1` | lines 39-55 | OK |
| A-3 | `CAP_TARGET_PCT = 0.07` | line 18 | OK |
| A-4 | `ATR_TARGET_MULT=0.8`, `ATR_TARGET_MULT_NORMAL=0.6` | lines 15-16 | OK |
| A-5 | `ATR_STOP_MULT=1.0`, `CAP_STOP_PCT=0.03` | lines 14, 17 | OK |
| A-6 | `RELAX_SCORE = 90` | line 7 | OK |
| A-7 | `DUPLICATE_WINDOW_MINUTES = 480` | line 21 | OK |
| A-8 | `MAX_INTRADAY_SENDS = 2` | line 19 | OK |
| A-9 | 알림 레이블 "[당일단타]", "청산 목표: 당일 장마감 전", "시초가 확인 후 진입" | lines 1597, 1600-1601 | OK |

### Group B — 신규 데이터 시그널 (5/5)

| ID | 설계 명세 | 구현 위치 | 결과 |
|----|----------|----------|:----:|
| B-1 | 갭 비율 계산 + 필터(-3%/+5%) + 점수 +10 | 필터: lines 1083-1085, 점수: lines 1367-1369 | OK |
| B-2 | 상한가 여유 계산 + <5% 차단 + 10~30% 구간 +15 | 필터: lines 1088-1090, 점수: lines 1373-1375 | OK |
| B-3 | KRX MDCSTAT02023 supplyMap + 외국인/기관 순매수 점수/차단 | 로딩: lines 464-489, 점수: lines 1378-1393 | OK |
| B-4 | KRX MDCSTAT05401 programNetBuy + pgmCaution + sizeFactor 반감 + 경고 | 로딩: lines 491-515, sizeFactor: lines 1442-1445, 경고: line 1595 | OK |
| B-5 | DART OpenAPI + 긍정/소형/부정 공시 필터링 | 로딩: lines 519-535, 점수: lines 1395-1409 | OK |

### 신규 상수 확인 (lines 70-87)

`DART_API_KEY`, `GAP_UP_MIN=0.01`, `GAP_UP_MAX=0.05`, `GAP_DOWN_BLOCK=-0.03`, `GAP_UP_SCORE=10`,
`LIMIT_ROOM_MIN=0.05`, `LIMIT_ROOM_LOW=0.10`, `LIMIT_ROOM_HIGH=0.30`, `LIMIT_ROOM_SCORE=15`,
`SUP_NETBUY_MIN=5e8`, `SUP_DUAL_SCORE=20`, `SUP_SINGLE_SCORE_FRGN=15`, `SUP_SINGLE_SCORE_ORG=10`,
`PGM_CAUTION_THRESHOLD=-5e11`, `DART_POSITIVE_SCORE=20`, `DART_MINOR_SCORE=5` — 전항목 일치

---

## 갭 항목

### Critical: 없음
### Minor: 없음

---

## 구현 참고사항 (갭 아님)

- B-4 pgmCaution 경고 문구가 설계 예시와 문자적으로 다름 (`"반절매 주의"` vs `"사이징 주의"`). 동일한 의미로 허용 범위.
- B-5 부정 공시 체크가 긍정 공시보다 먼저 실행됨. 설계 의도와 동일하게 동작 (부정이 항상 우선).
- B-3/B-4/B-5 캐시 키 변수를 `supCacheKey` 하나로 통합. DRY 원칙 적용, 기능 동일.

---

## 결론

**구현이 설계 명세를 완전히 충족합니다.**  
Check 단계 완료 (Match Rate 100%). `/pdca report intraday-swing` 실행을 권장합니다.

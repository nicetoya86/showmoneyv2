# Gap Analysis Report — showmoneyv2-fast-profit

- **분석일**: 2026-04-11
- **Plan**: `docs/01-plan/features/showmoneyv2-fast-profit.plan.md`
- **구현**: `swing_scanner_code.js`
- **Match Rate**: **100% (19/19)**

## 결과 요약

| 카테고리 | 항목 수 | 통과 |
|----------|---------|------|
| 발송 정책 변경 | 6 | 6 |
| 기존 개선 항목 | 5 | 5 |
| HIGH IMPACT 신규 | 5 | 5 |
| 회귀 테스트 | 3 | 3 |
| **합계** | **19** | **19** |

## 전체 항목 검증

| # | 항목 | 결과 | 근거 (라인) |
|---|------|------|------------|
| 1 | `매수` 등급 selected 미포함 | PASS | L1196: 조기 리턴 + L1317: FAST_GRADES 미포함 |
| 2 | filler 채움 제거 | PASS | L8: MIN_DAILY_PICKS=0, filler 로직 완전 제거 |
| 3 | 후보 0건 정상 종료 | PASS | selected=[] → send 루프 미실행 |
| 4 | MIN_TARGET_PCT=0.05 차단 | PASS | L26: 0.05, L1214: target 보장 |
| 5 | 강매 holdDays=5 | PASS | L38: HOLD_STRONG=5, L1405 |
| 6 | 급등 holdDays=2 | PASS | L54: HOLD_SURGE=2, L1406 |
| 7 | `[🚀급등]` 등급·알림 | PASS | L1186-1192: isSurge 판정, L1361: prefix |
| 8 | RSI 90 완화 (급등 후보) | PASS | L964: isSurgeCandidate, L970-971: RSI_SURGE_MAX |
| 9 | 52주신고가돌파 시그널 | PASS | L1055-1057: +40점 |
| 10 | 정배열 예외 (급등 후보) | PASS | L1003: !dailyUptrend && !isSurgeCandidate 조건 |
| 11 | 연속상승(N일) 시그널 | PASS | L1160-1169: +15점 |
| 12 | 수급집중(A) +20점 | PASS | L1076-1078 |
| 13 | 저점반등(100%+) +20점 | PASS | L1067-1070 |
| 14 | 장마감강세 +10점 | PASS | L1085-1087, rawOpen L931 |
| 15 | 섹터동반강세 rankScore+10 | PASS | L1298-1309 |
| 16 | openD fallback 처리 | PASS | L938: rawOpen[i]>0 ? rawOpen[i] : rawClose[i] |
| 17 | 강매/급등/매도차익 정상 발송 | PASS | L1317: FAST_GRADES Set |
| 18 | HIGH IMPACT 지표 0점 영향 없음 | PASS | 모두 if(조건) 형태 |
| 19 | 관심 등급 미발송 유지 | PASS | L1196 조기 리턴 |

## 추가 구현 (Plan 본문에 있으나 완료 조건 미기재)

- `수급집중(B)` (volTrend5_60 >= 2.0, +10점) — Plan §3.6에 명시
- `저점반등(30%+)` (+10점) — Plan §3.7에 명시

## 권고

**Act phase 불필요 — 바로 Report 단계 진행 권장**

# [Analysis] swing-nodup-fund-exclude

| Item | Detail |
|------|--------|
| Feature | swing-nodup-fund-exclude |
| Analysis Date | 2026-05-15 |
| Match Rate | **100%** (8/8) |
| Implementation File | `swing_scanner_code.txt` |

---

## Match Rate

```
┌──────────────────────────────────────────────┐
│  Match Rate: 100% (8/8 ACs)                  │
├──────────────────────────────────────────────┤
│  OK:           8 items                       │
│  Partial:      0 items                       │
│  Missing:      0 items                       │
└──────────────────────────────────────────────┘
```

---

## AC 검증 결과

| # | 기준 | 코드 위치 | 상태 | 비고 |
|---|------|-----------|:----:|------|
| AC-1 | `KRX_NAME` 맵 선언 + 우주 빌드 루프에서 `KRX_NAME[rc]` 저장 | line 716, 1008 | OK | `const KRX_NAME = {}` + `KRX_NAME[rc] = ...` |
| AC-2 | `isETF = isETFName(_stockName) \|\| isETFName(_krxName)` | line 1261 | OK | 두 이름 OR 조합 정확 |
| AC-3 | QI-1 필터에서 KRX 이름도 검사 | line 1002 | OK | `nm.includes(kw) \|\| krxRawNm.includes(kw)` |
| AC-4 | `swingSentToday` 초기화 + 14일 정리 | line 601-611 | OK | cutoffStr 공유, 정리 루프 존재 |
| AC-5 | 후보 스캔 루프 `swingSentToday` 체크 | line 1215-1217 | OK | `.KS/.KQ` 제거 후 `_rc`로 includes 체크 |
| AC-6 | send 직전 재확인 | line 1919 | OK | `selected[i].code` 기준 재확인 |
| AC-7 | send 성공 후 `swingSentToday` 즉시 기록 | line 1924-1925 | OK | `push(selected[i].code)` 즉시 실행 |
| AC-8 | `krxRawNm` 분리 저장 | line 985 | OK | KRX 원본 이름 선 추출 후 Naver 이름 fallback |

---

## 검증 상세

### 개선 1: KRX 원본 이름 분리 (ETF 필터 정확도)

- **line 716**: `const KRX_NAME = {}` — `NAME = {}` 옆에 선언, `[NODUP-1]` 태그 일치
- **line 985**: `krxRawNm`을 Naver 조회 이전에 `row.ISU_ABBRV || row.ISU_NM`에서 추출
- **line 1002**: `ETF_EXCLUDE_KEYWORDS` 필터가 `nm`(Naver) AND `krxRawNm`(KRX) 모두 검사
- **line 1008**: `KRX_NAME[rc]`에 `isGarbled` 가드 동일하게 적용
- **line 1261**: `isETFName(_stockName) || isETFName(_krxName)` — TIGER 구리삼물(160580)은 `_krxName="TIGER 구리삼물"` 경로로 `TIGER ∈ ETF_PROVIDERS` 매칭 → `true` 반환

### 개선 2: 당일 발송 Set (레이스 컨디션 방어)

- **line 601-611**: `swingSentToday` 초기화 → `cutoffStr` 기반 14일 정리 → `swingSentToday[today] = []`
- **line 1215-1217**: 배치 루프에서 `_rc`(suffix 제거) 기준 early return — Yahoo API 호출 이전 차단
- **line 1919**: send 루프 직전 `selected[i].code` 기준 재확인 — 최후 방어선
- **line 1922-1925**: 성공 후 `store.swingSent`(timestamp) + `store.swingSentToday`(code) 동시 기록

### 일관성 확인

- `swingSent` 키: ticker(`.KS/.KQ` suffix 포함) — timestamp 저장
- `swingSentToday` 키: raw code(suffix 없음) — 두 lookup 위치에서 일관되게 사용
- 14일 retention이 `weeklyRecommendations`와 동일한 `cutoffStr` 공유 → 정리 로직 일관성 확보

---

## 판정

**Match Rate 100% — 모든 AC 충족. `/pdca report` 진행 가능.**

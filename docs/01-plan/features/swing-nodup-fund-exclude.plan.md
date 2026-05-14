## Executive Summary

| Item | Detail |
|------|--------|
| Feature | swing-nodup-fund-exclude |
| Start Date | 2026-05-15 |
| Target Phase | Do |

| Perspective | Content |
|-------------|---------|
| Problem | Naver 이름 캐시가 ETF 제공사 접두사(TIGER 등)를 제거해 `isETFName()`이 ETF를 개별주로 오인 + 09:10·09:12 동시 실행 레이스 컨디션으로 같은 종목이 2분 간격으로 중복 발송 |
| Solution | KRX 원본 이름을 별도 저장하여 ETF 판별 정확도 향상 + 날짜 기반 당일 발송 Set(`swingSentToday`)으로 이중 검증 |
| UX Effect | 텔레그램 알림에 ETF/펀드가 사라지고 동일 종목 중복 알림 완전 소거 |
| Core Value | 스윙 추천 신뢰도 향상 + 알림 피로 제거 |

---

# [Plan] swing-nodup-fund-exclude

## 1. 개요

### 1.1 문제 정의

5월 14일 알림에서 두 가지 버그가 동시에 발생:

| 버그 | 증상 | 근본 원인 |
|------|------|-----------|
| ETF/펀드 추천 | TIGER 구리삼물(160580) 추천 | Naver 이름 캐시("구리삼물")가 ETF 제공사 접두사를 제거 → `isETFName()` false 반환 |
| 같은날 중복 추천 | 09:19, 09:21 동일 종목 2회 발송 | 09:10 트리거 + 09:12 워치독 동시 실행 레이스 컨디션 |

### 1.2 버그 추적

#### 버그 1: ETF/펀드 필터 우회

```
KRX 원본 이름: "TIGER 구리삼물"   → isETFName() → true  ✅
Naver 캐시 이름: "구리삼물"        → isETFName() → false ❌  ← 문제
```

**코드 경로 (`swing_scanner_code.txt`)**:
```
line 978:  nm = (store.naverNames && store.naverNames[rc]) || row.ISU_ABBRV  ← Naver 우선
line 999:  NAME[rc] = nm                                                       ← Naver 이름 저장
line 1246: _stockName = NAME[_tickerCode]                                      ← Naver 이름 사용
line 1248: isETF = isETFName(_stockName)                                       ← "구리삼물" 검사 → false
```

#### 버그 2: 같은날 중복 추천 (레이스 컨디션)

```
09:10  → Swing Scanner 시작 (이유 불명: lastRunDate 미설정 or 에러 조기 탈출)
09:12  → Watchdog 실행: lastRunDate !== today → 백업 스캔 시작
(두 실행이 동시 진행)
09:19  → 실행 A가 먼저 send() 완료 → store.swingSent[ticker] 저장
09:21  → 실행 B: 이미 candidates 루프 완료, send() 단계에서 swingSent 미확인 → 중복 발송
```

`store.swingSent[ticker]` 는 send 이후 line 1907에 저장되므로, 실행 B의 candidates 선발이 실행 A의 저장 전에 완료되면 중복 발생.

---

## 2. 개선 방향

### 개선 1: KRX 원본 이름 별도 저장 (ETF 필터 정확도 향상)

**목표**: `isETFName()` 검사 시 Naver 이름과 KRX 원본 이름을 모두 사용

**변경 위치**: `swing_scanner_code.txt` — 우주 빌드 루프 (line ~978, ~999)

**변경 전**:
```js
const nm = (store.naverNames && store.naverNames[rc]) || String(row.ISU_ABBRV || row.ISU_NM || '').trim();
// ...
NAME[rc] = isGarbled(nm) ? rc : nm;
```

**변경 후**:
```js
const nm = (store.naverNames && store.naverNames[rc]) || String(row.ISU_ABBRV || row.ISU_NM || '').trim();
const krxRawNm = String(row.ISU_ABBRV || row.ISU_NM || '').trim(); // [NODUP-1] KRX 원본 이름 별도 보존
// ...
NAME[rc] = isGarbled(nm) ? rc : nm;
KRX_NAME[rc] = isGarbled(krxRawNm) ? rc : krxRawNm;  // [NODUP-1] KRX 원본 이름 맵
```

**변경 위치**: ETF 분류 (line ~1245-1248)

**변경 전**:
```js
const _stockName = NAME[_tickerCode] || _tickerCode;
const isETF = isETFName(_stockName);
```

**변경 후**:
```js
const _stockName = NAME[_tickerCode] || _tickerCode;
const _krxName   = KRX_NAME[_tickerCode] || _stockName;  // [NODUP-1] KRX 원본 이름 활용
const isETF = isETFName(_stockName) || isETFName(_krxName); // [NODUP-1] 두 이름 모두 검사
```

**`KRX_NAME` 초기화 위치**: 스캐너 함수 최상단 변수 선언 영역:
```js
const KRX_NAME = {};   // [NODUP-1] 코드 → KRX 원본 이름 맵 (Naver 캐시 오염 방지)
```

---

### 개선 2: 당일 발송 Set으로 이중 검증 (중복 추천 방지)

**목표**: 날짜 기반 `swingSentToday[today]` Set으로 레이스 컨디션과 무관하게 당일 중복 차단

**변경 전 흐름**:
```
실행 A: [선발] → [send()] → [swingSent[ticker] 저장]
실행 B: [선발] ← swingSent 미저장 상태 통과 → [send()] ← 중복 발송!
```

**변경 후 흐름**:
```
실행 A: [선발] → [send 직전 swingSentToday 재확인] → [send()] → [swingSentToday 즉시 기록]
실행 B: [선발] → [send 직전 swingSentToday 재확인] → today에 이미 있으면 skip!
```

**변경 위치**: store 초기화 영역 (line ~599 이후):
```js
// [NODUP-2] 당일 발송 Set — 날짜 기반 완전 차단 (레이스 컨디션 방어)
if (!store.swingSentToday) store.swingSentToday = {};
// 14일 이상 지난 날짜 항목 정리
for (const d in store.swingSentToday) {
  if (d < cutoffStr) delete store.swingSentToday[d];
}
if (!store.swingSentToday[today]) store.swingSentToday[today] = [];
```

**변경 위치**: 후보 스캔 루프 (line ~1204-1205):
```js
if (store.swingSent[t]) return;
// [NODUP-2] 당일 발송 Set 추가 체크
if (store.swingSentToday[today] && store.swingSentToday[today].includes(rc)) return;
```

**변경 위치**: 최종 send 루프 (line ~1903-1910):
```js
for (let i = 0; i < selected.length; i++) {
  // [NODUP-2] send 직전 재확인 — 동시 실행 레이스 컨디션 최후 방어
  if (store.swingSentToday[today] && store.swingSentToday[today].includes(selected[i].code)) {
    continue;
  }
  const res = await send(selected[i]);
  if (res) {
    store.swingSent[selected[i].ticker] = now.getTime();
    // [NODUP-2] 당일 발송 Set에 즉시 기록
    if (!store.swingSentToday[today]) store.swingSentToday[today] = [];
    store.swingSentToday[today].push(selected[i].code);
    // ... 기존 weeklyRecommendations 기록 유지
  }
}
```

---

## 3. 구현 범위

### 수정 위치 요약

| 파일 | 위치 | 변경 내용 |
|------|------|-----------|
| `swing_scanner_code.txt` | 변수 선언 최상단 | `const KRX_NAME = {}` 추가 |
| `swing_scanner_code.txt` | store 초기화 영역 | `swingSentToday` 초기화 + 14일 정리 |
| `swing_scanner_code.txt` | 우주 빌드 루프 (line ~978) | `krxRawNm` 분리 저장 |
| `swing_scanner_code.txt` | 우주 빌드 루프 (line ~999) | `KRX_NAME[rc] = krxRawNm` 추가 |
| `swing_scanner_code.txt` | ETF 분류 (line ~1245-1248) | `_krxName` 추출 + `isETF` OR 조합 |
| `swing_scanner_code.txt` | 후보 스캔 루프 (line ~1204) | `swingSentToday` 체크 추가 |
| `swing_scanner_code.txt` | send 루프 (line ~1903) | send 직전 재확인 + 발송 후 즉시 기록 |
| `autostock_showmoneyv2_YYYYMMDD_HHMMSS_nodup_fund_exclude.json` | Swing Scanner 노드 | 수정 코드 반영 |

### 수정하지 않는 것

| 항목 | 이유 |
|------|------|
| `isETFName()` 함수 시그니처 | 호출 방식만 변경, 함수 자체는 유지 |
| `store.swingSent` 타임스탬프 방식 | 기존 8시간 창은 동일 실행 내 dedup용으로 유지 |
| `ETF_EXCLUDE_KEYWORDS` / `ETF_PROVIDERS` | 그대로 활용 |
| `MAX_STOCK_PER_SEND = 2` | 유지 |
| Scalping Scanner | 이 플랜 범위 밖 (별도 검토) |

---

## 4. 구현 순서

1. `KRX_NAME = {}` 상단 선언 추가
2. store 초기화: `swingSentToday` 초기화 + 정리 로직
3. 우주 빌드 루프: `krxRawNm` 분리 + `KRX_NAME[rc]` 저장
4. ETF 분류: `_krxName` + `isETFName()` OR 조합
5. 후보 스캔 루프: `swingSentToday` 체크 추가
6. send 루프: 재확인 + 즉시 기록
7. `swing_scanner_code.txt` 업데이트
8. n8n 워크플로우 JSON 생성 (Swing Scanner 노드 코드 반영)

---

## 5. 수용 기준 (Acceptance Criteria)

| # | 기준 | 검증 방법 |
|---|------|-----------|
| AC-1 | `KRX_NAME` 맵이 선언되고 우주 빌드 루프에서 채워짐 | 코드 리뷰 |
| AC-2 | `isETF = isETFName(_stockName) \|\| isETFName(_krxName)` 로 두 이름 검사 | 코드 리뷰 |
| AC-3 | TIGER 구리삼물(160580)이 KRX 이름으로 ETF 감지되어 `stockCandidates` 제외 | 코드 리뷰 |
| AC-4 | `store.swingSentToday[today]` 초기화가 store 초기화 시점에 존재 | 코드 리뷰 |
| AC-5 | 후보 스캔 루프에서 `swingSentToday` 체크 추가 | 코드 리뷰 |
| AC-6 | send 루프: 발송 직전 재확인 + 발송 성공 시 `swingSentToday` 즉시 기록 | 코드 리뷰 |
| AC-7 | 기존 `store.swingSent` 타임스탬프 dedup 로직 유지 | 코드 리뷰 |
| AC-8 | n8n 워크플로우 JSON에 수정 코드 반영 완료 | 파일 확인 |

## Executive Summary

| Item | Detail |
|------|--------|
| Feature | krx-healthcheck-fix |
| Start Date | 2026-05-11 |
| Target Phase | Do (완료) |

| Perspective | Content |
|-------------|---------|
| Problem | 배포된 Daily Healthcheck 노드가 KRX API를 live로 호출(09:00 KST)하여 HTTP 400 에러 반복 발생. ORIGINAL 파일에는 이미 비활성화되어 있었으나 n8n에 미반영 |
| Solution | Daily Healthcheck 노드를 ORIGINAL 버전으로 교체하여 live KRX 호출 제거, `krxUniverseCache` 캐시 조회 방식으로 대체 |
| UX Effect | 매일 09:00 헬스체크 알림에서 "KRX: 에러: Request failed with status code 400" 메시지 제거 → "KRX: 캐시 OK (N개)" 정상 메시지 표시 |
| Core Value | 불필요한 에러 알림 제거로 운영 신뢰도 향상, KRX 장애 시에도 헬스체크 안정 동작 |

---

# [Plan] krx-healthcheck-fix

## 1. 개요

### 1.1 문제 정의

2026-05-11(월) 09:00 KST 헬스체크 알림에서 아래 에러 확인:

```
✅ [헬스체크] Autostock 스케줄러 정상
- KST: 2026-05-11 09:00
- KRX: 에러: Request failed with status code 400
```

| 구분 | 내용 |
|------|------|
| 에러 | HTTP 400 from `https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd` |
| 발생 시각 | 매일 09:00 KST (Daily Healthcheck 트리거) |
| 발생 주기 | 반복 (매 평일) |

### 1.2 근본 원인

**배포된 헬스체크 코드 vs ORIGINAL 파일 불일치:**

| 구분 | 배포된 코드 (5,678자) | ORIGINAL 파일 (3,340자) |
|------|----------------------|------------------------|
| KRX 처리 | Live POST 호출 (`data.krx.co.kr`) | 캐시 조회만 (`krxUniverseCache`) |
| 에러 발생 | 09:00 KST → KRX 준비 안 된 시점 → 400 | 없음 |
| 서킷 브레이커 | 자체 포함 (`hcKrx.circuitUntil`) | 불필요 (live 호출 없음) |

`Daily_Healthcheck_ORIGINAL.js`에는 이미 아래 주석이 있음:
```js
// (KRX live probe disabled) - KRX 차단/불안정 시 400을 유발할 수 있어 live 호출을 하지 않습니다.
// 대신, 오늘자 KRX 유니버스 캐시/서킷 상태만 보고합니다.
```

즉, 이전에 동일한 이슈를 인지하고 ORIGINAL 파일을 수정했으나 n8n 워크플로우에 반영되지 않은 상태로 방치됨.

### 1.3 추가 관찰 사항

**스윙 09:10 트리거 누락** (동일 날짜):
- 증상: 스윙 백업 알림 "09:10 트리거 누락 감지" → 09:12에 백업 실행
- 원인: n8n 스케줄러 간헐적 지연 (KRX 에러와 무관)
- 헬스체크 circuit breaker는 `store.healthcheck.krx`를 사용하며, 스윙 스캐너의 `store.krxState`와 완전히 분리됨
- 코드 수정 불필요 — 백업 메커니즘이 정상 작동함

---

## 2. 수정 범위

### 수정 파일

| 파일 | 수정 내용 |
|------|-----------|
| n8n `Daily Healthcheck` 노드 | ORIGINAL 코드로 교체 (live KRX 호출 제거) |
| `autostock_showmoneyv2_20260511_234525_krx_healthcheck_fix.json` | 수정 반영된 신규 워크플로우 파일 |

### 변경 내역 상세

**제거된 코드 (배포 버전에만 존재):**
```js
// ===== autofix_krx_stabilize_v1 =====
// KRX 장애를 "기록 + 폴백 + 스팸 없는 경고"로 흡수하기 위한 공통 유틸
if (!store.healthcheck.krx) store.healthcheck.krx = {};
...
const r = await http({
  method: 'POST',
  url: 'https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd',
  ...
});
```

**적용된 코드 (ORIGINAL):**
```js
// (KRX live probe disabled)
const cache = store && store.krxUniverseCache;
if (circuitActive) {
  krxStatus = `서킷 활성(circuitUntil=${st.circuitUntil})`;
} else if (cache && cache.trdDd === trdDd && ...) {
  krxStatus = `캐시 OK (${krxCount}개)`;
} else {
  krxStatus = '캐시 없음 (live probe 비활성)';
}
```

---

## 3. 구현 순서 (완료)

1. ✅ **원인 분석** — 배포 코드 vs ORIGINAL 파일 비교
2. ✅ **수정 파일 생성** — Python 스크립트로 `functionCode` 교체
3. ✅ **검증** — live KRX 호출 제거, 캐시 조회 로직 확인
4. ⬜ **n8n Import** — `autostock_showmoneyv2_20260511_234525_krx_healthcheck_fix.json` 임포트

---

## 4. 수용 기준 (Acceptance Criteria)

| # | 기준 | 검증 방법 |
|---|------|-----------|
| AC-1 | 배포된 헬스체크 노드에 `data.krx.co.kr` 호출 없음 | 코드 검사 (완료) |
| AC-2 | `krxUniverseCache` 조회 로직 정상 포함 | 코드 검사 (완료) |
| AC-3 | 내일 09:00 헬스체크 알림에 KRX 400 에러 미발생 | 실제 실행 결과 |
| AC-4 | 스윙 스캐너 동작에 영향 없음 | 코드 격리 확인 (완료) |

---

## 5. 비고

- `Daily_Healthcheck_ORIGINAL.js` 파일이 항상 n8n 배포 기준 파일이어야 함
- 향후 헬스체크 수정 시 반드시 ORIGINAL 파일을 먼저 수정 후 워크플로우 JSON 갱신 절차 준수
- 스윙 트리거 누락은 n8n 인프라 레벨 간헐적 이슈이므로 현재의 백업 메커니즘(09:12 실행)으로 대응 유지

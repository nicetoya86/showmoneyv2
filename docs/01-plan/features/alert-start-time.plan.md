# Plan: alert-start-time

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 코드 422번 라인에 `m < 30` 하드코딩으로 09:30 이전 실행을 무조건 스킵. n8n을 09:00으로 앞당겨도 알림이 발송되지 않음. |
| **Solution** | `ALERT_START_MINUTE` 상수 도입 → 09:00 허용으로 변경. 전일 일봉 데이터는 09:00에 이미 준비 완료 (KRX T+1 + Naver 전일 종가). |
| **Function UX Effect** | 시초가 직후 (09:00~09:05) 알림 수신 → 당일단타 최적 진입 타이밍 확보. 현재 09:30 알림은 30분 가격 움직임 놓침. |
| **Core Value** | 당일단타 전략의 실효성 향상 — 시초가 체결 직후 진입 가능 구간에서 알림 제공. |

---

## 배경

### 현재 문제

`swing_scanner_code.js` line 421-422:
```js
if (h < 9) return [...]; // 09:00 이전 차단
if (h === 9 && m < 30) return [{ skipped: true, reason: 'Too early - daily data not ready before 09:30' }];
```

- `m < 30` 하드코딩으로 **09:00~09:29 사이 항상 스킵**
- n8n 트리거를 09:00으로 변경해도 무의미
- 전일단타 전략인데 30분 지난 후 알림 수신 → 진입 타이밍 불리

### 데이터 준비 현황 (09:00 기준)

| 데이터 | 준비 시점 | 09:00 사용 가능 |
|--------|---------|:----------:|
| Naver 전일 종가 (일봉) | 전일 15:30 이후 | ✅ |
| KRX 외국인/기관 순매수 (T+1) | 당일 08:00~08:30 | ✅ |
| KRX 프로그램 매매 (T+1) | 당일 08:00~08:30 | ✅ |
| DART 공시 | 실시간 | ✅ |
| 오늘 시초가 | 09:00 체결 시작 | ✅ (09:01부터) |

→ "daily data not ready before 09:30" 주석은 과도하게 보수적. **전일 데이터 기반 분석은 09:00에도 완전히 준비됨.**

---

## 변경 계획

### 코드 변경 (swing_scanner_code.js)

**1. 상수 추가**
```js
const ALERT_START_HOUR   = 9;  // 알림 허용 시작: 09:00 KST
const ALERT_START_MINUTE = 0;  // 09:00부터 스캔 허용
```

**2. 시간 체크 로직 수정 (line 422)**

Before:
```js
if (h === 9 && m < 30) return [{ json: { skipped: true, reason: 'Too early - daily data not ready before 09:30' } }];
```

After:
```js
if (h < ALERT_START_HOUR || (h === ALERT_START_HOUR && m < ALERT_START_MINUTE)) {
  return [{ json: { skipped: true, reason: 'Before alert start time' } }];
}
```

### n8n 워크플로우 변경

- 현재 트리거: 09:30 (또는 다른 시간) → **09:00~09:05 KST**로 변경
- n8n Cron 설정: `0 9 * * 1-5` (매주 월~금 09:00 UTC+9)
- 또는 interval 트리거로 09:00~11:30 사이 매 X분 실행 유지

---

## 리스크 및 고려사항

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 09:00~09:05 시초가 미체결 종목 | 호가 형성 전 진입 시도 | 메시지에 "09:00~09:10 시초가 체결 확인 후 진입" 안내 추가 |
| KRX T+1 데이터 지연 (08:30 이전) | supplyMap 빈 데이터 | 기존 캐시 fallback 로직 유지 (정상 동작) |
| n8n 트리거 시간 미변경 시 | 코드만 바뀌고 효과 없음 | plan에 n8n 설정 변경 명시 |

---

## 구현 순서

1. `swing_scanner_code.js` 상수 2개 추가 (`ALERT_START_HOUR`, `ALERT_START_MINUTE`)
2. 하드코딩 `m < 30` → 상수 기반 체크로 교체
3. 알림 메시지 매수 안내 문구 업데이트: "시초가 확인 후 진입" → "09:00~09:10 시초가 체결 확인 후 진입"
4. n8n 워크플로우 트리거 시간 09:00 KST로 변경 (별도 n8n 설정)

---

## 예상 효과

- 알림 수신 시점: 09:30 → **09:00~09:05**
- 당일단타 유효 진입 시간: 30분 연장
- 시초가 체결 직후 알림으로 당일 변동성 최대 구간 활용 가능

# Plan: trailing-stop-regime-fix

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | trailing-stop-regime-fix |
| 분석 기반 | 2026-04-27 ~ 05-01 주간 리포트 (손절 5건, 수익 3건) |
| 핵심 문제 ① | LS네트웍스 +16.4% 고점 후 당일 손절 → 트레일링 스탑 부재로 수익 소멸 |
| 핵심 문제 ② | Market Regime 필터가 sizeFactor만 줄일 뿐 진입 자체를 차단하지 않음 |
| 작성일 | 2026-05-02 |

### Value Delivered (4-Perspective)

| 관점 | 내용 |
|------|------|
| **Problem** | 당일단타 모델에서 장중 +16.4%까지 오른 종목이 급반전 후 손절로 기록됨. Market Regime riskOn=false 상태에서도 약체 종목(230~238점) 진입이 차단되지 않아 04-30 동시 손절 2건 발생 |
| **Solution** | ① 주간 리포터에 당일 트레일링 스탑 시뮬레이션 추가(성과 재분류) ② Market Regime riskOn=false 시 점수 기준 상향(진입 품질 강화) ③ 04-30 Regime 상태 사후 검증 |
| **Function UX Effect** | 주간 리포트에서 "수익 구간 도달 후 손절" 종목이 이익 청산으로 재분류됨. riskOn=false 일에는 더 엄격한 기준으로 종목 수 감소 |
| **Core Value** | 진입 신호보다 **출구 전략**이 당일단타 성과에 더 큰 영향. 장중 수익을 잠그는 구조 구축 |

---

## 1. 이번 주 성과 분석 (2026-04-27 ~ 05-01)

### 1.1 손절 5건 세부 분류

**Type A — 수익 구간 도달 후 당일 급반전 손절 (핵심 문제)**

| 종목 | 진입일 | 최고 수익률 | 결과 | 점수 |
|------|--------|-----------|------|------|
| LS네트웍스(000680) | 04-28 | **+16.4%** | 손절 04-28 | 250점 |
| 도이치모터스(067990) | 04-28 | **+6.5%** | 손절 04-28 | 253점 |

> LS네트웍스는 목표가 상한(`CAP_TARGET_PCT=0.07`, +7%)을 초과해 +16.4%까지 상승했다가 급반전.
> 도이치모터스는 목표 +7% 직전에서 반전. 두 경우 모두 **트레일링 스탑 없이 원래 손절가에 걸림**.

**Type B — 04-30 동시 진입 즉시 손절 (Regime 문제)**

| 종목 | 진입일 | 최고 수익률 | 결과 | 점수 |
|------|--------|-----------|------|------|
| SIMPAC(009160) | 04-30 | 데이터 없음 | 손절 04-30 | 238점 |
| LS머트리얼즈(417200) | 04-30 | +1.1% | 손절 04-30 | 230점 |

> 04-30에 진입한 2종목 모두 당일 즉시 손절. 점수 230~238점은 알고리즘상 강매 등급 기준(120점) 대비
> 충분히 높지만, **시장 환경이 불량한 날 진입 자체가 문제**.

**Type C — 보유 후 손절 (소익 후 반전)**

| 종목 | 진입일 | 최고 수익률 | 결과 | 점수 |
|------|--------|-----------|------|------|
| SOL반도체후공정(475310) | 04-27 | +3.7% | 보유→손절 처리 | 235점 |

---

## 2. 근본 원인 분석

### 2.1 문제 ①: 당일단타 트레일링 스탑 부재

**현재 코드 구조 (swing_scanner_code.js):**

```javascript
// 손절가: ATR × 1.0, 최대 -3% 캡 (고정)
const ATR_STOP_MULT = 1.0;
const CAP_STOP_PCT = 0.03;

let stop = currentPrice - atrAbs * ATR_STOP_MULT;
const stopCap = currentPrice * (1 - CAP_STOP_PCT);
stop = Math.max(stop, stopCap);  // 진입 시점에 고정 → 이후 불변
```

**문제 시나리오 (LS네트웍스):**
```
진입가: X
장중 최고 +16.4%: X × 1.164
급반전: X × 1.164 → X × 0.97 (손절가 도달)
결과: "손절" 기록

트레일링 스탑이 있었다면:
  +5% 도달 → 손절가: 진입가 × 1.00 (브레이크이븐)
  +10% 도달 → 손절가: 최고가 × 0.95
  +16.4% 후 급락 → 손절가 ~X × 1.12 에서 청산
  결과: "+12% 이익 실현" 기록
```

**구조적 문제:** 스캐너는 09:00~11:30에만 실행되고, 진입 후 장중 추적 로직이 없음.
그러나 **주간 리포터는 사후에 일별 OHLC 데이터로 성과를 평가**하므로
트레일링 스탑 시뮬레이션을 소급 적용할 수 있음.

---

### 2.2 문제 ②: Market Regime 필터 — 진입 차단 없음

**현재 코드 구조 (swing_scanner_code.js, line ~1443~1449):**

```javascript
const rg = await getMarketRegime(store, today);
const riskOn = !!(rg && rg.riskOn);

// riskOn=false여도 진입 차단 없음! sizeFactor만 감소
const sizeFactor = riskOn
  ? (pgmCaution ? 0.5  : 1.0)
  : (pgmCaution ? 0.25 : 0.5);   // riskOn=false → 수량만 절반

const qty = calcQty(ACCOUNT_KRW, RISK_PCT_PER_TRADE * sizeFactor, currentPrice, stop);
```

**getMarketRegime 판단 로직 (line ~360~379):**

```javascript
// KOSPI SMA20 > SMA60 AND KOSDAQ SMA20 > SMA60 → riskOn=true
// 둘 중 하나라도 SMA20 < SMA60 → riskOn=false
if (ks === false || kq === false) riskOn = false;
```

**04-30 Regime 분석:**
- 2026-04-02 미국 관세 쇼크(Liberation Day)로 KOSPI 급락
- 2026-04-30까지 약 4주 회복기
- 이 기간 KOSPI SMA20(20일 이평)는 빠르게 회복되지만
  SMA60(60일 이평)은 이전 고점을 반영해 더 높을 가능성 큼
- **결론: 04-30에 riskOn=false 상태였을 가능성 높음**

**그러나 riskOn=false여도:**
- SIMPAC(238점), LS머트리얼즈(230점) 진입은 차단되지 않음
- 수량만 절반으로 줄었을 뿐 — 손절 자체는 동일하게 발생

---

## 3. 개선안 설계

### 3.1 개선 모듈 요약

| ID | 모듈 | 대상 파일 | 우선순위 | 기대 효과 |
|----|------|---------|---------|---------|
| TRAIL-01 | 주간 리포터 트레일링 스탑 시뮬레이션 | `weekly_reporter_code.js` | **최고** | LS네트웍스 → 손절→이익 재분류 |
| REGIME-FIX | riskOn=false 시 점수 커트라인 상향 | `swing_scanner_code.js` | **높음** | 04-30 약체 종목 진입 차단 |
| REGIME-LOG | Regime 상태 Telegram 디버그 알림 | `swing_scanner_code.js` | **중간** | 04-30 사후 검증 / 향후 감사 |

---

### 3.2 TRAIL-01 — 주간 리포터 트레일링 스탑 시뮬레이션

**대상 파일:** `weekly_reporter_code.js`

**변경 로직:**

```javascript
// 현재: 고정 손절가로만 평가
// if (day.low <= r.stop) → hitStopDay → 'loss'

// 개선: 당일단타 트레일링 스탑 시뮬레이션
const simulateTrailingStop = (r, dayData) => {
  // dayData = { open, high, low, close } (진입일 당일 데이터)
  let trailingStop = r.stop;   // 초기 = 원래 손절가
  const entry = r.entry;
  const atrAbs = r.atrAbs;     // 진입 시 저장된 ATR 값

  const maxHigh = dayData.high;   // 당일 최고가
  const gain = (maxHigh - entry) / entry;

  // 당일단타 트레일링 스탑 단계별 상향
  if (gain >= 0.15 && atrAbs) {
    trailingStop = Math.max(trailingStop, maxHigh - atrAbs * 0.5); // +15%: 고점-ATR×0.5
  } else if (gain >= 0.10 && atrAbs) {
    trailingStop = Math.max(trailingStop, maxHigh - atrAbs * 0.7); // +10%: 고점-ATR×0.7
  } else if (gain >= 0.05 && atrAbs) {
    trailingStop = Math.max(trailingStop, maxHigh - atrAbs * 1.0); // +5%: 고점-ATR×1.0
  } else if (gain >= 0.03) {
    trailingStop = Math.max(trailingStop, entry);                   // +3%: 브레이크이븐
  }

  // 트레일링 스탑에서 청산됐는지 체크
  if (dayData.low <= trailingStop) {
    return { hitStop: true, exitPrice: trailingStop, isTrailing: true };
  }
  return { hitStop: false };
};
```

**기대 결과:**

| 종목 | 현재 판정 | 개선 후 판정 |
|------|---------|------------|
| LS네트웍스(+16.4%) | 손절(-3%) | **이익 청산(+약 12%)** |
| 도이치모터스(+6.5%) | 손절(-3%) | **이익 청산(+약 3%)** |
| SOL반도체후공정(+3.7%) | 보유→손절 | **브레이크이븐 또는 소이익** |

> **전제 조건:** `weeklyRecommendations`에 `atrAbs` 값이 저장되어 있어야 함.
> 현재 `swing_scanner_code.js`의 `candidates.push()`에 `atrAbs`가 포함되어 있음 (line 1460 확인).
> `store.weeklyRecommendations[today]`에도 atrAbs가 실제로 저장되는지 검증 필요.

---

### 3.3 REGIME-FIX — riskOn=false 시 점수 커트라인 상향

**대상 파일:** `swing_scanner_code.js`

**신규 상수 추가:**

```javascript
const REGIME_OFF_SCORE_BOOST = 20;  // riskOn=false 시 최소 점수 상향치
```

**적용 위치 (후보 필터 직전):**

```javascript
// riskOn=false 시 기준 강화 — 약세장 진입 품질 향상 (REGIME-FIX)
const minScoreForEntry = riskOn ? 0 : REGIME_OFF_SCORE_BOOST;
// candidates.push 전에:
if (score < RELAX_SCORE + minScoreForEntry) return; // REGIME-FIX: 약세장 추가 점수 요구
```

**효과 시뮬레이션 (04-30 기준):**

| 종목 | 점수 | riskOn=false 기준(90+20=110) | 진입 |
|------|------|---------------------------|------|
| SIMPAC | 238점 | 238 >= 110 ✅ | 통과 |
| LS머트리얼즈 | 230점 | 230 >= 110 ✅ | 통과 |

> **결론:** REGIME_OFF_SCORE_BOOST=20으로는 04-30 종목 차단 불가.
> 더 강한 기준이 필요하다면 `REGIME_OFF_SCORE_BOOST = 40~50` 검토.
> 또는 riskOn=false 시 **강매(120점) 등급만 허용**하는 방식도 가능.

**강매 전용 옵션:**

```javascript
// riskOn=false 시 강매 등급(score>=SCORE_STRONG)만 허용
if (!riskOn && !isStrong) return;  // REGIME-FIX-STRICT: 약세장 강매 전용
```

---

### 3.4 REGIME-LOG — Regime 상태 디버그 알림

**목적:** 04-30처럼 사후 검증이 필요할 때, Regime 상태를 로그로 남겨 추적 가능하게 함.

**적용 위치 (getMarketRegime 호출 직후):**

```javascript
const rg = await getMarketRegime(store, today);
const riskOn = !!(rg && rg.riskOn);

// REGIME-LOG: 첫 스캔 시 Regime 상태 Telegram 발송 (하루 1회)
if (!store.regimeLogSent || store.regimeLogSent !== today) {
  store.regimeLogSent = today;
  const regimeMsg =
    `📊 [시장 Regime] ${today}` + NL +
    `KOSPI SMA20>SMA60: ${rg.ksUp === null ? 'N/A' : (rg.ksUp ? '✅' : '❌')}` + NL +
    `KOSDAQ SMA20>SMA60: ${rg.kqUp === null ? 'N/A' : (rg.kqUp ? '✅' : '❌')}` + NL +
    `riskOn: ${riskOn ? '✅ 정상' : '⚠️ 약세장'}`;
  try { await http({ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
    json: true, body: { chat_id: CHAT, text: regimeMsg } }); } catch(e) {}
}
```

---

## 4. 04-30 Market Regime 작동 여부 — 사후 검증 방법

현재 코드에는 Regime 상태 로그가 없어 04-30 당시 riskOn 값을 직접 확인할 수 없음.
다음 방법으로 간접 검증 가능:

### 4.1 KOSPI SMA20/SMA60 역산

```
2026-04-30 기준:
  - SMA20 = 2026-04-03 ~ 04-30 종가 평균 (20거래일)
  - SMA60 = 2026-02-12 ~ 04-30 종가 평균 (60거래일)
  - 04-02 Liberation Day 급락 이후 SMA60이 더 높을 가능성 → riskOn=false 추정
```

### 4.2 n8n Static Data 확인

n8n 워크플로우의 `getWorkflowStaticData('global')`에 `store.regimeCache`가 남아있다면:
- `store.regimeCache.date`, `store.regimeCache.riskOn` 값 확인
- n8n 워크플로우 실행 이력에서 Static Data JSON 조회

### 4.3 주간 리포트 간접 증거

- 04-30에 진입한 2종목이 모두 즉시 손절됐다는 사실 자체가
  당일 시장 환경 불량(riskOn=false)을 간접적으로 시사
- REGIME-LOG 구현 후에는 매일 Telegram으로 상태 확인 가능

---

## 5. 파일별 변경 요약

| 파일 | ID | 변경 유형 | 변경 내용 |
|------|----|---------|---------| 
| `weekly_reporter_code.js` | TRAIL-01 | **수정** | 당일단타 트레일링 스탑 시뮬레이션 로직 추가 |
| `weekly_reporter_code.js` | TRAIL-01 | **수정** | atrAbs 저장 여부 검증 및 누락 시 보완 |
| `swing_scanner_code.js` | REGIME-FIX | **수정** | riskOn=false 시 점수/등급 추가 커트라인 |
| `swing_scanner_code.js` | REGIME-LOG | **수정** | 하루 1회 Regime 상태 Telegram 발송 |

---

## 6. 구현 우선순위 및 순서

```
Phase 1 — 즉시 효과 (Do 단계 1순위):
  1. REGIME-LOG: 먼저 추가 → 다음 거래일부터 매일 상태 확인 가능
  2. REGIME-FIX: riskOn=false 시 강매 전용 또는 +20점 상향

Phase 2 — 성과 정확화:
  3. TRAIL-01: weekly_reporter_code.js 트레일링 스탑 시뮬레이션
     - atrAbs가 store에 저장되어 있는지 먼저 확인 필요
```

---

## 7. 기대 효과 (이번 주 리포트 소급 시뮬레이션)

| 항목 | 현재 | 개선 후 (예상) |
|------|------|--------------|
| 수익 건수 | 3건 (승률 43%) | **5~6건** (LS네트웍스, 도이치모터스 재분류) |
| 손절 건수 | 5건 | **3건 이하** |
| LS네트웍스 결과 | 손절(-3%) | **이익 청산(+12% 추정)** |
| 도이치모터스 결과 | 손절(-3%) | **이익 청산(+3~4%)** |
| riskOn=false 날 진입 | 차단 없음 | 강매 등급만 허용 |

---

## 8. 제약 사항 및 리스크

| 리스크 | 내용 | 대응 |
|--------|------|------|
| atrAbs 미저장 | weekly_reporter에서 trailingStop 계산 불가 | 실제 store 구조 먼저 확인 후 진행 |
| Regime 과도 차단 | riskOn=false 시 강매 전용으로 하면 추천 0건 가능성 | REGIME_OFF_SCORE_BOOST=20 먼저 적용, 추이 관찰 |
| 트레일링 시뮬레이션 한계 | 일별 OHLC만 사용 — 장중 구체적 출구 타임스탬프 불명 | 보수적 배수(0.5~1.0) 사용으로 과대 추정 방지 |
| 04-30 데이터 없음 | Regime 상태 직접 확인 불가 | REGIME-LOG 이후부터만 추적 가능 |

---

## 9. 변경 제외 항목 (현행 유지)

| 항목 | 유지 이유 |
|------|---------|
| `ATR_STOP_MULT = 1.0` | 진입 시 손절은 적정, 문제는 트레일링 없음 |
| `CAP_TARGET_PCT = 0.07` | 7% 목표 캡 유지 (당일 달성 가능 범위) |
| `RELAX_SCORE = 90` | 품질 기준 현행 유지 |
| `MAX_INTRADAY_SENDS = 2` | 집중도 현행 유지 |
| `STOP_NEW_ALERTS_HOUR = 11` | 오전 알림 한정 현행 유지 |

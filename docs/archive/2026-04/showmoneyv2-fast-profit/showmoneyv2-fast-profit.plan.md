## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | showmoneyv2-fast-profit |
| 시작일 | 2026-04-11 |
| 대상 파일 | `swing_scanner_code.js` |

### Value Delivered

| 관점 | 내용 |
|------|------|
| Problem | ① 급등주 차단(RSI 상한·정배열 필수) ② `매수` 등급 저품질 종목이 2주 보유 대기하며 알림 자리 차지 ③ 최소 목표 3%로 수익성 낮은 종목도 발송 |
| Solution | `급등` 등급 신설 + HIGH IMPACT 4개 지표 + **`매수` 등급 알림 차단** + **최소 목표 5% 상향** + **보유기간 단축** + **filler 채움 로직 비활성화** |
| Function UX Effect | 알림 수는 줄지만 수신 시 **1~3일 내 5%+ 수익 가능성 높은 종목만** 도착 (`강매`/`급등`/`매도차익` 3등급 한정) |
| Core Value | 종목 수 < 정확도 — 옵티시스(+55%), 대한광통신(+35%) 유형만 수신, 현대건설(+1.3%) 유형 완전 차단 |

---

# Plan: showmoneyv2-fast-profit

## 1. 개요

### 1.1 배경 및 문제 정의

현재 스윙 스캐너는 **기술적 정배열·RSI 구간·ADX 추세** 기반의 중기 스윙을 포착하도록 설계됨.
실제 주간 리포트(2026-04-06~04-10) 결과를 보면 두 가지 문제가 동시에 존재:

**문제 ① 급등주 포착 실패 (신호 차단)**

| 차단 원인 | 현재 로직 | 급등주 실제 상태 |
|-----------|-----------|----------------|
| RSI 상한 | `RSI > 80 → return` | 급등주는 RSI 80-95로 진입 |
| 일봉 정배열 필수 | `SMA20 > SMA60 필수` | 테마 초기 급등은 정배열 전에 폭발 |
| 매도차익 기준 낮음 | `dailyChange >= 2%` | 실제 급등은 +5~15% 이상 |
| 신고가 처리 미흡 | `PTH >= 0.95 → +25점` | 진짜 신고가 돌파(`currentPrice > high252`)는 별도 처리 없음 |
| 연속 상승 미감지 | 없음 | 테마주 2일 연속 강세 후 추가 급등 패턴 |

**문제 ② 저품질 종목 알림 발송 (노이즈)**

실제 결과: 총 추천 20건 중 **보유 12건**이 예정일(04-20~04-24)까지 2주 대기 중.
이 중 +5% 미만 종목: 현대건설(+1.3%), 넥스틸(+2.5%), 엘앤에프(+4.4%), GS건설(+4.9%) = **4건**

| 문제 원인 | 현재 로직 | 결과 |
|-----------|-----------|------|
| `매수` 등급 발송 | score 80~119면 알림 발송 | 저품질 스윙픽 2주 보유 대기 |
| filler 채움 | `MIN_DAILY_PICKS=2` 미달 시 완화 통과 종목 강제 추가 | 저품질 종목 의무 발송 |
| 최소 목표 3% | `MIN_TARGET_PCT = 0.03` | 3~4% 목표 종목도 발송 |
| 보유기간 6거래일 | `HOLD_NORMAL = 6` | 2주간 동일 종목 재추천 차단 |

### 1.2 목표

**[포착 개선] 급등주 탐지 강화**
1. **`급등` 등급 신설** - 테마 모멘텀 급등 전용 알림 등급 (`[🚀급등]`)
2. **RSI 상한 예외 처리** - 고RVOL·고변화율 조건 충족 시 RSI 90까지 허용
3. **52주 신고가 돌파 강화** - 신고가 돌파 시 최우선 보너스 점수
4. **연속 상승 패턴 감지** - 2일+ 연속 양봉 & 거래량 확대 보너스
5. **정배열 예외 허용** - RVOL 5x 이상 & 당일 +5% 이상 시 정배열 조건 생략 허용
6. **`vol_trend_5_60` 추가** - 5일/60일 거래량 비율로 지속 수급 집중 감지
7. **`priceFromLow` 추가** - 52주 저점 대비 반등률로 추세전환 + 모멘텀 이중 확인
8. **`intradayStrength` 추가** - 당일 시가 대비 종가 강도로 장 마감 강세 확인
9. **`sectorMomentum` 추가** - 업종 코드 기반 동반 강세 카운트로 테마 신뢰도 향상

**[발송 정책] 단기 고수익 종목만 알림**
10. **`매수` 등급 알림 차단** - score 80~119 표준 스윙픽 발송 중단 (`강매`/`급등`/`매도차익` 3등급만)
11. **최소 목표수익률 상향** - `MIN_TARGET_PCT` 3% → **5%** (3~4% 목표 종목 차단)
12. **filler 채움 로직 비활성화** - `MIN_DAILY_PICKS` 강제 채움 제거 (없으면 0건 발송)
13. **보유기간 단축** - 강매 10일→5일 / 급등 2일 / 매도차익 2일 (DUPLICATE_WINDOW 연동)

---

## 2. 현재 로직 분석

### 2.1 현재 등급 체계

```
강매  : score >= 120
매수  : score >= 80
매도차익: strictPass & dailyChange >= 2% & RVOL >= A(3x)
관심  : score >= 60 (미발송)
```

### 2.2 핵심 필터 (순서대로)

```javascript
// 현재 코드 (swing_scanner_code.js, 약 930-965줄)
RSI_MIN_ENTRY = 45   // RSI 하한
RSI_MAX_ENTRY = 80   // RSI 상한 ← 급등주 차단 주범

// SMA20 > SMA60 필수 (line ~964)
if (!dailyUptrend) return;   // 급등 초기 돌파 차단

// RVOL
RVOL_GRADE_A = 3.0   // 현재 A등급
```

### 2.3 옵티시스/대한광통신 패턴 분석

```
패턴 특징:
- RVOL: 5x ~ 20x (기존 A등급 3x 대비 훨씬 높음)
- vol_trend_5_60: 3x ~ 8x (60일 평균 대비 5일 평균이 폭발적으로 증가)
- dailyChange: +5% ~ +20%
- RSI: 진입 시 이미 75-90 (현재 로직 차단)
- 52주 신고가 돌파 or 근접
- priceFromLow: 저점 대비 +50~200% 반등 중 (추세 이미 전환된 상태)
- intradayStrength: 시가 갭업 + 위꼬리 없이 마감 (장 마감 강세)
- 동일 업종(광통신) 2~4종목 동시 강세 (테마 확인)
- 테마(AI 광통신) 이슈 촉발
- 보유기간: 1~3거래일
```

### 2.4 현재 미활용 데이터 현황

| 데이터 | 현재 상태 | 활용 방안 |
|--------|-----------|----------|
| `rawOpen` (시가) | Naver API 응답에 존재하지만 미수집 | `intradayStrength` 계산용 |
| `low252` (52주 최저가) | `high252`만 계산, `low252` 없음 | `priceFromLow` 계산용 |
| `volD` 장기 평균 | 20일 평균(RVOL)만 계산 | 60일 평균 추가로 `vol_trend_5_60` 산출 |
| KRX Universe 업종코드 | 유니버스 로딩 시 존재하나 저장 안 됨 | `sectorMomentum` 집계용 |

---

## 3. 개선 사항

### 3.1 변경 상수 (기존 상수 수정)

**Before:**
```javascript
const MIN_TARGET_PCT  = 0.03;  // 최소 목표 수익률 3%
const MIN_DAILY_PICKS = 2;     // 최소 발송 건수 (filler 채움 트리거)
const HOLD_STRONG     = 10;    // 강매 보유 기간 10거래일
const HOLD_NORMAL     = 6;     // 매수 보유 기간 6거래일
```

**After:**
```javascript
const MIN_TARGET_PCT  = 0.05;  // 최소 목표 수익률 3% → 5% (저수익 종목 차단)
const MIN_DAILY_PICKS = 0;     // filler 채움 비활성화 (0건이어도 발송 안 함)
const HOLD_STRONG     = 5;     // 강매 보유 기간 10→5거래일 (빠른 단기 종료)
const HOLD_NORMAL     = 6;     // 매수 보유 기간 유지 (발송 차단되므로 실질 미사용)
```

---

### 3.2 신규 상수 추가

```javascript
// === 급등 모멘텀 포착 상수 ===
const SURGE_DAILY_CHANGE = 0.05;   // 급등 최소 당일 변화율 (+5%)
const SURGE_RVOL_MIN    = 5.0;     // 급등 최소 RVOL (5x)
const RSI_SURGE_MAX     = 90;      // 급등 모멘텀 RSI 상한 완화 (80→90)
const SURGE_SCORE_BONUS = 50;      // 급등 조건 충족 시 추가 점수
const CONSEC_UP_BONUS   = 15;      // 2일+ 연속 양봉 거래량 확대 보너스
const NEW_HIGH52W_BONUS = 40;      // 52주 신고가 돌파 보너스 (PTH>1.0)
const HOLD_SURGE        = 2;       // 급등 등급 보유 기간 (거래일)
const SCORE_SURGE       = 100;     // 급등 등급 점수 기준

// === HIGH IMPACT 정밀 지표 상수 ===
const VOL_TREND_5_60_B  = 2.0;     // 5/60일 거래량 비율 B등급 (수급 집중 시작)
const VOL_TREND_5_60_A  = 3.0;     // 5/60일 거래량 비율 A등급 (수급 집중 강화)
const PRICE_FROM_LOW_MIN = 0.30;   // 52주 저점 대비 최소 반등률 (+30%: 추세전환 확인)
const PRICE_FROM_LOW_BONUS = 20;   // 저점반등 확인 보너스
const INTRADAY_STR_MIN  = 0.6;     // 당일 강도 하한 (종가가 범위 상단 60% 이상)
const INTRADAY_STR_BONUS = 10;     // 당일 강도 보너스
const SECTOR_MOMENTUM_BONUS = 10;  // 동일 업종 2개+ 동시 강세 보너스
```

### 3.2 RSI 예외 처리 (현재 line ~936-940)

**Before:**
```javascript
if (rsi14Val < RSI_MIN_ENTRY) return;
if (rsi14Val > RSI_MAX_ENTRY) return;  // 무조건 차단
```

**After:**
```javascript
// 급등 모멘텀 조건: RVOL 선계산 필요하므로 RSI 필터를 RVOL 계산 후로 이동
// → 필터 순서 재배치 후:
const isSurgeCandiate = dailyChange >= SURGE_DAILY_CHANGE && rvolVal >= SURGE_RVOL_MIN;
if (rsi14Val < RSI_MIN_ENTRY) return;
if (rsi14Val > RSI_SURGE_MAX) return;          // 급등주 포함 상한 90
if (!isSurgeCandidate && rsi14Val > RSI_MAX_ENTRY) return;  // 일반 80 유지
```

### 3.3 일봉 정배열 예외 (현재 line ~963-966)

**Before:**
```javascript
const dailyUptrend = sma20_d[dIdx] > sma60_d[dIdx];
if (!dailyUptrend) return;
score += 15;
```

**After:**
```javascript
const dailyUptrend = sma20_d[dIdx] > sma60_d[dIdx];
const isSurgeCandidate = dailyChange >= SURGE_DAILY_CHANGE && rvolVal >= SURGE_RVOL_MIN;
if (!dailyUptrend && !isSurgeCandidate) return;  // 급등 조건 충족 시 정배열 예외
if (dailyUptrend) { score += 15; signals.push('일봉정배열'); }
```

### 3.4 52주 신고가 돌파 보너스 강화 (현재 line ~1014-1021)

**Before:**
```javascript
if (pth >= 0.95) { score += 25; signals.push('신고가근접(PTH)'); }
else if (pth >= 0.90) { score += 15; signals.push('52주고점근접'); }
```

**After:**
```javascript
if (currentPrice >= high252) {          // 진짜 신고가 돌파
  score += NEW_HIGH52W_BONUS;           // +40
  signals.push('52주신고가돌파');
} else if (pth >= 0.95) {
  score += 25; signals.push('신고가근접(PTH)');
} else if (pth >= 0.90) {
  score += 15; signals.push('52주고점근접');
}
```

### 3.5 연속 상승 패턴 보너스 (새 로직 추가)

```javascript
// dIdx 기준 최근 3일 연속 양봉 & 거래량 확대 여부
const recentDays = 3;
let consecUp = 0;
let volExpanding = true;
for (let i = dIdx - recentDays + 1; i <= dIdx; i++) {
  if (i > 0 && closeD[i] > closeD[i-1]) consecUp++;
  else { consecUp = 0; break; }
  if (i > 0 && volD[i] < volD[i-1]) volExpanding = false;
}
if (consecUp >= 2 && volExpanding) {
  score += CONSEC_UP_BONUS;
  signals.push(`연속상승(${consecUp}일)`);
}
```

### 3.6 [HIGH] 5일/60일 거래량 비율 (`vol_trend_5_60`)

기존 RVOL은 당일 거래량 vs 20일 평균이지만, **수급이 며칠째 집중되고 있는지**는 감지하지 못함.
`volAvg5 / volAvg60`은 최근 5일 평균이 60일 평균의 몇 배인지를 측정해 **지속적 수급 유입**을 포착.

```javascript
// 기존 vol20Avg 계산 이후 추가
const volAvg5  = volD.slice(Math.max(0, dIdx-5),  dIdx).reduce((a,b)=>a+b,0) / Math.min(5, dIdx);
const volAvg60 = volD.slice(Math.max(0, dIdx-60), dIdx).reduce((a,b)=>a+b,0) / Math.min(60, dIdx);
const volTrend5_60 = (volAvg60 > 0) ? volAvg5 / volAvg60 : 0;

// 스코어링 블록에 추가
if (volTrend5_60 >= VOL_TREND_5_60_A) {
  score += 20;
  signals.push('수급집중(A)');         // 5일 평균이 60일 평균의 3배 이상
} else if (volTrend5_60 >= VOL_TREND_5_60_B) {
  score += 10;
  signals.push('수급집중(B)');         // 5일 평균이 60일 평균의 2배 이상
}
```

**기대 효과**: RVOL(단일 당일) + vol_trend_5_60(5일 누적) 이중 확인으로 "오늘 우연히 많은 것"과 "수일간 수급이 쌓이는 것"을 구분.

---

### 3.7 [HIGH] 52주 저점 대비 반등률 (`priceFromLow`)

현재 `high252`(52주 고점)는 계산하지만 `low252`(52주 최저가)는 없음.
저점 대비 반등률은 **추세가 이미 전환된 종목** 여부를 확인하는 독립 지표.

```javascript
// high252 계산 바로 아래에 추가
const low252 = Math.min(...lowD.slice(Math.max(0, dIdx-252), dIdx+1).map(Number));
const priceFromLow = (low252 > 0) ? (currentPrice / low252 - 1) : 0;

// 스코어링 블록에 추가 (PTH 섹션 근처)
if (priceFromLow >= 1.0) {
  // 저점 대비 +100% 이상 & 신고가 근접 = 최강 추세전환 모멘텀
  score += PRICE_FROM_LOW_BONUS;       // +20
  signals.push('저점반등(100%+)');
} else if (priceFromLow >= PRICE_FROM_LOW_MIN) {
  score += 10;
  signals.push('저점반등(30%+)');
}
```

**기대 효과**: PTH(신고가 근접)와 조합하면 "바닥에서 올라온 종목이 신고가 돌파하는" 패턴 — 가장 강한 상승 초입 신호.

---

### 3.8 [HIGH] 당일 장 마감 강도 (`intradayStrength`)

Naver daily API 응답에 `open`(시가)가 존재하나 현재 미수집. `rawOpen` 추가 후 당일 캔들 형태를 분석.

```javascript
// rawOpen 수집 추가 (line ~905-909)
const rawOpen  = (qD.open   || []).map(Number);   // ← 추가
// validIdx 필터 및 openD 배열 생성
const openD  = validIdx.map(i => rawOpen[i] > 0 ? rawOpen[i] : closeD[validIdx.indexOf(i)]);

// 스코어링 블록에 추가
const dayRange = highD[dIdx] - lowD[dIdx];
const intradayStrength = (dayRange > 0)
  ? (closeD[dIdx] - openD[dIdx]) / dayRange : 0;

if (intradayStrength >= INTRADAY_STR_MIN) {
  score += INTRADAY_STR_BONUS;   // +10
  signals.push('장마감강세');     // 종가가 범위 상단 60% 이상
}
```

**기대 효과**: 위꼬리 없이 강하게 마감한 종목을 구분. 급등주가 장 초반 갭업 후 흘러내리지 않고 강세 마감한 날만 포착.

---

### 3.9 [HIGH] 업종 동반 강세 (`sectorMomentum`)

같은 업종에서 복수 종목이 동시에 candidates에 들어오면 테마 모멘텀이 **섹터 전반으로 확산**되고 있다는 신호.

**구현 방법 — 2단계:**

**Step 1: 유니버스 빌드 시 업종코드 저장 (line ~665 근처)**
```javascript
// KRX/Naver Universe 파싱 시 업종코드 추출하여 저장
if (!store.sectorMap) store.sectorMap = {};
const sectorCode = String(row.IDX_IND_NM || row.ISU_SRT_CD || '').slice(0, 4); // 업종코드 앞 4자리
if (rc && sectorCode) store.sectorMap[rc] = sectorCode;
```

**Step 2: candidates 집계 후 rankScore 보정 (line ~1208 집계 직후)**
```javascript
// candidates 정렬 전에 섹터 카운트 집계
const sectorCounts = {};
for (const c of candidates) {
  const sc = store.sectorMap && store.sectorMap[c.code];
  if (sc) sectorCounts[sc] = (sectorCounts[sc] || 0) + 1;
}
// 동일 섹터 2개+ 강세 종목에 rankScore 보너스 부여
for (const c of candidates) {
  const sc = store.sectorMap && store.sectorMap[c.code];
  if (sc && sectorCounts[sc] >= 2) {
    c.rankScore  += SECTOR_MOMENTUM_BONUS;   // +10
    c.signals.push(`섹터동반강세(${sectorCounts[sc]}종목)`);
  }
}
```

**기대 효과**: 광통신 섹터에서 옵티시스만 오르는 것과 옵티시스+대한광통신+이노와이어리스가 동시에 오르는 것을 구분 → 테마 확산 시 신뢰도 대폭 향상.

---

### 3.10 급등 등급 신설 및 알림 형식

**등급 판정 (현재 line ~1102-1108)**

**Before:**
```javascript
const isStrong    = score >= SCORE_STRONG;
const isShortTrade = !isStrong && strictPass && dailyChange >= 0.02 && rvolVal >= RVOL_GRADE_A;
const grade = isStrong     ? '강매'
            : isShortTrade ? '매도차익'
            : strictPass   ? '매수'
            : '관심';
```

**After:**
```javascript
const isStrong     = score >= SCORE_STRONG;
const isSurge      = !isStrong && score >= SCORE_SURGE
                     && dailyChange >= SURGE_DAILY_CHANGE
                     && rvolVal >= SURGE_RVOL_MIN;
const isShortTrade = !isStrong && !isSurge && strictPass
                     && dailyChange >= 0.02 && rvolVal >= RVOL_GRADE_A;
const grade = isStrong     ? '강매'
            : isSurge      ? '급등'
            : isShortTrade ? '매도차익'
            : strictPass   ? '매수'
            : '관심';
```

**알림 prefix (현재 line ~1257)**

```javascript
const gradePrefix = (c.grade === '강매')    ? '[★강매] '
                  : (c.grade === '급등')    ? '[🚀급등] '  // 신규
                  : (c.grade === '매도차익') ? '[⚡단기] '
                  : (c.grade === '관심')    ? '[관심] '
                  : '';
```

**보유 기간 (현재 HOLD 상수 참조 영역)**

```javascript
const holdDays = (grade === '강매')    ? HOLD_STRONG
               : (grade === '급등')    ? HOLD_SURGE      // 2거래일
               : (grade === '매도차익') ? HOLD_SHORTTRADE
               : HOLD_NORMAL;
```

---

### 3.11 [발송 정책] `매수` 등급 알림 차단 + filler 제거

현재 `선정 로직` (line ~1209-1217):
```javascript
// 현재: strictPass(score>=80) 전체 발송 + 부족 시 완화 종목 강제 추가
const strictSelected = candidates.filter((c) => c.strictPass).slice(0, MAX_INTRADAY_SENDS);
const selected = strictSelected.slice();
if (selected.length < MIN_DAILY_PICKS) {           // MIN_DAILY_PICKS=2 미달 시
  const fillers = candidates.filter((c) => !used.has(c.ticker) && c.relaxedPass).slice(0, need);
  for (const f of fillers) selected.push(f);       // 완화 종목 강제 추가 ← 문제
}
```

**After — 단기 고수익 등급만 발송:**
```javascript
// 변경: 강매/급등/매도차익 3등급만 선발, filler 없음
const FAST_GRADES = new Set(['강매', '급등', '매도차익']);
const selected = candidates
  .filter((c) => FAST_GRADES.has(c.grade))
  .slice(0, MAX_INTRADAY_SENDS);
// MIN_DAILY_PICKS=0이므로 0건이면 그냥 종료 (알림 없음)
```

**기대 효과:**
- `매수` 등급(머큐리, 남선알미늄, 삼아알미늄 등 2주 보유 유형) → 발송 차단
- 완화 통과 종목(relaxedPass) 강제 채움 → 제거
- 하루에 0~2건만 발송되더라도 발송된 종목은 모두 고신뢰도

---

### 3.12 [발송 정책] holdDays 단축 및 DUPLICATE_WINDOW 연동

현재 holdDays (line ~1301-1304):
```javascript
const holdDays = (selected[i].grade === '강매')    ? HOLD_STRONG     // 10거래일
               : (selected[i].grade === '매수')     ? HOLD_NORMAL     // 6거래일
               : (selected[i].grade === '매도차익') ? HOLD_SHORTTRADE // 2거래일
               : HOLD_WEAK;                                           // 2거래일
```

**After:**
```javascript
const holdDays = (selected[i].grade === '강매')    ? HOLD_STRONG     // 10→5거래일
               : (selected[i].grade === '급등')    ? HOLD_SURGE      // 2거래일 (신규)
               : (selected[i].grade === '매도차익') ? HOLD_SHORTTRADE // 2거래일
               : HOLD_WEAK;
```

> **참고**: `DUPLICATE_WINDOW_MINUTES = 4320`(3일)은 유지.
> 급등/매도차익은 2거래일 보유이므로 3일 dedup 창과 자연스럽게 일치.
> 강매는 5거래일(약 7일)이므로 재추천 가능성 있으나 점수 재확인 후 재진입 허용.

---

## 4. 구현 순서

### Phase 1: 발송 정책 변경 (즉각 효과 — 노이즈 차단)
1. **상수 수정** - `MIN_TARGET_PCT` 3%→5%, `MIN_DAILY_PICKS` 2→0, `HOLD_STRONG` 10→5 (§3.1)
2. **선발 로직 교체** - `FAST_GRADES` 필터 + filler 제거 (line ~1209, §3.11)
3. **holdDays 수정** - 급등 등급 추가, 강매 단축 (line ~1301, §3.12)

### Phase 2: 기존 필터 개선 (급등주 포착)
4. **신규 상수 추가** - `SURGE_*` 및 HIGH IMPACT 상수 블록 (§3.2)
5. **`rawOpen` 수집** - Naver daily API 파싱 시 open 데이터 추가 (line ~905)
6. **필터 순서 재배치** - RVOL 계산을 RSI 필터보다 먼저 수행
7. **RSI 예외 로직** - `isSurgeCandidate` 플래그 (RSI 80→90 완화) (§3.3)
8. **정배열 예외** - `if (!dailyUptrend && !isSurgeCandidate) return` (§3.4)

### Phase 3: 신규 지표 추가
9. **`low252` + `volAvg60`** - 기존 계산 블록 직후 추가
10. **스코어링 블록 확장** - vol_trend_5_60 / priceFromLow / intradayStrength / 신고가돌파 / 연속상승 (§3.6~3.9)

### Phase 4: 등급·섹터 처리
11. **급등 등급 판정** - `isSurge` 조건 삽입 (§3.10)
12. **알림 prefix** - `[🚀급등]` 추가 (§3.10)
13. **업종코드 저장 + 섹터 보너스** - `store.sectorMap` + `sectorCounts` (§3.9)

---

## 5. 리스크 및 제약

| 리스크 | 대응 |
|--------|------|
| 급등 당일 고점 매수 위험 | HOLD_SURGE = 2일 짧게 유지, 손절 ATR 1.5x 유지 |
| 노이즈 급증 (저품질 급등) | SURGE_RVOL_MIN >= 5x & dailyChange >= 5% 이중 조건 |
| 정배열 조건 완화로 하락주 유입 | `!dailyUptrend` 진입 시 score 보너스 없음 (0점 시작) |
| RSI 90 완화로 과매수 포착 위험 | 급등 등급 전용 짧은 보유기간 + 손절 유지 |
| `rawOpen` 누락 종목 (시가 0) | `openD[i] = 0`인 경우 `closeD[i]`로 fallback (intradayStrength = 0 처리) |
| 업종코드 미수록 종목 | `sectorMap` 미등록 시 섹터 보너스 skip (0점, 오류 없음) |
| `low252` 계산 오류 (상장일 < 252일) | `lowD.slice` 범위가 짧아도 `Math.min` 적용 정상 동작 |

---

## 6. 완료 조건

### 기존 개선 항목
- [ ] `급등` 등급이 정상 판정되어 `[🚀급등]` 알림 발송
- [ ] RVOL 5x & dailyChange 5%+ 종목이 RSI 80-90 구간에서도 포착
- [ ] 52주 신고가 돌파 종목에 `52주신고가돌파` 시그널 표시
- [ ] 일봉 정배열 미형성이어도 급등 조건 충족 시 candidates에 포함
- [ ] 연속 상승 2일+ 종목에 `연속상승(N일)` 시그널 표시

### HIGH IMPACT 신규 항목
- [ ] `vol_trend_5_60 >= 3.0` 종목에 `수급집중(A)` 시그널 및 +20점 반영
- [ ] `priceFromLow >= 1.0` 종목에 `저점반등(100%+)` 시그널 및 +20점 반영
- [ ] `intradayStrength >= 0.6` 종목에 `장마감강세` 시그널 및 +10점 반영
- [ ] 동일 업종 2개+ 강세 시 `섹터동반강세(N종목)` 시그널 및 rankScore +10 반영
- [ ] `openD` 데이터 정상 수집 확인 (open = 0인 fallback 동작 포함)

### 발송 정책 변경 항목
- [ ] `매수` 등급 종목이 candidates에 있어도 selected에 포함되지 않음
- [ ] 완화 통과(relaxedPass) 종목이 filler로 추가되지 않음
- [ ] 후보 0건 시 알림 없이 정상 종료
- [ ] 목표가 < 진입가 × 1.05인 종목은 R:R 필터에서 차단 (`MIN_TARGET_PCT=0.05`)
- [ ] 강매 holdDays = 5거래일 (기존 10 → 5)
- [ ] 급등 holdDays = 2거래일

### 회귀 테스트
- [ ] 강매/급등/매도차익 등급은 정상 발송
- [ ] HIGH IMPACT 지표가 0점이어도 기존 로직에 영향 없음
- [ ] 기존 `관심` 등급 미발송 동작 유지

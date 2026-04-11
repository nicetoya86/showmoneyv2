# Design: swing-benchmark-best

> Plan 문서: `docs/01-plan/features/swing-benchmark-best.plan.md`
> 대상 파일: `swing_scanner_code.js`, `weekly_reporter_code.js`

---

## 1. 변경 목록 (총 7곳)

| ID | 파일 | 위치 | 변경 유형 |
|----|------|------|---------|
| HOLD-02 | swing_scanner_code.js | 상수 블록 | HOLD_STRONG/NORMAL 수정, HOLD_SHORTTRADE 추가 |
| TARGET-01-A | swing_scanner_code.js | 상수 블록 | TARGET1_PCT, ATR_TARGET_SHORT 추가 |
| TARGET-01-B | swing_scanner_code.js | target 계산 | target1 계산 추가, 매도차익 목표배수 분기 |
| TARGET-01-C | swing_scanner_code.js | candidates.push | target1, rvolVal 필드 추가 |
| SHORTTRADE-01 | swing_scanner_code.js | 등급 판정 | 매도차익 등급 조건 추가 |
| MSG-01 | swing_scanner_code.js | Telegram 메시지 | 1차목표 줄 추가, [⚡단기] prefix |
| SEND-01 | swing_scanner_code.js | send() + weeklyRec | target1, atrAbs 저장, holdDays 매도차익 추가 |
| REPORTER-02 | weekly_reporter_code.js | 평가 루프 + 리포트 | hitTarget1Day, partial_win, 🎯 1차달성 섹션 |

---

## 2. 상세 변경 명세

### HOLD-02 — 보유기간 상수 변경

**변경 후:**
```javascript
const HOLD_STRONG = 10;         // 강매: 10거래일 (트레일링 스탑과 병행)
const HOLD_NORMAL = 6;          // 매수: 6일 (데이터 5.64일 기반)
const HOLD_WEAK = 2;            // 완화: 유지
const HOLD_SHORTTRADE = 2;      // 매도차익: 2일 (데이터 1.5일 기반)
```

> 참고: Plan에는 `HOLD_STRONG = 0`(무제한)으로 명시했으나, weekly_reporter 호환성 및
> 미구현 상태의 Daily_Position_Monitor 연동 전까지 10일로 한시 운영.

---

### TARGET-01-A — 1차 목표 상수 추가

```javascript
const TARGET1_PCT = 0.07;       // 1차 목표 비율 (+7%, 5~10% 구간 중앙값)
const ATR_TARGET_SHORT = 1.5;   // 매도차익 등급 목표 배수 (ATR 1.5x)
```

---

### SHORTTRADE-01 — 매도차익 등급 판정

**변경 후:**
```javascript
const isStrong = score >= SCORE_STRONG;
const isShortTrade = !isStrong && strictPass && dailyChange >= 0.02 && rvolVal >= RVOL_GRADE_A;
const grade = isStrong ? '강매'
            : isShortTrade ? '매도차익'
            : strictPass ? '매수'
            : '관심';
```

> 조건: `dailyChange >= 0.02` (당일 +2%↑) AND `rvolVal >= RVOL_GRADE_A` (3.0x+) AND `strictPass`

---

### TARGET-01-B — target1 계산 및 매도차익 목표배수 분기

```javascript
const atrAbs = calcAtrAbs(highD, lowD, dIdx, ATR_WINDOW);
let stop = currentPrice - atrAbs * ATR_STOP_MULT;
const targetMult = (grade === '매도차익') ? ATR_TARGET_SHORT : ATR_TARGET_MULT;
let target = currentPrice + atrAbs * targetMult;
// ... cap 적용 후 ...
const target1 = currentPrice * (1 + TARGET1_PCT);  // 모든 등급 공통
```

---

### TARGET-01-C — candidates.push 필드 추가

```javascript
candidates.push({
  ticker: t, code, name, market: mkt,
  entry: currentPrice, target, target1, stop,
  score, signals, dailyChange, currentPrice, prevClose,
  timeStr: timeStrNow, type: '스윙',
  rankScore, atrAbs, rvolVal, riskOn, qty, strictPass, relaxedPass, grade,
});
```

> `predType`, `predProb` 필드 제거됨 (swing-remove-hitalk에서 처리).

---

### MSG-01 — Telegram 메시지 변경

**변경 후:**
```javascript
const gradePrefix = (c.grade === '강매') ? '[★강매] '
                  : (c.grade === '매도차익') ? '[⚡단기] '
                  : (c.grade === '관심') ? '[관심] '
                  : '';
const target1Line = Number.isFinite(c.target1)
  ? '- 1차 목표: ' + to0(c.target1) + '원 (+' + pct(c.target1 / c.entry - 1) + ')' + NL
  : '';
const msg =
  gradePrefix + '[스윙 포착] ...' + NL +
  '등급: ' + (c.grade || '매수') + NL +
  '기준가: ' + to0(c.entry) + '원' + dailyChangeText + NL +
  '- 매수가: ...' + NL +
  target1Line +
  '- 최종 목표: ' + to0(c.target) + '원 (+' + pct(...) + ')' + NL +
  '- 손절가: ...' + NL +
  'ATR(14): ...' + NL +
  '- 점수: ' + c.score + '점' + NL +
  '핵심 시그널: ...';
```

---

### SEND-01 — send() 리턴 및 weeklyRecommendations 저장

**send() 리턴:**
```javascript
return { entry: c.entry, target: c.target, target1: c.target1, stop: c.stop, resolvedName: displayName };
```

**holdDays 계산:**
```javascript
const holdDays = (selected[i].grade === '강매') ? HOLD_STRONG
               : (selected[i].grade === '매수') ? HOLD_NORMAL
               : (selected[i].grade === '매도차익') ? HOLD_SHORTTRADE
               : HOLD_WEAK;
```

**weeklyRecommendations 저장:**
```javascript
store.weeklyRecommendations[today2].push({
  ...,
  target1: res.target1,
  atrAbs: selected[i].atrAbs,
  holdingDays: holdDays,
  ...
});
```

---

### REPORTER-02 — weekly_reporter_code.js 변경

**변수 추가:**
```javascript
let partialWins = 0;
let hitTarget1Day = null;
```

**평가 루프 내 target1 감지:**
```javascript
if (!hitTarget1Day && r.target1 && high >= r.target1) {
  hitTarget1Day = localDate;
}
```

**result 판정:**
```javascript
if (hitTargetDay && hitStopDay) {
  result = hitTargetDay <= hitStopDay ? 'win' : 'loss';
} else if (hitTargetDay) {
  result = 'win';
} else if (hitStopDay) {
  result = hitTarget1Day && hitTarget1Day <= hitStopDay ? 'partial_win' : 'loss';
}
if (result === 'partial_win') partialWins++;
```

**리포트 헤더:**
```
✅ 목표 N건 │ 🎯 1차달성 M건 │ ❌ 손절 K건 │ 🔄 보유 L건
```

**🎯 1차달성 섹션 추가:**
```
🎯 1차달성 (M건)
종목명(코드) │ 날짜 │ 1차 MM-DD │ 손절 MM-DD │ 최고 +X.X% │ 점수점
```

---

## 3. 변경 전/후 시나리오

### 시나리오 A — 당일 +3%, RVOL 4.5x, score=90 (매도차익)

| 항목 | 변경 전 | 변경 후 |
|------|--------|--------|
| 등급 | 매수 | **매도차익** |
| 목표가 | ATR×2.8 | **ATR×1.5** (더 가까운 목표) |
| 보유기간 | 3일 | **2일** |
| Telegram prefix | 없음 | **[⚡단기]** |

### 시나리오 B — score=85, 수요일 (매수)

| 항목 | 변경 전 | 변경 후 |
|------|--------|--------|
| 보유기간 | 3일 | **6일** |
| 1차 목표 | 없음 | **entry × 1.07** |
| Telegram | 목표가 1줄 | **1차목표 + 최종목표 2줄** |
| reporter partial_win | 없음 | 1차 달성 후 손절 시 `🎯 1차달성` |

### 시나리오 C — score=125 (강매)

| 항목 | 변경 전 | 변경 후 |
|------|--------|--------|
| 보유기간 | 5일 | **10일** |
| 목표배수 | ATR×2.8 | **ATR×2.8** (유지) |

---

## 4. 영향 없는 항목

| 항목 | 유지 이유 |
|------|---------|
| MIN_SCORE = 80 | swing-remove-hitalk에서 조정됨 |
| ATR_STOP_MULT = 1.9 | 유지 |
| ATR_TARGET_MULT = 2.8 | 2차 목표로 유지 |
| DOW 요일 보정 | 데이터와 일치 |
| R:R 1.5 필터 | 유지 |

---

## 5. 구현 순서

```
1. HOLD-02: 상수 수정 (HOLD_STRONG/NORMAL + 신규 3개)
2. TARGET-01-A: TARGET1_PCT, ATR_TARGET_SHORT 추가
3. SHORTTRADE-01: 등급 판정 로직 수정
4. TARGET-01-B: target 계산 분기 + target1 계산
5. TARGET-01-C: candidates.push 필드 추가
6. MSG-01: Telegram 메시지 수정
7. SEND-01: send() 리턴 + weeklyRec 저장
8. REPORTER-02: weekly_reporter_code.js 변경
```

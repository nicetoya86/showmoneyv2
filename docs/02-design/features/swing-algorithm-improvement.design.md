# Design: swing-algorithm-improvement

> Plan 문서: `docs/01-plan/features/swing-algorithm-improvement.plan.md`
> 대상 파일: `swing_scanner_code.js`

---

## ⚠️ Plan 문서 값 보정

코드 실측 결과 Plan 문서의 일부 파라미터 값이 달랐습니다. 설계는 실제 코드 기준으로 작성합니다.

| 항목 | Plan 문서 (잘못됨) | 실제 코드 값 |
|------|-------------------|------------|
| PMAT_STRICT | 75% | **60%** |
| PMAT_RELAX | 55% | **60%** |
| MIN_SCORE | 100점 | **60점** |
| RELAX_SCORE | 80점 | **50점** |
| CAP_TARGET_PCT | 15% | **25% (GAP-02 해당 없음)** |

> **CAP_TARGET_PCT가 이미 25%이므로 GAP-02 (목표가 상한 캡)는 실제 갭이 아닙니다. 제외합니다.**

---

## 1. 구현 대상 변경 (4개)

| ID | 항목 | 변경 위치 (line) | 난이도 |
|----|------|-----------------|--------|
| DOW-01 | 요일별 rankScore 보정 | line 1191 | 낮음 |
| HOLD-01 | 보유 기간 동적 계산 | line 1369 + candidates push | 낮음 |
| GRADE-01 | 강매 등급 식별 및 표기 | line 1217 candidates.push + send 함수 | 낮음 |
| CONST-01 | 신규 상수 추가 | 상단 상수 영역 (line 1 근처) | 낮음 |

---

## 2. 상세 설계

### 2.1 CONST-01 — 신규 상수 추가

**위치:** `swing_scanner_code.js` 상단 상수 선언부 (`MIN_RR_RATIO` 다음 줄)

```javascript
// ===== 실증 데이터 기반 개선 상수 (2026-03-29) =====
const PMAT_STRONG = 0.75;       // 강매 등급 PMAT 기준 (데이터 근거: 강매 등급 평균 30.34%)
const SCORE_STRONG = 100;       // 강매 등급 점수 기준
const HOLD_STRONG = 5;          // 강매 등급 보유 기간 (일)
const HOLD_NORMAL = 3;          // 기본 보유 기간 (일) - 현행 유지
const HOLD_WEAK = 2;            // 완화 통과 종목 보유 기간 (일)
const DOW_BONUS_THU = 3;        // 목요일 rankScore 보너스 (데이터: +0.57%)
const DOW_BONUS_WED = 2;        // 수요일 rankScore 보너스 (데이터: +0.34%)
const DOW_PENALTY_FRI = 5;      // 금요일 rankScore 패널티 (데이터: -0.62%)
```

---

### 2.2 DOW-01 — 요일별 rankScore 보정

**위치:** line 1191 (`const rankScore = pMAT * 100 + score;`)

**현재 코드:**
```javascript
const rankScore = pMAT * 100 + score;
```

**변경 후:**
```javascript
// 요일별 rankScore 보정 (실증 데이터 기반: 목요일 최고, 금요일 최저)
// d는 line 329에서 이미 선언됨 (kst.getUTCDay())
const dowAdj = (d === 4) ? DOW_BONUS_THU     // 목요일 +3
             : (d === 3) ? DOW_BONUS_WED     // 수요일 +2
             : (d === 5) ? -DOW_PENALTY_FRI  // 금요일 -5
             : 0;
const rankScore = pMAT * 100 + score + dowAdj;
```

**효과:**
- 목요일 진입 종목이 후보 정렬 상단에 더 많이 위치
- 금요일 진입 종목이 자연스럽게 하단으로 밀려 선발 제외 가능성 증가
- 기존 strictPass / relaxedPass 판정 로직 무변경

---

### 2.3 GRADE-01 — 강매 등급 식별

**위치 1:** line 1191 근처 (rankScore 계산 직후)

**추가 코드:**
```javascript
// 강매 등급 판정 (데이터 근거: 130점급 + PMAT 75%+ → 평균 30.34%)
const isStrong = (pMAT >= PMAT_STRONG) && (score >= SCORE_STRONG);
const grade = isStrong ? '강매' : '매수';
```

**위치 2:** `candidates.push(...)` (line 1217~1223)

**현재:**
```javascript
candidates.push({
  ticker: t, code, name, market: mkt,
  entry: currentPrice, target, stop,
  score, signals, dailyChange, currentPrice, prevClose,
  timeStr: timeStrNow, type: '스윙', predType, predProb,
  rankScore, atrAbs, riskOn, qty, strictPass, relaxedPass,
});
```

**변경 후:**
```javascript
candidates.push({
  ticker: t, code, name, market: mkt,
  entry: currentPrice, target, stop,
  score, signals, dailyChange, currentPrice, prevClose,
  timeStr: timeStrNow, type: '스윙', predType, predProb,
  rankScore, atrAbs, riskOn, qty, strictPass, relaxedPass,
  grade,  // ← 추가
});
```

**위치 3:** `send` 함수 내 메시지 구성 (line 1330~1339)

**현재:**
```javascript
const msg =
  '[스윙 포착] ' + c.market + ' | ' + esc(displayName) + '(' + c.code + ')' + NL +
  '예측유형: ' + (c.predType || 'N/A') + ...
```

**변경 후:**
```javascript
const gradePrefix = (c.grade === '강매') ? '[★강매] ' : '';
const msg =
  gradePrefix + '[스윙 포착] ' + c.market + ' | ' + esc(displayName) + '(' + c.code + ')' + NL +
  '등급: ' + (c.grade || '매수') + NL +
  '예측유형: ' + (c.predType || 'N/A') + ...
```

---

### 2.4 HOLD-01 — 보유 기간 동적 계산

**위치:** line 1365~1370 (`weeklyRecommendations` 저장부)

**현재:**
```javascript
store.weeklyRecommendations[today2].push({
  type: 'swing', subType: selected[i].type,
  ticker: selected[i].ticker, code: selected[i].code, name: res.resolvedName || selected[i].name,
  entry: res.entry, target: res.target, stop: res.stop,
  holdingDays: 3, score: selected[i].score,
});
```

**변경 후:**
```javascript
// 보유 기간 동적 계산 (데이터 근거: 강매급은 5일, 완화 통과는 2일)
const holdDays = (selected[i].grade === '강매') ? HOLD_STRONG
               : selected[i].strictPass ? HOLD_NORMAL
               : HOLD_WEAK;

store.weeklyRecommendations[today2].push({
  type: 'swing', subType: selected[i].type,
  ticker: selected[i].ticker, code: selected[i].code, name: res.resolvedName || selected[i].name,
  entry: res.entry, target: res.target, stop: res.stop,
  holdingDays: holdDays, score: selected[i].score,
  grade: selected[i].grade,  // ← 추가 (weekly reporter에서 활용 가능)
});
```

---

## 3. 변경 요약표

| ID | 파일 | 위치 | 변경 유형 | 코드 줄 수 |
|----|------|------|----------|-----------|
| CONST-01 | swing_scanner_code.js | 상수 영역 | 추가 | +8줄 |
| DOW-01 | swing_scanner_code.js | line 1191 | 수정 | 1→4줄 |
| GRADE-01 | swing_scanner_code.js | line 1191, 1222, 1330 | 추가/수정 | +6줄 |
| HOLD-01 | swing_scanner_code.js | line 1369 | 수정 | 1→4줄 |
| JSON | workflow_FINAL_*.json | — | 재생성 | — |

---

## 4. 변경 전/후 동작 비교

### 시나리오 A — 목요일, 강매 등급 종목

| 항목 | 변경 전 | 변경 후 |
|------|--------|--------|
| rankScore | 60 + 80 = 140 | 140 + 3(목요일) = **143** |
| 등급 표기 | `[스윙 포착]` | `[★강매] [스윙 포착]` + `등급: 강매` |
| 보유 기간 | 3일 | **5일** |
| Telegram 메시지 | 변화 없음 | 강매 프리픽스 추가 |

### 시나리오 B — 금요일, 완화 통과 종목

| 항목 | 변경 전 | 변경 후 |
|------|--------|--------|
| rankScore | 60 + 55 = 115 | 115 - 5(금요일) = **110** |
| 등급 표기 | `[스윙 포착]` | `[스윙 포착]` + `등급: 매수` |
| 보유 기간 | 3일 | **2일** |
| 후보 선정 | 가능 | 상대적으로 어려워짐 |

### 시나리오 C — 수요일, 기본 strictPass 종목

| 항목 | 변경 전 | 변경 후 |
|------|--------|--------|
| rankScore | 60 + 70 = 130 | 130 + 2(수요일) = **132** |
| 등급 표기 | `[스윙 포착]` | `[스윙 포착]` + `등급: 매수` |
| 보유 기간 | 3일 | **3일 (유지)** |

---

## 5. Telegram 메시지 예시 (변경 후)

**강매 등급:**
```
[★강매] [스윙 포착] KOSPI | 삼성전자(005930)
등급: 강매
예측유형: 재료 (82%)
기준가: 75,400원 (전일 대비 +3.2%)
- 매수가: 75,400원 (전일종가 기준, 시초가 확인 필수)
- 목표가: 88,500원 (+17.4%)
- 손절가: 68,100원 (-9.7%)
ATR(14): 2,840원
- 점수: 115점
핵심 시그널: N자형눌림목, RVOL급증(A), 20일고점돌파
```

**일반 매수 등급:**
```
[스윙 포착] KOSDAQ | 에코프로비엠(247540)
등급: 매수
예측유형: 재료 (64%)
...
```

---

## 6. 미변경 항목 (현행 유지)

| 항목 | 현재 값 | 유지 이유 |
|------|--------|----------|
| PMAT_STRICT / PMAT_RELAX | 0.60 / 0.60 | 데이터 검증 없이 변경 시 추천 수 급감 위험 |
| ATR_TARGET_MULT | 2.8x | 평균 수익률 12.59%와 잘 부합 |
| ATR_STOP_MULT | 1.9x | 현행 R:R 유지 |
| CAP_TARGET_PCT | 0.25 (25%) | 이미 충분 |
| RSI 범위 | 45~80 | — |
| MIN_RR_RATIO | 1.5 | — |

---

## 7. 구현 순서 (Do 단계)

```
1. CONST-01: 상수 8줄 추가
2. GRADE-01 (1): rankScore 직후 grade 판정 코드 추가
3. DOW-01: rankScore 계산 수정 (dowAdj 포함)
4. GRADE-01 (2): candidates.push에 grade 필드 추가
5. GRADE-01 (3): send 함수 메시지에 gradePrefix + 등급 줄 추가
6. HOLD-01: weeklyRecommendations 저장 시 holdDays 동적 계산
7. workflow JSON 재생성 (update_weekly_reporter.py 방식 동일)
```

---

## 8. 리스크 및 제약

| 리스크 | 설명 | 대응 |
|--------|------|------|
| `d` 변수 스코프 | line 329에서 선언된 `d`가 candidates 루프 내부에서 접근 가능한지 확인 필요 | 루프는 동일 함수 스코프 — 접근 가능 |
| 강매 등급 희소성 | PMAT 75%+ & 60점+ 동시 만족이 드물 수 있음 | 기준 조정 가능 (SCORE_STRONG 상수로 제어) |
| weekly_reporter 연동 | `grade` 필드 추가로 리포트 표기 개선 가능 (선택) | 본 구현 범위 외, 추후 독립 작업 |

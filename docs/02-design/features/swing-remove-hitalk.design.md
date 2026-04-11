# Design: swing-remove-hitalk

> Plan 문서: `docs/01-plan/features/swing-remove-hitalk.plan.md`
> 대상 파일: `swing_scanner_code.js`

---

## 1. 변경 목록 (총 7곳)

| ID | 위치 | 변경 유형 | 줄 수 변화 |
|----|------|---------|----------|
| C-01 | line 6 | 상수 값 수정 | 0 |
| C-02 | line 9~10 | 상수 2줄 제거 | -2 |
| C-03 | line 37 | 상수 1줄 제거 | -1 |
| C-04 | line 38 | 상수 값 수정 | 0 |
| C-05 | line 400~516 | HITALK 블록 전체 제거 | -117줄 |
| C-06 | line 1209~1235 | pMAT 의존 로직 수정 | -6줄 |
| C-07 | line 1378 | Telegram 메시지 수정 | -1줄 |

---

## 2. 상세 변경 명세

### C-01 — MIN_SCORE 상향 (line 6)

**현재:**
```javascript
  const MIN_SCORE = 70;         // 매수 등급 점수 기준 (60→70 상향, 수익 가능성 향상)
```

**변경 후:**
```javascript
  const MIN_SCORE = 80;         // 매수 등급 점수 기준 (pMAT 제거로 70→80 상향, 필터 강도 유지)
```

---

### C-02 — PMAT 상수 2개 제거 (line 9~10)

**현재:**
```javascript
  const PMAT_STRICT = 0.65;     // 매수 등급 PMAT 기준 (0.60→0.65 상향)
  const PMAT_RELAX = 0.60;      // 관심 등급 PMAT 기준 (최저 진입선)
```

**변경 후:**
```javascript
  // (PMAT_STRICT, PMAT_RELAX 제거 — HITALK 모델 제거로 불필요)
```

> 단순 삭제. 주석 1줄 남겨 의도 명시.

---

### C-03 — PMAT_STRONG 상수 제거 (line 37)

**현재:**
```javascript
  const PMAT_STRONG = 0.75;       // 강매 등급 PMAT 기준 (강매 등급 평균 30.34%)
```

**변경 후:** 해당 줄 삭제 (comment block 유지)

---

### C-04 — SCORE_STRONG 상향 (line 38)

**현재:**
```javascript
  const SCORE_STRONG = 100;       // 강매 등급 점수 기준
```

**변경 후:**
```javascript
  const SCORE_STRONG = 120;       // 강매 등급 점수 기준 (pMAT 제거로 100→120 상향)
```

---

### C-05 — HITALK 블록 전체 제거 (line 400~516)

**현재 (117줄):**
```javascript
  // ===== HiTalk Setup Models =====
  const HITALK_UP_MODEL = { ... };   // line 401 (대용량 JSON)
  const HITALK_MAT_MODEL = { ... };  // line 402 (대용량 JSON)
  const HITALK_SETUP_CFG = { ... };  // line 403
  const hitalkSigmoid = (x) => ...;  // line 404
  const hitalkDot = (w, x) => ...;   // line 405
  const hitalkStandardize = ...;     // line 406~412
  const hitalkPredictBin = ...;      // line 413~417
  const hitalkSma = ...;             // line 418~432
  const hitalkRsi14 = ...;           // line 433~452
  const hitalkFeaturesFromDaily = ...; // line 453~508
  const hitalkScoreSetups = ...;     // line 509~515
  // ===== /HiTalk Setup Models =====  // line 516
```

**변경 후:** 해당 블록 전체 삭제 (line 400~516, 117줄)

---

### C-06 — pMAT 의존 로직 수정 (line 1209~1235)

**현재:**
```javascript
        // HiTalk AI 모델 (daily features 전용)
        const setup = hitalkScoreSetups(closeD, highD, lowD, volD, dIdx);
        const pMAT = setup.pMAT;

        if (pMAT < PMAT_RELAX) return;

        const strictPass = (pMAT >= PMAT_STRICT) && (score >= MIN_SCORE);
        const relaxedPass = (pMAT >= PMAT_RELAX) && (score >= RELAX_SCORE);
        if (!strictPass) signals.push('완화');

        // 등급 판정 (수익 발생 가능성 기반 3단계 분류)
        // 강매: PMAT≥75% & score≥100 → 30.34% avg (데이터 근거)
        // 매수: PMAT≥65% & score≥70 → 중상급 수익 가능성
        // 관심: PMAT≥60% & score≥60 → 기본 진입 (2일 단기)
        const isStrong = (pMAT >= PMAT_STRONG) && (score >= SCORE_STRONG);
        const grade = isStrong ? '강매'
                    : strictPass ? '매수'
                    : '관심';
        if (grade === '관심') return; // 관심 등급 미발송 (수익 가능성 낮은 구간 차단)
        // 요일별 rankScore 보정 (d = kst.getUTCDay(), 상단에서 선언됨)
        const dowAdj = (d === 4) ? DOW_BONUS_THU     // 목요일 +3
                     : (d === 3) ? DOW_BONUS_WED     // 수요일 +2
                     : (d === 5) ? -DOW_PENALTY_FRI  // 금요일 -5
                     : 0;
        const rankScore = pMAT * 100 + score + dowAdj;
        const predType = '재료';
        const predProb = pMAT;
```

**변경 후:**
```javascript
        // 등급 판정 (기술 점수 기반 3단계 분류)
        // 강매: score≥120 → 고강도 기술 신호 집중
        // 매수: score≥80  → 표준 기술 신호
        // 관심: score≥60  → 기본 진입 (2일 단기)
        const strictPass = score >= MIN_SCORE;
        const relaxedPass = score >= RELAX_SCORE;
        if (!strictPass) signals.push('완화');

        const isStrong = score >= SCORE_STRONG;
        const grade = isStrong ? '강매'
                    : strictPass ? '매수'
                    : '관심';
        if (grade === '관심') return; // 관심 등급 미발송
        // 요일별 rankScore 보정 (d = kst.getUTCDay(), 상단에서 선언됨)
        const dowAdj = (d === 4) ? DOW_BONUS_THU     // 목요일 +3
                     : (d === 3) ? DOW_BONUS_WED     // 수요일 +2
                     : (d === 5) ? -DOW_PENALTY_FRI  // 금요일 -5
                     : 0;
        const rankScore = score + dowAdj;
        const predType = null;
        const predProb = null;
```

**변경 요점:**
- `hitalkScoreSetups()` 호출 제거 (3줄)
- `if (pMAT < PMAT_RELAX) return;` 제거 (1줄) — line 1207의 `score < RELAX_SCORE` 체크가 대신 필터
- `strictPass` / `relaxedPass` → score 단독 조건
- `isStrong` → score 단독 조건
- `rankScore` → `pMAT * 100` 제거
- `predType = null`, `predProb = null`

---

### C-07 — Telegram 메시지 predType 줄 제거 (line 1378)

**현재:**
```javascript
      '예측유형: ' + (c.predType || 'N/A') + (c.predProb ? ' (' + Math.round(c.predProb * 100) + '%)' : '') + NL +
```

**변경 후:** 해당 줄 전체 삭제

> predType/predProb 모두 null이므로 `예측유형: N/A` 가 표시되는 것 방지.

---

## 3. 변경 전/후 시나리오 비교

### 시나리오 A — score=85점, 수요일

| 항목 | 변경 전 | 변경 후 |
|------|--------|--------|
| pMAT 계산 | hitalkScoreSetups() 호출 | 없음 |
| strictPass | pMAT≥0.65 AND 85≥70 | **85≥80 → true** |
| grade | pMAT에 따라 결정 | `매수` |
| rankScore | pMAT×100 + 85 + 2 | **85 + 2 = 87** |
| Telegram | `예측유형: 재료 (72%)` 줄 포함 | 해당 줄 없음 |

### 시나리오 B — score=75점

| 항목 | 변경 전 | 변경 후 |
|------|--------|--------|
| strictPass | pMAT≥0.65 AND 75≥70 → pMAT 의존 | **75≥80 → false (relaxedPass=true)** |
| grade | pMAT에 따라 매수 또는 관심 | `관심` → return (미발송) |
| 결과 | pMAT 높으면 발송 | **발송 안됨** (점수 부족으로 차단 강화) |

### 시나리오 C — score=125점 (강매)

| 항목 | 변경 전 | 변경 후 |
|------|--------|--------|
| isStrong | pMAT≥0.75 AND 125≥100 → pMAT 의존 | **125≥120 → true** |
| grade | pMAT 낮으면 매수로 강등 | `강매` (점수 충족 시 확실히 강매) |
| rankScore | pMAT×100 + 125 + dowAdj | **125 + dowAdj** |

---

## 4. 영향 없는 항목 (변경 없음)

| 항목 | 유지 이유 |
|------|---------|
| RSI 45~80 범위 | 기술 지표, HITALK 무관 |
| ADX ≥ 20 | 기술 지표, HITALK 무관 |
| RVOL ≥ 1.0x 기준 | 기술 지표, HITALK 무관 |
| N자형 눌림목 +40점 등 패턴 점수 | 점수 체계 유지 |
| DOW_BONUS/PENALTY 요일 보정 | 유지 |
| HOLD_STRONG/NORMAL/WEAK | grade 판정 결과 기반, 유지 |
| ATR 손절/목표 계산 | HITALK 무관 |
| weekly_reporter_code.js | 본 변경 범위 외 |

---

## 5. 구현 순서

```
1. C-02: line 9~10 PMAT_STRICT, PMAT_RELAX 제거 (+ 주석 1줄)
2. C-03: line 37 PMAT_STRONG 줄 제거
3. C-01: line 6 MIN_SCORE 70 → 80
4. C-04: line 38 SCORE_STRONG 100 → 120
5. C-05: line 400~516 HITALK 블록 117줄 제거
6. C-06: line 1209~1235 pMAT 로직 교체
7. C-07: line 1378 predType 메시지 줄 삭제
```

> **순서 근거:** 상수 먼저 정리 → 대형 블록 제거 → 로직 수정 → 메시지 수정.
> 각 단계별 저장 후 문법 오류 없는지 확인.

---

## 6. 리스크 체크

| 항목 | 확인 결과 |
|------|---------|
| `hitalkScoreSetups` 다른 곳 참조 여부 | line 1210 단 1곳만 사용 — 안전 |
| `pMAT` 변수 다른 곳 사용 여부 | line 1211~1235 내부만 — 안전 |
| `PMAT_STRICT/RELAX/STRONG` 다른 곳 사용 | line 1213~1223 내부만 — 안전 |
| `predType/predProb` candidates.push 포함 여부 | line 1263에 포함됨 → null로 전달, 메시지에서 제거하면 OK |
| `relaxedPass` 변수 candidates.push 이후 사용 여부 | `strictPass`, `relaxedPass`는 holdDays 계산에 사용됨 (line 1413~1414) — 변경 후에도 유지됨 |

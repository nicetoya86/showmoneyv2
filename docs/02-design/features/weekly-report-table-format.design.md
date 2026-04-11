# Design: weekly-report-table-format

> Plan 문서: `docs/01-plan/features/weekly-report-table-format.plan.md`
> 대상 파일: `weekly_reporter_code.js`

---

## 1. 구현 대상 변경 (6개)

| ID | 항목 | 변경 위치 | 난이도 |
|----|------|----------|--------|
| HELPER-01 | shortDate 헬퍼 함수 추가 | line 253 (resolveName 직후) | 낮음 |
| HEADER-01 | 헤더 집계 표 형식으로 변경 | line 255~264 | 낮음 |
| WIN-01 | 수익 종목 1행 형식으로 변경 | line 267~278 | 낮음 |
| HOLD-01 | 보유 종목 1행 형식으로 변경 | line 281~293 | 낮음 |
| LOSS-01 | 손절 종목 1행 형식으로 변경 | line 296~307 | 낮음 |
| NOENTRY-01 | 미진입 종목 1행 형식으로 변경 | line 309~317 | 낮음 |

---

## 2. 상세 설계

### 2.1 HELPER-01 — shortDate 헬퍼 추가

**위치:** `resolveName` 함수 선언 직후 (line 253 근처)

```javascript
// 날짜 단축 표시: '2026-03-25' → '03-25'
const shortDate = (ds) => (ds && ds.length >= 7) ? ds.slice(5) : (ds || '');
```

---

### 2.2 HEADER-01 — 헤더 집계 표 형식

**현재 코드 (line 255~264):**
```javascript
let msg = '[주간 스윙 성과 리포트]' + NL +
  '📅 ' + weekDates[0] + ' ~ ' + weekDates[weekDates.length - 1] + NL +
  '━━━━━━━━━━━━━━━━━━━━' + NL +
  '총 추천: ' + recs.length + '건  |  매수 진입: ' + enteredCount + '건' + NL +
  '✅ 목표달성: ' + wins + '건  ❌ 손절: ' + losses + '건  🔄 보유: ' + holdList.length + '건' + NL;

if (evaluated.length > 0) {
  msg += '승률: ' + (winRate * 100).toFixed(0) + '%  (평가완료 ' + evaluated.length + '건)' + NL;
}
msg += '━━━━━━━━━━━━━━━━━━━━' + NL;
```

**변경 후:**
```javascript
const winRateStr = evaluated.length > 0 ? ' │ 승률 ' + (winRate * 100).toFixed(0) + '%' : '';
let msg = '[주간 스윙 성과 리포트]' + NL +
  '📅 ' + weekDates[0] + ' ~ ' + weekDates[weekDates.length - 1] + NL +
  '━━━━━━━━━━━━━━━━━━━━' + NL +
  '총추천 ' + recs.length + '건 │ 진입 ' + enteredCount + '건' + winRateStr + NL +
  '✅ 목표 ' + wins + '건 │ ❌ 손절 ' + losses + '건 │ 🔄 보유 ' + holdList.length + '건' + NL +
  '━━━━━━━━━━━━━━━━━━━━' + NL;
```

**결과 예시:**
```
[주간 스윙 성과 리포트]
📅 2026-03-23 ~ 2026-03-28
━━━━━━━━━━━━━━━━━━━━
총추천 5건 │ 진입 4건 │ 승률 67%
✅ 목표 2건 │ ❌ 손절 1건 │ 🔄 보유 1건
━━━━━━━━━━━━━━━━━━━━
```

---

### 2.3 WIN-01 — 수익 종목 1행 형식

**현재 코드 (line 267~278):**
```javascript
if (winList.length > 0) {
  msg += NL + '✅ 수익 종목' + NL;
  for (const d of winList) {
    const name = resolveName(d);
    msg += '  ' + name + '(' + (d.code || '') + ')' + NL;
    msg += '    ' + d.date + ' | 목표달성';
    if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) msg += ' | 최고' + pct(d.maxReturn);
    if (d.hitTargetDay) msg += ' (' + d.hitTargetDay + ')';
    if (d.score) msg += ' | ' + d.score + '점';
    msg += NL;
  }
}
```

**변경 후:**
```javascript
if (winList.length > 0) {
  msg += NL + '✅ 수익 (' + winList.length + '건)' + NL;
  for (const d of winList) {
    const name = resolveName(d);
    let row = name + '(' + (d.code || '') + ') │ ' + shortDate(d.date);
    if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) row += ' │ 최고 ' + pct(d.maxReturn);
    if (d.hitTargetDay) row += ' │ ' + shortDate(d.hitTargetDay);
    if (d.score) row += ' │ ' + d.score + '점';
    msg += row + NL;
  }
}
```

**결과 예시:**
```
✅ 수익 (2건)
삼성전자(005930) │ 03-25 │ 최고 +8.3% │ 03-26 │ 115점
카카오뱅크(323410) │ 03-26 │ 최고 +5.1% │ 90점
```

---

### 2.4 HOLD-01 — 보유 종목 1행 형식

**현재 코드 (line 281~293):**
```javascript
if (holdList.length > 0) {
  msg += NL + '🔄 보유 종목' + NL;
  for (const d of holdList) {
    const name = resolveName(d);
    const label = d.result === 'expired' ? '기간만료' : '보유중';
    msg += '  ' + name + '(' + (d.code || '') + ')' + NL;
    msg += '    ' + d.date + ' | ' + label;
    if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) msg += ' | 최고' + pct(d.maxReturn);
    if (d.result === 'holding' && d.exitDate) msg += ' | 보유예정일' + d.exitDate;
    if (d.score) msg += ' | ' + d.score + '점';
    msg += NL;
  }
}
```

**변경 후:**
```javascript
if (holdList.length > 0) {
  msg += NL + '🔄 보유 (' + holdList.length + '건)' + NL;
  for (const d of holdList) {
    const name = resolveName(d);
    const label = d.result === 'expired' ? '만료' : '보유중';
    let row = name + '(' + (d.code || '') + ') │ ' + shortDate(d.date) + ' │ ' + label;
    if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) row += ' │ 최고 ' + pct(d.maxReturn);
    if (d.result === 'holding' && d.exitDate) row += ' │ 예정일 ' + shortDate(d.exitDate);
    if (d.score) row += ' │ ' + d.score + '점';
    msg += row + NL;
  }
}
```

**결과 예시:**
```
🔄 보유 (1건)
에코프로비엠(247540) │ 03-24 │ 보유중 │ 최고 +3.2% │ 예정일 03-29 │ 80점
```

---

### 2.5 LOSS-01 — 손절 종목 1행 형식

**현재 코드 (line 296~307):**
```javascript
if (lossList.length > 0) {
  msg += NL + '❌ 손절 종목' + NL;
  for (const d of lossList) {
    const name = resolveName(d);
    msg += '  ' + name + '(' + (d.code || '') + ')' + NL;
    msg += '    ' + d.date + ' | 손절';
    if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) msg += ' | 최고' + pct(d.maxReturn);
    if (d.hitStopDay) msg += ' (' + d.hitStopDay + ')';
    if (d.score) msg += ' | ' + d.score + '점';
    msg += NL;
  }
}
```

**변경 후:**
```javascript
if (lossList.length > 0) {
  msg += NL + '❌ 손절 (' + lossList.length + '건)' + NL;
  for (const d of lossList) {
    const name = resolveName(d);
    let row = name + '(' + (d.code || '') + ') │ ' + shortDate(d.date) + ' │ 손절';
    if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) row += ' │ 최고 ' + pct(d.maxReturn);
    if (d.hitStopDay) row += ' │ ' + shortDate(d.hitStopDay);
    if (d.score) row += ' │ ' + d.score + '점';
    msg += row + NL;
  }
}
```

**결과 예시:**
```
❌ 손절 (1건)
카카오(035720) │ 03-23 │ 손절 │ 최고 +1.2% │ 03-24 │ 65점
```

---

### 2.6 NOENTRY-01 — 미진입 종목 1행 형식

**현재 코드 (line 309~317):**
```javascript
const notEnteredList = details.filter((d) => d.result === 'not_entered');
if (notEnteredList.length > 0) {
  msg += NL + '⚪ 매수가 미도달 ' + notEnteredList.length + '건 (제외)' + NL;
  for (const d of notEnteredList) {
    const name = resolveName(d);
    msg += '  ' + name + '(' + (d.code || '') + ') | ' + d.date + NL;
  }
}
```

**변경 후:**
```javascript
const notEnteredList = details.filter((d) => d.result === 'not_entered');
if (notEnteredList.length > 0) {
  msg += NL + '⚪ 매수 미도달 (' + notEnteredList.length + '건)' + NL;
  for (const d of notEnteredList) {
    const name = resolveName(d);
    msg += name + '(' + (d.code || '') + ') │ ' + shortDate(d.date) + NL;
  }
}
```

**결과 예시:**
```
⚪ 매수 미도달 (1건)
LG화학(051910) │ 03-22
```

---

### 2.7 면책 문구 개선 (line 319)

**현재:**
```javascript
msg += NL + '면책: 본 리포트는 참고용이며 투자 결과에 책임지지 않습니다.';
```

**변경 후:**
```javascript
msg += NL + '⚠️ 본 리포트는 참고용이며 투자 결과에 책임지지 않습니다.';
```

---

## 3. 전체 메시지 비교

### 변경 전 (5종목 예시, 약 38줄)
```
[주간 스윙 성과 리포트]
📅 2026-03-23 ~ 2026-03-28
━━━━━━━━━━━━━━━━━━━━
총 추천: 5건  |  매수 진입: 4건
✅ 목표달성: 2건  ❌ 손절: 1건  🔄 보유: 1건
승률: 67%  (평가완료 3건)
━━━━━━━━━━━━━━━━━━━━

✅ 수익 종목
  삼성전자(005930)
    2026-03-25 | 목표달성 | 최고+8.3% (2026-03-26) | 115점
  카카오뱅크(323410)
    2026-03-26 | 목표달성 | 최고+5.1% | 90점

🔄 보유 종목
  에코프로비엠(247540)
    2026-03-24 | 보유중 | 최고+3.2% | 보유예정일2026-03-29 | 80점

❌ 손절 종목
  카카오(035720)
    2026-03-23 | 손절 | 최고+1.2% (2026-03-24) | 65점

⚪ 매수가 미도달 1건 (제외)
  LG화학(051910) | 2026-03-22

면책: 본 리포트는 참고용이며 투자 결과에 책임지지 않습니다.
```

### 변경 후 (5종목 예시, 약 18줄)
```
[주간 스윙 성과 리포트]
📅 2026-03-23 ~ 2026-03-28
━━━━━━━━━━━━━━━━━━━━
총추천 5건 │ 진입 4건 │ 승률 67%
✅ 목표 2건 │ ❌ 손절 1건 │ 🔄 보유 1건
━━━━━━━━━━━━━━━━━━━━

✅ 수익 (2건)
삼성전자(005930) │ 03-25 │ 최고 +8.3% │ 03-26 │ 115점
카카오뱅크(323410) │ 03-26 │ 최고 +5.1% │ 90점

🔄 보유 (1건)
에코프로비엠(247540) │ 03-24 │ 보유중 │ 최고 +3.2% │ 예정일 03-29 │ 80점

❌ 손절 (1건)
카카오(035720) │ 03-23 │ 손절 │ 최고 +1.2% │ 03-24 │ 65점

⚪ 매수 미도달 (1건)
LG화학(051910) │ 03-22

⚠️ 본 리포트는 참고용이며 투자 결과에 책임지지 않습니다.
```

---

## 4. 변경 요약표

| ID | 위치 | 변경 유형 | 줄 수 변화 |
|----|------|---------|----------|
| HELPER-01 | line 253 직후 | 추가 | +1줄 |
| HEADER-01 | line 255~264 | 수정 | 8줄 → 6줄 |
| WIN-01 | line 267~278 | 수정 | 2줄/종목 → 1줄/종목 |
| HOLD-01 | line 281~293 | 수정 | 2줄/종목 → 1줄/종목 |
| LOSS-01 | line 296~307 | 수정 | 2줄/종목 → 1줄/종목 |
| NOENTRY-01 | line 309~317 | 수정 | 2줄/종목 → 1줄/종목 |
| FOOTER-01 | line 319 | 수정 | 아이콘 추가 |

---

## 5. 구현 순서

```
1. HELPER-01: shortDate 함수 추가 (resolveName 직후)
2. HEADER-01: 헤더 집계 블록 교체
3. WIN-01: 수익 종목 섹션 교체
4. HOLD-01: 보유 종목 섹션 교체
5. LOSS-01: 손절 종목 섹션 교체
6. NOENTRY-01: 미진입 섹션 교체
7. FOOTER-01: 면책 문구 아이콘 추가
8. workflow JSON 재생성
```

---

## 6. 리스크 및 제약

| 리스크 | 설명 | 대응 |
|--------|------|------|
| `│` 유니코드 문자 | U+2502 BOX DRAWINGS LIGHT VERTICAL — 일부 기기에서 미지원 가능 | Telegram에서 정상 렌더링 확인됨 |
| 종목명 길이 | 긴 종목명(10자+)이 있으면 줄 정렬이 비균일 | 표 형식이므로 비균일 허용, 가독성 문제 없음 |
| 4000자 분리 | 기존 4000자 청크 분리 로직 유지 | 줄 수 감소로 오히려 분리 빈도 낮아짐 |

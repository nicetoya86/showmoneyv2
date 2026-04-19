# Gap Analysis: swing-macd-rsi-risk-filter

## 분석 개요

| 항목 | 내용 |
|------|------|
| Feature | swing-macd-rsi-risk-filter |
| Plan 문서 | `docs/01-plan/features/swing-macd-rsi-risk-filter.plan.md` |
| 구현 파일 | `swing_scanner_code.js` |
| 분석 일자 | 2026-04-19 |
| 분석 기준 | Plan 섹션 4.2 체크리스트 (6개 항목, 22개 서브항목) |

---

## 전체 결과

| 구분 | 결과 | 상태 |
|------|------|------|
| Plan vs 구현 일치율 | **100%** | PASS |
| **최종 Match Rate** | **100%** | **PASS** |

---

## Plan 섹션 4.2 항목별 검증 (6개 항목)

### 1. CONST-01: 신규 상수 추가

| 요건 (Plan) | 구현 (코드) | 상태 |
|-------------|------------|------|
| `RSI_RISING_BONUS = 10` 신규 상수 | Line 66: `const RSI_RISING_BONUS   = 10;` | ✅ PASS |
| `DELIST_CONSEC_DOWN = 5` 신규 상수 | Line 67: `const DELIST_CONSEC_DOWN = 5;` | ✅ PASS |
| `DELIST_VOL_DROP = 0.3` 신규 상수 | Line 68: `const DELIST_VOL_DROP    = 0.3;` | ✅ PASS |

```javascript
// Line 65-69
const RSI_RISING_BONUS   = 10;
const DELIST_CONSEC_DOWN = 5;
const DELIST_VOL_DROP    = 0.3;
```

---

### 2. THEME-01: 테마주 필터 기본값 활성화

| 요건 | 구현 | 상태 |
|------|------|------|
| `themeFilterMode` 기본값 `'off'` → `'on'` | Line 426: `String(bl.themeFilterMode \|\| 'on')` | ✅ PASS |

```javascript
// Line 426
const themeFilterMode = String(bl.themeFilterMode || 'on').toLowerCase(); // 2026-04-19: 기본값 'on' 활성화
```

**동작:** `bl.themeFilterMode`가 명시 설정 없으면 `'on'`으로 작동. `bl.themeCodes`가 빈 경우 `themeSet`이 비어 안전하게 미차단.

---

### 3. DELIST-01: 상장폐지 위험 패턴 차단

| 요건 | 구현 | 상태 |
|------|------|------|
| `consecDown` 5일 연속 하락 루프 (`dIdx-4 ~ dIdx`) | Lines 1003-1006: 정확히 구현 | ✅ PASS |
| `closeD[ci] < closeD[ci-1]` 하락 판정 | Line 1005: 동일 조건 | ✅ PASS |
| `recentVol` = 최근 4일 평균 (`dIdx-3 ~ dIdx`) | Line 1007: `recentVol4` (변수명 명확화) | ✅ PASS |
| `prevVol` = 직전 5일 평균 (`dIdx-8 ~ dIdx-3`) | Line 1008: `prevVol5` (변수명 명확화) | ✅ PASS |
| `volDropped = prevVol > 0 && ratio < DELIST_VOL_DROP` | Line 1009: 동일 로직 | ✅ PASS |
| `consecDown >= DELIST_CONSEC_DOWN && volDropped → return` | Line 1010: 정확히 구현 | ✅ PASS |

```javascript
// Lines 1001-1010
let consecDown = 0;
for (let ci = dIdx - 4; ci <= dIdx; ci++) {
  if (ci > 0 && closeD[ci] < closeD[ci - 1]) consecDown++;
}
const recentVol4 = volD.slice(Math.max(0, dIdx - 3), dIdx + 1).reduce((a, b) => a + b, 0) / 4;
const prevVol5   = volD.slice(Math.max(0, dIdx - 8), dIdx - 3).reduce((a, b) => a + b, 0) / 5;
const volDropped = prevVol5 > 0 && (recentVol4 / prevVol5) < DELIST_VOL_DROP;
if (consecDown >= DELIST_CONSEC_DOWN && volDropped) return;
```

---

### 4. RSI-01: RSI 방향성 추가 + 보너스 확장

| 요건 | 구현 | 상태 |
|------|------|------|
| `rsi5DayAgo = calcRSI14(closeD, Math.max(0, dIdx-5))` | Line 1088: 동일 호출 | ✅ PASS |
| `rsiRising = Number.isFinite(rsi5DayAgo) && rsi14Val > rsi5DayAgo` | Line 1089: 동일 조건 | ✅ PASS |
| `rsiRising && rsi14Val >= 50 → score += RSI_RISING_BONUS` | Line 1091: 정확히 구현 | ✅ PASS |
| `signals.push('RSI상승모멘텀')` 신호 레이블 | Line 1091: 동일 | ✅ PASS |
| 골든존 보너스 10 → 5점 (축소, 방향성 보너스와 합산) | Line 1092: `score += 5` | ✅ PASS |

```javascript
// Lines 1086-1092
const rsi5DayAgo = calcRSI14(closeD, Math.max(0, dIdx - 5));
const rsiRising  = Number.isFinite(rsi5DayAgo) && rsi14Val > rsi5DayAgo;
if (Number.isFinite(rsi14Val)) {
  if (rsiRising && rsi14Val >= 50) { score += RSI_RISING_BONUS; signals.push('RSI상승모멘텀'); }
  if (rsi14Val >= 65 && rsi14Val <= 75) { score += 5; signals.push('RSI골든존'); }
}
```

---

### 5. MACD-01: MACD 연속 하락 → 강매 제외 차단

| 요건 | 구현 | 상태 |
|------|------|------|
| `macdNegativeTrend = hist<0 && histPrev<0` | Lines 1245-1246: 동일 조건 (`Number.isFinite` 포함) | ✅ PASS |
| `macdNegativeTrend && grade !== '강매' → return` | Line 1247: 정확히 구현 | ✅ PASS |
| OBV-01 필터 이후 등급 판정 후 적용 | Line 1242 OBV-01 바로 다음에 위치 | ✅ PASS |

```javascript
// Lines 1243-1247
const macdNegativeTrend = Number.isFinite(macdResult.hist) && macdResult.hist < 0
                        && Number.isFinite(macdResult.histPrev) && macdResult.histPrev < 0;
if (macdNegativeTrend && grade !== '강매') return;
```

---

### 6. JSON-01: 워크플로우 JSON 재생성

| 요건 | 구현 | 상태 |
|------|------|------|
| 워크플로우 JSON 재생성 | `workflow_FINAL_20260419_152529_swing_macd_rsi_risk_filter.json` 생성 | ✅ PASS |
| Swing Scanner 노드 코드 업데이트 | `functionCode` 파라미터에 최신 코드 적용 (66,088 chars) | ✅ PASS |

---

## Match Rate 계산

| 항목 | 서브항목 수 | PASS | FAIL |
|------|------------|------|------|
| CONST-01 | 3 | 3 | 0 |
| THEME-01 | 1 | 1 | 0 |
| DELIST-01 | 6 | 6 | 0 |
| RSI-01 | 5 | 5 | 0 |
| MACD-01 | 3 | 3 | 0 |
| JSON-01 | 2 | 2 | 0 |
| **합계** | **20** | **20** | **0** |

**Match Rate: 20/20 = 100%**

---

## 구현 위치 요약

| 항목 | 위치 | 설명 |
|------|------|------|
| CONST-01 | Lines 65-68 | 상수 블록 끝에 신규 섹션 추가 |
| THEME-01 | Line 426 | blacklist 초기화 영역 |
| DELIST-01 | Lines 1001-1010 | RSI 필터([2]) 직후 — 조기 차단 위치 |
| RSI-01 | Lines 1086-1092 | 점수 계산 [NEW-3] 영역 |
| MACD-01 | Lines 1243-1247 | OBV-01 필터([OBV-01]) 직후 |
| JSON-01 | 파일시스템 | `workflow_FINAL_20260419_152529_swing_macd_rsi_risk_filter.json` |

---

## 스코어링 변화 검증

**시나리오 A — MACD 연속 하락 종목 차단 확인:**
```
hist < 0 && histPrev < 0 → macdNegativeTrend = true
grade ≠ '강매' → return (차단)
기존: -10점 패널티 후 통과 가능 → 개선: 하드 차단
```

**시나리오 B — RSI 상승 중 보너스 확인:**
```
RSI 5일 전 = 55, 현재 = 62 (상승 중, >= 50)
→ +10 (RSI상승모멘텀)
RSI = 62 (골든존 아님) → +0
합계: +10 (기존 0에서 향상)
```

**시나리오 C — RSI 골든존 + 상승 중 (최대 보너스):**
```
RSI 5일 전 = 68, 현재 = 70 (상승 중, >= 50, 골든존)
→ +10 (RSI상승모멘텀) + 5 (RSI골든존) = +15
기존: +10 (골든존만) → 개선: +15
```

---

## 미구현 항목

없음. 모든 Plan 요건 구현 완료.

---

## 결론

- **Match Rate: 100%** (20/20) — Plan 요건 전항목 구현 완료
- 코드 변경 불필요
- 권장 다음 단계: `/pdca report swing-macd-rsi-risk-filter`

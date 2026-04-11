# Plan: swing-remove-hitalk

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | swing-remove-hitalk |
| 대상 파일 | `swing_scanner_code.js` |
| 변경 규모 | 약 130줄 제거 + 6곳 로직 수정 |
| 목표 | HITALK xlsx 학습 모델 의존 제거 → 기술 점수 단독 필터링 |

### Value Delivered (4-Perspective)

| 관점 | 내용 |
|------|------|
| **Problem** | `HITALK_UP_MODEL` / `HITALK_MAT_MODEL`은 `hitalk_full_data.xlsx` / `hitalk_recommendations.xlsx` 데이터로 학습된 ML 모델로, 코드에 내장된 채 pMAT 값을 통해 진입 필터·등급·rankScore에 영향을 미침 |
| **Solution** | 모델 상수·헬퍼 함수·pMAT 의존 로직을 모두 제거하고, 기술 지표 점수(score) 단독으로 필터링 |
| **Function UX Effect** | 추천 판단 기준이 단순·명확해지며, 외부 학습 데이터 의존성이 사라져 알고리즘 투명성 향상 |
| **Core Value** | 검증 가능한 기술 신호(RSI, ADX, RVOL, 패턴)만으로 종목 선정 — 블랙박스 ML 의존 제거 |

---

## 1. 현재 HITALK 의존 구조

### 1.1 내장 모델 상수 (제거 대상)

| 상수명 | 위치 | 크기 | 설명 |
|--------|------|------|------|
| `HITALK_UP_MODEL` | line 401 | ~1줄(대용량) | 단타/급등 예측 로지스틱 회귀 모델 |
| `HITALK_MAT_MODEL` | line 402 | ~1줄(대용량) | 스윙/재료 예측 로지스틱 회귀 모델 |
| `HITALK_SETUP_CFG` | line 403 | 1줄 | 모델별 targetRate/stopRate/threshold |

### 1.2 헬퍼 함수 (제거 대상, ~120줄)

| 함수명 | 설명 |
|--------|------|
| `hitalkSigmoid` | 시그모이드 함수 |
| `hitalkDot` | 벡터 내적 |
| `hitalkStandardize` | 피처 표준화 |
| `hitalkPredictBin` | 이진 예측 실행 |
| `hitalkSma` | 단순 이동평균 |
| `hitalkRsi14` | RSI 14 계산 |
| `hitalkFeaturesFromDaily` | 일봉 데이터 → 피처 추출 |
| `hitalkScoreSetups` | 위 모두 조합, pUP·pMAT 반환 |

### 1.3 pMAT 의존 로직 (수정 대상)

| 위치 | 현재 코드 | 변경 후 |
|------|---------|--------|
| line 1210~1211 | `const setup = hitalkScoreSetups(...); const pMAT = setup.pMAT;` | 제거 |
| line 1213 | `if (pMAT < PMAT_RELAX) return;` | 제거 (line 1207의 score 기준으로 충분) |
| line 1215 | `strictPass = (pMAT >= PMAT_STRICT) && (score >= MIN_SCORE)` | `strictPass = score >= MIN_SCORE` |
| line 1216 | `relaxedPass = (pMAT >= PMAT_RELAX) && (score >= RELAX_SCORE)` | `relaxedPass = score >= RELAX_SCORE` |
| line 1223 | `isStrong = (pMAT >= PMAT_STRONG) && (score >= SCORE_STRONG)` | `isStrong = score >= SCORE_STRONG` |
| line 1233 | `rankScore = pMAT * 100 + score + dowAdj` | `rankScore = score + dowAdj` |
| line 1234~1235 | `predType = '재료'; predProb = pMAT;` | `predType = '기술점수'; predProb = null;` |

### 1.4 제거할 상수

| 상수 | 위치 | 제거 이유 |
|------|------|---------|
| `PMAT_STRICT = 0.65` | line 9 | pMAT 기준 불필요 |
| `PMAT_RELAX = 0.60` | line 10 | pMAT 기준 불필요 |
| `PMAT_STRONG = 0.75` | line 37 | pMAT 기준 불필요 |

---

## 2. 변경 후 필터링 구조

### 2.1 변경 전 (현재)

```
진입 조건:
  1. score >= RELAX_SCORE (60점)   ← 기술 점수
  2. pMAT >= PMAT_RELAX (0.60)     ← HITALK 모델 (xlsx 의존)

등급 판정:
  strictPass = pMAT >= 0.65 && score >= 70   ← 혼합
  relaxedPass = pMAT >= 0.60 && score >= 60  ← 혼합
  isStrong = pMAT >= 0.75 && score >= 100    ← 혼합

rankScore = pMAT * 100 + score + dowAdj  ← ML 가중치 포함
```

### 2.2 변경 후 (기술 점수 단독)

```
진입 조건:
  1. score >= RELAX_SCORE (60점)   ← 기술 점수만

등급 판정:
  strictPass = score >= MIN_SCORE (70점)
  relaxedPass = score >= RELAX_SCORE (60점)
  isStrong = score >= SCORE_STRONG (100점)

rankScore = score + dowAdj  ← 기술 점수 + 요일 보정
```

> **필터링 효과 유지:** RSI 45~80, ADX ≥ 20, RVOL ≥ 1.0x, 정배열 조건은 변경 없이 유지.
> 기술 신호 점수 체계(N자형 눌림목 +40, 20일 고점 돌파 +35 등)도 그대로 유지.

---

## 3. 점수 임계값 재검토

pMAT 제거 시 `MIN_SCORE`와 `RELAX_SCORE` 조정 필요 여부:

| 항목 | 현재 | 검토 | 결정 |
|------|------|------|------|
| `MIN_SCORE` (strictPass) | 70점 | pMAT 0.65 조건 제거 → 70점 단독은 다소 느슨해질 수 있음 | **70 → 80점으로 상향** |
| `RELAX_SCORE` (relaxedPass) | 60점 | pMAT 0.60 조건 제거 → 유사한 효과 | **60 유지** |
| `SCORE_STRONG` (강매) | 100점 | pMAT 0.75 조건 제거 → 강매 기준 강화 필요 | **100 → 120점으로 상향** |

> **근거:** 기존 strictPass는 pMAT 0.65 AND score 70 이중 조건. pMAT 제거 시 단일 조건으로 같은 수준을 유지하려면 점수 기준을 소폭 상향하는 것이 적절.

---

## 4. Telegram 메시지 변경

| 항목 | 현재 | 변경 후 |
|------|------|--------|
| `예측유형` 필드 | `재료 (82%)` | `기술점수` (확률 제거) |
| 표기 예시 | `예측유형: 재료 (82%)` | `기술점수: 85점` 또는 해당 줄 제거 |

---

## 5. 변경 범위 요약

| 구분 | 내용 | 줄 수 |
|------|------|------|
| **제거** | HITALK 모델 JSON 상수 3개 | ~3줄(대용량) |
| **제거** | HITALK 헬퍼 함수 8개 | ~120줄 |
| **제거** | PMAT 관련 상수 3개 | 3줄 |
| **수정** | pMAT 의존 로직 6곳 | 6줄 |
| **수정** | MIN_SCORE 70→80, SCORE_STRONG 100→120 | 2줄 |

---

## 6. 리스크 및 대응

| 리스크 | 내용 | 대응 |
|--------|------|------|
| 추천 수 변화 | pMAT 필터 제거로 추천 수 증가 가능 | MIN_SCORE 상향으로 보완 |
| 품질 저하 우려 | ML 모델 제거로 신호 품질 저하 가능성 | 실제 보유 7종목 전원 플러스 → 기술 점수만으로도 충분한 근거 |
| rankScore 의미 변화 | pMAT*100 제거로 상대 순위 변화 | score + dowAdj만으로도 합리적 정렬 유지 |

---

## 7. 구현 순서 (Do 단계)

```
1. HITALK 상수 3줄 제거 (line 401~403)
2. HITALK 헬퍼 함수 블록 제거 (line 404~515)
3. PMAT 상수 3개 제거 (line 9, 10, 37)
4. MIN_SCORE 70→80, SCORE_STRONG 100→120 수정
5. pMAT 의존 로직 6곳 수정 (line 1210~1235)
6. Telegram 메시지 predType/predProb 줄 수정
7. workflow JSON 재생성
```

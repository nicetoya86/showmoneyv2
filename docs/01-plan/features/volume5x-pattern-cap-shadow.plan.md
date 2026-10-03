---
template: plan
version: 1.2
description: 거래량 5x 필터 + 패턴우선순위 일 2건 캡을 shadow 모드(발송 불변, 기록만)로 검증하는 계획
---

# volume5x-pattern-cap-shadow Planning Document

> **Summary**: 실제 발송은 그대로 두고, 추천 레코드에 rvol/발송시각을 기록한 뒤 주간 리포트에서 "거래량 5x 이상"·"일 2건 패턴우선순위 캡" 가상 코호트를 실발송과 나란히 비교한다.
>
> **Project**: showmoneyv2 (swing algo, n8n workflow `ScHaeFdneOoH1ZNZ`)
> **Author**: kevin
> **Date**: 2026-10-03
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 실측 승률 약 24%(확정 115건). 손절 78건 중 33건이 본전/수익 청산이라 어떤 필터가 실제로 도움 되는지 근거가 약하다. 패턴 캡(D>C>B>A)은 주간 편차가 커서(W1 17% / W2 75%) 단독 배포 불가, 거래량 필터는 라이브 증거가 오염돼 있다(아래 §1.2). |
| **Solution** | scanner는 `rvol`·`sentAt`만 추가 기록(발송 로직 무변경), weekly-reporter가 가상 코호트(5x 이상 / 일 2건 캡 / 둘의 교집합)를 사후 계산해 리포트 하단에 비교 표시. 2~3주 누적 후 게이트 기준으로 live 승격 여부 결정. |
| **Function/UX Effect** | 사용자가 받는 알림은 변화 없음. 주간 리포트에 "shadow 비교" 섹션이 추가된다. |
| **Core Value** | 과적합 위험이 있는 규칙을 실제 자금/알림에 적용하기 전에 새 데이터(out-of-sample)로 검증한다. 되돌릴 비용 0. |

---

## 1. Overview

### 1.1 Purpose

거래량 필터와 패턴 캡이 실제로 승률/기대값을 개선하는지, 발송 흐름을 건드리지 않고 검증한다.

### 1.2 Background (근거와 한계, 2026-10-03 세션)

| 근거 | 결과 | 신뢰도 |
|------|------|--------|
| 백테스트 2,686건 (2022~25, `backtest_out_swing_v2_with_features.json`, 진짜 `rvol_tier`) | **5x 이상** 승률이 4개 연도 모두 +4~7%p 높음, 학습(22~23)/검증(24~25)에서도 같은 방향. **3x 이상**은 학습에서만 효과, 검증에서 소멸 | 중 (효과 크기 작음, 백테스트 청산 모델≠라이브) |
| 라이브 W1+W2 (9/21~23, 9/28~10/2, 신규 129건) | 5x 이상 33% vs 미만 17% | **오염됨 → P0에서 재계산(§1.4)**: 실제 rvol 기준 26% vs 22%, 평균수익률은 +1.02% vs +1.54%로 뒤집힘. 필터 효과 소멸 |
| 패턴 캡 D>C>B>A, 일 2건 | W1 17%(6건), W2 75%(8건) — 합치면 14건 50% | 낮음 (표본 극소, 주간 편차 큼) |

**라이브 증거 오염 (확인됨)**: `weeklyRecommendations`에는 `signals.slice(0,3)`만 저장된다(`swing-scanner.src.js:1840`). 신호 push 순서가 패턴태그 → `복합C+D`/`복합A+B` → 거래량(1273~1281행)이라, 복합 신호가 붙은 종목은 거래량 태그가 잘려 나간다. 따라서 라이브 분석의 "거래량 신호 없음" 버킷에는 실제 rvol이 높은 복합 종목이 섞여 있고, "복합C+D가 나쁘다"와 "거래량이 낮으면 나쁘다"가 분리되지 않는다. 실제 rvol 값을 저장하지 않고 있다는 것이 이 문제의 뿌리다.

### 1.4 P0 결과 (2026-10-03): 실제 rvol 재계산 — 계획 방향 수정

방법: 129건 각각 Naver 일봉으로 스캐너 공식(`volD[dIdx]/avg(직전 20일)`, 추천일 이전 마지막 거래일 기준)대로 rvol 재계산. 태그가 보이는 93건 중 92건이 계산값과 일치(1건 불일치: LK삼양)해서 계산 신뢰 가능.

| 비교 | 결과 (승률 / 평균수익률) |
|------|--------------------------|
| rvol ≥5x vs <5x (전체) | 26% / +1.02% vs 22% / +1.54% — **평균은 5x 미만이 더 높음** |
| 주별 (≥5x vs <5x) | W1 24% vs 11%, W2 27% vs 30% (평균 +1.41% vs +2.95%) — **W2에서 뒤집힘** |
| 티어별 | 2x 15%, 3x 29%, 5x 21%, 8x+ 29% — 단조 증가 아님(5x 티어가 오히려 약함) |
| rvol ≥3x vs <3x | 26% vs 15%이나 W2에서 소멸(28% vs 29%), <3x 표본 20건 |
| **복합 신호 있음 vs 없음** | **12% / -0.72% (n=26) vs 28% / +1.77% (n=89)** — W1 11% vs 21%, W2 12% vs 34%로 **두 주 모두 같은 방향** |
| 복합 제외 후 ≥5x vs <5x | 32% / +1.78% vs 23% / +1.75% — 승률만 +9%p, 평균 차이 없음 |

해석:
- 라이브에서 본 "거래량 필터 효과"의 대부분은 **복합C+D 종목(26/28이 5x 이상)이 "거래량 낮음" 버킷에 잘못 들어간 착시**였다. 진짜 신호는 거래량이 아니라 **복합 신호 유무**다.
- 복합C+D는 9/26에 점수 -10 페널티가 적용됐지만(`score` 재조정) 여전히 발송되고 있고(W2에서도 19건, 승률 12%), 발송 자체를 막지는 않는다.
- 한계: 복합 효과는 라이브 2주(n=26)뿐이다. 백테스트 거래 레코드에는 신호 태그가 저장돼 있지 않아 독립 검증 불가(재실행하려면 `backtest/swing_signal_engine.py`가 만드는 `signals`를 trade에 저장해야 함 — 비용 큼, 이번 범위 밖).

**계획 수정**: 거래량 5x 코호트는 "참고용"으로 강등(백테스트 4년은 약하게 지지, 라이브는 미지지). **복합 제외 코호트를 주 후보로 추가**한다. 코호트는 shadow에서 모두 동시에 측정하므로 비용 증가는 거의 없다.

### 1.3 Related Documents

- 메모리: `swing-algo-pattern-priority-selection-proposal-2026-09-26`, `swing-algo-report-deepdive-and-fixes-2026-09-26`
- 코드: `src/swing-scanner.src.js` (선정 1447~1486행, 발송/기록 1802~1847행, 신호 1266~1281행), `src/weekly-reporter.src.js`
- 배포 선례: `scripts/patch_*.py --apply` (n8n PUT), `scripts/verify_*.js` (self-check)

---

## 2. Scope

### 2.1 In Scope

- [x] **P0** 라이브 W1+W2 129건의 실제 rvol 재계산 → 오염 없이 5x 필터/복합C+D 효과 재평가 (완료, §1.4: 5x 효과 소멸, 복합 신호가 실제 변수)
- [ ] **P1** scanner: 추천 레코드에 `rvol`(숫자), `sentAt`(ISO) 추가 기록. 발송 대상/순서/수량 무변경
- [ ] **P2** weekly-reporter: shadow 코호트 계산 + 리포트 하단 비교 섹션
- [ ] **P3** self-check 스크립트 1개 + patch 스크립트(`--apply` 없으면 dry-run)
- [ ] **P4** 2~3주 관찰 후 게이트 판정

### 2.2 Out of Scope

- 실제 발송 규칙 변경(필터/캡 live 적용) — 게이트 통과 후 별도 plan
- 트레일링 BE 상향 구간 튜닝 (별도 plan)
- KSS해운형 분류 버그 패치 (`weekly-reporter.src.js:312-313`, 1건, 별도 최소 패치)
- A눌림목 우선순위 재조정 (표본 부족)
- 새 외부 라이브러리, 새 파일 추가 최소화 (기존 파일 수정 위주)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 발송 시 추천 레코드에 `rvol`(소수 2자리) 저장. 기존 필드/발송 흐름 불변. (`sentAt`/`composite`는 불필요 — 캡은 date·patternType·score로, 복합은 `signals`(앞 3개 안에 항상 포함)로 판정 가능. Design v0.1 결정) | High | Pending |
| FR-02 | 리포트에 코호트 표시: ①복합 제외(`!composite`) ②`rvol>=5`(참고용) ③일 2건 캡(패턴 D>C>B>A, 동순위 score) ④①∩③ — 각 코호트별 n/승/부분/손절/승률/평균수익률 + 전체(실발송) 대비 차이 | High | Pending |
| FR-03 | 캡 코호트는 같은 날(`date`) 레코드 전체에서 사후 정렬(발송 시각 순서와 무관). 단 유니버스는 "실제 발송된 것"으로 한정됨을 리포트에 명시 | High | Pending |
| FR-04 | `rvol` 없는 과거 레코드는 코호트 계산에서 제외하고 n만 표기 | Medium | Pending |
| FR-05 | shadow 섹션 계산 실패 시 try/catch로 삼키고 기존 리포트는 그대로 발송 (Fail-Safe) | High | Pending |
| FR-06 | 주간 누적(최근 N주) 집계를 위해 리포트가 코호트 통계를 staticData에 주 단위로 저장 (예: `store.shadowStats[weekStart]`) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Safety | 발송 대상 종목·수량·순서·메시지 본문이 배포 전후 동일 | 배포 전후 같은 입력에 대한 `selected` 비교(self-check) |
| Fail-Safe | shadow 로직 예외가 발송/리포트를 막지 않음 | self-check에서 예외 주입 |
| Cost | 추가 외부 API 호출 0 (rvol은 이미 계산된 `c.rvolVal` 사용, reporter는 저장값만 사용) | 코드 리뷰 |
| Reproducibility | shadow 규칙(임계값 5, 캡 2, 우선순위 맵)은 상수 1곳에 정의 | 코드 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done (shadow 구현 단계)

- [ ] FR-01~06 구현, self-check 통과
- [ ] dry-run diff 확인 후 사용자 재확인을 받고 n8n 반영, 반영 후 재조회로 diff 100% 일치 확인
- [ ] 다음 주간 리포트에 shadow 섹션이 정상 출력

### 4.2 Gate — shadow → live 승격 기준 (관찰 후)

최소 **3주 누적, 코호트별 확정 n ≥ 30** (미달 시 관찰 연장, 승격 금지).

| 규칙 | 승격 조건 |
|------|-----------|
| 복합 제외 | 복합 없는 코호트 승률이 실발송 전체보다 **+4%p 이상**, 평균수익률도 높고, 3주 중 **2주 이상** 같은 방향 (P0 기준선: 복합 12% vs 비복합 28%) |
| 거래량 5x (참고) | 5x 이상 승률이 5x 미만보다 **+4%p 이상**이고 **평균수익률도 높음**, 3주 중 **2주 이상** 같은 방향 (P0에서는 평균이 뒤집혀 기대 낮음) |
| 패턴 캡 | 캡 코호트 평균수익률이 실발송 전체보다 높고, 3주 중 **2주 이상** 같은 방향, 확정 n ≥ 30 |
| 공통 | 실발송 대비 신호량 감소율을 사용자에게 보고하고 감수 여부 확인 |

백테스트(2022~25) 수준의 효과 크기(승률 +4~5%p)는 주간 노이즈보다 작을 수 있어, **통과 못 하면 폐기**도 정상 결과로 취급한다.

### 4.2 Quality Criteria

- [ ] `scripts/verify_volume_shadow.js` self-check 통과 (코호트 계산, 빈 입력, `rvol` 누락, 예외 주입)
- [ ] 기존 `scripts/verify_*.js` 회귀 통과
- [ ] 배포 후 라이브 재조회 diff 일치

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 라이브 증거 오염(§1.2)으로 효과 과대평가 | High | 발생함 (P0에서 5x 효과 소멸 확인) | 해소: 실제 rvol로 재평가 완료, 주 후보를 복합 제외로 교체. 복합 효과도 2주·26건이라 shadow에서 재검증 |
| shadow 유니버스가 "실제 발송분"이라 캡 효과 과소/과대 추정 (발송 못 된 상위 우선순위 후보 누락) | Medium | High | 리포트에 한계 명시. 필요 시 scanLog `topCandidates`를 보조 근거로 사용 |
| 표본 부족으로 게이트 미통과/오판 | Medium | High | n≥30·3주·2/3주 일관성 조건, 미달 시 관찰 연장 |
| 레코드 필드 추가가 `weeklyRecommendations` 소비처(reporter, Daily_Position_Monitor)를 깨뜨림 | Medium | Low | 필드 추가만(기존 키 불변), self-check로 소비처 파싱 확인 |
| n8n 라이브 PUT 실수 | High | Low | dry-run diff → 사용자 명시 재확인 → `--apply` → 재조회 diff, 배포 전 백업 JSON 저장(`.claude/live_workflow_backup_*`) |
| 규칙이 2주 데이터에서 찾은 것이라 과적합 | High | Medium | 백테스트 4년에서 5x만 재현됨(3x 제외), 게이트에서 새 데이터로 재검증 |

---

## 6. Architecture Considerations

- **Level**: 해당 없음 (n8n Code 노드 기반 단일 워크플로우, 기존 `src/*.src.js` + `lib/*.js` 구조 유지)
- **변경 지점 (예정)**:
  1. `src/swing-scanner.src.js` ~1830행 `weeklyRecommendations.push({...})`에 `rvol: +selected[i].rvolVal.toFixed(2)`, `sentAt: new Date().toISOString()` 추가 (2줄). `selected`/`send` 경로 불변.
  2. `src/weekly-reporter.src.js` 리포트 조립 직전에 shadow 코호트 계산 블록 + 메시지 하단 섹션 (try/catch 감쌈). 계산 순수 함수는 `lib/`에 두면 self-check가 쉬움(예: `lib/shadowCohorts.js`, 신규 1파일 — 기존 `lib/trailingStop.js` 선례).
  3. `swing_scanner_code.js` / `weekly_reporter_code.js` 번들 재생성(`scripts/build_deploy_bundle.js`), `scripts/patch_volume_shadow.py` 작성.
- **규칙 상수**: `SHADOW_RVOL_MIN = 5`, `SHADOW_DAY_CAP = 2`, `SHADOW_PATTERN_PRIORITY = {D박스:0, C촉매:1, B지지선:2, A눌림목:3}`.
- **발송 영향 0 보장**: scanner 변경은 기록 필드 추가뿐. 필터/캡은 reporter의 사후 계산에서만 적용.

---

## 7. Convention Prerequisites

- 기존 관례 따름: 한국어 주석, `[FIX-YYYY-MM-DD]` 태그, `ponytail:` 한계 주석, patch 스크립트 dry-run 기본 + `--apply`.
- 새 환경변수/의존성 없음.

---

## 8. Next Steps

1. [ ] **P0** 라이브 129건 실제 rvol 재계산 → 필터 효과 재평가 (결과가 약하면 여기서 계획 재검토)
2. [ ] Design 문서 (`/pdca design volume5x-pattern-cap-shadow`): 코호트 계산 함수 시그니처, 리포트 섹션 포맷, staticData 스키마
3. [ ] 구현(Do) → self-check → dry-run diff → 사용자 재확인 → 라이브 반영
4. [ ] 2~3주 관찰 → §4.2 게이트 판정 → (통과 시) live 승격 plan

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-03 | Initial draft (백테스트 4년 + 라이브 2주 근거, 라이브 증거 오염 명시) | kevin |
| 0.2 | 2026-10-03 | P0 결과 반영: 5x 효과 소멸(착시), 복합 제외 코호트 추가(FR-01b), 5x는 참고용 강등 | kevin |

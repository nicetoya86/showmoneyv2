# volume5x-pattern-cap-shadow Design Document

> **Summary**: 발송은 그대로 두고, 주간 리포트가 "복합 제외 / 일 2건 패턴캡 / 거래량 5x(참고)" 가상 코호트를 실발송과 나란히 계산·표시한다. 규칙 판정은 순수 함수 1개(`lib/shadowCohorts.js`)에 모은다.
>
> **Project**: showmoneyv2 (n8n workflow `ScHaeFdneOoH1ZNZ`)
> **Author**: kevin
> **Date**: 2026-10-03
> **Status**: Draft
> **Planning Doc**: [volume5x-pattern-cap-shadow.plan.md](../../01-plan/features/volume5x-pattern-cap-shadow.plan.md)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 필터/캡 후보 규칙이 2주 데이터에서 나와 과적합 위험이 크고, 거래량 5x 효과는 P0에서 착시로 판명(복합C+D 종목이 저거래량 버킷에 섞임). 실제 신호는 복합 신호 유무(12% vs 28%)로 보임. |
| **Solution** | scanner는 추천 레코드에 `rvol` 1필드만 추가. weekly-reporter가 순수 함수로 코호트 4종을 사후 계산해 리포트 하단에 표시하고 주별 통계를 `store.shadowStats`에 보관. 승격 게이트는 리포트가 진행 상황만 보여주고 판정은 사람이 한다. |
| **Function/UX Effect** | 사용자 알림 불변. 주간 리포트에 8줄 내외 "Shadow 비교" 섹션 추가. |
| **Core Value** | 규칙을 배포 이후(out-of-sample) 데이터로만 검증. 되돌릴 비용 0, 외부 호출 0. |

---

## 1. Overview

### 1.1 Design Goals

1. 발송 대상·순서·수량·본문이 배포 전후 동일 (shadow 불변성).
2. 사후 계산에서 look-ahead 편향 제거 — 코호트 선정은 결과(승/패)를 모르는 시점의 정보만 사용.
3. 코드 최소화: 신규 파일 1(`lib/shadowCohorts.js`) + 검증 1(`scripts/verify_shadow_cohorts.js`) + 배포 1(`scripts/patch_volume_shadow.py`).

### 1.2 Design Principles

- **순수 함수 + Fail-Safe**: 계산은 I/O 없는 함수, 호출부는 try/catch로 감싸 실패 시 섹션만 생략.
- **파생 가능한 건 저장하지 않는다(YAGNI)**: 복합 여부는 `signals`에서 판정 가능(복합 태그는 항상 앞 3개 안에 들어감 — 패턴태그 ≤2 + 복합 1), 캡 순서는 `patternType`/`score`/`date`로 충분. 저장은 `rvol`만 추가(잘리는 거래량 태그를 대체).
- **게이트 카운트는 배포 이후 주만**: W1/W2(9/21~10/2)는 규칙을 도출한 in-sample이라 승격 근거에서 제외.

---

## 2. Architecture

### 2.1 Component Diagram

```
swing-scanner (발송 경로 불변)
  └─ weeklyRecommendations[date].push({... , rvol})   ← 1필드 추가
                    │ (staticData)
weekly-reporter     ▼
  details[] = {...rec, result, targetPct, stopPct, finalReturn, expiredForced, ...}
       │
       ├─ (기존) 리포트 본문 조립 ─────────────────────────┐
       └─ computeShadowCohorts(details, CFG)  [lib, 순수]   │
              │  try/catch                                  │
              ├─ msg += formatShadowSection(...)  ──────────┤→ telegram
              └─ store.shadowStats[weekStart] = summary     │
```

### 2.2 Data Flow

1. 발송 시 `rvol`(소수 2자리, 없으면 null)이 레코드에 붙는다. 이후 `details.push({...r, ...})`가 이미 `...r` 스프레드라 reporter 쪽 변경 없이 `details`로 전달된다.
2. reporter가 평가 완료 후(`details` 확정, 약 line 359~404) 코호트 계산.
3. 결과를 메시지 하단(line ~600, 면책 문구 직전)에 추가, 주별 요약을 staticData에 저장.

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `lib/shadowCohorts.js` | 없음 (순수) | 코호트 선정·통계 |
| `weekly-reporter.src.js` | `lib/shadowCohorts.js` | 호출·포맷·저장 |
| `scripts/build_deploy_bundle.js` | `lib/*.js` | 번들 인라인. **lib 최상위 식별자 충돌 사전 점검 대상** → 신규 lib의 최상위 식별자는 `shadow*`/`SHADOW_*` 접두로 통일 |

---

## 3. Data Model

### 3.1 추천 레코드 (변경: 1필드)

```js
// weeklyRecommendations[date][i]  (기존 필드 전부 유지)
{ ...,
  signals: string[],      // 기존: slice(0,3)
  rvol: number | null     // NEW: selected[i].rvolVal.toFixed(2) → Number, 없으면 null
}
```

기존 레코드(rvol 없음)는 그대로 유효. 소비처(Daily_Position_Monitor, reporter)는 알려지지 않은 키를 무시한다.

### 3.2 코호트 설정 (상수 1곳)

```js
const SHADOW_CFG = {
  rvolMin: 5,                    // 참고용 코호트
  dayCap: 2,
  patternPriority: { 'D박스': 0, 'C촉매': 1, 'B지지선': 2, 'A눌림목': 3 }, // 미등록 패턴은 99
  gateMinClosed: 30, gateMinWeeks: 3, gateMinWinPctGain: 4,
};
```

### 3.3 코호트 정의

입력: 이번 주 **신규 추천**(`carryOver` 제외) 전체 `details`. 결과 미확정(`holding`/`no_data`/`error`)도 **선정 단계에는 포함**하고, 통계 집계 시 확정(win/partial_win/loss)만 센다 (look-ahead 방지).

| 코호트 | 선정 규칙 |
|--------|-----------|
| `ALL` | 전체 (실발송 기준선) |
| `NOCOMP` | `signals`에 `'복합'` 포함 종목 제외 |
| `CAP2` | 날짜별로 `patternPriority` 오름차순, 동순위 `score` 내림차순 상위 2건 |
| `NOCOMP+CAP2` | `NOCOMP` 적용 후 날짜별 CAP2 |
| `RVOL5` (참고) | `rvol >= 5`. `rvol == null`은 제외하고 누락 건수를 `missing`으로 표기 |

### 3.4 통계 정의 (코호트별)

```js
{ name, n, closed, win, part, loss, winPct, wpPct, avgRet, missing? }
// avgRet: win → (expiredForced ? finalReturn : targetPct), partial_win/loss → stopPct
//   ponytail: 승을 목표가 수익률로 간주(수수료·슬리피지·부분체결 미반영) — 방향 비교용, 절대 수익률 아님
```

### 3.5 주별 저장 스키마

```js
store.shadowStats[weekStart('YYYY-MM-DD')] = {
  ALL: {...}, NOCOMP: {...}, CAP2: {...}, 'NOCOMP+CAP2': {...}, RVOL5: {...}
}
// 최근 12주만 보관(초과분 삭제)
```

---

## 4. 모듈 인터페이스

### 4.1 `lib/shadowCohorts.js`

```js
const SHADOW_CFG = {...};
function shadowSelect(newRecs, cohort, cfg)          // → 선정된 레코드 배열 (결과 무관)
function shadowStats(selected, name)                  // → §3.4 객체 (확정 건만 집계)
function computeShadowCohorts(details, cfg = SHADOW_CFG) // → { ALL, NOCOMP, CAP2, 'NOCOMP+CAP2', RVOL5 }
function shadowGate(weeklyStatsMap, cfg = SHADOW_CFG)    // → 코호트별 { closedTotal, weeks, weeksPositive, passN, passWeeks }
module.exports = { SHADOW_CFG, shadowSelect, shadowStats, computeShadowCohorts, shadowGate };
```

- `computeShadowCohorts`는 예외를 던질 수 있는 입력(undefined 등)에 대해 빈 배열로 방어하되, **호출부가 try/catch**로 최종 방어한다.
- `shadowGate`의 "주별 방향": 해당 주 코호트의 `winPct`가 같은 주 `ALL.winPct`보다 높고 `avgRet`도 높으면 +1 (확정 5건 미만 주는 판정 제외).

### 4.2 `weekly-reporter.src.js` 변경점

```js
const { computeShadowCohorts, shadowGate } = require('../lib/shadowCohorts');
...
// msg += 직전 (면책 문구 앞)
try {
  const sh = computeShadowCohorts(details.filter(d => !d.carryOver));
  store.shadowStats = store.shadowStats || {};
  store.shadowStats[weekDates[0]] = sh;
  // 12주 초과 정리
  msg += formatShadowSection(sh, shadowGate(store.shadowStats));   // 호출부 로컬 함수
} catch (e) { logger.warning('shadow cohorts failed', { error: e && e.message }, requestId); }
```

`formatShadowSection`은 reporter 내부 로컬 함수(리포트 포맷 전용, 재사용 없음).

### 4.3 `swing-scanner.src.js` 변경점

`weeklyRecommendations[today2].push({...})`(약 1830행)에 `rvol` 한 줄 추가. `selected`/`send`/필터/캡 로직 무변경.

```js
rvol: Number.isFinite(selected[i].rvolVal) ? +selected[i].rvolVal.toFixed(2) : null,
```

---

## 5. 리포트 섹션 포맷 (예시, ~8줄)

```
🔬 Shadow 비교 (발송 불변 · 이번 주 신규 확정 기준)
실발송   확정 64 │ 승 28% │ 부분포함 39% │ 평균 +1.96%
복합제외 확정 47 │ 승 34% │ 평균 +2.86% (승률 +6%p)
일2건캡  확정 8 │ 승 75% │ 평균 +7.11%   ※표본 적음
복합제외+캡 확정 8 │ ...
5x+(참고) 확정 41 │ 승 27% │ 평균 +1.41% (rvol 미기록 23건 제외)
게이트(배포 후 N주): 복합제외 확정 n/30 · 주별 방향 k/N
```

- 확정 5건 미만 코호트는 `※표본 적음` 표기.
- 게이트 줄은 진행 상황만 표시, 자동 승격 없음.
- 배포 후 첫 주: 게이트 줄은 `수집 중 (1/3주)`.

---

## 6. Error Handling

| 상황 | 처리 |
|------|------|
| `rvol` 없는 과거 레코드 | RVOL5에서 제외, `missing` 표기 (다른 코호트는 영향 없음) |
| 코호트 계산 예외 | try/catch → 섹션 생략, warning 로그, 기존 리포트·저장 로직 정상 진행 |
| `store.shadowStats` 손상/미존재 | 매 실행 시 `|| {}` 초기화, 현재 주만 덮어씀 |
| 12주 초과 | 오래된 키부터 삭제 |

---

## 7. Test Plan

`scripts/verify_shadow_cohorts.js` (assert 기반, 프레임워크 없음, 기존 `verify_*.js` 스타일):

| # | 케이스 | 기대 |
|---|--------|------|
| 1 | 복합 판정: `['박스권돌파','촉매이벤트','복합C+D']` | NOCOMP에서 제외 |
| 2 | 캡 look-ahead 방지: 같은 날 후보 중 1순위가 `holding` | 선정에는 포함, 통계 closed에서는 제외 |
| 3 | 우선순위 정렬: D>C>B>A, 동순위는 score 내림차순 | 상위 2건 정확 |
| 4 | `NOCOMP+CAP2`: 복합 먼저 제외 후 캡 | 복합 종목이 캡 슬롯을 차지하지 않음 |
| 5 | `rvol` 누락/null 혼재 | RVOL5 제외·missing 카운트, 타 코호트 불변 |
| 6 | `avgRet` 공식: win=targetPct, expiredForced win=finalReturn, partial/loss=stopPct | 수치 일치 |
| 7 | 빈 입력 / `carryOver`만 있는 입력 | 예외 없이 n=0 |
| 8 | `shadowGate`: 확정 n<30 또는 주 수<3 | `passN`/`passWeeks` false |
| 9 | 불변성: `computeShadowCohorts`가 입력 `details`를 변형하지 않음 | deep-equal |
| 10 | 호출부 예외 주입 | reporter가 섹션만 생략하고 정상 종료(하네스 `harness.js` 방식으로 확인) |

실데이터 확인: P0에서 만든 하네스(`details.json`)로 W2 `NOCOMP` 승률(34%)과 기대값이 재현되는지 대조.

---

## 8. Deployment & Rollback

1. `node scripts/build_deploy_bundle.js` → `swing_scanner_code.js`, `weekly_reporter_code.js` 재생성 (lib 식별자 충돌 점검 통과 확인).
2. `scripts/patch_volume_shadow.py`: 기본 dry-run(diff 출력), `--apply`일 때만 PUT. 적용 전 라이브 워크플로우 JSON을 `.claude/live_workflow_backup_*.json`으로 백업. 대상 노드는 **Swing Scanner**와 **Weekly Reporter** 2개.
3. **`--apply` 전 사용자 명시 재확인 필수** ([feedback-production-deploy-confirmation]).
4. 적용 후 재조회 diff 100% 일치 확인.
5. 롤백: 백업 JSON의 해당 노드 코드를 PUT으로 복원(필드 추가·섹션 추가뿐이라 데이터 마이그레이션 없음).
6. 검증 시점: 다음 주간 리포트(토요일 09:00 트리거) 출력 확인, 첫 스캔 후 `weeklyRecommendations`에 `rvol` 기록 확인.

---

## 9. Implementation Order (Do phase 체크리스트)

1. [ ] `lib/shadowCohorts.js` 작성 + `scripts/verify_shadow_cohorts.js` (테스트 먼저, 1~9)
2. [ ] `weekly-reporter.src.js`에 호출/포맷/저장 추가 → 하네스로 실제 데이터 대조(케이스 10)
3. [ ] `swing-scanner.src.js`에 `rvol` 1줄 추가 → 기존 `verify_*.js` 회귀
4. [ ] 번들 빌드, 식별자 충돌 점검
5. [ ] `patch_volume_shadow.py` dry-run diff 검토 → 사용자 재확인 → `--apply` → 재조회 diff
6. [ ] 다음 주간 리포트에서 섹션 확인, `rvol` 기록 확인

## 10. 범위 밖 / 후속

- 승격(필터/캡 live 적용): 게이트 통과 후 별도 plan.
- 복합 효과의 독립 검증: 백테스트 trade에 `signals` 저장하도록 `swing_signal_engine` 확장 필요(비용 큼). shadow가 쌓이는 동안 보류.
- KSS해운형 분류 버그(`weekly-reporter.src.js:312-313`) 최소 패치는 별건.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-03 | Initial design (P0 반영: 복합 제외 주 후보, 5x 참고용, `rvol` 1필드·`sentAt` 불필요) | kevin |

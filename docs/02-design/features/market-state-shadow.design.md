# market-state-shadow Design Document

> **Summary**: 발송은 그대로 두고, 추천마다 "그 종목이 속한 시장(KOSPI/KOSDAQ)의 상태(5종)"를 기록한 뒤, 주간 리포트가 "상태 기반 차단 / 상태×패턴 제외표 / 상태별 일 노출 상한" 가상 코호트를 실발송과 나란히 계산·표시한다. 라이브 규칙 승격은 사람이 게이트를 보고 판정한다.
>
> **Project**: showmoneyv2 (n8n workflow `ScHaeFdneOoH1ZNZ`)
> **Author**: kevin
> **Date**: 2026-10-19
> **Status**: Draft — 빌더 검토 반영 완료, 사용자 승인 대기
> **선행 문서**: [volume5x-pattern-cap-shadow.design.md](./volume5x-pattern-cap-shadow.design.md) (같은 shadow 프레임워크 확장)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 레짐 게이트는 "약세=강매 전용 + 1회 1종목" 두 가지뿐이고 하락만 감지한다. 10/02~10/16 124건 중 87건(70%)이 소속 시장이 *과열(SURGE)* 일 때 발송됐고 게이트는 이를 0단계(강세, 전 등급 허용)로 봤다. 10/13부터는 -20% 급락(CRASH). 2022~25 백테스트에서 SURGE는 train/test 모두 음수(-0.35/-0.33%). 하루 총량 상한도 없다. |
| **Solution** | 지수 직전 종가 기준 5상태(CRASH/DOWN/FLAT/UP/SURGE) 분류 순수 함수 1개 + 추천 레코드에 상태 4필드 기록 + 가상 코호트 5종(차단·패턴표·상한(선착순)·상한(일 최선, 참고)·결합)을 리포트가 사후 비교. |
| **Function/UX Effect** | 사용자 알림 불변. 주간 리포트에 "시장상태 Shadow" 섹션(약 10줄) 추가. |
| **Core Value** | 규칙을 배포 이후(out-of-sample) 데이터로만 검증. 되돌릴 비용 0, 라이브 레짐 경로 무변경. 가치는 수익 창출보다 *좌측 꼬리(노출) 관리*. |

---

## 1. Overview

### 1.1 Goals
1. 발송 대상·순서·수량·본문·**기존 레짐 게이트 입력**이 배포 전후 동일 (shadow 불변성).
2. 모든 추천에 발송 시점 시장상태를 기록해, 이후 어떤 규칙도 look-ahead 없이 사후 평가 가능.
3. 3개 후보 규칙(차단 / 상태×패턴 제외 / 상태별 일 상한)의 효과를 신규 추천 기준 주별로 측정.

### 1.2 Non-goals
- 라이브 발송 규칙 변경(승격은 별도 PDCA, 사용자 재확인 필요).
- 상태별 목표·손절·BE·보유기간 적응 (검증 결과 효과 없음 — 4절 근거).
- 신호 군집(하루 후보 수) 기반 규칙 (연도별 부호 뒤집힘).
- 사이징(비중 조절). 모든 거래 동일 비중 가정.
- 소스 내 평문 시크릿 정리(별건, 12절).

### 1.3 Anti-goals (기술적으로 동작해도 실패인 것)
- shadow 코드 예외가 발송·기존 리포트를 막거나 지연시킴.
- 상태 판정 때문에 기존 `getMarketRegime`/`fetchDailyOHLC` 라이브 경로의 데이터·결과가 달라짐.
- 한두 주의 폭락/과열로 규칙을 승격 (게이트 3절 참고).

---

## 2. 근거 (분석 완료, 구현 대상 아님)

백테스트: 후보 21,587건(959종목, 2022-01~2025-12, `backtest_candidates_with_paths.json`), 지수 상태는 해당 신호일 *직전 종가까지*로 분류, 청산은 일봉 단순 가정(T+8%/S-4%, 5일, 비용 전). train=2022~23, test=2024~25.

| 상태 | 평균%/건 train → test | 판정 |
|---|---|---|
| UP | +0.16 → +0.18 | 안정 양수 |
| FLAT | -0.06 → +0.33 | 약한 양수 |
| DOWN | -0.45 → -0.07 | 둘 다 음수 |
| SURGE | -0.35 → -0.33 | 둘 다 음수, 전 패턴 음수(D만 뒤집힘) |
| CRASH | -0.43 → +0.38 | 부호 뒤집힘, 표본 적음 → 통계 아닌 **위험 규칙**으로 취급 |

부호가 train/test 일치한 셀: UP×A/B/C 양수, CRASH×D 음수(-0.53/-0.56), DOWN×A 음수, DOWN×B 양수, SURGE×A/B/C 음수.
효과 크기: 상태 필터·허용표 적용 시 test +0.13 → +0.26~0.27%/건. 비용 0.2% 차감하면 기본 풀은 -0.07% — **적응은 수익을 만들기보다 손실을 줄이는 도구**.
제외 근거: 상태별 청산 적응은 전역 최적(T15/S7)보다 나아지지 않음. 하루 후보 수 군집은 연도별 부호 불일치.

사전 in-sample 참고치(게이트 제외, 10/02~10/16 라이브 추천 124건, BE6 재생 기준, 선착순=`weeklyRecommendations` 배열 순서):

| 코호트 | 건수 | 확정 | 승률 | 평균 | 합 |
|---|---|---|---|---|---|
| 실발송(ALL) | 124 | 122 | 16% | -1.28% | -156%p |
| STATE_BLOCK | 18 | 18 | 17% | -0.32% | -6%p |
| STATE_PAT | 30 | 28 | 11% | -1.44% | -40%p |
| STATE_CAP(선착순) | 18 | 18 | 28% | +1.61% | +29%p |
| STATE_CAP_BEST(참고) | 18 | 18 | 22% | -0.24% | -4%p |
| STATE_ALL | 13 | 13 | 23% | +1.36% | +18%p |

한 주·소표본·사후 확인이므로 방향 참고용. STATE_PAT가 BLOCK보다 나쁜 건 CRASH에서 D 외 패턴을 통과시키기 때문(이번 폭락은 패턴 무관) — 이 차이 자체를 shadow가 측정한다.

---

## 3. 상태 정의 (`lib/marketState.js`, 순수 함수)

입력: 지수 일봉 배열(`{date:'yyyyMMdd', close}` 시간순), `asOf`(오늘 'yyyy-MM-dd'), `expectedPrev`(직전 거래일 'yyyyMMdd').

1. **룩어헤드 금지**: `date < today`인 봉만 사용(당일 진행 중 봉 제외).
2. **신선도**: 사용 가능한 마지막 봉의 날짜 == `expectedPrev`가 아니면 `state='UNKNOWN'`. 봉 61개 미만도 `UNKNOWN`.
3. 지표(종가 기준): `r5 = c[i]/c[i-5]-1`, `r20 = c[i]/c[i-20]-1`, `dd20 = c[i]/max(c[i-19..i]) - 1`, `MA5/20/60`(단순).
4. 판정 순서(앞이 우선):

| 순서 | 상태 | 조건 |
|---|---|---|
| 1 | CRASH | `r5 <= -5%` 또는 `dd20 <= -8%` |
| 2 | DOWN | `c < MA20` 그리고 `c < MA60` |
| 3 | SURGE | `r20 >= +8%` |
| 4 | UP | `c > MA20 > MA60` 그리고 `r20 >= +2%` |
| 5 | FLAT | 위 어디에도 해당 없음 |

5. 추천이 속하는 시장: `ticker`가 `.KS`면 KOSPI, 아니면 KOSDAQ. 추천의 상태 = 그 시장 지수의 상태(두 시장 상태를 섞지 않음).
6. 경계값(−5%, −8%, +8%, +2%)은 분석에서 쓴 값 그대로(작성자 판단). 민감도 점검은 미실시 → 7절 검증에 포함.

반환: `{ state, r5, r20, dd20, aboveMa20, aboveMa60, asOfBar }`. 식별자는 번들러 충돌 점검 때문에 `ms*`/`MS_*` 접두.

### 3.1 지수 데이터 소스 (라이브 레짐 경로와 분리)
- `msFetchIndexBars(http, 'KOSPI'|'KOSDAQ')`: 1순위 `https://api.stock.naver.com/chart/domestic/index/{KOSPI|KOSDAQ}/day?startDateTime&endDateTime`(2026-10-19 확인: 10/16 봉까지 반환, 필드 `localDate`/`closePrice`), 2순위 Yahoo(`^KS11`/`^KQ11`). `http`는 호출부에서 주입(lib 간 상호 require 금지 규칙).
- **기존 `fetchDailyOHLC`/`getMarketRegime`는 건드리지 않는다.** 이유: 10/16 `regimeCache`가 `stale(20261014)`였음(10/15의 -7.6% 급락 봉 누락). shadow가 자체 소스를 쓰면 라이브 입력이 바뀌지 않으면서 stale 문제를 피한다.
- 하루 1회 캐시(`store.marketStateCache = {date, KOSPI:{...}, KOSDAQ:{...}}`). 결과가 `UNKNOWN`이면 캐시하지 않고 다음 스캔에서 재시도(호출 2회/스캔, 영향 미미).

---

## 4. 데이터 기록 (swing-scanner)

`weeklyRecommendations[date].push({...})`(약 1830행)에 필드 4개 추가:

| 필드 | 값 | 용도 |
|---|---|---|
| `mkt` | `'KOSPI'`/`'KOSDAQ'` | 그룹 단위 |
| `mstate` | 5종 + `'UNKNOWN'`, 계산 실패 시 `null` | 코호트 판정 |
| `mstateAsOf` | 사용한 마지막 봉 날짜 | 감사 |
| `sentAt` | 발송 시각 `Date.now()` | 선착순 상한 재현(배열 순서가 있으나 시각이 있으면 정렬 안정) |

- 상태 계산 전체를 try/catch로 감싸 실패 시 `mstate:null`로 기록하고 발송 경로는 그대로 진행. 상태 조회는 발송 *이전*에 한다. 하루 1회 캐시라 평소엔 읽기만 하고, 캐시 미스(첫 스캔·`UNKNOWN` 재시도) 때만 두 시장을 **병렬** 조회하며 개별 http 6초, 전체 최대 15초로 상한(실패 시 `UNKNOWN`/`null`로 즉시 진행). [최종 리뷰 반영]
- 번들 diff는 "순수 추가"여야 한다(삭제 0).

---

## 5. 가상 코호트 (`lib/shadowCohorts.js` 확장, 순수)

적용 대상: `mstate`가 정의된(`null`/미존재 제외) 신규 추천. 비교 기준선 `ALLS` = 같은 조건(`mstate` 정의됨)의 실발송 전체 — 기존 `ALL`과 별개로 계산(배포 주에 일부 추천만 필드가 있을 수 있음). `UNKNOWN` 상태는 모든 코호트에서 **통과**(차단·제외하지 않음)시키고 건수를 따로 표시.

| 코호트 | 규칙 |
|---|---|
| `STATE_BLOCK` | `mstate ∈ {SURGE, CRASH}` 추천 제외 |
| `STATE_PAT` | 제외 셀: SURGE×전 패턴, CRASH×`D박스`, DOWN×`A눌림목` |
| `STATE_CAP` | (일자, 시장) 그룹별 상한 `UP 3 / FLAT 3 / DOWN 1 / SURGE 1 / CRASH 0`, 그룹 내 **선착순**(`sentAt`, 없으면 배열 순서). **라이브 재현 가능한 기준** |
| `STATE_CAP_BEST` | 같은 상한을 기존 `D>C>B>A`(+점수) 순으로 선별. 하루가 끝나야 알 수 있는 정보를 쓰므로 **참고용**(라이브 불가) |
| `STATE_ALL` | `STATE_BLOCK` → `STATE_PAT` → `STATE_CAP` 순차 적용(최종 승격 후보 정책) |

- 선정은 결과(result)를 보지 않는다. 미확정(holding)도 슬롯을 차지한다.
- **상한 버킷은 (일자, 시장, `mstate`) 단위**다. 한 (일자, 시장)에 상태가 섞이는 경우는 `UNKNOWN`→확정 상태 전환뿐이므로, 각 추천은 자기 상태의 상한만 적용받는다. `UNKNOWN` 추천은 통과하며 **슬롯을 소비하지 않는다**(상한 없음). (작성자 판단)
- `STATE_CAP`이 `STATE_CAP_BEST`보다 크게 나쁘면 "선착순 캡은 라이브에서 효과가 줄어든다"는 뜻 — 승격 시 배치 발송(아침 일괄 선별) 필요 여부를 그때 판단한다.
- 한계: 코호트는 *실제 발송된 집합*에서만 고른다. 라이브에서 상한이 걸리면 빈 슬롯을 다른 종목이 채울 수 있어 효과 추정이 근사치다.
- 통계에 `sumRet`(합계 %p)과 `excludedAvg`(제외된 집합의 평균)를 추가. 캡은 거래 수를 줄이므로 평균만 보면 오판한다.

---

## 6. 리포트 및 저장

### 6.1 섹션 (weekly-reporter, 기존 Shadow 섹션 바로 아래, try/catch)
```
🌡️ 시장상태 Shadow (발송 불변 · 이번 주 신규 확정 기준)
시장상태(추천일 기준): KOSDAQ SURGE 4일→CRASH 4일 | KOSPI UP 1일→...   (UNKNOWN n건)
실발송(상태기록분) 확정 N │ 승 x% │ 평균 ±x% │ 합 ±x%p
상태차단   확정 N │ 승 x% │ 평균 ... (승률 ±x%p) │ 제외분 평균 ±x%
패턴표     ...
상한(선착순) ...
상한(일최선·참고) ...
결합       ...
게이트(배포 후 정보주 k주): 상태차단 확정 a/30 · 방향 b/c ...
```
기존 `fmt` 헬퍼 재사용(`※표본 적음` 규칙 포함). 텔레그램 4000자 분할은 기존 로직이 처리.

### 6.2 저장
`store.shadowStats[weekStart]`에 새 키(`ALLS`, `STATE_BLOCK`, `STATE_PAT`, `STATE_CAP`, `STATE_CAP_BEST`, `STATE_ALL`) 추가. 구조는 기존 `shadowStats`(`name,n,closed,win,part,loss,winPct,wpPct,avgRet`)에 `sumRet`/`excludedAvg`만 더해 호환 유지, 최근 12주 보관은 기존 코드 그대로.

### 6.3 게이트 (판정은 사람)
상태 코호트 비교 기준선은 `ALLS`. 한 주가 **정보주(informative)**가 되려면 코호트가 제외한 추천이 `max(5, ALLS 건수의 15%)` 이상이어야 한다(제외가 없는 주는 코호트=기준선이라 증거가 아님).

| 조건 | 기준 |
|---|---|
| 표본 | 코호트(통과분) 확정 누적 ≥ 30 |
| 기간 | 정보주 ≥ 3주 (시장이 안 변하면 자연히 길어짐 → 8주 시점에 재검토, 자동 승격 없음) |
| 일관성 | 정보주의 2/3 이상에서 승률·평균 모두 `ALLS` 초과 |
| 효과 | 누적 승률 +4%p 이상 **그리고** 누적 평균 개선 > 0 **그리고** 제외분 누적 평균 < 0(좋은 종목을 걷어내지 않았음) |

배포 이전 주(10/02~10/16 포함)는 규칙을 도출한 in-sample이므로 게이트에서 제외한다.

구현 세부 (작성자 판단):
- 게이트는 **별도 함수 `shadowStateGate`** 로 추가한다. 기존 `shadowGate`(NOCOMP/CAP2, 기준선 `ALL`)의 출력은 바이트 단위로 불변.
- 대상 코호트: `STATE_BLOCK`, `STATE_PAT`, `STATE_CAP`, `STATE_ALL`. `STATE_CAP_BEST`는 라이브 불가 참고용이라 게이트 제외.
- 정보주 판정의 제외 건수 = `ALLS.n − cohort.n`(미확정 포함, 저장된 통계로 계산 가능). 효과 조건의 `excludedAvg`는 확정 건 기준.
- `ALLS`가 없는 과거 주(`shadowStats`에 이전 키만 있는 주)는 오류 없이 건너뛴다.
- 리포트 게이트 줄은 `STATE_ALL`과 `STATE_BLOCK` 두 개만 표시(공간 절약), 나머지는 저장만.

---

## 7. 구현 범위 (파일)

| 구분 | 파일 | 내용 |
|---|---|---|
| 신규 | `lib/marketState.js` | `msClassify`, `msFetchIndexBars`, `MS_CFG`(경계값) |
| 수정 | `lib/shadowCohorts.js` | 코호트 5종 + `ALLS`, `sumRet`/`excludedAvg`, `shadowGate`의 기준선 선택 |
| 수정 | `src/swing-scanner.src.js` | 캐시된 상태 조회 + 레코드 필드 4개(전부 try/catch) |
| 수정 | `src/weekly-reporter.src.js` | 섹션 추가 |
| 신규 | `scripts/verify_market_state.js` | 8절 |
| 수정 | `scripts/verify_shadow_cohorts.js` | 새 코호트 케이스 |
| 신규 | `scripts/patch_market_state_shadow.py` | 번들→라이브 패치(dry-run/--apply, 백업, 재조회 검증; 기존 `patch_volume_shadow.py` 패턴) |
| 빌드 | `scripts/build_deploy_bundle.js` | 변경 없음. 충돌 점검 때문에 lib 간 require 금지, 최상위 식별자 `ms*`/`shadow*` 접두 |

---

## 8. 검증 계획
- `verify_market_state.js`: (a) 경계값(r5 정확히 -5%, dd20 -8%, r20 +8%/+2%), (b) 판정 우선순위, (c) 봉 60개 이하→UNKNOWN, (d) 마지막 봉이 expectedPrev가 아니면 UNKNOWN, (e) 당일 진행 봉 무시(룩어헤드), (f) **실데이터 회귀**: 체크인된 픽스처 `scripts/fixtures/index_2026.json`(Naver 지수 일봉 2026-03-01~10-16 종가, 약 150봉 — 60봉 이상 확보)로 KOSDAQ 10/06=SURGE, 10/12=CRASH, KOSPI 10/08=DOWN, 10/12=CRASH, 10/02=UP 확인, (g) 경계값 민감도: ±1%p 흔들었을 때 4년 후보의 상태 분포·부호가 크게 바뀌지 않는지(스크립트가 표만 출력, 판정은 사람).
- `verify_shadow_cohorts.js` 확장: 차단/패턴표/상한(선착순 vs 일최선 순서 차이)/결합, `UNKNOWN` 통과, `mstate` 미존재 추천 제외, 정보주 판정, 제외분 평균, 기존 코호트 회귀 불변.
- 불변성: 번들 dry-run diff가 순수 추가(삭제 0), 기존 `verify_*.js` 전부 통과, 예외 주입(`msFetchIndexBars` throw) 시 발송·리포트 정상(`mstate:null`).
- 실데이터 재현(참고 점검, 게이트 아님): 라이브 `weeklyRecommendations`에서 추출한 추천 124건 덤프(`scripts/fixtures/recs_2026-10-02_16.json`, 추천 필드만·시크릿 제외·배열 순서 보존)에 위 지수 픽스처로 `mkt`/`mstate`를 **같은 분류 함수로 역산(backfill)** 해 새 코호트를 돌리고 2절 표(124/18/30/18/18/13)와 대조한다. 결과 열(승/평균/합)은 BE6 재생 결과 파일이 필요하므로 건수만 일치 확인, 불일치 시 원인 기록(설계 차단 사유 아님).

---

## 9. 롤아웃·롤백
1. 구현 → 로컬 검증 전부 통과 → 번들 재빌드.
2. `patch_market_state_shadow.py` dry-run → diff(순수 추가) 사용자 확인.
3. **라이브 PUT은 사용자 명시 재확인 후에만** `--apply`(기존 규칙). 직전 백업 파일 생성, 적용 후 재조회로 노드 코드 일치 검증.
4. 롤백: 백업의 노드 코드를 PUT. 새 필드는 읽기 전용이라 남겨도 무해.
5. 관찰: 첫 스캔 후 `weeklyRecommendations`에 4필드 기록 확인 → 토요일 리포트에 섹션 확인.

---

## 10. 위험
| 위험 | 대응 |
|---|---|
| 한 번의 과열→폭락 사건에 규칙이 과적합 | 게이트가 정보주 3주+·일관성·제외분 평균까지 요구, 자동 승격 없음, 상태 정의·상한값은 백테스트 4년 분석에서 온 것이지 이번 주에서 온 것이 아님 |
| CRASH 표본 부족(부호 뒤집힘) | CRASH는 통계가 아닌 위험 규칙으로 표기, 코호트에서 별도 비교(BLOCK vs PAT) |
| 지수 데이터 지연/누락 | 자체 소스 + `UNKNOWN`은 통과·재시도, 리포트가 `UNKNOWN` 건수를 표시 |
| 선착순 캡이 일 최선 캡과 다름 | 두 코호트를 동시에 측정해 차이를 가시화 |
| 텔레그램 메시지 길이 | 섹션 10줄 이내, 기존 분할 전송 사용 |

---

## 11. 빌더 검토 반영
독립 빌더 검토(2026-10-19)가 "대체로 그대로 구현 가능"으로 확인했고, 남은 질문 4개는 모두 문서 안에서 닫았다(전부 작성자 판단 — 승인 시 확인 요망):

1. 8절 검증 데이터: 지수 픽스처(약 150봉)와 추천 124건 덤프를 `scripts/fixtures/`에 체크인, 추천은 같은 분류 함수로 backfill. 2절 재현은 참고 점검이지 게이트가 아님.
2. 상한 버킷: (일자, 시장, 상태) 단위, `UNKNOWN`은 통과·슬롯 비소비 (5절).
3. 게이트: `shadowStateGate` 별도 함수, 기존 `shadowGate` 출력 불변, 대상은 BLOCK/PAT/CAP/ALL, 정보주는 `ALLS.n − cohort.n` 기준 (6.3절).
4. `ALLS`가 없는 과거 주는 조용히 건너뜀 (6.3절).

빌더가 스스로 결정 가능하다고 본 항목(스캔 시작 시 지수 봉 조회를 await+try/catch로, `expectedPrev`는 스캐너의 `getPrevTradingDay`, `.KS`→KOSPI 매핑)도 그대로 채택.

---

## 12. 별건 메모 (이 설계 범위 밖)
`src/swing-scanner.src.js` 상단에 DART API 키와 텔레그램 봇 토큰이 평문으로 들어 있고 git에 올라가 있다. 이 설계와 무관하게 재발급 + 환경변수/n8n 자격증명 분리를 권한다(별도 작업).

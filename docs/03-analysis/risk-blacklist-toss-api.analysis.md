# risk-blacklist-toss-api Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) — PDCA Check
>
> **Project**: showmoneyv2 (Autostock Swing Scanner)
> **Version**: n/a (n8n workflow, `algo-v1.0` 기준)
> **Analyst**: kevin (bkit-gap-detector)
> **Date**: 2026-07-10
> **Design Doc**: [risk-blacklist-toss-api.design.md](../02-design/features/risk-blacklist-toss-api.design.md)
> **Plan Doc**: [risk-blacklist-toss-api.plan.md](../01-plan/features/risk-blacklist-toss-api.plan.md)

> ⚠️ **배포/검증 대기 (NOT DEPLOYED)**: 본 분석은 로컬 구현본(`Refresh_Risk_Blacklist_KRX_KIND_code.js`)과 `swing_scanner_code.js`의 `[TOSS-RISK]` 블록에 대한 정적 코드 대조이다. 라이브 n8n `Risk Blacklist Updater` 노드에는 **아직 미반영**이며, Design 11.2절 6~7번(Manual Trigger 대조 검증 / 3영업일 실행 로그 확인)은 **미수행(Not Implemented)** 상태다. 따라서 아래 Match Rate는 "코드 정합성"이며 "런타임 검증"은 포함하지 않는다.

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

KRX 스크래핑 3종(정리매매/투자경고/투자위험)을 토스 Open API `/api/v1/stocks/{symbol}/warnings`로 대체하는 설계가 실제 코드에 정확히 반영되었는지, 관리종목(Naver)·KIND 로직 회귀가 없는지, Fail-Safe 폴백/매핑 표/알림 문구가 Design과 일치하는지 라인 단위로 검증한다.

### 1.2 Analysis Scope

- **Design Document**: `docs/02-design/features/risk-blacklist-toss-api.design.md`
- **Implementation (Risk Blacklist Updater)**: `Refresh_Risk_Blacklist_KRX_KIND_code.js` (신규, 295 lines)
- **Implementation (Swing Scanner 저장)**: `swing_scanner_code.js` L1758–L1767 (`[TOSS-RISK]` 블록)
- **Reference only (비교 대상 아님)**: `Refresh_Risk_Blacklist_KRX_KIND_ORIGINAL.js` (구버전 Naver+KIND)
- **Analysis Date**: 2026-07-10

> **참고**: `ORIGINAL.js`는 Naver+KIND만 있는 구조가 다른 구버전 파일이므로 회귀(FR-02) 판정의 절대 기준으로 삼지 않는다. FR-02는 "Design이 명시한 무변경 대상 함수의 동작 동일성" 기준으로 판정한다.

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 Functional Requirements (Plan §3.1)

| FR | 요구사항 | 근거 코드 | 상태 |
|----|----------|-----------|------|
| FR-01 | KRX 정리매매/투자경고/투자위험 3종 제거 + 토스 `/warnings` 대체 | `KRX_BLDS`에 4종만 존재(L74–79, MDCSTAT21201/21401/21701/22801) — 23701/23101/23401 제거됨. `fetchTossWarnings` 신설(L193–214) | ✅ Match |
| FR-02 | `fetchNaverAdminStocks`, `fetchKindCodes` 동작 무변경 (회귀 방지) | `fetchNaverAdminStocks`(L32–57): 동일 3 URL·`code=(\d{6})`·200ms sleep 로직 유지. `fetchKindCodes`(L121–147): 동일 form·`latin1`·`mso-number-format` 정규식 유지 | ✅ Match (동작 동일) |
| FR-03 | 토스 API 키 미설정/오류 시 캐시 유지 폴백 | 키 없음 → `skippedNoKey` 빈 결과(L197–200); 개별 오류 → `fetchTossAPI` catch → `null`(L170); 전체 0건 → 캐시 유지(L245–249) | ✅ Match |
| FR-04 | `/warnings` 대상을 1차 필터 통과 종목으로 한정 | `store.lastFilteredUniverse.symbols`만 사용(L238–240); 전체 유니버스 미사용 | ✅ Match |
| FR-05 | 텔레그램 알림에 Toss 소스 반영 | `Toss(정리매매·경고·위험): ... N개 (검사 N개)`(L267) | ✅ Match |

### 2.2 Design §4.2 매핑 표 (`RISK_WARNING_TYPES`)

| 검증 항목 | Design 기대값 | 실제 코드 (L152) | 상태 |
|-----------|---------------|------------------|------|
| `LIQUIDATION_TRADING` 포함 | ✅ | 포함 | ✅ |
| `INVESTMENT_WARNING` 포함 | ✅ | 포함 | ✅ |
| `INVESTMENT_RISK` 포함 | ✅ | 포함 | ✅ |
| `OVERHEATED` 편입 | 보수적 미편입(§4.2 각주) | 미편입 | ✅ |
| `VI_STATIC/VI_DYNAMIC/VI_STATIC_AND_DYNAMIC` | 미편입 | 미편입 | ✅ |
| `STOCK_WARRANTS` | 미편입 | 미편입 | ✅ |

`RISK_WARNING_TYPES = new Set(['LIQUIDATION_TRADING', 'INVESTMENT_WARNING', 'INVESTMENT_RISK'])` — **정확히 3종만**. Design 4.2 각주와 완전 일치. ✅

### 2.3 Design §4.3 `fetchTossWarnings` 함수 명세

| 명세 항목 | Design (§4.3) | 실제 코드 | 상태 |
|-----------|---------------|-----------|------|
| concurrency | `mapLimit(symbols, 6, ...)` | `TOSS_WARNINGS_CONCURRENCY = 6`(L153), `mapLimit(symbols, 6, ...)`(L203) | ✅ |
| warningType hit 판정 | `resp.some(w => RISK_WARNING_TYPES.has(w.warningType))` | 동일 + null-guard `w && w.warningType`(L206) | ✅ (더 견고) |
| 배열 아닐 때 무시 | `Array.isArray(resp)` 가드 | 동일(L206) | ✅ |
| 에러 수집 | `errors.push({symbol, message})` | `mapLimit` 내부 errors 수집 → `errorCount`(L212) | 🔵 Changed |
| 반환 구조 | `{ codes, errors }` | `{ codes, errorCount, checked, skippedNoKey }` | 🔵 Changed |
| 엔드포인트 경로 | `fetchTossAPI('/stocks/${symbol}/warnings')` (§4.3 스니펫) | `fetchTossAPI('/api/v1/stocks/' + symbol + '/warnings')`(L205) | ✅ (impl이 정답, 아래 Note 참조) |
| 404 개별 스킵 | `catch` 후 개별 스킵 | `fetchTossAPI`가 모든 오류를 `null` 반환 → 자동 스킵(L170) | ⚠️ 부분 (404와 401/403 구분 없음) |

> **Note (Design 내부 불일치, impl 정답)**: Design §4.1은 경로를 `/api/v1/stocks/{symbol}/warnings`로, `TOSS_API_BASE`를 `https://openapi.tossinvest.com`으로 명시한다. 반면 §4.3 코드 스니펫은 `/api/v1` 접두사가 누락된 `'/stocks/${symbol}/warnings'`로 적혀 있다. 실제 코드(L205)는 §4.1을 따라 `/api/v1` 포함 — **구현이 옳고, Design §4.3 스니펫이 오기**이다. → Design 문서 수정 필요(§10).

> **반환 구조 변경(🔵)**: Design은 `{ codes, errors }`(errors=상세 배열), 구현은 `{ codes, errorCount, checked, skippedNoKey }`. 텔레그램 알림에 필요한 카운터(검사 수/오류 수/스킵 사유)를 담기 위한 확장으로, Design 의도(에러 수집 후 알림 반영)를 만족한다. 다만 **개별 심볼 오류 메시지가 소실**된다(아래 2.5 Gap 참조).

### 2.4 Design §6.1 에러 케이스 테이블

| Case | Design 처리 | 실제 코드 | 상태 |
|------|-------------|-----------|------|
| `store.tossApiKey` 미설정 | 빈 결과, 기존 소스만 사용 | `skippedNoKey=true` 빈 결과(L197–200), 알림 `⏭️(키 없음, 스킵)`(L258) | ✅ |
| 토스 401/403 | 개별 실패 처리 + **3건 이상 연속 실패 시 `notifyOncePerDay('toss_warnings_fail')` 1회 발송** | `fetchTossAPI` catch → `null` 반환(L170). HTTP 오류가 `mapLimit` errors에 잡히지 않아 **`errorCount`가 0으로 집계됨**. `notifyOncePerDay` 미구현 | ❌ Not implemented |
| 토스 404 (stock-not-found) | 해당 종목만 스킵 | `null` 반환 → 자동 스킵(정상). 단 404/401 구분 없음 | ⚠️ 부분 |
| `lastFilteredUniverse` 없음 | 호출 스킵, 기존 소스만 진행 | `tossSymbols=[]` → `fetchTossWarnings` 빈 결과(L201), 알림 `⏭️(전일 필터 종목 없음, 스킵)`(L259) | ✅ |
| 전체 소스 0건 | `prev.riskCodes` 캐시 유지 + 알림 | L245–249 캐시 유지 분기 | ✅ |

### 2.5 store.lastFilteredUniverse 저장 로직 (Design §3.1 / §2.2)

| 검증 항목 | Design 기대 | 실제 코드 (`swing_scanner_code.js` L1762–1765) | 상태 |
|-----------|-------------|-----------------------------------------------|------|
| 저장 위치 | `[SCAN-LOG]` 직후, `_lastFullFinish` 대입 직전 | L1758(TOSS-RISK) → L1769(`_lastFullFinish`) 사이. 정확히 일치 | ✅ |
| 구조 | `{ symbols: string[], updatedAt: ISO }` | `{ symbols, updatedAt: new Date().toISOString() }` | ✅ |
| 6자리 코드 추출 | ALL_TICKERS(`"005930.KS"`)에서 6자리만 | `ALL_TICKERS.map(t => t.slice(0,6))`. ALL_TICKERS는 `rc(6자리) + ".KS"/".KQ"`(L1029)이므로 `.slice(0,6)` = 6자리 코드. 정확 | ✅ |
| 실패 격리 | 저장 실패해도 스캔 중단 없음 | `try/catch` 무시(L1766) | ✅ |

> **Minor (컨벤션)**: L723에 이미 `getCode(sym)`(`.KS`/`.KQ` 접미사 제거) 헬퍼가 존재하나 TOSS-RISK 블록은 `t.slice(0,6)`을 사용. 결과는 동일하나 기존 헬퍼 미재사용 → §7 컨벤션 감점 요인(경미).

### 2.6 Design §11.2 구현 순서 반영 여부

| # | 항목 | 상태 | 근거 |
|---|------|------|------|
| 1 | Swing Scanner 말미 `lastFilteredUniverse` 저장 | ✅ 완료 | L1758–1767 |
| 2 | `RISK_WARNING_TYPES` 상수 + `fetchTossWarnings` 추가 | ✅ 완료 | L152, L193–214 |
| 3 | `lastFilteredUniverse` 존재 시 호출 / 없으면 스킵 | ✅ 완료 | L238–240 + 빈 배열 스킵 |
| 4 | `allCodes` 병합 + `sourceCounts.TossWarnings` 기록 | ✅ 완료 | L241–242 |
| 5 | 텔레그램 알림 문구 §5 형식으로 갱신 | ✅ 완료 | L263–268 |
| 6 | Manual Trigger 샘플 대조 검증 | ❌ 미수행 | 배포/검증 대기 |
| 7 | 3영업일 실행 로그 확인 | ❌ 미수행 | 배포/검증 대기 |

### 2.7 Out of Scope 무침습 확인 (Plan §2.2)

| 항목 | 기대 | 결과 |
|------|------|------|
| 관리종목(Naver) 소스 | 무변경 | ✅ `fetchNaverAdminStocks` 동작 동일 |
| KIND 실질심사 | 무변경 | ✅ `fetchKindCodes` 동작 동일 |
| KRX 거래정지/관리종목/투자주의/투자주의환기 4종 | best-effort 유지 | ✅ `KRX_BLDS` 4종 유지(L74–79) |
| 테마 블랙리스트 | 손대지 않음 | ✅ 본 파일에 테마 로직 없음 |

### 2.8 Match Rate Summary

```
┌───────────────────────────────────────────────────────┐
│  Overall Design Match Rate: 88%  (코드 정합성 기준)     │
│  ⚠️ 배포/런타임 검증 미포함 (§11.2 6~7 Not Implemented) │
├───────────────────────────────────────────────────────┤
│  ✅ Match:            29 items (85%)                    │
│  🔵 Changed(수용가능):  2 items (6%)                    │
│  ⚠️ Partial:           2 items (6%)                    │
│  ❌ Not implemented:    1 item  (3%)  ← 401/403 알림     │
└───────────────────────────────────────────────────────┘
비고: §11.2 6~7(배포/검증)은 계획상 미수행이므로 분모에서 제외.
```

---

## 3. Code Quality Analysis

### 3.1 Complexity Analysis

| 함수 | 파일 | 복잡도 | 상태 |
|------|------|--------|------|
| `fetchTossWarnings` | Risk...code.js | 낮음 (단일 루프+가드) | ✅ Good |
| `mapLimit` | Risk...code.js | 낮음 | ✅ Good |
| 메인 try 블록 | Risk...code.js | 중간 (4소스 순차 병합) | ✅ 허용 범위 |

### 3.2 Code Smells

N/A — n8n 단일 Function 노드 특성상 표준 웹앱 code smell 기준 대부분 비해당. 발견된 경미 항목:
| 유형 | 위치 | 설명 | 심각도 |
|------|------|------|--------|
| 헬퍼 미재사용 | swing L1763 | 기존 `getCode` 대신 `.slice(0,6)` | 🟢 Info |
| 하드코딩 시크릿 | Risk L15–16 | `BOT`/`CHAT` 텔레그램 토큰 평문 | 🟡 (기존 파일 관행, 본 기능 신규 아님) |

### 3.3 Security Issues

| 심각도 | 위치 | 이슈 | 권장 |
|--------|------|------|------|
| 🟢 Info | Risk L155–171 | 토스 API 키는 `store.tossApiKey`에서만 읽고 에러 메시지·알림에 미노출 — Design §7 준수 | 유지 |
| 🟡 Warning | Risk L15–16 | 텔레그램 BOT 토큰/CHAT ID 코드 평문(본 기능 도입분 아님, 기존 노드 관행) | 후속 과제로 env/static data 이전 검토 |

---

## 4. Performance Analysis

N/A (표준 웹 응답시간 지표 비해당). n8n 관점 참고:
- `/warnings`는 종목별 개별 호출이나 대상이 1차 필터(~630개)로 한정 + concurrency 6(L153). Plan §3.2 NFR(2분 이내) 목표는 **런타임 미검증(배포 대기)**.
- `fetchTossAPI` timeout 8000ms(L169)로 hang 방지.

---

## 5. Test Coverage

N/A — 자동화 테스트 프레임워크 없음(n8n Function 노드, 순수 JS). Design §8 테스트는 수동(Manual Trigger + Log Viewer + `n8n_list_executions` MCP) 기반이며 **미수행**.

| 테스트(Design §8.2) | 상태 |
|---------------------|------|
| Happy path (정리매매/경고/위험 정확 선별) | ⏳ 배포 후 검증 대기 |
| API 키 미설정 폴백 | 🟢 코드상 보장(L197–200), 런타임 미검증 |
| `lastFilteredUniverse` 없음 스킵 | 🟢 코드상 보장(L201), 런타임 미검증 |
| 404 개별 스킵 무영향 | 🟢 코드상 보장(L170), 런타임 미검증 |

---

## 6. Clean Architecture Compliance (n8n Function 노드 구조로 대체)

> Design §9: 표준 Presentation/Application/Domain/Infrastructure 레이어 **비적용**. n8n 함수 단위 책임 분리로 대체 평가.

### 6.1 Layer(함수 역할) 배치 검증 (Design §9.1 / §9.4)

| 역할 | Design 위치 | 실제 위치 | 상태 |
|------|-------------|-----------|------|
| Orchestration | 메인 try 블록 | L218–281 (4소스 병합) | ✅ |
| Source Adapter: `fetchNaverAdminStocks` | 노드 내부 | L32–57 | ✅ |
| Source Adapter: `fetchKrxAllCodes` | 노드 내부 | L102–118 | ✅ |
| Source Adapter: `fetchKindCodes` | 노드 내부 | L121–147 | ✅ |
| Source Adapter: `fetchTossWarnings` (신규) | 노드 내부 | L193–214 | ✅ |
| `RISK_WARNING_TYPES` 상수 | 노드 상단 | L152 | ✅ |
| Infra(HTTP): `http`, `fetchTossAPI` | 헬퍼 | L13, L159–171 | ✅ |
| `lastFilteredUniverse` 저장 | Swing Scanner 말미 | swing L1762 | ✅ |

### 6.2 Dependency Rule (Design §9.2)

| 규칙 | 준수 여부 |
|------|-----------|
| Source Adapter 간 상호 호출 없음(독립·실패 격리) | ✅ 각 fetch* 함수 독립, 상호 미호출 |
| Orchestration만 결과 병합 | ✅ 메인 try에서만 병합(L219–242) |
| `fetchTossWarnings → fetchTossAPI → http` 체인 | ✅ L205→L163 |

### 6.3 Architecture Score

```
┌─────────────────────────────────────────────┐
│  n8n 노드 구조 준수: 100%                    │
│  (함수 역할 분리·의존 방향·실패 격리 완전 일치)│
└─────────────────────────────────────────────┘
```

---

## 7. Convention Compliance (Design §10)

### 7.1 Naming Convention

| 항목 | 규칙(Design §10.1) | 실제 | 상태 |
|------|--------------------|------|------|
| 수집 함수 `fetch` 접두사 | `fetchTossWarnings` | 준수 | ✅ |
| 상수 UPPER_SNAKE_CASE | `RISK_WARNING_TYPES`, `TOSS_API_BASE`, `TOSS_WARNINGS_CONCURRENCY` | 준수 | ✅ |
| store 네임스페이스 | `store.lastFilteredUniverse`, `store.blacklist.*` | 준수 | ✅ |
| 텔레그램 dedup 키 | `notifyOncePerDay('toss_warnings_fail', ...)` (Design §10.1 예시) | **미사용** (아래 참조) | ⚠️ |

### 7.2 실패 처리 패턴 (Design §10.4 / Plan §7.2)

| 항목 | Design 규칙 | 실제 | 상태 |
|------|-------------|------|------|
| 서킷브레이커 재사용 | "기존 서킷브레이커 패턴 재사용" | 신규 파일에 **서킷브레이커 없음** (`krxState`/`openCircuit`/`circuitActive` 부재) | ❌ |
| `notifyOncePerDay` 재사용 | "재사용" 명시(§10.1/§10.4/Plan §7.2) | 신규 파일은 dedup 없는 `notify()`만 사용(L20–24) | ❌ |
| `mapLimit(list, limit, worker)` 재사용 | concurrency 6 | ✅ L174–189, 6 적용 | ✅ |
| 캐시 유지 폴백 | 재사용 | ✅ L245–249, L289–290 | ✅ |

### 7.3 Convention Score

```
┌─────────────────────────────────────────────┐
│  Convention Compliance: 78%                  │
├─────────────────────────────────────────────┤
│  Naming:            95%                      │
│  실패처리 패턴:      55% (서킷/dedup 알림 부재)│
│  동시성/캐시 폴백:   100%                     │
│  헬퍼 재사용:        85% (getCode 미재사용)   │
└─────────────────────────────────────────────┘
```

---

## 8. Overall Score

```
┌─────────────────────────────────────────────┐
│  Overall Score: 87/100                       │
├─────────────────────────────────────────────┤
│  Design Match:        88 points              │
│  Code Quality:        90 points              │
│  Security:            88 points              │
│  Testing:             N/A (배포 후 수동 검증) │
│  Performance:         N/A (런타임 미검증)     │
│  Architecture(n8n):  100 points              │
│  Convention:          78 points              │
└─────────────────────────────────────────────┘
상태: 배포/검증 대기 — 런타임 검증 완료 시 재평가 필요.
```

---

## 9. Recommended Actions

### 9.1 Immediate (배포 전 처리 권장)

| 우선 | 항목 | 위치 | 비고 |
|------|------|------|------|
| 🟡 1 | **401/403 3건↑ 연속 실패 시 `notifyOncePerDay('toss_warnings_fail')` 알림 구현** — 현재 `fetchTossAPI`가 오류를 `null`로 삼켜 `errorCount`가 항상 0. 인증 만료를 감지 못함 | Risk L159–171, L203–213 | Design §6.1 미충족 항목. `fetchTossAPI`가 status를 상위로 전달하거나 `fetchTossWarnings`에서 오류/스킵을 별도 집계 필요 |
| 🟡 2 | **서킷브레이커/`notifyOncePerDay` 패턴 재도입 검토** — Design §10이 재사용을 명시했으나 신규 파일에 부재. 라이브 노드 배포 시 기존 노드의 서킷 로직과 병합 필요 | Risk 전역 | 라이브 노드 코드에 이미 서킷 로직이 있다면 병합 시 자연 해소될 수 있음(배포 시 확인) |

### 9.2 Short-term

| 우선 | 항목 | 위치 |
|------|------|------|
| 🟢 1 | Design §11.2 6~7 수행: Manual Trigger 샘플(10~20종목) KRX vs 토스 대조표 작성, 3영업일 실행 로그 확인 | n8n |
| 🟢 2 | `t.slice(0,6)` → 기존 `getCode(t)` 헬퍼로 통일(가독성) | swing L1763 |

### 9.3 Long-term (backlog)

| 항목 | 비고 |
|------|------|
| 텔레그램 BOT/CHAT 토큰 static data 이전 | 기존 노드 공통 관행, 본 기능 범위 밖 |
| 테마 블랙리스트 정치 필터 재배포 | 별도 Plan (Plan §2.2 Out of Scope) |

---

## 10. Design Document Updates Needed

- [ ] **§4.3 코드 스니펫 경로 수정**: `fetchTossAPI('/stocks/${symbol}/warnings')` → `fetchTossAPI('/api/v1/stocks/${symbol}/warnings')` (§4.1과 일치, 구현이 정답).
- [ ] **§4.3 반환 구조 반영**: `{ codes, errors }` → 실제 `{ codes, errorCount, checked, skippedNoKey }`로 명세 갱신.
- [ ] **§6.1 401/403 알림 조건 명확화**: `errorCount`가 HTTP 오류를 집계하지 못하는 현 구조 반영 또는 구현 보완(9.1-1과 연동).

---

## 11. Next Steps

- [ ] 🟡 401/403 실패 감지·알림 구현(9.1-1) — Design §6.1 미충족 해소
- [ ] 서킷브레이커/`notifyOncePerDay` 재사용 여부 배포 시 확정(9.1-2)
- [ ] Design 문서 3건 수정(§10)
- [ ] 라이브 n8n 배포 → Manual Trigger 대조 검증 → 3영업일 로그 확인
- [ ] 검증 완료 후 재분석 및 완료 보고서(`risk-blacklist-toss-api.report.md`) 작성

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-10 | Initial gap analysis (배포 전, 코드 정합성 기준) | kevin |

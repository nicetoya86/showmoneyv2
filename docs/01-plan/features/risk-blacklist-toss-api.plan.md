# risk-blacklist-toss-api Planning Document

> **Summary**: 매일 실패하는 KRX 7종 스크래핑 중 토스 Open API로 대체 가능한 3종(정리매매/투자경고/투자위험)만 전환하고, 대체 불가한 관리종목/KIND/테마 블랙리스트는 현행 유지 및 후속 과제로 분리한다.
>
> **Project**: showmoneyv2 (Autostock Swing Scanner)
> **Version**: n/a (n8n workflow, `algo-v1.0` 기준)
> **Author**: kevin
> **Date**: 2026-07-09
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 리스크 블랙리스트의 KRX 7종 스크래핑(거래정지/관리종목/투자주의/투자주의환기/투자경고/투자위험/정리매매)이 매일 아침 실패해 "❌(캐시없이 진행)" 상태로 방치되고 있음. |
| **Solution** | 이미 연동된 토스증권 Open API `/api/v1/stocks/{symbol}/warnings`로 대체 가능한 3종(정리매매·투자경고·투자위험)만 전환하고, 대체 불가 항목(관리종목/KIND 실질심사/테마·섹터)은 현행 소스를 그대로 유지한다. |
| **Function/UX Effect** | 매일 08:30 텔레그램 알림에서 KRX 실패 문구가 사라지고 정리매매·투자경고·투자위험 상태가 안정적으로 반영된다. 테마 블랙리스트 과다 제외 문제는 이번 범위 밖(별도 Plan 필요). |
| **Core Value** | 외부 스크래핑(KRX data.krx.co.kr) 의존도를 낮춰 리스크 블랙리스트 갱신의 신뢰성을 확보하고, 이미 도입된 토스 API 인프라의 활용도를 높인다. |

---

## 1. Overview

### 1.1 Purpose

`Risk Blacklist Updater` n8n 노드가 매일 08:30 KST에 갱신하는 리스크 블랙리스트 중, KRX(`data.krx.co.kr`) 7종 스크래핑이 매일 실패(`❌ 캐시없이 진행`)하는 문제를 해결한다. 이미 스윙 스캐너에 연동된 토스증권 Open API로 대체 가능한 항목만 우선 전환하고, 대체 불가능한 항목은 명확히 구분해 현행 유지한다.

### 1.2 배경

- 2026-07-06~07-09 실행 로그 분석 결과, 리스크 블랙리스트 갱신 텔레그램 알림에 매일 `KRX: ❌(캐시없이 진행)` 표시 확인. 라이브 n8n 노드(`Risk Blacklist Updater`) 코드 직접 조회로 KRX MDCSTAT 7종(거래정지/관리종목/투자주의환기/정리매매/투자주의/투자경고/투자위험)이 모두 best-effort로만 시도되고 실패 시 그냥 스킵되는 구조임을 확인.
- 같은 대화에서 토스 Open API 도입 가능성을 조사한 결과:
  - `GET /api/v1/stocks/{symbol}/warnings` — `warningType` enum: `LIQUIDATION_TRADING`(정리매매), `OVERHEATED`, `INVESTMENT_WARNING`(투자경고), `INVESTMENT_RISK`(투자위험), `VI_STATIC`/`VI_DYNAMIC`, `STOCK_WARRANTS` 제공 확인.
  - **관리종목, 투자주의, 투자주의환기, KIND 실질심사, 테마/섹터 분류는 토스 공식 API 범위 밖**으로 확인됨(공식 문서 기준; 테마/섹터는 비공식 커뮤니티 도구만 지원).
- 테마 블랙리스트(네이버 전체 266개 테마 무차별 차단, 유니버스의 69% 제외) 이슈는 별도로 이미 논의됨 — 토스로 대체 불가하며, 기존에 작성된 정치 테마 키워드 필터(`Refresh_Theme_Blacklist_Naver_code.js`, 미배포 상태)를 적용하는 것이 여전히 유효한 다음 단계임. 이번 Plan의 Scope에서는 제외.

### 1.3 Related Documents

- 참고 노드 코드: `Refresh_Risk_Blacklist_KRX_KIND_ORIGINAL.js` (로컬 스냅샷, 라이브 노드와 유사)
- 라이브 n8n 워크플로우: `Autostock Swing Scanner (benchmark-best + profit-protection)` (ID: `ScHaeFdneOoH1ZNZ`) — `Risk Blacklist Updater` 노드
- 토스 API 기존 연동: `swing_scanner_code.js` 내 `TOSS_API_BASE`, `fetchTossAPI`, `fetchTossMinuteCandles` 등 (2026-06-30 추가)
- 외부 문서: [토스증권 Open API 가이드](https://developers.tossinvest.com/docs/stock-info)
- 별도 후속 문서(미작성): 테마 블랙리스트 정치 필터 재배포 Plan

---

## 2. Scope

### 2.1 In Scope

- [ ] `Risk Blacklist Updater` 노드에 토스 `/api/v1/stocks/{symbol}/warnings` 호출 헬퍼 추가 (기존 `fetchTossAPI` 패턴 재사용)
- [ ] KRX_BLDS 중 정리매매(`MDCSTAT23701`)/투자경고(`MDCSTAT23101`)/투자위험(`MDCSTAT23401`) 3종을 토스 결과(`LIQUIDATION_TRADING`/`INVESTMENT_WARNING`/`INVESTMENT_RISK`)로 대체
- [ ] `/warnings` 호출 대상은 전체 유니버스(~3,000종목)가 아니라 스윙 스캐너가 1차 필터링한 종목 풀(628~631개 수준)로 한정해 API 콜 수 절감
- [ ] 토스 API 미승인/오류 시 기존 리스크 블랙리스트 캐시 유지 폴백(기존 서킷브레이커·`notifyOncePerDay` 패턴 재사용)
- [ ] 텔레그램 성공/실패 알림 문구에 Toss 소스 결과 반영 (`네이버 N개 | KIND N개 | Toss(정리매매/경고/위험) N개` 형태)
- [ ] 배포 전 샘플 종목 대상 KRX 스크래핑 결과 vs 토스 `/warnings` 결과 대조 검증

### 2.2 Out of Scope

- 관리종목(Naver 소스), 투자주의, 투자주의환기, KIND 실질심사 — 토스 미지원 확인됨, 변경 없이 현행 유지
- 테마 블랙리스트 정치 필터 적용 — 토스로 대체 불가, 별도 Plan으로 분리
- 토스 API 기반 시세/캔들/보유내역 등 기존 기능 변경
- KRX 거래정지/관리종목/투자주의/투자주의환기 4종 스크래핑 로직 제거 여부 결정 (이번 범위에서는 실패해도 best-effort로 계속 시도, 제거는 다음 단계에서 검토)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | KRX 정리매매/투자경고/투자위험 3종을 토스 `/warnings` 호출로 대체 | High | Pending |
| FR-02 | 관리종목(Naver)+KIND 실질심사 소스는 코드 변경 없이 유지 (회귀 방지) | High | Pending |
| FR-03 | 토스 API 키 미설정/오류 시 기존 리스크 블랙리스트 캐시를 유지하는 폴백 | High | Pending |
| FR-04 | `/warnings` 호출 대상을 스윙 스캐너 1차 필터 통과 종목으로 한정 | Medium | Pending |
| FR-05 | 텔레그램 성공/실패 알림 문구에 Toss 소스 결과 반영 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | `/warnings` per-symbol 호출 방식이므로 08:30 Risk Blacklist 갱신 스텝 전체 실행시간이 기존(약 30~40초) 대비 과도하게 늘어나지 않아야 함(목표 2분 이내) | n8n execution duration 로그 비교 |
| Reliability | 토스 API 실패 시 기존 KRX 실패와 동일하게 캐시 유지, 서킷 브레이커 로직 재사용 | 토스 API 키 임시 무효화 후 동작 확인 |
| Security | 토스 API 키(`store.tossApiKey`)는 n8n workflow static data에만 저장, 코드/로그/텔레그램 알림에 평문 노출 금지 | 코드 리뷰 + 알림 메시지 샘플 확인 |
| Consistency | 토스 `warningType`과 KRX MDCSTAT 분류가 1:1 대응하지 않을 가능성 대비, 매핑 기준을 문서화 | Design 문서에 매핑 표 명시 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `Risk Blacklist Updater` 노드가 토스 `/warnings` 결과로 정리매매/투자경고/투자위험을 반영
- [ ] 관리종목/KIND 로직 무변경 확인(diff 검토)
- [ ] 텔레그램 알림에서 "KRX ❌(캐시없이 진행)" 문구가 토스 결과 기반 문구로 대체됨
- [ ] 3영업일 연속 실행 로그에서 에러 없이 성공(success) 상태 확인

### 4.2 Quality Criteria

- [ ] 기존 코드 스타일(서킷브레이커, `notifyOncePerDay`, `store.blacklist` 네임스페이스) 유지
- [ ] n8n Function 노드 배포 전 로컬 문법 검증
- [ ] 배포 전 샘플 종목(10~20개) 기준 KRX 결과와 토스 결과 대조표 작성 및 검토

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 토스 `/warnings`가 종목별 개별 호출만 지원 → 전체 유니버스 조회 시 API 과다호출/레이트리밋 | High | High | 스윙 스캐너 1차 필터 통과 종목(~630개)에만 적용, 배치/동시성 제한(concurrency 6 수준 유지) |
| 토스 API 키 만료/미승인 상태로 전면 실패 | High | Medium | 기존 캐시 유지 폴백 + 실패 시 기존 KRX 스크래핑 병행 운영(즉시 KRX 로직 제거하지 않음) |
| `/warnings`의 `warningType`이 KRX MDCSTAT 분류와 명칭/기준이 다를 가능성 | Medium | Medium | 배포 전 샘플 종목으로 KRX 결과와 토스 결과 대조 검증, Design 문서에 매핑 표 명시 |
| 관리종목 등 토스 미지원 항목이 실수로 함께 제거되어 필터링 공백 발생 | High | Low | 관리종목/KIND 로직은 이번 변경에서 손대지 않음(코드 diff로 재확인) |

---

## 6. Architecture Considerations

> 참고: 이 프로젝트는 Next.js/React 기반 웹앱이 아니라 **n8n 워크플로우 Function 노드로 구현된 자동매매 스캐너**이므로, 아래 6.2/6.3 항목 중 프레임워크·상태관리·스타일링 등은 해당 없음(N/A)으로 표기한다.

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 해당 없음 | - | ☐ |
| **Dynamic** | 해당 없음 | - | ☐ |
| **Enterprise** | 해당 없음 | - | ☐ |
| **N/A (n8n Workflow Automation)** | Function 노드 + workflow static data, 외부 스크래핑/API 연동 | 트레이딩 알고리즘 자동화 | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 리스크 데이터 소스 | KRX 스크래핑 유지 / 토스 API 전환 / 하이브리드 | **하이브리드** (정리매매·투자경고·투자위험은 토스, 관리종목·KIND는 기존 소스) | 토스가 관리종목/KIND를 지원하지 않으므로 전면 전환 불가 |
| 호출 대상 범위 | 전체 유니버스 / 1차 필터 통과 종목만 | **1차 필터 통과 종목만** | `/warnings`가 종목별 개별 호출이라 전체 대상 시 API 콜 수 과다 |
| 실패 시 동작 | 즉시 에러 / 캐시 유지 | **캐시 유지** | 기존 `notifyOncePerDay` + 캐시 폴백 패턴과 일관성 유지 |
| Framework / State Management / API Client / Form Handling / Styling / Testing | (웹앱 항목) | N/A | n8n Function 노드 기반, 해당 카테고리 없음 |

### 6.3 노드 구조 (Clean Architecture 대체)

```
Risk Blacklist Updater (n8n Function 노드)
├─ fetchNaverAdminStocks()        — 유지 (관리종목)
├─ fetchKrxAllCodes()             — 부분 축소 검토
│    ├─ 거래정지 / 관리종목 / 투자주의환기 / 투자주의  — best-effort 유지 (Out of Scope)
│    └─ 정리매매 / 투자경고 / 투자위험              — 토스로 대체 (In Scope)
├─ fetchKindCodes()               — 유지 (KIND 실질심사)
└─ fetchTossWarnings(symbols)     — 신규 추가 (정리매매/투자경고/투자위험)
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [ ] `CLAUDE.md` 코딩 컨벤션 섹션 — 해당 없음 (n8n 노드 코드는 별도 컨벤션 없이 기존 패턴 준수)
- [x] 기존 노드 코드의 암묵적 컨벤션 존재: 서킷브레이커, `notifyOncePerDay`, `store.blacklist.*` 네임스페이스, 텔레그램 알림 포맷
- [ ] ESLint/Prettier/TypeScript — 해당 없음 (n8n Function 노드는 순수 JS, 별도 빌드 파이프라인 없음)

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| Toss `/warnings` 호출 헬퍼 명명 | 미존재 | `fetchTossWarnings(symbols)` 형태로 기존 `fetchTossAPI` 패턴 재사용 | High |
| 소스별 카운트 알림 포맷 | `네이버 N개 \| KRX ✅/❌ \| KIND N개` | `네이버 N개 \| KIND N개 \| Toss(정리매매/경고/위험) N개` 형태로 확장 | Medium |
| 캐시 실패 폴백 | 기존 `keptCache` 패턴 존재 | 토스 실패 시에도 동일 패턴 적용 | High |

### 7.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `store.tossApiKey` (n8n workflow static data) | 토스 Open API 인증 | n8n workflow 전역 | ☐ (기존 candles/prices/holdings 호출에서 이미 사용 중 — 신규 설정 불필요) |

### 7.4 Pipeline Integration

해당 없음 — 9-phase Development Pipeline이 아닌 기존 운영 중인 n8n 워크플로우에 대한 개선 작업.

---

## 8. Next Steps

1. [ ] Design 문서 작성 (`risk-blacklist-toss-api.design.md`) — 토스 `warningType` ↔ KRX MDCSTAT 매핑 표 포함
2. [ ] 샘플 종목(10~20개) 대상 KRX 스크래핑 결과 vs 토스 `/warnings` 결과 대조 검증
3. [ ] `Risk Blacklist Updater` 노드 코드 수정 및 로컬 문법 검증
4. [ ] 라이브 n8n 노드 배포 후 3영업일 실행 로그로 안정성 확인
5. [ ] (별도 Plan) 테마 블랙리스트 정치 필터 재배포 — 이번 범위 밖

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-09 | Initial draft | kevin |

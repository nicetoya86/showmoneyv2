# risk-blacklist-toss-api Design Document

> **Summary**: `Risk Blacklist Updater` n8n 노드 내부에서 KRX 정리매매/투자경고/투자위험 3종 스크래핑을 토스 Open API `/warnings` 호출로 교체하는 구현 설계.
>
> **Project**: showmoneyv2 (Autostock Swing Scanner)
> **Version**: n/a (n8n workflow, `algo-v1.0` 기준)
> **Author**: kevin
> **Date**: 2026-07-09
> **Status**: Draft
> **Planning Doc**: [risk-blacklist-toss-api.plan.md](../../01-plan/features/risk-blacklist-toss-api.plan.md)

### Pipeline References (if applicable)

N/A — 9-phase Development Pipeline 대상 프로젝트가 아니며, 운영 중인 n8n 워크플로우에 대한 개선 작업이므로 Phase 1~4 문서는 해당 없음.

---

## 1. Overview

### 1.1 Design Goals

- KRX `data.krx.co.kr` 스크래핑 중 매일 실패하는 정리매매(`MDCSTAT23701`)/투자경고(`MDCSTAT23101`)/투자위험(`MDCSTAT23401`) 3종을 토스 Open API `/api/v1/stocks/{symbol}/warnings`로 안정적으로 대체한다.
- 기존 `Risk Blacklist Updater` 노드의 서킷브레이커, 캐시 폴백, 텔레그램 알림 패턴을 그대로 재사용해 회귀 위험을 최소화한다.
- 관리종목(Naver)·KIND 실질심사 로직은 한 줄도 건드리지 않는다.

### 1.2 Design Principles

- **최소 침습(Minimal Invasion)**: 기존 함수(`fetchNaverAdminStocks`, `fetchKindCodes`)는 그대로 두고, 신규 함수만 추가/교체한다.
- **1차 필터 이후 호출(Scoped Fetch)**: `/warnings`가 종목별 개별 호출이므로 전체 유니버스가 아니라 스윙 스캐너가 필터링한 종목 풀에만 적용한다.
- **Fail-Safe 우선**: 토스 API가 실패해도 기존 KRX 스크래핑(best-effort)과 캐시 유지 로직이 살아있어 전체 파이프라인이 멈추지 않는다.

---

## 2. Architecture

### 2.1 Component Diagram

```
┌───────────────────────┐     ┌──────────────────────────┐     ┌────────────────────────┐
│ Risk Blacklist Trigger│────▶│ Risk Blacklist Updater    │────▶│ store.blacklist.*       │
│ (n8n cron, 08:30 KST) │     │ (n8n Function Node)       │     │ (workflow static data) │
└───────────────────────┘     │  ├─ fetchNaverAdminStocks │     └────────────────────────┘
                               │  ├─ fetchKrxAllCodes      │              │
                               │  ├─ fetchKindCodes        │              ▼
                               │  └─ fetchTossWarnings ★신규│     ┌────────────────────────┐
                               └──────────────┬────────────┘     │ Telegram 알림 발송       │
                                              │                  └────────────────────────┘
                                              ▼
                               ┌──────────────────────────┐
                               │ openapi.tossinvest.com    │
                               │ GET /api/v1/stocks/       │
                               │     {symbol}/warnings     │
                               └──────────────────────────┘
```

### 2.2 Data Flow

```
[08:30 Cron 발동]
  → Naver 관리종목 스크래핑 (유지)
  → KRX 7종 중 거래정지/관리종목/투자주의/투자주의환기 4종 best-effort 시도 (유지, Out of Scope)
  → KIND 실질심사 스크래핑 (유지)
  → 스윙 스캐너 1차 필터 통과 종목 풀(628~631개) 조회
      → 종목별 fetchTossWarnings(symbol) 호출 (concurrency 제한)
      → warningType → 정리매매/투자경고/투자위험 매핑 후 riskCodes에 병합
  → 전체 결과 통합 → store.blacklist.riskCodes 갱신
  → 성공/실패 텔레그램 알림 발송 (소스별 카운트 포함)
```

> **참고**: 스윙 스캐너의 1차 필터링은 `Swing Scanner` 노드에서 실행되고 `Risk Blacklist Updater`는 08:30에 먼저 실행되므로, "스윙 스캐너가 필터링한 종목 풀"은 **전일자 캐시된 필터 결과**(`store.lastFilteredUniverse` 신규 필드, 전일 09:10 스캔 종료 시 저장)를 사용한다. 당일 최초 실행 시 캐시가 없으면 이 스텝은 스킵하고 기존 KRX 결과만 사용한다(Fail-Safe).

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `fetchTossWarnings(symbols)` | `fetchTossAPI` (기존 `swing_scanner_code.js` 헬퍼) | 토스 Open API 인증/호출 재사용 |
| `fetchTossWarnings(symbols)` | `store.lastFilteredUniverse` (신규) | 호출 대상 종목 풀 확보 |
| Risk Blacklist Updater | `store.tossApiKey` (기존) | 토스 API 인증 — 신규 설정 불필요 |

---

## 3. Data Model

### 3.1 Entity Definition (workflow static data 확장)

```javascript
// store.blacklist (기존 구조 확장)
{
  riskCodes: string[],           // 기존 — 관리종목+KRX+KIND+Toss 통합 결과 (변경 없음)
  riskUpdatedAt: string,         // 기존 — ISO timestamp
  riskSourceCounts: {            // 기존 구조에 필드 추가
    Naver: number,
    'issue/MDCSTAT21201': number,   // 거래정지 (KRX 유지, Out of Scope)
    'issue/MDCSTAT21401': number,   // 관리종목 (KRX 유지, Out of Scope)
    'issue/MDCSTAT21701': number,   // 투자주의환기 (KRX 유지, Out of Scope)
    'issue/MDCSTAT22801': number,   // 투자주의 (KRX 유지, Out of Scope)
    KIND: number,
    TossWarnings: number,         // ★신규 — 정리매매+투자경고+투자위험 토스 대체 결과 수
  },
  riskSource: string,             // 'Naver+KRX+KIND+TossWarnings' 로 갱신
  riskLastError: object | undefined,
}

// store.lastFilteredUniverse (신규 — Swing Scanner 노드가 09:10 스캔 종료 시 저장)
{
  symbols: string[],   // 1차 필터 통과 종목 코드 (628~631개 수준)
  updatedAt: string,   // ISO timestamp
}
```

### 3.2 Entity Relationships

```
[Risk Blacklist Updater]
   │ reads
   ▼
[store.lastFilteredUniverse] ◀── written by [Swing Scanner] (전일 09:10 실행 종료 시)
   │
   ▼
[Risk Blacklist Updater] → fetchTossWarnings(symbols) → [store.blacklist.riskCodes]
```

### 3.3 Database Schema

N/A — 별도 DB 없음. 모든 상태는 n8n `getWorkflowStaticData('global')`(workflow static data)에 저장(기존 방식 그대로).

---

## 4. API Specification

### 4.1 외부 API — 토스증권 Open API (신규 연동 엔드포인트)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/stocks/{symbol}/warnings` | 종목의 매수 유의사항 및 VI 발동 정보 조회 | Bearer Token (`store.tossApiKey`) |

**Response (200):**
```json
[
  {
    "warningType": "INVESTMENT_WARNING",
    "exchange": "KOSDAQ",
    "startDate": "2026-07-08",
    "endDate": null
  }
]
```
- 200 + 빈 배열: 유의사항 없음
- 404: `stock-not-found` (종목코드 오류/상장폐지 등)

### 4.2 warningType ↔ KRX MDCSTAT 매핑 표

| 토스 `warningType` | 대응 KRX MDCSTAT 분류 | 이번 범위 처리 |
|---|---|---|
| `LIQUIDATION_TRADING` | 정리매매 (`MDCSTAT23701`) | ✅ 토스로 대체 |
| `INVESTMENT_WARNING` | 투자경고 (`MDCSTAT23101`) | ✅ 토스로 대체 |
| `INVESTMENT_RISK` | 투자위험 (`MDCSTAT23401`) | ✅ 토스로 대체 |
| `OVERHEATED` | (KRX 분류 없음 — 단기과열 지정, 익일 30분 단일가매매 적용) | ✅ 토스로 편입 (2026-07-14, riskCodes 포함 확정) |
| `VI_STATIC` / `VI_DYNAMIC` / `VI_STATIC_AND_DYNAMIC` | (KRX 분류 없음 — 변동성완화장치) | riskCodes 미편입. 대신 Swing Scanner 발송 직전 실시간 확인(TOSS-CONFIRM, 2026-07-14)에서 활성 VI 감지 시 해당 발송을 보류 |
| `STOCK_WARRANTS` | (신주인수권 관련, KRX 분류 없음) | riskCodes 미편입 |
| — (대응 없음) | 관리종목 (`MDCSTAT21401`) | ❌ 유지 (Naver 소스) |
| — (대응 없음) | 투자주의 (`MDCSTAT22801`) | ❌ 유지 (KRX best-effort, 실패 허용) |
| — (대응 없음) | 투자주의환기(코) (`MDCSTAT21701`) | ❌ 유지 (KRX best-effort, 실패 허용) |
| — (대응 없음) | 거래정지 (`MDCSTAT21201`) | ❌ 유지 (KRX best-effort, 실패 허용) |
| — (대응 없음) | KIND 실질심사법인 | ❌ 유지 (KIND 소스) |

> `riskCodes`에 편입할 토스 `warningType`은 **`LIQUIDATION_TRADING`, `INVESTMENT_WARNING`, `INVESTMENT_RISK`, `OVERHEATED` 4종** (2026-07-14 `OVERHEATED` 추가) — `VI_*`는 별도로 Swing Scanner의 TOSS-CONFIRM 단계에서 실시간 처리, `STOCK_WARRANTS`는 미편입 유지.

### 4.3 내부 헬퍼 함수 명세

#### `fetchTossWarnings(symbols)`

```javascript
// Risk Blacklist Updater 노드 내부, fetchTossAPI 재사용
async function fetchTossWarnings(symbols) {
  const RISK_WARNING_TYPES = new Set(['LIQUIDATION_TRADING', 'INVESTMENT_WARNING', 'INVESTMENT_RISK', 'OVERHEATED']);
  const codes = new Set();
  const errors = [];

  await mapLimit(symbols, 6, async (symbol) => {  // 기존 mapLimit 재사용, concurrency 6
    try {
      const resp = await fetchTossAPI(`/stocks/${symbol}/warnings`);
      if (Array.isArray(resp)) {
        const hit = resp.some(w => RISK_WARNING_TYPES.has(w.warningType));
        if (hit) codes.add(symbol);
      }
    } catch (e) {
      errors.push({ symbol, message: e?.message || String(e) });
    }
  });

  return { codes: [...codes], errors };
}
```

**Request:** 없음(경로 파라미터만, symbol 6자리)
**Response 처리:** `warningType`이 `RISK_WARNING_TYPES`에 포함되면 해당 종목코드를 `riskCodes`에 추가
**Error Responses:**
- `404 stock-not-found`: 개별 종목 스킵(전체 실패로 취급하지 않음)
- 그 외 네트워크/인증 오류: `errors` 배열에 수집, 3건 이상 실패 시 텔레그램에 경고 포함

---

## 5. UI/UX Design

N/A — 사용자 UI 없음. "UX 접점"은 텔레그램 알림 문구뿐이며 아래 형식으로 변경한다.

**변경 전:**
```
✅ [리스크 블랙리스트 갱신 성공]
총 613개 종목
네이버: 102개 | KRX: ❌(캐시없이 진행) | KIND: 572개
갱신: 2026-07-08T23:30:36.207Z
```

**변경 후:**
```
✅ [리스크 블랙리스트 갱신 성공]
총 {N}개 종목
네이버: 102개 | KIND: 572개 | Toss(정리매매·경고·위험): {M}개
KRX(거래정지/관리종목/투자주의/투자주의환기): ✅/❌(캐시없이 진행)
갱신: {timestamp}
```

---

## 6. Error Handling

### 6.1 Error Case Definition

| Case | Cause | Handling |
|------|-------|----------|
| `store.tossApiKey` 미설정 | API 키 미주입 | `fetchTossAPI`가 `null` 반환(기존 동작) → `fetchTossWarnings`는 빈 결과 반환, 기존 KRX/캐시 결과만 사용 |
| 토스 API 401/403 | 키 만료/미승인 | 개별 요청 실패로 처리, 3건 이상 연속 실패 시 텔레그램 경고 1회 발송(`notifyOncePerDay` 재사용) |
| 토스 API 404 (`stock-not-found`) | 종목코드 오류/상장폐지 | 해당 종목만 스킵, 전체 실패로 취급하지 않음 |
| `store.lastFilteredUniverse` 없음(최초 실행 등) | Swing Scanner가 아직 결과를 저장하지 않음 | `fetchTossWarnings` 호출 스킵, 기존 소스 결과만으로 진행(Fail-Safe) |
| 전체 소스 0건 수집 | 모든 소스 실패 | 기존 패턴대로 `prev.riskCodes` 캐시 유지 + 텔레그램 알림 |

### 6.2 Error Response Format

N/A — REST API 응답 포맷이 아니라 n8n 노드 반환 객체. 기존 포맷 유지:
```javascript
{ ok: false, error: "HTTP 401: ...", status: 401, riskUpdatedAt: "..." }
```

---

## 7. Security Considerations

- [x] 토스 API 키(`store.tossApiKey`)는 n8n workflow static data에만 보관 — 코드/로그/텔레그램 알림 문구에 절대 포함하지 않음(기존 `fetchTossAPI` 헬퍼가 이미 이 원칙을 따름)
- [x] 인증 실패(401/403) 시 에러 메시지에 키 값이 노출되지 않도록 `e.message`만 로깅(기존 catch 패턴 재사용)
- [x] Rate Limiting: concurrency 6, 종목별 순차 슬립 없이도 토스 시세 API가 "분당 수백 콜" 허용 범위 내에서 동작하도록 호출 대상을 1차 필터 종목(~630개)으로 제한
- [ ] N/A: XSS/SQL Injection — 사용자 입력을 받지 않는 서버-서버 배치 작업이므로 해당 없음

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| 대조 검증 | 샘플 종목(10~20개)의 KRX 결과 vs 토스 `/warnings` 결과 | n8n Manual Trigger + Log Viewer 노드(기존 존재) |
| 회귀 확인 | 관리종목/KIND 로직 무변경 | 코드 diff 리뷰 |
| 장애 주입 | `store.tossApiKey` 임시 제거 후 동작 확인 | n8n workflow static data 수동 조작 후 Manual Trigger |
| 실행 안정성 | 배포 후 3영업일 연속 실행 로그 | n8n `n8n_list_executions` (MCP) 로 success/error 확인 |

### 8.2 Test Cases (Key)

- [ ] Happy path: 정상 종목 목록에 대해 `fetchTossWarnings`가 정리매매/투자경고/투자위험 종목만 정확히 골라냄
- [ ] Error scenario: 토스 API 키 미설정 시 전체 파이프라인이 기존 KRX/캐시 결과로 정상 완료됨
- [ ] Edge case: `store.lastFilteredUniverse`가 없는 최초 실행(혹은 캐시 만료) 시 토스 호출을 스킵하고 에러 없이 완료됨
- [ ] Edge case: 404(`stock-not-found`) 응답을 받은 종목이 있어도 나머지 종목 처리에 영향 없음

---

## 9. Clean Architecture (n8n Function 노드 구조로 대체)

> 이 프로젝트는 레이어드 웹앱이 아니므로 표준 Presentation/Application/Domain/Infrastructure 레이어는 적용하지 않는다. 대신 **n8n Function 노드 내부 함수 단위 책임 분리**로 대체한다.

### 9.1 Layer Structure (대체 매핑)

| 역할 | 책임 | 위치(함수) |
|-------|---------------|----------|
| Trigger | 스케줄 발동 | `Risk Blacklist Trigger (08:30 KST)` (cron 노드, 변경 없음) |
| Orchestration | 소스별 수집 함수 호출 및 병합 | `Risk Blacklist Updater` 노드의 메인 실행 블록(`try { ... }`) |
| Source Adapter | 각 외부 소스별 수집 로직 | `fetchNaverAdminStocks`, `fetchKrxAllCodes`, `fetchKindCodes`, `fetchTossWarnings` (신규) |
| Infra (HTTP) | 실제 네트워크 호출 | `http()`, `fetchTossAPI()` (기존 헬퍼 재사용) |

### 9.2 Dependency Rules

```
Orchestration(메인 실행 블록)
   ├─▶ fetchNaverAdminStocks()   ─▶ http()
   ├─▶ fetchKrxAllCodes()        ─▶ http()
   ├─▶ fetchKindCodes()          ─▶ http()
   └─▶ fetchTossWarnings()       ─▶ fetchTossAPI() ─▶ http()

규칙: Source Adapter 함수는 서로를 호출하지 않는다(독립적, 실패 격리).
      Orchestration만 여러 Adapter의 결과를 병합한다.
```

### 9.3 File Import Rules

N/A — 단일 n8n Function 노드 내 하나의 코드 블록(모듈 임포트 체계 없음). 함수 간 호출 순서만 9.2를 따른다.

### 9.4 This Feature's Layer Assignment

| Component | 역할 | 위치 |
|-----------|-------|----------|
| `fetchTossWarnings(symbols)` | Source Adapter (신규) | `Risk Blacklist Updater` 노드 코드 내부 |
| `RISK_WARNING_TYPES` 상수 | 매핑 정의 | `Risk Blacklist Updater` 노드 코드 상단 |
| `store.lastFilteredUniverse` 저장 로직 (신규) | 데이터 소스 제공 | `Swing Scanner` 노드 코드 말미(09:10 실행 종료 시) |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions (기존 노드 코드 컨벤션 그대로 적용)

| Target | Rule | Example |
|--------|------|---------|
| 함수 | camelCase, `fetch` 접두사(수집 함수) | `fetchTossWarnings`, `fetchKindCodes` |
| 상수 | UPPER_SNAKE_CASE | `RISK_WARNING_TYPES`, `TOSS_API_BASE` |
| store 네임스페이스 | `store.blacklist.*`, `store.krxState.*` 패턴 유지 | `store.lastFilteredUniverse` (신규, 동일 패턴) |
| 텔레그램 알림 키(중복 방지) | `notifyOncePerDay('키_설명', text)` | `notifyOncePerDay('toss_warnings_fail', ...)` |

### 10.2 Import Order

N/A — n8n Function 노드는 모듈 임포트 없이 단일 스코프 내 정의(기존 코드 전체와 동일 스타일 유지).

### 10.3 Environment Variables

| Prefix | Purpose | Scope | Example |
|--------|---------|-------|---------|
| (n8n workflow static data, prefix 없음) | 토스 API 인증 | n8n workflow 전역 | `store.tossApiKey` (기존, 신규 설정 불필요) |

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 함수 명명 | 기존 `fetch*` 접두사 패턴 유지 |
| 실패 처리 | 기존 서킷브레이커 + `notifyOncePerDay` + 캐시 유지 폴백 패턴 재사용 |
| 동시성 제어 | 기존 `mapLimit(list, limit, worker)` 헬퍼 재사용 (concurrency 6) |

---

## 11. Implementation Guide

### 11.1 File/Node Structure

```
n8n Workflow: Autostock Swing Scanner (ScHaeFdneOoH1ZNZ)
├── Swing Scanner (Function 노드)
│   └── 스캔 종료 시 store.lastFilteredUniverse 저장 로직 추가 (신규)
└── Risk Blacklist Updater (Function 노드)
    ├── RISK_WARNING_TYPES 상수 추가
    ├── fetchTossWarnings(symbols) 함수 추가
    └── 메인 실행 블록에서 fetchTossWarnings 결과를 riskCodes에 병합 + 알림 문구 갱신
```

### 11.2 Implementation Order

1. [ ] `Swing Scanner` 노드 말미에 `store.lastFilteredUniverse = { symbols, updatedAt }` 저장 로직 추가
2. [ ] `Risk Blacklist Updater` 노드에 `RISK_WARNING_TYPES` 상수 + `fetchTossWarnings(symbols)` 함수 추가
3. [ ] 메인 실행 블록에서 `store.lastFilteredUniverse` 존재 여부 확인 → 있으면 `fetchTossWarnings` 호출, 없으면 스킵
4. [ ] 결과를 `allCodes`에 병합, `sourceCounts.TossWarnings` 기록
5. [ ] 텔레그램 알림 문구를 4.section 형식으로 갱신
6. [ ] n8n Manual Trigger로 샘플 종목 대조 검증 (8.1 참고)
7. [ ] 라이브 배포 후 3영업일 실행 로그 확인 (`n8n_list_executions` MCP)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-09 | Initial draft | kevin |

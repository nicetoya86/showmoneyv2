# theme-blacklist-political-filter Planning Document

> **Summary**: `Theme Blacklist Updater` n8n 노드가 네이버 전체 266개 테마를 무차별로 차단해 유니버스의 69%(2,342종목)를 제외하는 문제를, 이미 작성돼 있으나 미배포 상태인 정치 테마 전용 필터(`Refresh_Theme_Blacklist_Naver_code.js`)를 라이브 노드에 반영해 해결한다.
>
> **Project**: showmoneyv2 (Autostock Swing Scanner)
> **Version**: n/a (n8n workflow, `algo-v1.0` 기준)
> **Author**: kevin
> **Date**: 2026-07-14
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `Theme Blacklist Updater` 노드가 네이버 테마 목록 266개 전부를 무차별로 수집해 2,342개 종목(유니버스의 약 69%)을 스윙 스캔 대상에서 제외하고 있음. 2026-07-14 실행에서도 1차 필터 통과 628종목 중 2,115개가 테마 사유로 제외되어 최종 후보가 0건("추천 종목 없음")으로 종료됨. |
| **Solution** | 이미 로컬에 작성돼 있으나 라이브 노드에는 반영되지 않은 정치 테마 키워드 필터(`Refresh_Theme_Blacklist_Naver_code.js`, `POLITICAL_KEYWORDS`/`isPoliticalTheme`)를, 라이브 `Theme Blacklist Updater` 노드의 기존 운영 패턴(텔레그램 알림, 0건 시 캐시 유지 폴백)에 병합하여 배포한다. |
| **Function/UX Effect** | 텔레그램 "테마 블랙리스트 갱신 성공" 알림의 종목/테마 수가 대폭 감소하고(266개 테마 전체 → 정치 테마만), 스윙 스캔에서 테마 사유로 제외되는 종목 수가 줄어 실제 후보가 나올 가능성이 높아진다. |
| **Core Value** | 무관한 산업/섹터 테마(반도체, 2차전지 등)까지 함께 차단되어 스캔 후보가 고갈되는 현상을 해소하고, 실제 위험 요인(정치 테마주 급등락)만 선별적으로 차단해 필터의 목적성을 회복한다. |

---

## 1. Overview

### 1.1 Purpose

`Theme Blacklist Updater`(매일 08:45 KST 실행) 노드가 네이버 테마 목록에 등록된 **모든** 테마(현재 266개)에 속한 종목을 예외 없이 블랙리스트에 편입시키는 현재 로직을, **정치 테마로 분류되는 테마만** 블랙리스트에 편입시키는 로직으로 교체한다.

### 1.2 배경

- 2026-07-14 08:46 텔레그램 알림: `[테마 블랙리스트 갱신 성공] 총 2342개 종목 / 테마 266개`. 같은 날 09:13 스윙 스캔 알림에서 `분석 종목(필터 후): 628개 / 제외(테마): 2115개 / 후보: 1개` → 추천 종목 없음으로 종료.
- 라이브 워크플로우(`autostock_showmoneyv2_20260714_toss_confirm_risk_blacklist.json`)의 `Theme Blacklist Updater` 노드 코드를 직접 조회한 결과, `extractThemeNos()`가 네이버 테마 목록 페이지에서 발견되는 테마 번호를 필터 없이 전부 수집 → `sise_group_detail.naver`로 각 테마의 종목코드를 모아 `store.blacklist.themeCodes`에 저장하는 구조임을 확인. 정치 테마 여부를 구분하는 로직은 존재하지 않음.
- 같은 저장소에 정치 테마만 걸러내는 개선판 스크립트 `Refresh_Theme_Blacklist_Naver_code.js`가 이미 작성되어 있으나(`POLITICAL_KEYWORDS` 키워드 목록 + `isPoliticalTheme(name)` 필터 포함), **한 번도 라이브 노드에 배포된 적이 없음**을 확인.
- `docs/01-plan/features/risk-blacklist-toss-api.plan.md`(2026-07-09)에서 이미 이 문제를 인지하고 "테마 블랙리스트 정치 필터 재배포"를 후속 과제로 명시적으로 분리해 두었음(해당 Plan은 리스크 블랙리스트만 다루고 테마는 Out of Scope 처리).

### 1.3 Related Documents

- 로컬 개선판 스크립트: `Refresh_Theme_Blacklist_Naver_code.js` (정치 테마 필터 포함, 미배포)
- 라이브 노드 참고: `Refresh_Theme_Blacklist_Naver_ORIGINAL.js` (구버전 스냅샷)
- 라이브 n8n 워크플로우: `autostock_showmoneyv2_20260714_toss_confirm_risk_blacklist.json` — `Theme Blacklist Updater` 노드 (전체 테마 무차별 차단 로직, 현재 배포 상태)
- 선행 문서: `docs/01-plan/features/risk-blacklist-toss-api.plan.md` §1.2 (테마 블랙리스트 이슈 최초 언급 및 Out of Scope 처리)
- 검증 스크립트: `scripts/verify_theme_filter_disabled.py` (라이브 노드의 테마 필터 적용 여부 확인용, 기존 작성됨)

---

## 2. Scope

### 2.1 In Scope

- [ ] `Theme Blacklist Updater` 노드에 `POLITICAL_KEYWORDS` 상수 + `isPoliticalTheme(name)` 함수 추가(기존 `Refresh_Theme_Blacklist_Naver_code.js` 로직 재사용)
- [ ] 테마 수집 방식을 `extractThemeNos()`(번호만) → `extractThemeEntries()`(번호+테마명) 방식으로 교체해 이름 기반 필터링이 가능하도록 변경
- [ ] 정치 테마로 판정된 테마만 상세 페이지(`sise_group_detail.naver`) 조회 대상으로 한정 → 해당 종목코드만 `store.blacklist.themeCodes`에 편입
- [ ] 라이브 노드의 기존 운영 패턴(텔레그램 성공/0건 캐시유지 알림, `BOT_T`/`CHAT_T` 토큰 사용, FIX C-4/W-6 로직) 유지 — 단순 파일 교체가 아니라 정치 필터 로직만 이식(병합)
- [ ] 텔레그램 알림 문구에 "전체 테마 수 vs 정치 테마 매칭 수" 반영 (예: `총 {N}개 종목 / 정치 테마 {M}개 (전체 {T}개 중)`)
- [ ] 배포 전/후 `store.blacklist.themeCodes` 개수 비교 및 정치 테마명 목록(`politicalThemeNames`) 로그 확인

### 2.2 Out of Scope

- 정치 테마 외 다른 기준(예: 급등 테마주, 작전주 의심 종목 등)의 별도 필터링 — 이번 범위는 "정치 테마만" 한정, 확장은 별도 Plan
- `Risk Blacklist Updater` 로직 변경 — `risk-blacklist-toss-api`에서 이미 처리, 이번 범위에서 재수정하지 않음
- `POLITICAL_KEYWORDS` 키워드 목록의 지속적 유지보수 자동화(예: 최신 정치 이슈 자동 반영) — 이번 범위는 기존에 작성된 키워드 목록을 그대로 배포하는 것까지만 포함, 목록 확장/자동화는 백로그
- 스윙 스캐너의 테마 제외 로직(`themeSet.has(...)`) 자체 변경 — `store.blacklist.themeCodes` 데이터가 줄어드는 것으로 자연히 완화되며, 소비 측 로직은 손대지 않음

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 테마 목록 수집 시 테마 번호와 테마명을 함께 추출(`extractThemeEntries`) | High | Pending |
| FR-02 | 정치 테마 키워드(`POLITICAL_KEYWORDS`)에 매칭되는 테마만 상세 조회 및 종목코드 편입 | High | Pending |
| FR-03 | 정치 테마 매칭이 0건이어도 스크래핑 자체가 성공했다면 정상 결과로 캐시를 갱신(비움)하고, 상세 조회가 실패해 0건이 된 경우에만 기존 `store.blacklist.themeCodes` 캐시를 유지(Do 단계 실측 검증 후 FIX C-4 분기를 이렇게 수정) | High | Done |
| FR-04 | 텔레그램 성공 알림에 전체 테마 수 대비 정치 테마 매칭 수를 함께 표기 | Medium | Pending |
| FR-05 | 라이브 노드의 기존 실패 격리/재시도(`fetchTextRetry`, `mapLimit` concurrency) 로직 무변경 유지 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 정치 테마만 상세 조회하므로 기존 대비 상세 페이지 요청 수가 대폭 감소(266개 → 정치 테마 수만큼) — 실행시간은 기존보다 짧아지는 방향, 목표 08:45 실행이 1분 이내 완료 | n8n execution duration 로그 비교 |
| Reliability | 정치 테마 매칭 0건 시에도 파이프라인이 에러 없이 완료되고 기존 캐시가 유지되어야 함 | 키워드 목록을 임시로 매칭 불가하게 바꾼 뒤 동작 확인 |
| Consistency | 테마명 매칭 기준(`name.includes(keyword)`)이 최신 네이버 테마명 표기와 어긋나지 않는지 배포 전 샘플 대조 | 배포 전 전체 테마명 목록에 대해 매칭 결과 수동 검토 |
| Observability | `store.blacklist.themeFetchStats`에 `totalThemesFound`, `politicalThemesMatched`, `politicalThemeNames`가 기록되어 사후 검증 가능해야 함 | 배포 후 n8n Manual Trigger 결과 확인 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `Theme Blacklist Updater` 노드가 정치 테마로 판정된 테마의 종목만 `themeCodes`에 편입
- [ ] 텔레그램 알림에 "전체 266개 테마 중 정치 테마 N개, 종목 M개" 형태로 표기됨(정확한 문구는 Design에서 확정)
- [ ] 배포 후 첫 실행에서 `themeCodesCount`가 기존 2,342개 대비 뚜렷하게 감소(정치 테마 관련 종목 수준으로)
- [ ] 3영업일 연속 실행 로그에서 에러 없이 성공(success) 상태 확인
- [ ] 배포 이후 스윙 스캔 알림의 "제외(테마)" 수치가 유의미하게 감소하는지 확인

### 4.2 Quality Criteria

- [ ] 라이브 노드의 텔레그램 토큰/캐시 유지/알림 포맷 등 기존 컨벤션 유지
- [ ] n8n Function 노드 배포 전 로컬 문법 검증(Node.js로 실행 가능한 순수 함수 단위 검증)
- [ ] 배포 전 정치 테마 매칭 목록을 수동 검토하여 명백한 오탐/누락이 없는지 확인

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `POLITICAL_KEYWORDS` 키워드 목록이 최신 정치 이슈(신규 후보/정당명 등)를 반영하지 못해 일부 정치 테마를 놓칠 수 있음 | Medium | Medium | 배포 전 전체 테마명 266개 목록을 실제로 조회해 키워드 누락 여부 1회 검토, 이후 정기 점검은 백로그로 분리 |
| 기존에 테마로 차단되던 비정치 종목(급등 테마주 등)이 대거 필터 해제되어 스윙 스캔 후보에 노출될 수 있음 | Medium | High (의도된 변경) | 배포 직후 며칠간 스윙 스캔 결과를 모니터링해 품질 저하 여부 확인 — 필요 시 별도 "투기적 테마" 필터를 후속 Plan으로 추가 검토 |
| 단순 파일 교체 시 라이브 노드의 텔레그램 알림/캐시 유지 로직이 유실될 수 있음(`Refresh_Theme_Blacklist_Naver_code.js`는 이 부분이 없는 구버전 초안) | High | Medium | Design 단계에서 "정치 필터 로직만 이식, 운영 패턴은 라이브 노드 기준 유지"를 명시하고 코드 diff로 재확인 |
| 네이버 테마명 표기 변경/구조 변경으로 `extractThemeEntries` 정규식이 깨질 수 있음 | Medium | Low | 기존 `extractThemeNos`와 동일한 정규식 베이스에 이름 캡처 그룹만 추가하는 최소 변경으로 리스크 최소화 |

---

## 6. Architecture Considerations

> 참고: 이 프로젝트는 Next.js/React 기반 웹앱이 아니라 **n8n 워크플로우 Function 노드로 구현된 자동매매 스캐너**이므로, 아래 6.2/6.3 항목 중 프레임워크·상태관리·스타일링 등은 해당 없음(N/A)으로 표기한다.

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 해당 없음 | - | ☐ |
| **Dynamic** | 해당 없음 | - | ☐ |
| **Enterprise** | 해당 없음 | - | ☐ |
| **N/A (n8n Workflow Automation)** | Function 노드 + workflow static data, 외부 스크래핑 연동 | 트레이딩 알고리즘 자동화 | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 필터 기준 | 전체 테마 차단(현행) / 정치 테마만 차단 / 화이트리스트 방식 | **정치 테마만 차단** | 기존에 작성된 `POLITICAL_KEYWORDS` 자산을 재사용, Plan §2.2에서 명시한 범위와 일치 |
| 배포 방식 | `Refresh_Theme_Blacklist_Naver_code.js` 파일 통째 교체 / 정치 필터 로직만 라이브 노드에 이식 | **로직만 이식(병합)** | 로컬 초안에는 텔레그램 알림·캐시 유지 폴백이 없어 그대로 교체 시 운영 기능 유실 |
| 테마 수집 범위 | 번호만 수집 후 별도 이름 조회 / 목록 페이지에서 번호+이름 동시 추출 | **목록 페이지에서 동시 추출** | 추가 HTTP 요청 없이 기존 목록 페이지 응답만으로 이름 필터링 가능(`Refresh_Theme_Blacklist_Naver_code.js`의 `extractThemeEntries` 방식) |
| Framework / State Management / API Client / Form Handling / Styling / Testing | (웹앱 항목) | N/A | n8n Function 노드 기반, 해당 카테고리 없음 |

### 6.3 노드 구조 (Clean Architecture 대체)

```
Theme Blacklist Updater (n8n Function 노드)
├─ fetchTextRetry(url, referer)         — 유지 (재시도 포함 HTTP 헬퍼)
├─ extractThemeNos(html)                — 제거 → extractThemeEntries(html)로 교체
├─ extractThemeEntries(html) ★신규       — 테마 번호+이름 동시 추출 (Refresh_Theme_Blacklist_Naver_code.js 이식)
├─ isPoliticalTheme(name) ★신규          — POLITICAL_KEYWORDS 기반 판정 (동일 파일에서 이식)
├─ extractCodes(html)                   — 유지 (테마 상세 → 종목코드 추출)
└─ 메인 실행 블록                        — 정치 테마만 필터링 후 상세 조회, 캐시/알림 패턴은 라이브 노드 그대로 유지
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [ ] `CLAUDE.md` 코딩 컨벤션 섹션 — 해당 없음 (n8n 노드 코드는 별도 컨벤션 없이 기존 패턴 준수)
- [x] 기존 노드 코드의 암묵적 컨벤션 존재: `fetchTextRetry`/`mapLimit` 헬퍼, `store.blacklist.*` 네임스페이스, FIX 태그 주석(`FIX C-4`, `FIX W-6`) 관행, 텔레그램 알림 포맷
- [ ] ESLint/Prettier/TypeScript — 해당 없음 (n8n Function 노드는 순수 JS, 별도 빌드 파이프라인 없음)

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 정치 테마 판정 함수 명명 | `Refresh_Theme_Blacklist_Naver_code.js`에 `isPoliticalTheme(name)` 존재 | 라이브 노드에도 동일 이름으로 이식 | High |
| 테마 소스 표기 | `store.blacklist.themeSource = 'naver:sise_group_detail'` | `'naver:sise_group_detail:political_only'`로 갱신(로컬 초안과 동일 값 사용) | Medium |
| 알림 문구 포맷 | `총 {N}개 종목 / 테마 {M}개` | `총 {N}개 종목 / 정치 테마 {M}개 (전체 {T}개 중)` 형태로 확장 | Medium |

### 7.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| 해당 없음 | 네이버 공개 페이지 스크래핑만 사용, 인증 불필요 | - | - |

### 7.4 Pipeline Integration

해당 없음 — 9-phase Development Pipeline이 아닌 기존 운영 중인 n8n 워크플로우에 대한 개선 작업.

---

## 8. Next Steps

1. [ ] Design 문서 작성 (`theme-blacklist-political-filter.design.md`) — 정치 필터 이식 상세 코드 diff, 알림 문구 최종안, `POLITICAL_KEYWORDS` 목록 재검토 포함
2. [ ] 전체 테마명 266개 대상 정치 테마 매칭 결과 사전 검토(오탐/누락 확인)
3. [ ] `Theme Blacklist Updater` 노드 코드 수정 및 로컬 문법 검증
4. [ ] 라이브 n8n 노드 배포 후 Manual Trigger로 1회 결과 확인
5. [ ] 3영업일 연속 실행 로그 + 스윙 스캔 "제외(테마)" 수치 변화 확인
6. [ ] (선택) 비정치 투기적 테마 필터 필요성 재검토 — 별도 Plan 여부는 배포 후 스캔 품질을 보고 결정

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-14 | Initial draft | kevin |

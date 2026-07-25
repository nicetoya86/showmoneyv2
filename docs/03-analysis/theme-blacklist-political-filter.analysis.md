# theme-blacklist-political-filter Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) — PDCA Check
>
> **Project**: showmoneyv2 (Autostock Swing Scanner)
> **Version**: n/a (n8n workflow, `algo-v1.0` 기준)
> **Analyst**: kevin (bkit-gap-detector)
> **Date**: 2026-07-14
> **Design Doc**: [theme-blacklist-political-filter.design.md](../02-design/features/theme-blacklist-political-filter.design.md)
> **Plan Doc**: [theme-blacklist-political-filter.plan.md](../01-plan/features/theme-blacklist-political-filter.plan.md)

> ⚠️ **배포/검증 대기 (NOT DEPLOYED)**: 본 분석은 로컬 구현본(`Refresh_Theme_Blacklist_Naver_code.js`, 256 lines)과 Design 문서 간의 **정적 코드 대조(static comparison)** 이다. 이 코드는 라이브 n8n `Theme Blacklist Updater` 노드에 **아직 반영되지 않았다**. 따라서 런타임/실행 로그 검증(n8n Manual Trigger, 3영업일 실행 로그, 스윙 스캔 "제외(테마)" 수치 변화)은 **수행 불가·미포함**이며, 아래 Match Rate는 "코드 정합성" 기준이지 "런타임 검증"을 포함하지 않는다. Design §11.2 6~7번은 배포 후 과제로 남는다.

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

라이브 `Theme Blacklist Updater` 노드가 네이버 테마 266개 전체를 무차별 차단(`extractThemeNos`)해 유니버스의 69%(2,342종목)를 제외하는 문제를, 정치 테마 전용 필터(`POLITICAL_KEYWORDS` + `isPoliticalTheme` + `extractThemeEntries`)로 교체하는 설계가 실제 코드에 정확히 반영되었는지, 기존 운영 패턴(텔레그램 알림·`BOT_T`/`CHAT_T`·FIX C-4 캐시 유지)과 무변경 대상 헬퍼(`fetchTextRetry`·`extractCodes`·`mapLimit`·concurrency=6·상세 조회 루프)에 회귀가 없는지 라인 단위로 검증한다. 특히 Do 단계 중 도출된 **FIX C-4 분기 수정**(정치 테마 0건=정상 vs 상세 조회 실패=장애 구분)이 코드에 정확히 구현되고 Design §5.2/§6.1과 일치하는지 집중 검증한다.

### 1.2 Analysis Scope

- **Design Document**: `docs/02-design/features/theme-blacklist-political-filter.design.md`
- **Plan Document**: `docs/01-plan/features/theme-blacklist-political-filter.plan.md` (§3.1 FR-01~FR-05)
- **Implementation (신규, 미배포)**: `Refresh_Theme_Blacklist_Naver_code.js` (repo root, 256 lines)
- **Reference (회귀 비교 기준)**: `cache/_live_theme_blacklist_updater.js` (194 lines, 현재 배포된 라이브 노드 스냅샷 — `autostock_showmoneyv2_20260714_toss_confirm_risk_blacklist.json`에서 추출)
- **Do 단계 실측 근거(참고)**: `cache/_naver_theme_page{1-7}.utf8.html` (2026-07-14 네이버 테마 목록 7페이지 원본 HTML)
- **Analysis Date**: 2026-07-14

> **참고**: 회귀(FR-05) 판정 기준은 `cache/_live_theme_blacklist_updater.js`(현재 배포 상태)를 절대 기준으로 삼는다 — "Design이 명시한 무변경 대상 함수의 동작 동일성"을 라이브 노드 대비 직접 diff로 확인했다.

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 Functional Requirements (Plan §3.1)

| FR | 요구사항 | 근거 코드 | 상태 |
|----|----------|-----------|------|
| FR-01 | 테마 목록 수집 시 테마 번호+테마명 함께 추출(`extractThemeEntries`) | `extractThemeEntries`(L64-79): `{no, name}` 반환, `seen` 중복 제거, `name.length>0` 가드. 메인 블록 L120/L146에서 `extractThemeNos` 대체 | ✅ Match |
| FR-02 | `POLITICAL_KEYWORDS` 매칭 테마만 상세 조회·편입 | `politicalEntries = allEntries.filter(e => isPoliticalTheme(e.name))`(L164) → `themeNos = politicalEntries.map(e => e.no)`(L165) → `mapLimit(themeNos, CONCURRENCY, ...)`(L172)만 상세 조회 | ✅ Match |
| FR-03 | 정치 테마 0건 매칭 시 기존 캐시 유지(현행 FIX C-4 재사용) | **⚠️ 문언(literal) 미충족 — 의도된 수정으로 대체됨**. Do 단계 실데이터 검증 후 "정치 0건=캐시 유지"는 오히려 옛 2,342개 캐시를 영구 보존하는 결함으로 판명 → Design §5.2/§6.1(Row 5)에서 "정치 0건=정상, 캐시 비움"으로 수정. 코드 L193은 수정본을 정확히 구현. **Plan FR-03 문언이 stale** | 🔵 Changed (Design 수정으로 대체, 코드 정확) |
| FR-04 | 텔레그램 성공 알림에 전체 테마 수 대비 정치 매칭 수 표기 | 성공 알림 L233: `'총 ' + themeCodes.length + '개 종목 / 정치 테마 ' + themeNos.length + '개 (전체 ' + allEntries.length + '개 중)'` | ✅ Match |
| FR-05 | 기존 실패 격리/재시도(`fetchTextRetry`, `mapLimit` concurrency) 무변경 유지 | 라이브 노드 대비 완전 일치(§2.4 회귀표 참조) | ✅ Match |

> **FR-03 상세**: Plan §3.1 FR-03의 문언은 "정치 테마가 0건 매칭될 경우 기존 캐시를 유지"이다. 그러나 Do 단계에서 실제 네이버 테마 266개를 대조한 결과 **현재(비선거 시즌) 정치 테마가 0/266건이 정상 상태**임이 확인되었고(§8.3 / `cache/_naver_theme_page{1-7}`), 이 상태에서 기존 FIX C-4를 그대로 적용하면 필터가 영구히 무효화된다. 이에 Design이 §5.2/§6.1에서 분기를 수정했고 코드는 수정본을 구현했다. **따라서 FR-03은 "문언 그대로는 미구현"이나 "설계 의도상 올바르게 대체"된 항목**이다. Plan 문서의 FR-03 문언 갱신이 필요하다(§10).

### 2.2 Design §4 정치 테마 판정 사양

#### 2.2.1 §4.1 `POLITICAL_KEYWORDS` / `isPoliticalTheme`

| 검증 항목 | Design (§4.1, L130-138) | 실제 코드 | 상태 |
|-----------|-------------------------|-----------|------|
| 키워드 목록 (19개) | `대선…한동훈` 19개 | L53-57 동일 19개, 순서·표기 완전 일치 | ✅ |
| `isPoliticalTheme(name)` | `POLITICAL_KEYWORDS.some(kw => name.includes(kw))` | L59-61 동일 | ✅ |

> 키워드 수: 대선/대통령/총선/선거/정치/국회/의원(7) + 여당/야당/공천/후보/당대표/대권/집권(7) + 국정감사/탄핵/윤석열/이재명/한동훈(5) = **19개, Design과 완전 일치**.

#### 2.2.2 §4.2 `extractThemeEntries`

| 검증 항목 | Design (§4.2, L147-161) | 실제 코드 (L64-79) | 상태 |
|-----------|-------------------------|--------------------|------|
| 정규식 | `/sise_group_detail\.naver\?type=theme&(?:amp;)?no=(\d+)[^>]*>([^<]{1,60})/g` | 동일 | ✅ |
| `(?:amp;)?` 대체 패턴 포함 | 포함(라이브 `extractThemeNos`의 `&no=`만 매칭보다 견고) | 포함 | ✅ |
| 중복 제거 `seen` Set | 있음 | 있음 | ✅ |
| `name.length>0` 가드 | 있음(`name.length > 0`) | `if (!seen.has(no) && name.length > 0)`(L73) | ✅ |
| 반환 구조 | `{no, name}[]` | 동일 | ✅ |

> **Do 단계 실측(§8.3 반영)**: `extractThemeEntries` vs 라이브 `extractThemeNos` 매칭 수 = **266 vs 266 완전 일치**(`cache/_naver_theme_page{1-7}.utf8.html` 대상). 정규식 교체 안전성 실증됨.

#### 2.2.3 §4.3 페이지 순회 로직

| 검증 항목 | Design (§4.3, L168-201) | 실제 코드 | 상태 |
|-----------|-------------------------|-----------|------|
| 1페이지 `allEntries = extractThemeEntries(html1)` | 있음 | L120 | ✅ |
| 0건 시 `ok:false` 조기 반환 | `reason: 'No theme entries found on list page'` | L122-133, reason 문언 동일 | ✅ |
| `seenNos = new Set(allEntries.map(e => e.no))` | 있음 | L140 | ✅ |
| 2~maxPage 순회, `{no,name}[]` 누적 | 있음(added 카운트, `added===0 && p>=3` break) | L143-161 동일 | ✅ |
| `politicalEntries` 필터 → `themeNos` | `allEntries.filter(...)`, `politicalEntries.map(e=>e.no)` | L164-165 동일 | ✅ |
| 페이지 수 추정(`pagesFound`/`maxPage`) 무변경 | `html1.matchAll(/page=(\d+)/g)` 기반, 변경 없음 | L136-138, 라이브(L112-114)와 동일 | ✅ |

### 2.3 Design §5 저장/알림 로직 (라이브 L156-193 대응)

| 검증 항목 | Design (§5.2, L220-271) | 실제 코드 | 상태 |
|-----------|--------------------------|-----------|------|
| `themeCodes = [...codeSet].sort()` | 있음 | L184 | ✅ |
| `prevThemeCodes` 안전 추출 | `Array.isArray(...) ? ... : []` | L185 동일 | ✅ |
| `BOT_T`/`CHAT_T`/`NL_T` 상수 | 변경 없음(평문) | L186-188 라이브와 동일 값 | ✅ |
| **FIX C-4 수정 분기** | `if (themeCodes.length===0 && politicalEntries.length>0 && prevThemeCodes.length>0)` | **L193 완전 일치** | ✅ (핵심) |
| 상세 조회 실패 경고 알림 | 정치 N개 매칭됐으나 상세 조회 실패 — 캐시 유지 | L194-205 문구·반환(`keptCache:true`) 일치 | ✅ |
| `politicalEntries.length===0` → 저장 로직으로 낙하(캐시 비움) | 주석·낙하 로직 명시 | L190-192 주석 + 조건 false 시 낙하 | ✅ |
| `themeSource` 갱신 | `'naver:sise_group_detail:political_only'` | L211 동일 | ✅ |
| `themeNosCount` = 정치 매칭 수 | `themeNos.length` | L210 동일 | ✅ |
| `themeFetchStats` 신규 3필드 | `totalThemesFound`/`politicalThemesMatched`/`politicalThemeNames` | L218-220 동일 | ✅ |
| 성공 알림 문구 | `총 N개 종목 / 정치 테마 M개 (전체 T개 중)` | L233 동일 | ✅ |
| 반환 객체 | `ok/done/totalThemesFound/politicalThemesMatched/politicalThemeNames/themeNosCount/themeCodesCount/themeUpdatedAt/stats/sampleCodes/detailErrors` | L239-255 필드·순서 일치 | ✅ |

### 2.4 회귀 확인 — 무변경 대상 함수 (Plan §2.2 / Design "최소 침습") — vs 라이브 노드

`cache/_live_theme_blacklist_updater.js`(194L) 대비 직접 diff:

| 함수/상수 | 라이브 (line) | 구현 (line) | 결과 |
|-----------|---------------|-------------|------|
| `http` / `sleep` / `toText` / `fetchText` | L4-33 | L4-33 | ✅ byte-identical |
| `fetchTextRetry(url, referer, tries=2)` | L35-46 | L35-46 | ✅ byte-identical |
| `uniq` | L48-50 | L48-50 | ✅ byte-identical |
| `extractCodes` (`/code=(\d{6})/g`) | L57-60 | L81-84 | ✅ byte-identical |
| `mapLimit(list, limit, worker)` | L62-81 | L86-105 | ✅ byte-identical (errors 수집 포함) |
| 튜닝 상수 `MAX_LIST_PAGES=20`/`CONCURRENCY=6`/`DETAIL_SLEEP_MS=120`/`LIST_SLEEP_MS=120` | L83-88 | L107-112 | ✅ 동일 |
| 상세 조회 루프 `mapLimit(themeNos, CONCURRENCY, ...)` + `sleep(DETAIL_SLEEP_MS)` + URL + `extractCodes` + `codeSet.add` | L145-152 | L172-179 | ✅ 구조·동시성 동일 |
| `detailErrors` 수집 | L154 | L181 | ✅ 동일 |

**결론: FR-05 회귀 없음.** `fetchTextRetry`, `extractCodes`, `mapLimit`, concurrency=6, 상세 조회 루프 모두 라이브 노드와 동작 동일.

#### 2.4.1 회귀 관련 경미 차이 (기능 무영향)

| 항목 | 라이브 | 구현 | 영향 |
|------|--------|------|------|
| 상세 조회 전 `themeNos` 정렬 | `[...allNos].sort((a,b)=>Number(a)-Number(b))`(L138) | 정렬 없음(`politicalEntries.map` 순서 그대로, L165) | 🟢 무영향 — 상세 조회 순서만 다를 뿐 결과 `codeSet`은 Set, 최종 `themeCodes`는 `[...codeSet].sort()`(L184)로 정렬됨 |
| 0건 목록 `reason` 문구 | `'No theme no found on list page (expected type=theme&no=###)'`(L103) | `'No theme entries found on list page'`(L127) | 🟢 무영향 — Design §4.3(L174)이 명시한 신규 문구를 정확히 따름 |

### 2.5 Design §6 에러 처리 테이블

| Case | Design 처리 (§6.1) | 실제 코드 | 상태 |
|------|--------------------|-----------|------|
| 목록 페이지 0건 | `ok:false` + 스니펫(변경 없음) | L122-133 (`store` 미변경 → 캐시 암묵 보존) | ✅ |
| `isPoliticalTheme` 매칭 0건 **(§6.1 Row 2)** | "…기존 FIX C-4(0건 시 캐시 유지) 경로로 자연 처리됨" | **코드는 캐시 유지가 아니라 캐시를 비움(L190-192, L208~)** | ❌ **Design 내부 모순** (아래 Note) |
| 상세 조회 일부 실패 | `mapLimit` errors 재사용, 해당 테마만 스킵 | L172-181 그대로 | ✅ |
| `extractThemeEntries` 미매칭 | Do 단계 HTML 샘플 사전 검증 | §8.3에서 266/266 확인 완료 | ✅ |
| **정치 매칭 자체 0건(스크래핑 정상) (§6.1 Row 5)** | ⚠️ 기존 FIX C-4 쓰면 안 됨. `politicalEntries.length===0`이면 정상→캐시 비움, `>0`인데 상세 실패면 캐시 유지 | L190-193 정확히 구현 | ✅ |

> **❌ Design 내부 모순 (§6.1 Row 2 ↔ Row 5 / §5.2)**: §6.1 **Row 2**는 수정 이전 서술("정치 0건 → FIX C-4 캐시 유지 경로로 자연 처리, 추가 분기 불필요")을 그대로 남겨두고 있어, **동일 표의 Row 5 및 §5.2의 수정된 로직과 정면으로 모순**된다. 실제 코드는 Row 5/§5.2(정치 0건=정상=캐시 비움)를 따른다. **코드가 정답이며, Design §6.1 Row 2가 갱신 누락된 stale 서술**이다(§10 문서 수정 필요). 사용자 요청("코드가 Design §5.2/§6.1과 일치하는가")에 대한 답: **§5.2 및 §6.1 Row 5와는 완전 일치하나, §6.1 Row 2와는 불일치 — 원인은 코드 결함이 아니라 Design 표의 갱신 누락**이다.

### 2.6 Design §11.2 구현 순서 반영 여부

| # | 항목 | 상태 | 근거 |
|---|------|------|------|
| 1 | `extractThemeEntries` 정규식 사전 검증(no 집합·이름 추출) | ✅ 완료 | §8.3, 266/266 (`cache/_naver_theme_page{1-7}`) |
| 2 | `POLITICAL_KEYWORDS`/`isPoliticalTheme` 추가 | ✅ 완료 | L53-61 |
| 3 | `extractThemeNos`→`extractThemeEntries` 교체 + 엔트리 배열 누적 | ✅ 완료 | L64-79, L120-161 |
| 4 | `politicalEntries` 필터 후 `themeNos` 재정의(상세 루프 무변경) | ✅ 완료 | L164-165, L172-179 |
| 5 | `themeFetchStats`/텔레그램 알림 신규 필드 반영 | ✅ 완료 | L218-220, L233 |
| 6 | n8n Manual Trigger 1회 실행 + `politicalThemeNames` 육안 검토 | ❌ 미수행 | 배포 대기 |
| 7 | 라이브 배포 후 3영업일 로그 + 스윙 스캔 "제외(테마)" 수치 확인 | ❌ 미수행 | 배포 대기 |

### 2.7 Out of Scope 무침습 확인 (Plan §2.2)

| 항목 | 기대 | 결과 |
|------|------|------|
| `Risk Blacklist Updater` 로직 | 무변경 | ✅ 본 파일에 Risk 로직 없음 |
| 스윙 스캐너 `themeSet.has(...)` 소비 로직 | 무변경 | ✅ 본 파일 범위 밖, 미변경 |
| `POLITICAL_KEYWORDS` 목록 확장/자동화 | 이번 범위 아님 | ✅ 기존 초안 목록 그대로 이식 |
| 비정치 투기 테마 필터 | 이번 범위 아님 | ✅ 미구현(정치 한정) |

### 2.8 Match Rate Summary

```
┌────────────────────────────────────────────────────────────┐
│  Overall Design Match Rate: 96%  (코드 정합성 기준)          │
│  ⚠️ 배포/런타임 검증 미포함 (§11.2 6~7 Not Implemented)      │
├────────────────────────────────────────────────────────────┤
│  ✅ Match:              30 items (91%)                       │
│  🔵 Changed(의도된 대체): 1 item  (3%)  ← FR-03 문언 대체     │
│  ❌ Doc 모순(코드 정답):  1 item  (3%)  ← Design §6.1 Row 2   │
│  🟢 경미 차이(무영향):    2 items       ← 정렬/문구           │
└────────────────────────────────────────────────────────────┘
비고: 코드-vs-Design(§5.2/§6.1 Row 5) 정합성은 사실상 100%.
      감점 2건은 코드 결함이 아니라 Plan/Design 문서의 갱신 누락(stale)임.
      §11.2 6~7(배포/런타임 검증)은 계획상 미수행이므로 분모에서 제외.
```

---

## 3. FIX C-4 수정 분기 건전성 심층 검증 (사용자 요청 Q4)

수정 분기(L193): `if (themeCodes.length === 0 && politicalEntries.length > 0 && prevThemeCodes.length > 0)` → 캐시 유지, 그 외 낙하하여 저장.

### 3.1 상태 공간 전수 검토

| # | politicalEntries | themeCodes | prevThemeCodes | 분기 | 동작 | 판정 |
|---|:---:|:---:|:---:|------|------|:----:|
| A | 0 (비선거 시즌 정상) | 0 | any | false | 낙하 → `themeCodes=[]` 저장(캐시 비움) | ✅ 의도대로 |
| B | >0 | >0 | any | false | 낙하 → 정상 저장 | ✅ |
| C | >0 | 0 | >0 | **true** | 캐시 유지 + ⚠️ 경고 알림 | ✅ (상세 조회 전멸 장애) |
| D | >0 | 0 | 0 | false | 낙하 → `themeCodes=[]` 저장 | ✅ 허용(보존할 캐시 없음, `detailErrors`로 추적 가능) |
| E | 목록 스크래핑 자체 0건 | — | — | (L122 조기 반환) | `ok:false`, `store` 미변경 → 캐시 암묵 보존 | ✅ 별도 가드로 처리 |

**결론: 분기 로직에 오류 없음.** 정치 0건(정상)과 상세 조회 실패(장애)를 정확히 구분하며, 총 스크래핑 실패(Case E)는 상위 L122 가드가 별도로 캐시를 보존한다.

### 3.2 텔레메트리/캐시가 "조용히 틀릴" 여지 검토

| 잠재 이슈 | 분석 | 심각도 |
|-----------|------|:------:|
| **부분 상세 조회 실패** (정치 N개 중 일부만 성공) | 성공분으로 `themeCodes.length>0`이면 Case B로 정상 저장되어 **불완전한 블랙리스트가 저장됨**. 캐시 유지 보호(Case C)는 `themeCodes`가 **전부** 비었을 때만 발동(all-or-nothing). 단 `detailErrors`가 `themeFetchStats.detailErrors` 및 반환 객체(L252, slice 10)에 기록되어 **완전히 조용하진 않음** | 🟡 (라이브 노드에서 상속된 기존 동작, 회귀 아님) |
| **`politicalThemeNames` vs `themeCodes` 커버리지 불일치** | `politicalThemeNames`는 매칭된 정치 테마명 전체를 기록하나, `themeCodes`는 상세 조회 성공분만 포함. 부분 실패 시 "이름 목록"과 "실제 코드"가 어긋날 수 있음. `detailErrors` 카운트로 교차 확인 가능 | 🟢 Info (관측 뉘앙스) |
| **`extractThemeEntries` 부분 미매칭 → 캐시 오삭제 위험** | 네이버 마크업 변경으로 정규식이 일부만 매칭하면 `allEntries`가 축소되고, 그 결과 `politicalEntries`가 0이 되면 Case A로 **정상 캐시(정치 종목)를 삭제**할 수 있음. 이는 FIX C-4 범위 밖(스크래핑 무결성 문제). 현재 §8.3의 266/266 실측으로 완화되나 **런타임 가드는 없음** | 🟡 (배포 후 모니터링 필요) |
| 정상 정치 0건 → 캐시 비움 | 의도된 동작. 향후 네이버에 정치 테마 재등장 시 자동으로 해당 종목만 차단 재개 | ✅ |

**종합 판정**: 수정 분기는 **건전(sound)** 하다. "조용히 틀리는" 치명적 경로는 없다. 다만 (a) 부분 상세 조회 실패 시 불완전 저장(라이브 상속), (b) 스크래핑 정규식 부분 파손 시 캐시 오삭제 — 두 잠재 리스크는 코드 결함이라기보다 "최소 침습" 원칙상 라이브에서 상속되었거나 스크래핑 무결성 영역이며, `detailErrors`/§8.3 실측으로 부분 완화된다. 배포 후 관측 권장(§9).

---

## 4. Code Quality Analysis

### 4.1 Complexity Analysis

| 함수 | 복잡도 | 상태 |
|------|--------|------|
| `extractThemeEntries` | 낮음 (단일 matchAll 루프 + 가드) | ✅ Good |
| `isPoliticalTheme` | 낮음 (`some` 1줄) | ✅ Good |
| `mapLimit` | 낮음 (라이브 상속) | ✅ Good |
| 메인 실행 블록 | 중간 (목록→필터→상세→저장/알림) | ✅ 허용 범위 |

### 4.2 Code Smells

N/A — n8n 단일 Function 노드 특성. 발견된 경미 항목:

| 유형 | 위치 | 설명 | 심각도 |
|------|------|------|--------|
| 하드코딩 시크릿 | L186-187 | `BOT_T`/`CHAT_T` 텔레그램 토큰 평문 | 🟡 (라이브 노드 관행 상속, 본 기능 신규 아님) |
| 중복 필드 | L210 `themeNosCount` = L219 `politicalThemesMatched` | 두 필드가 동일 값(정치 매칭 수). 하위호환 위해 `themeNosCount` 유지, `politicalThemesMatched` 신규 — 의도적 중복 | 🟢 Info |

### 4.3 Security Issues

| 심각도 | 위치 | 이슈 | 권장 |
|--------|------|------|------|
| 🟡 Warning | L186-187 | 텔레그램 BOT 토큰/CHAT ID 평문(본 기능 도입분 아님, 기존 노드 관행) | 후속 과제로 static data/env 이전 검토(risk-blacklist analysis §9.3와 동일 백로그) |
| 🟢 Info | 전역 | 네이버 공개 페이지 스크래핑만, 인증/API 키 없음 | Design §7 준수 |

---

## 5. Performance Analysis

N/A (표준 웹 응답시간 지표 비해당). n8n 관점 참고:
- 상세 페이지 요청이 **266개 → 정치 매칭 수(현재 0개)** 로 대폭 감소 → 실행시간 단축 방향. Plan §3.2 NFR(08:45 실행 1분 이내) 목표는 **런타임 미검증(배포 대기)**.
- concurrency 6, `DETAIL_SLEEP_MS=120`, `fetchTextRetry` timeout 30000ms(L9) — 라이브와 동일, hang 방지 유지.

---

## 6. Test Coverage

N/A — 자동화 테스트 프레임워크 없음(n8n Function 노드, 순수 JS). Design §8 테스트는 수동(Manual Trigger + Log Viewer) 기반.

| 테스트 (Design §8.2) | 상태 |
|----------------------|------|
| Happy path (정치 테마만 선별) | ⏳ 배포 후 검증 대기 (현재 정치 0건이라 실질 happy path 관측 불가) |
| `politicalThemesMatched`/`totalThemesFound` 알림·반환 일치 | 🟢 코드상 보장(L219/L218, L245/L244), 런타임 미검증 |
| Edge: 정치 0건 + 스크래핑 성공 → 캐시 비움 | 🟢 코드상 보장(L190-193 Case A), 런타임 미검증 |
| Edge: 정치 매칭 + 상세 전멸 → 캐시 유지 | 🟢 코드상 보장(L193 Case C), 런타임 미검증 |
| Edge: 목록 조회 실패 → `ok:false`(회귀 없음) | 🟢 코드상 보장(L122-133), 런타임 미검증 |
| §8.3 Do 단계 사전 검증 (정규식 266/266) | ✅ 완료 (`cache/_naver_theme_page{1-7}.utf8.html`) |

---

## 7. Clean Architecture Compliance (n8n Function 노드 구조로 대체)

> Design §9: 표준 Presentation/Application/Domain/Infrastructure 레이어 비적용. n8n 함수 단위 책임 분리로 대체 평가.

### 7.1 Layer(함수 역할) 배치 검증 (Design §9.1 / §9.4)

| 역할 | Design 위치 | 실제 위치 | 상태 |
|------|-------------|-----------|------|
| Orchestration | 메인 실행 블록 | L114-255 | ✅ |
| Source Adapter: `extractThemeEntries` (교체) | 노드 내부 | L64-79 | ✅ |
| Source Adapter: `extractCodes` (유지) | 노드 내부 | L81-84 | ✅ |
| Filter: `isPoliticalTheme` (신규) | `POLITICAL_KEYWORDS` 바로 아래 | L59-61 (L53-57 상수 직후) | ✅ |
| `POLITICAL_KEYWORDS` 상수 | 노드 상단 튜닝 상수 근처 | L53-57 (튜닝 상수 블록 L107보다 위, `fetchTextRetry` 아래) | ✅ 허용 |
| Infra(HTTP): `http`, `fetchTextRetry` | 헬퍼 | L4-12, L35-46 | ✅ |

### 7.2 Dependency Rule (Design §9.2)

| 규칙 | 준수 여부 |
|------|-----------|
| `isPoliticalTheme`는 Source Adapter 미호출(순수 함수, 부작용 없음) | ✅ `POLITICAL_KEYWORDS` 상수만 참조(L60) |
| Orchestration만 목록→필터→상세 조합 | ✅ 메인 블록에서만 조합(L164 필터, L172 상세) |
| `mapLimit → fetchTextRetry → http` 체인 | ✅ L172→L175→L4 |

### 7.3 Architecture Score

```
┌─────────────────────────────────────────────┐
│  n8n 노드 구조 준수: 100%                     │
│  (함수 역할 분리·의존 방향·순수 필터 완전 일치)│
└─────────────────────────────────────────────┘
```

---

## 8. Convention Compliance (Design §10)

### 8.1 Naming Convention

| 항목 | 규칙 (Design §10.1) | 실제 | 상태 |
|------|---------------------|------|------|
| 함수 camelCase 동사+명사 | `extractThemeEntries`, `isPoliticalTheme` | 준수 | ✅ |
| 상수 UPPER_SNAKE_CASE | `POLITICAL_KEYWORDS`, `MAX_LIST_PAGES`, `CONCURRENCY` | 준수 | ✅ |
| store 네임스페이스 | `store.blacklist.*` | `store.blacklist.themeFetchStats.politicalThemesMatched` 등 준수 | ✅ |
| FIX 태그 주석 | 기존 `FIX C-4`/`FIX W-6` 관행 유지, 신규 태그 추가 금지 | L190(`FIX C-4 (정치 필터 대응 수정)`), L223(`FIX W-6`) — 기존 태그 위치 유지, 신규 태그 없음 | ✅ |

### 8.2 실패 처리/관측성 패턴 (Design §10.4)

| 항목 | Design 규칙 | 실제 | 상태 |
|------|-------------|------|------|
| FIX C-4(0건 캐시 유지) 패턴 재사용·수정 | 신규 분기 추가 없이 기존 분기 조건만 확장 | L193에서 기존 분기에 `politicalEntries.length>0` 조건 추가(신규 함수/분기 아님) | ✅ |
| `themeFetchStats` 신규 3필드만 추가 | 기존 필드 삭제/변경 없음 | L212-221: 기존 5필드 유지 + 신규 3필드 | ✅ |
| `mapLimit` concurrency 6 재사용 | 유지 | L172, `CONCURRENCY=6`(L109) | ✅ |
| 캐시 유지 폴백 | 재사용 | L193-206 | ✅ |

### 8.3 Convention Score

```
┌─────────────────────────────────────────────┐
│  Convention Compliance: 100%                 │
├─────────────────────────────────────────────┤
│  Naming:            100%                     │
│  실패처리 패턴:      100% (기존 분기 확장)    │
│  동시성/캐시 폴백:   100%                     │
│  관측성 필드 추가:   100% (기존 필드 무변경)  │
└─────────────────────────────────────────────┘
비고: risk-blacklist(78%)와 달리 서킷/notifyOncePerDay 요구가
      본 기능 설계에 없어 감점 요인 부재.
```

---

## 9. Overall Score

```
┌─────────────────────────────────────────────┐
│  Overall Score: 95/100                       │
├─────────────────────────────────────────────┤
│  Design Match:        96 points              │
│  Code Quality:        94 points              │
│  Security:            88 points (토큰 평문)   │
│  Testing:             N/A (배포 후 수동 검증) │
│  Performance:         N/A (런타임 미검증)     │
│  Architecture(n8n):  100 points              │
│  Convention:         100 points              │
│  FIX C-4 건전성:     Sound (§3)              │
└─────────────────────────────────────────────┘
상태: 배포/런타임 검증 대기 — 정적 코드 정합성 기준 우수.
      감점 대부분이 Plan/Design 문서 stale(코드 결함 아님).
```

---

## 10. Document Updates Needed (코드가 정답 — 문서 갱신 필요)

- [ ] **Plan §3.1 FR-03 문언 갱신**: "정치 테마 0건 매칭 시 캐시 유지" → "정치 테마 0건은 정상 결과로 간주해 캐시를 비우고, 정치 테마가 매칭됐으나 상세 조회가 전멸한 경우에만 캐시 유지"로 수정(Do 단계 실데이터 검증 반영, Design §5.2와 일치화).
- [ ] **Design §6.1 Row 2 수정(내부 모순 해소)**: `isPoliticalTheme` 매칭 0건 행의 처리 서술이 "FIX C-4 캐시 유지 경로로 자연 처리"로 남아 있어 동일 표 Row 5 및 §5.2와 모순. Row 5(정치 0건=정상=캐시 비움)에 맞춰 Row 2를 갱신하거나 Row 2를 삭제하고 Row 5로 통합.
- [ ] (선택) Design §3.1 주석에 `themeNosCount`와 `politicalThemesMatched`가 동일 값(중복)임을 명시.

---

## 11. Recommended Actions

### 11.1 Immediate (배포 전 처리 권장)

| 우선 | 항목 | 위치 | 비고 |
|------|------|------|------|
| 🟢 1 | 문서 2건 수정(§10) — 코드 변경 불필요, Plan FR-03 / Design §6.1 Row 2 stale 해소 | plan.md §3.1, design.md §6.1 | 코드는 이미 정답 |
| 🟡 2 | 배포 후 **부분 상세 조회 실패 관측** 계획 확정 — `detailErrors > 0`이면서 `politicalThemesMatched > themeCodes 커버` 상황 모니터링 | 배포 후 n8n 로그 | §3.2 리스크 (a) |

### 11.2 Short-term (배포 후)

| 우선 | 항목 |
|------|------|
| 🟢 1 | Design §11.2 6~7 수행: Manual Trigger 1회 실행 → `politicalThemeNames` 육안 검토, 3영업일 로그 + 스윙 스캔 "제외(테마)" 수치 변화 확인 |
| 🟢 2 | 배포 후 첫 실행에서 `themeCodesCount`가 기존 2,342 → (현재 정치 0건이므로) 0으로 정상 갱신되는지 확인 — 이는 의도된 동작 |
| 🟡 3 | 향후 네이버에 정치 테마 재등장 시 자동 차단 재개 여부 재검증(정치 카테고리 활성화 시점) |

### 11.3 Long-term (backlog)

| 항목 | 비고 |
|------|------|
| 텔레그램 BOT/CHAT 토큰 static data/env 이전 | 기존 노드 공통 관행, 본 기능 범위 밖 |
| `extractThemeEntries` 스크래핑 무결성 가드 | 예: `allEntries.length`가 직전 실행 대비 급감(예: 50% 이하)하면 캐시 오삭제 방지 위해 보수적 처리 검토 (§3.2 리스크 b) |
| `POLITICAL_KEYWORDS` 목록 정기 점검 자동화 | Plan §2.2 Out of Scope, 별도 Plan |
| 비정치 투기적 테마 필터 | Plan §2.2 Out of Scope, 배포 후 스캔 품질 보고 결정 |

---

## 12. Next Steps

- [ ] 🟢 문서 2건 수정(§10) — Plan FR-03 / Design §6.1 Row 2 stale 해소
- [ ] 라이브 n8n `Theme Blacklist Updater` 노드에 `Refresh_Theme_Blacklist_Naver_code.js` 반영(배포)
- [ ] Manual Trigger 1회 실행 → `politicalThemeNames`/`themeCodesCount` 확인 → 3영업일 로그 검증
- [ ] 검증 완료 후 재분석 및 완료 보고서(`theme-blacklist-political-filter.report.md`) 작성

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-14 | Initial gap analysis (배포 전, 코드 정합성 기준) | kevin (bkit-gap-detector) |

# theme-blacklist-political-filter Design Document

> **Summary**: `Theme Blacklist Updater` n8n 노드 내부에서 네이버 테마 266개 전체를 무차별 차단하는 `extractThemeNos()` 기반 로직을, 테마명까지 함께 추출해 정치 테마만 골라내는 `extractThemeEntries()` + `isPoliticalTheme()` 로직으로 교체하는 구현 설계.
>
> **Project**: showmoneyv2 (Autostock Swing Scanner)
> **Version**: n/a (n8n workflow, `algo-v1.0` 기준)
> **Author**: kevin
> **Date**: 2026-07-14
> **Status**: Draft
> **Planning Doc**: [theme-blacklist-political-filter.plan.md](../../01-plan/features/theme-blacklist-political-filter.plan.md)

### Pipeline References (if applicable)

N/A — 9-phase Development Pipeline 대상 프로젝트가 아니며, 운영 중인 n8n 워크플로우에 대한 개선 작업이므로 Phase 1~4 문서는 해당 없음.

---

## 1. Overview

### 1.1 Design Goals

- `Theme Blacklist Updater` 노드(라이브 워크플로우 `autostock_showmoneyv2_20260714_toss_confirm_risk_blacklist.json`, 194라인)가 네이버 테마 목록의 **모든** 테마(현재 266개)를 무차별로 블랙리스트에 편입시키는 문제를, **정치 테마로 판정된 테마만** 편입시키도록 교체한다.
- 이미 로컬에 작성된 `Refresh_Theme_Blacklist_Naver_code.js`(217라인, 미배포)의 `POLITICAL_KEYWORDS`/`isPoliticalTheme`/`extractThemeEntries` 로직을 재사용하되, 해당 초안에는 없는 **라이브 노드의 운영 패턴(텔레그램 알림, 0건 시 캐시 유지 폴백, `BOT_T`/`CHAT_T` 토큰)은 반드시 유지**한다.
- 기존 함수(`fetchTextRetry`, `extractCodes`, `mapLimit`, 상세 페이지 조회 루프)는 최대한 그대로 두고, 테마 수집·필터링 부분만 교체하는 최소 침습 방식을 따른다.

### 1.2 Design Principles

- **최소 침습(Minimal Invasion)**: `extractThemeNos` → `extractThemeEntries`로 교체하는 지점과 필터링 지점(L94~138 대응부)만 수정하고, 상세 조회(L140~154)·저장/알림(L156~193) 로직은 구조를 유지한 채 필드만 확장한다.
- **정치 필터 로직 이식, 운영 패턴은 라이브 기준(Merge, not Replace)**: `Refresh_Theme_Blacklist_Naver_code.js`를 통째로 덮어쓰지 않는다. 그 파일에서는 `POLITICAL_KEYWORDS`, `isPoliticalTheme`, `extractThemeEntries` 3가지만 가져오고, 텔레그램 알림·FIX C-4 캐시 유지 폴백은 라이브 노드 코드를 그대로 유지한다.
- **관측 가능성(Observability) 우선**: 필터링 전후 수치(전체 테마 수, 정치 테마 매칭 수, 매칭된 테마명 목록)를 `store.blacklist.themeFetchStats`와 텔레그램 알림에 모두 남겨, 배포 직후 정치 키워드 매칭이 의도대로 동작했는지 즉시 확인 가능하게 한다.

---

## 2. Architecture

### 2.1 Component Diagram

```
┌────────────────────────────┐     ┌──────────────────────────────┐     ┌────────────────────────┐
│ Theme Blacklist Trigger    │────▶│ Theme Blacklist Updater       │────▶│ store.blacklist.        │
│ (n8n cron, 08:45 KST)      │     │ (n8n Function 노드)           │     │ themeCodes              │
└────────────────────────────┘     │  ├─ fetchTextRetry (유지)     │     │ (workflow static data) │
                                    │  ├─ extractThemeEntries ★교체 │     └────────────────────────┘
                                    │  ├─ isPoliticalTheme ★신규    │              │
                                    │  ├─ extractCodes (유지)       │              ▼
                                    │  └─ mapLimit (유지)           │     ┌────────────────────────┐
                                    └──────────────┬────────────────┘     │ Telegram 알림 발송       │
                                                   │                      └────────────────────────┘
                                                   ▼
                                    ┌──────────────────────────────┐
                                    │ finance.naver.com             │
                                    │ /sise/theme.naver (목록)      │
                                    │ /sise/sise_group_detail.naver │
                                    │   (정치 테마만 상세 조회)      │
                                    └──────────────────────────────┘
```

### 2.2 Data Flow

```
[08:45 Cron 발동]
  → 테마 목록 페이지(최대 20페이지) 순회
      → extractThemeEntries(html)로 {no, name} 쌍 수집 (기존 extractThemeNos 대체)
  → allEntries(전체 테마, 현재 약 266개)에 대해 isPoliticalTheme(name) 필터링
      → politicalEntries만 남김 (POLITICAL_KEYWORDS 매칭)
  → politicalEntries의 no만 상세 페이지(sise_group_detail.naver) 동시 조회(concurrency 6, 기존 유지)
      → extractCodes(html)로 종목코드 수집 → codeSet 병합
  → 0건이면 기존 캐시 유지 + 텔레그램 경고(기존 FIX C-4 패턴 그대로)
  → 0건 아니면 store.blacklist.themeCodes 갱신 + 텔레그램 성공 알림(문구에 전체/정치 테마 수 병기)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `extractThemeEntries(html)` | 정규식 기반 HTML 파싱 (신규, `Refresh_Theme_Blacklist_Naver_code.js` 이식) | 테마 번호+이름 동시 추출 |
| `isPoliticalTheme(name)` | `POLITICAL_KEYWORDS` 상수 (신규, 동일 파일에서 이식) | 정치 테마 여부 판정 |
| 상세 조회 루프 (L140~154, 변경 없음) | `politicalEntries.map(e => e.no)` | 정치 테마만 상세 조회 대상으로 축소 |
| 텔레그램 알림 (L162~193, 로직 유지·문구만 확장) | `BOT_T`/`CHAT_T` (기존, 변경 없음) | 결과 알림 |

---

## 3. Data Model

### 3.1 Entity Definition (workflow static data 확장)

```javascript
// store.blacklist (기존 구조 확장)
{
  themeCodes: string[],           // 기존 — 이제 "정치 테마"에 속한 종목만 포함 (동작 변경, 필드명은 유지)
  themeUpdatedAt: string,         // 기존 — ISO timestamp (변경 없음)
  themeNosCount: number,          // 기존 — 이제 "정치 테마 매칭 수"를 의미 (전체 테마 수 아님, 명확화 필요)
  themeSource: string,            // 'naver:sise_group_detail' → 'naver:sise_group_detail:political_only' 로 갱신
  themeFetchStats: {              // 기존 구조에 필드 추가
    stoppedEarlyAtPage: number | null,  // 기존
    maxPageTried: number,                // 기존
    concurrency: number,                 // 기존
    detailErrors: number,                // 기존
    ms: number,                          // 기존
    totalThemesFound: number,            // ★신규 — 필터링 전 전체 테마 수(약 266)
    politicalThemesMatched: number,      // ★신규 — 정치 테마로 판정된 테마 수
    politicalThemeNames: string[],       // ★신규 — 매칭된 테마명 목록 (배포 직후 육안 검증용)
  },
}
```

### 3.2 Entity Relationships

```
[Theme Blacklist Updater]
   │ fetches
   ▼
[finance.naver.com/sise/theme.naver] → allEntries: {no, name}[]
   │ filter: isPoliticalTheme(name)
   ▼
[politicalEntries] → sise_group_detail.naver(no) → [store.blacklist.themeCodes]
```

### 3.3 Database Schema

N/A — 별도 DB 없음. 모든 상태는 n8n `getWorkflowStaticData('global')`(workflow static data)에 저장(기존 방식 그대로).

---

## 4. 정치 테마 판정 사양

### 4.1 `POLITICAL_KEYWORDS` (기존 초안에서 그대로 이식)

```javascript
const POLITICAL_KEYWORDS = [
  '대선', '대통령', '총선', '선거', '정치', '국회', '의원',
  '여당', '야당', '공천', '후보', '당대표', '대권', '집권',
  '국정감사', '탄핵', '윤석열', '이재명', '한동훈',
];

function isPoliticalTheme(name) {
  return POLITICAL_KEYWORDS.some((kw) => name.includes(kw));
}
```

> **Design 단계 확인 필요(Do 진입 전)**: 이 키워드 목록은 2026-07 시점 초안 그대로이며, 최신 정치 이슈(신규 후보명 등) 반영 여부는 Do 단계에서 실제 테마명 266개 목록을 1회 조회해 수동 대조 검증한다(Plan §5 Risk 대응).

### 4.2 `extractThemeEntries(html)` (신규, `extractThemeNos` 대체)

```javascript
// Refresh_Theme_Blacklist_Naver_code.js 이식, 라이브 노드 정규식 스타일에 맞춰 조정
function extractThemeEntries(html) {
  const seen = new Set();
  const entries = [];
  for (const m of html.matchAll(
    /sise_group_detail\.naver\?type=theme&(?:amp;)?no=(\d+)[^>]*>([^<]{1,60})/g
  )) {
    const no = m[1];
    const name = m[2].trim();
    if (!seen.has(no) && name.length > 0) {
      seen.add(no);
      entries.push({ no, name });
    }
  }
  return entries;
}
```

> **Note**: 라이브 노드의 기존 `extractThemeNos`는 `&(?:amp;)?` 대체 패턴 없이 `&no=`만 매칭했다(L54: `/sise_group_detail\.naver\?type=theme&no=(\d+)/g`). 페이지 소스에 `&amp;no=` 형태가 섞여 있을 가능성에 대비해 `extractThemeEntries`는 `(?:amp;)?`를 포함한 초안 정규식을 그대로 채택한다. Do 단계에서 실제 목록 페이지 HTML로 두 정규식의 매칭 결과 개수가 동일한지 1회 대조한다.

### 4.3 페이지 순회 로직 변경 (라이브 노드 L94~138 대응)

```javascript
// 기존(L94~138)은 Set<string>(테마번호)만 누적 → allEntries: {no, name}[] 누적으로 변경
const html1 = await fetchTextRetry(`${baseList}?&page=1`, listReferer, 2);
let allEntries = extractThemeEntries(html1);   // 기존: extractThemeNos(html1)

if (allEntries.length === 0) {
  return [{ json: { ok: false, reason: 'No theme entries found on list page', ... } }];
}

const seenNos = new Set(allEntries.map((e) => e.no));
let stoppedEarlyAtPage = null;

for (let p = 2; p <= maxPage; p++) {
  await sleep(LIST_SLEEP_MS);
  const html = await fetchTextRetry(`${baseList}?&page=${p}`, listReferer, 2);
  const entries = extractThemeEntries(html);   // 기존: extractThemeNos(html)

  let added = 0;
  for (const entry of entries) {
    if (!seenNos.has(entry.no)) {
      seenNos.add(entry.no);
      allEntries.push(entry);
      added++;
    }
  }
  if (added === 0 && p >= 3) { stoppedEarlyAtPage = p; break; }
}

// ★신규: 정치 테마 필터링
const politicalEntries = allEntries.filter((e) => isPoliticalTheme(e.name));
const themeNos = politicalEntries.map((e) => e.no);   // 이후 L140~154 상세 조회 루프는 변경 없이 그대로 사용
```

> 페이지 수 추정(`pagesFound`/`maxPage` 계산, L112~114)은 `html1.matchAll(/page=(\d+)/g)` 기반으로 테마 이름 추출과 무관하므로 **변경 없음**.

---

## 5. 저장/알림 로직 변경 (라이브 노드 L156~193 대응)

### 5.1 변경 전 (현재 라이브 코드, L156~193)

```javascript
const themeCodes = [...codeSet].sort();
...
store.blacklist.themeSource = 'naver:sise_group_detail';
store.blacklist.themeFetchStats = { stoppedEarlyAtPage, maxPageTried: maxPage, concurrency: CONCURRENCY, detailErrors: detailErrors.length, ms: Date.now() - startTs };
...
text: '✅ [테마 블랙리스트 갱신 성공]' + NL_T + '총 ' + themeCodes.length + '개 종목 / 테마 ' + themeNos.length + '개' + NL_T + '갱신: ' + ...
```

### 5.2 변경 후

```javascript
const themeCodes = [...codeSet].sort();
const prevThemeCodes = Array.isArray(store.blacklist.themeCodes) ? store.blacklist.themeCodes : [];
const BOT_T = '8366696724:AAHROcjGoQEn9BziD-sYdAu3ZuaolwtkgLE';  // 변경 없음
const CHAT_T = '523002062';                                        // 변경 없음
const NL_T = String.fromCharCode(10);

// FIX C-4 (★수정 — 2026-07-14 실데이터 검증 후 반영): 실제 네이버 테마 266개를 대조해보니
// 현재(비선거 시즌) 정치 테마가 0건이 정상 상태임을 확인. 기존처럼 "결과 0건 = 캐시 유지"로 두면
// 정치 테마가 항상 0건인 지금 시점에 필터가 영구히 무효화되어 옛 2,342개 캐시가 그대로 남는다.
// → "정치 테마 자체가 0건"(정상)과 "상세 조회 실패로 0건"(장애)을 구분해야 한다.
if (themeCodes.length === 0 && politicalEntries.length > 0 && prevThemeCodes.length > 0) {
  // 정치 테마는 매칭됐으나 상세 페이지 조회가 전부 실패한 경우에만 캐시 유지
  try { await http({ ... text: '⚠️ [테마 블랙리스트] 정치 테마 ' + politicalEntries.length + '개 매칭됐으나 상세 조회 실패 — 기존 캐시 유지' + ... }); } catch(e) {}
  return [{ json: { ok: true, keptCache: true, themeCodesCount: prevThemeCodes.length } }];
}
// politicalEntries.length === 0 인 경우는 정상 결과이므로 아래 저장 로직으로 그대로 진행되어 themeCodes=[]로 갱신된다.

store.blacklist.themeCodes = themeCodes;
store.blacklist.themeUpdatedAt = new Date().toISOString();
store.blacklist.themeNosCount = themeNos.length;                         // 이제 "정치 테마 매칭 수"
store.blacklist.themeSource = 'naver:sise_group_detail:political_only';  // ★변경
store.blacklist.themeFetchStats = {
  stoppedEarlyAtPage, maxPageTried: maxPage, concurrency: CONCURRENCY, detailErrors: detailErrors.length,
  ms: Date.now() - startTs,
  totalThemesFound: allEntries.length,                                   // ★신규
  politicalThemesMatched: politicalEntries.length,                       // ★신규
  politicalThemeNames: politicalEntries.map((e) => e.name),              // ★신규
};

// FIX W-6: 성공 알림 (문구 확장)
try {
  await http({ method: 'POST', url: 'https://api.telegram.org/bot' + BOT_T + '/sendMessage', json: true, body: {
    chat_id: CHAT_T,
    text: '✅ [테마 블랙리스트 갱신 성공]' + NL_T
      + '총 ' + themeCodes.length + '개 종목 / 정치 테마 ' + themeNos.length + '개 (전체 ' + allEntries.length + '개 중)' + NL_T
      + '갱신: ' + store.blacklist.themeUpdatedAt,
  } });
} catch(e) {}

return [{ json: {
  ok: true, done: true,
  totalThemesFound: allEntries.length,
  politicalThemesMatched: politicalEntries.length,
  politicalThemeNames: politicalEntries.map((e) => e.name),
  themeNosCount: themeNos.length,
  themeCodesCount: themeCodes.length,
  themeUpdatedAt: store.blacklist.themeUpdatedAt,
  stats: store.blacklist.themeFetchStats,
  sampleCodes: themeCodes.slice(0, 20),
  detailErrors: detailErrors.slice(0, 10),
} }];
```

**변경 전/후 텔레그램 알림 비교:**

변경 전:
```
✅ [테마 블랙리스트 갱신 성공]
총 2342개 종목 / 테마 266개
갱신: 2026-07-13T23:46:00.126Z
```

변경 후 (예시, 실제 수치는 배포 후 확인):
```
✅ [테마 블랙리스트 갱신 성공]
총 {N}개 종목 / 정치 테마 {M}개 (전체 266개 중)
갱신: {timestamp}
```

---

## 6. Error Handling

### 6.1 Error Case Definition

| Case | Cause | Handling |
|------|-------|----------|
| 목록 페이지에서 테마 항목 0건 | 네이버 페이지 구조 변경/차단 | 기존과 동일하게 `ok:false` 반환, 페이지 스니펫 포함(변경 없음) |
| `isPoliticalTheme` 매칭 0건(스크래핑 자체는 정상 성공) | 비선거 시즌 등으로 네이버에 정치 테마 카테고리가 실제로 존재하지 않음(2026-07-14 실측 확인, §8.3) | `politicalEntries.length === 0` → `themeNos=[]` → 상세 조회 스킵 → `themeCodes=[]`. ⚠️ **기존 FIX C-4("0건이면 무조건 캐시 유지")를 그대로 쓰면 안 됨** — 옛 캐시(2,342개)가 영구 보존되어 필터가 무효화된다. **수정된 분기**(§5.2): 이 경우(`politicalEntries.length === 0`)는 정상 결과로 간주해 캐시를 비우고 정상 갱신한다. |
| 상세 페이지 조회 실패(정치 테마는 매칭됐으나 전부 실패) | 네트워크 오류/차단 | 기존 `mapLimit`의 `errors` 수집 로직 그대로 재사용. `politicalEntries.length > 0`인데 `themeCodes.length === 0`인 이 경우에만 §5.2의 캐시 유지 분기가 적용된다 |
| `extractThemeEntries` 정규식 미매칭(테마명 파싱 실패) | 네이버 마크업이 `extractThemeNos`가 가정한 것과 다른 위치에 이름을 노출 | Do 단계에서 실제 HTML 샘플로 사전 검증(§4.2 Note), 매칭 실패 시 §4.2의 대체 정규식 조정 |

### 6.2 Error Response Format

N/A — REST API 응답 포맷이 아니라 n8n 노드 반환 객체. 기존 포맷 유지(§5.2 반환 구조 참고).

---

## 7. Security Considerations

- [x] 네이버 공개 페이지 스크래핑만 사용 — 인증/API 키 없음, 이번 변경으로 신규 보안 고려사항 없음
- [x] 텔레그램 BOT/CHAT 토큰은 기존 라이브 코드에 이미 평문 존재(L159~160) — 이번 기능 범위에서 신규로 노출을 늘리지 않음(risk-blacklist-toss-api analysis §9.3에서 이미 후속 과제로 분리된 기존 이슈, 본 Design에서 재수정하지 않음)
- [ ] N/A: 사용자 입력 없음(서버-서버 배치)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| 정규식 검증 | `extractThemeEntries`가 실제 목록 페이지 HTML에서 `extractThemeNos`와 동일한 테마 수를 추출하는지 | n8n Manual Trigger + Log Viewer 노드(기존 존재) |
| 키워드 매칭 검토 | 266개 테마명 전체 중 `isPoliticalTheme` 매칭 결과 수동 검토(오탐/누락) | `politicalThemeNames` 배열 육안 확인 |
| 회귀 확인 | 상세 조회(`extractCodes`)·`mapLimit`·FIX C-4 캐시 유지 로직 무변경 | 코드 diff 리뷰 |
| 장애 주입 | 정치 키워드를 임시로 매칭 불가능하게 설정 후 0건 캐시 유지 경로 동작 확인 | n8n Manual Trigger |

### 8.2 Test Cases (Key)

- [ ] Happy path: 정치 테마(예: 관련 테마명)만 정확히 골라내고 나머지(반도체, 2차전지 등)는 제외됨
- [ ] `politicalThemesMatched`/`totalThemesFound` 값이 텔레그램 알림·반환 객체에 일치하게 기록됨
- [ ] Edge case: 정치 테마 매칭 0건이지만 스크래핑 자체는 성공한 경우 → 캐시를 비우고 정상 갱신됨(§6.1 수정 반영, 무조건 캐시 유지 아님)
- [ ] Edge case: 정치 테마는 매칭됐으나 상세 조회가 전부 실패한 경우에만 캐시 유지
- [ ] Edge case: 목록 페이지 조회 자체가 실패해도 기존과 동일하게 `ok:false` 응답(회귀 없음)

### 8.3 Do 단계 사전 검증 결과 (실행일: 2026-07-14)

`curl`로 네이버 테마 목록 페이지 1~7페이지(전체) 원본 HTML을 직접 가져와 Node.js로 두 정규식과 정치 키워드 매칭을 실측했다.

| 검증 항목 | 결과 |
|-----------|------|
| `extractThemeEntries` vs 라이브 `extractThemeNos` 매칭 수 | **266 vs 266, 완전 일치** — 정규식 교체 안전함 확인 |
| 현재 시점 `isPoliticalTheme` 매칭 결과 | **0/266건** — 2026-07-14 기준 네이버에 정치 테마 카테고리가 존재하지 않음(비선거 시즌) |
| 파생 이슈 | 기존 FIX C-4를 그대로 쓰면 "0건=캐시 유지"로 처리되어 옛 2,342개 캐시가 영구 보존됨 → §5.2/§6.1에 수정 반영(정치 테마 자체가 0건인 경우는 정상 결과로 캐시를 비움) |
| 결론 | 수정 반영 후 배포 시 **테마 블랙리스트가 0개(정치 테마 없음)로 정상 갱신**될 것으로 예상됨 — 이는 의도된 동작이며, 향후 네이버에 정치 테마가 다시 생기면 자동으로 해당 종목만 차단 재개 |

### 8.4 QA 드라이런 결과 (n8n Function 노드 전체 실행 시뮬레이션, 실행일: 2026-07-14)

Gap 분석(Match Rate 96%) 이후, 실제 배포 전에 `Refresh_Theme_Blacklist_Naver_code.js` 전체를 Node.js `vm` 모듈로 감싸 n8n 실행 컨텍스트(`this.getWorkflowStaticData`, `this.helpers.httpRequest`)를 모킹한 하네스로 end-to-end 드라이런했다. 목록 페이지는 §8.3에서 수집한 실제 캐시된 HTML(`cache/_naver_theme_page{1-7}.utf8.html`)을 사용했고, 텔레그램 전송은 실제 발송 없이 모킹해 기록만 남겼다.

| 시나리오 | 검증 목적 | 결과 |
|---------|-----------|------|
| A. 최초 실행(캐시 없음) | 정상 최초 실행 시 에러 없이 완료되는지 | ✅ 에러 없음, `totalThemesFound=266`, `politicalThemesMatched=0`, `themeCodes=[]` |
| B. 기존 캐시 = 오늘자 실제 운영값 2,342개 | **핵심 버그 수정 검증** — 실제로 옛 캐시가 비워지는지(로직상 추론이 아니라 실행 결과로 확인) | ✅ 실행 후 `store.blacklist.themeCodes.length === 0`(2,342 → 0), 텔레그램 성공 알림만 발송(경고 알림 아님) |
| C. 정치 테마 1건 매칭 + 상세 페이지 조회 전부 실패(합성 데이터) | 상세조회 실패 시 캐시 유지 분기가 여전히 정상 동작하는지(회귀 확인) | ✅ `keptCache:true`, 기존 캐시(2건) 그대로 보존, "정치 테마 1개 매칭됐으나 상세 조회 실패" 경고 정상 발송 |

부가 확인: 정치 테마가 0건일 때 상세 페이지(`sise_group_detail.naver`) 호출이 **0건**으로 집계됨 — 불필요한 네트워크 호출 없이 목록 조회만으로 종료되어 Plan §3.2 NFR(실행시간 단축) 방향과 일치.

**결론: 3개 시나리오 전부 통과, 발견된 이슈 없음.** 로컬 구현은 배포 준비 완료 상태이며, 실제 라이브 배포와 08:45 KST 실행 로그 확인만 남아 있음(§11.2 6~7).

---

## 9. Clean Architecture (n8n Function 노드 구조로 대체)

> 이 프로젝트는 레이어드 웹앱이 아니므로 표준 Presentation/Application/Domain/Infrastructure 레이어는 적용하지 않는다. 대신 **n8n Function 노드 내부 함수 단위 책임 분리**로 대체한다.

### 9.1 Layer Structure (대체 매핑)

| 역할 | 책임 | 위치(함수) |
|-------|---------------|----------|
| Trigger | 스케줄 발동 | `Theme Blacklist Trigger (08:45 KST)` (cron 노드, 변경 없음) |
| Orchestration | 목록 수집 → 필터링 → 상세 조회 → 저장/알림 | `Theme Blacklist Updater` 노드의 메인 실행 블록 |
| Source Adapter | 목록/상세 페이지 파싱 | `extractThemeEntries` ★교체, `extractCodes` (유지) |
| Filter | 정치 테마 판정 | `isPoliticalTheme` ★신규 |
| Infra (HTTP) | 실제 네트워크 호출 | `http()`, `fetchTextRetry()` (기존 헬퍼 재사용) |

### 9.2 Dependency Rules

```
Orchestration(메인 실행 블록)
   ├─▶ extractThemeEntries()  ─▶ (정규식 파싱, 외부 호출 없음)
   ├─▶ isPoliticalTheme()     ─▶ POLITICAL_KEYWORDS (상수만 참조)
   ├─▶ extractCodes()         ─▶ (정규식 파싱, 변경 없음)
   └─▶ mapLimit()             ─▶ fetchTextRetry() ─▶ http()

규칙: Filter(isPoliticalTheme)는 Source Adapter를 호출하지 않는다(순수 함수, 부작용 없음).
      Orchestration만 목록 수집 → 필터링 → 상세 조회 순서로 조합한다.
```

### 9.3 File Import Rules

N/A — 단일 n8n Function 노드 내 하나의 코드 블록(모듈 임포트 체계 없음).

### 9.4 This Feature's Layer Assignment

| Component | 역할 | 위치 |
|-----------|-------|----------|
| `extractThemeEntries(html)` | Source Adapter (교체) | `Theme Blacklist Updater` 노드 코드 내부 |
| `isPoliticalTheme(name)` | Filter (신규) | 동일 노드, `POLITICAL_KEYWORDS` 바로 아래 |
| `POLITICAL_KEYWORDS` 상수 | 매핑 정의 (신규) | 노드 코드 상단, `MAX_LIST_PAGES` 등 튜닝 상수 근처 |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions (기존 노드 코드 컨벤션 그대로 적용)

| Target | Rule | Example |
|--------|------|---------|
| 함수 | camelCase, 동사+명사 | `extractThemeEntries`, `isPoliticalTheme` |
| 상수 | UPPER_SNAKE_CASE | `POLITICAL_KEYWORDS`, `MAX_LIST_PAGES` |
| store 네임스페이스 | `store.blacklist.*` 패턴 유지 | `store.blacklist.themeFetchStats.politicalThemesMatched` |
| FIX 태그 주석 | 기존 노드의 `FIX C-4`, `FIX W-6` 관행 유지 | 새 코드에는 신규 FIX 태그 추가하지 않고 기존 태그 위치만 유지 |

### 10.2 Import Order

N/A — n8n Function 노드는 모듈 임포트 없이 단일 스코프 내 정의(기존 코드 전체와 동일 스타일 유지).

### 10.3 Environment Variables

N/A — 인증 불필요(공개 페이지 스크래핑).

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 함수 명명 | 기존 노드의 `extract*` 접두사 패턴 유지 |
| 실패 처리 | 기존 FIX C-4(0건 캐시 유지) 패턴 그대로, 신규 분기 추가하지 않음 |
| 관측성 | `themeFetchStats`에 신규 필드 3개만 추가(기존 필드 삭제/변경 없음) |

---

## 11. Implementation Guide

### 11.1 File/Node Structure

```
n8n Workflow: autostock_showmoneyv2_20260714_toss_confirm_risk_blacklist.json (또는 이후 최신 임포트본)
└── Theme Blacklist Updater (Function 노드)
    ├── POLITICAL_KEYWORDS 상수 추가 (L83 튜닝 포인트 블록 근처)
    ├── isPoliticalTheme(name) 함수 추가
    ├── extractThemeNos(html) → extractThemeEntries(html) 교체 (L52-55 대응)
    ├── 페이지 순회 로직을 Set<no> → {no,name}[] 누적으로 변경 (L94-138 대응)
    ├── politicalEntries 필터링 추가, themeNos = politicalEntries.map(e=>e.no)
    └── 저장/알림 블록에 totalThemesFound/politicalThemesMatched/politicalThemeNames 반영 (L156-193 대응)
```

### 11.2 Implementation Order

1. [ ] 실제 네이버 테마 목록 페이지 HTML 1페이지 확보 → `extractThemeEntries` 정규식이 `extractThemeNos`와 동일한 no 집합을 추출하는지, 이름도 정상 추출되는지 사전 검증
2. [ ] `POLITICAL_KEYWORDS`/`isPoliticalTheme` 추가
3. [ ] `extractThemeNos` → `extractThemeEntries` 교체, 페이지 순회 로직을 엔트리 배열 누적 방식으로 수정
4. [ ] `politicalEntries` 필터링 후 `themeNos` 재정의(하위 상세 조회 루프는 무변경)
5. [ ] `themeFetchStats`/텔레그램 알림 문구에 신규 필드 반영
6. [ ] n8n Manual Trigger로 1회 실행 → `politicalThemeNames` 목록을 육안으로 검토(오탐/누락 확인)
7. [ ] 라이브 배포 후 3영업일 실행 로그 확인 + 같은 기간 스윙 스캔 "제외(테마)" 수치 변화 확인

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-14 | Initial draft | kevin |

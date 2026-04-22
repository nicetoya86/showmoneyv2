const store = this.getWorkflowStaticData('global');
if (!store.blacklist) store.blacklist = {};

const http = async (o) =>
  await this.helpers.httpRequest(
    Object.assign(
      {
        timeout: 30000,
      },
      o
    )
  );

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function toText(raw) {
  if (Buffer.isBuffer(raw)) return raw.toString('utf8');
  return String(raw ?? '');
}

async function fetchText(url, referer) {
  const raw = await http({
    method: 'GET',
    url,
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      Referer: referer || 'https://finance.naver.com/',
      'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
    },
    json: false,
  });
  return toText(raw);
}

async function fetchTextRetry(url, referer, tries = 2) {
  let lastErr;
  for (let i = 0; i < tries; i++) {
    try {
      return await fetchText(url, referer);
    } catch (e) {
      lastErr = e;
      await sleep(300 + i * 500);
    }
  }
  throw lastErr;
}

function uniq(arr) {
  return [...new Set(arr)];
}

// 정치 테마 키워드 — 여기에 원하는 키워드를 추가/제거하세요
const POLITICAL_KEYWORDS = [
  '대선', '대통령', '총선', '선거', '정치', '국회', '의원',
  '여당', '야당', '공천', '후보', '당대표', '대권', '집권',
  '국정감사', '탄핵', '윤석열', '이재명', '한동훈',
];

function isPoliticalTheme(name) {
  return POLITICAL_KEYWORDS.some((kw) => name.includes(kw));
}

// 테마번호 + 테마명을 함께 추출
function extractThemeEntries(html) {
  const seen = new Set();
  const entries = [];
  // <a href="...?type=theme&no=123">테마명</a> 패턴
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

function extractCodes(html) {
  // /item/main.naver?code=005930
  return uniq([...html.matchAll(/code=(\d{6})/g)].map((m) => m[1]));
}

async function mapLimit(list, limit, worker) {
  const results = [];
  const errors = [];
  let idx = 0;

  const runners = new Array(Math.min(limit, list.length)).fill(0).map(async () => {
    while (idx < list.length) {
      const i = idx++;
      try {
        results[i] = await worker(list[i], i);
      } catch (e) {
        errors.push({ i, item: list[i], message: e?.message || String(e) });
        results[i] = null;
      }
    }
  });

  await Promise.all(runners);
  return { results, errors };
}

// ====== 튜닝 포인트(차단/느림이면 여기만 조절) ======
const MAX_LIST_PAGES = 20;     // 테마 목록 페이지 최대 탐색
const CONCURRENCY = 6;         // 테마 상세 동시 요청 수 (차단되면 3으로 낮추세요)
const DETAIL_SLEEP_MS = 120;   // 상세 요청 사이 아주 짧은 텀(차단 완화)
const LIST_SLEEP_MS = 120;     // 목록 페이지 요청 텀
// =====================================================

const startTs = Date.now();
const baseList = 'https://finance.naver.com/sise/theme.naver';
const listReferer = 'https://finance.naver.com/sise/theme.naver';

// 1) 테마 목록 수집 (테마번호 + 테마명)
const html1 = await fetchTextRetry(`${baseList}?&page=1`, listReferer, 2);
let allEntries = extractThemeEntries(html1);

if (allEntries.length === 0) {
  return [
    {
      json: {
        ok: false,
        reason: 'No theme entries found on list page',
        lenUtf8: html1.length,
        snippet: html1.slice(0, 1200),
      },
    },
  ];
}

// 페이지 수 추정
const pagesFound = uniq([...html1.matchAll(/page=(\d+)/g)].map((m) => Number(m[1]) || 1)).filter((n) => n >= 1);
let maxPage = pagesFound.length ? Math.max(...pagesFound) : MAX_LIST_PAGES;
maxPage = Math.min(maxPage, MAX_LIST_PAGES);

const seenNos = new Set(allEntries.map((e) => e.no));
let stoppedEarlyAtPage = null;

for (let p = 2; p <= maxPage; p++) {
  await sleep(LIST_SLEEP_MS);
  const html = await fetchTextRetry(`${baseList}?&page=${p}`, listReferer, 2);
  const entries = extractThemeEntries(html);

  let added = 0;
  for (const entry of entries) {
    if (!seenNos.has(entry.no)) {
      seenNos.add(entry.no);
      allEntries.push(entry);
      added++;
    }
  }

  if (added === 0 && p >= 3) {
    stoppedEarlyAtPage = p;
    break;
  }
}

// 2) 정치 테마만 필터링
const politicalEntries = allEntries.filter((e) => isPoliticalTheme(e.name));
const themeNos = politicalEntries.map((e) => e.no);

// 2) 정치 테마 상세에서 종목코드 수집
const codeSet = new Set();
const detailErrors = [];

const detailReferer = 'https://finance.naver.com/sise/theme.naver';
const { errors } = await mapLimit(themeNos, CONCURRENCY, async (no) => {
  await sleep(DETAIL_SLEEP_MS);
  const url = `https://finance.naver.com/sise/sise_group_detail.naver?type=theme&no=${no}`;
  const html = await fetchTextRetry(url, detailReferer, 2);
  const codes = extractCodes(html);
  for (const c of codes) codeSet.add(c);
  return { no, codesCount: codes.length };
});

if (errors.length) detailErrors.push(...errors);

// 3) 저장 + 리턴
const themeCodes = [...codeSet].sort();

store.blacklist.themeCodes = themeCodes;
store.blacklist.themeUpdatedAt = new Date().toISOString();
store.blacklist.themeNosCount = themeNos.length;
store.blacklist.themeSource = 'naver:sise_group_detail:political_only';
store.blacklist.themeFetchStats = {
  totalThemesFound: allEntries.length,
  politicalThemesMatched: politicalEntries.length,
  politicalThemeNames: politicalEntries.map((e) => e.name),
  stoppedEarlyAtPage,
  maxPageTried: maxPage,
  concurrency: CONCURRENCY,
  detailErrors: detailErrors.length,
  ms: Date.now() - startTs,
};

return [
  {
    json: {
      ok: true,
      done: true,
      totalThemesFound: allEntries.length,
      politicalThemesMatched: politicalEntries.length,
      politicalThemeNames: politicalEntries.map((e) => e.name),
      themeCodesCount: themeCodes.length,
      themeUpdatedAt: store.blacklist.themeUpdatedAt,
      stats: store.blacklist.themeFetchStats,
      sampleCodes: themeCodes.slice(0, 20),
      detailErrors: detailErrors.slice(0, 10),
    },
  },
];

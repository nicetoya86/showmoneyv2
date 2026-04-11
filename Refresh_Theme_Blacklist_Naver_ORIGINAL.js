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

function extractThemeNos(html) {
  // /sise/sise_group_detail.naver?type=theme&no=584
  return uniq([...html.matchAll(/sise_group_detail\.naver\?type=theme&no=(\d+)/g)].map((m) => m[1]));
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

// 1) 테마 no 목록 수집
const html1 = await fetchTextRetry(`${baseList}?&page=1`, listReferer, 2);
let themeNos = extractThemeNos(html1);

if (themeNos.length === 0) {
  return [
    {
      json: {
        ok: false,
        reason: 'No theme no found on list page (expected type=theme&no=###)',
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

const allNos = new Set(themeNos);
let stoppedEarlyAtPage = null;

for (let p = 2; p <= maxPage; p++) {
  await sleep(LIST_SLEEP_MS);
  const html = await fetchTextRetry(`${baseList}?&page=${p}`, listReferer, 2);
  const nos = extractThemeNos(html);

  let added = 0;
  for (const no of nos) {
    if (!allNos.has(no)) {
      allNos.add(no);
      added++;
    }
  }

  if (added === 0 && p >= 3) {
    stoppedEarlyAtPage = p;
    break;
  }
}

themeNos = [...allNos].sort((a, b) => Number(a) - Number(b));

// 2) 테마 상세에서 종목코드 수집(동시처리)
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
store.blacklist.themeSource = 'naver:sise_group_detail';
store.blacklist.themeFetchStats = {
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
      themeNosCount: themeNos.length,
      themeCodesCount: themeCodes.length,
      themeUpdatedAt: store.blacklist.themeUpdatedAt,
      stats: store.blacklist.themeFetchStats,
      sampleCodes: themeCodes.slice(0, 20),
      detailErrors: detailErrors.slice(0, 10),
    },
  },
];
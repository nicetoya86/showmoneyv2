// ========================================
// [수정됨] Refresh Risk Blacklist - 네이버 금융 버전
// 수정일: 2026-01-21
// 변경사항: KRX API 대신 네이버 금융 사용
// ========================================

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

const BOT = '8366696724:AAHROcjGoQEn9BziD-sYdAu3ZuaolwtkgLE';
const CHAT = '523002062';
const NL = String.fromCharCode(10);

// --- KST date ---
const now = new Date();
const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
const today = `${kst.getUTCFullYear()}-${String(kst.getUTCMonth()+1).padStart(2,'0')}-${String(kst.getUTCDate()).padStart(2,'0')}`;

// --- circuit breaker shared with scanners ---
if (!store.krxState) store.krxState = {};
if (!store.krxState.alerts) store.krxState.alerts = {};
const ks = store.krxState;
const nowMs = now.getTime();

// 서킷 브레이커 자동 리셋 (3일 경과 시)
const CIRCUIT_RESET_DAYS = 3;
const lastFailMs = ks.lastFailAt ? new Date(ks.lastFailAt).getTime() : 0;
const daysSinceLastFail = lastFailMs > 0 ? (nowMs - lastFailMs) / (24 * 60 * 60 * 1000) : 999;

if (daysSinceLastFail >= CIRCUIT_RESET_DAYS && ks.circuitUntil) {
  delete ks.circuitUntil;
  delete ks.circuitDate;
  delete ks.lastFailAt;
  delete ks.lastFailReason;
  ks.autoResetAt = new Date(nowMs).toISOString();
  ks.autoResetReason = CIRCUIT_RESET_DAYS + '일 이상 경과로 자동 리셋';
}

const circuitUntilMs = ks.circuitUntil ? new Date(ks.circuitUntil).getTime() : 0;
const circuitActive = !!(circuitUntilMs && circuitUntilMs > nowMs && ks.circuitDate === today);

const openCircuit = (reason) => {
  const until = new Date(nowMs + 30 * 60 * 1000).toISOString();
  ks.circuitDate = today;
  ks.circuitUntil = until;
  ks.lastFailAt = new Date(nowMs).toISOString();
  ks.lastFailReason = String(reason || 'unknown');
};

const notifyOncePerDay = async (key, text) => {
  const k = String(key || 'default');
  if (ks.alerts[k] === today) return false;
  try {
    await http({
      method: 'POST',
      url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
      json: true,
      body: { chat_id: CHAT, text },
    });
    ks.alerts[k] = today;
    return true;
  } catch (e) {
    return false;
  }
};

// --- keep previous cache ---
const prev = {
  riskCodes: Array.isArray(store.blacklist.riskCodes) ? store.blacklist.riskCodes.slice() : null,
  riskUpdatedAt: store.blacklist.riskUpdatedAt || null,
  riskSourceCounts: store.blacklist.riskSourceCounts || null,
};

// 서킷 활성 시 스킵
if (circuitActive) {
  await notifyOncePerDay(
    'risk_blacklist_skip_circuit',
    '[리스크 블랙리스트] 서킷 활성으로 갱신 스킵' + NL + 
    '- date: ' + today + NL + 
    '- circuitUntil: ' + ks.circuitUntil
  );
  return [{ json: { ok: false, skipped: true, reason: 'circuit_active', riskUpdatedAt: prev.riskUpdatedAt } }];
}

// ===== 네이버 금융에서 관리종목 가져오기 =====
const NAVER_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
  'Referer': 'https://finance.naver.com/',
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function toText(raw) {
  if (Buffer.isBuffer(raw)) return raw.toString('utf8');
  return String(raw ?? '');
}

async function fetchNaverAdminStocks() {
  // 네이버 금융 관리종목 페이지에서 종목 코드 추출
  const codes = new Set();
  
  const urls = [
    'https://finance.naver.com/sise/management.naver',           // 전체
    'https://finance.naver.com/sise/management.naver?sosok=0',   // KOSPI
    'https://finance.naver.com/sise/management.naver?sosok=1',   // KOSDAQ
  ];
  
  for (const url of urls) {
    try {
      const raw = await http({
        method: 'GET',
        url,
        headers: NAVER_HEADERS,
        json: false,
      });
      
      const text = toText(raw);
      
      // code=XXXXXX 패턴으로 종목 코드 추출
      const matches = text.matchAll(/code=(\d{6})/g);
      for (const m of matches) {
        codes.add(m[1]);
      }
      
      await sleep(200);
    } catch (e) {
      // 개별 URL 실패는 무시하고 계속
    }
  }
  
  return [...codes];
}

// KIND 실질심사법인 (기존 로직 유지 - 이건 작동할 수 있음)
async function fetchKindRealInvestigationCodes() {
  try {
    const url = 'https://kind.krx.co.kr/corpgeneral/delistRealInvstg.do';
    const form = {
      method: 'searchDelistRealInvstg',
      forward: 'delistRealInvstg_down',
      pageIndex: '1',
      currentPageSize: '3000',
      mktTpCd: '',
      progrsDelistYn: '',
      fromDate: '',
      toDate: '',
    };

    const body = Object.entries(form)
      .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v))
      .join('&');

    const raw = await http({
      method: 'POST',
      url,
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://kind.krx.co.kr',
        'Referer': 'https://kind.krx.co.kr/corpgeneral/delistRealInvstg.do?method=searchDelistRealInvstgMain',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
      },
      body,
      json: false,
    });

    const text = Buffer.isBuffer(raw) ? raw.toString('latin1') : String(raw);
    const set = new Set();
    for (const m of text.matchAll(/mso-number-format:'@'[^>]*>\s*(\d{6})\s*<\/td>/g)) {
      set.add(m[1]);
    }
    return [...set];
  } catch (e) {
    return [];
  }
}

try {
  const codes = new Set();
  const sourceCounts = {};

  // 1. 네이버 금융 관리종목
  const naverAdminCodes = await fetchNaverAdminStocks();
  sourceCounts['Naver:adminStocks'] = naverAdminCodes.length;
  for (const c of naverAdminCodes) codes.add(c);

  // 2. KIND 실질심사법인 (best-effort)
  const kindCodes = await fetchKindRealInvestigationCodes();
  sourceCounts['KIND:realInvestigation'] = kindCodes.length;
  for (const c of kindCodes) codes.add(c);

  // 최소 1개 이상의 코드가 있어야 성공
  if (codes.size === 0 && prev.riskCodes && prev.riskCodes.length > 0) {
    await notifyOncePerDay(
      'risk_blacklist_empty_keep_cache',
      '[리스크 블랙리스트] 신규 데이터 0건 - 기존 캐시 유지' + NL +
      '- 기존 캐시: ' + prev.riskCodes.length + '개' + NL +
      '- 마지막 갱신: ' + prev.riskUpdatedAt
    );
    return [{ json: { ok: true, keptCache: true, riskCodesCount: prev.riskCodes.length, riskUpdatedAt: prev.riskUpdatedAt } }];
  }

  store.blacklist.riskCodes = [...codes].sort();
  store.blacklist.riskUpdatedAt = new Date().toISOString();
  store.blacklist.riskSourceCounts = sourceCounts;
  store.blacklist.riskSource = 'Naver+KIND';

  // 성공 시 에러 상태 클리어
  delete store.blacklist.riskLastError;

  // 성공 알림
  await notifyOncePerDay(
    'risk_blacklist_success',
    '[리스크 블랙리스트 갱신 성공]' + NL +
    '- 총 ' + store.blacklist.riskCodes.length + '개 종목' + NL +
    '- 네이버: ' + naverAdminCodes.length + '개' + NL +
    '- KIND: ' + kindCodes.length + '개' + NL +
    '- 갱신 시간: ' + store.blacklist.riskUpdatedAt
  );

  return [
    {
      json: {
        ok: true,
        riskCodesCount: store.blacklist.riskCodes.length,
        riskSourceCounts: sourceCounts,
        riskUpdatedAt: store.blacklist.riskUpdatedAt,
        source: 'Naver+KIND',
      },
    },
  ];
} catch (e) {
  const msg = e?.message ? String(e.message) : String(e);
  openCircuit(msg);
  store.blacklist.riskLastError = { at: new Date().toISOString(), message: msg };
  
  // 기존 값 유지
  if (prev.riskCodes) store.blacklist.riskCodes = prev.riskCodes;
  if (prev.riskUpdatedAt) store.blacklist.riskUpdatedAt = prev.riskUpdatedAt;
  if (prev.riskSourceCounts) store.blacklist.riskSourceCounts = prev.riskSourceCounts;

  await notifyOncePerDay('risk_blacklist_fail', '[리스크 블랙리스트 갱신 실패]' + NL + msg);
  return [{ json: { ok: false, error: msg, riskUpdatedAt: store.blacklist.riskUpdatedAt || null } }];
}

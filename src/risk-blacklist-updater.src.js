// ========================================
// Refresh Risk Blacklist - Naver+KRX+KIND+Toss 통합 버전
// 참고: docs/02-design/features/risk-blacklist-toss-api.design.md
// ========================================
const { sleep } = require('../lib/format');
const { createTelegram } = require('../lib/telegramClient');
const { createTossClient } = require('../lib/tossClient');

const run = async function () {
  const store = this.getWorkflowStaticData('global');
  if (!store.blacklist) store.blacklist = {};

  const http = async (o) => await this.helpers.httpRequest(Object.assign({ timeout: 30000 }, o));

  const BOT = '8366696724:AAHROcjGoQEn9BziD-sYdAu3ZuaolwtkgLE';
  const CHAT = '523002062';
  const NL = String.fromCharCode(10);
  const telegram = createTelegram(http, BOT, CHAT);

  async function notify(text) {
    try {
      await telegram.send(text);
    } catch (e) {}
  }

  const prev = {
    riskCodes: Array.isArray(store.blacklist.riskCodes) ? store.blacklist.riskCodes.slice() : null,
    riskUpdatedAt: store.blacklist.riskUpdatedAt || null,
  };

  // ===== Naver Finance 관리종목 (1차 소스 - 안정적, 변경 없음) =====
  async function fetchNaverAdminStocks() {
    const codes = new Set();
    const urls = [
      'https://finance.naver.com/sise/management.naver',
      'https://finance.naver.com/sise/management.naver?sosok=0',
      'https://finance.naver.com/sise/management.naver?sosok=1',
    ];
    for (const url of urls) {
      try {
        const raw = await http({
          method: 'GET',
          url,
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
            'Referer': 'https://finance.naver.com/',
          },
          json: false,
        });
        const text = Buffer.isBuffer(raw) ? raw.toString('utf8') : String(raw || '');
        for (const m of text.matchAll(/code=(\d{6})/g)) codes.add(m[1]);
        await sleep(200);
      } catch (e) {}
    }
    return [...codes];
  }

  // ===== KRX 거래소 데이터 (2차 소스 - best-effort, 변경 없음) =====
  // FIX: json: false 로 변경 — json: true 는 form-encoded body를 JSON 직렬화해 400 유발
  const KRX_URL = 'https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd';
  const KRX_HEADERS = {
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Origin': 'https://data.krx.co.kr',
    'Referer': 'https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC02021201',
    'X-Requested-With': 'XMLHttpRequest',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
  };

  // [TOSS-RISK] 정리매매/투자경고/투자위험/단기과열 4종은 토스 /warnings 로 대체 — 아래 목록에서 제외 (2026-07-10, 단기과열 추가 2026-07-14)
  // 유지되는 4종: 거래정지 / 관리종목 / 투자주의환기(코) / 투자주의
  const KRX_BLDS = [
    'dbms/MDC/STAT/issue/MDCSTAT21201', // 거래정지
    'dbms/MDC/STAT/issue/MDCSTAT21401', // 관리종목
    'dbms/MDC/STAT/issue/MDCSTAT21701', // 투자주의환기(코)
    'dbms/MDC/STAT/issue/MDCSTAT22801', // 투자주의
  ];

  async function fetchKrxCodes(bld) {
    const body = 'bld=' + encodeURIComponent(bld) + '&locale=ko_KR&mktId=ALL&csvxls_isNo=true';
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        const raw = await http({
          method: 'POST',
          url: KRX_URL,
          headers: KRX_HEADERS,
          body,
          json: false,  // FIX: form-encoded body를 그대로 전송 (json:true는 body를 JSON 직렬화해 400 유발)
        });
        const res = typeof raw === 'string' ? JSON.parse(raw) : (Buffer.isBuffer(raw) ? JSON.parse(raw.toString('utf8')) : raw); // FIX W-5
        const rows = (res && (res.output || res.OutBlock_1 || [])) || [];
        return rows.map(r => String(r && r.ISU_CD || '').trim()).filter(c => /^\d{6}$/.test(c));
      } catch (e) {
        if (attempt < 2) await sleep(3000);
      }
    }
    return null; // null = 실패 ([] = 성공이나 0건과 구분)
  }

  async function fetchKrxAllCodes() {
    const codes = new Set();
    const sourceCounts = {};
    let anySuccess = false;
    for (const bld of KRX_BLDS) {
      const list = await fetchKrxCodes(bld);
      const key = bld.split('/').pop();
      if (list !== null) {
        sourceCounts[key] = list.length;
        for (const c of list) codes.add(c);
        anySuccess = true;
      } else {
        sourceCounts[key] = -1;
      }
    }
    return { codes, sourceCounts, anySuccess };
  }

  // ===== KIND 실질심사법인 (best-effort, 변경 없음) =====
  async function fetchKindCodes() {
    try {
      const formData = [
        'method=searchDelistRealInvstg', 'forward=delistRealInvstg_down',
        'pageIndex=1', 'currentPageSize=3000',
        'mktTpCd=', 'progrsDelistYn=', 'fromDate=', 'toDate=',
      ].join('&');
      const raw = await http({
        method: 'POST',
        url: 'https://kind.krx.co.kr/corpgeneral/delistRealInvstg.do',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'Origin': 'https://kind.krx.co.kr',
          'Referer': 'https://kind.krx.co.kr/corpgeneral/delistRealInvstg.do?method=searchDelistRealInvstgMain',
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        },
        body: formData,
        json: false,
      });
      const text = Buffer.isBuffer(raw) ? raw.toString('latin1') : String(raw || '');
      const set = new Set();
      for (const m of text.matchAll(/mso-number-format:'@'[^>]*>\s*(\d{6})\s*<\/td>/g)) set.add(m[1]);
      return [...set];
    } catch (e) {
      return [];
    }
  }

  // ===== [TOSS-RISK] 토스 Open API — 정리매매/투자경고/투자위험 (2026-07-10 신규) =====
  // 매핑: docs/02-design/features/risk-blacklist-toss-api.design.md §4.2
  // OVERHEATED(단기과열): 다음날 30분 단일가매매 적용 종목 — 스윙 신규진입 리스크 커서 포함 (2026-07-14)
  const RISK_WARNING_TYPES = new Set(['LIQUIDATION_TRADING', 'INVESTMENT_WARNING', 'INVESTMENT_RISK', 'OVERHEATED']);
  const TOSS_WARNINGS_CONCURRENCY = 6;
  const toss = createTossClient(http, store.tossApiKey || '', { timeout: 8000 });

  // 동시성 제한 실행 헬퍼 (Refresh_Theme_Blacklist_Naver_code.js 의 mapLimit 패턴 재사용)
  async function mapLimit(list, limit, worker) {
    const errors = [];
    let idx = 0;
    const runners = new Array(Math.min(limit, list.length)).fill(0).map(async () => {
      while (idx < list.length) {
        const i = idx++;
        try {
          await worker(list[i], i);
        } catch (e) {
          errors.push({ i, item: list[i], message: e?.message || String(e) });
        }
      }
    });
    await Promise.all(runners);
    return { errors };
  }

  // symbols: 6자리 종목코드 배열 (store.lastFilteredUniverse.symbols — Swing Scanner가 전일 09:10 스캔 종료 시 저장)
  // 대상이 없거나 API 키가 없으면 빈 결과 반환(Fail-Safe — 호출부에서 기존 소스만으로 계속 진행)
  async function fetchTossWarnings(symbols) {
    const codes = new Set();
    const result = { codes: [], errorCount: 0, checked: 0, skippedNoKey: !(store.tossApiKey) };

    if (result.skippedNoKey) return result;
    if (!Array.isArray(symbols) || symbols.length === 0) return result;

    const { errors } = await mapLimit(symbols, TOSS_WARNINGS_CONCURRENCY, async (symbol) => {
      result.checked++;
      const resp = await toss.fetchWarnings(symbol);
      if (Array.isArray(resp) && resp.some(w => RISK_WARNING_TYPES.has(w && w.warningType))) {
        codes.add(symbol);
      }
    });

    result.codes = [...codes];
    result.errorCount = errors.length;
    return result;
  }
  // ===== /TOSS-RISK =====

  // ===== 메인 실행 =====
  try {
    const allCodes = new Set();
    const sourceCounts = {};

    // 1. Naver 관리종목 (1차 소스, 변경 없음)
    const naverCodes = await fetchNaverAdminStocks();
    sourceCounts['Naver'] = naverCodes.length;
    for (const c of naverCodes) allCodes.add(c);

    // 2. KRX 4종 (거래정지/관리종목/투자주의환기/투자주의만 — 정리매매/투자경고/투자위험은 토스로 이동)
    const krxResult = await fetchKrxAllCodes();
    Object.assign(sourceCounts, krxResult.sourceCounts);
    for (const c of krxResult.codes) allCodes.add(c);

    // 3. KIND (best-effort, 변경 없음)
    const kindCodes = await fetchKindCodes();
    sourceCounts['KIND'] = kindCodes.length;
    for (const c of kindCodes) allCodes.add(c);

    // 4. [TOSS-RISK] 정리매매/투자경고/투자위험 — 전일 스윙 스캔 1차 필터 통과 종목에만 적용
    const lastUniverse = store.lastFilteredUniverse;
    const tossSymbols = (lastUniverse && Array.isArray(lastUniverse.symbols)) ? lastUniverse.symbols : [];
    const tossResult = await fetchTossWarnings(tossSymbols);
    sourceCounts['TossWarnings'] = tossResult.codes.length;
    for (const c of tossResult.codes) allCodes.add(c);

    // 수집 결과 0건이고 캐시가 있으면 캐시 유지
    if (allCodes.size === 0 && prev.riskCodes && prev.riskCodes.length > 0) {
      await notify('⚠️ [리스크 블랙리스트] 신규 0건 — 기존 캐시 유지' + NL +
        '기존: ' + prev.riskCodes.length + '개 / 마지막 갱신: ' + (prev.riskUpdatedAt || '없음'));
      return [{ json: { ok: true, keptCache: true, riskCodesCount: prev.riskCodes.length, riskUpdatedAt: prev.riskUpdatedAt } }];
    }

    store.blacklist.riskCodes = [...allCodes].sort();
    store.blacklist.riskUpdatedAt = new Date().toISOString();
    store.blacklist.riskSourceCounts = sourceCounts;
    store.blacklist.riskSource = 'Naver+KRX+KIND+TossWarnings';
    delete store.blacklist.riskLastError;

    const krxStatus = krxResult.anySuccess ? '✅' : '❌(캐시없이 진행)';
    const tossStatus = tossResult.skippedNoKey ? '⏭️(키 없음, 스킵)'
      : (tossSymbols.length === 0) ? '⏭️(전일 필터 종목 없음, 스킵)'
      : (tossResult.errorCount > 0) ? '⚠️(' + tossResult.errorCount + '건 오류)'
      : '✅';

    await notify('✅ [리스크 블랙리스트 갱신 성공]' + NL +
      '총 ' + store.blacklist.riskCodes.length + '개 종목' + NL +
      '네이버: ' + naverCodes.length + '개 | KIND: ' + kindCodes.length + '개' + NL +
      'KRX(거래정지/관리종목/투자주의/투자주의환기): ' + krxStatus + NL +
      'Toss(정리매매·경고·위험·단기과열): ' + tossStatus + ' ' + tossResult.codes.length + '개 (검사 ' + tossResult.checked + '개)' + NL +
      '갱신: ' + store.blacklist.riskUpdatedAt);

    return [{
      json: {
        ok: true,
        riskCodesCount: store.blacklist.riskCodes.length,
        riskSourceCounts: sourceCounts,
        riskUpdatedAt: store.blacklist.riskUpdatedAt,
        krxSuccess: krxResult.anySuccess,
        tossChecked: tossResult.checked,
        tossSkippedNoKey: tossResult.skippedNoKey,
      },
    }];

  } catch (e) {
    const msg = String(e && e.message ? e.message : e);
    // FIX: axios는 e.response.status (statusCode 아님)
    const status = (e && (e.statusCode || (e.response && (e.response.status || e.response.statusCode)))) || null;
    const detail = status ? 'HTTP ' + status + ': ' + msg : msg;

    store.blacklist.riskLastError = { at: new Date().toISOString(), message: detail, status };
    if (prev.riskCodes) store.blacklist.riskCodes = prev.riskCodes;
    if (prev.riskUpdatedAt) store.blacklist.riskUpdatedAt = prev.riskUpdatedAt;

    await notify('🚨 [리스크 블랙리스트 갱신 실패]' + NL + detail + NL + '(캐시: ' + (store.blacklist.riskUpdatedAt || '없음') + ')');
    return [{ json: { ok: false, error: detail, status, riskUpdatedAt: store.blacklist.riskUpdatedAt || null } }];
  }
};

return run();

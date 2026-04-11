const run = async function () {
  const BOT = '8366696724:AAHROcjGoQEn9BziD-sYdAu3ZuaolwtkgLE';
  const CHAT = '523002062';
  const http = async (o) => await this.helpers.httpRequest(Object.assign({ timeout: 30000 }, o));
  const NL = String.fromCharCode(10);
  const pct = (r) => (r >= 0 ? '+' : '') + (r * 100).toFixed(1) + '%';

  const HOLIDAYS = ['2025-01-01','2025-01-28','2025-01-29','2025-01-30','2025-03-01','2025-03-03','2025-05-05','2025-05-06','2025-06-06','2025-08-15','2025-10-03','2025-10-06','2025-10-07','2025-10-08','2025-10-09','2025-12-25','2026-01-01','2026-02-16','2026-02-17','2026-02-18','2026-03-01','2026-03-02','2026-05-05','2026-05-24','2026-05-25','2026-06-03','2026-06-06','2026-07-17','2026-08-15','2026-08-17','2026-09-24','2026-09-25','2026-09-26','2026-10-03','2026-10-05','2026-10-09','2026-12-25'];

  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const today = `${kst.getUTCFullYear()}-${String(kst.getUTCMonth() + 1).padStart(2, '0')}-${String(kst.getUTCDate()).padStart(2, '0')}`;

  if (HOLIDAYS.includes(today)) return [{ json: { skipped: true, reason: 'Holiday', today } }];

  // 마지막 완료된 거래일 (토요일/장중 실행 시 Naver API가 비거래일 endDate에 빈 배열 반환 방지)
  const getPrevTradingDay = () => {
    let d = new Date(Date.now() + 9 * 3600000 - 24 * 3600000);
    for (let i = 0; i < 10; i++) {
      const dow = d.getUTCDay();
      const ds = d.toISOString().slice(0, 10);
      if (dow >= 1 && dow <= 5 && !HOLIDAYS.includes(ds)) return ds;
      d = new Date(d.getTime() - 24 * 3600000);
    }
    return new Date(Date.now() + 9 * 3600000 - 24 * 3600000).toISOString().slice(0, 10);
  };
  const prevTradingDay = getPrevTradingDay(); // 토요일 실행 시 금요일, 장중 실행 시 전일

  // N 거래일 후 날짜 계산 (주말/공휴일 제외)
  const addTradingDays = (startDateStr, n) => {
    const d = new Date(startDateStr + 'T00:00:00Z');
    let count = 0;
    while (count < n) {
      d.setUTCDate(d.getUTCDate() + 1);
      const dow = d.getUTCDay();
      const ds = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
      if (dow >= 1 && dow <= 5 && !HOLIDAYS.includes(ds)) count++;
    }
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
  };

  // 지난 주 거래일 목록 (토요일 트리거 기준: 직전 월~금)
  const getWeekDates = (ref) => {
    const dates = [];
    const d = new Date(ref + 'T00:00:00Z');
    const dow = d.getUTCDay(); // 6=토
    const daysToFri = (dow === 6) ? 1 : (dow + 2); // Sat→1, Sun→2, Mon→3 ... Fri→7 (last week)
    const friday = new Date(d.getTime() - daysToFri * 24 * 60 * 60 * 1000);
    const monday = new Date(friday.getTime() - 4 * 24 * 60 * 60 * 1000);
    for (let i = 0; i < 5; i++) {
      const cur = new Date(monday.getTime() + i * 24 * 60 * 60 * 1000);
      const wd = cur.getUTCDay();
      const ds = `${cur.getUTCFullYear()}-${String(cur.getUTCMonth() + 1).padStart(2, '0')}-${String(cur.getUTCDate()).padStart(2, '0')}`;
      if (wd >= 1 && wd <= 5 && !HOLIDAYS.includes(ds)) dates.push(ds);
    }
    return dates;
  };

  const input = (items && items[0] && items[0].json) || {};
  const forceTest = !!input.forceTest;
  if (forceTest) {
    const msg = '[주간 스윙 리포트 테스트] 시스템 정상 작동 - ' + kst.toISOString().slice(0, 16).replace('T', ' ') + ' KST';
    try { await http({ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage', json: true, body: { chat_id: CHAT, text: msg } }); } catch (e) {}
    return [{ json: { testSent: true } }];
  }

  const store = this.getWorkflowStaticData('global');
  if (!store.weeklyRecommendations) store.weeklyRecommendations = {};
  const weekDates = getWeekDates(today);
  if (weekDates.length === 0) return [{ json: { skipped: true, reason: 'No trading days this week' } }];

  // 이번 주 스윙 추천 수집 (scalping 제외 - swing 전용)
  const recs = [];
  for (const ds of weekDates) {
    const arr = store.weeklyRecommendations[ds] || [];
    for (const r of arr) {
      if (r.type === 'swing') recs.push({ ...r, date: ds });
    }
  }

  if (recs.length === 0) {
    const msg = '[주간 스윙 리포트]' + NL +
      '📅 ' + weekDates[0] + ' ~ ' + weekDates[weekDates.length - 1] + NL + NL +
      '이번 주 스윙 추천 없음';
    try { await http({ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage', json: true, body: { chat_id: CHAT, text: msg } }); } catch (e) {}
    return [{ json: { sent: true, count: 0 } }];
  }

  // Naver 일봉 API (Yahoo Finance 대체)
  const fetchNaverDaily = async (code, startDate, endDate) => {
    const url = `https://api.stock.naver.com/chart/domestic/item/${code}/day?startDateTime=${startDate}&endDateTime=${endDate}`;
    try {
      const resp = await http({
        method: 'GET', url, json: true,
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
          'Referer': 'https://finance.naver.com/',
          'Accept': 'application/json', 'Accept-Charset': 'utf-8', 'Accept-Language': 'ko-KR,ko;q=0.9'
        }
      });
      return Array.isArray(resp) && resp.length > 0 ? resp : null;
    } catch (e) {
      return null;
    }
  };

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ===== 성과 평가: 매수가 진입 여부 + 목표가/손절가 도달 여부 =====
  const details = [];
  let wins = 0;
  let partialWins = 0;
  let losses = 0;
  let notEntered = 0;

  for (const r of recs) {
    try {
      const holdDays = r.holdingDays || 3;
      const exitDate = addTradingDays(r.date, holdDays);
      // exitDate가 미래인 경우 prevTradingDay 사용 (비거래일 endDate → Naver API 빈배열 방지)
      const endCheck = exitDate <= today ? exitDate : prevTradingDay;

      const startStr = r.date.replace(/-/g, '');
      const endStr = endCheck.replace(/-/g, '');

      const data = await fetchNaverDaily(r.code, startStr, endStr);

      if (!data) {
        details.push({ ...r, result: 'no_data', maxReturn: 0, finalReturn: 0, exitDate });
        await sleep(400);
        continue;
      }

      // 추천일 ~ exitDate 범위 필터
      const recDateStr = r.date.replace(/-/g, '');
      const exitDateStr = exitDate.replace(/-/g, '');
      const relevant = data.filter((d) => d.localDate >= recDateStr && d.localDate <= exitDateStr);

      // W-002 수정: relevant 비어있으면 데이터 없음으로 처리 (not_entered 오판정 방지)
      if (relevant.length === 0) {
        details.push({ ...r, result: 'no_data', maxReturn: 0, finalReturn: 0, exitDate });
        await sleep(400);
        continue;
      }

      // ===== 매수가 진입 여부 확인 =====
      // 추천 매수가(r.entry)에 저가(low)가 도달했을 때 진입으로 판정
      let entryHit = !r.entry || r.entry <= 0; // 매수가 미설정 시 진입 간주
      for (const day of relevant) {
        if (Number(day.lowPrice) <= r.entry) {
          entryHit = true;
          break;
        }
      }

      // 매수가 미진입 → 리포트 제외
      if (!entryHit) {
        notEntered++;
        details.push({ ...r, result: 'not_entered', maxReturn: 0, finalReturn: 0, exitDate });
        await sleep(400);
        continue;
      }

      let result = exitDate > today ? 'holding' : 'expired';
      let maxHigh = r.entry || 0;
      let finalClose = r.entry || 0;
      let hitTargetDay = null;
      let hitTarget1Day = null;
      let hitStopDay = null;

      for (const day of relevant) {
        const high = Number(day.highPrice);
        const low = Number(day.lowPrice);
        finalClose = Number(day.closePrice);
        if (high > maxHigh) maxHigh = high;
        if (!hitTargetDay && r.target && high >= r.target) {
          hitTargetDay = day.localDate.slice(0, 4) + '-' + day.localDate.slice(4, 6) + '-' + day.localDate.slice(6, 8);
        }
        if (!hitTarget1Day && r.target1 && high >= r.target1) {
          hitTarget1Day = day.localDate.slice(0, 4) + '-' + day.localDate.slice(4, 6) + '-' + day.localDate.slice(6, 8);
        }
        if (!hitStopDay && r.stop && low <= r.stop) {
          hitStopDay = day.localDate.slice(0, 4) + '-' + day.localDate.slice(4, 6) + '-' + day.localDate.slice(6, 8);
        }
      }

      // 목표/손절 중 먼저 도달한 것 기준 판정
      // partial_win: 1차 목표 달성 후 손절 (이익 실현 일부)
      if (hitTargetDay && hitStopDay) {
        result = hitTargetDay <= hitStopDay ? 'win' : 'loss';
      } else if (hitTargetDay) {
        result = 'win';
      } else if (hitStopDay) {
        result = hitTarget1Day && hitTarget1Day <= hitStopDay ? 'partial_win' : 'loss';
      }

      const maxReturn = r.entry > 0 ? (maxHigh - r.entry) / r.entry : 0;
      const finalReturn = r.entry > 0 ? (finalClose - r.entry) / r.entry : 0;
      const targetPct = (r.entry > 0 && r.target > 0) ? (r.target / r.entry - 1) : 0;
      const stopPct = (r.entry > 0 && r.stop > 0) ? (r.stop / r.entry - 1) : 0;

      if (result === 'win') wins++;
      else if (result === 'partial_win') partialWins++;
      else if (result === 'loss') losses++;

      details.push({ ...r, result, maxReturn, finalReturn, exitDate, hitTargetDay, hitTarget1Day, hitStopDay, targetPct, stopPct });
    } catch (e) {
      details.push({ ...r, result: 'error', maxReturn: 0, finalReturn: 0, exitDate: '' });
    }
    await sleep(400);
  }

  // 매수 진입 종목만 평가 대상
  const entered = details.filter((d) => d.result !== 'not_entered' && d.result !== 'no_data' && d.result !== 'error');
  // W-001 수정: 승률 = win/(win+partial_win+loss) — expired는 분모에서 제외
  const evaluated = entered.filter((d) => d.result === 'win' || d.result === 'partial_win' || d.result === 'loss');
  const winRate = evaluated.length > 0 ? (wins + partialWins) / evaluated.length : 0;
  const enteredCount = entered.length;

  // 섹션별 분류
  const winList = details.filter((d) => d.result === 'win');
  const partialWinList = details.filter((d) => d.result === 'partial_win');
  const holdList = details.filter((d) => d.result === 'holding' || d.result === 'expired');
  const lossList = details.filter((d) => d.result === 'loss');

  // 각 섹션 내 수익률 기준 정렬
  winList.sort((a, b) => (b.maxReturn || 0) - (a.maxReturn || 0));
  holdList.sort((a, b) => (b.maxReturn || 0) - (a.maxReturn || 0));
  lossList.sort((a, b) => (a.maxReturn || 0) - (b.maxReturn || 0));

  // ===== 깨진 종목명 보완: Naver API로 재조회 =====
  const isGarbled = (s) => !s || !/^[\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F\u3200-\u321F\uFF01-\uFF9F\u4E00-\u9FFF\u0020-\u007E]+$/.test(s);
  const allCodes = [...new Set(details.map((d) => d.code))];
  for (const code of allCodes) {
    const cached = store.naverNames && store.naverNames[code];
    if (cached && cached !== code && !isGarbled(cached)) continue;
    const stored = details.find((d) => d.code === code)?.name;
    if (stored && stored !== code && !isGarbled(stored)) continue;
    try {
      const nr = await http({
        method: 'GET',
        url: 'https://m.stock.naver.com/api/stock/' + code + '/basic',
        json: true,
        headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.naver.com/', 'Accept-Language': 'ko-KR,ko;q=0.9' },
      });
      const nm = nr && (nr.stockName || nr.itemName || nr.name || nr.symbolName);
      if (nm && nm !== code && !isGarbled(nm)) {
        if (!store.naverNames) store.naverNames = {};
        store.naverNames[code] = nm;
      }
    } catch (e) {}
    await sleep(300);
  }

  const resolveName = (d) => {
    const cached = store.naverNames && store.naverNames[d.code];
    if (cached && cached !== d.code && !isGarbled(cached)) return cached;
    if (d.name && d.name !== d.code && !isGarbled(d.name)) return d.name;
    return d.code;
  };

  // HELPER-01: 날짜 단축 (2026-03-25 → 03-25)
  const shortDate = (ds) => (ds && ds.length >= 7) ? ds.slice(5) : (ds || '');

  // ===== 메시지 구성 =====
  let msg = '[주간 스윙 성과 리포트]' + NL +
    '📅 ' + weekDates[0] + ' ~ ' + weekDates[weekDates.length - 1] + NL +
    '━━━━━━━━━━━━━━━━━━━━' + NL +
    '총추천 ' + recs.length + '건 │ 진입 ' + enteredCount + '건 │ 승률 ' + (evaluated.length > 0 ? (winRate * 100).toFixed(0) + '%' : 'N/A') + NL +
    '✅ 목표 ' + wins + '건 │ 🎯 1차달성 ' + partialWins + '건 │ ❌ 손절 ' + losses + '건 │ 🔄 보유 ' + holdList.length + '건' + NL +
    '━━━━━━━━━━━━━━━━━━━━' + NL;

  // ✅ 수익 종목
  if (winList.length > 0) {
    msg += NL + '✅ 수익 (' + winList.length + '건)' + NL;
    for (const d of winList) {
      const name = resolveName(d);
      let line = name + '(' + (d.code || '') + ') │ ' + shortDate(d.date);
      if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) line += ' │ 최고 ' + pct(d.maxReturn);
      if (d.hitTargetDay) line += ' │ ' + shortDate(d.hitTargetDay);
      if (d.score) line += ' │ ' + d.score + '점';
      msg += line + NL;
    }
  }

  // 🎯 1차 목표 달성 후 손절 (부분 수익)
  if (partialWinList.length > 0) {
    msg += NL + '🎯 1차달성 (' + partialWinList.length + '건)' + NL;
    for (const d of partialWinList) {
      const name = resolveName(d);
      let line = name + '(' + (d.code || '') + ') │ ' + shortDate(d.date);
      if (d.hitTarget1Day) line += ' │ 1차 ' + shortDate(d.hitTarget1Day);
      if (d.hitStopDay) line += ' │ 손절 ' + shortDate(d.hitStopDay);
      if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) line += ' │ 최고 ' + pct(d.maxReturn);
      if (d.score) line += ' │ ' + d.score + '점';
      msg += line + NL;
    }
  }

  // 🔄 보유 종목
  if (holdList.length > 0) {
    msg += NL + '🔄 보유 (' + holdList.length + '건)' + NL;
    for (const d of holdList) {
      const name = resolveName(d);
      let line = name + '(' + (d.code || '') + ') │ ' + shortDate(d.date);
      if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) line += ' │ 최고 ' + pct(d.maxReturn);
      if (d.result === 'holding' && d.exitDate) line += ' │ 예정일 ' + shortDate(d.exitDate);
      if (d.result === 'expired') line += ' │ 보유예정일 ' + shortDate(d.exitDate || d.date);
      if (d.score) line += ' │ ' + d.score + '점';
      msg += line + NL;
    }
  }

  // ❌ 손절 종목
  if (lossList.length > 0) {
    msg += NL + '❌ 손절 (' + lossList.length + '건)' + NL;
    for (const d of lossList) {
      const name = resolveName(d);
      let line = name + '(' + (d.code || '') + ') │ ' + shortDate(d.date);
      if (Number.isFinite(d.maxReturn) && d.maxReturn !== 0) line += ' │ 최고 ' + pct(d.maxReturn);
      if (d.hitStopDay) line += ' │ 손절 ' + shortDate(d.hitStopDay);
      if (d.score) line += ' │ ' + d.score + '점';
      msg += line + NL;
    }
  }

  // 매수 미진입 종목
  const notEnteredList = details.filter((d) => d.result === 'not_entered');
  if (notEnteredList.length > 0) {
    msg += NL + '⚪ 매수 미도달 (' + notEnteredList.length + '건)' + NL;
    for (const d of notEnteredList) {
      const name = resolveName(d);
      msg += name + '(' + (d.code || '') + ') │ ' + shortDate(d.date) + NL;
    }
  }

  msg += NL + '⚠️ 본 리포트는 참고용이며 투자 결과에 책임지지 않습니다.';

  // Telegram 4096자 초과 시 분리 전송
  const TELE_LIMIT = 4000;
  const chunks = [];
  if (msg.length <= TELE_LIMIT) {
    chunks.push(msg);
  } else {
    let remaining = msg;
    while (remaining.length > 0) {
      if (remaining.length <= TELE_LIMIT) { chunks.push(remaining); break; }
      let cut = remaining.lastIndexOf(NL, TELE_LIMIT);
      if (cut <= 0) cut = TELE_LIMIT;
      chunks.push(remaining.slice(0, cut));
      remaining = remaining.slice(cut).replace(/^\n/, '');
    }
  }

  for (let ci = 0; ci < chunks.length; ci++) {
    try {
      await http({ method: 'POST', url: 'https://api.telegram.org/bot' + BOT + '/sendMessage', json: true, body: { chat_id: CHAT, text: chunks[ci] } });
    } catch (e) {}
    if (ci < chunks.length - 1) await sleep(500);
  }

  return [{ json: { sent: true, count: recs.length, enteredCount, wins, losses, winRate } }];
};
return run();

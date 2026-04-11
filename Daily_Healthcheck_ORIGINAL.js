const run = async function () {
  const BOT = '8366696724:AAHROcjGoQEn9BziD-sYdAu3ZuaolwtkgLE';
  const CHAT = '523002062';
  const http = async (o) => await this.helpers.httpRequest(Object.assign({ timeout: 30000 }, o));

  const now = new Date();
  const kst = new Date(now.getTime() + 9*60*60*1000);
  const today = `${kst.getUTCFullYear()}-${String(kst.getUTCMonth()+1).padStart(2,'0')}-${String(kst.getUTCDate()).padStart(2,'0')}`;
  const timeKst = `${String(kst.getUTCHours()).padStart(2,'0')}:${String(kst.getUTCMinutes()).padStart(2,'0')}`;
  const HOLIDAYS_2026 = ['2026-01-01','2026-02-16','2026-02-17','2026-02-18','2026-03-01','2026-03-02','2026-05-05','2026-05-24','2026-05-25','2026-06-03','2026-06-06','2026-08-15','2026-08-17','2026-09-24','2026-09-25','2026-09-26','2026-10-03','2026-10-05','2026-10-09','2026-12-25'];
  if (HOLIDAYS_2026.includes(today)) {
    return [{ json: { skipped: true, reason: 'Holiday (KRX closed)', today, timeKst } }];
  }

  const store = this.getWorkflowStaticData('global');
  if (!store.healthcheck) store.healthcheck = {};
  if (store.healthcheck.lastSentDate === today) {
    return [{ json: { skipped: true, reason: 'Already sent today', today, timeKst } }];
  }

  // (선택) KRX 데이터 접근 가능 여부를 같이 점검  // (KRX live probe disabled) - KRX 차단/불안정 시 400을 유발할 수 있어 live 호출을 하지 않습니다.
  // 대신, 오늘자 KRX 유니버스 캐시/서킷 상태만 보고합니다.  // (KRX live probe disabled) - KRX 차단/불안정 시 400을 유발할 수 있어 live 호출을 하지 않습니다.
  // 대신, 오늘자 KRX 유니버스 캐시/서킷 상태만 보고합니다.
  let krxStatus = '미확인';
  let krxCount = 0;
  try {
    const store = this.getWorkflowStaticData('global');
    const trdDd = `${kst.getUTCFullYear()}${String(kst.getUTCMonth()+1).padStart(2,'0')}${String(kst.getUTCDate()).padStart(2,'0')}`;
    const cache = store && store.krxUniverseCache;
    const st = store && store.krxState;

    const nowMs = now.getTime();
    const circuitUntil = st && st.circuitUntil ? new Date(st.circuitUntil).getTime() : 0;
    const circuitActive = !!(circuitUntil && circuitUntil > nowMs && st && st.circuitDate === today);

    if (circuitActive) {
      krxStatus = `서킷 활성(circuitUntil=${st.circuitUntil})`;
    } else if (cache && cache.trdDd === trdDd && Array.isArray(cache.rows) && cache.rows.length) {
      krxCount = cache.rows.length;
      krxStatus = `캐시 OK (${krxCount}개)`;
    } else if (cache && Array.isArray(cache.rows) && cache.rows.length) {
      krxCount = cache.rows.length;
      krxStatus = `캐시(최근) ${krxCount}개 (trdDd=${cache.trdDd || 'unknown'})`;
    } else {
      krxStatus = '캐시 없음 (live probe 비활성)';
    }
  } catch (e) {
    krxStatus = '상태확인 실패: ' + String(e && e.message ? e.message : e);
  }

  const msg = `✅ [헬스체크] Autostock 스케줄러 정상\n- KST: ${today} ${timeKst}\n- KRX: ${krxStatus}`;

  try {
    await http({
      method: 'POST',
      url: 'https://api.telegram.org/bot' + BOT + '/sendMessage',
      json: true,
      body: { chat_id: CHAT, text: msg }
    });
  } catch (e) {
    return [{ json: { ok: false, error: String(e && e.message ? e.message : e), today, timeKst, krxStatus, krxCount } }];
  }

  store.healthcheck.lastSentDate = today;
  store.healthcheck.lastSentAt = now.toISOString();
  store.healthcheck.lastKrxStatus = krxStatus;
  store.healthcheck.lastKrxCount = krxCount;

  return [{ json: { ok: true, today, timeKst, krxStatus, krxCount } }];
};
return run();
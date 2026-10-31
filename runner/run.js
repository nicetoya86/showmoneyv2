// 사용: node runner/run.js <job> [--dry]   env: BOT CHAT DART STATE_PAT (DRY_RUN=1 도 가능)
// 로그 위생: 번들 console 전부 무음, 출력은 "job ok|err 소요시간"만. 상태/시그널/토큰 절대 출력 금지.
const fs = require('fs');
const path = require('path');
const { getState, snap, commit } = require('./state');

const JOBS = {
  scanner: 'swing-scanner', weekly: 'weekly-reporter', risk: 'risk-blacklist-updater',
  theme: 'theme-blacklist-updater', healthcheck: 'healthcheck', monitor: 'daily-position-monitor',
};
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

const job = process.argv[2];
const DRY = process.argv.includes('--dry') || process.env.DRY_RUN === '1';
const SECRETS = { BOT: process.env.BOT, CHAT: process.env.CHAT, DART: process.env.DART };
const mask = (s) => String(s).split(/\s+/).join(' ').replace(/\d{8,}:[\w-]{20,}/g, '***').replace(/[0-9a-f]{32,}/gi, '***')
  .split(SECRETS.BOT || '\u0000').join('***').split(SECRETS.DART || '\u0000').join('***').slice(0, 200);

// n8n this.helpers.httpRequest 호환 (쓰이는 옵션: json,method,headers,url,timeout,encoding,body)
const sent = [];
async function httpRequest(o) {
  if (DRY && /api\.telegram\.org/.test(o.url)) { sent.push(o.body && o.body.text ? o.body.text.length : 0); return { ok: true, dry: true }; }
  const json = o.json !== false;
  const headers = Object.assign({}, o.headers);
  let body = o.body;
  if (body != null && typeof body !== 'string' && !Buffer.isBuffer(body)) {
    body = JSON.stringify(body);
    if (!Object.keys(headers).some((k) => k.toLowerCase() === 'content-type')) headers['Content-Type'] = 'application/json';
  }
  const r = await fetch(o.url, { method: o.method || 'GET', headers, body, signal: AbortSignal.timeout(o.timeout || 30000) });
  const text = await r.text();
  if (!r.ok) { const e = new Error('HTTP ' + r.status); e.statusCode = r.status; throw e; }
  if (!json) return text;
  try { return JSON.parse(text); } catch (_) { return text; }
}

(async () => {
  const t0 = Date.now();
  const real = { log: console.log, err: console.error };
  let status = 'ok';
  try {
    if (!JOBS[job]) throw new Error('unknown job');
    const code = fs.readFileSync(path.join(__dirname, 'bundles', JOBS[job] + '.js'), 'utf8');
    const { data } = await getState();
    const base = snap(data);
    // 번들 소스는 맨 호출(run())이라 this = globalThis -> 전역에 노출 (n8n과 동일)
    globalThis.helpers = { httpRequest };
    globalThis.getWorkflowStaticData = () => data;
    console.log = console.info = console.warn = console.error = console.debug = () => {};
    const fn = new AsyncFunction('items', 'SECRETS', code);
    await fn.call(globalThis, [{ json: {} }], SECRETS);
    Object.assign(console, { log: real.log, error: real.err });
    if (DRY) {
      fs.writeFileSync(path.join(process.cwd(), 'state.dryrun.json'), JSON.stringify(data));
      status = 'ok dry sends=' + sent.length;
    } else {
      const { keys } = await commit(base, data, job);
      status = 'ok keys=' + keys.length;
    }
  } catch (e) {
    Object.assign(console, { log: real.log, error: real.err });
    status = 'err ' + mask(e && e.message);
    process.exitCode = 1;
  }
  real.log(`${job} ${status} ${((Date.now() - t0) / 1000).toFixed(1)}s`);
})();

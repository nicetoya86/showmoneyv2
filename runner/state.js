// 상태 저장: 비공개 저장소(showmoneyv2-state)의 state.json. Contents API + sha 낙관적 잠금.
// 잡 시작 시 전체 로드, 종료 시 "바뀐 최상위 키만" 최신본에 병합해 PUT (충돌 409/422면 재시도).
const REPO = process.env.STATE_REPO || 'nicetoya86/showmoneyv2-state';
const FILE = 'state.json';
const API = `https://api.github.com/repos/${REPO}/contents/${FILE}`;

const hdr = () => ({
  Authorization: `Bearer ${(process.env.STATE_PAT || "").replace(/[^!-~]/g, "")}`,
  Accept: 'application/vnd.github+json',
  'X-GitHub-Api-Version': '2022-11-28',
  'User-Agent': 'showmoneyv2-runner',
});

async function getState() {
  const r = await fetch(API, { headers: hdr() });
  if (r.status === 404) return { sha: null, data: {} };
  if (!r.ok) throw new Error('state GET ' + r.status);
  const j = await r.json();
  if (!j.content) throw new Error('state too large for contents API');
  return { sha: j.sha, data: JSON.parse(Buffer.from(j.content, 'base64').toString('utf8')) };
}

const snap = (o) => Object.fromEntries(Object.keys(o).map((k) => [k, JSON.stringify(o[k])]));

// base: 시작 시 로드본, cur: 잡이 수정한 객체. 반환: 바뀐 키 목록
function changedKeys(baseSnap, cur) {
  const keys = new Set([...Object.keys(baseSnap), ...Object.keys(cur)]);
  return [...keys].filter((k) => (k in cur ? JSON.stringify(cur[k]) : undefined) !== baseSnap[k]);
}

async function commit(baseSnap, cur, label) {
  const keys = changedKeys(baseSnap, cur);
  if (!keys.length) return { keys };
  for (let i = 0; i < 5; i++) {
    const latest = await getState();
    for (const k of keys) { if (k in cur) latest.data[k] = cur[k]; else delete latest.data[k]; }
    const body = { message: 'state ' + label, content: Buffer.from(JSON.stringify(latest.data)).toString('base64') };
    if (latest.sha) body.sha = latest.sha;
    const r = await fetch(API, { method: 'PUT', headers: { ...hdr(), 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (r.ok) return { keys };
    if (r.status !== 409 && r.status !== 422) throw new Error('state PUT ' + r.status);
    await new Promise((res) => setTimeout(res, 500 + Math.random() * 1500));
  }
  throw new Error('state PUT conflict x5');
}

module.exports = { getState, snap, changedKeys, commit };

// Shadow 코호트 계산 — 발송은 그대로 두고, weekly-reporter가 "만약 이 규칙으로 걸렀다면"의
// 성과를 사후 비교하기 위한 순수 함수 모음(I/O 없음). 설계: docs/02-design/features/volume5x-pattern-cap-shadow.design.md
// 번들러(build_deploy_bundle.js)가 lib 최상위 식별자 충돌을 점검하므로 전부 shadow*/SHADOW_* 접두를 쓴다.
const SHADOW_CFG = {
  rvolMin: 5,                    // 참고용 코호트(P0에서 효과 불확실)
  dayCap: 2,
  patternPriority: { 'D박스': 0, 'C촉매': 1, 'B지지선': 2, 'A눌림목': 3 }, // 미등록 패턴은 99
  gateMinClosed: 30, gateMinWeeks: 3, gateMinWinPctGain: 4,
  // [SHADOW-2026-10-19] market-state-shadow (docs/02-design/features/market-state-shadow.design.md §5)
  state: {
    block: ['SURGE', 'CRASH'],
    patExclude: { SURGE: '*', CRASH: ['D박스'], DOWN: ['A눌림목'] },   // '*' = 전 패턴
    caps: { UP: 3, FLAT: 3, DOWN: 1, SURGE: 1, CRASH: 0 },              // (일자, 시장, 상태) 버킷별 상한
    informativeMin: 5, informativeFrac: 0.15,                          // 정보주: 제외 건수 >= max(5, 15%)
  },
};
const SHADOW_COHORTS = ['ALL', 'NOCOMP', 'CAP2', 'NOCOMP+CAP2', 'RVOL5'];
const SHADOW_GATE_COHORTS = ['NOCOMP', 'CAP2', 'NOCOMP+CAP2', 'RVOL5'];

// 복합 태그는 패턴태그(≤2) 바로 뒤에 붙어 저장되는 signals.slice(0,3) 안에 항상 남는다.
function shadowIsComposite(r) {
  return Array.isArray(r && r.signals) && r.signals.some((s) => String(s).includes('복합'));
}

function shadowCapByDay(recs, cfg) {
  const byDate = new Map();
  for (const r of recs) {
    if (!byDate.has(r.date)) byDate.set(r.date, []);
    byDate.get(r.date).push(r);
  }
  const prio = (r) => (cfg.patternPriority[r.patternType] != null ? cfg.patternPriority[r.patternType] : 99);
  const out = [];
  for (const arr of byDate.values()) {
    out.push(...arr.slice().sort((a, b) => prio(a) - prio(b) || (b.score || 0) - (a.score || 0)).slice(0, cfg.dayCap));
  }
  return out;
}

// 선정은 결과(result)를 보지 않는다 — look-ahead 방지. 미확정(holding 등)도 슬롯을 차지한다.
function shadowSelect(newRecs, cohort, cfg) {
  cfg = cfg || SHADOW_CFG;
  const recs = Array.isArray(newRecs) ? newRecs : [];
  const noComp = () => recs.filter((r) => !shadowIsComposite(r));
  if (cohort === 'ALL') return recs.slice();
  if (cohort === 'NOCOMP') return noComp();
  if (cohort === 'CAP2') return shadowCapByDay(recs, cfg);
  if (cohort === 'NOCOMP+CAP2') return shadowCapByDay(noComp(), cfg);
  if (cohort === 'RVOL5') return recs.filter((r) => Number.isFinite(r.rvol) && r.rvol >= cfg.rvolMin);
  return [];
}

// ponytail: 승(win)을 목표가 수익률로 간주(수수료·슬리피지·부분체결 미반영) — 코호트 간 방향 비교용,
// 절대 수익률 아님. 정밀 손익이 필요하면 체결 단가 기록이 선행돼야 한다.
function shadowRet(r) {
  const v = r.result === 'win' ? (r.expiredForced ? r.finalReturn : r.targetPct) : r.stopPct;
  return Number.isFinite(v) ? v : 0;
}

function shadowStats(selected, name) {
  const sel = Array.isArray(selected) ? selected : [];
  const closed = sel.filter((r) => r.result === 'win' || r.result === 'partial_win' || r.result === 'loss');
  const win = closed.filter((r) => r.result === 'win').length;
  const part = closed.filter((r) => r.result === 'partial_win').length;
  const loss = closed.length - win - part;
  const c = closed.length;
  return {
    name, n: sel.length, closed: c, win, part, loss,
    winPct: c ? +(100 * win / c).toFixed(1) : 0,
    wpPct: c ? +(100 * (win + part) / c).toFixed(1) : 0,
    avgRet: c ? +(100 * closed.reduce((s, r) => s + shadowRet(r), 0) / c).toFixed(2) : 0,
  };
}

function computeShadowCohorts(details, cfg) {
  cfg = cfg || SHADOW_CFG;
  const newRecs = (Array.isArray(details) ? details : []).filter((d) => d && !d.carryOver);
  const out = {};
  for (const name of SHADOW_COHORTS) out[name] = shadowStats(shadowSelect(newRecs, name, cfg), name);
  out.RVOL5.missing = newRecs.filter((r) => !Number.isFinite(r.rvol)).length;
  return out;
}

// 승격 게이트 진행 상황(판정은 사람이 한다). weeklyStatsMap = store.shadowStats (배포 이후 주만 쌓임).
function shadowGate(weeklyStatsMap, cfg) {
  cfg = cfg || SHADOW_CFG;
  const weeks = Object.values(weeklyStatsMap || {});
  const res = {};
  for (const name of SHADOW_GATE_COHORTS) {
    let closedTotal = 0, nWeeks = 0, positive = 0, cWin = 0, aWin = 0, aClosed = 0;
    for (const w of weeks) {
      const c = w && w[name], a = w && w.ALL;
      if (!c || !a || !(a.closed > 0)) continue;
      closedTotal += c.closed;
      cWin += c.win; aWin += a.win; aClosed += a.closed;
      if (c.closed >= 5) { // 확정 5건 미만 주는 방향 판정 제외
        nWeeks++;
        if (c.winPct > a.winPct && c.avgRet > a.avgRet) positive++;
      }
    }
    const pooledWinGain = closedTotal > 0 && aClosed > 0 ? +(100 * cWin / closedTotal - 100 * aWin / aClosed).toFixed(1) : 0;
    res[name] = {
      closedTotal, weeks: nWeeks, weeksPositive: positive, pooledWinGain,
      passN: closedTotal >= cfg.gateMinClosed,
      passWeeks: nWeeks >= cfg.gateMinWeeks && positive * 3 >= nWeeks * 2,
      passGain: pooledWinGain >= cfg.gateMinWinPctGain,
    };
  }
  return res;
}

// ===== [SHADOW-2026-10-19] 시장상태 코호트 (market-state-shadow) =====
// 입력 추천은 mstate가 문자열인 것만 대상(null/미기록 제외). 'UNKNOWN'은 모든 코호트에서 통과하고 상한 슬롯을 쓰지 않는다.
const SHADOW_STATE_COHORTS = ['STATE_BLOCK', 'STATE_PAT', 'STATE_CAP', 'STATE_CAP_BEST', 'STATE_ALL'];
const SHADOW_STATE_GATE_COHORTS = ['STATE_BLOCK', 'STATE_PAT', 'STATE_CAP', 'STATE_ALL'];   // CAP_BEST는 라이브 불가(참고용)

const shadowHasState = (r) => !!r && typeof r.mstate === 'string';

function shadowStateBlock(recs, cfg) {
  return recs.filter((r) => r.mstate === 'UNKNOWN' || !cfg.state.block.includes(r.mstate));
}

function shadowStatePat(recs, cfg) {
  return recs.filter((r) => {
    if (r.mstate === 'UNKNOWN') return true;
    const rule = cfg.state.patExclude[r.mstate];
    if (rule === '*') return false;
    return !(Array.isArray(rule) && rule.includes(r.patternType));
  });
}

// mode 'first' = 선착순(sentAt, 없으면 입력 순서; 라이브 재현 가능), 'best' = D>C>B>A + 점수(하루가 끝나야 알 수 있음, 참고용)
function shadowStateCap(recs, cfg, mode) {
  const buckets = new Map();
  recs.forEach((r, idx) => {
    if (r.mstate === 'UNKNOWN' || cfg.state.caps[r.mstate] === undefined) return; // 상한 없음
    const key = [r.date, r.mkt, r.mstate].join('|');
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push({ r, idx });
  });
  const prio = (r) => (cfg.patternPriority[r.patternType] != null ? cfg.patternPriority[r.patternType] : 99);
  const keep = new Set();
  for (const arr of buckets.values()) {
    const useSentAt = arr.every((x) => Number.isFinite(x.r.sentAt));
    arr.sort((a, b) => {
      if (mode === 'best') return prio(a.r) - prio(b.r) || (b.r.score || 0) - (a.r.score || 0) || a.idx - b.idx;
      return (useSentAt ? a.r.sentAt - b.r.sentAt : 0) || a.idx - b.idx;
    });
    arr.slice(0, cfg.state.caps[arr[0].r.mstate]).forEach((x) => keep.add(x.r));
  }
  // 상한 대상이 아닌 추천은 통과, 대상은 keep에 있는 것만 — 출력은 입력 순서 유지
  return recs.filter((r) => r.mstate === 'UNKNOWN' || cfg.state.caps[r.mstate] === undefined || keep.has(r));
}

function shadowStateSelect(recs, cohort, cfg) {
  cfg = cfg || SHADOW_CFG;
  const base = (Array.isArray(recs) ? recs : []).filter(shadowHasState);
  if (cohort === 'STATE_BLOCK') return shadowStateBlock(base, cfg);
  if (cohort === 'STATE_PAT') return shadowStatePat(base, cfg);
  if (cohort === 'STATE_CAP') return shadowStateCap(base, cfg, 'first');
  if (cohort === 'STATE_CAP_BEST') return shadowStateCap(base, cfg, 'best');
  if (cohort === 'STATE_ALL') return shadowStateCap(shadowStatePat(shadowStateBlock(base, cfg), cfg), cfg, 'first');
  return [];
}

const shadowIsClosed = (r) => r.result === 'win' || r.result === 'partial_win' || r.result === 'loss';
const shadowSumPct = (rs) => +(100 * rs.filter(shadowIsClosed).reduce((s, r) => s + shadowRet(r), 0)).toFixed(2);

function computeShadowStateCohorts(details, cfg) {
  cfg = cfg || SHADOW_CFG;
  const recs = (Array.isArray(details) ? details : []).filter((d) => shadowHasState(d) && !d.carryOver);
  const all = shadowStats(recs, 'ALLS');
  all.sumRet = shadowSumPct(recs);
  all.excludedClosed = 0;
  all.excludedSum = 0;
  all.unknown = recs.filter((r) => r.mstate === 'UNKNOWN').length;
  const out = { ALLS: all };
  for (const name of SHADOW_STATE_COHORTS) {
    const sel = shadowStateSelect(recs, name, cfg);
    const picked = new Set(sel);
    const excluded = recs.filter((r) => !picked.has(r));
    const st = shadowStats(sel, name);
    st.sumRet = shadowSumPct(sel);
    st.excludedClosed = excluded.filter(shadowIsClosed).length;
    st.excludedSum = shadowSumPct(excluded);
    out[name] = st;
  }
  return out;
}

// 정보주(informative) = 코호트가 제외한 추천이 max(informativeMin, ceil(informativeFrac*ALLS.n)) 이상인 주.
// 제외가 없는 주는 코호트=기준선이라 증거가 아니다. 표본(passN)도 정보주의 확정만 센다. 판정은 사람이 한다.
function shadowStateGate(weeklyStatsMap, cfg) {
  cfg = cfg || SHADOW_CFG;
  const weeks = Object.values(weeklyStatsMap || {});
  const res = {};
  for (const name of SHADOW_STATE_GATE_COHORTS) {
    let closedTotal = 0, nWeeks = 0, positive = 0, cWin = 0, aWin = 0, aClosed = 0, cAvgSum = 0, aAvgSum = 0, exC = 0, exS = 0;
    for (const w of weeks) {
      const c = w && w[name], a = w && w.ALLS;
      if (!c || !a || !(a.n > 0)) continue;
      const need = Math.max(cfg.state.informativeMin, Math.ceil(cfg.state.informativeFrac * a.n - 1e-9));
      if (a.n - c.n < need) continue;
      nWeeks++;
      closedTotal += c.closed;
      cWin += c.win; aWin += a.win; aClosed += a.closed;
      cAvgSum += c.avgRet * c.closed; aAvgSum += a.avgRet * a.closed;
      exC += c.excludedClosed || 0; exS += c.excludedSum || 0;
      if (c.winPct > a.winPct && c.avgRet > a.avgRet) positive++;
    }
    const pooledWinGain = closedTotal > 0 && aClosed > 0 ? +(100 * cWin / closedTotal - 100 * aWin / aClosed).toFixed(1) : 0;
    const pooledAvgGain = closedTotal > 0 && aClosed > 0 ? +(cAvgSum / closedTotal - aAvgSum / aClosed).toFixed(2) : 0;
    const excludedAvgPooled = exC > 0 ? +(exS / exC).toFixed(2) : 0;
    res[name] = {
      closedTotal, informativeWeeks: nWeeks, weeksPositive: positive, pooledWinGain, pooledAvgGain, excludedAvgPooled,
      passN: closedTotal >= cfg.gateMinClosed,
      passWeeks: nWeeks >= cfg.gateMinWeeks && positive * 3 >= nWeeks * 2,
      passEffect: pooledWinGain >= cfg.gateMinWinPctGain && pooledAvgGain > 0 && exC > 0 && excludedAvgPooled < 0,
    };
  }
  return res;
}

// 일자·시장별 최빈 상태(동률이면 먼저 나온 것). mstate/mkt 없는 추천 무시.
function shadowStateSummary(recs) {
  const out = { KOSPI: [], KOSDAQ: [] };
  const by = { KOSPI: new Map(), KOSDAQ: new Map() };
  for (const r of Array.isArray(recs) ? recs : []) {
    if (!shadowHasState(r) || !by[r.mkt]) continue;
    const m = by[r.mkt];
    if (!m.has(r.date)) m.set(r.date, new Map());
    const s = m.get(r.date);
    s.set(r.mstate, (s.get(r.mstate) || 0) + 1);
  }
  for (const mkt of Object.keys(by)) {
    for (const date of [...by[mkt].keys()].sort()) {
      const s = by[mkt].get(date);
      let state = null, best = 0, n = 0;
      for (const [k, v] of s) { n += v; if (v > best) { best = v; state = k; } }
      out[mkt].push({ date, state, n });
    }
  }
  return out;
}

const SHADOW_STATE_LABELS = {
  STATE_BLOCK: '상태차단', STATE_PAT: '패턴표', STATE_CAP: '상한(선착순)', STATE_CAP_BEST: '상한(일최선·참고)', STATE_ALL: '결합',
};

function shadowFormatStateSection(stats, gate, summary) {
  const head = '🌡️ 시장상태 Shadow (발송 불변 · 이번 주 신규 확정 기준)';
  if (!stats || !stats.ALLS || !(stats.ALLS.n > 0)) return head + '\n상태 기록 없음 (배포 이후 추천부터 기록)';
  const sgn = (v, d) => (v >= 0 ? '+' : '') + v.toFixed(d);
  const lines = [head];
  const md = (d) => String(d).slice(5);
  for (const mkt of ['KOSDAQ', 'KOSPI']) {
    const rows = summary && summary[mkt];
    if (!rows || !rows.length) continue;
    const runs = [];
    for (const r of rows) {
      const last = runs[runs.length - 1];
      if (last && last.state === r.state) last.end = r.date; else runs.push({ state: r.state, start: r.date, end: r.date });
    }
    lines.push(mkt + ' ' + runs.map((x) => x.state + ' ' + md(x.start) + (x.end !== x.start ? '~' + md(x.end) : '')).join(' → '));
  }
  const fmt = (label, s, isBase) => {
    const base = label + ' 확정 ' + s.closed;
    if (!s.closed) return base + ' │ 데이터 없음';
    return base + ' │ 승 ' + s.winPct.toFixed(0) + '%' +
      ' │ 평균 ' + sgn(s.avgRet, 2) + '%' + ' │ 합 ' + sgn(s.sumRet, 0) + '%p' +
      (isBase ? '' : ' (승률 ' + sgn(s.winPct - stats.ALLS.winPct, 0) + '%p)') +
      (!isBase && s.excludedClosed > 0 ? ' │ 제외분 평균 ' + sgn(s.excludedSum / s.excludedClosed, 2) + '%' : '') +
      (s.closed < 5 ? ' ※표본 적음' : '');
  };
  lines.push(fmt('실발송(상태기록분)', stats.ALLS, true) + (stats.ALLS.unknown ? ' │ UNKNOWN ' + stats.ALLS.unknown + '건' : ''));
  for (const name of SHADOW_STATE_COHORTS) lines.push(fmt(SHADOW_STATE_LABELS[name], stats[name], false));
  for (const name of ['STATE_ALL', 'STATE_BLOCK']) {
    const g = gate && gate[name];
    if (!g) continue;
    lines.push('게이트 ' + SHADOW_STATE_LABELS[name] + ': 정보주 ' + g.informativeWeeks + '주 · 확정 ' + g.closedTotal + '/' + SHADOW_CFG.gateMinClosed +
      ' · 방향 ' + g.weeksPositive + '/' + g.informativeWeeks + ' · 승률 ' + sgn(g.pooledWinGain, 1) + '%p');
  }
  return lines.join('\n');
}

module.exports = {
  SHADOW_CFG, SHADOW_COHORTS, shadowIsComposite, shadowSelect, shadowStats, computeShadowCohorts, shadowGate,
  SHADOW_STATE_COHORTS, SHADOW_STATE_GATE_COHORTS, shadowStateSelect, computeShadowStateCohorts, shadowStateGate,
  shadowStateSummary, shadowFormatStateSection,
};

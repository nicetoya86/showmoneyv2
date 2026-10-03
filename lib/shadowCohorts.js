// Shadow 코호트 계산 — 발송은 그대로 두고, weekly-reporter가 "만약 이 규칙으로 걸렀다면"의
// 성과를 사후 비교하기 위한 순수 함수 모음(I/O 없음). 설계: docs/02-design/features/volume5x-pattern-cap-shadow.design.md
// 번들러(build_deploy_bundle.js)가 lib 최상위 식별자 충돌을 점검하므로 전부 shadow*/SHADOW_* 접두를 쓴다.
const SHADOW_CFG = {
  rvolMin: 5,                    // 참고용 코호트(P0에서 효과 불확실)
  dayCap: 2,
  patternPriority: { 'D박스': 0, 'C촉매': 1, 'B지지선': 2, 'A눌림목': 3 }, // 미등록 패턴은 99
  gateMinClosed: 30, gateMinWeeks: 3, gateMinWinPctGain: 4,
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

module.exports = { SHADOW_CFG, SHADOW_COHORTS, shadowIsComposite, shadowSelect, shadowStats, computeShadowCohorts, shadowGate };

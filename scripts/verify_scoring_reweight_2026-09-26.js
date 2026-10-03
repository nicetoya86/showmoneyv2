/**
 * Self-check for [FIX-2026-09-26] src/swing-scanner.src.js 스코어 재조정:
 * 09-09~09-23 11주/152건 실측 재검증(주간 리포트 항목4/5 연구) 결과를 반영한
 * 패턴 배점 순서, 복합태그 부호, 거래량2x/MACD↑ 가산점 제거, 진입가/ATR% 축 추가가
 * 소스에 그대로 남아있는지 확인한다(정성적 회귀 실수 방지 — 나중에 누가 실수로
 * 되돌리거나 값만 바꿔도 이 체크가 걸린다).
 *
 * 실제 로직은 스캐너 내부 클로저 안에 있어 단위함수로 분리하기 전까지는 소스 텍스트
 * 기반으로 검증한다(값/부호/순서만 확인, 계산 자체는 안 함).
 *
 * Run: node scripts/verify_scoring_reweight_2026-09-26.js
 */
'use strict';
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, '../src/swing-scanner.src.js'), 'utf-8');

let failures = 0;
const assert = (label, cond) => { if (!cond) { failures++; console.error(`FAIL ${label}`); } };

const scoreOf = (tag) => {
  const re = new RegExp(`score\\s*([+-]=)\\s*(\\d+);\\s*signals\\.push\\('${tag}'\\)`);
  const m = src.match(re);
  if (!m) return undefined;
  return m[1] === '+=' ? Number(m[2]) : -Number(m[2]);
};

// ---- 패턴 배점 순서: B > D > C > A ----
const b = scoreOf('지지선반등');
const d = scoreOf('박스권돌파');
const c = scoreOf('촉매이벤트');
const a = scoreOf('급등후눌림목');
assert('패턴 배점 전부 파싱됨', [a, b, c, d].every((v) => v !== undefined));
assert('B지지선 > D박스', b > d);
assert('D박스 > C촉매', d > c);
assert('C촉매 > A눌림목', c > a);

// ---- 복합 태그: 페널티(음수)로 전환 ----
assert('복합A+B는 음수(페널티)', scoreOf('복합A\\+B') < 0);
assert('복합C\\+D는 음수(페널티)', scoreOf('복합C\\+D') < 0);

// ---- 거래량2x / MACD↑: 가산점 제거(score +=/-= 없이 signals.push만) ----
assert('거래량2x에 score 가산 없음', !/rvolVal >= 2\.0.*\{\s*score/s.test(src.match(/rvolVal >= 2\.0[^\n]*\n?/)?.[0] || ''));
assert(
  '거래량2x 줄이 signals.push만 있음(score 변경 없음)',
  /else if \(rvolVal >= 2\.0\) \{ signals\.push\('거래량2x'\); \}/.test(src)
);
assert(
  'MACD↑ 줄이 signals.push만 있음(score 변경 없음)',
  /signals\.push\('MACD↑'\);\s*\n\s*\}/.test(src) && !/score\s*[+-]=\s*\d+;\s*signals\.push\('MACD↑'\)/.test(src)
);

// ---- 신규 축: 진입가(저가주/고가주), ATR%(스윗스팟/저변동주의) ----
assert('저가주 가산점 존재', scoreOf('저가주') > 0);
assert('고가주 페널티 존재', scoreOf('고가주') < 0);
assert('ATR스윗스팟 가산점 존재', scoreOf('ATR스윗스팟') > 0);
assert('ATR저변동주의 페널티 존재', scoreOf('ATR저변동주의') < 0);

// ---- atrAbs/atrPct가 스코어링 블록보다 먼저 선언돼야(ATR% 스코어링이 참조 가능) ----
const atrDeclIdx = src.indexOf('const atrAbs = calcAtrAbs(');
const scoringBlockIdx = src.indexOf("// ---- [S] 스코어링 ----");
assert('atrAbs 선언이 스코어링 블록보다 앞에 있음', atrDeclIdx >= 0 && scoringBlockIdx > atrDeclIdx);
assert('atrAbs 중복 선언 없음(재사용 확인)', (src.match(/const atrAbs = calcAtrAbs\(/g) || []).length === 1);

if (failures > 0) {
  console.error(`\n${failures} FAILURE(S)`);
  process.exit(1);
}
console.log('OK: scoring reweight (pattern order, composite penalty, weak-signal removal, price/ATR axes) verified');

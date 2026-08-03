/**
 * build_workflow.js
 * 최신 workflow JSON의 Code 노드를 swing_scanner_code.js 현재 버전으로 교체
 * 실행: node build_workflow.js
 */

const fs = require('fs');
const path = require('path');

const BASE = __dirname;
const SOURCE_CODE = path.join(BASE, 'swing_scanner_code.js');
const LATEST_WF   = path.join(BASE, 'workflow_FINAL_20260803_regime_gate_score_tier_intraday_breaker.json');

// 출력 파일명: 오늘 날짜 + 기능명
const now = new Date();
const ts = now.getFullYear().toString() +
  String(now.getMonth() + 1).padStart(2, '0') +
  String(now.getDate()).padStart(2, '0');
const OUTPUT = path.join(BASE, `workflow_FINAL_${ts}_running_lock_nodup.json`);

// 1. 파일 읽기
console.log('Reading files...');
const newCode = fs.readFileSync(SOURCE_CODE, 'utf8');
let rawWf = fs.readFileSync(LATEST_WF, 'utf8');
if (rawWf.charCodeAt(0) === 0xFEFF) rawWf = rawWf.slice(1); // strip BOM
const wf = JSON.parse(rawWf);

// 2. Code 노드 탐색 및 교체
let replaced = 0;
const codeNodes = [];

const CODE_FIELDS = ['functionCode', 'jsCode', 'code'];
const TARGET_NODE = 'Swing Scanner';

for (const node of wf.nodes) {
  const isFunction = node.type === 'n8n-nodes-base.function' || node.type === 'n8n-nodes-base.code';
  if (!isFunction) continue;
  if (node.name !== TARGET_NODE) continue;

  codeNodes.push(node.name);
  if (!node.parameters) continue;

  for (const field of CODE_FIELDS) {
    if (typeof node.parameters[field] === 'string' && node.parameters[field].length > 1000) {
      node.parameters[field] = newCode;
      replaced++;
      console.log(`  ✅ Replaced "${field}" in node: "${node.name}"`);
      break;
    }
  }
}

console.log(`\nCode nodes found: ${codeNodes.join(', ')}`);

if (replaced === 0) {
  console.error('❌ No code node replaced. Check node structure.');
  process.exit(1);
}

// 3. 저장
fs.writeFileSync(OUTPUT, JSON.stringify(wf, null, 2), 'utf8');
const size = (fs.statSync(OUTPUT).size / 1024).toFixed(1);
console.log(`\n✅ Output: ${path.basename(OUTPUT)}`);
console.log(`   Size: ${size} KB`);
console.log(`   Nodes replaced: ${replaced}`);
console.log('\n코드 변경 내용:');
console.log('  - [NODUP-3] _lastFullFinish(완료 후 90초 차단) → _runningSince 실행 중 락으로 교체');
console.log('    cron 1분 간격인데 실제 스캔이 9분+ 걸려 겹쳐 실행되며 동일 종목 중복 발송되던 문제 수정');
console.log('    MAX_SCAN_RUNTIME_MS(20분) 초과 시 락 자동 해제로 크래시 시 영구 잠김 방지');

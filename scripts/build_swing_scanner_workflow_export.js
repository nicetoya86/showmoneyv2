/**
 * build_swing_scanner_workflow_export.js
 * showmoneyv2_n8n_workflow.json(전체 워크플로우, 모든 노드 포함)의 각 Function 노드
 * 코드를 대응하는 현재 루트 배포 파일(*_code.js, scripts/build_deploy_bundle.js가 생성)로
 * 교체해 임포트용 워크플로우 파일을 만든다.
 *
 * 베이스 파일이 Swing Scanner뿐 아니라 Weekly Reporter/Risk Blacklist Updater/
 * Theme Blacklist Updater/Healthcheck 전부 2026-07-25 리팩토링(커밋 3d4ff24,
 * lib/naverClient.js BOM 정규화 버그픽스 포함) 이전 버전이라는 게 QA로 확인됨 —
 * Swing Scanner만 교체하면 이미 고친 "Naver BOM 응답 시 주간리포트 텅 비어 발송"
 * 버그가 재발한다. 그래서 5개 노드 전부 동기화한다.
 * (Backup Watchdog / Log Viewer는 src/ 관리 대상이 아니라 그대로 둔다.)
 *
 * 실행: node scripts/build_swing_scanner_workflow_export.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const BASE_WF = path.join(ROOT, 'showmoneyv2_n8n_workflow.json');

const now = new Date();
const ts = now.getFullYear().toString()
  + String(now.getMonth() + 1).padStart(2, '0')
  + String(now.getDate()).padStart(2, '0');
const OUT_NAME = `workflow_FINAL_${ts}_scan_interval_fix.json`;
const OUTPUT = path.join(ROOT, OUT_NAME);
const ARCHIVE = path.join(ROOT, 'backups', 'workflow-history', OUT_NAME);

// node name -> 현재 루트 배포 파일 (scripts/build_deploy_bundle.js의 MANIFEST와 동일 매핑)
const NODE_SOURCE_MAP = {
  'Swing Scanner': 'swing_scanner_code.js',
  'Weekly Reporter': 'weekly_reporter_code.js',
  'Risk Blacklist Updater': 'Refresh_Risk_Blacklist_KRX_KIND_code.js',
  'Theme Blacklist Updater': 'Refresh_Theme_Blacklist_Naver_code.js',
  'Healthcheck': 'Daily_Healthcheck_code.js',
};

let rawWf = fs.readFileSync(BASE_WF, 'utf8');
if (rawWf.charCodeAt(0) === 0xFEFF) rawWf = rawWf.slice(1);
const wf = JSON.parse(rawWf);

const CODE_FIELDS = ['functionCode', 'jsCode', 'code'];

let replaced = 0;
const expectedTargets = new Set(Object.keys(NODE_SOURCE_MAP));
for (const node of wf.nodes) {
  const isFunction = node.type === 'n8n-nodes-base.function' || node.type === 'n8n-nodes-base.code';
  if (!isFunction || !NODE_SOURCE_MAP[node.name]) continue;
  if (!node.parameters) continue;

  const sourceFile = path.join(ROOT, NODE_SOURCE_MAP[node.name]);
  const newCode = fs.readFileSync(sourceFile, 'utf8');

  for (const field of CODE_FIELDS) {
    if (typeof node.parameters[field] === 'string' && node.parameters[field].length > 500) {
      const oldLen = node.parameters[field].length;
      node.parameters[field] = newCode;
      replaced++;
      expectedTargets.delete(node.name);
      console.log(`Replaced "${field}" on node "${node.name}": ${oldLen} -> ${newCode.length} bytes`);
      break;
    }
  }
}

if (expectedTargets.size > 0) {
  console.error(`ERROR: expected to sync these nodes but did not find/replace them: ${[...expectedTargets].join(', ')}`);
  process.exit(1);
}
if (replaced !== Object.keys(NODE_SOURCE_MAP).length) {
  console.error(`ERROR: expected ${Object.keys(NODE_SOURCE_MAP).length} replacements, got ${replaced}.`);
  process.exit(1);
}

const out = JSON.stringify(wf, null, 2);
fs.writeFileSync(OUTPUT, out, 'utf8');
fs.mkdirSync(path.dirname(ARCHIVE), { recursive: true });
fs.writeFileSync(ARCHIVE, out, 'utf8');

console.log(`\nWrote: ${OUT_NAME} (${(out.length / 1024).toFixed(1)} KB)`);
console.log(`Archived copy: backups/workflow-history/${OUT_NAME}`);
console.log(`Total nodes in workflow: ${wf.nodes.length} (${replaced} code nodes synced: ${Object.keys(NODE_SOURCE_MAP).join(', ')}; Backup Watchdog/Log Viewer left as-is, no src/ file to sync from)`);

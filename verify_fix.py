import json
with open('workflow_WEEKLY_UPDATED_20260308_174439.json', encoding='utf-8') as f:
    wf = json.load(f)
nodes = wf.get('nodes', [])
sw = next((n for n in nodes if n.get('name') == 'Swing Scanner'), None)
code = sw['parameters'].get('functionCode','') or sw['parameters'].get('jsCode','')

checks = [
    ('[1] naverRawSample 진단 변수', 'naverRawSample = null' in code),
    ('[2] rawSample 캡처 로직', 'naverRawSample = JSON.stringify' in code),
    ('[3] YYYYMMDDHHMMSS 형식 변환', '000000' in code and '235959' in code),
    ('[4] fchart.stock.naver.com 폴백', 'fchart.stock.naver.com' in code),
    ('[5] fetchDailyFchart 파싱 로직', 'fetchDailyFchart' in code),
    ('[6] respToChart 공통 함수', 'const respToChart' in code),
    ('[7] rawSample 경고 메시지 포함', 'rawSample' in code and 'noResultAllDate' in code),
    ('[8] prevTradingDay 경고 포함', 'prevTradingDay' in code and 'rawInfo' in code),
    ('[9] n8n static data 재할당', 'store.naverCache = { daily: {}, dayKey }' in code),
    ('[10] prevTradingDay endDate', 'endDate = prevTradingDay' in code),
    ('[11] 3단계 폴백 구조', code.count('fetchDailyFchart') >= 1 and code.count('fetchDaily(') >= 2),
]
ok_cnt = sum(1 for _,v in checks if v)
fail_cnt = len(checks) - ok_cnt
for label, ok in checks:
    print(('[OK] ' if ok else '[NG] ') + label)
print()
print(f'결과: {ok_cnt} PASS / {fail_cnt} FAIL')

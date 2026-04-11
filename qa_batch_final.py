"""
최종 배치 동작 QA
스윙 스캐너 + 주간 리포트 전체 항목 검증
"""
import json, re

WF = 'workflow_WEEKLY_UPDATED_20260308_174439.json'
with open(WF, encoding='utf-8') as f:
    wf = json.load(f)
nodes = wf.get('nodes', [])

def get_code(name):
    n = next((x for x in nodes if x.get('name') == name), None)
    if not n: return ''
    p = n.get('parameters', {})
    return p.get('functionCode', '') or p.get('jsCode', '')

sw = get_code('Swing Scanner')
wr = get_code('Weekly Reporter')

results = []
p_cnt = 0
f_cnt = 0

def chk(label, cond, note=''):
    global p_cnt, f_cnt
    if cond: p_cnt += 1
    else: f_cnt += 1
    results.append(('PASS' if cond else 'FAIL', label, note))

# ============================================================
# 1. 워크플로우 구조
# ============================================================
scalp_off = [n for n in nodes if n.get('disabled') and
             any(k in n.get('name','') for k in ['Scalping','scalping'])]
chk('[구조] 스캘핑 4개 비활성화', len(scalp_off) == 4)
chk('[구조] Swing Scanner 활성', bool(sw))
chk('[구조] Weekly Reporter 활성', bool(wr))

# ============================================================
# 2. Naver API endDate 핵심 버그 수정 (2/25 장애 원인)
# ============================================================
chk('[API/핵심] getPrevTradingDay 함수 존재', 'getPrevTradingDay' in sw,
    '장중 당일 endDate → Naver 빈배열 반환 방지')
chk('[API/핵심] endDate = prevTradingDay 사용', 'endDate = prevTradingDay' in sw)
chk('[API/핵심] 당일 날짜 endDate 제거됨', 'endDate = kstNow.toISOString' not in sw)
chk('[API/핵심] retry도 prevTradingDay 사용', sw.count('prevTradingDay') >= 2)
chk('[API/핵심] HOLIDAYS 기반 주말/공휴일 skip', 'getPrevTradingDay' in sw and 'HOLIDAYS.includes(ds)' in sw)
# 최대 10회 반복 (공휴일 최대 연속 10일 처리)
chk('[API/핵심] 최대 10회 역방향 탐색', 'for (let i = 0; i < 10; i++)' in sw)

# ============================================================
# 3. API Rate-limiting 방어
# ============================================================
chk('[API/RateLimit] BATCH_SIZE = 10', 'BATCH_SIZE = 10' in sw)
chk('[API/RateLimit] BATCH_DELAY_MS = 600ms', 'BATCH_DELAY_MS = 600' in sw)
chk('[API/RateLimit] MIN_INTRADAY_TURNOVER 30억', 'MIN_INTRADAY_TURNOVER = 3000000000' in sw)
chk('[API/RateLimit] MAX_PAGES = 15', 'MAX_PAGES = 15' in sw)
chk('[API/RateLimit] timeout 45초', 'timeout: 45000' in sw)
chk('[API/RateLimit] 180일 fallback retry', '180 * 24 * 3600000' in sw)
chk('[API/RateLimit] 400/404 캐싱(무한재시도 방지)', 'status === 400 || status === 404' in sw)
chk('[API/RateLimit] sise_quant fallback try/catch', 'sise_quant.nhn' in sw and sw.count('try {') >= 3)
chk('[API/RateLimit] KRX 회로차단기', 'openCircuit' in sw)

# ============================================================
# 4. 데이터 무결성
# ============================================================
chk('[데이터] validIdx 배열 정렬', 'validIdx' in sw)
chk('[데이터] closeD/highD/lowD/volD 동기화', 'validIdx.map(i => rawClose[i])' in sw)
chk('[데이터] 최소 60일 데이터 보장', 'closeD.length < 60' in sw)
chk('[데이터] naverCache 당일 초기화', 'naverCache.dayKey !== dayKey' in sw)
chk('[데이터] 스캔 후 naverCache 메모리 정리', 'store.naverCache.daily = {}' in sw)

# ============================================================
# 5. 실행 제어 (시간/중복/공휴일)
# ============================================================
chk('[제어] 주말 차단', 'd >= 1 && d <= 5' in sw)
chk('[제어] 공휴일 차단', 'HOLIDAYS.includes(today)' in sw)
chk('[제어] 09:30 이전 차단', 'm < 30' in sw)
chk('[제어] 15:20 이후 차단', 'STOP_NEW_ALERTS_MINUTE = 20' in sw)
chk('[제어] 90초 재실행 방지', '_lastFullFinish' in sw)
chk('[제어] 3일 중복추천 방지', 'DUPLICATE_WINDOW_MINUTES = 4320' in sw)
chk('[제어] 9분 실행제한', '_MAX_EXEC_MS = 9 * 60 * 1000' in sw)

# ============================================================
# 6. 거래 로직
# ============================================================
chk('[로직] RSI 45-80 진입구간', 'RSI_MIN_ENTRY = 45' in sw and 'RSI_MAX_ENTRY = 80' in sw)
chk('[로직] ADX >= 20 추세강도', 'ADX_TREND_MIN = 20' in sw)
chk('[로직] RVOL >= 1.0 거래량', 'rvolVal < 1.0' in sw)
chk('[로직] SMA20 > SMA60 정배열', 'dailyUptrend' in sw)
chk('[로직] 3% 최저 목표가', 'MIN_TARGET_PCT = 0.03' in sw)
chk('[로직] R:R >= 1.5', 'MIN_RR_RATIO = 1.5' in sw)
chk('[로직] EMA 단기정배열', 'ema5[dIdx] > ema10[dIdx]' in sw)
chk('[로직] PTH 52주고점근접', 'pth >= 0.95' in sw)
chk('[로직] HiTalk AI pMAT', 'hitalkScoreSetups' in sw)
chk('[로직] 최소 2종목 relaxed', 'MIN_DAILY_PICKS = 2' in sw)
chk('[로직] 최대 4종목', 'MAX_INTRADAY_SENDS = 4' in sw)

# ============================================================
# 7. 에러 알림 체계
# ============================================================
chk('[알림] 유니버스 로드실패 경고', 'KRX 종목 데이터 로드 실패' in sw)
chk('[알림] 전종목빈결과 totalFetched 기준', 'totalFetched' in sw)
chk('[알림] API 에러 30분 쿨다운', 'lastErrorAt' in sw)
chk('[알림] 텔레그램 발송실패 알림', '발송 오류' in sw)
chk('[알림] 추천없음 당일1회 알림', 'noHitDate' in sw)

# ============================================================
# 8. 메시지 포맷
# ============================================================
chk('[메시지] 종목명(종목코드) 포맷', "esc(c.name) + '(' + c.code + ')'" in sw)
chk('[메시지] 전일종가 기준 안내', '전일종가 기준, 시초가 확인 필수' in sw)
chk('[메시지] HTML esc() 적용', 'esc(' in sw)

# ============================================================
# 9. 주간 리포트 핵심
# ============================================================
chk('[리포트] Yahoo Finance 제거됨', 'finance.yahoo.com' not in wr)
chk('[리포트] Naver API 사용', 'api.stock.naver.com' in wr)
chk('[리포트] swing 전용 필터', "r.type === 'swing'" in wr)
chk('[리포트] 3거래일 성과평가', 'addTradingDays' in wr and 'exitDate' in wr)
chk('[리포트] 목표가/손절가 도달판정', 'hitTargetDay' in wr and 'hitStopDay' in wr)
chk('[리포트] 먼저도달한것 기준', 'hitTargetDay <= hitStopDay' in wr)
chk('[리포트] 4가지 결과구분', "'expired'" in wr and "'holding'" in wr)
chk('[리포트] Telegram 4096자 분리전송', 'TELE_LIMIT' in wr)
chk('[리포트] daysToFri 올바른공식 (dow+2)', '(dow + 2)' in wr)
chk('[리포트] 잘못된공식(dow+1) 제거됨', '(dow + 1)' not in wr)
chk('[리포트] prevTradingDay 함수 추가됨', 'getPrevTradingDay' in wr,
    '토요일 실행시 Naver API 빈배열 방지')
chk('[리포트] endCheck prevTradingDay 사용', 'exitDate <= today ? exitDate : prevTradingDay' in wr)
# 스윙 스캐너 신규 수정 항목
chk('[스캐너] naverRawSample 진단 변수', 'naverRawSample = null' in sw)
chk('[스캐너] YYYYMMDDHHMMSS 형식', '000000' in sw and '235959' in sw)
chk('[스캐너] fchart.naver.com 폴백', 'fchart.stock.naver.com' in sw)
chk('[스캐너] n8n static data 재할당', 'store.naverCache = { daily: {}, dayKey }' in sw)
chk('[스캐너] rawSample 경고 포함', 'rawSample' in sw and 'rawInfo' in sw)
chk('[리포트] 2026-07-17 제헌절 포함', '2026-07-17' in wr)

# ============================================================
# 10. 공통 일관성
# ============================================================
sw_h = set(re.findall(r"'(\d{4}-\d{2}-\d{2})'", re.search(r'HOLIDAYS = \[([^\]]+)\]', sw).group(1) if re.search(r'HOLIDAYS = \[([^\]]+)\]', sw) else ''))
wr_h = set(re.findall(r"'(\d{4}-\d{2}-\d{2})'", re.search(r'HOLIDAYS = \[([^\]]+)\]', wr).group(1) if re.search(r'HOLIDAYS = \[([^\]]+)\]', wr) else ''))
chk('[공통] 스윙-리포트 공휴일 목록 일치', sw_h == wr_h,
    f'SW:{len(sw_h)}개 WR:{len(wr_h)}개')
chk('[공통] weeklyRecommendations 저장(스윙)', 'store.weeklyRecommendations' in sw)
chk('[공통] weeklyRecommendations 읽기(리포트)', 'store.weeklyRecommendations' in wr)
chk('[공통] holdingDays:3 저장', 'holdingDays: 3' in sw)
chk('[공통] r.holdingDays 읽기', 'r.holdingDays' in wr)
chk('[공통] entry/target/stop 저장', 'entry: res.entry' in sw)
chk('[공통] score 저장 및 리포트표시', 'score: selected[i].score' in sw and 'd.score' in wr)

# ============================================================
# 결과 출력
# ============================================================
total = p_cnt + f_cnt
print('=' * 62)
print(f'  최종 배치 QA: {p_cnt} PASS / {f_cnt} FAIL  (총 {total}개 항목)')
print('=' * 62)

cats = {}
for s, label, note in results:
    cat = label.split(']')[0].replace('[','').split('/')[0]
    cats.setdefault(cat, []).append((s, label, note))

for cat, items in cats.items():
    cp = sum(1 for s,_,__ in items if s == 'PASS')
    cf = sum(1 for s,_,__ in items if s == 'FAIL')
    print(f'\n  [{cat}]  {cp}/{len(items)} PASS')
    for s, label, note in items:
        mark = 'OK' if s == 'PASS' else 'NG'
        line = f'  {mark} {label}'
        if note: line += f'  ({note})'
        print(line)

if f_cnt > 0:
    print('\n  ===== FAIL 목록 =====')
    for s, label, note in results:
        if s == 'FAIL':
            print(f'  FAIL: {label}' + (f' ({note})' if note else ''))

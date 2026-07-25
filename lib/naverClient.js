// Naver 일봉/분봉 조회 — swing_scanner_code.js / weekly_reporter_code.js / Daily_Position_Monitor.js에
// 각각 독립적으로(그리고 서로 다르게) 구현돼 있던 것을 통합.
//
// 통합하며 실제로 확인된 차이(리팩토링 계획서 "결정 필요 항목" 참고)와 채택안:
// - 에러 처리: swing_scanner/Daily_Position_Monitor는 에러를 그대로 throw, weekly_reporter는
//   try/catch로 null 반환 → null 반환으로 통일(모든 호출부가 이미 null 체크 로직을 가짐).
// - Accept-Language: swing_scanner만 'en;q=0.8'까지 포함 → 더 넓은 값을 채택.
// - encoding: 'utf8': weekly_reporter만 빠져 있었음 → 포함으로 통일.
// - 응답 형태 정규화: Daily_Position_Monitor만 res.body/data/result/chartPriceList 언래핑을
//   했었음 → 다른 두 곳도 이 언래핑 혜택을 받도록 포함.
//
// [2026-07-25 BUGFIX] 통합 과정에서 swing_scanner_code.js에만 있던 Buffer/BOM/문자열
// JSON 응답 처리(_normalizeNaverResp, 2026-03-30 naver_resp_normalize 패치로 추가됨)가
// 빠져 있었다. 이 상태에서는 Naver가 응답을 문자열(BOM 포함)이나 Buffer로 반환하는 경우
// 정규화에 실패해 모든 종목이 null을 반환받아 주간 리포트가 "총추천 N건 │ 진입 0건"으로
// 통째로 비어버리는 문제가 재발한다(2026-03-30 "0/1348/0" 장애와 동일 유형). 아래에서
// 그 방어 로직을 다시 포함시킨다.
function createNaverClient(http) {
  const baseHeaders = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://finance.naver.com/',
    'Accept': 'application/json',
    'Accept-Charset': 'utf-8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
  };

  const normalize = (resp) => {
    let r = resp;
    if (r === null || r === undefined) return null;
    if (typeof Buffer !== 'undefined' && Buffer.isBuffer(r)) r = r.toString('utf8');
    if (typeof r === 'string') {
      const cleaned = r.replace(/^\uFEFF/, '').trim(); // BOM 및 앞뒤 공백 제거
      try { r = JSON.parse(cleaned); } catch (_) { return null; }
    }
    const items = Array.isArray(r)
      ? r
      : (r && (r.body || r.data || r.result || r.chartPriceList));
    return (Array.isArray(items) && items.length > 0) ? items : null;
  };

  const fetchDaily = async (code, startDate, endDate) => {
    const url = `https://api.stock.naver.com/chart/domestic/item/${code}/day?startDateTime=${startDate}&endDateTime=${endDate}`;
    try {
      const resp = await http({ method: 'GET', url, json: true, headers: baseHeaders, encoding: 'utf8' });
      return normalize(resp);
    } catch (e) {
      return null;
    }
  };

  const fetchMinute = async (code, dateStr) => {
    const ymd = dateStr.replace(/-/g, '');
    const url = `https://api.stock.naver.com/chart/domestic/item/${code}/minute?startDateTime=${ymd}000000&endDateTime=${ymd}235959`;
    try {
      const resp = await http({ method: 'GET', url, json: true, headers: baseHeaders, encoding: 'utf8' });
      return normalize(resp);
    } catch (e) {
      return null;
    }
  };

  return { fetchDaily, fetchMinute };
}

module.exports = { createNaverClient };

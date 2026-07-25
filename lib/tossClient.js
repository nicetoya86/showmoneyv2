// Toss Open API 원시 fetch — swing_scanner_code.js(fetchTossJSON)와
// Refresh_Risk_Blacklist_KRX_KIND_code.js(fetchTossAPI)에 독립적으로 구현돼 있던 것을 통합.
// 비즈니스 판단(VI/추격위험/재계산 등)은 여기 포함하지 않는다 — 순수 HTTP fetch만 담당.
//
// 통합하며 확인된 차이: swing_scanner 쪽만 `r.result`가 있으면 그 안쪽을 반환하는
// 언래핑을 했고, Risk Blacklist Updater 쪽은 언래핑 없이 raw 응답을 그대로 썼다(그 뒤
// `Array.isArray(resp)`로 바로 검사하므로, 만약 Toss가 그 엔드포인트를 `{result:[...]}`로
// 감싸서 내려주면 Risk Blacklist 쪽은 항상 배열이 아니라고 판단해 조용히 아무 종목도
// 걸러내지 못했을 가능성이 있다). 두 곳 다 언래핑을 포함한 버전으로 통일한다(더 안전한 쪽).
function createTossClient(http, apiKey, opts) {
  const timeout = (opts && opts.timeout) || 8000;

  const fetchJSON = async (endpoint) => {
    if (!apiKey) return null;
    try {
      const r = await http({
        method: 'GET',
        url: 'https://openapi.tossinvest.com' + endpoint,
        json: true,
        headers: { 'Authorization': 'Bearer ' + apiKey, 'Content-Type': 'application/json' },
        timeout,
      });
      return (r && r.result !== undefined) ? r.result : r;
    } catch (e) {
      return null;
    }
  };

  const fetchWarnings = (symbol) => fetchJSON('/api/v1/stocks/' + symbol + '/warnings');
  const fetchOrderbook = (symbol) => fetchJSON('/api/v1/orderbook?symbol=' + symbol);
  const fetchTrades = (symbol, count) => fetchJSON('/api/v1/trades?symbol=' + symbol + '&count=' + (count || 50));
  const fetchPriceLimits = (symbol) => fetchJSON('/api/v1/price-limits?symbol=' + symbol);

  return { fetchJSON, fetchWarnings, fetchOrderbook, fetchTrades, fetchPriceLimits };
}

module.exports = { createTossClient };

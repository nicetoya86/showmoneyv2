// 공통 포맷/유틸 헬퍼 — 여러 노드 소스에 복붙되어 있던 것을 통합.
//
// 주의(swing-scanner.src.js는 이 pct()를 쓰지 않는다): swing_scanner_code.js의 기존 pct()는
// 부호를 붙이지 않는 버전이었다(호출부 템플릿에서 '(+' / '(-'를 직접 문자열로 적어왔기
// 때문). 여기 pct()는 weekly_reporter/Daily_Position_Monitor가 쓰던, 값의 부호에 따라
// +/-를 스스로 붙이는 버전이다. 동작을 하나로 강제 통합하면 swing-scanner 쪽 메시지에
// 부호가 두 번 붙는 회귀가 생기므로, swing-scanner.src.js는 의도적으로 자기 파일 안에
// 부호 없는 pct()를 그대로 로컬로 유지한다.
function pct(r) {
  return (r >= 0 ? '+' : '') + (Number(r) * 100).toFixed(1) + '%';
}

// to0(): Daily_Position_Monitor의 기존 버전은 Number() 방어가 없었다(비정상 입력 시 'NaN'
// 문자열 노출). swing_scanner_code.js의 방어적인 버전(Number(n) || 0)을 정본으로 채택.
function to0(n) {
  return Math.round(Number(n) || 0).toLocaleString('ko-KR');
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

module.exports = { pct, to0, sleep };

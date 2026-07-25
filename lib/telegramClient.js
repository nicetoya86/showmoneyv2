// Telegram sendMessage 래퍼 — 여러 노드 소스에 복붙된 POST 요청을 통합.
// send()는 에러를 스스로 삼키지 않는다(순수 http() 호출 그대로) — 호출부마다
// try/catch 유무가 달랐던 기존 동작을 그대로 보존하기 위함.
function createTelegram(http, botToken, chatId) {
  const send = (text) => http({
    method: 'POST',
    url: 'https://api.telegram.org/bot' + botToken + '/sendMessage',
    json: true,
    body: { chat_id: chatId, text },
  });
  return { send };
}

module.exports = { createTelegram };

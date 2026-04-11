## n8n MCP 서버 (Cursor용)

이 폴더는 **Cursor(MCP 클라이언트)** 가 **n8n Cloud** 를 직접 다루도록 해주는 **로컬 MCP 서버**입니다.

- Cursor → (이 MCP 서버) → n8n Cloud REST API
- 워크플로우 “실행”은 환경에 따라 REST API로 막힐 수 있어서, 가장 확실한 방법인 **Webhook Trigger 호출**도 도구로 포함했습니다.

### 1) 준비물

- **n8n Cloud URL**
  - 예: `https://fastlane12.app.n8n.cloud`
- **n8n API Key**
  - n8n 설정에서 생성합니다.
  - API 인증/키 문서: `https://docs.n8n.io/api/authentication/`
- **Node.js 18 이상**

### 2) 설치

PowerShell(또는 터미널)에서 아래를 순서대로 실행하세요.

```bash
cd D:\vibecording\showmoneyv2\mcp\n8n-mcp
npm install
```

### 3) Cursor에 MCP Servers 추가 (UI로)

Cursor → Settings → MCP Servers → Add (또는 비슷한 메뉴)

- **Name**: `n8n-cloud`
- **Command**: `node`
- **Args**: `D:\vibecording\showmoneyv2\mcp\n8n-mcp\src\index.js`
- **Env**
  - `N8N_BASE_URL` = `https://fastlane12.app.n8n.cloud`
  - `N8N_API_KEY` = (n8n에서 발급받은 API Key)

> 주의: API Key는 절대 코드/파일에 저장하지 말고, 꼭 Cursor의 Env로만 넣으세요.

### 4) 연결 테스트

Cursor에서 아래 툴을 호출해보세요.

- `n8n_ping`
  - 성공하면 `ok: true` 와 함께 워크플로우 샘플이 나옵니다.

### 5) 워크플로우 실행(권장: Webhook Trigger)

1. n8n에서 워크플로우 시작 노드를 **Webhook Trigger**로 만든 뒤 저장/활성화합니다.
2. n8n이 제공하는 **Production URL**을 복사합니다.
3. Cursor에서 `n8n_trigger_webhook` tool에 URL을 넣어 호출합니다.




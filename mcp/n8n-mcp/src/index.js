import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

function requiredEnv(name) {
  const v = process.env[name];
  if (!v) throw new Error(`환경변수 ${name} 가(이) 필요합니다.`);
  return v;
}

function normalizeBaseUrl(raw) {
  let url = String(raw || "").trim();
  if (!url) throw new Error("N8N_BASE_URL 이 비어있습니다.");
  url = url.replace(/\/+$/, "");
  return url;
}

function buildHeaders() {
  const apiKey = requiredEnv("N8N_API_KEY");
  // n8n API Key 인증은 일반적으로 X-N8N-API-KEY 헤더를 사용합니다.
  // (문서/예시 참고: https://docs.n8n.io/api/authentication/)
  return {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-N8N-API-KEY": apiKey,
  };
}

async function fetchJson(url, init = {}) {
  const res = await fetch(url, init);
  const text = await res.text();

  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    // ignore
  }

  if (!res.ok) {
    const detail =
      json?.message ||
      json?.error ||
      (typeof json === "string" ? json : null) ||
      text ||
      res.statusText;
    const e = new Error(`n8n API 오류 (${res.status}): ${detail}`);
    e.status = res.status;
    e.responseText = text;
    e.responseJson = json;
    throw e;
  }
  return json;
}

function asTextResult(obj) {
  return [
    {
      type: "text",
      text: JSON.stringify(obj, null, 2),
    },
  ];
}

const server = new Server(
  { name: "n8n-mcp", version: "0.1.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "n8n_list_workflows",
        description: "n8n 워크플로우 목록을 조회합니다.",
        inputSchema: {
          type: "object",
          properties: {
            active: { type: "boolean", description: "활성화된 워크플로우만 조회" },
            limit: { type: "integer", minimum: 1, maximum: 200, default: 50 },
          },
          additionalProperties: false,
        },
      },
      {
        name: "n8n_get_workflow",
        description: "n8n 워크플로우 상세 정보를 조회합니다.",
        inputSchema: {
          type: "object",
          properties: {
            id: { type: ["string", "number"], description: "워크플로우 ID" },
          },
          required: ["id"],
          additionalProperties: false,
        },
      },
      {
        name: "n8n_list_executions",
        description: "n8n 실행(Execution) 목록을 조회합니다.",
        inputSchema: {
          type: "object",
          properties: {
            limit: { type: "integer", minimum: 1, maximum: 200, default: 20 },
            status: {
              type: "string",
              description: "success | error | waiting | running (n8n 버전에 따라 다를 수 있음)",
            },
            workflowId: { type: ["string", "number"], description: "특정 워크플로우 ID로 필터" },
          },
          additionalProperties: false,
        },
      },
      {
        name: "n8n_get_execution",
        description: "n8n 실행(Execution) 상세 정보를 조회합니다.",
        inputSchema: {
          type: "object",
          properties: {
            id: { type: ["string", "number"], description: "Execution ID" },
          },
          required: ["id"],
          additionalProperties: false,
        },
      },
      {
        name: "n8n_trigger_webhook",
        description:
          "n8n Webhook Trigger URL로 요청을 보내 워크플로우를 실행합니다. (가장 안정적인 실행 방식)",
        inputSchema: {
          type: "object",
          properties: {
            url: { type: "string", description: "n8n Webhook URL (Production URL 권장)" },
            method: { type: "string", enum: ["GET", "POST"], default: "POST" },
            body: { type: "object", description: "POST일 때 보낼 JSON 바디", default: {} },
            headers: {
              type: "object",
              description: "추가 헤더 (예: 인증 토큰 등). 기본값은 {}",
              default: {},
            },
          },
          required: ["url"],
          additionalProperties: false,
        },
      },
      {
        name: "n8n_ping",
        description: "n8n API 연결/인증이 정상인지 빠르게 확인합니다.",
        inputSchema: {
          type: "object",
          properties: {},
          additionalProperties: false,
        },
      },
    ],
  };
});

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const baseUrl = normalizeBaseUrl(requiredEnv("N8N_BASE_URL"));
  const headers = buildHeaders();

  try {
    switch (req.params.name) {
      case "n8n_ping": {
        // 가장 가벼운 호출로 인증/연결 확인
        const url = `${baseUrl}/api/v1/workflows?limit=1`;
        const data = await fetchJson(url, { method: "GET", headers });
        return { content: asTextResult({ ok: true, sample: data }) };
      }

      case "n8n_list_workflows": {
        const active = req.params.arguments?.active;
        const limit = req.params.arguments?.limit ?? 50;
        const qs = new URLSearchParams();
        qs.set("limit", String(limit));
        if (typeof active === "boolean") qs.set("active", String(active));
        const url = `${baseUrl}/api/v1/workflows?${qs.toString()}`;
        const data = await fetchJson(url, { method: "GET", headers });
        return { content: asTextResult(data) };
      }

      case "n8n_get_workflow": {
        const id = req.params.arguments?.id;
        const url = `${baseUrl}/api/v1/workflows/${encodeURIComponent(String(id))}`;
        const data = await fetchJson(url, { method: "GET", headers });
        return { content: asTextResult(data) };
      }

      case "n8n_list_executions": {
        const limit = req.params.arguments?.limit ?? 20;
        const status = req.params.arguments?.status;
        const workflowId = req.params.arguments?.workflowId;
        const qs = new URLSearchParams();
        qs.set("limit", String(limit));
        if (status) qs.set("status", String(status));
        if (workflowId != null) qs.set("workflowId", String(workflowId));
        const url = `${baseUrl}/api/v1/executions?${qs.toString()}`;
        const data = await fetchJson(url, { method: "GET", headers });
        return { content: asTextResult(data) };
      }

      case "n8n_get_execution": {
        const id = req.params.arguments?.id;
        const url = `${baseUrl}/api/v1/executions/${encodeURIComponent(String(id))}`;
        const data = await fetchJson(url, { method: "GET", headers });
        return { content: asTextResult(data) };
      }

      case "n8n_trigger_webhook": {
        const url = String(req.params.arguments?.url || "");
        const method = (req.params.arguments?.method || "POST").toUpperCase();
        const body = req.params.arguments?.body ?? {};
        const extraHeaders = req.params.arguments?.headers ?? {};

        if (!/^https?:\/\//i.test(url)) {
          throw new Error("url은 http(s)로 시작해야 합니다.");
        }

        const init = {
          method,
          headers: {
            "Accept": "application/json, text/plain, */*",
            ...(method === "POST" ? { "Content-Type": "application/json" } : {}),
            ...extraHeaders,
          },
        };
        if (method === "POST") init.body = JSON.stringify(body);

        const res = await fetch(url, init);
        const text = await res.text();
        let json = null;
        try {
          json = text ? JSON.parse(text) : null;
        } catch {
          // ignore
        }

        return {
          content: asTextResult({
            ok: res.ok,
            status: res.status,
            response: json ?? text,
          }),
        };
      }

      default:
        throw new Error(`알 수 없는 tool: ${req.params.name}`);
    }
  } catch (e) {
    return {
      content: asTextResult({
        ok: false,
        error: e?.message || String(e),
        status: e?.status,
      }),
      isError: true,
    };
  }
});

async function main() {
  // 시작 시 필수 env 확인 (실수 방지)
  normalizeBaseUrl(requiredEnv("N8N_BASE_URL"));
  requiredEnv("N8N_API_KEY");

  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error(err);
  process.exit(1);
});




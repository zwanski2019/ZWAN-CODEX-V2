const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8731";
const WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? "ws://127.0.0.1:8731";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export type Platform = "bbs" | "h1" | "bugcrowd" | "hackenproof";
export type FindingStatus = "pending" | "valid" | "killed" | "needs_review" | "submitted";
export type Severity = "critical" | "high" | "medium" | "low" | "info";

export interface Engagement {
  id: string;
  name: string;
  platform: Platform;
  scope_urls: string[];
  llm_budget_usd: number;
  llm_spent_usd: number;
}

export interface Finding {
  id: string;
  engagement_id: string;
  title: string;
  severity: Severity;
  status: FindingStatus;
  cvss_score: number | null;
  description: string;
  reproducer: string;
  impact: string;
  report_md: string;
  validator_reasoning: string;
  dup_similarity: number | null;
}

export interface AgentRun {
  id: string;
  engagement_id: string;
  agent_name: string;
  status: string;
  llm_tokens_in: number;
  llm_tokens_out: number;
  llm_cost_usd: number;
  error: string | null;
}

export const api = {
  engagements: {
    list: () => req<Engagement[]>("/api/engagements/"),
    get: (id: string) => req<Engagement>(`/api/engagements/${id}`),
    create: (body: { name: string; platform: Platform; scope_urls: string[]; llm_budget_usd?: number }) =>
      req<Engagement>("/api/engagements/", { method: "POST", body: JSON.stringify(body) }),
    start: (id: string) => req<{ queued: boolean }>(`/api/engagements/${id}/start`, { method: "POST" }),
  },
  findings: {
    list: (params?: { engagement_id?: string; status?: string; severity?: string }) => {
      const qs = new URLSearchParams(params as Record<string, string>).toString();
      return req<Finding[]>(`/api/findings/${qs ? "?" + qs : ""}`);
    },
    get: (id: string) => req<Finding>(`/api/findings/${id}`),
    update: (id: string, body: Partial<Finding>) =>
      req<Finding>(`/api/findings/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  },
  agents: {
    runs: (engagement_id?: string) => {
      const qs = engagement_id ? `?engagement_id=${engagement_id}` : "";
      return req<AgentRun[]>(`/api/agents/runs${qs}`);
    },
  },
  loot: {
    assets: (engagement_id?: string) => {
      const qs = engagement_id ? `?engagement_id=${engagement_id}` : "";
      return req<unknown[]>(`/api/loot/assets${qs}`);
    },
    secrets: (engagement_id?: string) => {
      const qs = engagement_id ? `?engagement_id=${engagement_id}` : "";
      return req<unknown[]>(`/api/loot/secrets${qs}`);
    },
  },
};

export function createWS(engagementId: string): WebSocket {
  return new WebSocket(`${WS_BASE}/ws/${engagementId}`);
}

import type {
  Analytics,
  Autopool,
  GatewayStatus,
  Me,
  ProxyFilters,
  ProxyResponse,
  ProxySource,
  Settings,
  SiteCheckResponse,
  Stats,
  Status,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: "include", ...init });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body.error ?? body.detail ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(message, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function jsonBody(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export const api = {
  me: () => request<Me>("/api/me"),

  login: (username: string, password: string) => {
    const form = new URLSearchParams({ username, password });
    return request<{ ok: boolean }>("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form.toString(),
    });
  },

  register: (username: string, password: string) => {
    const form = new URLSearchParams({ username, password });
    return request<{ ok: boolean }>("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form.toString(),
    });
  },

  logout: () => request<{ ok: boolean }>("/api/logout", { method: "POST" }),

  status: () => request<Status>("/api/status"),

  stats: () => request<Stats>("/api/stats"),

  settings: () => request<Settings>("/api/settings"),

  proxies: (filters: ProxyFilters) => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== "" && value !== null) {
        params.set(key, String(value));
      }
    }
    return request<ProxyResponse>(`/api/proxies?${params.toString()}`);
  },

  collect: (body: { target: number; protocols: string[]; rounds: number; use_custom: boolean }) =>
    request<{ ok: boolean; error: string | null }>("/api/collect", jsonBody(body)),

  stop: () => request<{ ok: boolean }>("/api/stop", { method: "POST" }),

  recheck: () => request<{ ok: boolean; error?: string }>("/api/proxies/recheck", { method: "POST" }),

  purgeDead: () => request<{ ok: boolean; removed: number }>("/api/proxies/purge-dead", {
    method: "POST",
  }),

  dedupe: () => request<{ ok: boolean; removed: number }>("/api/proxies/dedupe", {
    method: "POST",
  }),

  testProxies: (body: {
    url: string;
    protocol?: string;
    country?: string;
    anonymity?: string;
    limit?: number;
    timeout?: number;
  }) => request<SiteCheckResponse>("/api/proxies/test", jsonBody(body)),

  exportUrl: (fmt: "txt" | "json", protocol?: string) => {
    const params = new URLSearchParams({ fmt });
    if (protocol) params.set("protocol", protocol);
    return `/api/proxies/export?${params.toString()}`;
  },

  gateway: () => request<GatewayStatus>("/api/gateway"),

  gatewayStart: () => request<{ ok: boolean; error?: string; socks?: string; http?: string }>(
    "/api/gateway/start",
    { method: "POST" },
  ),

  gatewayStop: () => request<{ ok: boolean }>("/api/gateway/stop", { method: "POST" }),

  gatewayDropDead: () =>
    request<{ ok: boolean; dropped: number }>("/api/gateway/drop-dead", { method: "POST" }),

  gatewayRestore: () =>
    request<{ ok: boolean; restored: number }>("/api/gateway/restore", { method: "POST" }),

  gatewayScan: () =>
    request<{ ok: boolean; checked: number; alive: number; passed: number; failed: number }>(
      "/api/gateway/scan",
      { method: "POST" },
    ),

  gatewaySettings: (patch: Record<string, unknown>) =>
    request<GatewayStatus>("/api/gateway/settings", jsonBody(patch)),

  analytics: () => request<Analytics>("/api/analytics"),

  sources: () => request<{ items: ProxySource[] }>("/api/sources"),

  sourceAdd: (body: { url: string; protocol: string; note?: string }) =>
    request<{ ok: boolean; rows: number; detail: string }>("/api/sources", jsonBody(body)),

  sourceToggle: (body: { url: string; protocol: string; enabled: boolean }) =>
    request<{ ok: boolean }>("/api/sources/toggle", jsonBody(body)),

  sourceRemove: (body: { url: string; protocol: string }) =>
    request<{ ok: boolean }>("/api/sources/remove", jsonBody(body)),

  autopool: () => request<Autopool>("/api/autopool"),

  autopoolSet: (body: Partial<Autopool>) =>
    request<Autopool>("/api/autopool", jsonBody(body)),

  setQuota: (body: { mb: number; scope?: "all"; items?: { ip: string; port: number; protocol: string }[] }) =>
    request<{ ok: boolean; updated: number | string; quota_bytes: number }>(
      "/api/proxies/quota",
      jsonBody(body),
    ),

  setExcluded: (body: {
    excluded?: boolean;
    scope?: "all";
    items?: { ip: string; port: number; protocol: string }[];
  }) =>
    request<{ ok: boolean; updated: number | string; excluded: boolean }>(
      "/api/proxies/exclude",
      jsonBody(body),
    ),
};

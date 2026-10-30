export type LogLine = { ts: string; level: string; msg: string };

export type Status = {
  running: boolean;
  phase: string;
  target: number;
  alive: number;
  dead: number;
  checked: number;
  found_new: number;
  round: number;
  rounds: number;
  started_at: number | null;
  elapsed_s: number;
  message: string;
  logs: LogLine[];
  signup_sources: number;
  recheck_running: boolean;
  recheck_done: number;
  recheck_total: number;
};

export type ProxyRow = {
  ip: string;
  port: number;
  protocol: string;
  anonymity: string;
  latency_ms: number | null;
  https: number;
  country: string | null;
  country_code: string | null;
  city: string | null;
  isp: string | null;
  source: string | null;
  alive: number;
  checks_failed: number;
  last_checked: string | null;
  added_at: string;
  bytes_in: number;
  bytes_out: number;
  requests: number;
  quota_bytes: number;
  excluded: number;
  last_used: string | null;
};

export type ProxyResponse = {
  proxies: ProxyRow[];
  countries: string[];
  total: number;
};

export type Stats = {
  totals: { alive: number; dead: number; total: number; duplicates: number };
  protocols: { protocol: string; c: number; avg_ms: number | null }[];
  anonymity: { anonymity: string; c: number }[];
  countries: { code: string; country: string | null; c: number }[];
  latency: { bucket: string; c: number }[];
};

export type Settings = {
  validate_timeout: number;
  validate_concurrency: number;
  max_failed_checks: number;
  max_candidates: number;
  auto_dedupe: boolean;
  site_check_timeout: number;
  site_check_limit: number;
  geo_enrich: boolean;
  geo_max: number;
  signup_sources: string[];
};

export type SiteCheckRow = {
  ip: string;
  port: number;
  protocol: string;
  ok: boolean;
  status: number | null;
  latency_ms: number | null;
  error: string | null;
  country_code: string | null;
  isp: string | null;
  checked_at: string;
};

export type SiteCheckResponse = {
  url: string;
  total: number;
  passed: number;
  failed: number;
  avg_latency_ms: number | null;
  results: SiteCheckRow[];
};

export type Me = { username: string; is_admin: boolean };

export type GatewayStatus = {
  running: boolean;
  host: string;
  socks_port: number;
  http_port: number;
  strategy: string;
  quota_mb: number;
  timeout: number;
  max_fails: number;
  enabled_protocols: string[];
  connections: number;
  fails: number;
  active: number;
  bytes_in: number;
  bytes_out: number;
  uptime_s: number;
  pool: { eligible: number; bytes: number; requests: number; quota_rows: number };
  warnings: string[];
  last_error: string;
};

export type TrafficSample = {
  ts: string;
  bytes_in: number;
  bytes_out: number;
  requests: number;
};

export type Analytics = {
  totals: {
    total: number;
    alive: number;
    dead: number;
    excluded: number;
    exhausted: number;
    requests: number;
    bytes_in: number;
    bytes_out: number;
  };
  protocols: { protocol: string; c: number; bytes: number; requests: number; avg_ms: number | null }[];
  top: {
    ip: string;
    port: number;
    protocol: string;
    requests: number;
    bytes_in: number;
    bytes_out: number;
    quota_bytes: number;
    latency_ms: number | null;
    country_code: string | null;
  }[];
  quota: { bucket: string; c: number }[];
  samples: TrafficSample[];
  site_checks: { recent: number; passed: number };
  gateway: GatewayStatus;
};

export type ProxyFilters = {
  protocol?: string;
  country?: string;
  anonymity?: string;
  q?: string;
  sort?: string;
  offset?: number;
  limit?: number;
};

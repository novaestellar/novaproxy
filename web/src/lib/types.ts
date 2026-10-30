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

export type ProxyFilters = {
  protocol?: string;
  country?: string;
  anonymity?: string;
  q?: string;
  sort?: string;
  offset?: number;
  limit?: number;
};

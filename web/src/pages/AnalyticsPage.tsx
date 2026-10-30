import { useQuery } from "@tanstack/react-query";
import { BarChart3, CheckCircle2, Gauge, HardDrive, Layers, TrendingUp } from "lucide-react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { fmtBytes, fmtDuration, fmtLatency, pct } from "@/lib/utils";

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) {
    return (
      <div className="flex h-24 items-center justify-center text-[11px] text-faint">
        collecting samples…
      </div>
    );
  }
  const max = Math.max(...points, 1);
  const width = 600;
  const height = 96;
  const step = width / (points.length - 1);
  const path = points
    .map((value, index) => {
      const x = index * step;
      const y = height - (value / max) * (height - 8) - 4;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const area = `${path} L${width},${height} L0,${height} Z`;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-24 w-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id="traffic-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#traffic-fill)" />
      <path d={path} fill="none" stroke="var(--color-accent)" strokeWidth="1.5" />
    </svg>
  );
}

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string;
  value: string;
  hint?: string;
  icon: typeof Gauge;
}) {
  return (
    <Card>
      <CardContent className="flex items-start justify-between p-4">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-faint">{label}</div>
          <div className="mt-1 font-mono text-lg text-fg">{value}</div>
          {hint && <div className="mt-0.5 text-[11px] text-faint">{hint}</div>}
        </div>
        <div className="grid size-8 place-items-center rounded-md bg-accent/10 text-accent">
          <Icon className="size-4" />
        </div>
      </CardContent>
    </Card>
  );
}

export function AnalyticsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["analytics"],
    queryFn: api.analytics,
    refetchInterval: 5_000,
  });

  if (isLoading || !data) {
    return <div className="text-sm text-muted">Loading analytics…</div>;
  }

  const totals = data.totals;
  const relayed = totals.bytes_in + totals.bytes_out;
  const unlimited = data.quota.find((row) => row.bucket === "unlimited")?.c ?? 0;
  const quotaRows = data.quota
    .filter((row) => row.bucket !== "unlimited")
    .reduce((sum, row) => sum + row.c, 0);
  const checkRate = data.site_checks.recent
    ? pct(data.site_checks.passed, data.site_checks.recent)
    : 0;
  const series = data.samples.map((sample) => sample.bytes_in + sample.bytes_out);
  const totalRequests = Math.max(1, ...data.protocols.map((row) => row.c));

  return (
    <div>
      <PageHeader
        title="Analytics"
        subtitle="Pool composition, relayed traffic, quota usage and site-check health."
        actions={
          <Badge variant={data.gateway.running ? "success" : "default"}>
            gateway {data.gateway.running ? "running" : "stopped"}
          </Badge>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Alive / total"
          value={`${totals.alive.toLocaleString()} / ${totals.total.toLocaleString()}`}
          hint={`${totals.dead.toLocaleString()} dead · ${totals.excluded.toLocaleString()} excluded`}
          icon={Layers}
        />
        <StatCard
          label="Requests relayed"
          value={totals.requests.toLocaleString()}
          hint={`${fmtBytes(relayed)} total · ↓ ${fmtBytes(totals.bytes_in)}`}
          icon={TrendingUp}
        />
        <StatCard
          label="Quota exhausted"
          value={totals.exhausted.toLocaleString()}
          hint={`${quotaRows} limited · ${unlimited} unlimited`}
          icon={HardDrive}
        />
        <StatCard
          label="Site check pass"
          value={`${checkRate}%`}
          hint={`${data.site_checks.passed}/${data.site_checks.recent} recent checks`}
          icon={CheckCircle2}
        />
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="size-4 text-accent" />
                Traffic samples
              </CardTitle>
              <CardDescription>Bytes relayed per 30 s sample, newest right.</CardDescription>
            </div>
            <Badge variant="info">
              {fmtBytes(series.reduce((a, b) => a + b, 0))} sampled
            </Badge>
          </CardHeader>
          <CardContent>
            <Sparkline points={series} />
            <div className="mt-1 flex justify-between text-[10px] text-faint">
              <span>{data.samples[0]?.ts ?? "—"}</span>
              <span>{data.samples[data.samples.length - 1]?.ts ?? "—"}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Quota distribution</CardTitle>
              <CardDescription>Per-proxy allowance state.</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.quota.map((row) => {
              const variant =
                row.bucket === "exhausted"
                  ? "danger"
                  : row.bucket === "half"
                    ? "warning"
                    : row.bucket === "fresh"
                      ? "success"
                      : "default";
              const total = data.quota.reduce((sum, item) => sum + item.c, 0) || 1;
              return (
                <div key={row.bucket}>
                  <div className="mb-1 flex items-center justify-between text-[11px]">
                    <Badge variant={variant}>{row.bucket}</Badge>
                    <span className="font-mono text-faint">{row.c}</span>
                  </div>
                  <Progress
                    value={pct(row.c, total)}
                    className="h-1"
                    indicatorClassName={
                      row.bucket === "exhausted"
                        ? "from-danger to-danger"
                        : row.bucket === "half"
                          ? "from-warning to-warning"
                          : undefined
                    }
                  />
                </div>
              );
            })}
          </CardContent>
        </Card>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>By protocol</CardTitle>
              <CardDescription>Count, relayed bytes and average latency.</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.protocols.length === 0 && (
              <div className="text-[12px] text-muted">No alive proxies yet.</div>
            )}
            {data.protocols.map((row) => (
              <div key={row.protocol}>
                <div className="mb-1 flex items-center justify-between text-[12px]">
                  <span className="font-mono text-fg">{row.protocol}</span>
                  <span className="text-faint">
                    {row.c.toLocaleString()} · {fmtBytes(row.bytes)} · {fmtLatency(row.avg_ms)}
                  </span>
                </div>
                <Progress value={pct(row.c, totalRequests)} className="h-1" />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Gateway</CardTitle>
              <CardDescription>Live counters from the local endpoint.</CardDescription>
            </div>
            <Badge variant={data.gateway.running ? "success" : "default"}>
              {data.gateway.running ? "up" : "down"}
            </Badge>
          </CardHeader>
          <CardContent className="space-y-2 text-[12px]">
            {[
              ["SOCKS5", `${data.gateway.host}:${data.gateway.socks_port}`],
              ["HTTP", `${data.gateway.host}:${data.gateway.http_port}`],
              ["Strategy", data.gateway.strategy],
              ["Uptime", fmtDuration(data.gateway.uptime_s)],
              ["Connections", data.gateway.connections.toLocaleString()],
              ["Active", data.gateway.active.toLocaleString()],
              ["Failures", data.gateway.fails.toLocaleString()],
              ["Relayed", fmtBytes(data.gateway.bytes_in + data.gateway.bytes_out)],
            ].map(([label, value]) => (
              <div
                key={label}
                className="flex items-center justify-between border-b border-border/60 pb-1.5 last:border-0 last:pb-0"
              >
                <span className="text-faint">{label}</span>
                <span className="font-mono text-fg">{value}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

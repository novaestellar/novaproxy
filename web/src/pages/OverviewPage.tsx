import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowRight,
  Globe2,
  Loader2,
  Play,
  Square,
  Target,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useLive } from "@/lib/live";
import { fmtDuration, pct } from "@/lib/utils";
import { PageHeader } from "@/components/PageHeader";
import { LogConsole } from "@/components/LogConsole";
import { CollectDialog } from "@/components/CollectDialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, Skeleton } from "@/components/ui/progress";

const LATENCY_ORDER = ["<250", "250-500", "500-1k", "1-2k", "2s+", "n/a"];
const ANON_COLORS: Record<string, string> = {
  elite: "var(--color-success)",
  anonymous: "var(--color-accent-bright)",
  transparent: "var(--color-warning)",
  unknown: "var(--color-faint)",
};

const tooltipStyle = {
  background: "var(--color-panel)",
  border: "1px solid var(--color-border)",
  borderRadius: 8,
  fontSize: 12,
  color: "var(--color-fg)",
};

type BadgeTone = "default" | "accent" | "success" | "warning" | "danger" | "info" | "outline";

function phaseTone(running: boolean, phase: string): BadgeTone {
  if (!running) return phase === "done" ? "success" : phase === "stopped" ? "warning" : "default";
  if (phase.includes("cooldown")) return "warning";
  if (phase.includes("validat") || phase.includes("fetch") || phase.includes("signup"))
    return "info";
  return "accent";
}

export function OverviewPage() {
  const { status } = useLive();
  const [collectOpen, setCollectOpen] = useState(false);

  const statsQuery = useQuery({
    queryKey: ["stats"],
    queryFn: api.stats,
    refetchInterval: 10_000,
  });

  const stop = useMutation({
    mutationFn: api.stop,
    onSuccess: () => toast.message("Stop requested — finishing current checks"),
    onError: (error: Error) => toast.error(error.message),
  });

  const stats = statsQuery.data;
  const running = status?.running ?? false;
  const target = status?.target ?? 0;
  const alive = status?.alive ?? stats?.totals.alive ?? 0;
  const progress = pct(alive, target);

  const latencyData = LATENCY_ORDER.map((bucket) => ({
    bucket,
    count: stats?.latency.find((row) => row.bucket === bucket)?.c ?? 0,
  }));

  const anonymityData = (stats?.anonymity ?? []).map((row) => ({
    name: row.anonymity,
    value: row.c,
  }));

  const protocolTotal = (stats?.protocols ?? []).reduce((sum, row) => sum + row.c, 0);
  const topCountryMax = Math.max(1, ...(stats?.countries ?? []).map((row) => row.c));
  const weightedLatency = (stats?.protocols ?? []).reduce(
    (sum, row) => sum + (row.avg_ms ?? 0) * row.c,
    0,
  );
  const avgLatency = protocolTotal ? Math.round(weightedLatency / protocolTotal) : 0;
  const eliteCount =
    stats?.anonymity.find((row) => row.anonymity === "elite")?.c ?? 0;
  const idleCells: [string, string][] = [
    ["Dead", (stats?.totals.dead ?? status?.dead ?? 0).toLocaleString()],
    ["Validated", (stats?.totals.total ?? 0).toLocaleString()],
    ["Elite", eliteCount.toLocaleString()],
    ["Avg latency", avgLatency ? `${avgLatency}ms` : "—"],
  ];
  const runCells: [string, string][] = [
    ["Round", `${status?.round ?? 0}/${status?.rounds ?? 0}`],
    ["Checked", (status?.checked ?? 0).toLocaleString()],
    ["New", (status?.found_new ?? 0).toLocaleString()],
    ["Elapsed", fmtDuration(status?.elapsed_s ?? 0)],
  ];

  return (
    <>
      <PageHeader
        title="Overview"
        actions={
          running ? (
            <>
              <Badge variant="success" className="h-7 px-2.5">
                <span className="size-1.5 rounded-full bg-success live-dot" />
                running
              </Badge>
              <Button variant="danger" onClick={() => stop.mutate()} disabled={stop.isPending}>
                <Square className="size-3.5" />
                Stop
              </Button>
            </>
          ) : (
            <Button onClick={() => setCollectOpen(true)}>
              <Play className="size-3.5" />
              Start collecting
            </Button>
          )
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle className="flex items-center gap-2">
                <Target className="size-4 text-accent" />
                Collection quota
              </CardTitle>
              <CardDescription>
                {running
                  ? `Round ${status?.round}/${status?.rounds} · ${status?.phase}`
                  : status?.message || "No active run"}
              </CardDescription>
            </div>
            <Badge variant={phaseTone(running, status?.phase ?? "idle")}>
              {running && <Loader2 className="size-3 animate-spin" />}
              {status?.phase ?? "idle"}
            </Badge>
          </CardHeader>
          <CardContent>
            <div className="flex items-end justify-between">
              <div className="font-mono text-3xl tracking-tight">
                {alive.toLocaleString()}
                <span className="ml-2 text-sm text-faint">
                  {running && target ? `/ ${target.toLocaleString()} alive` : "alive"}
                </span>
              </div>
              {running && target > 0 && (
                <div className="text-right text-[11px] text-faint">{progress}% of target</div>
              )}
            </div>
            {running && target > 0 && (
              <Progress value={progress} className="mt-3 h-2" />
            )}

            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {(running ? runCells : idleCells).map(([label, value]) => (
                <div key={label} className="rounded-md border border-border bg-background/40 p-2.5">
                  <div className="text-[10px] uppercase tracking-wider text-faint">{label}</div>
                  <div className="mt-1 font-mono text-[13px] text-fg">{value}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle className="flex items-center gap-2">
                <Globe2 className="size-4 text-info" />
                Protocol mix
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {statsQuery.isLoading &&
              Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-9 w-full" />)}
            {!statsQuery.isLoading && protocolTotal === 0 && (
              <div className="py-6 text-center text-[12px] text-faint">No proxies yet.</div>
            )}
            {(stats?.protocols ?? []).map((row) => (
              <div key={row.protocol}>
                <div className="mb-1.5 flex items-baseline justify-between text-[12px]">
                  <span className="font-mono uppercase text-fg">{row.protocol}</span>
                  <span className="text-faint">
                    {row.c.toLocaleString()}
                    {row.avg_ms != null && (
                      <span className="ml-2 text-[11px]">~{Math.round(row.avg_ms)}ms</span>
                    )}
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-elevated">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-accent/70 to-accent"
                    style={{ width: `${pct(row.c, protocolTotal)}%` }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Latency distribution</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={latencyData} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <XAxis
                    dataKey="bucket"
                    tick={{ fill: "var(--color-faint)", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: "var(--color-faint)", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip
                    cursor={{ fill: "color-mix(in oklab, var(--color-accent) 10%, transparent)" }}
                    contentStyle={tooltipStyle}
                    labelStyle={{ color: "var(--color-muted)" }}
                  />
                  <Bar
                    dataKey="count"
                    radius={[4, 4, 0, 0]}
                    fill="var(--color-accent-bright)"
                    maxBarSize={56}
                    isAnimationActive={false}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Anonymity</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="relative h-40">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={anonymityData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={44}
                    outerRadius={66}
                    paddingAngle={2}
                    stroke="none"
                    isAnimationActive={false}
                  >
                    {anonymityData.map((entry) => (
                      <Cell key={entry.name} fill={ANON_COLORS[entry.name] ?? "var(--color-faint)"} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                <span className="font-mono text-xl text-fg">
                  {anonymityData.reduce((sum, entry) => sum + entry.value, 0).toLocaleString()}
                </span>
                <span className="text-[10px] uppercase tracking-wider text-faint">alive</span>
              </div>
            </div>
            <div className="mt-2 space-y-1.5">
              {anonymityData.map((entry) => (
                <div key={entry.name} className="flex items-center gap-2 text-[11px]">
                  <span
                    className="size-2 rounded-full"
                    style={{ background: ANON_COLORS[entry.name] ?? "var(--color-faint)" }}
                  />
                  <span className="capitalize text-muted">{entry.name}</span>
                  <span className="ml-auto font-mono text-faint">{entry.value}</span>
                </div>
              ))}
              {anonymityData.length === 0 && (
                <div className="py-4 text-center text-[11px] text-faint">No data yet.</div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Top countries</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-2.5">
            {(stats?.countries ?? []).map((row) => (
              <div key={row.code} className="flex items-center gap-2 text-[12px]">
                <span className="w-7 font-mono text-[11px] text-faint">{row.code}</span>
                <span className="w-28 truncate text-muted">{row.country ?? row.code}</span>
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-elevated">
                  <div
                    className="h-full rounded-full bg-info/70"
                    style={{ width: `${pct(row.c, topCountryMax)}%` }}
                  />
                </div>
                <span className="w-8 text-right font-mono text-[11px] text-faint">{row.c}</span>
              </div>
            ))}
            {(stats?.countries ?? []).length === 0 && (
              <div className="py-6 text-center text-[12px] text-faint">
                No geo data yet.
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Recent activity</CardTitle>
            </div>
            <Link
              to="/logs"
              className="flex items-center gap-1 text-[11px] text-accent hover:underline"
            >
              Full log <ArrowRight className="size-3" />
            </Link>
          </CardHeader>
          <CardContent>
            <LogConsole logs={(status?.logs ?? []).slice(-14)} height="13.5rem" compact />
          </CardContent>
        </Card>
      </div>

      <CollectDialog open={collectOpen} onOpenChange={setCollectOpen} />
    </>
  );
}

import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowDownToLine,
  ArrowUpFromLine,
  Copy,
  Network,
  Play,
  Square,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label, NativeSelect } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { fmtBytes, fmtDuration, fmtLatency, pct } from "@/lib/utils";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-[11px] uppercase tracking-wide text-faint">{label}</div>
        <div className="mt-1 font-mono text-lg text-fg">{value}</div>
        {hint && <div className="mt-0.5 text-[11px] text-faint">{hint}</div>}
      </CardContent>
    </Card>
  );
}

export function GatewayPage() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["gateway"],
    queryFn: api.gateway,
    refetchInterval: 2_000,
  });
  const { data: analytics } = useQuery({
    queryKey: ["analytics"],
    queryFn: api.analytics,
    refetchInterval: 5_000,
  });

  const [form, setForm] = useState({
    strategy: "round_robin",
    quota_mb: 0,
    timeout: 12,
    max_fails: 3,
    socks_port: 11080,
    http_port: 8120,
  });

  useEffect(() => {
    if (!data) return;
    setForm({
      strategy: data.strategy,
      quota_mb: data.quota_mb,
      timeout: data.timeout,
      max_fails: data.max_fails,
      socks_port: data.socks_port,
      http_port: data.http_port,
    });
  }, [data?.strategy, data?.quota_mb, data?.timeout, data?.max_fails, data?.socks_port, data?.http_port]);

  const start = useMutation({
    mutationFn: api.gatewayStart,
    onSuccess: (res) => {
      if (res.ok) toast.success(`Gateway up · ${res.socks} / ${res.http}`);
      else toast.error(res.error ?? "Failed to start");
      refetch();
    },
  });

  const stop = useMutation({
    mutationFn: api.gatewayStop,
    onSuccess: () => {
      toast.success("Gateway stopped");
      refetch();
    },
  });

  const save = useMutation({
    mutationFn: () => api.gatewaySettings(form),
    onSuccess: () => {
      toast.success("Gateway settings saved");
      refetch();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const dropDead = useMutation({
    mutationFn: api.gatewayDropDead,
    onSuccess: (res) => {
      toast.success(`Dropped ${res.dropped} dead proxies from rotation`);
      refetch();
    },
  });

  const restore = useMutation({
    mutationFn: api.gatewayRestore,
    onSuccess: (res) => {
      toast.success(`Restored ${res.restored} proxies`);
      refetch();
    },
  });

  const scan = useMutation({
    mutationFn: api.gatewayScan,
    onSuccess: (res) => {
      toast.success(`Scanned ${res.checked} · ${res.passed} alive · ${res.alive} eligible`);
      refetch();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const copy = (text: string, label: string) =>
    navigator.clipboard.writeText(text).then(
      () => toast.success(`${label} copied`),
      () => toast.error("Clipboard unavailable"),
    );

  if (isLoading || !data) {
    return <div className="text-sm text-muted">Loading gateway…</div>;
  }

  const socksUrl = `socks5://${data.host}:${data.socks_port}`;
  const httpUrl = `http://${data.host}:${data.http_port}`;
  const top = analytics?.top ?? [];

  return (
    <div>
      <PageHeader
        title="Gateway"
        subtitle="One local endpoint in front of the pool — rotation, failover, byte accounting and quota."
        actions={
          <>
            <Button
              size="sm"
              variant="outline"
              onClick={() => scan.mutate()}
              disabled={scan.isPending}
            >
              {scan.isPending ? "Scanning…" : "Scan pool"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => dropDead.mutate()}
              disabled={dropDead.isPending}
            >
              Drop dead
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => restore.mutate()}
              disabled={restore.isPending}
            >
              Restore
            </Button>
            {data.running ? (
              <Button variant="danger" size="sm" onClick={() => stop.mutate()} disabled={stop.isPending}>
                <Square className="size-3.5" />
                Stop gateway
              </Button>
            ) : (
              <Button size="sm" onClick={() => start.mutate()} disabled={start.isPending}>
                <Play className="size-3.5" />
                Start gateway
              </Button>
            )}
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Status"
          value={data.running ? "running" : "stopped"}
          hint={data.running ? `uptime ${fmtDuration(data.uptime_s)}` : "not accepting clients"}
        />
        <Stat
          label="Connections"
          value={data.connections.toLocaleString()}
          hint={`${data.active} active · ${data.fails} failed`}
        />
        <Stat
          label="Relayed"
          value={fmtBytes(data.bytes_in + data.bytes_out)}
          hint={`↓ ${fmtBytes(data.bytes_in)} · ↑ ${fmtBytes(data.bytes_out)}`}
        />
        <Stat
          label="Eligible proxies"
          value={data.pool.eligible.toLocaleString()}
          hint={data.pool.quota_rows ? `${data.pool.quota_rows} with quota` : "no quotas set"}
        />
      </div>

      {data.warnings.length > 0 && (
        <Card className="mt-3 border-warning/25 bg-warning/5">
          <CardContent className="space-y-1.5 p-4">
            {data.warnings.map((warning) => (
              <div key={warning} className="flex items-start gap-2 text-[12px] text-warning">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                <span>{warning}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div>
              <CardTitle className="flex items-center gap-2">
                <Network className="size-4 text-accent" />
                Endpoints
              </CardTitle>
              <CardDescription>Point any client here; the gateway rotates and fails over.</CardDescription>
            </div>
            <Badge variant={data.running ? "success" : "default"}>
              {data.running ? "listening" : "offline"}
            </Badge>
          </CardHeader>
          <CardContent className="space-y-2">
            {[
              { label: "SOCKS5", value: socksUrl },
              { label: "HTTP", value: httpUrl },
            ].map((row) => (
              <div
                key={row.label}
                className="flex items-center justify-between gap-3 rounded-md border border-border bg-background/60 px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="text-[10px] uppercase tracking-wide text-faint">{row.label}</div>
                  <div className="truncate font-mono text-[12px] text-fg">{row.value}</div>
                </div>
                <Button size="icon-sm" variant="ghost" onClick={() => copy(row.value, row.label)}>
                  <Copy className="size-3.5" />
                </Button>
              </div>
            ))}
            <div className="rounded-md border border-border bg-background/60 p-3">
              <div className="text-[10px] uppercase tracking-wide text-faint">curl test</div>
              <div className="mt-1 flex items-start justify-between gap-2">
                <code className="break-all font-mono text-[11px] text-muted">
                  curl -x {httpUrl} https://api.ipify.org
                </code>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  onClick={() => copy(`curl -x ${httpUrl} https://api.ipify.org`, "curl")}
                >
                  <Copy className="size-3.5" />
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Rotation &amp; quota</CardTitle>
              <CardDescription>Applied immediately; persisted in the database.</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <Label>Strategy</Label>
                <NativeSelect
                  value={form.strategy}
                  onChange={(e) => setForm({ ...form, strategy: e.target.value })}
                >
                  <option value="round_robin">round robin</option>
                  <option value="least_used">least used</option>
                  <option value="fastest">fastest</option>
                </NativeSelect>
              </div>
              <div>
                <Label>Quota per proxy (MB, 0 = none)</Label>
                <Input
                  type="number"
                  min={0}
                  value={form.quota_mb}
                  onChange={(e) => setForm({ ...form, quota_mb: Number(e.target.value) })}
                />
              </div>
              <div>
                <Label>Connect timeout (s)</Label>
                <Input
                  type="number"
                  min={1}
                  max={60}
                  value={form.timeout}
                  onChange={(e) => setForm({ ...form, timeout: Number(e.target.value) })}
                />
              </div>
              <div>
                <Label>Failures before dead</Label>
                <Input
                  type="number"
                  min={1}
                  max={10}
                  value={form.max_fails}
                  onChange={(e) => setForm({ ...form, max_fails: Number(e.target.value) })}
                />
              </div>
              <div>
                <Label>SOCKS5 port</Label>
                <Input
                  type="number"
                  min={1}
                  max={65535}
                  value={form.socks_port}
                  onChange={(e) => setForm({ ...form, socks_port: Number(e.target.value) })}
                />
              </div>
              <div>
                <Label>HTTP port</Label>
                <Input
                  type="number"
                  min={1}
                  max={65535}
                  value={form.http_port}
                  onChange={(e) => setForm({ ...form, http_port: Number(e.target.value) })}
                />
              </div>
            </div>
            <div className="flex items-center justify-between pt-1">
              <span className="text-[11px] text-faint">
                Port changes take effect after a stop/start.
              </span>
              <Button size="sm" variant="secondary" onClick={() => save.mutate()} disabled={save.isPending}>
                Save settings
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-3">
        <CardHeader>
          <div>
            <CardTitle className="flex items-center gap-2">
              <Activity className="size-4 text-success" />
              Busiest proxies
            </CardTitle>
            <CardDescription>Traffic relayed through the pool, highest first.</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          {top.length === 0 ? (
            <div className="p-4 text-[12px] text-muted">
              No traffic recorded yet. Start the gateway and send a request through it.
            </div>
          ) : (
            <table className="w-full text-left text-[12px]">
              <thead className="border-y border-border text-[10px] uppercase tracking-wide text-faint">
                <tr>
                  <th className="px-4 py-2 font-medium">Endpoint</th>
                  <th className="px-3 py-2 font-medium">Proto</th>
                  <th className="px-3 py-2 font-medium">Requests</th>
                  <th className="px-3 py-2 font-medium">↓ / ↑</th>
                  <th className="px-3 py-2 font-medium">Quota</th>
                  <th className="px-3 py-2 font-medium">Latency</th>
                </tr>
              </thead>
              <tbody>
                {top.map((row) => {
                  const used = row.bytes_in + row.bytes_out;
                  return (
                    <tr
                      key={`${row.ip}:${row.port}:${row.protocol}`}
                      className="border-b border-border/60 last:border-0"
                    >
                      <td className="px-4 py-2 font-mono text-fg">
                        {row.ip}:{row.port}
                      </td>
                      <td className="px-3 py-2 text-muted">{row.protocol}</td>
                      <td className="px-3 py-2 font-mono text-muted">{row.requests}</td>
                      <td className="px-3 py-2 font-mono text-muted">
                        {fmtBytes(row.bytes_in)} / {fmtBytes(row.bytes_out)}
                      </td>
                      <td className="min-w-32 px-3 py-2">
                        {row.quota_bytes ? (
                          <div className="flex items-center gap-2">
                            <Progress
                              value={pct(used, row.quota_bytes)}
                              className="h-1 w-16"
                              indicatorClassName={
                                used >= row.quota_bytes
                                  ? "from-danger to-danger"
                                  : undefined
                              }
                            />
                            <span className="font-mono text-[10px] text-faint">
                              {pct(used, row.quota_bytes)}%
                            </span>
                          </div>
                        ) : (
                          <span className="text-[10px] text-faint">unlimited</span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono text-muted">{fmtLatency(row.latency_ms)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <div className="mt-3 flex items-center gap-4 text-[11px] text-faint">
        <span className="flex items-center gap-1.5">
          <ArrowDownToLine className="size-3" /> {fmtBytes(data.bytes_in)} in
        </span>
        <span className="flex items-center gap-1.5">
          <ArrowUpFromLine className="size-3" /> {fmtBytes(data.bytes_out)} out
        </span>
        {data.last_error && <span className="text-danger">last error: {data.last_error}</span>}
      </div>
    </div>
  );
}

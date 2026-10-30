import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Cpu,
  Database,
  Globe2,
  KeyRound,
  Layers,
  Loader2,
  ShieldAlert,
  Timer,
  Trash2,
  UserRound,
} from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useLive } from "@/lib/live";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/progress";

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-border/60 py-2.5 last:border-0">
      <span className="text-[12px] text-muted">{label}</span>
      <span className="font-mono text-[12px] text-fg">{value}</span>
    </div>
  );
}

export function SettingsPage() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const { status } = useLive();
  const queryClient = useQueryClient();
  const [purgeOpen, setPurgeOpen] = useState(false);

  const purge = useMutation({
    mutationFn: api.purgeDead,
    onSuccess: (res) => {
      toast.success(`Removed ${res.removed} dead proxies`);
      setPurgeOpen(false);
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const dedupe = useMutation({
    mutationFn: api.dedupe,
    onSuccess: (res) => {
      toast.success(
        res.removed ? `Removed ${res.removed} duplicate listings` : "No duplicates found",
      );
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      queryClient.invalidateQueries({ queryKey: ["proxies"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const data = settings.data;

  return (
    <>
      <PageHeader title="Settings" />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div>
              <CardTitle className="flex items-center gap-2">
                <Cpu className="size-4 text-accent" />
                Validator
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {settings.isLoading ? (
              <Skeleton className="h-28 w-full" />
            ) : (
              <>
                <Row
                  label="Per-check timeout"
                  value={`${data?.validate_timeout ?? "—"} s`}
                />
                <Row
                  label="Concurrency"
                  value={`${data?.validate_concurrency ?? "—"} tasks`}
                />
                <Row
                  label="Failures before dead"
                  value={data?.max_failed_checks ?? "—"}
                />
                <Row label="Candidates / round" value={data?.max_candidates ?? "—"} />
                <Row label="Judges" value="httpbin · ip-api" />
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle className="flex items-center gap-2">
                <Globe2 className="size-4 text-info" />
                Enrichment
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {settings.isLoading ? (
              <Skeleton className="h-28 w-full" />
            ) : (
              <>
                <Row
                  label="Geo enrichment"
                  value={
                    <Badge variant={data?.geo_enrich ? "success" : "default"}>
                      {data?.geo_enrich ? "enabled" : "disabled"}
                    </Badge>
                  }
                />
                <Row label="Batch cap" value={`${data?.geo_max ?? "—"} proxies`} />
                <Row label="Provider" value="ip-api.com (batch)" />
                <Row
                  label="Site check timeout"
                  value={`${data?.site_check_timeout ?? "—"} s`}
                />
                <Row
                  label="Site check default"
                  value={`${data?.site_check_limit ?? "—"} proxies`}
                />
                <Row
                  label="Signup sources"
                  value={
                    data?.signup_sources.length
                      ? data.signup_sources.join(", ")
                      : "none configured"
                  }
                />
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle className="flex items-center gap-2">
                <UserRound className="size-4 text-success" />
                Account
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <Row label="Signed in as" value={me.data?.username ?? "—"} />
            <Row
              label="Role"
              value={
                <Badge variant={me.data?.is_admin ? "accent" : "default"}>
                  {me.data?.is_admin ? "admin" : "member"}
                </Badge>
              }
            />
            <Row label="Session TTL" value="7 days" />
            <Row label="Password hash" value="PBKDF2-SHA256 · 200k" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle className="flex items-center gap-2">
                <Database className="size-4 text-warning" />
                Pool
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <Row label="Alive rows" value={(status?.alive ?? 0).toLocaleString()} />
            <Row label="Dead rows" value={(status?.dead ?? 0).toLocaleString()} />
            <Row
              label="Duplicates"
              value={(stats.data?.totals.duplicates ?? 0).toLocaleString()}
            />
            <Row
              label="Auto dedupe"
              value={
                <Badge variant={settings.data?.auto_dedupe ? "success" : "default"}>
                  {settings.data?.auto_dedupe ? "enabled" : "disabled"}
                </Badge>
              }
            />
            <Row label="Database" value="SQLite · novaproxy.db" />

            <div className="mt-3 flex items-center justify-between rounded-md border border-warning/20 bg-warning/5 p-3">
              <div>
                <div className="flex items-center gap-1.5 text-[12px] font-medium text-warning">
                  <Layers className="size-3.5" />
                  Remove duplicates
                </div>
                <div className="text-[11px] text-muted">Keep the healthiest row per endpoint.</div>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => dedupe.mutate()}
                disabled={dedupe.isPending}
              >
                {dedupe.isPending ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Layers className="size-3.5" />
                )}
                Dedupe
              </Button>
            </div>
            <div className="mt-4 flex items-center justify-between rounded-md border border-danger/20 bg-danger/5 p-3">
              <div>
                <div className="flex items-center gap-1.5 text-[12px] font-medium text-danger">
                  <ShieldAlert className="size-3.5" />
                  Danger zone
                </div>
                <div className="text-[11px] text-muted">Delete every proxy marked dead.</div>
              </div>
              <Button variant="danger" size="sm" onClick={() => setPurgeOpen(true)}>
                <Trash2 className="size-3.5" />
                Purge
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader>
          <div>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="size-4 text-muted" />
              Config
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 text-[12px] text-muted sm:grid-cols-2">
            <div className="rounded-md border border-border bg-background/40 p-3">
              <div className="font-mono text-[11px] text-fg">app/config.py</div>
              <div className="mt-1 text-faint">timeouts · concurrency · geo · signup</div>
            </div>
            <div className="rounded-md border border-border bg-background/40 p-3">
              <div className="font-mono text-[11px] text-fg">NP_DB · NP_ADMIN_USER · NP_ADMIN_PASS</div>
              <div className="mt-1 flex items-center gap-1.5 text-faint">
                <Timer className="size-3" />
                read at boot
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Dialog
        open={purgeOpen}
        onOpenChange={setPurgeOpen}
        title="Purge dead proxies?"
        description="Delete all rows marked dead. This cannot be undone."
        footer={
          <>
            <Button variant="ghost" onClick={() => setPurgeOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={() => purge.mutate()} disabled={purge.isPending}>
              {purge.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Trash2 className="size-4" />
              )}
              Purge dead
            </Button>
          </>
        }
      >
        <div className="rounded-md border border-warning/20 bg-warning/5 p-3 text-[12px] text-warning">
          {status?.dead ?? 0} dead rows will be deleted. The engine will re-add any that validate
          again later.
        </div>
      </Dialog>
    </>
  );
}

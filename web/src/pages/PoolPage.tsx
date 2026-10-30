import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  ChevronLeft,
  ChevronRight,
  Copy,
  FileJson,
  Filter,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  Square,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useLive } from "@/lib/live";
import type { ProxyRow } from "@/lib/types";
import { cn, fmtLatency, fmtTime } from "@/lib/utils";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Input, NativeSelect } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const PAGE_SIZE = 50;

const ANON_TONE: Record<string, "success" | "accent" | "warning" | "default"> = {
  elite: "success",
  anonymous: "accent",
  transparent: "warning",
  unknown: "default",
};

function latencyTone(ms: number | null) {
  if (ms == null) return "text-faint";
  if (ms < 400) return "text-success";
  if (ms < 1000) return "text-fg";
  if (ms < 2000) return "text-warning";
  return "text-danger";
}

function Row({ proxy }: { proxy: ProxyRow }) {
  const [copied, setCopied] = useState(false);
  const address = `${proxy.protocol}://${proxy.ip}:${proxy.port}`;

  const copy = () => {
    navigator.clipboard.writeText(address).then(() => {
      setCopied(true);
      toast.success("Copied", { description: address });
      setTimeout(() => setCopied(false), 1200);
    });
  };

  return (
    <TableRow className="group">
      <TableCell>
        <button
          onClick={copy}
          className="flex items-center gap-2 font-mono text-[12.5px] text-fg hover:text-accent"
          title={`Copy ${address}`}
        >
          {proxy.ip}
          <span className="text-faint">:</span>
          {proxy.port}
          <Copy
            className={cn(
              "size-3 text-faint opacity-0 transition-opacity group-hover:opacity-100",
              copied && "text-success opacity-100",
            )}
          />
        </button>
      </TableCell>
      <TableCell>
        <Badge variant="outline" className="font-mono uppercase">
          {proxy.protocol}
        </Badge>
      </TableCell>
      <TableCell className="hidden sm:table-cell">
        <Badge variant={ANON_TONE[proxy.anonymity] ?? "default"} className="capitalize">
          {proxy.anonymity}
        </Badge>
      </TableCell>
      <TableCell className={cn("font-mono", latencyTone(proxy.latency_ms))}>
        {fmtLatency(proxy.latency_ms)}
      </TableCell>
      <TableCell className="hidden sm:table-cell">
        {proxy.https ? (
          <ShieldCheck className="size-4 text-success" />
        ) : (
          <span className="text-faint">—</span>
        )}
      </TableCell>
      <TableCell className="hidden sm:table-cell">
        <div className="flex items-center gap-2">
          {proxy.country_code ? (
            <span className="rounded bg-elevated px-1.5 py-0.5 font-mono text-[10px] text-muted">
              {proxy.country_code}
            </span>
          ) : (
            <span className="text-faint">—</span>
          )}
          <span className="truncate text-[12px] text-muted">
            {proxy.country ?? proxy.isp ?? "unknown"}
          </span>
        </div>
      </TableCell>
      <TableCell className="hidden text-[12px] text-muted lg:table-cell">
        {proxy.isp ?? "—"}
      </TableCell>
      <TableCell className="hidden whitespace-nowrap text-[11px] text-faint xl:table-cell">
        {fmtTime(proxy.last_checked)}
      </TableCell>
    </TableRow>
  );
}

export function PoolPage() {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [protocol, setProtocol] = useState("");
  const [country, setCountry] = useState("");
  const [anonymity, setAnonymity] = useState("");
  const [sort, setSort] = useState("latency");
  const [offset, setOffset] = useState(0);
  const [purgeOpen, setPurgeOpen] = useState(false);
  const queryClient = useQueryClient();
  const { status } = useLive();
  const rechecking = status?.recheck_running ?? false;
  const recheckDone = status?.recheck_done ?? 0;
  const recheckTotal = status?.recheck_total ?? 0;

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => setOffset(0), [debounced, protocol, country, anonymity, sort]);

  const filters = useMemo(
    () => ({
      q: debounced || undefined,
      protocol: protocol || undefined,
      country: country || undefined,
      anonymity: anonymity || undefined,
      sort,
      offset,
      limit: PAGE_SIZE,
    }),
    [debounced, protocol, country, anonymity, sort, offset],
  );

  const proxiesQuery = useQuery({
    queryKey: ["proxies", filters],
    queryFn: () => api.proxies(filters),
    placeholderData: keepPreviousData,
    refetchInterval: rechecking ? 4000 : false,
  });

  const recheck = useMutation({
    mutationFn: api.recheck,
    onSuccess: (res) => {
      if (!res.ok) {
        toast.error(res.error ?? "Engine busy");
        return;
      }
      toast.success("Recheck started", { description: "Alive proxies are being revalidated." });
      queryClient.invalidateQueries({ queryKey: ["proxies"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const purge = useMutation({
    mutationFn: api.purgeDead,
    onSuccess: (res) => {
      toast.success(`Removed ${res.removed} dead proxies`);
      setPurgeOpen(false);
      queryClient.invalidateQueries({ queryKey: ["proxies"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const stop = useMutation({
    mutationFn: api.stop,
    onSuccess: () => toast.message("Stopping…"),
    onError: (error: Error) => toast.error(error.message),
  });

  const total = proxiesQuery.data?.total ?? 0;
  const rows = proxiesQuery.data?.proxies ?? [];
  const countries = proxiesQuery.data?.countries ?? [];
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasFilters = Boolean(debounced || protocol || country || anonymity);

  return (
    <>
      <PageHeader
        title="Pool"
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => proxiesQuery.refetch()}>
              <RefreshCw className={cn("size-3.5", proxiesQuery.isFetching && "animate-spin")} />
              Refresh
            </Button>
            <Button variant="secondary" size="sm" onClick={() => recheck.mutate()} disabled={rechecking}>
              {rechecking ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <ShieldCheck className="size-3.5" />
              )}
              {rechecking ? `${recheckDone}/${recheckTotal}` : "Recheck"}
            </Button>
            {rechecking && (
              <Button
                variant="danger"
                size="sm"
                onClick={() => stop.mutate()}
                disabled={stop.isPending}
              >
                <Square className="size-3.5" />
                Stop
              </Button>
            )}
            <Button variant="outline" size="sm" asChild>
              <a href={api.exportUrl("txt", protocol || undefined)} download>
                <ArrowDownToLine className="size-3.5" />
                .txt
              </a>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <a href={api.exportUrl("json", protocol || undefined)} download>
                <FileJson className="size-3.5" />
                .json
              </a>
            </Button>
          </>
        }
      />

      <div className="rounded-lg border border-border bg-panel/70">
        <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-faint" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search IP, ISP or country…"
              className="h-8 pl-8 text-[13px]"
            />
          </div>

          <NativeSelect
            value={protocol}
            onChange={(e) => setProtocol(e.target.value)}
            className="h-8 w-32 text-[13px]"
          >
            <option value="">All protocols</option>
            <option value="http">HTTP</option>
            <option value="socks4">SOCKS4</option>
            <option value="socks5">SOCKS5</option>
          </NativeSelect>

          <NativeSelect
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            className="h-8 w-32 text-[13px]"
          >
            <option value="">All countries</option>
            {countries.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </NativeSelect>

          <NativeSelect
            value={anonymity}
            onChange={(e) => setAnonymity(e.target.value)}
            className="h-8 w-32 text-[13px]"
          >
            <option value="">Any anonymity</option>
            <option value="elite">Elite</option>
            <option value="anonymous">Anonymous</option>
            <option value="transparent">Transparent</option>
          </NativeSelect>

          <NativeSelect
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="h-8 w-36 text-[13px]"
          >
            <option value="latency">Fastest first</option>
            <option value="last_checked">Recently checked</option>
            <option value="country">Country A–Z</option>
            <option value="port">Port</option>
          </NativeSelect>

          {hasFilters && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setQuery("");
                setProtocol("");
                setCountry("");
                setAnonymity("");
              }}
            >
              <Filter className="size-3.5" />
              Clear
            </Button>
          )}

          <div className="ml-auto flex items-center gap-3 text-[11px] text-faint">
            <span className="font-mono">{total.toLocaleString()} rows</span>
            <Button variant="danger" size="sm" onClick={() => setPurgeOpen(true)}>
              <Trash2 className="size-3.5" />
              Purge dead
            </Button>
          </div>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Endpoint</TableHead>
              <TableHead>Proto</TableHead>
              <TableHead className="hidden sm:table-cell">Anonymity</TableHead>
              <TableHead>Latency</TableHead>
              <TableHead className="hidden sm:table-cell">HTTPS</TableHead>
              <TableHead className="hidden sm:table-cell">Country</TableHead>
              <TableHead className="hidden lg:table-cell">ISP</TableHead>
              <TableHead className="hidden xl:table-cell">Checked</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {proxiesQuery.isLoading &&
              Array.from({ length: 8 }, (_, i) => (
                <TableRow key={i}>
                  <TableCell colSpan={8}>
                    <Skeleton className="h-5 w-full" />
                  </TableCell>
                </TableRow>
              ))}

            {!proxiesQuery.isLoading && rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={8}>
                  <div className="py-16 text-center">
                    <div className="text-sm text-fg">No proxies found.</div>
                    <div className="mt-1 text-[12px] text-faint">
                      {hasFilters ? "Clear the filters." : "Run a collection first."}
                    </div>
                  </div>
                </TableCell>
              </TableRow>
            )}

            {rows.map((proxy) => (
              <Row key={`${proxy.ip}:${proxy.port}:${proxy.protocol}`} proxy={proxy} />
            ))}
          </TableBody>
        </Table>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-3 py-2 text-[11px] text-faint">
          <span>
            Showing{" "}
            <span className="font-mono text-muted">
              {total === 0 ? 0 : offset + 1}–{Math.min(offset + PAGE_SIZE, total)}
            </span>{" "}
            of <span className="font-mono text-muted">{total.toLocaleString()}</span>
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="icon-sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              <ChevronLeft className="size-3.5" />
            </Button>
            <span className="font-mono">
              {page} / {pages}
            </span>
            <Button
              variant="secondary"
              size="icon-sm"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              <ChevronRight className="size-3.5" />
            </Button>
            {proxiesQuery.isFetching && <Loader2 className="size-3.5 animate-spin" />}
          </div>
        </div>
      </div>

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
          Dead rows failed 3 consecutive checks. They return if they validate again.
        </div>
      </Dialog>
    </>
  );
}

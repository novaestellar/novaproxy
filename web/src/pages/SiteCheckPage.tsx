import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Globe2, Loader2, Play, ScanSearch, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { SiteCheckRow } from "@/lib/types";
import { cn, fmtLatency, fmtTime } from "@/lib/utils";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, NativeSelect } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function ResultRow({ row }: { row: SiteCheckRow }) {
  return (
    <TableRow>
      <TableCell>
        <span className="font-mono text-[12.5px] text-fg">
          {row.ip}:{row.port}
        </span>
      </TableCell>
      <TableCell>
        <Badge variant="outline" className="font-mono uppercase">
          {row.protocol}
        </Badge>
      </TableCell>
      <TableCell className="hidden sm:table-cell">
        {row.country_code ? (
          <span className="rounded bg-elevated px-1.5 py-0.5 font-mono text-[10px] text-muted">
            {row.country_code}
          </span>
        ) : (
          <span className="text-faint">—</span>
        )}
      </TableCell>
      <TableCell className="hidden font-mono text-[12px] text-muted sm:table-cell">
        {row.status ?? "—"}
      </TableCell>
      <TableCell className={cn("font-mono", row.ok ? "text-success" : "text-faint")}>
        {fmtLatency(row.latency_ms)}
      </TableCell>
      <TableCell>
        {row.ok ? (
          <Badge variant="success">
            <CheckCircle2 className="size-3" />
            passed
          </Badge>
        ) : (
          <Badge variant="danger">
            <XCircle className="size-3" />
            failed
          </Badge>
        )}
      </TableCell>
      <TableCell className="hidden max-w-56 truncate text-[11px] text-faint lg:table-cell" title={row.error ?? ""}>
        {row.error ?? "—"}
      </TableCell>
      <TableCell className="hidden whitespace-nowrap text-[11px] text-faint xl:table-cell">
        {fmtTime(row.checked_at)}
      </TableCell>
    </TableRow>
  );
}

export function SiteCheckPage() {
  const [url, setUrl] = useState("https://example.com");
  const [protocol, setProtocol] = useState("");
  const [limit, setLimit] = useState(50);

  const test = useMutation({
    mutationFn: () =>
      api.testProxies({
        url: url.trim(),
        protocol: protocol || undefined,
        limit,
      }),
    onSuccess: (data) => {
      toast.success(`${data.passed}/${data.total} proxies reached the target`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const data = test.data;
  const valid = /^https?:\/\/\S+$/i.test(url.trim());

  return (
    <>
      <PageHeader
        title="Site check"
        actions={
          <Button onClick={() => test.mutate()} disabled={!valid || test.isPending}>
            {test.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Play className="size-3.5" />
            )}
            Run check
          </Button>
        }
      />

      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-64 flex-1">
              <Globe2 className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-faint" />
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com"
                className="pl-8 font-mono text-[13px]"
                spellCheck={false}
              />
            </div>
            <NativeSelect
              value={protocol}
              onChange={(e) => setProtocol(e.target.value)}
              className="w-36"
            >
              <option value="">All protocols</option>
              <option value="http">HTTP</option>
              <option value="socks4">SOCKS4</option>
              <option value="socks5">SOCKS5</option>
            </NativeSelect>
            <NativeSelect
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="w-28"
            >
              {[25, 50, 100, 200].map((n) => (
                <option key={n} value={n}>
                  {n} proxies
                </option>
              ))}
            </NativeSelect>
          </div>
        </CardContent>
      </Card>

      {data && (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ["Passed", data.passed.toLocaleString(), "text-success"],
            ["Failed", data.failed.toLocaleString(), "text-danger"],
            ["Avg latency", data.avg_latency_ms ? `${data.avg_latency_ms}ms` : "—", "text-fg"],
            ["Tested", data.total.toLocaleString(), "text-fg"],
          ].map(([label, value, tone]) => (
            <div key={label} className="rounded-lg border border-border bg-panel/70 px-3 py-2.5">
              <div className="text-[10px] uppercase tracking-wider text-faint">{label}</div>
              <div className={cn("mt-1 font-mono text-[15px]", tone)}>{value}</div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-panel/70">
        <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
          <div className="flex items-center gap-2 text-[12px] text-muted">
            <ScanSearch className="size-3.5 text-accent" />
            {data ? data.url : "Results"}
          </div>
          <span className="font-mono text-[11px] text-faint">
            {data ? `${data.results.length} rows` : "no run yet"}
          </span>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Endpoint</TableHead>
              <TableHead>Proto</TableHead>
              <TableHead className="hidden sm:table-cell">Country</TableHead>
              <TableHead className="hidden sm:table-cell">Status</TableHead>
              <TableHead>Latency</TableHead>
              <TableHead>Result</TableHead>
              <TableHead className="hidden lg:table-cell">Error</TableHead>
              <TableHead className="hidden xl:table-cell">Checked</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {test.isPending && (
              <TableRow>
                <TableCell colSpan={8}>
                  <div className="flex items-center justify-center gap-2 py-14 text-[12px] text-faint">
                    <Loader2 className="size-3.5 animate-spin" />
                    Testing {limit} proxies against {url.trim()}…
                  </div>
                </TableCell>
              </TableRow>
            )}

            {!test.isPending && data?.results.map((row) => (
              <ResultRow key={`${row.ip}:${row.port}:${row.protocol}`} row={row} />
            ))}

            {!test.isPending && !data && (
              <TableRow>
                <TableCell colSpan={8}>
                  <div className="flex flex-col items-center gap-2 py-16 text-center">
                    <ScanSearch className="size-6 text-faint" />
                    <div className="text-sm text-fg">No checks yet</div>
                    <div className="text-[12px] text-faint">
                      Enter a URL and run a check against the alive pool.
                    </div>
                  </div>
                </TableCell>
              </TableRow>
            )}

            {!test.isPending && data && data.results.length === 0 && (
              <TableRow>
                <TableCell colSpan={8}>
                  <div className="py-16 text-center text-sm text-muted">
                    No alive proxies for this filter.
                  </div>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </>
  );
}

import { useMutation } from "@tanstack/react-query";
import { ClipboardCopy, Download, Loader2, Square, Terminal } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useLive } from "@/lib/live";
import { fmtDuration } from "@/lib/utils";
import { PageHeader } from "@/components/PageHeader";
import { LogConsole } from "@/components/LogConsole";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export function LogsPage() {
  const { status, connected } = useLive();
  const logs = status?.logs ?? [];
  const running = status?.running ?? false;

  const stop = useMutation({
    mutationFn: api.stop,
    onSuccess: () => toast.message("Stop requested"),
    onError: (error: Error) => toast.error(error.message),
  });

  const dump = logs.map((line) => `[${line.ts}] ${line.level.toUpperCase()} ${line.msg}`).join("\n");

  const copyAll = () => {
    navigator.clipboard.writeText(dump).then(
      () => toast.success(`Copied ${logs.length} lines`),
      () => toast.error("Clipboard unavailable"),
    );
  };

  const download = () => {
    const blob = new Blob([dump], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `novaproxy-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.log`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const counts = logs.reduce<Record<string, number>>((acc, line) => {
    acc[line.level] = (acc[line.level] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <>
      <PageHeader
        title="Logs"
        actions={
          <>
            <Badge variant={connected ? "success" : "danger"}>
              <Terminal className="size-3" />
              {connected ? "SSE connected" : "reconnecting"}
            </Badge>
            {running && (
              <Button variant="danger" size="sm" onClick={() => stop.mutate()}>
                <Square className="size-3.5" />
                Stop
              </Button>
            )}
          </>
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Phase", status?.phase ?? "idle"],
          ["Round", running ? `${status?.round}/${status?.rounds}` : "—"],
          ["Checked", (status?.checked ?? 0).toLocaleString()],
          ["Elapsed", running ? fmtDuration(status?.elapsed_s ?? 0) : "—"],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg border border-border bg-panel/70 px-3 py-2.5">
            <div className="text-[10px] uppercase tracking-wider text-faint">{label}</div>
            <div className="mt-1 truncate font-mono text-[13px] text-fg">{value}</div>
          </div>
        ))}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-3 text-[11px] text-faint">
        <span className="font-mono">{logs.length} buffered</span>
        {["info", "ok", "warn", "error"].map((level) =>
          counts[level] ? (
            <span key={level} className="font-mono">
              {level} <span className="text-muted">{counts[level]}</span>
            </span>
          ) : null,
        )}
        <div className="ml-auto flex gap-2">
          <Button variant="secondary" size="sm" onClick={copyAll} disabled={logs.length === 0}>
            <ClipboardCopy className="size-3.5" />
            Copy
          </Button>
          <Button variant="outline" size="sm" onClick={download} disabled={logs.length === 0}>
            <Download className="size-3.5" />
            Download
          </Button>
        </div>
      </div>

      <LogConsole logs={logs} height="calc(100vh - 340px)" />

      <div className="mt-3 flex items-center gap-2 text-[11px] text-faint">
        {running && <Loader2 className="size-3 animate-spin text-success" />}
        {running
          ? `${status?.phase} · ${status?.found_new} new`
          : status?.message || "Idle."}
      </div>
    </>
  );
}

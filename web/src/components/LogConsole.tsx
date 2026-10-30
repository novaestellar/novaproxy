import { useEffect, useRef, useState } from "react";
import { Search, ArrowDownToLine, Pause, Play } from "lucide-react";
import type { LogLine } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

const LEVELS = ["all", "info", "ok", "warn", "error"] as const;
type Level = (typeof LEVELS)[number];

const LEVEL_STYLE: Record<string, string> = {
  info: "text-muted",
  ok: "text-success",
  warn: "text-warning",
  error: "text-danger",
};

function timeOf(ts: string) {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString(undefined, { hour12: false });
}

export function LogConsole({
  logs,
  height = "20rem",
  compact = false,
}: {
  logs: LogLine[];
  height?: string;
  compact?: boolean;
}) {
  const [level, setLevel] = useState<Level>("all");
  const [query, setQuery] = useState("");
  const [follow, setFollow] = useState(true);
  const scroller = useRef<HTMLDivElement>(null);

  const filtered = logs.filter((line) => {
    if (level !== "all" && line.level !== level) return false;
    if (query && !line.msg.toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  });

  useEffect(() => {
    if (!follow) return;
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [filtered.length, follow]);

  return (
    <div className="flex flex-col overflow-hidden rounded-lg border border-border bg-[#080a0d]">
      {!compact && (
        <div className="flex flex-wrap items-center gap-2 border-b border-border bg-panel/60 px-3 py-2">
          <div className="flex items-center gap-1">
            {LEVELS.map((l) => (
              <button
                key={l}
                onClick={() => setLevel(l)}
                className={cn(
                  "rounded px-2 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors",
                  level === l
                    ? "bg-elevated text-fg"
                    : "text-faint hover:bg-elevated/60 hover:text-muted",
                )}
              >
                {l}
              </button>
            ))}
          </div>
          <div className="relative ml-auto w-56">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-faint" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter messages…"
              className="h-7 pl-8 text-xs"
            />
          </div>
          <button
            onClick={() => setFollow((f) => !f)}
            className={cn(
              "flex items-center gap-1.5 rounded px-2 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors",
              follow ? "bg-success/10 text-success" : "bg-elevated text-muted",
            )}
            title={follow ? "Following output" : "Paused"}
          >
            {follow ? <Pause className="size-3" /> : <Play className="size-3" />}
            follow
          </button>
          <button
            onClick={() => {
              const el = scroller.current;
              if (el) el.scrollTop = el.scrollHeight;
            }}
            className="rounded p-1 text-faint transition-colors hover:bg-elevated hover:text-fg"
            title="Jump to latest"
          >
            <ArrowDownToLine className="size-3.5" />
          </button>
        </div>
      )}

      <div
        ref={scroller}
        style={{ height }}
        className="overflow-y-auto px-3 py-2 font-mono text-[11.5px] leading-relaxed"
        onScroll={(e) => {
          const el = e.currentTarget;
          const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
          if (!atBottom && follow) setFollow(false);
        }}
      >
        {filtered.length === 0 && (
          <div className="py-10 text-center text-[11px] text-faint">
            {logs.length === 0 ? "Waiting for engine output…" : "No lines match this filter."}
          </div>
        )}
        {filtered.map((line, index) => (
          <div key={`${line.ts}-${index}`} className="flex gap-2 whitespace-pre-wrap break-words">
            <span className="shrink-0 text-[#3d4453]">{timeOf(line.ts)}</span>
            <span className={cn("shrink-0 uppercase", LEVEL_STYLE[line.level] ?? "text-muted")}>
              {line.level.padEnd(5, " ")}
            </span>
            <span className="text-[#c3c9d4]">{line.msg}</span>
          </div>
        ))}
      </div>

      {!compact && (
        <div className="flex items-center justify-between border-t border-border bg-panel/60 px-3 py-1.5 text-[10px] text-faint">
          <span>
            {filtered.length} / {logs.length} lines
          </span>
          <Badge variant={follow ? "success" : "warning"}>
            {follow ? "streaming" : "paused"}
          </Badge>
        </div>
      )}
    </div>
  );
}

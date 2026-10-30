import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, Square } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useLive } from "@/lib/live";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input, Label, NativeSelect } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

const PROTOCOLS = [
  { id: "http", label: "HTTP" },
  { id: "socks4", label: "SOCKS4" },
  { id: "socks5", label: "SOCKS5" },
];

export function CollectDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { status } = useLive();
  const [target, setTarget] = useState(100);
  const [rounds, setRounds] = useState(3);
  const [protocols, setProtocols] = useState<string[]>(["http", "socks5"]);
  const [useCustom, setUseCustom] = useState(true);
  const queryClient = useQueryClient();

  const running = status?.running ?? false;

  const start = useMutation({
    mutationFn: () => api.collect({ target, protocols, rounds, use_custom: useCustom }),
    onSuccess: (res) => {
      if (!res.ok) {
        toast.error(res.error ?? "Engine is already running");
        return;
      }
      toast.success(`Harvest started — target ${target} alive proxies`);
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      onOpenChange(false);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const stop = useMutation({
    mutationFn: api.stop,
    onSuccess: () => toast.message("Stop requested — finishing current checks"),
    onError: (error: Error) => toast.error(error.message),
  });

  const toggleProtocol = (id: string) => {
    setProtocols((current) =>
      current.includes(id) ? current.filter((p) => p !== id) : [...current, id],
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={running ? "Collection running" : "New collection"}
      description={
        running
          ? `Round ${status?.round}/${status?.rounds} · ${status?.phase}`
          : "Validate candidates until the target is met."
      }
      footer={
        running ? (
          <>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Close
            </Button>
            <Button variant="danger" onClick={() => stop.mutate()} disabled={stop.isPending}>
              <Square className="size-3.5" />
              Stop
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => start.mutate()}
              disabled={protocols.length === 0 || start.isPending}
            >
              {start.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Play className="size-4" />
              )}
              Start collecting
            </Button>
          </>
        )
      }
    >
      {running && status ? (
        <div className="grid grid-cols-2 gap-3 text-sm">
          {[
            ["Phase", status.phase],
            ["Round", `${status.round} / ${status.rounds}`],
            ["Alive", `${status.alive} / ${status.target}`],
            ["Checked", status.checked.toLocaleString()],
          ].map(([label, value]) => (
            <div key={label} className="rounded-md border border-border bg-background/50 p-3">
              <div className="text-[10px] uppercase tracking-wider text-faint">{label}</div>
              <div className="mt-1 font-mono text-[13px] text-fg">{value}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="target">Target alive count</Label>
              <Input
                id="target"
                type="number"
                min={1}
                max={50000}
                value={target}
                onChange={(e) => setTarget(Math.max(1, Number(e.target.value) || 1))}
              />
            </div>
            <div>
              <Label htmlFor="rounds">Max rounds</Label>
              <NativeSelect
                id="rounds"
                value={rounds}
                onChange={(e) => setRounds(Number(e.target.value))}
              >
                {Array.from({ length: 10 }, (_, i) => i + 1).map((r) => (
                  <option key={r} value={r}>
                    {r} round{r > 1 ? "s" : ""}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>

          <div>
            <Label>Protocols</Label>
            <div className="grid grid-cols-3 gap-2">
              {PROTOCOLS.map(({ id, label }) => {
                const active = protocols.includes(id);
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => toggleProtocol(id)}
                    className={cn(
                      "rounded-md border p-2.5 text-left transition-colors",
                      active
                        ? "border-accent/50 bg-accent/10"
                        : "border-border bg-background/40 hover:border-border-strong",
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-medium text-fg">{label}</span>
                      <span
                        className={cn(
                          "size-2 rounded-full",
                          active ? "bg-accent" : "bg-border-strong",
                        )}
                      />
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex items-center justify-between rounded-md border border-border bg-background/40 p-3">
            <div className="text-[12px] text-fg">Signup-gated sources</div>
            <Switch checked={useCustom} onCheckedChange={setUseCustom} />
          </div>
        </div>
      )}
    </Dialog>
  );
}

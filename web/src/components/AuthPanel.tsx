import type { ReactNode } from "react";
import { Activity, Gauge, ShieldCheck, Zap } from "lucide-react";

const FEATURES = [
  { icon: Zap, title: "Quota loop", text: "Rounds until target" },
  { icon: ShieldCheck, title: "Two judges", text: "Live validation" },
  { icon: Gauge, title: "300 concurrent", text: "Parallel checks" },
];

export function AuthPanel({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      <aside className="relative hidden overflow-hidden border-r border-border bg-surface p-10 lg:flex lg:flex-col">
        <div className="pointer-events-none absolute inset-0 grid-noise opacity-60" />
        <div className="pointer-events-none absolute -left-24 top-1/3 size-[420px] rounded-full bg-accent/10 blur-[120px]" />
        <div className="pointer-events-none absolute -right-24 bottom-0 size-[320px] rounded-full bg-info/10 blur-[100px]" />

        <div className="relative flex items-center gap-2.5">
          <div className="grid size-9 place-items-center rounded-lg bg-gradient-to-br from-accent to-info text-base font-bold text-white shadow-lg shadow-accent/25">
            P
          </div>
          <div>
            <div className="text-[15px] font-semibold tracking-tight">novaproxy</div>
          </div>
        </div>

        <div className="relative mt-auto max-w-md">
          <h1 className="text-balance text-3xl font-semibold leading-tight tracking-tight">
            Fresh proxies,
            <br />
            <span className="bg-gradient-to-r from-accent to-info bg-clip-text text-transparent">
              validated.
            </span>
          </h1>

          <div className="mt-8 space-y-3">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <div key={title} className="flex items-center gap-3">
                <div className="grid size-7 place-items-center rounded-md border border-border bg-panel text-accent">
                  <Icon className="size-3.5" />
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-[13px] font-medium text-fg">{title}</span>
                  <span className="text-[11px] text-faint">{text}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="relative mt-10 flex items-center gap-4 border-t border-border pt-5 text-[11px] text-faint">
          <span className="flex items-center gap-1.5">
            <Activity className="size-3.5 text-success" />
            SQLite · dedupe · health
          </span>
        </div>
      </aside>

      <main className="flex items-center justify-center px-5 py-12">
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  );
}

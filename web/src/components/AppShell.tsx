import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Globe2,
  LayoutDashboard,
  LogOut,
  Network,
  Play,
  ScanSearch,
  Settings2,
  Terminal,
  WifiOff,
} from "lucide-react";
import { api } from "@/lib/api";
import { useLive } from "@/lib/live";
import type { Me } from "@/lib/types";
import { cn, fmtDuration, pct } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { CollectDialog } from "@/components/CollectDialog";
import { toast } from "sonner";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/pool", label: "Pool", icon: Globe2 },
  { to: "/gateway", label: "Gateway", icon: Network },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/check", label: "Site check", icon: ScanSearch },
  { to: "/logs", label: "Logs", icon: Terminal },
  { to: "/settings", label: "Settings", icon: Settings2 },
];

function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-accent to-info text-[15px] font-bold text-white shadow-lg shadow-accent/20">
        P
      </div>
      <div className="leading-none">
        <div className="text-[15px] font-semibold tracking-tight">NovaProxy</div>
      </div>
    </div>
  );
}

function EnginePill() {
  const { status, connected } = useLive();
  const running = status?.running ?? false;

  if (!connected) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-danger/20 bg-danger/5 px-2.5 py-2 text-[11px] text-danger">
        <WifiOff className="size-3.5" />
        offline
      </div>
    );
  }

  if (!running && !status?.recheck_running) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-border bg-background/60 px-2.5 py-2 text-[11px]">
        <span className="size-1.5 rounded-full bg-faint" />
        <span className="text-muted">Idle</span>
      </div>
    );
  }

  if (status?.recheck_running) {
    return (
      <div className="rounded-md border border-border bg-background/60 p-2.5">
        <div className="flex items-center gap-2 text-[11px]">
          <span className="size-1.5 rounded-full bg-info live-dot" />
          <span className="text-info">Rechecking</span>
          <span className="ml-auto font-mono text-[10px] text-faint">
            {status.recheck_done}/{status.recheck_total}
          </span>
        </div>
        <Progress
          value={pct(status.recheck_done, status.recheck_total)}
          className="mt-2 h-1"
          indicatorClassName="from-info to-info"
        />
      </div>
    );
  }

  if (!status) return null;

  return (
    <div className="rounded-md border border-border bg-background/60 p-2.5">
      <div className="flex items-center gap-2 text-[11px]">
        <span className="size-1.5 rounded-full bg-success live-dot" />
        <span className="text-success">Running</span>
        <span className="ml-auto font-mono text-[10px] text-faint">
          R{status.round}/{status.rounds}
        </span>
      </div>
      <div className="mt-1.5 flex items-baseline justify-between font-mono text-[11px]">
        <span className="text-fg">
          {status.alive.toLocaleString()}
          <span className="text-faint"> / {status.target.toLocaleString()}</span>
        </span>
        <span className="text-[10px] text-faint">{fmtDuration(status.elapsed_s)}</span>
      </div>
      <Progress value={pct(status.alive, status.target)} className="mt-1.5 h-1" />
      <div className="mt-1 flex justify-between text-[10px] text-faint">
        <span>{status.checked.toLocaleString()} checked</span>
        <span>{status.found_new.toLocaleString()} new</span>
      </div>
    </div>
  );
}

export function AppShell({ me, children }: { me: Me; children: ReactNode }) {
  const [collectOpen, setCollectOpen] = useState(false);
  const { status } = useLive();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const location = useLocation();

  useEffect(() => {
    const match = NAV.find((item) =>
      item.end ? location.pathname === item.to : location.pathname.startsWith(item.to),
    );
    document.title = `${match?.label ?? "Console"} · NovaProxy`;
  }, [location.pathname]);

  const logout = async () => {
    try {
      await api.logout();
    } finally {
      queryClient.clear();
      navigate("/login", { replace: true });
    }
  };

  const copyKey = () => {
    const text = `alive ${status?.alive ?? 0} · dead ${status?.dead ?? 0}`;
    navigator.clipboard.writeText(text).then(
      () => toast.success("Pool summary copied"),
      () => toast.error("Clipboard unavailable"),
    );
  };

  return (
    <div className="min-h-full">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-border bg-surface/80 px-3 py-4 backdrop-blur lg:flex">
        <div className="px-2">
          <Brand />
        </div>

        <div className="mt-6 px-2">
          <Button className="w-full justify-start" onClick={() => setCollectOpen(true)}>
            <Play className="size-3.5" />
            New collection
          </Button>
        </div>

        <nav className="mt-5 space-y-0.5">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] text-muted transition-colors",
                  "hover:bg-elevated/70 hover:text-fg",
                  isActive && "bg-elevated text-fg shadow-[inset_0_0_0_1px_var(--color-border)]",
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto space-y-3">
          <button
            onClick={copyKey}
            className="flex w-full items-center justify-between rounded-md border border-border bg-background/60 px-2.5 py-2 text-left text-[11px] text-muted transition-colors hover:border-border-strong hover:text-fg"
          >
            <span className="flex items-center gap-2">
              <Activity className="size-3.5 text-success" />
              <span className="font-mono">{status?.alive ?? 0} alive</span>
            </span>
            <ArrowUpRight className="size-3" />
          </button>
          <EnginePill />
          <div className="flex items-center gap-2 rounded-md border border-border bg-background/60 px-2 py-2">
            <div className="grid size-6 place-items-center rounded-full bg-accent/15 text-[10px] font-semibold uppercase text-accent">
              {me.username.slice(0, 2)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12px] text-fg">{me.username}</div>
              <div className="text-[10px] text-faint">{me.is_admin ? "admin" : "member"}</div>
            </div>
            <button
              onClick={logout}
              className="rounded p-1 text-faint transition-colors hover:bg-elevated hover:text-danger"
              title="Sign out"
            >
              <LogOut className="size-3.5" />
            </button>
          </div>
        </div>
      </aside>

      <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-border bg-background/80 px-4 py-3 backdrop-blur lg:hidden relative">
        <Brand />
        <div className="ml-auto flex items-center gap-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "rounded-md p-2 text-muted hover:bg-elevated hover:text-fg",
                  isActive && "bg-elevated text-fg",
                )
              }
              title={label}
            >
              <Icon className="size-4" />
            </NavLink>
          ))}
          <Button size="icon-sm" onClick={() => setCollectOpen(true)}>
            <Play className="size-3.5" />
          </Button>
          <button
            onClick={logout}
            className="rounded-md p-2 text-muted hover:bg-elevated hover:text-danger"
            title="Sign out"
          >
            <LogOut className="size-4" />
          </button>
        </div>
        {status?.running && (
          <div className="absolute inset-x-0 bottom-0 h-0.5 bg-elevated">
            <div
              className="h-full bg-accent transition-[width] duration-500"
              style={{ width: `${pct(status.alive, status.target)}%` }}
            />
          </div>
        )}
        {status?.recheck_running && (
          <div className="absolute inset-x-0 bottom-0 h-0.5 bg-elevated">
            <div
              className="h-full bg-info transition-[width] duration-500"
              style={{ width: `${pct(status.recheck_done, status.recheck_total)}%` }}
            />
          </div>
        )}
      </header>

      <main className="lg:pl-60">
        <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">{children}</div>
      </main>

      <CollectDialog open={collectOpen} onOpenChange={setCollectOpen} />
    </div>
  );
}

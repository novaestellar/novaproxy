import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  LogOut,
  Moon,
  Play,
  Sun,
} from "lucide-react";
import { api } from "@/lib/api";
import { useLive } from "@/lib/live";
import { useTheme } from "@/lib/theme";
import type { Me } from "@/lib/types";
import { cn, pct } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { CollectDialog } from "@/components/CollectDialog";

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/pool", label: "Pool" },
  { to: "/gateway", label: "Gateway" },
  { to: "/analytics", label: "Analytics" },
  { to: "/check", label: "Site check" },
  { to: "/logs", label: "Logs" },
  { to: "/settings", label: "Settings" },
];

function Brand() {
  return (
    <div className="flex min-w-0 items-center gap-3.5">
      <div className="nova-mark">N</div>
      <div className="min-w-0">
        <div className="nova-title">
          nova<span>proxy</span>
        </div>
        <div className="nova-sub truncate">harvest · validate · gateway</div>
      </div>
    </div>
  );
}

export function AppShell({ me, children }: { me: Me; children: ReactNode }) {
  const [collectOpen, setCollectOpen] = useState(false);
  const { status } = useLive();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const location = useLocation();

  const { data: gateway } = useQuery({
    queryKey: ["gateway"],
    queryFn: api.gateway,
    refetchInterval: 5_000,
  });

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

  const running = status?.running ?? false;
  const rechecking = status?.recheck_running ?? false;
  const progress = running
    ? pct(status?.alive ?? 0, status?.target ?? 0)
    : rechecking
      ? pct(status?.recheck_done ?? 0, status?.recheck_total ?? 0)
      : 0;

  return (
    <div className="min-h-full">
      <div className="aurora" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>

      <header className="nova-header">
        <Brand />

        <div className="ml-auto flex items-center gap-2">
          <span className="nova-pill hidden sm:inline-flex">
            <span className="size-1.5 rounded-full bg-[var(--color-success)]" />
            {(status?.alive ?? 0).toLocaleString()} alive
          </span>
          <span className="nova-pill hidden md:inline-flex">
            <span
              className={cn(
                "size-1.5 rounded-full",
                gateway?.running ? "bg-[var(--color-success)]" : "bg-[var(--color-faint)]",
              )}
            />
            gateway {gateway?.running ? "up" : "down"}
          </span>
          <button
            className="nova-theme"
            onClick={toggle}
            title={theme === "dark" ? "Switch to light" : "Switch to dark"}
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
          <div className="hidden items-center gap-2 sm:flex">
            <div className="grid size-8 place-items-center rounded-full bg-white/15 text-[11px] font-semibold uppercase text-[var(--c-header-ink)]">
              {me.username.slice(0, 2)}
            </div>
            <button
              onClick={logout}
              className="rounded-lg p-2 text-[var(--c-header-muted)] transition-colors hover:bg-white/10 hover:text-[var(--c-header-ink)]"
              title="Sign out"
            >
              <LogOut className="size-4" />
            </button>
          </div>
          <Button
            size="sm"
            className="bg-white/15 text-[var(--c-header-ink)] hover:bg-white/25"
            onClick={() => setCollectOpen(true)}
          >
            <Play className="size-3.5" />
            <span className="hidden sm:inline">New collection</span>
          </Button>
        </div>
      </header>

      <nav className="nova-nav" aria-label="Sections">
        {NAV.map(({ to, label, end }) => (
          <NavLink key={to} to={to} end={end}>
            {label}
          </NavLink>
        ))}
      </nav>

      {(running || rechecking) && (
        <div className="h-0.5 w-full bg-[var(--color-elevated)]">
          <div
            className="h-full bg-[var(--color-accent)] transition-[width] duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">{children}</main>

      <CollectDialog open={collectOpen} onOpenChange={setCollectOpen} />
    </div>
  );
}

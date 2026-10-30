import { Suspense, lazy, useEffect } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useNavigate } from "react-router-dom";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { LiveProvider } from "@/lib/live";
import { ThemeProvider } from "@/lib/theme";
import { AppShell } from "@/components/AppShell";

const LoginPage = lazy(() =>
  import("@/pages/LoginPage").then((m) => ({ default: m.LoginPage })),
);
const RegisterPage = lazy(() =>
  import("@/pages/RegisterPage").then((m) => ({ default: m.RegisterPage })),
);
const OverviewPage = lazy(() =>
  import("@/pages/OverviewPage").then((m) => ({ default: m.OverviewPage })),
);
const PoolPage = lazy(() => import("@/pages/PoolPage").then((m) => ({ default: m.PoolPage })));
const GatewayPage = lazy(() =>
  import("@/pages/GatewayPage").then((m) => ({ default: m.GatewayPage })),
);
const AnalyticsPage = lazy(() =>
  import("@/pages/AnalyticsPage").then((m) => ({ default: m.AnalyticsPage })),
);
const SiteCheckPage = lazy(() =>
  import("@/pages/SiteCheckPage").then((m) => ({ default: m.SiteCheckPage })),
);
const LogsPage = lazy(() => import("@/pages/LogsPage").then((m) => ({ default: m.LogsPage })));
const SettingsPage = lazy(() =>
  import("@/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })),
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false, staleTime: 5_000 },
  },
});

function Booting() {
  return (
    <div className="flex h-full min-h-screen items-center justify-center gap-3 text-sm text-muted">
      <Loader2 className="size-4 animate-spin" />
      Loading console…
    </div>
  );
}

function Protected() {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
  });

  useEffect(() => {
    if (isError) navigate("/login", { replace: true });
  }, [isError, navigate]);

  if (isLoading) return <Booting />;
  if (!data) return null;

  return (
    <LiveProvider>
      <AppShell me={data}>
        <Outlet />
      </AppShell>
    </LiveProvider>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Suspense fallback={<Booting />}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route element={<Protected />}>
                <Route path="/" element={<OverviewPage />} />
                <Route path="/pool" element={<PoolPage />} />
                <Route path="/gateway" element={<GatewayPage />} />
                <Route path="/analytics" element={<AnalyticsPage />} />
                <Route path="/check" element={<SiteCheckPage />} />
                <Route path="/logs" element={<LogsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
        <Toaster
          theme="system"
          position="bottom-right"
          toastOptions={{
            style: {
              background: "var(--color-panel)",
              border: "1px solid var(--color-border)",
              color: "var(--color-fg)",
            },
          }}
        />
      </QueryClientProvider>
    </ThemeProvider>
  );
}

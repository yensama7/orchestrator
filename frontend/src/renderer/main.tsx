import "./lib/apply-initial-theme";
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import "./styles.css";

const queryClient = new QueryClient();

// Phase 0 placeholder: proves the graphite theme renders, the theme toggle
// flips data-theme, and /api proxies to the backend. Replaced by the real shell
// in Phase 1.
function ThemeToggle() {
  const [theme, setTheme] = useState(
    () => document.documentElement.getAttribute("data-theme") ?? "dark",
  );
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);
  return (
    <button
      onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
      className="rounded-md border px-3 py-1.5 text-sm hover:bg-[var(--color-interactive-hover)]"
      style={{ borderColor: "var(--color-border)" }}
    >
      Theme: {theme}
    </button>
  );
}

function HealthCheck() {
  const { data, isError, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: () => fetch("/api/health").then((r) => r.json()),
    retry: false,
  });
  const label = isLoading ? "checking…" : isError ? "unreachable" : JSON.stringify(data);
  return (
    <code className="font-mono text-sm" style={{ color: "var(--color-text-muted)" }}>
      /api/health → {label}
    </code>
  );
}

function Scaffold() {
  return (
    <div className="flex min-h-full flex-col gap-6 p-10">
      <div className="flex items-center gap-4">
        <h1 className="text-heading font-semibold tracking-tight">Lineage</h1>
        <span
          className="rounded-full px-2 py-0.5 text-caption"
          style={{ background: "var(--color-accent-weak)", color: "var(--color-accent)" }}
        >
          Phase 0 scaffold
        </span>
        <ThemeToggle />
      </div>
      <div
        className="flex flex-col gap-3 rounded-lg border p-6"
        style={{ borderColor: "var(--color-border)", background: "var(--color-bg-secondary)" }}
      >
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          Graphite design tokens render. Backend proxy:
        </p>
        <HealthCheck />
      </div>
    </div>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <QueryClientProvider client={queryClient}>
    <Scaffold />
  </QueryClientProvider>,
);

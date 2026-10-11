import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { sse } from "./api";
// §P5: self-hosted fonts (bundled by Vite) — no CDN request, no FOUT, offline.
// Only the weights the UI actually uses (Archivo 400/500/600, JBM 400/500).
import "@fontsource/archivo/400.css";
import "@fontsource/archivo/500.css";
import "@fontsource/archivo/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "./styles.css";

// SSE-first (§P4d): REST snapshot on load, then SSE deltas invalidate the cache
// (App.tsx) so views refetch on real change. The 4s poll is a *fallback* — it
// only runs while the stream is down, so a healthy connection carries state over
// one mechanism, not two.
const qc = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 2_000, refetchInterval: () => (sse.stale ? 4_000 : false), retry: 1 },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

// Poll every 4s so every view stays live during a run; the ticker/spend also
// stream over SSE for sub-second updates.
const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 2_000, refetchInterval: 4_000, retry: 1 } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);

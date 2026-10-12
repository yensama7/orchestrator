import "./lib/apply-initial-theme";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import "./styles.css";
import { createAppRouter } from "./router";
import { sse } from "./lib/api";

// SSE-first (§P4d): REST snapshot on load, then SSE deltas invalidate the cache
// (RunProvider) so views refetch on real change. The 4s poll is a *fallback* —
// it only runs while the stream is down, so a healthy connection carries state
// over one mechanism, not two.
const queryClient = new QueryClient({
	defaultOptions: {
		queries: { staleTime: 2_000, refetchInterval: () => (sse.stale ? 4_000 : false), retry: 1 },
	},
});
const router = createAppRouter(queryClient);

declare module "@tanstack/react-router" {
	interface Register {
		router: typeof router;
	}
}

createRoot(document.getElementById("root") as HTMLElement).render(
	<QueryClientProvider client={queryClient}>
		<RouterProvider router={router} />
	</QueryClientProvider>,
);

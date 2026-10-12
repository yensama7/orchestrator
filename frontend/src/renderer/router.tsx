import { createHashHistory, createRouter } from "@tanstack/react-router";
import type { QueryClient } from "@tanstack/react-query";
import { routeTree } from "./routeTree.gen";

// Hash history: we serve over nginx with an /api proxy, but hash history needs
// zero SPA-fallback config and is otherwise identical — same choice as the
// reference. defaultPreloadStaleTime: 0 because SSE is the source of truth, so
// a preloaded route must always re-run its loader rather than serve stale cache.
export function createAppRouter(queryClient: QueryClient) {
	return createRouter({
		history: createHashHistory(),
		routeTree,
		context: { queryClient },
		defaultPreload: "intent",
		defaultPreloadStaleTime: 0,
		scrollRestoration: true,
	});
}

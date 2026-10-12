import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

// Ported verbatim from web/src/api.ts (Phase 3) — the data layer is unchanged;
// only the presentation moves to shadcn/Tailwind.

const get = (path: string) => fetch(path).then((r) => r.json());

// POST helper (shared) — JSON in, JSON out, tolerant of empty bodies.
export const post = async <T = any,>(path: string, body?: unknown): Promise<T> => {
	const r = await fetch(path, {
		method: "POST",
		headers: { "content-type": "application/json" },
		body: body ? JSON.stringify(body) : undefined,
	});
	return r.json().catch(() => ({}) as T);
};

// `run` scopes per-run reads to a selected run (omit for run-independent ones
// like catalog/settings). It's part of the queryKey so switching runs refetches.
export const useApi = <T,>(key: string, run?: string) =>
	useQuery<T>({
		queryKey: run ? [key, run] : [key],
		queryFn: () => get(`/api/${key}${run ? `?run=${encodeURIComponent(run)}` : ""}`),
	});

export type TickerEvent = { key: string; text: string };

// SSE-first liveness (§P4d). Source of truth is the stream; the 4s poll is a
// *reconnect fallback* that only runs while the stream is down. This module flag
// is what the react-query default reads (main.tsx) to decide whether to poll, so
// a healthy SSE connection means zero background polling — no duplicate fetches.
// Starts stale so the very first load still fetches if SSE never connects.
export const sse = { stale: true };

// SSE — ticker + spend (§20.9). Native EventSource: reconnects for free.
export function useStream(runId: string) {
	const [events, setEvents] = useState<TickerEvent[]>([]);
	const [spent, setSpent] = useState<number | null>(null);
	const [stale, setStale] = useState(true);

	useEffect(() => {
		const es = new EventSource(`/api/runs/${encodeURIComponent(runId)}/stream`);
		const up = () => {
			sse.stale = false;
			setStale(false);
		};
		es.onopen = up;
		es.addEventListener("ticker", (e) => {
			up();
			const ev = JSON.parse((e as MessageEvent).data);
			setEvents((prev) => [ev, ...prev].slice(0, 40)); // newest first
		});
		es.addEventListener("spend", (e) => {
			up();
			setSpent(JSON.parse((e as MessageEvent).data).spent);
		});
		es.onerror = () => {
			sse.stale = true;
			setStale(true);
		};
		return () => {
			es.close();
			sse.stale = true;
		};
	}, [runId]);

	return { events, spent, stale };
}

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

const get = (path: string) => fetch(path).then((r) => r.json());

// POST helper (shared) — JSON in, JSON out, tolerant of empty bodies.
export const post = async <T = any,>(path: string, body?: unknown): Promise<T> => {
  const r = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return r.json().catch(() => ({} as T));
};

// `run` scopes per-run reads to a selected run (omit for run-independent ones
// like catalog/settings). It's part of the queryKey so switching runs refetches.
export const useApi = <T,>(key: string, run?: string) =>
  useQuery<T>({
    queryKey: run ? [key, run] : [key],
    queryFn: () => get(`/api/${key}${run ? `?run=${encodeURIComponent(run)}` : ""}`),
  });

export type TickerEvent = { key: string; text: string };

// SSE — ticker + spend (§20.9). Native EventSource: reconnects for free.
export function useStream(runId: string) {
  const [events, setEvents] = useState<TickerEvent[]>([]);
  const [spent, setSpent] = useState<number | null>(null);
  const [stale, setStale] = useState(false);

  useEffect(() => {
    const es = new EventSource(`/api/runs/${encodeURIComponent(runId)}/stream`);
    es.addEventListener("ticker", (e) => {
      const ev = JSON.parse((e as MessageEvent).data);
      setStale(false);
      setEvents((prev) => [ev, ...prev].slice(0, 40)); // newest first
    });
    es.addEventListener("spend", (e) => setSpent(JSON.parse((e as MessageEvent).data).spent));
    es.onerror = () => setStale(true);
    return () => es.close();
  }, [runId]);

  return { events, spent, stale };
}

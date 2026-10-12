import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useApi, useStream, type TickerEvent } from "@/lib/api";
import type { RunData, RunsList } from "@/lib/types";
import { useRunStore } from "@/stores/run-store";

// One place owns the live run: the `run`/`runs` reads, the single SSE stream,
// and the §P4d invalidation that refetches open views on each delta. The old
// App.tsx did this at the root; here the shell provides it and every route +
// the topbar/ticker consume it, so there's still exactly one EventSource.

type RunCtx = {
	run?: RunData;
	runs?: RunsList;
	events: TickerEvent[];
	spent: number | null;
	stale: boolean;
};

const Ctx = createContext<RunCtx | null>(null);

export function RunProvider({ children }: { children: ReactNode }) {
	const qc = useQueryClient();
	const selectedRun = useRunStore((s) => s.selectedRun);
	const { data: run } = useApi<RunData>("run", selectedRun ?? undefined);
	const { data: runs } = useApi<RunsList>("runs");
	const { events, spent, stale } = useStream(run?.id ?? "current");

	// Each SSE delta (a ticker line or a spend tick) invalidates the read queries
	// so open views refetch on real change — this is what keeps polling off while
	// the stream is healthy.
	useEffect(() => {
		qc.invalidateQueries();
	}, [events.length, spent, qc]);

	return <Ctx.Provider value={{ run, runs, events, spent, stale }}>{children}</Ctx.Provider>;
}

export function useRun(): RunCtx {
	const ctx = useContext(Ctx);
	if (!ctx) throw new Error("useRun must be used within <RunProvider>");
	return ctx;
}

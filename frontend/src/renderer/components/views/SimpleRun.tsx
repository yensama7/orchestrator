import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { post } from "@/lib/api";
import { useRun } from "@/hooks/use-run";
import { useRunStore } from "@/stores/run-store";
import { Hint, Panel } from "@/components/common";
import { Button } from "@/components/ui/button";
import { ModeBadge } from "@/components/ModeBadge";
import { cn } from "@/lib/utils";

// §P5 Simple UI: brief in → progress → result + cost-per-verified-result out.
// Progressive disclosure, not a second codebase — Expert reuses the same APIs
// and the same run. Reads the live run + ticker from the shell's RunProvider.

const ACTIVE = (s?: string) => s === "active";

const STATUS_PILL: Record<string, string> = {
	passed: "border-success/50 text-success",
	active: "border-warning/50 text-warning",
	failed: "border-destructive/50 text-destructive",
	abandoned: "border-destructive/50 text-destructive",
};

export function SimpleRun() {
	const { run, events } = useRun();
	const qc = useQueryClient();
	const setSelectedRun = useRunStore((s) => s.setSelectedRun);
	const [brief, setBrief] = useState("");
	const [busy, setBusy] = useState(false);

	const build = async () => {
		setBusy(true);
		try {
			// one step: fingerprint the brief, then start a fresh run on it.
			const fp = await post<Record<string, unknown>>("/api/extract", { brief });
			const name = String(fp.subdomain || fp.domain || "untitled run");
			await post("/api/runs/new/start", { fingerprint: fp, ceiling: 15, name });
			setSelectedRun(null);
			qc.invalidateQueries();
		} finally {
			setBusy(false);
		}
	};

	const running = ACTIVE(run?.status);
	const cpv = run?.cost_per_verified;

	return (
		<div className="mx-auto flex max-w-[680px] flex-col gap-4 p-5">
			<Panel className="p-4">
				<h3 className="mb-2.5 text-xs font-semibold text-foreground">Build from a brief</h3>
				<textarea
					rows={4}
					value={brief}
					disabled={busy || running}
					onChange={(e) => setBrief(e.target.value)}
					className="w-full resize-y rounded-md border border-border bg-input/50 p-2 font-mono text-xs text-foreground outline-none disabled:opacity-50"
					placeholder="Describe what to build — e.g. a CLI that converts CSV to JSON, with tests."
				/>
				<div className="mt-2.5 flex items-center gap-2.5">
					<Button disabled={!brief.trim() || busy || running} onClick={build}>
						{busy ? "Starting…" : running ? "Run in progress…" : "Build"}
					</Button>
					{running && <Hint>a run is live — watch it below</Hint>}
				</div>
			</Panel>

			{run && run.id !== "—" && (
				<Panel className="p-4">
					<div className="flex items-center gap-2.5">
						<h3 className="text-xs font-semibold text-foreground">{run.spec}</h3>
						<ModeBadge mode={run.mode} />
						<span
							className={cn(
								"rounded-md border px-1.5 py-0.5 font-mono text-[10px] tracking-wide uppercase",
								STATUS_PILL[run.status] ?? "border-border text-muted-foreground",
							)}
						>
							{run.status}
						</span>
					</div>
					<div className="my-3.5 flex gap-8">
						<Metric label="cost / verified result" value={cpv != null ? `$${cpv.toFixed(2)}` : "—"} big />
						<Metric label="verified nodes" value={String(run.verified_count)} />
						<Metric label="spent" value={`$${run.spent.toFixed(2)}`} />
					</div>
					{cpv == null && (
						<Hint>
							Nothing verified yet{running ? " — the run is still going." : "."} A result counts only when a
							check that <em>executes the produced code</em> passes.
						</Hint>
					)}
					<div className="mt-3 flex flex-col gap-1 border-t border-border pt-2.5">
						{events.slice(0, 8).map((e, i) => (
							<div key={i} className="font-mono text-[11px] text-muted-foreground">
								<span className="mr-2 text-passive uppercase">{e.key}</span>
								{e.text}
							</div>
						))}
						{events.length === 0 && <div className="font-mono text-[11px] text-passive">no activity yet</div>}
					</div>
				</Panel>
			)}
		</div>
	);
}

function Metric({ label, value, big }: { label: string; value: string; big?: boolean }) {
	return (
		<div>
			<span className="text-xs text-muted-foreground">{label}</span>
			<div className={cn("font-mono", big ? "text-2xl text-warning" : "text-xl")}>{value}</div>
		</div>
	);
}

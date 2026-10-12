import { useRun } from "@/hooks/use-run";
import { cn } from "@/lib/utils";

// Topbar spend rail — live spent / projected / ceiling from the run query, with
// the SSE spend tick overriding `spent`. A green/dim dot reflects stream health.
export function SpendRail() {
	const { run, spent, stale } = useRun();
	const liveSpent = spent ?? run?.spent ?? 0;
	return (
		<div className="flex items-center gap-3 font-mono text-xs">
			<span
				className={cn("size-1.5 rounded-full", stale ? "bg-passive" : "bg-success")}
				aria-hidden
				title={stale ? "stream reconnecting" : "live"}
			/>
			<span className="text-warning">
				${liveSpent.toFixed(2)}
				<span className="ml-1 text-passive">spent</span>
			</span>
			{run && (
				<>
					<span className="text-muted-foreground">
						${run.projected.toFixed(2)}
						<span className="ml-1 text-passive">proj</span>
					</span>
					<span className="text-passive">
						${run.ceiling.toFixed(2)}
						<span className="ml-1">ceiling</span>
					</span>
				</>
			)}
		</div>
	);
}

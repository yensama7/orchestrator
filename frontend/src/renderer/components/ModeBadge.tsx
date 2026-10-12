import { Badge } from "@/components/ui/badge";

// §P0 truth-in-labeling: every chart/number on screen belongs to a run; this
// badge tells a reviewer at a glance whether it's a verified (live) outcome or a
// simulated one (echo stubs + structural verifiers).
export function ModeBadge({ mode }: { mode: string }) {
	const live = mode === "live";
	return (
		<Badge
			variant={live ? "success" : "warning"}
			className="font-mono text-[10px] tracking-wide uppercase"
			title={
				live
					? "live — real model + behavioral verifier; counts toward scoring/benchmarks"
					: "simulated — echo stub and/or structural verifiers only; not a verified outcome"
			}
		>
			{live ? "live" : "simulated"}
		</Badge>
	);
}

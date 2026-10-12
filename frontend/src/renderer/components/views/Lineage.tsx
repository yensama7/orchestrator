import { useState } from "react";
import { useApi } from "@/lib/api";
import { useRun } from "@/hooks/use-run";
import { Legend, Scatter, spread, type Pt } from "@/components/charts";
import { Chip, EmptyState, Hint, Panel, PanelHeader, Row } from "@/components/common";

type Lin = {
	points: (Pt & { kind: string })[];
	edges: [string, string][];
	nearest: { name: string; score: number; outcome: string }[];
	inherited: { template: string; status: string; rows: { label: string; n: string; color?: string }[] } | null;
	domains: string[];
};

// status→text-color for inherited rows (backend sends the semantic color name).
const TEXT: Record<string, string> = {
	sage: "text-success",
	amber: "text-warning",
	rust: "text-destructive",
	violet: "text-primary",
};

export function Lineage() {
	const run = useRun().run?.id;
	const { data } = useApi<Lin>("lineage", run);
	const [domain, setDomain] = useState("all domains");
	if (!data) return null;

	// filtered-out run nodes render dimmed as context; templates always shown.
	const points: Pt[] = spread(
		data.points.map((p) => ({
			...p,
			dimmed: p.kind === "run" && domain !== "all domains" && p.domain !== domain,
		})),
	);
	const runCount = data.points.filter((p) => p.kind === "run").length;

	return (
		<div className="grid grid-cols-[1fr_320px] items-start gap-4 p-5">
			{data.points.length ? (
				<div className="flex flex-col gap-2">
					<Scatter points={points} edges={data.edges} />
					<div className="flex items-center justify-between">
						<Legend
							items={[
								{ color: "sage", label: "passed" },
								{ color: "amber", label: "active" },
								{ color: "rust", label: "failed" },
								{ color: "violet", label: "template" },
							]}
						/>
						<Hint>
							{runCount} run{runCount === 1 ? "" : "s"}
						</Hint>
					</div>
				</div>
			) : (
				<Panel className="p-4">
					<EmptyState message="No runs yet. Start one from New run to populate the lineage graph." />
				</Panel>
			)}

			<div className="flex flex-col gap-3.5">
				<Panel className="p-4">
					<PanelHeader title="Nearest past work" help="Matched on spec fingerprint, not prose similarity." />
					{data.nearest.length ? (
						data.nearest.map((r) => (
							<Row key={r.name} color={r.outcome} label={r.name} value={r.score.toFixed(2)} />
						))
					) : (
						<Hint>no comparable runs yet</Hint>
					)}
				</Panel>

				{data.inherited && (
					<Panel className="p-4">
						<PanelHeader
							title={`Inherited from ${data.inherited.template}`}
							help="What the template contributed before any model was called."
						/>
						{data.inherited.rows.map((r) => (
							<Row
								key={r.label}
								label={<span className={r.color ? TEXT[r.color] : undefined}>{r.label}</span>}
								value={r.n}
							/>
						))}
					</Panel>
				)}

				<Panel className="p-4">
					<PanelHeader title="Show" />
					<div className="flex flex-wrap gap-1.5">
						{data.domains.map((d) => (
							<Chip key={d} active={d === domain} onClick={() => setDomain(d)}>
								{d}
							</Chip>
						))}
					</div>
					<Hint className="mt-2">Hover a node to trace its inheritance edges.</Hint>
				</Panel>
			</div>
		</div>
	);
}

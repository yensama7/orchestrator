import { useState } from "react";
import { useApi } from "@/lib/api";
import { useRun } from "@/hooks/use-run";
import { HEX, Scatter, spread, type Pt } from "@/components/charts";
import { EmptyState, Hint, Panel, PanelHeader, Row } from "@/components/common";

type Mem = {
	tiers: { key: string; n: number; color: string; lines: string[] }[];
	recall: { label: string; n: number; color: string }[];
	quality: { label: string; n: string }[];
	points: Pt[];
};

const BLURB: Record<string, string> = {
	episodic: "What happened, in order, never edited. Powers replay and audit.",
	semantic: "What the project knows now, distilled from the diary. This is what agents retrieve.",
	procedural: "How to build things — the agent stack, the order, the known traps.",
};

export function Memory() {
	const run = useRun().run?.id;
	const { data } = useApi<Mem>("memory", run);
	const [filter, setFilter] = useState<string | null>(null);
	if (!data) return null;

	// semantic points coloured by status; subject filter dims the rest.
	const points: Pt[] = spread(
		data.points.map((p) => ({ ...p, dimmed: !!filter && p.meta?.subject !== filter })),
	);

	return (
		<div className="flex flex-col gap-4 p-5">
			<div className="grid grid-cols-3 gap-3.5">
				{data.tiers.map((t) => (
					<Panel
						key={t.key}
						className="cursor-pointer p-4"
						style={{ borderTopColor: HEX[t.color], borderTopWidth: 2 }}
						onClick={() => setFilter(null)}
					>
						<div className="mb-2.5 flex items-center gap-2">
							<span className="size-2 rounded-full" style={{ background: HEX[t.color] }} />
							<h3 className="text-xs font-semibold text-foreground capitalize">{t.key}</h3>
							<span className="ml-auto font-mono text-xs text-muted-foreground">{t.n.toLocaleString()}</span>
						</div>
						<Hint className="mb-2.5">{BLURB[t.key]}</Hint>
						<pre className="m-0 font-mono text-[11.5px] whitespace-pre-wrap text-muted-foreground">
							{t.lines.join("\n")}
						</pre>
					</Panel>
				))}
			</div>

			<div className="grid grid-cols-[1fr_320px] items-start gap-4">
				{data.points.length ? (
					<Scatter
						points={points}
						height={430}
						onCommit={(id) => {
							const p = data.points.find((x) => x.id === id);
							setFilter(p?.meta?.subject ?? null);
						}}
					/>
				) : (
					<Panel className="p-4">
						<EmptyState message="No decisions recorded yet. Run something to populate memory." />
					</Panel>
				)}
				<div className="flex flex-col gap-3.5">
					<Panel className="p-4">
						<PanelHeader
							title="Row-level recall"
							help="Individual memory rows for this run — open when an agent does something you can't explain."
						/>
						{data.recall.map((r) => (
							<Row key={r.label} color={r.color} label={r.label} value={r.n.toLocaleString()} />
						))}
					</Panel>
					<Panel className="p-4">
						<PanelHeader title="Retrieval quality" />
						{data.quality.map((q) => (
							<Row key={q.label} label={q.label} value={q.n} />
						))}
					</Panel>
				</div>
			</div>
		</div>
	);
}

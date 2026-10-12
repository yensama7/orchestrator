import { useApi } from "@/lib/api";
import { useRun } from "@/hooks/use-run";
import { Donut, LineChart, Pie, type Slice } from "@/components/charts";
import { EmptyState, Hint, Panel, PanelHeader } from "@/components/common";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { TipLine } from "@/lib/hover";

type Agent = {
	agent: string;
	role: string;
	model: string;
	state: string;
	calls: number;
	tokens: string;
	cached: string;
	cost: string;
	pass: string;
	vind: string;
};
type Charts = {
	token_attr: Slice[];
	cost_share: Slice[];
	verification: Slice[];
	spend_series: Record<string, number>[];
	throughput: Record<string, number>[];
};

const STATE_COLOR: Record<string, string> = {
	running: "var(--chart-bone)",
	waiting: "#e0a33c",
	idle: "#69708a",
};

export function Agents() {
	const run = useRun().run?.id;
	// agents rows are the live global roster; charts' node/spend series are per-run.
	const { data } = useApi<Agent[]>("agents");
	const { data: charts } = useApi<Charts>("charts", run);
	if (!data) return null;

	if (!data.length) {
		return (
			<div className="p-5">
				<Panel className="p-4">
					<EmptyState
						message="No agents yet. Add models and assign roles in Settings, then start a run."
						action={<Hint>Settings → Add model → Add agent</Hint>}
					/>
				</Panel>
			</div>
		);
	}

	// spend chart footer: the computed saved figure.
	const savedFooter = (row: Record<string, number>): TipLine[] => {
		const saved = (row.uncached ?? 0) - (row.actual ?? 0);
		const pct = row.uncached ? Math.round((saved / row.uncached) * 100) : 0;
		return [{ text: `saved  $${saved.toFixed(2)}  (${pct}%)`, mono: true, color: "#7fb894" }];
	};

	return (
		<div className="flex flex-col gap-4 p-5">
			<Panel className="px-1">
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead>Agent</TableHead>
							<TableHead>Role</TableHead>
							<TableHead>Model</TableHead>
							<TableHead>State</TableHead>
							<TableHead>Calls</TableHead>
							<TableHead>Tokens</TableHead>
							<TableHead>Cached</TableHead>
							<TableHead>Cost</TableHead>
							<TableHead>Pass</TableHead>
							<TableHead>Vind</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{data.map((a) => (
							<TableRow key={a.agent}>
								<TableCell className="font-mono">{a.agent}</TableCell>
								<TableCell className="text-primary">{a.role}</TableCell>
								<TableCell className="font-mono text-muted-foreground">{a.model}</TableCell>
								<TableCell>
									<span className="inline-flex items-center gap-1.5">
										<span
											className="size-2 rounded-full"
											style={{ background: STATE_COLOR[a.state] }}
										/>
										{a.state}
									</span>
								</TableCell>
								<TableCell className="font-mono">{a.calls}</TableCell>
								<TableCell className="font-mono">{a.tokens}</TableCell>
								<TableCell className="font-mono text-muted-foreground">{a.cached}</TableCell>
								<TableCell className="font-mono text-warning">{a.cost}</TableCell>
								<TableCell className="font-mono">{a.pass}</TableCell>
								<TableCell className="font-mono text-primary">{a.vind}</TableCell>
							</TableRow>
						))}
					</TableBody>
				</Table>
			</Panel>

			{charts && (
				<div className="grid grid-cols-4 gap-3.5">
					<ChartCard title="Cumulative spend" hint="against the uncached counterfactual">
						{charts.spend_series.length ? (
							<LineChart
								data={charts.spend_series}
								series={[
									{ key: "actual", label: "actual", color: "amber" },
									{ key: "uncached", label: "uncached", color: "rust" },
								]}
								footer={savedFooter}
							/>
						) : (
							<Empty />
						)}
					</ChartCard>
					<ChartCard title="Throughput" hint="nodes completed over time">
						{charts.throughput.length ? (
							<LineChart data={charts.throughput} series={[{ key: "nodes", label: "nodes", color: "violet" }]} />
						) : (
							<Empty />
						)}
					</ChartCard>
					<ChartCard title="Token attribution" hint="by agent — radius scales with tokens">
						{charts.token_attr.some((s) => s.value) ? <Pie slices={charts.token_attr} unit="tokens" /> : <Empty />}
					</ChartCard>
					<ChartCard title="Cost share" hint="by agent — radius scales with spend">
						{charts.cost_share.some((s) => s.value) ? <Pie slices={charts.cost_share} unit="$" /> : <Empty />}
					</ChartCard>
					<ChartCard title="Verification" hint="nodes by outcome">
						{charts.verification.some((s) => s.value) ? (
							<Donut slices={charts.verification} centerLabel="nodes" />
						) : (
							<Empty />
						)}
					</ChartCard>
				</div>
			)}
		</div>
	);
}

function ChartCard({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
	return (
		<Panel className="p-4">
			<PanelHeader title={title} />
			<Hint className="-mt-1.5 mb-2.5">{hint}</Hint>
			<div className="flex min-h-[130px] items-center justify-center">{children}</div>
		</Panel>
	);
}

const Empty = () => <Hint>no data yet</Hint>;

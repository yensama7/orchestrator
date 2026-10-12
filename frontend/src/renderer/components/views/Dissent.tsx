import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useApi, post } from "@/lib/api";
import { useRun } from "@/hooks/use-run";
import { useRunStore } from "@/stores/run-store";
import { Chip, EmptyState, Panel, SectionTitle } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { HEX } from "@/components/charts";

type Dis = {
	leaderboard: {
		agent: string;
		model: string;
		rate: number;
		overruled: number;
		resurrected: number;
		vindicated: number;
		refuted: number;
		promote: boolean;
	}[];
	ledger: {
		id: string;
		node: string;
		dissenter: string;
		winner: string;
		stage: number;
		reason: string;
		status: string;
	}[];
};

type Resurrected = { ok: boolean; outcome?: string; reason?: string };

const STATUS_COLOR: Record<string, string> = {
	dormant: HEX.dimmer,
	resurrected: HEX.violet,
	vindicated: HEX.sage,
	refuted: HEX.rust,
};

export function Dissent() {
	const run = useRun().run?.id;
	const { data } = useApi<Dis>("dissent", run);
	const qc = useQueryClient();
	const navigate = useNavigate();
	const setSelectedRun = useRunStore((s) => s.setSelectedRun);
	const [filter, setFilter] = useState<string>("all");
	const [busy, setBusy] = useState<string | null>(null);

	async function resurrect(id: string) {
		setBusy(id);
		try {
			const res = await post<Resurrected>(`/api/dissent/${id}/resurrect`);
			// settling a dissent moves vindication + may rewrite a decision, so refresh
			// the ledger, the leaderboard's source, and the memory views it feeds.
			["dissent", "agents", "memory", "lineage", "charts"].forEach((k) =>
				qc.invalidateQueries({ queryKey: run ? [k, run] : [k] }),
			);
			if (!res.ok) alert(`Could not resurrect: ${res.reason ?? "unknown"}`);
		} finally {
			setBusy(null);
		}
	}

	async function fork(id: string) {
		setBusy(id);
		try {
			const res = await post<{ ok: boolean; run?: string; reason?: string }>(`/api/dissent/${id}/fork`);
			if (res.ok) {
				// the fork is now server-current — follow it and land on the board.
				setSelectedRun(null);
				qc.invalidateQueries();
				navigate({ to: "/" });
			} else alert(`Could not fork: ${res.reason ?? "unknown"}`);
		} finally {
			setBusy(null);
		}
	}

	if (!data) return null;
	const rows = data.ledger.filter((r) => filter === "all" || r.status === filter);

	return (
		<div className="flex flex-col gap-3 p-5">
			<SectionTitle>Vindication leaderboard — the roads not taken, and which were right</SectionTitle>
			{data.leaderboard.length === 0 ? (
				<Panel className="p-4">
					<EmptyState message="No dissent yet. When agents disagree on a node, the overruled proposals land here — and the ones that turn out right rise up the board." />
				</Panel>
			) : (
				<div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
					{data.leaderboard.map((a) => (
						<Panel key={a.agent} className="p-3">
							<div className="font-mono text-sm">{a.agent}</div>
							<div className="text-xs text-passive">{a.model}</div>
							<div className="my-1.5 font-mono text-2xl text-success">{a.rate}%</div>
							<div className="flex h-1.5 gap-px overflow-hidden rounded-sm">
								<span style={{ flex: a.overruled, background: HEX.dimmer }} />
								<span style={{ flex: a.resurrected, background: HEX.violet }} />
								<span style={{ flex: a.vindicated, background: HEX.sage }} />
								<span style={{ flex: a.refuted, background: HEX.rust }} />
							</div>
							{a.promote && (
								<div className="mt-2">
									<Chip active>promote?</Chip>
								</div>
							)}
						</Panel>
					))}
				</div>
			)}

			<SectionTitle className="mt-3">The ledger</SectionTitle>
			<div className="flex gap-1.5">
				{["all", "dormant", "resurrected", "vindicated", "refuted"].map((s) => (
					<Chip key={s} active={s === filter} onClick={() => setFilter(s)}>
						{s}
					</Chip>
				))}
			</div>
			<Panel className="px-1">
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead>Node</TableHead>
							<TableHead>Dissenter</TableHead>
							<TableHead>Winner</TableHead>
							<TableHead>Stage</TableHead>
							<TableHead>Reason</TableHead>
							<TableHead>Status</TableHead>
							<TableHead />
						</TableRow>
					</TableHeader>
					<TableBody>
						{rows.length === 0 && (
							<TableRow>
								<TableCell colSpan={7} className="py-3.5 text-center text-muted-foreground">
									{filter === "all"
										? "No dissenting proposals recorded for this run."
										: `No ${filter} dissent.`}
								</TableCell>
							</TableRow>
						)}
						{rows.map((r) => (
							<TableRow key={r.id}>
								<TableCell className="font-mono">{r.node}</TableCell>
								<TableCell className="font-mono">{r.dissenter}</TableCell>
								<TableCell className="font-mono text-muted-foreground">{r.winner}</TableCell>
								<TableCell className="font-mono">{r.stage}</TableCell>
								<TableCell className="whitespace-normal text-muted-foreground">{r.reason}</TableCell>
								<TableCell>
									<span className="inline-flex items-center gap-1.5">
										<span
											className="size-2 rounded-full"
											style={{ background: STATUS_COLOR[r.status] }}
										/>
										{r.status}
									</span>
								</TableCell>
								<TableCell>
									{r.status === "dormant" && (
										<span className="flex gap-1.5">
											<Button
												variant="ghost"
												size="sm"
												disabled={busy === r.id}
												onClick={() => resurrect(r.id)}
												title="Re-verify and install this proposal in place"
											>
												{busy === r.id ? "…" : "Resurrect"}
											</Button>
											<Button
												variant="ghost"
												size="sm"
												disabled={busy === r.id}
												onClick={() => fork(r.id)}
												title="Fork the run from this node using this proposal"
											>
												Fork
											</Button>
										</span>
									)}
								</TableCell>
							</TableRow>
						))}
					</TableBody>
				</Table>
			</Panel>
		</div>
	);
}

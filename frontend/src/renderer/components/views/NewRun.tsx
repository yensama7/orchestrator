import { Fragment, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useRunStore } from "@/stores/run-store";
import { Chip, Hint, Panel, Row } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

// §19.3 — six numbered step cards, one column, completed steps collapse.
const STEPS = ["Brief", "Fingerprint", "Lineage match", "Roster", "Budget", "Plan review"];

// placeholder example shown before a real extraction returns
const FINGERPRINT: [string, string][] = [
	["domain", "commerce"],
	["subdomain", "storefront"],
	["stack_hints", "nextjs, postgres"],
	["payments", "paystack"],
	["auth", "required"],
	["multi_tenant", "false"],
	["region", "NG"],
];

type Fp = Record<string, unknown>;
type Match = {
	nearest: { name: string; score: number; outcome: string }[];
	inherited: { template: string; status: string; rows: { label: string; n: string; color?: string }[] } | null;
};
type RosterRow = {
	role: string;
	model: string;
	transport: string;
	consensus: string;
	pass_rate: number | null;
	vindication_rate: number | null;
	available: boolean;
};
type Node = {
	id: string;
	role: string;
	intent: string;
	irreversible: boolean;
	budget_usd: number;
	constraints: string[];
	depends_on: string[];
};
type Plan = { nodes: Node[] };

const LIST_FIELDS = new Set(["stack_hints", "compliance"]);

// the kv grid stringifies everything; put the real types back before the API
// validates them (SpecFingerprint wants list/bool, not comma-strings).
function normalizeFp(raw: Fp): Fp {
	const out: Fp = { ...raw };
	for (const f of LIST_FIELDS) {
		if (typeof out[f] === "string")
			out[f] = (out[f] as string)
				.split(",")
				.map((s) => s.trim())
				.filter(Boolean);
	}
	if (typeof out.multi_tenant === "string") out.multi_tenant = out.multi_tenant === "true";
	return out;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
	const r = await fetch(url, {
		method: "POST",
		headers: { "content-type": "application/json" },
		body: JSON.stringify(body),
	});
	return r.json();
}

export function NewRun() {
	const qc = useQueryClient();
	const navigate = useNavigate();
	const setSelectedRun = useRunStore((s) => s.setSelectedRun);

	const [step, setStep] = useState(0);
	const [brief, setBrief] = useState("");
	const [ceiling, setCeiling] = useState(15);
	const [fp, setFp] = useState<Fp | null>(null);
	const [match, setMatch] = useState<Match | null>(null);
	const [roster, setRoster] = useState<RosterRow[] | null>(null);
	const [plan, setPlan] = useState<Plan | null>(null);
	const [busy, setBusy] = useState(false);

	const body = () => ({ fingerprint: normalizeFp(fp ?? {}), budget: ceiling });

	const extract = async () => {
		setBusy(true);
		try {
			setFp(await postJson<Fp>("/api/extract", { brief }));
			setStep(1);
		} finally {
			setBusy(false);
		}
	};

	// step 1 → 2: fingerprint is confirmed, so match lineage + propose a roster
	const findSimilar = async () => {
		setBusy(true);
		try {
			const [m, r] = await Promise.all([
				postJson<Match>("/api/match", body()),
				postJson<RosterRow[]>("/api/roster", body()),
			]);
			setMatch(m);
			setRoster(r);
			setStep(2);
		} finally {
			setBusy(false);
		}
	};

	// step 4 → 5: build the real DAG at the chosen ceiling
	const reviewPlan = async () => {
		setBusy(true);
		try {
			setPlan(await postJson<Plan>("/api/plan", body()));
			setStep(5);
		} finally {
			setBusy(false);
		}
	};

	const startRun = async () => {
		setBusy(true);
		try {
			// `new` mints a fresh run server-side and makes it current (§F multi-run).
			const name = String(fp?.subdomain || fp?.domain || "untitled run");
			await postJson("/api/runs/new/start", { fingerprint: normalizeFp(fp ?? {}), ceiling, name });
		} finally {
			setBusy(false);
		}
		// follow the new current run and land on the board.
		setSelectedRun(null);
		qc.invalidateQueries();
		navigate({ to: "/" });
	};

	const fpRows: [string, string][] = fp
		? Object.entries(fp)
				.filter(([, v]) => typeof v !== "object" || v === null || Array.isArray(v))
				.map(([k, v]) => [k, Array.isArray(v) ? v.join(", ") : String(v ?? "")])
		: FINGERPRINT;

	return (
		<div className="mx-auto flex max-w-[860px] flex-col gap-3.5 p-5">
			{STEPS.map((label, i) => (
				<Panel key={label} className={cn("p-4", i > step && "pointer-events-none opacity-40")}>
					<div className="mb-2.5 flex items-center gap-2">
						<span className="font-mono text-passive">{i + 1}</span>
						<h3 className="text-xs font-semibold text-foreground">{label}</h3>
						{i < step && (
							<button className="ml-auto text-xs text-warning" onClick={() => setStep(i)}>
								Edit
							</button>
						)}
					</div>

					{i === step && (
						<div>
							{i === 0 && (
								<>
									<textarea
										rows={5}
										value={brief}
										onChange={(e) => setBrief(e.target.value)}
										className="w-full resize-y rounded-md border border-border bg-input/50 p-2 font-mono text-xs text-foreground outline-none"
										placeholder="Build a storefront for a Nigerian fashion label, Paystack checkout, admin dashboard, ~2k SKUs."
									/>
									<div className="mt-2.5">
										<Button disabled={!brief.trim() || busy} onClick={extract}>
											{busy ? "Extracting…" : "Extract fingerprint"}
										</Button>
									</div>
								</>
							)}

							{i === 1 && (
								<>
									<div className="grid grid-cols-[160px_1fr] items-center gap-x-3 gap-y-2">
										{fpRows.map(([k, v]) => (
											<Fragment key={k}>
												<label className="text-xs text-muted-foreground">{k}</label>
												<Input
													value={v}
													className="font-mono"
													onChange={(e) =>
														setFp((prev) => ({ ...(prev ?? {}), [k]: e.target.value }))
													}
												/>
											</Fragment>
										))}
									</div>
									<div className="mt-3 flex gap-2">
										<Button
											variant="ghost"
											disabled={busy}
											onClick={() => {
												setStep(0);
												extract();
											}}
										>
											Re-extract
										</Button>
										<Button disabled={busy} onClick={findSimilar}>
											{busy ? "Matching…" : "Find similar work"}
										</Button>
									</div>
								</>
							)}

							{i === 2 && (
								<>
									{match?.nearest.length ? (
										match.nearest.map((r) => (
											<Row key={r.name} color={r.outcome} label={r.name} value={r.score.toFixed(2)} />
										))
									) : (
										<Hint>
											No prior runs to match against yet — this will be the first in its neighbourhood.
										</Hint>
									)}
									{match?.inherited && (
										<Panel className="mt-3 p-4">
											<div className="mb-2.5 flex items-center gap-2">
												<h3 className="text-xs font-semibold text-foreground">
													{match.inherited.template}
												</h3>
												<span className="ml-auto">
													<Chip active>{match.inherited.status}</Chip>
												</span>
											</div>
											<Hint>
												{match.inherited.rows.map((row, k) => (
													<span key={row.label}>
														{k ? " · " : ""}
														{row.n} {row.label.toLowerCase()}
													</span>
												))}
											</Hint>
										</Panel>
									)}
									<div className="mt-3 flex gap-2">
										<Button onClick={() => setStep(3)}>
											{match?.inherited ? "Use this template" : "Start clean"}
										</Button>
									</div>
								</>
							)}

							{i === 3 && (
								<>
									<Panel className="px-1">
										<Table>
											<TableHeader>
												<TableRow>
													<TableHead>Role</TableHead>
													<TableHead>Model</TableHead>
													<TableHead>Transport</TableHead>
													<TableHead>Consensus</TableHead>
													<TableHead>Pass</TableHead>
													<TableHead>Vind.</TableHead>
												</TableRow>
											</TableHeader>
											<TableBody>
												{(roster ?? []).map((r) => (
													<TableRow key={r.role} className={cn(!r.available && "opacity-50")}>
														<TableCell className="font-mono">{r.role}</TableCell>
														<TableCell className="font-mono text-muted-foreground">
															{r.model ?? "— unassigned"}
														</TableCell>
														<TableCell className="font-mono">{r.transport}</TableCell>
														<TableCell className="text-muted-foreground">{r.consensus}</TableCell>
														<TableCell className="font-mono">
															{r.pass_rate != null ? `${Math.round(r.pass_rate * 100)}%` : "—"}
														</TableCell>
														<TableCell className="font-mono">
															{r.vindication_rate != null
																? `${Math.round(r.vindication_rate * 100)}%`
																: "—"}
														</TableCell>
													</TableRow>
												))}
											</TableBody>
										</Table>
									</Panel>
									<div className="mt-3 flex gap-2">
										<Button onClick={() => setStep(4)}>Continue</Button>
									</div>
								</>
							)}

							{i === 4 && (
								<>
									<div className="mb-1">
										<span className="text-xs text-muted-foreground">Ceiling</span>
										<div className="font-mono text-xl text-warning">${ceiling.toFixed(2)}</div>
									</div>
									<input
										type="range"
										min={2}
										max={40}
										step={0.5}
										value={ceiling}
										onChange={(e) => setCeiling(+e.target.value)}
										className="w-full"
									/>
									<Hint>
										Budget is split evenly across DAG nodes — projected spend at this ceiling is{" "}
										<span className="text-warning">${ceiling.toFixed(2)}</span>.
									</Hint>
									<Button className="mt-3" disabled={busy} onClick={reviewPlan}>
										{busy ? "Planning…" : "Review plan"}
									</Button>
								</>
							)}

							{i === 5 && (
								<>
									{(() => {
										const nodes = plan?.nodes ?? [];
										const withPitfall = nodes.filter((n) => n.constraints.length).length;
										return (
											<>
												<Hint>
													DAG · {nodes.length} nodes. Irreversible nodes get consensus;
													{withPitfall ? (
														<>
															{" "}
															<span className="text-destructive">{withPitfall}</span> carry an
															inherited pitfall constraint.
														</>
													) : (
														" no inherited pitfalls."
													)}
												</Hint>
												<div className="my-2.5 flex flex-wrap gap-2">
													{nodes.map((n) => (
														<span
															key={n.id}
															className={cn(
																"rounded-md border px-2 py-1 font-mono text-xs",
																n.constraints.length
																	? "border-destructive text-destructive"
																	: n.irreversible
																		? "border-warning text-warning"
																		: "border-border text-muted-foreground",
															)}
															title={`${n.role} · $${n.budget_usd.toFixed(2)}${
																n.constraints.length
																	? ` · ${n.constraints.length} pitfall(s)`
																	: ""
															}`}
														>
															{n.id}
														</span>
													))}
												</div>
											</>
										);
									})()}
									<div className="flex gap-2">
										<Button disabled={busy} onClick={startRun}>
											{busy ? "Starting…" : "Start run"}
										</Button>
										<Button variant="ghost" onClick={() => setStep(4)}>
											Send back
										</Button>
									</div>
								</>
							)}
						</div>
					)}

					{i < step && (
						<div className="flex items-center gap-2 text-sm text-muted-foreground">
							{summary(i, brief, ceiling, fp, roster, plan)}
						</div>
					)}
				</Panel>
			))}
		</div>
	);
}

function summary(
	i: number,
	brief: string,
	ceiling: number,
	fp: Fp | null,
	roster: RosterRow[] | null,
	plan: Plan | null,
) {
	switch (i) {
		case 0:
			return brief.slice(0, 60) + (brief.length > 60 ? "…" : "");
		case 1: {
			if (!fp) return "—";
			return [fp.domain, fp.subdomain, fp.region, fp.payments].filter(Boolean).map(String).join(" / ") || "—";
		}
		case 2:
			return "lineage matched";
		case 3:
			return roster ? `${roster.length} roles assigned` : "roster proposed";
		case 4:
			return `ceiling $${ceiling.toFixed(2)}${plan ? ` · ${plan.nodes.length} nodes` : ""}`;
		default:
			return "";
	}
}

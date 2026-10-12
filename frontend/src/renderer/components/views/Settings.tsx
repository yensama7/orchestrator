import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/api";
import { Chip, Hint, Panel, PanelHeader, SectionTitle } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

type Model = { id: string; label: string; transports: string[] };
type Catalog = {
	providers: { provider: string; key_env: string | null; cli?: string; models: Model[] }[];
	roles: string[];
};
type Settings = {
	credentials: { model: string; transport: string; enabled: boolean; has_key: boolean; key_hint: string }[];
	agents: { agent: string; role: string; model: string; transport: string; enabled: boolean }[];
};
type Role = {
	name: string;
	description: string;
	skills: string[];
	resources: string[];
	egress: string[];
	researched_at: string | null;
};
type Preset = {
	name: string;
	description: string;
	model_hint: string;
	skills: string[];
	resources: string[];
	egress: string[];
};

type TestResult = { ok?: boolean; tested: boolean; working?: boolean; detail?: string };

// Native <select> styled to match the shadcn inputs. ponytail: a styled native
// select is accessible and handles hundreds of options with zero extra
// primitives — no Command/Popover needed for the searchable picker below.
const selectCls =
	"h-control-form rounded-md border border-border bg-input/50 px-2 text-sm text-foreground outline-none";

// one place deciding what a save result means, so ModelRow and ProviderPicker
// agree. The credential is persisted whenever ok !== false; a failed-closed save
// (ok:false) is NOT saved and its error must stay visible.
const notSaved = (r: TestResult) => r.ok === false;
const isErr = (r: TestResult) => r.ok === false || (r.tested && r.working === false);
const saveMsg = (r: TestResult) =>
	r.ok === false
		? `✗ ${r.detail || "not saved"}`
		: r.tested
			? r.working
				? "✓ key works"
				: `✗ ${r.detail} (saved — fix in the table below)`
			: null;

// above this many models per provider, the picker is a searchable dropdown
// instead of one row per model (OpenRouter's live catalogue is hundreds).
const DROPDOWN_OVER = 8;

async function post(url: string, body?: unknown): Promise<any> {
	const r = await fetch(url, {
		method: "POST",
		headers: { "content-type": "application/json" },
		body: body ? JSON.stringify(body) : undefined,
	});
	return r.json().catch(() => ({}));
}
async function del(url: string) {
	await fetch(url, { method: "DELETE" });
}

async function saveCred(model: string, transport: string, key: string): Promise<TestResult> {
	return post("/api/settings/credentials", { model, transport, api_key: key || null, enabled: true });
}

export function Settings() {
	const qc = useQueryClient();
	const { data: cat } = useApi<Catalog>("catalog");
	const { data: st } = useApi<Settings>("settings");
	const { data: roles } = useApi<Role[]>("roles");
	const refresh = () => {
		qc.invalidateQueries({ queryKey: ["settings"] });
		qc.invalidateQueries({ queryKey: ["agents"] });
		qc.invalidateQueries({ queryKey: ["credits"] });
	};
	const refreshRoles = () => qc.invalidateQueries({ queryKey: ["roles"] });
	if (!cat || !st) return null;

	const configured = new Set(st.credentials.map((c) => c.model));
	// researched roles extend the built-in hints; agents can bind to either.
	const roleNames = [...new Set([...cat.roles, ...(roles ?? []).map((r) => r.name)])];

	return (
		<div className="mx-auto flex max-w-[900px] flex-col gap-3.5 p-5">
			<h2 className="text-base font-semibold">Settings</h2>

			{/* ── models + keys ── */}
			<Panel className="p-4">
				<PanelHeader
					title="Models"
					help="Add a model and its API key, or pick subscription/local transport. Configured models can be assigned to agents below."
				/>
				{cat.providers.map((p) => (
					<div key={p.provider} className="mb-4">
						<SectionTitle className="my-1.5">
							{p.provider}
							{p.key_env && <span className="ml-2 font-normal text-passive">{p.key_env}</span>}
						</SectionTitle>
						{p.models.length > DROPDOWN_OVER ? (
							<ProviderPicker models={p.models} configured={configured} onSaved={refresh} />
						) : (
							p.models.map((m) => (
								<ModelRow key={m.id} m={m} configured={configured.has(m.id)} onSaved={refresh} />
							))
						)}
					</div>
				))}
			</Panel>

			{/* ── configured credentials ── */}
			<Panel className="p-4">
				<PanelHeader title="Configured models" />
				{st.credentials.length ? (
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead>Model</TableHead>
								<TableHead>Transport</TableHead>
								<TableHead>Key</TableHead>
								<TableHead>Enabled</TableHead>
								<TableHead>Status</TableHead>
								<TableHead />
							</TableRow>
						</TableHeader>
						<TableBody>
							{st.credentials.map((c) => (
								<CredRow key={c.model} c={c} onRemoved={refresh} />
							))}
						</TableBody>
					</Table>
				) : (
					<Hint>No models configured. Add one above to enable agents.</Hint>
				)}
			</Panel>

			{/* ── live credit monitoring ── */}
			<Panel className="p-4">
				<PanelHeader
					title="Credits & spend"
					help="OpenRouter balance (when used), API spend by provider, and subscription quota — all live."
				/>
				<CreditsPanel />
			</Panel>

			{/* ── local models ── */}
			<Panel className="p-4">
				<PanelHeader
					title="Local models"
					help="Download Ollama models to run nodes locally at zero marginal cost. Recommendations adapt to your detected GPU."
				/>
				<LocalModelsPanel onChanged={refresh} />
			</Panel>

			{/* ── roles ── */}
			<Panel className="p-4">
				<PanelHeader
					title="Roles"
					help="Define a role and the central agent researches its skills + resources (falling back to the ECC library), which get injected into every node prompt that uses the role."
				/>
				<RolesPanel roles={roles ?? []} onChanged={refreshRoles} />
			</Panel>

			{/* ── agents ── */}
			<Panel className="p-4">
				<PanelHeader
					title="Agents"
					help="An agent is a role bound to a configured model. The orchestrator runs the roster you build here."
				/>
				<AddAgent roles={roleNames} models={st.credentials} onAdded={refresh} />
				{st.agents.length ? (
					<Table className="mt-2.5">
						<TableHeader>
							<TableRow>
								<TableHead>Agent</TableHead>
								<TableHead>Role</TableHead>
								<TableHead>Model</TableHead>
								<TableHead>Transport</TableHead>
								<TableHead />
							</TableRow>
						</TableHeader>
						<TableBody>
							{st.agents.map((a) => (
								<TableRow key={a.agent}>
									<TableCell className="font-mono">{a.agent}</TableCell>
									<TableCell className="text-primary">{a.role}</TableCell>
									<TableCell className="font-mono text-muted-foreground">{a.model}</TableCell>
									<TableCell className="font-mono">{a.transport}</TableCell>
									<TableCell>
										<Button
											variant="ghost"
											size="sm"
											onClick={async () => {
												await del(`/api/settings/agents/${encodeURIComponent(a.agent)}`);
												refresh();
											}}
										>
											Remove
										</Button>
									</TableCell>
								</TableRow>
							))}
						</TableBody>
					</Table>
				) : (
					<Hint className="mt-2.5">No agents yet.</Hint>
				)}
			</Panel>
		</div>
	);
}

function CredRow({
	c,
	onRemoved,
}: {
	c: { model: string; transport: string; enabled: boolean; has_key: boolean; key_hint: string };
	onRemoved: () => void;
}) {
	const [res, setRes] = useState<TestResult | null>(null);
	const [busy, setBusy] = useState(false);
	return (
		<TableRow>
			<TableCell className="font-mono">{c.model}</TableCell>
			<TableCell className="font-mono">{c.transport}</TableCell>
			<TableCell className="font-mono text-muted-foreground">
				{c.transport === "api" ? (c.has_key ? c.key_hint : "— no key") : "n/a"}
			</TableCell>
			<TableCell>{c.enabled ? <span className="text-success">✓</span> : <span className="text-passive">off</span>}</TableCell>
			<TableCell>
				<Button
					variant="ghost"
					size="sm"
					disabled={busy}
					onClick={async () => {
						setBusy(true);
						setRes(await post(`/api/settings/credentials/${encodeURIComponent(c.model)}/test`));
						setBusy(false);
					}}
				>
					{busy ? "…" : "Test"}
				</Button>
				{res &&
					(res.working ? (
						<span className="ml-1.5 text-success" title={res.detail}>
							✓
						</span>
					) : (
						<span className="ml-1.5 text-destructive" title={res.detail}>
							✗
						</span>
					))}
			</TableCell>
			<TableCell>
				<Button
					variant="ghost"
					size="sm"
					onClick={async () => {
						await del(`/api/settings/credentials/${encodeURIComponent(c.model)}`);
						onRemoved();
					}}
				>
					Remove
				</Button>
			</TableCell>
		</TableRow>
	);
}

function ModelRow({ m, configured, onSaved }: { m: Model; configured: boolean; onSaved: () => void }) {
	const [transport, setTransport] = useState(m.transports[0]);
	const [key, setKey] = useState("");
	const [open, setOpen] = useState(false);
	const [busy, setBusy] = useState(false);
	const [res, setRes] = useState<TestResult | null>(null);
	return (
		<div className="flex items-center gap-2.5 border-b border-border/50 py-1.5">
			<span className="w-[200px] font-mono text-sm">{m.label}</span>
			<span className="w-[150px] font-mono text-xs text-muted-foreground">{m.id}</span>
			{configured ? (
				<Chip active>added</Chip>
			) : open ? (
				<>
					<select value={transport} onChange={(e) => setTransport(e.target.value)} className={selectCls}>
						{m.transports.map((t) => (
							<option key={t} value={t}>
								{t}
							</option>
						))}
					</select>
					{transport === "api" && (
						<Input
							placeholder="API key"
							value={key}
							type="password"
							className="w-[200px] font-mono"
							onChange={(e) => setKey(e.target.value)}
						/>
					)}
					<Button
						size="sm"
						disabled={busy}
						onClick={async () => {
							setBusy(true);
							setRes(null);
							const r = await saveCred(m.id, transport, key);
							setBusy(false);
							setRes(r);
							if (!notSaved(r)) {
								onSaved();
								setOpen(false);
								setKey("");
							}
						}}
					>
						{busy ? "Testing…" : "Save & test"}
					</Button>
					<Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
						Cancel
					</Button>
					{res && saveMsg(res) && (
						<span className={cn("text-xs", isErr(res) ? "text-destructive" : "text-success")} title={res.detail}>
							{saveMsg(res)}
						</span>
					)}
				</>
			) : (
				<Button variant="outline" size="sm" onClick={() => setOpen(true)}>
					Add
				</Button>
			)}
		</div>
	);
}

// Searchable single-select for providers with many models (OpenRouter live
// catalogue, installed local models). Pick one, set transport/key, add it.
// ponytail: native select + search input, not shadcn Command/Popover — same UX,
// far less code; add Command only if we need multi-select or rich rows.
function ProviderPicker({
	models,
	configured,
	onSaved,
}: {
	models: Model[];
	configured: Set<string>;
	onSaved: () => void;
}) {
	const [q, setQ] = useState("");
	const [picked, setPicked] = useState("");
	const [transport, setTransport] = useState("api");
	const [key, setKey] = useState("");
	const [busy, setBusy] = useState(false);
	const [res, setRes] = useState<TestResult | null>(null);

	const available = models.filter((m) => !configured.has(m.id));
	const filtered = q.trim()
		? available.filter((m) => (m.label + " " + m.id).toLowerCase().includes(q.toLowerCase())).slice(0, 50)
		: available.slice(0, 50);
	const model = available.find((m) => m.id === picked);
	useEffect(() => {
		if (model) setTransport(model.transports[0]);
	}, [picked]); // eslint-disable-line

	return (
		<div className="flex flex-wrap items-center gap-2">
			<Input
				placeholder={`search ${available.length} models…`}
				value={q}
				className="w-[200px]"
				onChange={(e) => setQ(e.target.value)}
			/>
			<select
				value={picked}
				onChange={(e) => {
					setPicked(e.target.value);
					setRes(null);
				}}
				className={cn(selectCls, "min-w-[260px]")}
			>
				<option value="">— pick a model —</option>
				{filtered.map((m) => (
					<option key={m.id} value={m.id}>
						{m.label} ({m.id})
					</option>
				))}
			</select>
			{model && (
				<>
					<select value={transport} onChange={(e) => setTransport(e.target.value)} className={selectCls}>
						{model.transports.map((t) => (
							<option key={t} value={t}>
								{t}
							</option>
						))}
					</select>
					{transport === "api" && (
						<Input
							placeholder="API key (optional if env set)"
							value={key}
							type="password"
							className="w-[200px] font-mono"
							onChange={(e) => setKey(e.target.value)}
						/>
					)}
					<Button
						size="sm"
						disabled={busy}
						onClick={async () => {
							setBusy(true);
							setRes(null);
							const r = await saveCred(model.id, transport, key);
							setBusy(false);
							setRes(r);
							if (!notSaved(r)) {
								onSaved();
								setPicked("");
								setKey("");
								setQ("");
							}
						}}
					>
						{busy ? "Testing…" : "Save & test"}
					</Button>
					{res && saveMsg(res) && (
						<span className={cn("text-xs", isErr(res) ? "text-destructive" : "text-success")} title={res.detail}>
							{saveMsg(res)}
						</span>
					)}
				</>
			)}
		</div>
	);
}

// ── live credit monitoring ───────────────────────────────────────────────────
type Credits = {
	openrouter: { configured: boolean; balance: { total: number; used: number; remaining: number } | null };
	api_spend: { total: number; by_provider: Record<string, number> };
	subscriptions: { cli: string; used: number; limit: number }[];
};
function CreditsPanel() {
	const { data } = useApi<Credits>("credits");
	if (!data) return <Hint>Loading…</Hint>;
	const or = data.openrouter;
	const providers = Object.entries(data.api_spend.by_provider);
	return (
		<div className="flex flex-col gap-3.5">
			<div>
				<SectionTitle>OpenRouter</SectionTitle>
				{!or.configured ? (
					<Hint>No OpenRouter key — add one above or set OPENROUTER_API_KEY.</Hint>
				) : or.balance ? (
					<div className="flex gap-4 text-sm">
						<span className="text-success">
							${or.balance.remaining.toFixed(2)}
							<span className="text-passive"> remaining</span>
						</span>
						<span className="text-muted-foreground">${or.balance.used.toFixed(2)} used</span>
						<span className="text-passive">${or.balance.total.toFixed(2)} total</span>
					</div>
				) : (
					<Hint className="text-destructive">Balance unavailable (key rejected or OpenRouter unreachable).</Hint>
				)}
			</div>
			<div>
				<SectionTitle>API spend (metered)</SectionTitle>
				{providers.length ? (
					<div className="flex flex-wrap gap-4 text-sm">
						<span className="text-warning">
							${data.api_spend.total.toFixed(2)}
							<span className="text-passive"> total</span>
						</span>
						{providers.map(([p, v]) => (
							<span key={p} className="text-muted-foreground">
								{p} ${v.toFixed(2)}
							</span>
						))}
					</div>
				) : (
					<Hint>No metered spend yet.</Hint>
				)}
			</div>
			<div>
				<SectionTitle>Subscription quota</SectionTitle>
				{data.subscriptions.length ? (
					data.subscriptions.map((s) => (
						<div key={s.cli} className="my-1 flex items-center gap-2">
							<span className="w-[70px] font-mono text-sm">{s.cli}</span>
							<div className="h-1.5 max-w-[240px] flex-1 overflow-hidden rounded-sm bg-interactive-active">
								<div
									className={cn("h-full rounded-sm", s.used >= s.limit ? "bg-destructive" : "bg-success")}
									style={{ width: `${Math.min(100, (s.used / s.limit) * 100)}%` }}
								/>
							</div>
							<span className="text-muted-foreground">
								{s.used}/{s.limit} req
							</span>
						</div>
					))
				) : (
					<Hint>No subscription agents configured.</Hint>
				)}
			</div>
		</div>
	);
}

// ── local model download ──────────────────────────────────────────────────────
type LocalStatus = {
	url: string | null;
	up: boolean;
	runtime: boolean;
	gpu: { available: boolean; name: string | null; vram_gb: number };
	installed: string[];
	recommended: { id: string; label: string; size_gb: number; min_vram_gb: number; use: string; fits: boolean }[];
};
function LocalModelsPanel({ onChanged }: { onChanged: () => void }) {
	const qc = useQueryClient();
	const { data } = useApi<LocalStatus>("local/status");
	const [progress, setProgress] = useState<Record<string, string>>({});
	const esRef = useRef<EventSource | null>(null);
	useEffect(() => () => esRef.current?.close(), []);

	if (!data) return <Hint>Loading…</Hint>;
	const gpu = data.gpu;

	const pull = (id: string) => {
		esRef.current?.close();
		setProgress((p) => ({ ...p, [id]: "starting…" }));
		const es = new EventSource(`/api/local/pull?model=${encodeURIComponent(id)}`);
		esRef.current = es;
		es.onmessage = (e) => {
			try {
				const d = JSON.parse(e.data);
				const pct = d.total ? ` ${Math.round(((d.completed || 0) / d.total) * 100)}%` : "";
				setProgress((p) => ({ ...p, [id]: (d.status || "pulling") + pct }));
			} catch {
				/* keep last */
			}
		};
		es.addEventListener("done", () => {
			es.close();
			setProgress((p) => ({ ...p, [id]: "✓ installed" }));
			qc.invalidateQueries({ queryKey: ["local/status"] });
			qc.invalidateQueries({ queryKey: ["catalog"] });
			onChanged();
		});
		es.addEventListener("error", (e) => {
			const d = (e as MessageEvent).data;
			es.close();
			// a generic transport close (no data) after "done" isn't a failure.
			if (!d) return;
			let msg = "failed";
			try {
				msg = JSON.parse(d).error;
			} catch {
				/* generic */
			}
			setProgress((p) => ({ ...p, [id]: "✗ " + msg }));
		});
	};

	return (
		<div className="flex flex-col gap-2.5">
			<Hint>
				Runtime:{" "}
				{data.up ? (
					<span className="text-success">Ollama up ({data.url})</span>
				) : data.runtime ? (
					<span className="text-destructive">
						configured but unreachable ({data.url}) — start it:{" "}
						<span className="font-mono">docker compose --profile local up</span>
					</span>
				) : (
					<span className="text-muted-foreground">
						none — set OLLAMA_URL or run{" "}
						<span className="font-mono">docker compose --profile local up</span>
					</span>
				)}
				{" · "}
				GPU:{" "}
				{gpu.available ? (
					<span className="text-success">
						{gpu.name} ({gpu.vram_gb} GB)
					</span>
				) : (
					<span className="text-muted-foreground">none detected — CPU-only recommendations</span>
				)}
			</Hint>
			<Table>
				<TableHeader>
					<TableRow>
						<TableHead>Model</TableHead>
						<TableHead>Size</TableHead>
						<TableHead>Use</TableHead>
						<TableHead>Fit</TableHead>
						<TableHead />
					</TableRow>
				</TableHeader>
				<TableBody>
					{data.recommended.map((m) => {
						const installed = data.installed.some((i) => i === m.id || i.startsWith(m.id + ":"));
						return (
							<TableRow key={m.id}>
								<TableCell className="font-mono">
									{m.label}
									<span className="ml-1.5 text-muted-foreground">{m.id}</span>
								</TableCell>
								<TableCell className="text-muted-foreground">{m.size_gb} GB</TableCell>
								<TableCell className="text-muted-foreground">{m.use}</TableCell>
								<TableCell>
									{m.fits ? (
										<span className="text-success" title="fits detected hardware">
											✓
										</span>
									) : (
										<span className="text-destructive" title={`wants ${m.min_vram_gb} GB VRAM`}>
											needs GPU
										</span>
									)}
								</TableCell>
								<TableCell>
									{installed ? (
										<Chip active>installed</Chip>
									) : (
										<Button
											variant="outline"
											size="sm"
											disabled={!data.up || /pulling|starting|%/.test(progress[m.id] || "")}
											onClick={() => pull(m.id)}
										>
											Download
										</Button>
									)}
									{progress[m.id] && (
										<span className="ml-2 font-mono text-muted-foreground">{progress[m.id]}</span>
									)}
								</TableCell>
							</TableRow>
						);
					})}
				</TableBody>
			</Table>
		</div>
	);
}

function RolesPanel({ roles, onChanged }: { roles: Role[]; onChanged: () => void }) {
	const [name, setName] = useState("");
	const [desc, setDesc] = useState("");
	const [busy, setBusy] = useState(false);
	const { data: presets } = useApi<Preset[]>("roles/presets");
	const have = new Set(roles.map((r) => r.name));
	const addable = (presets ?? []).filter((p) => !have.has(p.name));
	return (
		<>
			<div className="flex flex-wrap items-center gap-2">
				<Input
					placeholder="role name (e.g. data-eng)"
					value={name}
					className="w-[170px]"
					onChange={(e) => setName(e.target.value)}
				/>
				<Input
					placeholder="description (optional)"
					value={desc}
					className="min-w-[200px] flex-1"
					onChange={(e) => setDesc(e.target.value)}
				/>
				<Button
					disabled={!name.trim() || busy}
					onClick={async () => {
						setBusy(true);
						await post("/api/roles", { name: name.trim(), description: desc.trim() });
						setBusy(false);
						setName("");
						setDesc("");
						onChanged();
					}}
				>
					{busy ? "Researching…" : "Research & add"}
				</Button>
			</div>
			{addable.length ? (
				<div className="mt-2.5">
					<Hint className="mb-1.5">
						Starter roles (ECC) — skills, resources + egress pre-filled, no research call:
					</Hint>
					<div className="flex flex-wrap gap-1.5">
						{addable.map((p) => (
							<Button
								key={p.name}
								variant="ghost"
								size="sm"
								title={p.description}
								onClick={async () => {
									await post(`/api/roles/presets/${encodeURIComponent(p.name)}`);
									onChanged();
								}}
							>
								+ {p.name} <span className="text-muted-foreground">· {p.model_hint}</span>
							</Button>
						))}
					</div>
				</div>
			) : null}
			{roles.length ? (
				<Table className="mt-2.5">
					<TableHeader>
						<TableRow>
							<TableHead>Role</TableHead>
							<TableHead>Skills</TableHead>
							<TableHead>Resources</TableHead>
							<TableHead>Egress</TableHead>
							<TableHead />
						</TableRow>
					</TableHeader>
					<TableBody>
						{roles.map((r) => (
							<TableRow key={r.name}>
								<TableCell className="text-primary">{r.name}</TableCell>
								<TableCell className="text-muted-foreground">{r.skills.join(", ") || "—"}</TableCell>
								<TableCell className="text-muted-foreground">{r.resources.join(", ") || "—"}</TableCell>
								<TableCell className="text-muted-foreground">
									{r.egress?.length ? r.egress.join(", ") : "deny-all"}
								</TableCell>
								<TableCell>
									<Button
										variant="ghost"
										size="sm"
										onClick={async () => {
											await del(`/api/roles/${encodeURIComponent(r.name)}`);
											onChanged();
										}}
									>
										Remove
									</Button>
								</TableCell>
							</TableRow>
						))}
					</TableBody>
				</Table>
			) : (
				<Hint className="mt-2.5">No researched roles yet. Add one above, or pick a starter role.</Hint>
			)}
		</>
	);
}

function AddAgent({
	roles,
	models,
	onAdded,
}: {
	roles: string[];
	models: { model: string; transport: string }[];
	onAdded: () => void;
}) {
	const [agent, setAgent] = useState("");
	const [role, setRole] = useState(roles[0]);
	const [model, setModel] = useState(models[0]?.model ?? "");
	if (!models.length) return <Hint>Add a model first.</Hint>;
	const transport = models.find((m) => m.model === model)?.transport ?? "api";
	return (
		<div className="flex flex-wrap items-center gap-2">
			<Input
				placeholder="agent name (e.g. dev-a)"
				value={agent}
				className="w-[170px]"
				onChange={(e) => setAgent(e.target.value)}
			/>
			<select value={role} onChange={(e) => setRole(e.target.value)} className={selectCls}>
				{roles.map((r) => (
					<option key={r}>{r}</option>
				))}
			</select>
			<select value={model} onChange={(e) => setModel(e.target.value)} className={selectCls}>
				{models.map((m) => (
					<option key={m.model}>{m.model}</option>
				))}
			</select>
			<Chip>{transport}</Chip>
			<Button
				disabled={!agent.trim()}
				onClick={async () => {
					await post("/api/settings/agents", { agent, role, model, transport });
					setAgent("");
					onAdded();
				}}
			>
				Add agent
			</Button>
		</div>
	);
}

import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useApi } from "@/lib/api";
import { useRun } from "@/hooks/use-run";
import CodeEditor from "@/components/CodeEditor";
import { EmptyState } from "@/components/common";
import { Button } from "@/components/ui/button";
import { resolve } from "@/lib/lang-registry";
import { cn } from "@/lib/utils";

type Ws = {
	worktree: string;
	empty: boolean;
	tree: { folder: string; files: { name: string; ext: string; held: string | null }[] }[];
	open: {
		name: string;
		ext: string;
		mode: string;
		why: string;
		lines: number;
		chars: number;
		content: string;
		blame: string[];
		held: string | null;
	} | null;
	gate: {
		ready: boolean;
		file?: string;
		reason?: string;
		offer?: { label: string };
		services?: { name: string; health: string }[];
	};
};

export function Workspace() {
	const qc = useQueryClient();
	const run = useRun().run?.id;
	const { data } = useApi<Ws>("workspace", run);
	const rq = run ? `?run=${encodeURIComponent(run)}` : "";
	const [selected, setSelected] = useState<string | null>(null);
	const [importing, setImporting] = useState(false);
	const [runMsg, setRunMsg] = useState<string | null>(null);
	const inputRef = useRef<HTMLInputElement>(null);
	if (!data) return null;

	const runCompose = async () => {
		setRunMsg("Starting…");
		const r = await fetch(`/api/runs/${run ?? "current"}/run`, { method: "POST" }).then((x) => x.json());
		setRunMsg(r.started ? `${r.kind} · ${r.file}` : `can't run: ${r.reason}`);
	};

	const importFolder = async (files: FileList) => {
		setImporting(true);
		try {
			const fd = new FormData();
			const paths: string[] = [];
			Array.from(files).forEach((f) => {
				fd.append("files", f);
				paths.push((f as any).webkitRelativePath || f.name);
			});
			fd.append("paths", JSON.stringify(paths));
			await fetch(`/api/workspace/import${rq}`, { method: "POST", body: fd });
			setSelected(null);
			qc.invalidateQueries({ queryKey: ["workspace"] });
		} finally {
			setImporting(false);
		}
	};

	const clear = async () => {
		await fetch(`/api/workspace${rq}`, { method: "DELETE" });
		setSelected(null);
		qc.invalidateQueries({ queryKey: ["workspace"] });
	};

	const importInput = (
		<input
			ref={inputRef}
			type="file"
			hidden
			multiple
			{...({ webkitdirectory: "", directory: "" } as any)}
			onChange={(e) => e.target.files && importFolder(e.target.files)}
		/>
	);

	if (data.empty) {
		return (
			<div className="flex h-full flex-col items-center justify-center gap-3">
				{importInput}
				<EmptyState
					message="No worktree yet. Import a folder to browse and run it."
					action={
						<Button disabled={importing} onClick={() => inputRef.current?.click()}>
							{importing ? "Importing…" : "Import folder"}
						</Button>
					}
				/>
			</div>
		);
	}

	const f = data.open;
	const active = selected ?? f?.name ?? null;
	const showEditor = f && active === f.name;
	const res = f ? resolve(f.name) : null;

	return (
		<div className="grid h-full grid-cols-[218px_1fr] overflow-hidden">
			{/* file tree */}
			<div className="overflow-y-auto border-r border-border bg-sidebar">
				<div className="flex items-center gap-1.5 px-3 py-2 font-mono text-xs text-muted-foreground">
					<span className="flex-1 truncate">{data.worktree}</span>
					{importInput}
					<button
						className="rounded px-1.5 text-muted-foreground hover:text-foreground"
						onClick={() => inputRef.current?.click()}
						title="Import folder"
					>
						＋
					</button>
					<button
						className="rounded px-1.5 text-muted-foreground hover:text-foreground"
						onClick={clear}
						title="Clear worktree"
					>
						✕
					</button>
				</div>
				{data.tree.map((grp) => (
					<div key={grp.folder}>
						<div className="px-3 pt-2 pb-1 text-xs text-muted-foreground">{grp.folder}</div>
						{grp.files.map((file) => (
							<div
								key={grp.folder + file.name}
								className={cn(
									"flex cursor-pointer items-center gap-2 py-1.5 pr-3 pl-5 font-mono text-xs text-muted-foreground hover:text-foreground",
									file.name === active &&
										"border-l-2 border-primary bg-interactive-active pl-[18px] text-foreground",
								)}
								onClick={() => setSelected(file.name)}
							>
								<span>{file.name}</span>
								{file.held && <span title={`held by ${file.held}`}>🔒</span>}
								<span className="ml-auto rounded bg-interactive-active px-1.5 text-[10px] text-passive">
									{file.ext}
								</span>
							</div>
						))}
					</div>
				))}
			</div>

			{/* main */}
			<div className="flex min-w-0 flex-col bg-background">
				<div className="border-b border-border px-3.5 py-2 font-mono text-[11px] text-muted-foreground">
					<span>{data.worktree}</span>
					{active && (
						<>
							<span className="mx-1.5 text-passive">›</span>
							<span>
								{data.tree.find((g) => g.files.some((x) => x.name === active))?.folder.replace(/\/$/, "")}
							</span>
							<span className="mx-1.5 text-passive">›</span>
							<span className="text-foreground">{active}</span>
						</>
					)}
				</div>

				{showEditor && f && res ? (
					<>
						<div className="flex items-center gap-2.5 border-b border-border px-3.5 py-2 font-mono text-xs">
							<span className="rounded bg-interactive-active px-1.5 text-[10px] text-passive">
								{f.ext || "txt"}
							</span>
							<span className="text-foreground">{f.name}</span>
							<span className="text-passive">
								· {f.mode} · {f.lines} lines · {f.chars} chars
							</span>
							<span
								className="cursor-help text-passive"
								title={`extension .${f.ext} → tier ${res.tier} → ${res.mode}`}
							>
								ⓘ why
							</span>
							{res.tier === 3 && <span className="text-destructive">· generic fallback</span>}
							{f.held && <span className="ml-auto text-warning">🔒 held by {f.held}</span>}
						</div>
						<div className="min-h-0 flex-1">
							<CodeEditor filename={f.name} content={f.content} blame={f.blame} readOnly={!!f.held} />
						</div>
					</>
				) : (
					<div className="flex flex-1 items-center justify-center">
						<EmptyState message="Select a file with a local copy to view it." />
					</div>
				)}

				<div className="flex items-center gap-3 border-t border-border bg-sidebar px-3.5 py-2 font-mono text-xs">
					{data.gate.ready ? (
						<>
							<span className="text-success">{data.gate.file} ✓</span>
							<Button size="sm" onClick={runCompose}>
								▶ Run
							</Button>
							{runMsg && <span className="text-passive">{runMsg}</span>}
							{data.gate.services?.map((s) => (
								<span key={s.name} className="inline-flex items-center gap-1.5 text-muted-foreground">
									<span
										className={cn(
											"size-2 rounded-full",
											s.health === "up" ? "bg-success" : "bg-destructive",
										)}
									/>
									{s.name}
								</span>
							))}
						</>
					) : (
						<EmptyState
							message={
								data.gate.reason === "no_compose"
									? "No compose file. Generate one from the Dockerfile?"
									: "Not containerised yet — no compose file in the imported worktree."
							}
							action={<Button variant="outline">{data.gate.offer?.label}</Button>}
						/>
					)}
				</div>
			</div>
		</div>
	);
}

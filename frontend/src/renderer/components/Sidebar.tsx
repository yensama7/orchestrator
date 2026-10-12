import { Link } from "@tanstack/react-router";
import {
	Bot,
	Database,
	FolderGit2,
	GitBranch,
	LayoutDashboard,
	Plus,
	Scale,
	Settings,
	type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useRun } from "@/hooks/use-run";
import { useRunStore } from "@/stores/run-store";
import { useUiStore } from "@/stores/ui-store";
import { ModeBadge } from "@/components/ModeBadge";

// Nav mirrors the old App.tsx VIEWS, with Board replacing "New run" as the
// landing. Wired to the router via <Link>; `to` paths match the file-based
// routes under routes/_shell.*.
//
// ponytail: skipped the shadcn `sidebar` primitive (collapsible rail + mobile
// Sheet + cookie persistence). Static rail here; add it when collapse/mobile
// are actually needed.
export const NAV_ITEMS: { to: string; label: string; icon: LucideIcon }[] = [
	{ to: "/", label: "Board", icon: LayoutDashboard },
	{ to: "/lineage", label: "Lineage", icon: GitBranch },
	{ to: "/memory", label: "Memory", icon: Database },
	{ to: "/agents", label: "Agents", icon: Bot },
	{ to: "/dissent", label: "Dissent", icon: Scale },
	{ to: "/workspace", label: "Workspace", icon: FolderGit2 },
	{ to: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
	const mode = useUiStore((s) => s.mode);
	const { run, runs } = useRun();
	const selectedRun = useRunStore((s) => s.selectedRun);
	const setSelectedRun = useRunStore((s) => s.setSelectedRun);

	return (
		<aside className="flex h-full w-56 shrink-0 flex-col border-r border-border bg-sidebar text-sidebar-foreground">
			<div className="flex h-12 items-center gap-2 px-4">
				<span className="size-2 rounded-full bg-primary" aria-hidden />
				<span className="text-sm font-semibold tracking-tight">Lineage</span>
			</div>

			{mode === "expert" && (
				<div className="px-2 pb-2">
					<Link
						to="/newrun"
						className="flex h-8 items-center gap-2 rounded-md border border-border px-2.5 text-sm text-foreground transition-colors hover:bg-interactive-hover"
					>
						<Plus className="size-4 shrink-0" aria-hidden />
						New run
					</Link>
				</div>
			)}

			<nav className="flex flex-1 flex-col gap-0.5 px-2 py-2">
				{NAV_ITEMS.map(({ to, label, icon: Icon }) => (
					<Link
						key={to}
						to={to}
						activeOptions={{ exact: to === "/" }}
						className={cn(
							"flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors",
							"text-muted-foreground hover:bg-interactive-hover hover:text-foreground",
						)}
						activeProps={{ className: "bg-interactive-active text-foreground", "aria-current": "page" }}
					>
						<Icon className="size-4 shrink-0" aria-hidden />
						{label}
					</Link>
				))}
			</nav>

			{/* Project / run section — live run switcher + mode + spec + security footer. */}
			<div className="border-t border-border px-3 py-3 text-xs">
				{runs && runs.runs.length > 0 ? (
					// Native select: closes on its own and the OS manages the popup, so
					// there's no portal/overlay to get stuck open. [&>option] colors keep
					// the list readable in dark mode (see Settings.selectCls).
					<select
						value={selectedRun ?? runs.current}
						onChange={(e) =>
							setSelectedRun(e.target.value === runs.current ? null : e.target.value)
						}
						className="h-control-form w-full rounded-md border border-border bg-input/50 px-2 text-xs text-foreground outline-none [&>option]:bg-popover [&>option]:text-popover-foreground"
					>
						{runs.runs.map((r) => (
							<option key={r.id} value={r.id}>
								{r.name} · {r.status} · {r.mode}
								{r.current ? " · current" : ""}
							</option>
						))}
					</select>
				) : (
					<div className="font-medium text-foreground">{run?.label ?? "No run selected"}</div>
				)}

				{run && (
					<>
						<div className="mt-2 flex items-center gap-2">
							<ModeBadge mode={run.mode} />
							<span className="truncate text-muted-foreground" title={run.spec}>
								{run.spec}
							</span>
						</div>
						<div className="mt-2 space-y-0.5 font-mono text-[10.5px] leading-relaxed text-passive">
							<div>{run.navfoot.egress}</div>
							<div>{run.navfoot.agents}</div>
							<div>{run.navfoot.blocked}</div>
						</div>
					</>
				)}
			</div>
		</aside>
	);
}

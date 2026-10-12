import {
	Bot,
	Database,
	FolderGit2,
	GitBranch,
	LayoutDashboard,
	Scale,
	Settings,
	type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

// Nav mirrors the old App.tsx VIEWS, with Board replacing "New run" as the
// landing per the refactor plan. Wired to local state via props for now; the
// router takes over in Phase 2.
//
// ponytail: skipped the shadcn `sidebar` primitive (collapsible rail + mobile
// Sheet + cookie persistence). Static rail here; add it when collapse/mobile
// are actually needed.
export type NavKey = "board" | "lineage" | "memory" | "agents" | "dissent" | "workspace" | "settings";

export const NAV_ITEMS: { key: NavKey; label: string; icon: LucideIcon }[] = [
	{ key: "board", label: "Board", icon: LayoutDashboard },
	{ key: "lineage", label: "Lineage", icon: GitBranch },
	{ key: "memory", label: "Memory", icon: Database },
	{ key: "agents", label: "Agents", icon: Bot },
	{ key: "dissent", label: "Dissent", icon: Scale },
	{ key: "workspace", label: "Workspace", icon: FolderGit2 },
	{ key: "settings", label: "Settings", icon: Settings },
];

export function Sidebar({ active, onNavigate }: { active: NavKey; onNavigate: (key: NavKey) => void }) {
	return (
		<aside className="flex h-full w-56 shrink-0 flex-col border-r border-border bg-sidebar text-sidebar-foreground">
			<div className="flex h-12 items-center gap-2 px-4">
				<span className="size-2 rounded-full bg-primary" aria-hidden />
				<span className="text-sm font-semibold tracking-tight">Lineage</span>
			</div>

			<nav className="flex flex-1 flex-col gap-0.5 px-2 py-2">
				{NAV_ITEMS.map(({ key, label, icon: Icon }) => {
					const isActive = key === active;
					return (
						<button
							key={key}
							type="button"
							onClick={() => onNavigate(key)}
							aria-current={isActive ? "page" : undefined}
							className={cn(
								"flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors",
								isActive
									? "bg-interactive-active text-foreground"
									: "text-muted-foreground hover:bg-interactive-hover hover:text-foreground",
							)}
						>
							<Icon className="size-4 shrink-0" aria-hidden />
							{label}
						</button>
					);
				})}
			</nav>

			{/* Project / run section — live data lands in Phase 3. */}
			<div className="border-t border-border px-4 py-3 text-xs text-muted-foreground">
				<div className="font-medium text-foreground">No run selected</div>
				<div className="mt-0.5">Start a run to see it here.</div>
			</div>
		</aside>
	);
}

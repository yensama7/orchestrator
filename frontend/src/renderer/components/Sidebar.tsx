import { Link } from "@tanstack/react-router";
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
// landing. Wired to the router via <Link> (Phase 2); `to` paths match the
// file-based routes under routes/_shell.*.
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
	return (
		<aside className="flex h-full w-56 shrink-0 flex-col border-r border-border bg-sidebar text-sidebar-foreground">
			<div className="flex h-12 items-center gap-2 px-4">
				<span className="size-2 rounded-full bg-primary" aria-hidden />
				<span className="text-sm font-semibold tracking-tight">Lineage</span>
			</div>

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

			{/* Project / run section — live data lands in Phase 3. */}
			<div className="border-t border-border px-4 py-3 text-xs text-muted-foreground">
				<div className="font-medium text-foreground">No run selected</div>
				<div className="mt-0.5">Start a run to see it here.</div>
			</div>
		</aside>
	);
}

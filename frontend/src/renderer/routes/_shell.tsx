import { createFileRoute, Outlet, useRouterState } from "@tanstack/react-router";
import { Sidebar, NAV_ITEMS } from "@/components/Sidebar";
import { ShellTopbar } from "@/components/ShellTopbar";
import { CenterPanelShell } from "@/components/CenterPanelShell";
import { SpendRail } from "@/components/SpendRail";

export const Route = createFileRoute("/_shell")({ component: ShellLayout });

// Persistent app shell: Sidebar + Topbar survive route changes; only the
// <Outlet> content swaps. Title is derived from the active nav item (run detail
// falls back to "Run"). Replaces the Phase-1 local useState(view) switch.
function ShellLayout() {
	const pathname = useRouterState({ select: (s) => s.location.pathname });
	const title = NAV_ITEMS.find((v) => v.to === pathname)?.label ?? (pathname.startsWith("/run/") ? "Run" : "Board");
	return (
		<div className="flex h-full">
			<Sidebar />
			<div className="flex min-w-0 flex-1 flex-col">
				<ShellTopbar title={title} spendRail={<SpendRail />} />
				<CenterPanelShell>
					<Outlet />
				</CenterPanelShell>
			</div>
		</div>
	);
}

import { createFileRoute, Outlet, useRouterState } from "@tanstack/react-router";
import { Sidebar, NAV_ITEMS } from "@/components/Sidebar";
import { ShellTopbar } from "@/components/ShellTopbar";
import { CenterPanelShell } from "@/components/CenterPanelShell";
import { SpendRail } from "@/components/SpendRail";
import { Ticker } from "@/components/Ticker";
import { RunProvider } from "@/hooks/use-run";

export const Route = createFileRoute("/_shell")({ component: ShellLayout });

// Persistent app shell: Sidebar + Topbar + Ticker survive route changes; only
// the <Outlet> content swaps. RunProvider owns the single SSE stream + run reads
// so the sidebar switcher, spend rail, ticker, and every view share one source.
function ShellLayout() {
	const pathname = useRouterState({ select: (s) => s.location.pathname });
	const title =
		NAV_ITEMS.find((v) => v.to === pathname)?.label ?? (pathname.startsWith("/run/") ? "Run" : "Board");
	return (
		<RunProvider>
			<div className="flex h-full">
				<Sidebar />
				<div className="flex min-w-0 flex-1 flex-col">
					<ShellTopbar title={title} spendRail={<SpendRail />} />
					<CenterPanelShell>
						<Outlet />
					</CenterPanelShell>
					<Ticker />
				</div>
			</div>
		</RunProvider>
	);
}

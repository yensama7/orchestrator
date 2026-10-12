import "./lib/apply-initial-theme";
import { useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./styles.css";
import { Sidebar, NAV_ITEMS, type NavKey } from "./components/Sidebar";
import { ShellTopbar } from "./components/ShellTopbar";
import { CenterPanelShell } from "./components/CenterPanelShell";
import { SpendRail } from "./components/SpendRail";

const queryClient = new QueryClient();

// Phase 1 shell: Sidebar + Topbar on shadcn primitives + tokens, Simple/Expert
// and theme in the zustand ui-store. Views are placeholders — the router lands
// in Phase 2, the real views in Phase 3. Local nav state here for now.
function Shell() {
	const [active, setActive] = useState<NavKey>("board");
	const title = NAV_ITEMS.find((v) => v.key === active)?.label ?? "Board";
	return (
		<div className="flex h-full">
			<Sidebar active={active} onNavigate={setActive} />
			<div className="flex min-w-0 flex-1 flex-col">
				<ShellTopbar title={title} spendRail={<SpendRail />} />
				<CenterPanelShell>
					<div className="p-6 text-sm text-muted-foreground">
						<span className="font-medium text-foreground">{title}</span> — placeholder (Phase 3).
					</div>
				</CenterPanelShell>
			</div>
		</div>
	);
}

createRoot(document.getElementById("root") as HTMLElement).render(
	<QueryClientProvider client={queryClient}>
		<Shell />
	</QueryClientProvider>,
);

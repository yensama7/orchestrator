import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

// Shared page frame: sidebar-colored outer inset with a bordered inner surface,
// adapted from the reference's CenterPanelShell minus the Electron
// titlebar/fullscreen clearance logic (no custom window chrome here).
export function CenterPanelShell({ className, children }: { className?: string; children: ReactNode }) {
	return (
		<div className="min-h-0 flex-1 bg-sidebar p-2">
			<div className={cn("h-full overflow-auto rounded-lg border border-border bg-background", className)}>
				{children}
			</div>
		</div>
	);
}

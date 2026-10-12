import type * as React from "react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Dot } from "@/components/charts";

// Small shared view chrome. These replace the old Panel/PanelHeader/Row/Hint/
// EmptyState helpers from web/src/components.tsx, re-expressed on the graphite
// tokens. Panels themselves are now shadcn <Card>; these are the leftover
// repeated bits (a labelled value row, a hint line, an empty state).

// Flat hairline panel — the old `.panel`. Preferred over shadcn <Card> here
// because DESIGN.md calls for hairline borders, not the Card's shadow + ring.
export function Panel({ children, className, ...rest }: React.ComponentProps<"div">) {
	return (
		<div className={cn("rounded-lg border border-border bg-card", className)} {...rest}>
			{children}
		</div>
	);
}

export function PanelHeader({ title, help, children }: { title: string; help?: string; children?: ReactNode }) {
	return (
		<div className="mb-2.5 flex items-center gap-2">
			<h3 className="text-xs font-semibold text-foreground">{title}</h3>
			{help && (
				<span
					className="grid size-4 cursor-help place-items-center rounded-full border border-border text-[10px] text-passive"
					title={help}
				>
					?
				</span>
			)}
			{children && <span className="ml-auto">{children}</span>}
		</div>
	);
}

export function Hint({ children, className }: { children: ReactNode; className?: string }) {
	return <p className={cn("text-xs text-muted-foreground", className)}>{children}</p>;
}

export function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
	return (
		<div className="flex flex-col items-start gap-2 py-3">
			<p className="text-sm text-muted-foreground">{message}</p>
			{action}
		</div>
	);
}

// label + optional status dot + right-aligned mono number, hairline separated.
export function Row({ color, label, value }: { color?: string; label: ReactNode; value?: ReactNode }) {
	return (
		<div className="flex items-center gap-2 border-b border-border/50 py-1.5 last:border-b-0">
			{color && <Dot color={color} />}
			<span className="flex-1 text-sm">{label}</span>
			{value != null && <span className="font-mono text-xs text-muted-foreground">{value}</span>}
		</div>
	);
}

// Mono toggle chip (old `.chip` / `.chip.active`). Used for filters + small
// toggles across Lineage, Dissent, NewRun, Settings.
export function Chip({ active, children, onClick }: { active?: boolean; children: ReactNode; onClick?: () => void }) {
	return (
		<button
			type="button"
			onClick={onClick}
			className={cn(
				"rounded-md border px-2 py-1 font-mono text-xs transition-colors",
				active
					? "border-primary bg-primary text-primary-foreground"
					: "border-border text-muted-foreground hover:text-foreground",
			)}
		>
			{children}
		</button>
	);
}

// Section heading used between stacked cards (old `.section-title`).
export function SectionTitle({ children, className }: { children: ReactNode; className?: string }) {
	return <h2 className={cn("text-xs font-semibold text-muted-foreground", className)}>{children}</h2>;
}

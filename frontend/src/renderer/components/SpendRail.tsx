// Topbar spend rail. Phase 1 is a static placeholder in the shell slot; Phase 3
// wires it to the live `useStream` spend ticks + quota.
export function SpendRail() {
	return (
		<div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
			<span className="size-1.5 rounded-full bg-success" aria-hidden />
			<span>$0.00</span>
			<span className="text-passive">/ idle</span>
		</div>
	);
}

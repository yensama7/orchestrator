// Phase-2 stand-in: routes exist and navigate; real views land in Phase 3.
// ponytail: delete this once every route has its ported view.
export function ViewPlaceholder({ name }: { name: string }) {
	return (
		<div className="p-6 text-sm text-muted-foreground">
			<span className="font-medium text-foreground">{name}</span> — placeholder (Phase 3).
		</div>
	);
}

import { Link } from "@tanstack/react-router";
import { useApi } from "@/lib/api";
import { bucket, LANES, type BoardCard, type Lane } from "@/lib/board-presentation";
import { Dot } from "@/components/charts";
import { ModeBadge } from "@/components/ModeBadge";
import { EmptyState, Panel } from "@/components/common";

// Live Kanban (§P4). Cards = runs, derived from /api/board; SSE deltas invalidate
// the query (use-run.tsx) so lanes re-bucket live as runs verify / dissents open.
// Click a card → /run/:id. Lane bucketing is the pure board-presentation fn.
export function Board() {
	const { data } = useApi<{ cards: BoardCard[] }>("board");
	if (!data) return null;
	if (!data.cards.length)
		return (
			<div className="p-5">
				<Panel className="p-4">
					<EmptyState message="No runs yet. Start one from New run to populate the board." />
				</Panel>
			</div>
		);

	const lanes = bucket(data.cards);
	return (
		<div className="flex gap-3 overflow-x-auto p-5">
			{LANES.map((l) => (
				<BoardLane key={l.key} lane={l.key} label={l.label} color={l.color} cards={lanes[l.key]} />
			))}
		</div>
	);
}

function BoardLane({ lane, label, color, cards }: { lane: Lane; label: string; color: string; cards: BoardCard[] }) {
	return (
		<section className="flex w-64 shrink-0 flex-col gap-2" aria-label={label} data-lane={lane}>
			<header className="flex items-center gap-2 px-1">
				<Dot color={color} />
				<h3 className="text-xs font-semibold text-foreground">{label}</h3>
				<span className="ml-auto font-mono text-xs text-muted-foreground">{cards.length}</span>
			</header>
			<div className="flex flex-col gap-2">
				{cards.map((c) => (
					<SessionCard key={c.id} card={c} />
				))}
			</div>
		</section>
	);
}

function SessionCard({ card }: { card: BoardCard }) {
	const cpv = card.cost_per_verified;
	return (
		<Link
			to="/run/$runId"
			params={{ runId: card.id }}
			className="block rounded-lg border border-border bg-card p-3 transition-colors hover:border-primary"
		>
			<div className="flex items-center gap-2">
				<span className="truncate text-sm font-medium text-foreground">{card.name}</span>
				{card.open_dissent && (
					<span className="shrink-0 font-mono text-[10px] text-warning" title="A dissent is open — needs you">
						needs you
					</span>
				)}
				<span className="ml-auto shrink-0">
					<ModeBadge mode={card.mode} />
				</span>
			</div>
			<p className="mt-1 font-mono text-[10px] text-passive">{card.label}</p>
			<div className="mt-2 flex items-center justify-between font-mono text-xs text-muted-foreground">
				<span title="spend so far">${card.spent.toFixed(2)}</span>
				<span title="verified results">{card.verified_count} verified</span>
				<span title="cost per verified result">{cpv != null ? `$${cpv.toFixed(2)}/v` : "—"}</span>
			</div>
		</Link>
	);
}
